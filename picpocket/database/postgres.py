from __future__ import annotations

"""Support for using PostgreSQL as a backend"""

import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from subprocess import check_call
from typing import Any, Iterable, Optional

import psycopg
import psycopg.sql
from psycopg import AsyncClientCursor, AsyncConnection
from psycopg.errors import UndefinedTable

from picpocket.api import CredentialType
from picpocket.configuration import Configuration
from picpocket.database.dbapi import DbApi
from picpocket.database.logic import SQL, Comparator, Types
from picpocket.version import POSTGRES_VERSION as SCHEMA_VERSION
from picpocket.version import Version

LOGGER = logging.getLogger("picpocket.postgres")

SCHEMA_DIRECTORY = Path(__file__).absolute().parent / "schema" / "postgres"
TYPES_FILE = SCHEMA_DIRECTORY / "types.sql"
SCHEMA_FILE = SCHEMA_DIRECTORY / "schema.sql"


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
            await self._load_schema(cursor, TYPES_FILE)
            LOGGER.debug("Creating tables")
            await self._load_schema(cursor, SCHEMA_FILE, version=SCHEMA_VERSION)

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

    async def _load_schema(
        self,
        cursor: AsyncClientCursor,
        path: Path,
        version: Optional[Version] = None,
    ):
        await cursor.execute(path.read_text())

        if version:
            await cursor.execute(
                "INSERT INTO VERSION (version) VALUES (%s);", (version,)
            )

    async def create_backup(self, path: Path) -> Path:
        """Backup PicPocket data

        Create a backup of PicPocket's backend (locations, tasks, image
        info, tags).

        Returns:
            The path to the generated backup file.

        .. note::
            Unlike `export_data`, this stores the data in a
            backend-specific way. `create_backup` will create a file
            that is (probably) smaller and (probably) quicker to restore
            than `export_data` but will only be usable by the current
            backend.

        .. note::
            `create_backup` may not be implemented for all backends.

        .. warning::
            This file will not contain the images themselves, just the
            metadata you've created for the image (tags, captions,
            alt text, etc.).

        Args:
            path: The directory to save the backup to. The format of
                the resulting backup is backend-specific. With the
                Postgres backend, the backup will be created using
                `pg_dump`' default format. If the supplied path is
                an existing directory, it will be saved to a
                subdirectory with the name picpocket-<VERSION>-<DATE>.sql
        """
        if path.is_dir():
            version = await self.get_version()
            path = path / f"picpocket-{version}-{datetime.now():%Y-%m-%d-%H-%M-%S}.sql"

        path.parent.mkdir(exist_ok=True, parents=True)

        connection_info = self.configuration.contents["backend"]["connection"]

        command = [
            "pg_dump",
            "--clean",
            "--file",
            str(path),
            "--dbname",
            connection_info["dbname"],
            "--host",
            connection_info["host"],
            "--port",
            str(connection_info["port"]),
            "--username",
            connection_info["user"],
        ]

        if connection_info["password"]:
            command.extend(("--password", connection_info["password"]))
        else:
            command.append("--no-password")

        check_call(command)

        return path

    async def restore_backup(self, path: Path):
        if not path.is_file():
            logging.error("Attempting to restore non-existent file: %s", path)
            raise IOError(f"Missing file: {path}")

        connection_info = self.configuration.contents["backend"]["connection"]

        command = [
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "--file",
            str(path),
            "--dbname",
            connection_info["dbname"],
            "--host",
            connection_info["host"],
            "--port",
            str(connection_info["port"]),
            "--username",
            connection_info["user"],
        ]

        if connection_info["password"]:
            command.extend(("--password", connection_info["password"]))
        else:
            command.append("--no-password")

        check_call(command)


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
