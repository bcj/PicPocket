from __future__ import annotations

"""Support for using SQLite as a backend"""
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiosqlite
from aiosqlite import Connection

from picpocket.api import CredentialType
from picpocket.configuration import Configuration
from picpocket.database.dbapi import DbApi
from picpocket.database.logic import SQL, Types
from picpocket.version import SQLITE_VERSION as SCHEMA_VERSION
from picpocket.version import Version

LOGGER = logging.getLogger("picpocket.sqlite")

SCHEMA_FILE = Path(__file__).absolute().parent / "sqlite_schema.sql"

DEFAULT_FILENAME = "picpocket.sqlite3"


class SqliteSQL(SQL):
    """SQL support for SQLite"""

    @property
    def types(self) -> set[Types]:
        return {
            Types.BOOLEAN,
            Types.ID,
            Types.NUMBER,
            Types.TEXT,
        }

    @property
    def param(self) -> str:
        return "?"

    def placeholder(self, placeholder: str):
        if not re.search(r"^\w+$", placeholder):
            raise ValueError(f"Refusing use placeholder: {placeholder}")

        return f":{placeholder}"


class Sqlite(DbApi):
    """DbApi implementation for SQLite"""

    BACKEND_NAME = "sqlite"
    CREDENTIAL_TYPE = CredentialType.NONE

    TASKS_TABLE = {
        "name": Types.TEXT,
        "description": Types.TEXT,
        "source": Types.ID,
        "destination": Types.ID,
        "configuration": Types.TEXT,
    }

    TASK_INVOCATIONS_TABLE = {
        "task": Types.TEXT,
        "last_ran": Types.NUMBER,
    }

    IMAGES_TABLE = {
        "id": Types.ID,
        "name": Types.TEXT,
        "extension": Types.TEXT,
        "width": Types.TEXT,
        "height": Types.TEXT,
        "creator": Types.TEXT,
        "location": Types.ID,
        "path": Types.TEXT,
        "title": Types.TEXT,
        "caption": Types.TEXT,
        "alt": Types.TEXT,
        "rating": Types.NUMBER,
        "hash": Types.NUMBER,
        "creation_date": Types.NUMBER,
        "last_modified": Types.NUMBER,
        # TODO (by 1.0): the sqlite shipping with Python 3.11
        # supports JSON operations on text. We should be denoting this
        # column as JSON, denoting on the two sql objects that sqlite
        # is TEXT -> JSON -> TEXT and postgres is TEXT -> JSON -> OBJECT
        # and then have dbapi functions conditionally convert on both
        # sides
        "exif": Types.TEXT,
    }

    SESSION_INFO_TABLE = {
        "id": Types.NUMBER,
        "expires": Types.NUMBER,
        "data": Types.TEXT,
    }

    logger = LOGGER

    @classmethod
    def load(cls, configuration: Configuration) -> Sqlite:
        return cls(configuration)

    def __init__(self, configuration: Configuration):
        self._configuration = configuration
        self._mounts: dict[int, Path] = {}
        self._sql = SqliteSQL()

    @property
    def configuration(self) -> Configuration:
        return self._configuration

    @property
    def mounts(self) -> dict[int, Path]:
        return self._mounts

    @property
    def sql(self) -> SqliteSQL:
        return self._sql

    @asynccontextmanager
    async def cursor(self, connection: Connection, commit: bool = False):
        cursor = await connection.cursor()

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

    async def ensure_foreign_keys(self, cursor):
        await cursor.execute("PRAGMA foreign_keys = ON;")

    @classmethod
    def parse_connection_info(
        cls, directory: Path, *, store_credentials: Optional[bool] = None, **kwargs
    ) -> tuple[dict[str, str | int | bool], None]:
        info: dict[str, str | int | bool] = {}

        if "path" in kwargs:
            path = kwargs.pop("path")

            if isinstance(path, str):
                path = Path(path)
            elif not isinstance(path, Path):
                raise TypeError(path)

            if not path.is_absolute():
                if not directory.is_absolute() and path.is_relative_to(directory):
                    path = path.relative_to(directory)
                else:
                    path = path.absolute()

            info["path"] = str(path)
        else:
            info["path"] = DEFAULT_FILENAME

        if kwargs:
            raise ValueError(
                f"Unknown configuration values: {', '.join(sorted(kwargs))}"
            )

        return info, None

    async def connect(self, should_exist: Optional[bool] = True) -> Connection:
        backend_info = self.configuration.contents["backend"]
        if backend_info["type"] != self.BACKEND_NAME:
            raise ValueError(f"Wrong backend! {backend_info['type']}")

        pathstr = backend_info.get("connection", {})["path"]

        path = Path(pathstr)
        if not path.is_absolute():
            path = self.configuration.directory / path

        if should_exist is not None and path.is_file() != should_exist:
            if should_exist:
                raise ValueError(f"Database at {path} doesn't exist")
            else:
                raise ValueError(f"Database at {path} already exists")

        return aiosqlite.connect(path)

    async def initialize(self):
        LOGGER.debug("Creating tables")
        async with await self.connect(should_exist=False) as connection:
            cursor = await connection.executescript(SCHEMA_FILE.read_text())
            await cursor.execute(
                """
                INSERT INTO VERSION (major, minor, patch, label)
                VALUES (?, ?, ?, ?);
                """,
                SCHEMA_VERSION,
            )

            LOGGER.debug("committing database")
            await connection.commit()
            await cursor.close()

    def get_api_version(self) -> Version:
        return SCHEMA_VERSION

    async def get_version(self) -> Version:
        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            await cursor.execute(
                """
                SELECT major, minor, patch, label
                FROM version
                ORDER BY id DESC LIMIT 1;
                """
            )
            row = await cursor.fetchone()

            if not row:
                raise ValueError("Unknown database version")

            return Version(*row)

    async def matching_version(self) -> bool:
        async with (
            await self.connect() as connection,
            connection.cursor() as cursor,
        ):
            try:
                await cursor.execute(
                    """
                    SELECT major, minor, patch, label
                    FROM version
                    ORDER BY id DESC LIMIT 1;
                    """
                )
                row = await cursor.fetchone()
            except Exception:
                logging.exception("Checking version failed")
                await connection.rollback()
                return False

            if not row:
                LOGGER.error("Database doesn't contain version info")
                return False

            version = Version(*row)

            return version == SCHEMA_VERSION


__all__ = (
    "SCHEMA_FILE",
    "Sqlite",
)
