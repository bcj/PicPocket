from __future__ import annotations

"""Support for using PostgreSQL as a backend"""
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

import psycopg
import psycopg.sql
from psycopg import AsyncConnection
from psycopg.errors import UndefinedTable

from picpocket.api import CredentialType
from picpocket.configuration import Configuration
from picpocket.database.dbapi import DbApi
from picpocket.database.logic import SQL, Comparator, Types
from picpocket.version import POSTGRES_VERSION as SCHEMA_VERSION
from picpocket.version import Version

LOGGER = logging.getLogger("picpocket.postgres")

TYPES_FILE = Path(__file__).absolute().parent / "postgres_types.sql"
SCHEMA_FILE = TYPES_FILE.parent / "postgres_schema.sql"


class PostgreSQL(SQL):
    """SQL support for PostgreSQL"""

    def __init__(self):
        pass

    @property
    def types(self) -> set[Types]:
        return {
            Types.BOOLEAN,
            Types.DATETIME,
            Types.ID,
            Types.JSON,
            Types.NUMBER,
            Types.TEXT,
        }

    @property
    def arrays(self) -> bool:
        return True

    @property
    def param(self) -> str:
        return "%s"

    def format(self, statement: str, *parts) -> psycopg.sql.Composable:
        formatted = psycopg.sql.SQL(statement)

        return formatted.format(*parts)

    def join(self, joiner: str, parts: Iterable) -> psycopg.sql.Composable:
        return psycopg.sql.SQL(joiner).join(parts)

    def identifier(self, identifier: str) -> psycopg.sql.Identifier:
        return psycopg.sql.Identifier(identifier)

    def literal(self, literal: Any) -> psycopg.sql.Literal:
        return psycopg.sql.Literal(literal)

    def placeholder(self, placeholder: str) -> psycopg.sql.Placeholder:
        return psycopg.sql.Placeholder(placeholder)


class Postgres(DbApi):
    """DbApi implementation for PostgreSQL"""

    BACKEND_NAME = "postgres"
    CREDENTIAL_TYPE = CredentialType.PASSWORD
    TEXT_COMPARATORS = {
        Comparator.EQUALS,
        Comparator.STARTS_WITH,
        Comparator.ENDS_WITH,
        Comparator.CONTAINS,
    }

    logger = LOGGER

    @classmethod
    def load(cls, configuration: Configuration) -> Postgres:
        return cls(configuration)

    def __init__(self, configuration: Configuration):
        self._configuration = configuration
        self._mounts: dict[int, Path] = {}
        self._sql = PostgreSQL()

    @property
    def configuration(self) -> Configuration:
        return self._configuration

    @property
    def mounts(self) -> dict[int, Path]:
        return self._mounts

    @property
    def sql(self) -> PostgreSQL:
        return self._sql

    @asynccontextmanager
    async def cursor(self, connection: AsyncConnection, commit: bool = False):
        cursor = connection.cursor()

        try:
            yield cursor

            if commit:
                await connection.commit()
        except Exception:
            LOGGER.exception("Error occurred, rolling back")
            await connection.rollback()
            raise
        finally:
            await cursor.close()

    @classmethod
    def parse_connection_info(
        cls, directory: Path, *, store_credentials: Optional[bool] = None, **kwargs
    ) -> tuple[dict[str, str | int | bool], Optional[str]]:
        info: dict[str, str | int | bool] = {}

        host = kwargs.get("host")
        if host:
            if not isinstance(host, str):
                raise TypeError(f"Invalid host. Expected string, found: {host!r}")

            info["host"] = host

        port = kwargs.get("port")
        if not port:
            port = 5432
        elif not isinstance(port, int):
            raise TypeError(f"Invalid port. Expected int, found: {port!r}")

        info["port"] = port

        for key in ("dbname", "user"):
            value = kwargs.get(key, "picpocket")
            if value is not None:
                if not isinstance(value, str):
                    raise TypeError(f"Invalid {key}. Expected string, found: {value!r}")

            info[key] = value

        password = kwargs.get("password") or ""
        if not isinstance(password, str):
            raise TypeError(
                f"Invalid password. Expected string, found type {type(password)}"
            )

        if store_credentials or (store_credentials is None and not password):
            info["password"] = password
        else:
            info["password"] = True

        return info, password

    async def connect(self) -> AsyncConnection:
        backend_info = self.configuration.contents["backend"]
        if backend_info["type"] != self.BACKEND_NAME:
            raise ValueError(f"Wrong backend! {backend_info['type']}")

        info = backend_info["connection"]

        if info.get("password") is True:
            info = {**info, "password": self.configuration.credentials}

        return await AsyncConnection.connect(**info)

    async def initialize(self):
        async with (
            await self.connect() as connection,
            psycopg.AsyncClientCursor(connection) as cursor,
        ):
            LOGGER.debug("confirming tables don't already exist")
            existing = set()
            await cursor.execute(
                "SELECT tablename FROM pg_tables WHERE tablename = ANY(%s)",
                (list(_get_tables()),),
            )
            for (name,) in await cursor.fetchall():
                existing.add(name)

            if existing:
                raise ValueError(
                    "Can't create database, tables already exist: {}".format(
                        ", ".join(sorted(existing))
                    )
                )

            LOGGER.debug("Creating types")
            await cursor.execute(TYPES_FILE.read_text())
            LOGGER.debug("Creating tables")
            await cursor.execute(SCHEMA_FILE.read_text())

            await cursor.execute(
                "INSERT INTO VERSION (version) VALUES (%s);", (SCHEMA_VERSION,)
            )

            LOGGER.debug("committing database")
            await connection.commit()

    def get_api_version(self) -> Version:
        return SCHEMA_VERSION

    async def get_version(self) -> Version:
        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            await cursor.execute(
                """
                SELECT
                (version).major, (version).minor, (version).patch, (version).label
                FROM version
                ORDER BY id DESC LIMIT 1;
                """
            )
            row = await cursor.fetchone()

            if not row:
                raise ValueError("Unknown database version")

            return Version(*row)

    # TODO (1.0) actually check version on load
    async def matching_version(self) -> bool:
        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            try:
                await cursor.execute(
                    """
                    SELECT
                    (version).major, (version).minor, (version).patch, (version).label
                    FROM version
                    ORDER BY id DESC LIMIT 1;
                    """
                )
                rows = await cursor.fetchall()
            except UndefinedTable:
                LOGGER.exception("version table doesn't exist")
                return False

            if not len(rows):
                LOGGER.error("Database doesn't contain version info")
                return False

            version = Version(*rows[0])

            return version == SCHEMA_VERSION


def _get_types() -> set[str]:
    """Get the names of the types that exist in the types file.

    Since we created the file, it should be safe to regex parse

    Returns:
        The set of names in the types files
    """
    types = set()

    regex = re.compile(r"^\s*CREATE TYPE ([a-z0-9_]+) AS ")

    with TYPES_FILE.open("r") as stream:
        for line in stream.readlines():
            match = regex.search(line)

            if match:
                types.add(match.group(1))

    return types


def _get_tables() -> set[str]:
    """Get the names of the tables that exist in the schema file.

    Since we created the file, it should be safe to regex parse

    REturns:
        The set of names in the tables file
    """
    tables = set()

    regex = re.compile(r"^\s*CREATE TABLE IF NOT EXISTS ([a-z0-9_]+) \($")

    with SCHEMA_FILE.open("r") as stream:
        for line in stream.readlines():
            match = regex.search(line)

            if match:
                tables.add(match.group(1))

    return tables


all = (
    "SCHEMA_FILE",
    "TYPES_FILE",
    "Postgres",
)
