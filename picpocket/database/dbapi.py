from __future__ import annotations

"""Simplified support for DBAPI 2.0-compatible Databases"""

import json
import logging
import re
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncContextManager, AsyncGenerator, Optional, cast
from uuid import uuid4

from picpocket.api import NULL_SYMBOL, PicPocket
from picpocket.database.logic import (
    SQL,
    And,
    Comparator,
    Comparison,
    Number,
    Types,
    escape,
)
from picpocket.database.types import Image, Location, Tag, Task
from picpocket.images import hash_image, image_info
from picpocket.internal_use import NotSupplied
from picpocket.tasks import PathPart, load_path
from picpocket.version import VERSION

EXPIRATION = timedelta(days=1)


class DbApi(PicPocket, ABC):
    """A DBAPI 2.0 Implementation of PicPocket

    This class implements all required to support the PicPocket protocol
    other than the configuration and mounts properties and the
    parse_connection_info, initialize, get_api_version, get_version, and
    matching_version methods

    To add support for a new database you need to implement those
    methods yourself as well as some new methods related to getting
    connection and cursor objects, and a class for generating sql
    statements (which is largely modelled on psycopg's
    `sql <https://www.psycopg.org/psycopg3/docs/api/sql.html>`_ module).

    It will be assumed that an implementation is using the tables listed
    as class attributes (presently, LOCATIONS_TABLE, TASKS_TABLE,
    TASK_INVOCATIONS_TABLE, IMAGES_TABLE), that each of those tables
    will be named that attribute name in lowercase and without the
    _table. For all tables, it will be assumed that all columns listed
    exist. If your table uses different types, you will need to override
    that class attribute

    .. todo::
        DbApi additionaly assumed a tags table (with columns id, name,
        escaped_name, depth, description) and an image_tags table (with
        columns image, tag).

    .. todo::
        DbApi only really does type formatting on columns it knows
        differ between the postgres and sqlite. Once PicPocket adds
        proper JSON support for filtering on exif data, the
        :class:`Types <picpocket.database.logic.Types>` system will
        probably be addapted so that it accounts for input and output
        formats (e.g., postgres's JSON types expects text input but
        provides a deserialized output vs. sqlite's where input and
        output will both be strings but json operations are supported).
    """

    logger = logging.getLogger("picpocket.database")

    LOCATIONS_TABLE = {
        "id": Types.ID,
        "name": Types.TEXT,
        "description": Types.TEXT,
        "path": Types.TEXT,
        "source": Types.BOOLEAN,
        "destination": Types.BOOLEAN,
        "removable": Types.BOOLEAN,
    }

    TASKS_TABLE = {
        "name": Types.TEXT,
        "description": Types.TEXT,
        "source": Types.ID,
        "destination": Types.ID,
        "configuration": Types.JSON,
    }

    TASK_INVOCATIONS_TABLE = {
        "task": Types.TEXT,
        "last_ran": Types.DATETIME,
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
        "creation_date": Types.DATETIME,
        "last_modified": Types.DATETIME,
        "exif": Types.JSON,
    }

    SESSION_INFO_TABLE = {
        "id": Types.NUMBER,
        "expires": Types.DATETIME,
        "data": Types.JSON,
    }

    @property
    @abstractmethod
    def sql(self) -> SQL:
        """The sql object to use when dynamically generating sql.

        See :class:`picpocket.types`
        """

    @abstractmethod
    async def connect(self):
        """Establish a connection with the underlying database.

        Returns:
            A dbapi-compatible Connection object
        """

    @abstractmethod
    def cursor(self, connection, commit: bool = False) -> AsyncContextManager:
        """Yield a cursor that rolls back on error and optionally commits


        Args:
            connection: A connection object returned by connect
            commit: Whether to commit on (successful) exit

        Returns:
            A dbapi-compatible Cursor object
        """

    async def ensure_foreign_keys(self, cursor):
        """Ensure a cursor will support cascading changes.

        This will be a no-op for most DBs (or an exception for DBs that
        cannot support it I guess?) and only exists because an SQLite
        cursor needs to run a pragma to enable this and we don't want to
        do that on every single cursor creation.
        """

    async def import_data(
        self,
        path: Path,
        locations: Optional[list[str] | dict[str, Optional[Path]]] = None,
    ):
        if locations is None:
            locations = {}
        elif isinstance(locations, list):
            locations = {location: None for location in locations}

        with path.open("r") as stream:
            data = json.load(stream)

        # TODO (1.0): proper version checks
        if data["version"] != VERSION.as_dict():
            raise ValueError("Incompatible versions")

        tag_ids: dict[str, int] = {}

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            for name, description in data["tags"].items():
                # return_id guarantees an id
                tag_ids[name] = cast(
                    int,
                    await self._add_tag(cursor, name, description, return_id=True),
                )

            await connection.commit()

            for name, location_info in data["locations"].items():
                if locations and name not in locations:
                    self.logger.info("skipping location %s", name)
                    continue

                self.logger.info("importing location %s", name)

                existing = await self._get_location(cursor, name)

                if existing:
                    if existing.path is None:
                        if location_info["path"] is not None:
                            raise ValueError(
                                f"location {name} doesn't match existing version. "
                                f"{existing.path} != {location_info['path']}"
                            )
                    elif location_info["path"] is None:
                        if existing.path != locations.get(name):
                            raise ValueError(
                                f"location {name} doesn't match existing version. "
                                f"Imported version has no path"
                            )
                    elif Path(location_info["path"]) != existing.path:
                        raise ValueError(
                            f"location {name} doesn't match existing version. "
                            f"{existing.path} != {location_info['path']}"
                        )

                    location_id = existing.id
                    location_path = existing.path
                else:
                    if location_info["path"]:
                        location_path = Path(location_info["path"])
                    else:
                        location_path = None

                    location_id = await self._add_location(
                        cursor,
                        name,
                        location_path,
                        description=location_info["description"],
                        source=location_info["source"],
                        destination=location_info["destination"],
                        removable=location_info["removable"],
                    )

                old_mount = self.mounts.get(location_id)
                mounted = False
                try:
                    mount_path = locations.get(name)
                    if mount_path:
                        # don't use mount! location isn't committed yet
                        self._mount(location_id, mount_path)
                        mounted = True
                        location_path = mount_path
                    elif location_path is None:
                        self.logger.info("Skipping location %s, path not known", name)
                        continue

                    for image in location_info["images"]:
                        image_path = location_path / image.pop("path")
                        image_tags = image.pop("tags")
                        image_tag_ids = []
                        for tag in image_tags:
                            if tag in tag_ids:
                                image_tag_ids.append(tag_ids[tag])
                            else:
                                # return_id guarantees an id
                                tag_id = cast(
                                    int,
                                    await self._add_tag(cursor, tag, return_id=True),
                                )
                                tag_ids[tag] = tag_id
                                image_tag_ids.append(tag_id)

                        await self._import_image(
                            cursor,
                            location_id,
                            location_path,
                            image_path,
                            date_type=self.IMAGES_TABLE["creation_date"],
                            exif_type=self.IMAGES_TABLE["exif"],
                            tags=image_tag_ids,
                            **image,
                        )

                    await connection.commit()
                finally:
                    if mounted:
                        if old_mount:
                            self._mount(location_id, old_mount)
                        else:
                            await self.unmount(location_id)

            for name, task_info in data["tasks"].items():
                source = task_info["source"]
                destination = task_info["destination"]
                configuration = task_info["configuration"]

                if locations:
                    if source not in locations:
                        self.logger.info(
                            "skipping task %s: skipped source %s", name, source
                        )
                        continue

                    if destination not in locations:
                        self.logger.info(
                            "skipping task %s: skipped destination %s",
                            name,
                            destination,
                        )
                        continue

                if not await self._add_task(
                    cursor,
                    name,
                    description=task_info["description"],
                    source=source,
                    destination=destination,
                    source_path=configuration.get("source"),
                    destination_format=configuration.get("destination"),
                    creator=configuration.get("creator"),
                    tags=configuration.get("tags"),
                    file_formats=configuration.get("formats"),
                ):
                    self.logger.warning("failed to import task %s", name)

    async def export_data(
        self, path: Path, locations: Optional[list[str | int]] = None
    ):
        descriptive_tags: dict[str, str] = {}
        data: dict[str, list | dict] = {
            "locations": {},
            "tasks": {},
            "tags": descriptive_tags,
            "version": VERSION.as_dict(),
        }

        location_ids = []
        for name_or_id in locations or ():
            if isinstance(name_or_id, int):
                location_ids.append(name_or_id)
            else:
                location = await self.get_location(name_or_id)
                if location is None:
                    raise ValueError(f"Unknown location: {name_or_id}")
                location_ids.append(location.id)

        location_names = {}

        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            tags = {}

            await cursor.execute("SELECT id, name, description FROM tags;")
            for id, serialized, description in await cursor.fetchall():
                tags[id] = tag = deserialize_tag(serialized)

                if description:
                    descriptive_tags[tag] = description

            values: dict[str, Any] = {}
            if location_ids:
                where = self.sql.format(
                    " WHERE {}",
                    Number("id", Comparator.EQUALS, location_ids).prepare(
                        self.sql, values
                    ),
                )
            else:
                where = self.sql.format("")

            await cursor.execute(
                self.sql.format(
                    """
                    SELECT id, name, description, path, source, destination, removable
                    FROM locations {};
                    """,
                    where,
                ),
                values,
            )
            for (
                location_id,
                name,
                description,
                location_path,
                source,
                destination,
                removable,
            ) in await cursor.fetchall():
                location_names[location_id] = name

                images: list[dict[str, Any]] = []
                data["locations"][name] = {
                    "description": description,
                    "path": location_path,
                    "source": bool(source),
                    "destination": bool(destination),
                    "removable": bool(removable),
                    "images": images,
                }

                # we're storing images within locations so that we can
                # import images from individual locations and so that
                # it's easier to guarantee the location is present for
                # import (and therefore we don't need to store any
                # info we can derive from the actual file)
                await cursor.execute(
                    "SELECT id, path, creator, title, caption, alt, rating "
                    "FROM images "
                    f"WHERE location = {self.sql.param};",
                    (location_id,),
                )
                for (
                    image_id,
                    image_path,
                    creator,
                    title,
                    caption,
                    alt,
                    rating,
                ) in await cursor.fetchall():
                    await cursor.execute(
                        f"SELECT tag FROM image_tags WHERE image = {self.sql.param};",
                        (image_id,),
                    )
                    image_tags = [tags[tag_id] for (tag_id,) in await cursor.fetchall()]
                    image_tags = sorted(image_tags)

                    images.append(
                        {
                            "path": image_path,
                            "creator": creator,
                            "title": title,
                            "caption": caption,
                            "alt": alt,
                            "rating": rating,
                            "tags": image_tags,
                        }
                    )

            await cursor.execute(
                """
                SELECT name, description, source, destination, configuration
                FROM tasks;
                """
            )
            for (
                name,
                description,
                source,
                destination,
                configuration,
            ) in await cursor.fetchall():
                if self.TASKS_TABLE["configuration"] != Types.JSON:
                    configuration = json.loads(configuration)

                source_name = location_names.get(source)
                destination_name = location_names.get(destination)

                # happens if we're filtering locations
                if not (source_name and destination_name):
                    continue

                data["tasks"][name] = {
                    "description": description,
                    "source": source_name,
                    "destination": destination_name,
                    "configuration": configuration,
                }

        with path.open("w") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)

    async def add_location(
        self,
        name: str,
        path: Optional[Path] = None,
        *,
        description: Optional[str] = None,
        source: bool = False,
        destination: bool = False,
        removable: bool = True,
    ) -> int:
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            return await self._add_location(
                cursor,
                name,
                path,
                description=description,
                source=source,
                destination=destination,
                removable=removable,
            )

    async def _add_location(
        self,
        cursor,
        name: str,
        path: Optional[Path] = None,
        *,
        description: Optional[str] = None,
        source: bool = False,
        destination: bool = False,
        removable: bool = True,
    ) -> int:
        if not (source or destination):
            raise ValueError("A location must be a source, destination, or both")

        if not (path or removable):
            raise ValueError("Non-removable storage must have a supplied path")

        if path and not path.is_dir():
            raise ValueError(f"Supplied path ({path}) is not a directory")

        values = {
            "name": name,
            "source": source,
            "destination": destination,
            "removable": removable,
        }
        fields = list(values)

        if path:
            fields.append("path")
            values["path"] = str(path.absolute())

        if description:
            fields.append("description")
            values["description"] = description

        statement = self.sql.format(
            "INSERT INTO locations ({}) VALUES ({}) RETURNING id;",
            self.sql.join(", ", map(self.sql.identifier, fields)),
            self.sql.join(", ", map(self.sql.placeholder, fields)),
        )

        await cursor.execute(statement, values)
        row = await cursor.fetchone()

        return row[0]

    async def edit_location(
        self,
        name_or_id: str | int,
        new_name: Optional[str] = None,
        /,
        *,
        path: Optional[Path | NotSupplied] = NotSupplied(),
        description: Optional[str | NotSupplied] = NotSupplied(),
        source: Optional[bool] = None,
        destination: Optional[bool] = None,
        removable: Optional[bool] = None,
    ):
        fields = []
        values: dict[str, Optional[bool | int | str]] = {"identity": name_or_id}

        if isinstance(name_or_id, int):
            identity = self.sql.identifier("id")
        else:
            identity = self.sql.identifier("name")

        if new_name:
            fields.append("name")
            values["name"] = new_name

        if not isinstance(path, NotSupplied):
            if path and not path.is_dir():
                raise ValueError(f"Supplied path ({path}) is not a directory")

            fields.append("path")
            values["path"] = str(path.absolute()) if path else None

        if not isinstance(description, NotSupplied):
            fields.append("description")
            values["description"] = description

        for field, value in (
            ("source", source),
            ("destination", destination),
            ("removable", removable),
        ):
            if value is not None:
                fields.append(field)
                values[field] = value

        if not fields:
            raise ValueError(f"No edits made to location {name_or_id}")

        statement = self.sql.format(
            "UPDATE locations SET {} WHERE {} = {} RETURNING id;",
            self.sql.join(
                ", ",
                [
                    self.sql.join(
                        " = ", (self.sql.identifier(field), self.sql.placeholder(field))
                    )
                    for field in fields
                ],
            ),
            identity,
            self.sql.placeholder("identity"),
        )

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await cursor.execute(statement, values)
            row = await cursor.fetchone()

        if row is None:
            raise ValueError(f"Editing location {name_or_id} failed")

    async def remove_location(
        self,
        name_or_id: int | str,
        /,
        *,
        force: bool = False,
    ):
        id: int

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            if isinstance(name_or_id, str):
                await cursor.execute(
                    f"SELECT id FROM locations WHERE name = {self.sql.param};",
                    (name_or_id,),
                )
                row = await cursor.fetchone()
                if not row:
                    raise ValueError(f"Unknown location {name_or_id}")
                else:
                    (id,) = row
            else:
                id = name_or_id

            await cursor.execute(
                f"SELECT COUNT(id) FROM images WHERE location = {self.sql.param};",
                (id,),
            )
            (num_images,) = await cursor.fetchone()

            if num_images:
                if force:
                    self.logger.warning("Deleting %s images", num_images)
                else:
                    raise ValueError(
                        f"Cannot delete location ({name_or_id}). "
                        f"{num_images} images are associated with the location."
                    )

            await self.ensure_foreign_keys(cursor)
            await cursor.execute(
                f"DELETE FROM locations WHERE id = {self.sql.param} RETURNING id;",
                (id,),
            )
            row = await cursor.fetchone()

        return bool(row)

    async def get_location(
        self,
        name_or_id: str | int,
        /,
        *,
        expect: bool = False,
    ) -> Optional[Location]:
        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            return await self._get_location(cursor, name_or_id, expect)

    async def _get_location(
        self, cursor, name_or_id: str | int, expect: bool = False
    ) -> Optional[Location]:
        location = None

        if isinstance(name_or_id, int):
            identity = self.sql.identifier("id")
        else:
            identity = self.sql.identifier("name")

        await cursor.execute(
            self.sql.format(
                """
                SELECT id, name, description, path, source, destination, removable
                FROM locations
                WHERE {} = {} LIMIT 1;
                """,
                identity,
                self.sql.placeholder("identity"),
            ),
            {"identity": name_or_id},
        )
        row = await cursor.fetchone()

        if row:
            location = Location(*row, mount_point=self.mounts.get(row[0]))

        if expect and row is None:
            raise ValueError(f"Could not find location: {name_or_id}")

        return location

    async def list_locations(self) -> list[Location]:
        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            return await self._list_locations(cursor)

    async def _list_locations(self, cursor) -> list[Location]:
        locations = []

        await cursor.execute(
            """
            SELECT id, name, description, path, source, destination, removable
            FROM locations;
            """,
        )
        for row in await cursor.fetchall():
            locations.append(Location(*row, mount_point=self.mounts.get(row[0])))

        return locations

    async def mount(self, name_or_id: str | int, /, path: Path):
        # expect means we can guarantee not null
        id = cast(Location, await self.get_location(name_or_id, expect=True)).id
        self._mount(id, path)

    def _mount(self, id: int, path: Path):
        path = path.absolute()
        if not path.is_dir():
            raise ValueError(f"No directory named {path}")

        self.mounts[id] = path

    async def unmount(self, name_or_id: str | int):
        id = cast(Location, await self.get_location(name_or_id, expect=True)).id
        self.mounts.pop(id)

    async def import_location(
        self,
        name_or_id: str | int,
        /,
        *,
        file_formats: Optional[set[str]] = None,
        batch_size: int = 1000,
        creator: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[int]:
        location = cast(Location, await self.get_location(name_or_id, expect=True))

        path = self.mounts.get(location.id) or location.path
        if path is None:
            raise ValueError(f"Location {location.name} not mounted")

        if not path.exists():
            raise ValueError(f"Location {location.name} not found at {path}")

        if not path.is_dir():
            raise ValueError(f"Location {location.name} not a directory: {path}")

        if not file_formats:
            file_formats = set(self.configuration.contents["files"]["formats"])

        file_formats = {
            suffix if suffix.startswith(".") else f".{suffix}"
            for suffix in file_formats
        }

        tag_ids = None
        if tags:
            tag_ids = []

            async with (
                await self.connect() as connection,
                self.cursor(connection, commit=True) as cursor,
            ):
                for tag in tags:
                    tag_id = await self._add_tag(cursor, tag, return_id=True)
                    # return_id guarantees an id
                    tag_ids.append(cast(int, tag_id))

        directories = [path]
        images: list[int] = []
        importer = await self._import_images(
            location.id,
            path,
            batch_size=batch_size,
            image_ids=images,
            creator=creator,
            tags=tag_ids,
        )
        while directories:
            directory = directories.pop(0)

            for current in directory.iterdir():
                if current.is_dir():
                    directories.append(current)
                elif current.suffix.lower() in file_formats:
                    self.logger.debug(current)
                    await importer.asend(current)

        await importer.aclose()

        return images

    async def add_task(
        self,
        name: str,
        source: str | int,
        destination: str | int,
        *,
        description: Optional[str] = None,
        creator: Optional[str] = None,
        tags: Optional[list[str]] = None,
        source_path: Optional[str] = None,
        destination_format: Optional[str] = None,
        file_formats: Optional[set[str]] = None,
        force: bool = False,
    ):
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            if not await self._add_task(
                cursor,
                name,
                source,
                destination,
                description=description,
                creator=creator,
                tags=tags,
                source_path=source_path,
                destination_format=destination_format,
                file_formats=file_formats,
                force=force,
            ):
                raise ValueError(
                    "Failed to create task {name}. "
                    "If you're trying to edit a task, pass force=True"
                )

    async def _add_task(
        self,
        cursor,
        name: str,
        source: str | int,
        destination: str | int,
        *,
        description: Optional[str] = None,
        creator: Optional[str] = None,
        tags: Optional[list[str]] = None,
        source_path: Optional[str] = None,
        destination_format: Optional[str] = None,
        file_formats: Optional[set[str]] = None,
        force: bool = False,
    ) -> bool:
        configuration: dict[str, Any] = {}
        if creator:
            configuration["creator"] = creator

        if tags:
            configuration["tags"] = []
            for tag in tags:
                configuration["tags"].append(tag)

        if source_path:
            load_path(source_path)  # confirm it's loadable
            configuration["source"] = source_path

        if destination_format:
            destination_format.format(  # confirm it's loadable
                path="a/b/c.jpg",
                file="c.jpg",
                name="c",
                extension="jpg",
                uuid="uuid4",
                date=datetime.now().astimezone(),
                hash="hash",
                index=1,
            )
            configuration["destination"] = destination_format

        if file_formats:
            configuration["formats"] = [
                suffix if suffix.startswith(".") else f".{suffix}"
                for suffix in file_formats
            ]

        location = await self._get_location(cursor, source)
        if location is None:
            raise ValueError(f"Unkown source: {source}")
        source = location.id

        location = await self._get_location(cursor, destination)
        if location is None:
            raise ValueError(f"Unkown destination: {destination}")
        destination = location.id

        values = {
            "name": name,
            "source": source,
            "destination": destination,
            "description": description,
            "configuration": json.dumps(configuration),
        }

        if force:
            conflict = self.sql.format(
                "(name) DO UPDATE SET {}",
                self.sql.join(
                    ", ",
                    [
                        self.sql.format(
                            "{} = {}",
                            self.sql.identifier(key),
                            self.sql.placeholder(key),
                        )
                        for key in values
                    ],
                ),
            )
        else:
            conflict = self.sql.format("DO NOTHING")

        statement = self.sql.format(
            """
            INSERT INTO tasks ({})
            VALUES ({})
            ON CONFLICT {}
            RETURNING name;
            """,
            self.sql.join(", ", [self.sql.identifier(key) for key in sorted(values)]),
            self.sql.join(", ", [self.sql.placeholder(key) for key in sorted(values)]),
            conflict,
        )

        await cursor.execute(statement, values)
        row = await cursor.fetchone()

        # task changed, do a fresh run next time
        await cursor.execute(
            f"""
            UPDATE task_invocations
            SET last_ran = NULL
            WHERE task = {self.sql.param};
            """,
            (name,),
        )

        return row is not None

    async def run_task(
        self,
        name: str,
        *,
        since: Optional[datetime] = None,
        full: bool = False,
        tags: Optional[list[str]] = None,
    ) -> list[int]:
        now = datetime.now().astimezone()

        if tags is None:
            tags = []

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await cursor.execute(
                f"""
                SELECT source, destination, configuration
                FROM tasks
                WHERE name = {self.sql.param};
                """,
                (name,),
            )
            row = await cursor.fetchone()

            if not row:
                raise ValueError(f"Unknown task: {name}")

            source_id, destination_id, configuration = row
            if self.TASKS_TABLE["configuration"] == Types.TEXT:
                configuration = json.loads(configuration)

            if full:
                last_ran: Optional[datetime] = None
            elif since:
                last_ran = since
            else:
                await cursor.execute(
                    f"""
                    SELECT last_ran
                    FROM task_invocations
                    WHERE task = {self.sql.param};
                    """,
                    (name,),
                )
                row = await cursor.fetchone()

                if row and row[0] is not None:
                    (date,) = row

                    if self.TASK_INVOCATIONS_TABLE["last_ran"] == Types.NUMBER:
                        last_ran = datetime.fromtimestamp(date).astimezone()
                    else:
                        last_ran = date
                else:
                    last_ran = None

            source_root = self.mounts.get(source_id)
            if not source_root:
                location = await self._get_location(cursor, source_id, expect=True)

                source_root = cast(Location, location).path

                if not source_root:
                    raise ValueError("Source not mounted")

            destination_root = self.mounts.get(destination_id)
            if not destination_root:
                location = await self._get_location(cursor, destination_id, expect=True)

                destination_root = cast(Location, location).path

                if not destination_root:
                    raise ValueError("Destination not mounted")

            creator = configuration.get("creator")
            tags.extend(configuration.get("tags", []))

            if tags:
                tag_ids = []
                for tag in tags:
                    tag_ids.append(
                        cast(int, await self._add_tag(cursor, tag, return_id=True))
                    )

            else:
                tag_ids = None

            if "source" in configuration:
                source_path = load_path(configuration["source"])
            else:
                source_path = []
            destination_format = configuration.get("destination")

            if destination_format:
                include_date = "{date" in destination_format
                include_hash = "{hash" in destination_format

            formats = configuration.get("formats")
            if formats:
                formats = {format.lower() for format in formats}
            else:
                formats = {
                    format.lower()
                    for format in self.configuration.contents["files"]["formats"]
                }

            if last_ran:
                timestamp = last_ran.timestamp()
            else:
                timestamp = None

            base_params = {"last_ran": last_ran}
            remaining: list[tuple[Path, list[str | PathPart], dict[str, Any]]] = [
                (source_root, source_path, base_params)
            ]
            index = 1
            added = []
            while remaining:
                directory, remaining_parts, params = remaining.pop()
                for path in directory.iterdir():
                    if path.is_file():
                        if not remaining_parts and path.suffix.lower() in formats:
                            relative = path.relative_to(source_root)
                            if destination_format:
                                format_parts = {
                                    "directory": str(path.parent),
                                    "file": path.name,
                                    "name": path.stem,
                                    "extension": path.suffix[1:],
                                    "uuid": uuid4().hex,
                                    "index": index,
                                }
                                index += 1

                                if include_date:
                                    format_parts["date"] = datetime.fromtimestamp(
                                        path.stat().st_mtime
                                    )

                                if include_hash:
                                    format_parts["hash"] = hash_image(path)

                                relative = destination_format.format(**format_parts)

                            if (
                                timestamp is not None
                                and path.stat().st_mtime < timestamp
                            ):
                                continue

                            image_id = await self._add_image_copy(
                                cursor,
                                destination_id,
                                destination_root,
                                path,
                                destination_root / relative,
                                creator=creator,
                                tags=tag_ids,
                            )
                            if image_id is None:
                                self.logger.info(
                                    "skipping %s, image already exists at %s",
                                    path,
                                    destination_root / relative,
                                )
                            else:
                                added.append(image_id)
                    elif path.is_dir():
                        if not remaining_parts:
                            remaining.append((path, remaining_parts, params))
                        else:
                            part = remaining_parts[0]
                            if isinstance(part, str):
                                if part != path.name:
                                    continue

                                new_params = params
                            else:
                                maybe_new_params = part.matches(path.name, params)
                                if maybe_new_params is None:
                                    continue
                                else:
                                    new_params = {**params, **maybe_new_params}

                            remaining.append((path, remaining_parts[1:], new_params))

            if self.TASK_INVOCATIONS_TABLE["last_ran"] == Types.NUMBER:
                date = int(now.timestamp())
            else:
                date = now

            await cursor.execute(
                self.sql.format(
                    """
                    INSERT INTO task_invocations
                    (task, last_ran)
                    VALUES ({}, {})
                    ON CONFLICT (task) DO UPDATE SET last_ran = {};
                    """,
                    self.sql.placeholder("name"),
                    self.sql.placeholder("last_ran"),
                    self.sql.placeholder("last_ran"),
                ),
                {"name": name, "last_ran": date},
            )

        return added

    async def remove_task(self, name: str):
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await self.ensure_foreign_keys(cursor)
            await cursor.execute(
                f"DELETE FROM tasks WHERE name = {self.sql.param};",
                (name,),
            )

    async def get_task(self, name: str) -> Optional[Task]:
        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            task = None

            await cursor.execute(
                f"""
                SELECT source, destination, configuration, description
                FROM tasks
                WHERE name = {self.sql.param};
                """,
                (name,),
            )
            row = await cursor.fetchone()

            if row:
                source, destination, configuration, description = row
                last_ran = None

                if self.TASKS_TABLE["configuration"] != Types.JSON:
                    configuration = json.loads(configuration)

                await cursor.execute(
                    f"""
                    SELECT last_ran
                    FROM task_invocations
                    WHERE task = {self.sql.param};
                    """,
                    (name,),
                )
                row = await cursor.fetchone()

                if row and row[0] is not None:
                    if self.TASK_INVOCATIONS_TABLE["last_ran"] == Types.NUMBER:
                        last_ran = datetime.fromtimestamp(row[0]).astimezone()
                    else:
                        last_ran = row[0]

                task = Task(
                    name, source, destination, configuration, description, last_ran
                )

        return task

    async def list_tasks(self) -> list[Task]:
        tasks = []

        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            await cursor.execute(
                """
                SELECT name, source, destination, configuration, description
                FROM tasks;
                """,
            )

            for (
                name,
                source,
                destination,
                configuration,
                description,
            ) in await cursor.fetchall():
                last_ran = None

                if self.TASKS_TABLE["configuration"] != Types.JSON:
                    configuration = json.loads(configuration)

                await cursor.execute(
                    f"""
                    SELECT last_ran
                    FROM task_invocations
                    WHERE task = {self.sql.param};
                    """,
                    (name,),
                )
                row = await cursor.fetchone()

                if row and row[0] is not None:
                    if self.TASK_INVOCATIONS_TABLE["last_ran"] == Types.NUMBER:
                        last_ran = datetime.fromtimestamp(row[0]).astimezone()
                    else:
                        last_ran = row[0]

                tasks.append(
                    Task(
                        name, source, destination, configuration, description, last_ran
                    )
                )

            return tasks

    async def add_image_copy(
        self,
        source: Path,
        name_or_id: str | int,
        destination: Path,
        /,
        *,
        creator: Optional[str] = None,
        title: Optional[str] = None,
        caption: Optional[str] = None,
        alt: Optional[str] = None,
        rating: Optional[int] = None,
        tags: Optional[list[str]] = None,
    ) -> int:
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            location = cast(
                Location, await self._get_location(cursor, name_or_id, expect=True)
            )
            root = self.mounts.get(location.id, location.path)

            if root is None:
                raise ValueError(f"Unknown path for location {name_or_id}")

            tag_ids = []
            if tags:
                for tag in tags:
                    tag_ids.append(
                        # return_id guarantees it's not None
                        cast(
                            int,
                            await self._add_tag(cursor, tag, return_id=True),
                        )
                    )

            image_id = await self._add_image_copy(
                cursor,
                location.id,
                root,
                source,
                root / destination,
                creator=creator,
                title=title,
                caption=caption,
                alt=alt,
                rating=rating,
                tags=tag_ids,
            )

            if image_id is None:
                raise ValueError(f"Image already exists at {root /destination}")

        return image_id

    async def _add_image_copy(
        self,
        cursor,
        location: int,
        root: Path,
        source: Path,
        destination: Path,
        /,
        *,
        creator: Optional[str] = None,
        title: Optional[str] = None,
        caption: Optional[str] = None,
        alt: Optional[str] = None,
        rating: Optional[int] = None,
        tags: Optional[list[int]] = None,
    ) -> Optional[int]:
        if destination.exists():
            return None

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

        image_id = await self._import_image(
            cursor,
            location,
            root,
            destination,
            creator=creator,
            title=title,
            caption=caption,
            alt=alt,
            rating=rating,
            tags=tags,
            date_type=self.IMAGES_TABLE["creation_date"],
            exif_type=self.IMAGES_TABLE["exif"],
            no_update=True,
        )

        return image_id

    async def _import_images(
        self,
        location: int,
        root: Path,
        *,
        batch_size: Optional[int] = None,
        image_ids: Optional[list[int]] = None,
        creator: Optional[str] = None,
        tags: Optional[list[int]] = None,
    ) -> AsyncGenerator[None, Path]:
        """Create a generator for bulk-importing images

        Create a generator for mass-importing images to a single
        location. The generator will receive fully-qualified paths one
        at a time, and will need to derive all required information
        about the image and then store that in the images table.

        xxx

        Images will be sent to the generator, one at a time

        Return an initialized generator for bulk-importing images.
        Images should be passed one at a time, with the path being the
        fully qualified path, not relative to the root.

        location: The location the images are being added to
        root: The path to the location
        batch_size: If supplied, sync every N images. This is based on
            attempted images not actually-insterted.
        image_ids: If supplied, an array to fill with the ids of all
            imported images. Values will not be added to the array until
            the generator has commited changes (after the current batch
            commits or once aclose is called). If aclose is not called,
            the list will be missing everything in the final batch.
        creator: Who created these images
        tags: Tags to apply to the images
        """

        async def generator() -> AsyncGenerator[None, Path]:
            count = 0
            cached = []

            async with (
                await self.connect() as connection,
                self.cursor(connection) as cursor,
            ):
                try:
                    while True:
                        path = yield None

                        image_id = await self._import_image(
                            cursor,
                            location,
                            root,
                            path,
                            creator=creator,
                            tags=tags,
                            date_type=self.IMAGES_TABLE["creation_date"],
                            exif_type=self.IMAGES_TABLE["exif"],
                        )
                        if image_id is not None:
                            cached.append(image_id)

                        count += 1

                        if batch_size and count % batch_size == 0:
                            await connection.commit()
                            if image_ids is not None:
                                image_ids.extend(cached)
                            cached = []
                except GeneratorExit:
                    await connection.commit()
                    if image_ids is not None:
                        image_ids.extend(cached)

        importer = generator()
        # the first send to the generator can't pass a value. It just gets
        # the iterator to yield. This cast is gross but it appeased mypy
        await importer.asend(cast(Path, None))

        return importer

    async def _import_image(
        self,
        cursor,
        location: int,
        root: Path,
        path: Path,
        *,
        creator: Optional[str] = None,
        title: Optional[str] = None,
        caption: Optional[str] = None,
        alt: Optional[str] = None,
        rating: Optional[int] = None,
        tags: Optional[list[int]] = None,
        date_type: Types = Types.DATETIME,
        exif_type: Types = Types.JSON,
        no_update: bool = False,
    ) -> Optional[int]:
        image_id = None
        modified = False

        creation_date: Optional[datetime | int]
        exif: dict[str, Any] | str
        (
            width,
            height,
            creation_date,
            exif_creator,
            exif_description,
            exif,
        ) = image_info(path, self.logger)

        if creation_date and date_type == Types.NUMBER:
            creation_date = int(creation_date.timestamp())

        mtime = int(path.stat().st_mtime)

        if date_type == Types.DATETIME:
            last_modified: int | datetime = datetime.fromtimestamp(mtime).astimezone()
        else:
            last_modified = mtime

        if creation_date is None:
            creation_date = last_modified

        values = {
            "path": str(path.relative_to(root)),
            "name": path.stem,
            "extension": path.suffix[1:].lower(),
            "hash": hash_image(path),
            "creation_date": creation_date,
            "last_modified": last_modified,
            "location": location,
            "width": width,
            "height": height,
            "exif": json.dumps(exif),
        }

        if creator or exif_creator:
            values["creator"] = creator or exif_creator

        if title:
            values["title"] = title

        if caption or exif_description:
            values["caption"] = caption or exif_description

        if alt:
            values["alt"] = alt

        if rating is not None:
            values["rating"] = rating

        identifiers = self.sql.join(
            ", ", [self.sql.identifier(value) for value in sorted(values.keys())]
        )
        await cursor.execute(
            self.sql.format(
                """
                INSERT INTO images ({})
                VALUES ({})
                ON CONFLICT DO NOTHING
                RETURNING id;
                """,
                identifiers,
                self.sql.join(
                    ", ",
                    [self.sql.placeholder(value) for value in sorted(values.keys())],
                ),
            ),
            values,
        )
        row = await cursor.fetchone()

        if row:
            (image_id,) = row
            modified = True
        elif no_update:
            return None
        else:
            await cursor.execute(
                self.sql.format(
                    "SELECT id, {} FROM images WHERE location = {} AND path = {};",
                    identifiers,
                    self.sql.placeholder("location"),
                    self.sql.placeholder("path"),
                ),
                {"location": location, "path": values["path"]},
            )
            image_id, *current_values = await cursor.fetchone()
            for current, (key, value) in zip(current_values, sorted(values.items())):
                # these keys are user supplied so we should only update
                # if there aren't existing values. All other properties
                # are derived from the file so updates should be applied
                if key in (
                    "creator",
                    "title",
                    "caption",
                    "alt",
                    "rating",
                ):
                    if current is not None or current == value:
                        values.pop(key)
                elif current == value:
                    values.pop(key)
                elif key == "exif":
                    if exif_type == Types.JSON:
                        if json.dumps(current) == value:
                            values.pop(key)

            if values:
                values["id"] = image_id
                await cursor.execute(
                    self.sql.format(
                        "UPDATE images SET {} WHERE id = {};",
                        self.sql.join(
                            ", ",
                            [
                                self.sql.format(
                                    "{} = {}",
                                    self.sql.identifier(key),
                                    self.sql.placeholder(key),
                                )
                                for key in values.keys()
                                if key != "id"
                            ],
                        ),
                        self.sql.placeholder("id"),
                    ),
                    values,
                )
                modified = True

        if tags and image_id:
            await cursor.executemany(
                f"""
                INSERT INTO image_tags (image, tag)
                VALUES ({self.sql.param}, {self.sql.param})
                ON CONFLICT DO NOTHING;
                """,
                [(image_id, tag) for tag in tags],
            )

        return image_id if modified else None

    async def edit_image(
        self,
        id: int,
        *,
        creator: Optional[str | NotSupplied] = NotSupplied(),
        title: Optional[str | NotSupplied] = NotSupplied(),
        caption: Optional[str | NotSupplied] = NotSupplied(),
        alt: Optional[str | NotSupplied] = NotSupplied(),
        rating: Optional[int | NotSupplied] = NotSupplied(),
    ):
        fields = []
        values: dict[str, Optional[str | int | list[str]]] = {"id": id}

        for key, value in (
            ("creator", creator),
            ("title", title),
            ("caption", caption),
            ("alt", alt),
            ("rating", rating),
        ):
            if not isinstance(value, NotSupplied):
                fields.append(key)
                values[key] = value

        if not fields:
            raise ValueError(f"No edits to image {id} requested")

        statement = self.sql.format(
            "UPDATE images SET {} WHERE id = {} RETURNING id;",
            self.sql.join(
                ", ",
                [
                    self.sql.join(
                        " = ",
                        (self.sql.identifier(field), self.sql.placeholder(field)),
                    )
                    for field in fields
                ],
            ),
            self.sql.placeholder("id"),
        )

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await cursor.execute(statement, values)
            row = await cursor.fetchone()

        if not row:
            raise ValueError(f"Editing image {id} failed")

    async def tag_image(self, id: int, tag: str):
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            tag_id = await self._add_tag(cursor, tag, return_id=True)

            await cursor.execute(
                f"""
                INSERT INTO image_tags (image, tag)
                VALUES ({self.sql.param}, {self.sql.param})
                ON CONFLICT DO NOTHING;
                """,
                (id, tag_id),
            )

    async def untag_image(self, id: int, tag: str):
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await cursor.execute(
                f"SELECT id FROM tags WHERE name = {self.sql.param};",
                (serialize_tag(tag),),
            )
            row = await cursor.fetchone()

            if row:
                (tag_id,) = row

                await cursor.execute(
                    f"""
                    DELETE FROM image_tags
                    WHERE  image={self.sql.param} AND tag={self.sql.param};
                    """,
                    (id, tag_id),
                )

    async def move_image(self, id: int, path: Path, location: Optional[int] = None):
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            image = await self._get_image(cursor, id)

            if image is None:
                raise ValueError(f"Unknown image: {id}")

            source_root = self.mounts.get(image.location)

            if not source_root:
                # expect guarantees that this location will exist
                source_location = cast(
                    Location,
                    await self._get_location(cursor, image.location, expect=True),
                )

                if source_location.path:
                    source_root = source_location.path
                else:
                    raise ValueError(
                        f"Path not supplied for location: {image.location}"
                    )

            if not source_root.is_dir():
                raise ValueError(f"Source location not mounted at {source_root}")

            if location is None:
                destination_root = source_root
                location = image.location
            else:
                if location == image.location:
                    destination_root = source_root
                elif location in self.mounts:
                    destination_root = self.mounts[location]
                else:
                    destination_location = await self._get_location(cursor, location)

                    if destination_location is None:
                        raise ValueError(f"Unknown location: {destination_location}")

                    if destination_location.path:
                        destination_root = destination_location.path
                    else:
                        raise ValueError(f"Path not supplied for location: {location}")

            if not destination_root.is_dir():
                raise ValueError(
                    f"Destination location not mounted at {destination_root}"
                )

            source = source_root / image.path
            destination = destination_root / path
            moved = False

            if source == destination:
                raise ValueError(f"source and destination must be different: {source}")

            if destination.is_dir():
                raise ValueError("Filename must be supplied")

            if not source.is_file():
                if not destination.is_file():
                    raise ValueError(f"Image not found at {source}")

                self.logger.info(
                    "Image already moved from %s to %s", source, destination
                )
                moved = True
            elif destination.is_file():
                raise ValueError(f"File already exists at location {destination}")

            await cursor.execute(
                f"""
                UPDATE images
                SET
                    name = {self.sql.param},
                    extension = {self.sql.param},
                    location = {self.sql.param},
                    path = {self.sql.param}
                WHERE
                    id = {self.sql.param}
                    AND location = {self.sql.param}
                    AND path = {self.sql.param};
                """,
                (
                    destination.stem,
                    destination.suffix[1:].lower(),
                    location,
                    str(path),
                    id,
                    image.location,
                    str(image.path),
                ),
            )

            if moved:
                await connection.commit()
            else:
                destination.parent.mkdir(exist_ok=True, parents=True)
                shutil.move(source, destination)

    async def remove_image(self, id: int, *, delete: bool = False):
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await cursor.execute(
                f"""
                DELETE FROM images
                WHERE id = {self.sql.param}
                RETURNING location, path;
                """,
                (id,),
            )
            row = await cursor.fetchone()

            if not row:
                raise ValueError(f"Unknown image: {id}")

            if delete:
                location, pathstr = row

                root = self.mounts.get(location)

                if not root:
                    await cursor.execute(
                        f"SELECT path FROM locations WHERE id = {self.sql.param};",
                        (location,),
                    )
                    row = await cursor.fetchone()

                    (rootstr,) = row

                    if rootstr is None:
                        raise ValueError(f"Path to location ({location}) not supplied")

                    root = Path(rootstr)

                if not root.is_dir():
                    raise ValueError(f"Location ({location}) not mounted at {root}")

                path = root / pathstr
                if path.exists():
                    path.unlink()

    async def find_image(self, path: Path, tags: bool = False) -> Optional[Image]:
        path = path.absolute()

        image = None

        query = f"""
        SELECT
            id, location, path, creator, title, caption, alt, rating,
            width, height, hash, creation_date, last_modified, exif
        FROM images
        WHERE location={self.sql.param} AND path={self.sql.param};
        """

        location_query = "SELECT id, path FROM locations WHERE path IS NOT NULL;"
        location_args: dict[str, Any] = {}

        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            for id, root in self.mounts.items():
                if path.is_relative_to(root):
                    await cursor.execute(query, (id, str(path.relative_to(root))))
                    row = await cursor.fetchone()

                    if row:
                        (
                            image_id,
                            *args,
                            width,
                            height,
                            hash,
                            creatione_date,
                            last_modified,
                            exif,
                        ) = row

                        if self.IMAGES_TABLE["exif"] == Types.TEXT:
                            exif = json.loads(exif)

                        found_tags = None
                        if tags:
                            found_tags = await self.fetch_tags(cursor, image_id)

                        image = Image(
                            image_id,
                            *args,
                            width=width,
                            height=height,
                            hash=hash,
                            creation_date=creatione_date,
                            last_modified=last_modified,
                            exif=exif,
                            location_path=root,
                            tags=found_tags,
                        )
                        break

                if not image:
                    location_args = {}
                    location_query = self.sql.format(
                        "SELECT id, path "
                        "FROM locations "
                        "WHERE {} AND path IS NOT NULL;",
                        # postgres has ANY, sqlite doesn't
                        Number(
                            "id", Comparator.EQUALS, list(self.mounts), invert=True
                        ).prepare(self.sql, location_args),
                    )

            if not image:
                await cursor.execute(location_query, location_args)
                rows = await cursor.fetchall()
                for id, root in rows:
                    if path.is_relative_to(root):
                        await cursor.execute(query, (id, str(path.relative_to(root))))
                        row = await cursor.fetchone()

                        if row:
                            (
                                image_id,
                                *args,
                                width,
                                height,
                                hash,
                                creatione_date,
                                last_modified,
                                exif,
                            ) = row

                            if self.IMAGES_TABLE["exif"] == Types.TEXT:
                                exif = json.loads(exif)

                            found_tags = None
                            if tags:
                                found_tags = await self.fetch_tags(cursor, image_id)

                            image = Image(
                                image_id,
                                *args,
                                width=width,
                                height=height,
                                hash=hash,
                                creation_date=creatione_date,
                                last_modified=last_modified,
                                exif=exif,
                                location_path=root,
                                tags=found_tags,
                            )
                            break

        return image

    async def get_image(self, id: int, tags: bool = False) -> Optional[Image]:
        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            return await self._get_image(cursor, id, full_path=True, tags=tags)

    async def _get_image(
        self,
        cursor,
        id: int,
        *,
        full_path: bool = False,
        tags: bool = False,
    ) -> Optional[Image]:
        image = None

        await cursor.execute(
            f"""
            SELECT
            location, path, creator, title, caption, alt, rating,

            width, height, hash, creation_date, last_modified, exif
            FROM images
            WHERE id = {self.sql.param} LIMIT 1;
            """,
            (id,),
        )
        row = await cursor.fetchone()

        if row:
            (
                location,
                *args,
                width,
                height,
                hash,
                creatione_date,
                last_modified,
                exif,
            ) = row

            if self.IMAGES_TABLE["exif"] == Types.TEXT:
                exif = json.loads(exif)

            path = None
            if full_path:
                if location in self.mounts:
                    path = self.mounts[location]
                else:
                    await cursor.execute(
                        f"SELECT path FROM locations WHERE id = {self.sql.param}",
                        (location,),
                    )
                    row = await cursor.fetchone()
                    if row and row[0]:
                        path = Path(row[0])

            found_tags = None
            if tags:
                found_tags = await self.fetch_tags(cursor, id)

            image = Image(
                id,
                location,
                *args,
                hash=hash,
                width=width,
                height=height,
                creation_date=creatione_date,
                last_modified=last_modified,
                exif=exif,
                location_path=path,
                tags=found_tags,
            )

        return image

    async def count_images(
        self,
        filter: Optional[Comparison] = None,
        tagged: Optional[bool] = None,
        any_tags: Optional[list[str]] = None,
        all_tags: Optional[list[str]] = None,
        no_tags: Optional[list[str]] = None,
        reachable: Optional[bool] = None,
    ) -> int:
        values: dict[str, Any] = {}

        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            filter = await self._filter_reachable(cursor, filter, reachable)
            tag_check = await self._tag_comparison(
                cursor, tagged, any_tags, all_tags, no_tags, values
            )

            query = self.sql.format(
                "SELECT COUNT(id) FROM images{};",
                self._build_filter(
                    self.IMAGES_TABLE, filter, values, additional_comparison=tag_check
                ),
            )
            await cursor.execute(query, values)
            return (await cursor.fetchone())[0]

    async def get_image_ids(
        self,
        filter: Optional[Comparison] = None,
        *,
        tagged: Optional[bool] = None,
        any_tags: Optional[list[str]] = None,
        all_tags: Optional[list[str]] = None,
        no_tags: Optional[list[str]] = None,
        order: Optional[tuple[str, ...]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        reachable: Optional[bool] = None,
    ) -> list[int]:
        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            values: dict[str, Any] = {}
            filter = await self._filter_reachable(cursor, filter, reachable)
            tag_check = await self._tag_comparison(
                cursor, tagged, any_tags, all_tags, no_tags, values
            )

            query = self.sql.format(
                "SELECT id FROM images{}{};",
                self._build_filter(
                    self.IMAGES_TABLE, filter, values, additional_comparison=tag_check
                ),
                self._build_ordering(self.IMAGES_TABLE, order, limit, offset, values),
            )

            await cursor.execute(query, values)
            return [id for (id,) in await cursor.fetchall()]

    async def search_images(
        self,
        filter: Optional[Comparison] = None,
        *,
        tagged: Optional[bool] = None,
        any_tags: Optional[list[str]] = None,
        all_tags: Optional[list[str]] = None,
        no_tags: Optional[list[str]] = None,
        order: Optional[tuple[str, ...]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        reachable: Optional[bool] = None,
    ) -> list[Image]:
        images = []

        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            values: dict[str, Any] = {}
            filter = await self._filter_reachable(cursor, filter, reachable)
            tag_check = await self._tag_comparison(
                cursor, tagged, any_tags, all_tags, no_tags, values
            )

            query = self.sql.format(
                """
                SELECT
                id, location, path, creator, title, caption, alt, rating,
                width, height, hash, creation_date, last_modified, exif
                FROM images{}{};
                """,
                self._build_filter(
                    self.IMAGES_TABLE, filter, values, additional_comparison=tag_check
                ),
                self._build_ordering(self.IMAGES_TABLE, order, limit, offset, values),
            )

            location_paths: dict[str, Optional[Path]] = {}

            await cursor.execute(query, values)
            for (
                id,
                location,
                *args,
                width,
                height,
                hash,
                creatione_date,
                last_modified,
                exif,
            ) in await cursor.fetchall():
                if self.IMAGES_TABLE["exif"] == Types.TEXT:
                    exif = json.loads(exif)

                if location not in location_paths:
                    if location in self.mounts:
                        location_paths[location] = self.mounts[location]
                    else:
                        await cursor.execute(
                            f"SELECT path FROM locations WHERE id = {self.sql.param};",
                            (location,),
                        )
                        row = await cursor.fetchone()
                        location_path = None
                        if row and row[0]:
                            location_path = Path(row[0])
                        location_paths[location] = location_path

                images.append(
                    Image(
                        id,
                        location,
                        *args,
                        width=width,
                        height=height,
                        hash=hash,
                        creation_date=creatione_date,
                        last_modified=last_modified,
                        exif=exif,
                        location_path=location_paths[location],
                        tags=await self.fetch_tags(cursor, id),
                    )
                )

        return images

    async def _filter_reachable(
        self, cursor, filter: Optional[Comparison], reachable: Optional[bool]
    ) -> Optional[Comparison]:
        if reachable is not None:
            matching = []
            for location in await self._list_locations(cursor):
                path = self.mounts.get(location.id, location.path)
                if reachable == bool(path and path.is_dir()):
                    matching.append(location.id)

            location_filter = Number("location", Comparator.EQUALS, matching)
            if filter:
                filter = And(filter, location_filter)
            else:
                filter = location_filter

        return filter

    async def _tag_comparison(
        self,
        cursor,
        tagged: Optional[bool],
        any_tags: Optional[list[str]],
        all_tags: Optional[list[str]],
        no_tags: Optional[list[str]],
        values: dict[str, Any],
    ):
        parts = []

        if tagged is not None:
            comparison = "IN" if tagged else "NOT IN"
            parts.append(
                self.sql.format(
                    f"id {comparison} (SELECT DISTINCT image FROM image_tags)"
                )
            )

        if any_tags:
            tag_ids = set()
            for tag in any_tags:
                tag_ids.update(await self._related_tags(cursor, tag))

            parts.append(
                self.sql.format(
                    "id IN (SELECT image FROM image_tags WHERE {})",
                    Number("tag", Comparator.EQUALS, list(tag_ids)).prepare(
                        self.sql, values
                    ),
                )
            )

        if no_tags:
            tag_ids = set()
            for tag in no_tags:
                tag_ids.update(await self._related_tags(cursor, tag))

            parts.append(
                self.sql.format(
                    "id NOT IN (SELECT image FROM image_tags WHERE {})",
                    Number("tag", Comparator.EQUALS, list(tag_ids)).prepare(
                        self.sql, values
                    ),
                )
            )

        if all_tags:
            # rip to a real one. we were previously doing a single select
            # and counting the matching tags but that returns false
            # positives if you have multiple tags on an image that match
            # one of the requested tags
            for tag in all_tags:
                tag_ids = set()
                tag_ids.update(await self._related_tags(cursor, tag))
                parts.append(
                    self.sql.format(
                        "id IN (SELECT image FROM image_tags WHERE {})",
                        Number("tag", Comparator.EQUALS, list(tag_ids)).prepare(
                            self.sql, values
                        ),
                    )
                )

        if parts:
            return self.sql.join(" AND ", parts)

        return None

    async def verify_image_files(
        self,
        *,
        location: Optional[int] = None,
        path: Optional[Path] = None,
        reparse_exif: bool = False,
    ) -> list[Image]:
        search_locations = {}

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            if location:
                root = self.mounts.get(location)

                if root is None:
                    await cursor.execute(
                        f"""
                        SELECT path, removable
                        FROM locations
                        WHERE id = {self.sql.param};
                        """,
                        (location,),
                    )
                    row = await cursor.fetchone()

                    if not row:
                        raise ValueError(f"Unknown location: {location}")

                    pathstr, removable = row

                    if not pathstr:
                        raise ValueError(
                            f"No information about where {location} is mounted"
                        )

                    root = Path(pathstr)

                if root.is_dir():
                    if path:
                        if root.is_relative_to(path) or path.is_relative_to(root):
                            search_locations[location] = root
                    else:
                        search_locations[location] = root
                elif removable:
                    raise ValueError(f"Location {location} not mounted at {root}")
                else:
                    raise ValueError(f"Location {location} missing!")
            else:
                await cursor.execute("SELECT id, path, removable FROM locations;")
                for id, pathstr, removable in await cursor.fetchall():
                    root = self.mounts.get(id)

                    if root is None and pathstr:
                        root = Path(pathstr)

                    if root and root.is_dir():
                        if path:
                            if root.is_relative_to(path) or path.is_relative_to(root):
                                search_locations[id] = root
                        else:
                            search_locations[id] = root
                    elif not removable:
                        self.logger.warning("Permanent location (%s) missing", id)

            if not search_locations:
                raise ValueError("No valid search locations")

            images = []
            values: dict[str, Any] = {}
            statement = self.sql.format(
                """
                SELECT
                id, location, path, creator, title, caption, alt, rating,
                width, height, hash, creation_date, last_modified, exif
                FROM images
                WHERE {};
                """,
                # sqlite doesn't support ANY
                Number("location", Comparator.EQUALS, list(search_locations)).prepare(
                    self.sql, values
                ),
            )
            async with (
                await self.connect() as connection,
                self.cursor(connection, commit=True) as cursor,
            ):
                await cursor.execute(statement, values)
                for (
                    id,
                    image_location,
                    *args,
                    width,
                    height,
                    hash,
                    creatione_date,
                    last_modified,
                    exif,
                ) in await cursor.fetchall():
                    if self.IMAGES_TABLE["exif"] == Types.TEXT:
                        exif = json.loads(exif)

                    image = Image(
                        id,
                        image_location,
                        *args,
                        width=width,
                        height=height,
                        hash=hash,
                        creation_date=creatione_date,
                        last_modified=last_modified,
                        exif=exif,
                        location_path=search_locations[image_location],
                    )
                    image_path = search_locations[image.location] / image.path

                    if path and not image_path.is_relative_to(path):
                        continue

                    if image_path.exists():
                        mtime = int(image_path.stat().st_mtime)

                        if self.IMAGES_TABLE["last_modified"] == Types.DATETIME:
                            last_modified = datetime.fromtimestamp(mtime).astimezone()
                        else:
                            last_modified = mtime

                        # no point in checking for other changes if not modified
                        if last_modified != image.last_modified or reparse_exif:
                            values = {"last_modified": last_modified}

                            hashed = hash_image(image_path)
                            old_hash = image.hash

                            # no point loading image if same hash
                            if hashed != old_hash or reparse_exif:
                                values["hash"] = hashed

                                (
                                    width,
                                    height,
                                    creation_date,
                                    artist,
                                    caption,
                                    exif,
                                ) = image_info(image_path, self.logger)

                                if image.width != width:
                                    values["width"] = width

                                if image.height != height:
                                    values["height"] = height

                                if (
                                    creation_date
                                    and image.creation_date != creation_date
                                ):
                                    if (
                                        self.IMAGES_TABLE["creation_date"]
                                        == Types.NUMBER
                                    ):
                                        values["creation_date"] = int(
                                            creation_date.timestamp()
                                        )
                                    else:
                                        values["creation_date"] = creation_date

                                # If there's an existing value for this,
                                # our value is more likely to be 'correct'
                                # than the file
                                if not image.creator and artist:
                                    values["creator"] = artist

                                # see above
                                if not image.caption and caption:
                                    values["caption"] = caption

                                if exif and image.exif != exif:
                                    values["exif"] = json.dumps(exif)

                            await cursor.execute(
                                self.sql.format(
                                    "UPDATE images SET {} WHERE id = {} AND hash = {};",
                                    self.sql.join(
                                        ", ",
                                        [
                                            self.sql.format(
                                                "{} = {}",
                                                self.sql.identifier(value),
                                                self.sql.placeholder(value),
                                            )
                                            for value in values.keys()
                                        ],
                                    ),
                                    self.sql.placeholder("id"),
                                    self.sql.placeholder("old_hash"),
                                ),
                                {"id": image.id, "old_hash": old_hash, **values},
                            )
                    else:
                        images.append(image)

        return images

    async def add_tag(
        self,
        tag: str,
        description: Optional[str | NotSupplied] = NotSupplied(),
    ):
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await self._add_tag(cursor, tag, description)

    async def _add_tag(
        self,
        cursor,
        tag: str,
        description: Optional[str | NotSupplied] = NotSupplied(),
        return_id: bool = False,
    ) -> Optional[int]:
        if not re.search(r"^([^/]+)(/[^/]+)*$", tag):
            raise ValueError(f"Illegal tag name: {tag}")

        if isinstance(description, NotSupplied):
            conflict_clause = self.sql.format("DO NOTHING")
            description = None
        else:
            conflict_clause = self.sql.format(
                "(name) DO UPDATE SET description={}",
                self.sql.placeholder("description"),
            )

        serialized = serialize_tag(tag)
        await cursor.execute(
            self.sql.format(
                """
                INSERT INTO tags (name, escaped_name, depth, description)
                VALUES ({}, {}, {}, {})
                ON CONFLICT {}
                RETURNING id;
                """,
                self.sql.placeholder("name"),
                self.sql.placeholder("escaped_name"),
                self.sql.placeholder("depth"),
                self.sql.placeholder("description"),
                conflict_clause,
            ),
            {
                "name": serialized,
                "escaped_name": escape(serialized, self.sql.escape),
                "depth": tag.count("/") + 1,
                "description": description,
            },
        )
        row = await cursor.fetchone()
        if not row and return_id:  # DO NOTHING won't return the id
            await cursor.execute(
                f"SELECT id FROM tags WHERE name = {self.sql.param} LIMIT 1;",
                (serialized,),
            )
            row = await cursor.fetchone()

        if row:
            return row[0]

        return None

    async def move_tag(self, current: str, new: str, /, cascade: bool = True) -> int:
        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            values = {"name": serialize_tag(current)}
            if cascade:
                current_depth = current.count("/")
                new_depth = new.count("/")
                if current_depth < new_depth:
                    direction = self.sql.format("DESC")
                else:
                    direction = self.sql.format("ASC")

                query = self.sql.format(
                    """
                    SELECT name, id
                    FROM tags
                    WHERE name LIKE {} ESCAPE {}
                    ORDER BY depth {};
                    """,
                    self.sql.placeholder("name"),
                    self.sql.literal(self.sql.escape),
                    direction,
                )
                values["name"] = f"{escape(values['name'], self.sql.escape)}%"
            else:
                query = self.sql.format(
                    "SELECT name, id FROM tags WHERE name = {};",
                    self.sql.placeholder("name"),
                )

            await self.ensure_foreign_keys(cursor)

            offset = len(current)

            count = 0
            await cursor.execute(query, values)
            for name, id in await cursor.fetchall():
                count += 1

                new_name = f"{new}{deserialize_tag(name)[offset:]}"
                new_serialized = serialize_tag(new_name)

                await cursor.execute(
                    f"SELECT id FROM tags WHERE name = {self.sql.param};",
                    (new_serialized,),
                )
                row = await cursor.fetchone()

                if row:
                    (new_id,) = row
                    await cursor.execute(
                        # TODO: replace this with an on conflict?
                        f"""
                        UPDATE image_tags
                        SET tag = {self.sql.param}
                        WHERE tag = {self.sql.param} AND image NOT IN (
                            SELECT image FROM image_tags WHERE tag = {self.sql.param}
                        );
                        """,
                        (new_id, id, new_id),
                    )
                    await cursor.execute(
                        f"DELETE FROM tags WHERE id = {self.sql.param};", (id,)
                    )
                else:
                    new_escaped = f"{escape(new_serialized, self.sql.escape)}%"

                    await cursor.execute(
                        f"""
                        UPDATE tags
                        SET name = {self.sql.param}, escaped_name = {self.sql.param}
                        WHERE id = {self.sql.param};
                        """,
                        (new_serialized, new_escaped, id),
                    )

        return count

    async def remove_tag(self, tag: str, cascade: bool = False):
        serialized = serialize_tag(tag)
        if cascade:
            serialized = f"{escape(serialized, self.sql.escape)}%"
            statement = f"""
            DELETE FROM tags
            WHERE name LIKE {self.sql.param} ESCAPE '{self.sql.escape}';
            """
        else:
            statement = f"DELETE FROM tags WHERE name = {self.sql.param};"

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await self.ensure_foreign_keys(cursor)
            await cursor.execute(statement, (serialized,))

    async def get_tag(self, tag: str, children: bool = False) -> Tag:
        serialized = serialize_tag(tag)

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            description = None
            kids: set[str] = set()

            await cursor.execute(
                f"SELECT description FROM tags WHERE name = {self.sql.param};",
                (serialized,),
            )
            row = await cursor.fetchone()
            if row:
                description = row[0]

            if children:
                serialized = f"{escape(serialized, self.sql.escape)}_%"

                await cursor.execute(
                    f"""
                    SELECT name
                    FROM tags
                    WHERE name LIKE {self.sql.param} ESCAPE '{self.sql.escape}';
                    """,
                    (serialized,),
                )
                ignore = len(tag) + 1
                for (serialized,) in await cursor.fetchall():
                    kids.add(deserialize_tag(serialized)[ignore:].split("/", 1)[0])

            return Tag(tag, description, kids)

    async def all_tag_names(self) -> set[str]:
        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            await cursor.execute("SELECT name FROM tags;")
            return {
                deserialize_tag(serialized) for (serialized,) in await cursor.fetchall()
            }

    async def all_tags(self) -> dict[str, Any]:
        tags: dict[str, Any] = {}

        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            await cursor.execute("SELECT name, description FROM tags;")
            for serialized, description in await cursor.fetchall():
                current = tags
                *parents, name = deserialize_tag(serialized).split("/")
                for part in parents:
                    if part not in current:
                        current[part] = {"description": None, "children": {}}

                    current = current[part]["children"]

                if name in current:
                    current[name]["description"] = description
                else:
                    current[name] = {"description": description, "children": {}}

        return tags

    async def get_tag_set(self, *image_ids: int, minimum: int = 1) -> dict[str, int]:
        tags = {}

        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            values = {"minimum": minimum or 0}  # or 0 to be nice to Nones
            query = self.sql.format(
                """
                SELECT tag, COUNT(image) FROM image_tags
                WHERE {}
                GROUP BY tag
                HAVING COUNT(image) >= {}
                ORDER BY COUNT(image) DESC, tag ASC;
                """,
                Number("image", Comparator.EQUALS, list(image_ids)).prepare(
                    self.sql, values
                ),
                self.sql.placeholder("minimum"),
            )
            await cursor.execute(query, values)

            for tag_id, count in await cursor.fetchall():
                await cursor.execute(
                    f"SELECT name FROM tags WHERE id = {self.sql.param};",
                    (tag_id,),
                )
                row = await cursor.fetchone()
                if row:
                    name = deserialize_tag(row[0])
                    tags[name] = count

        return tags

    async def _related_tags(self, cursor, tag: str) -> set[int]:
        await cursor.execute(
            f"""
            SELECT id
            FROM tags
            WHERE name LIKE {self.sql.param} ESCAPE '{self.sql.escape}';
            """,
            (f"{serialize_tag(tag)}%",),
        )
        return {tag_id for (tag_id,) in await cursor.fetchall()}

    async def create_session(
        self,
        data: dict[str, Any],
        expires: Optional[datetime] = None,
    ) -> int:
        if expires is None:
            expires = datetime.utcnow().astimezone(timezone.utc) + EXPIRATION

        if self.SESSION_INFO_TABLE["expires"] == Types.NUMBER:
            date: int | datetime = int(expires.timestamp())
        else:
            date = expires

        serialized = json.dumps(data)

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await cursor.execute(
                f"""
                INSERT INTO session_info (expires, data)
                VALUES ({self.sql.param}, {self.sql.param})
                RETURNING id;
                """,
                (date, serialized),
            )
            (session_id,) = await cursor.fetchone()

        return session_id

    async def get_session(self, session_id: int) -> Optional[dict[str, Any]]:
        """Fetch session data

        Args:
            session_id: The id of the session

        Returns:
            the session data, if it exists
        """
        data = None

        async with (
            await self.connect() as connection,
            self.cursor(connection) as cursor,
        ):
            await cursor.execute(
                f"SELECT data FROM session_info WHERE id = {self.sql.param};",
                (session_id,),
            )
            row = await cursor.fetchone()

            if row:
                if self.SESSION_INFO_TABLE["data"] == Types.TEXT:
                    data = json.loads(row[0])
                else:
                    data = row[0]

        return data

    async def prune_sessions(self):
        cutoff = datetime.utcnow().astimezone(timezone.utc)

        if self.SESSION_INFO_TABLE["expires"] == Types.NUMBER:
            cutoff = int(cutoff.timestamp())

        async with (
            await self.connect() as connection,
            self.cursor(connection, commit=True) as cursor,
        ):
            await cursor.execute(
                f"DELETE FROM session_info WHERE expires < {self.sql.param};",
                (cutoff,),
            )

    async def fetch_tags(self, cursor, id: int) -> list[str]:
        await cursor.execute(
            f"""
            SELECT t.name FROM tags t, image_tags i
            WHERE t.id = i.tag AND i.image = {self.sql.param};
            """,
            (id,),
        )
        return [deserialize_tag(tag) for (tag,) in await cursor.fetchall()]

    def _build_filter(
        self,
        table: dict[str, Types],
        filter: Optional[Comparison],
        values: dict[str, Any],
        additional_comparison: Optional[Any] = None,
    ):
        conditions = []
        if filter:
            filter.validate(table)
            conditions.append(filter.prepare(self.sql, values))

        if additional_comparison:
            conditions.append(additional_comparison)

        if conditions:
            return self.sql.format(" WHERE {}", self.sql.join(" AND ", conditions))

        return self.sql.format("")

    def _build_ordering(
        self,
        table: dict[str, Types],
        order: Optional[tuple[str, ...]],
        limit: Optional[int],
        offset: Optional[int],
        values: dict[str, Any],
    ):
        parts = []

        if order:
            order_parts: list = []
            for part in order:
                raw_part = part
                descending = False
                nulls = None

                if order_parts:
                    order_parts.append(self.sql.format(", "))

                if part == "random":
                    order_parts.append(self.sql.format("random()"))
                else:
                    if part.startswith("-"):
                        descending = True
                        part = part[1:]

                    if part.startswith(NULL_SYMBOL):
                        nulls = self.sql.format(" NULLS FIRST")
                        part = part[1:]

                    if part.endswith(NULL_SYMBOL):
                        if nulls:
                            raise ValueError(raw_part)

                        nulls = self.sql.format(" NULLS LAST")
                        part = part[:-1]

                    if part not in table:
                        raise ValueError(f"Unknown property: {part}")

                    order_parts.append(self.sql.identifier(part))

                    if descending:
                        order_parts.append(self.sql.format(" DESC"))

                    if nulls:
                        order_parts.append(nulls)

            parts.append(
                self.sql.format(" ORDER BY {}", self.sql.join("", order_parts))
            )

        if limit:
            values["limit"] = limit
            parts.append(self.sql.format(" LIMIT {}", self.sql.placeholder("limit")))

            if offset:
                values["offset"] = offset
                parts.append(
                    self.sql.format(" OFFSET {}", self.sql.placeholder("offset"))
                )

        return self.sql.join("", parts)


def serialize_tag(tag: str) -> str:
    return f"//{tag}/"


def deserialize_tag(serialized: str) -> str:
    return serialized[2:-1]


__all__ = ("DbApi",)
