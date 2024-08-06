import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pytest


def test_sqlitesql():
    from picpocket.database.sqlite import SqliteSQL

    sql = SqliteSQL()

    # most checks done as part of api checks but we want to make sure
    # placeholder/identifier are handled correctly

    for safe in ("col", "table.col", "column_name", "column1"):
        assert sql.identifier(safe) == f'"{safe}"'

    for dangerous in ("", '"hi"', "'hi'", "name;", "two part"):
        with pytest.raises(ValueError):
            print(sql.identifier(dangerous))

    for safe in ("col", "column_name", "column1"):
        assert sql.placeholder(safe) == f":{safe}"

    for dangerous in ("", '"hi"', "'hi'", "name;", "two part", "table.col"):
        with pytest.raises(ValueError):
            print(sql.placeholder(dangerous))


def test_parse_connection_info(tmp_path):
    from picpocket.database.sqlite import Sqlite

    # default
    config, credentials = Sqlite.parse_connection_info(tmp_path)
    assert config == {"path": "picpocket.sqlite3"}
    assert credentials is None

    # absolute path
    config, credentials = Sqlite.parse_connection_info(
        tmp_path, path=Path.home() / "test.db"
    )
    assert config == {"path": str(Path.home() / "test.db")}
    assert credentials is None

    # relative path
    config, credentials = Sqlite.parse_connection_info(tmp_path, path="test.db")
    assert config == {"path": str(Path.cwd() / "test.db")}
    assert credentials is None

    # both paths relative
    config, credentials = Sqlite.parse_connection_info(
        Path("directory"), path="test.db"
    )
    assert config == {"path": str(Path.cwd() / "test.db")}
    assert credentials is None

    # both paths relative
    config, credentials = Sqlite.parse_connection_info(Path("dir"), path="dir/test.db")
    assert config == {"path": "test.db"}
    assert credentials is None

    # path of wrong type
    with pytest.raises(TypeError):
        Sqlite.parse_connection_info(tmp_path, path=False)

    # unknown arguments
    with pytest.raises(ValueError):
        Sqlite.parse_connection_info(tmp_path, path="test.db", key="value")


@pytest.mark.asyncio
async def test_matching_version(tmp_path):
    from picpocket.configuration import Configuration
    from picpocket.database.sqlite import SCHEMA_FILE, SCHEMA_VERSION, Sqlite
    from picpocket.version import Version

    configuration = Configuration.new(
        tmp_path, {"backend": {"type": "sqlite", "connection": {"path": "test.sqlite"}}}
    )

    sqlite = Sqlite(configuration)

    assert sqlite.get_api_version() == SCHEMA_VERSION

    # create the database file
    sqlite3.connect(tmp_path / "test.sqlite").close()

    assert not await sqlite.matching_version()

    async with await sqlite.connect() as connection:
        # no rows
        cursor = await connection.cursor()
        await cursor.executescript(SCHEMA_FILE.read_text())
        await connection.commit()

        assert not await sqlite.matching_version()

        with pytest.raises(ValueError):
            await sqlite.get_version()

        # matching version
        await cursor.execute(
            "INSERT INTO version (major, minor, patch, label) VALUES (?, ?, ?, ?);",
            SCHEMA_VERSION,
        )
        await connection.commit()

        assert await sqlite.matching_version()
        assert await sqlite.get_version() == SCHEMA_VERSION

        # version mismatch
        for offset in (-1, 1):
            for version in (
                Version(
                    SCHEMA_VERSION.major + offset,
                    SCHEMA_VERSION.minor,
                    SCHEMA_VERSION.patch,
                    SCHEMA_VERSION.label,
                ),
                Version(
                    SCHEMA_VERSION.major - offset,
                    SCHEMA_VERSION.minor,
                    SCHEMA_VERSION.patch,
                    SCHEMA_VERSION.label,
                ),
                Version(
                    SCHEMA_VERSION.major,
                    SCHEMA_VERSION.minor + offset,
                    SCHEMA_VERSION.patch,
                    SCHEMA_VERSION.label,
                ),
                Version(
                    SCHEMA_VERSION.major,
                    SCHEMA_VERSION.minor - offset,
                    SCHEMA_VERSION.patch,
                    SCHEMA_VERSION.label,
                ),
                Version(
                    SCHEMA_VERSION.major,
                    SCHEMA_VERSION.minor,
                    SCHEMA_VERSION.patch + offset,
                    SCHEMA_VERSION.label,
                ),
                Version(
                    SCHEMA_VERSION.major,
                    SCHEMA_VERSION.minor,
                    SCHEMA_VERSION.patch - offset,
                    SCHEMA_VERSION.label,
                ),
                Version(
                    SCHEMA_VERSION.major,
                    SCHEMA_VERSION.minor,
                    SCHEMA_VERSION.patch,
                    f"{SCHEMA_VERSION.label}-1",
                ),
            ):
                await cursor.execute(
                    """
                    INSERT INTO version (major, minor, patch, label)
                    VALUES (?, ?, ?, ?);
                    """,
                    version,
                )
                await connection.commit()

                assert not await sqlite.matching_version()
                assert await sqlite.get_version() == version

        # make sure it's looking at the last
        await cursor.execute(
            "INSERT INTO version (major, minor, patch, label) VALUES (?, ?, ?, ?);",
            SCHEMA_VERSION,
        )
        await connection.commit()

        assert await sqlite.matching_version()


@pytest.mark.asyncio
async def test_connect(tmp_path):
    from picpocket.configuration import Configuration
    from picpocket.database.sqlite import Sqlite

    db = tmp_path / "test.db"
    configuration = Configuration.new(
        tmp_path, {"backend": {"type": "sqlite", "connection": {"path": str(db)}}}
    )

    sqlite = Sqlite.load(configuration)

    connnection = sqlite3.connect(db)
    connnection.execute("CREATE TABLE test (value TEXT);")
    connnection.commit()

    async with await sqlite.connect() as aconnection:
        cursor = await aconnection.cursor()
        await cursor.execute(
            "INSERT INTO test (value) VALUES (:value)", {"value": "hi"}
        )
        await aconnection.commit()

    assert connnection.execute("SELECT value FROM TEST;").fetchall() == [("hi",)]

    # relative file
    Configuration.new(
        tmp_path, {"backend": {"type": "sqlite", "connection": {"path": db.name}}}
    )
    sqlite.configuration.reload()

    async with await sqlite.connect() as aconnection:
        cursor = await aconnection.cursor()
        await cursor.execute(
            "INSERT INTO test (value) VALUES (:value)", {"value": "hey"}
        )
        await aconnection.commit()

    assert connnection.execute("SELECT value FROM TEST;").fetchall() == [
        ("hi",),
        ("hey",),
    ]

    # unsupported db type
    Configuration.new(
        tmp_path, {"backend": {"type": "other", "connection": {"path": str(db)}}}
    )
    sqlite.configuration.reload()

    with pytest.raises(ValueError):
        async with await sqlite.connect():
            pass

    # missing db file
    Configuration.new(
        tmp_path, {"backend": {"type": "sqlite", "connection": {"path": "fake.sqlite"}}}
    )
    sqlite.configuration.reload()

    with pytest.raises(ValueError):
        async with await sqlite.connect():
            pass


@pytest.mark.asyncio
async def test_initialize(tmp_path):
    from picpocket.configuration import Configuration
    from picpocket.database.sqlite import SCHEMA_VERSION, Sqlite

    db = tmp_path / "test.db"
    configuration = Configuration.new(
        tmp_path, {"backend": {"type": "sqlite", "connection": {"path": str(db)}}}
    )

    sqlite = Sqlite(configuration)
    await sqlite.initialize()

    # separate connection to confirm commit
    with sqlite3.connect(db) as connection:
        cursor = connection.cursor()
        cursor.execute("SELECT major, minor, patch, label FROM version;")
        assert cursor.fetchone() == SCHEMA_VERSION

    # can't reinitialize
    with pytest.raises(ValueError):
        await sqlite.initialize()


@pytest.mark.asyncio
async def test_create_backup(load_api, tmp_path, image_files):
    from picpocket.version import SQLITE_VERSION

    async with load_api(backend="sqlite") as api:
        await api.add_tag("dogs", "dogs are cool")
        await api.add_tag("tag", "a tag")
        await api.add_tag("tag/that/is/nested", "another tag")

        main = tmp_path / "main"
        main.mkdir()
        shutil.copy2(image_files[0], main / "a.jpg")
        shutil.copy2(image_files[1], main / "b.jpg")

        portable = tmp_path / "portable"
        portable.mkdir()
        (portable / "subdirectory").mkdir()
        shutil.copy2(image_files[0], portable / "a.jpg")
        shutil.copy2(image_files[1], portable / "subdirectory" / "b.jpg")

        main_id = await api.add_location(
            "main",
            main,
            description="main storage",
            source=True,
            destination=True,
            removable=False,
        )
        await api.import_location(main_id, creator="bcj", tags=["tag/that", "other"])
        ajpg = await api.find_image(main / "a.jpg")
        await api.edit_image(
            ajpg.id,
            caption="a description",
            title="Title",
            alt="alt text",
            rating=5,
        )

        await api.add_location("portable", destination=True, removable=True)
        await api.mount("portable", portable)
        await api.import_location("portable")
        await api.unmount("portable")

        await api.add_task(
            "my task",
            description="a task description",
            source="portable",
            destination="main",
            source_path="subdirectory/{year}/{month}",
            destination_format="from_portable/{file}",
            tags=["a", "b/c"],
        )
        await api.add_task(
            "reversed",
            source="main",
            destination="portable",
            source_path="directory",
            destination_format="from_main/{file}",
        )
        await api.add_task(
            "portable task",
            description="a task that only touches portable",
            source="portable",
            destination="portable",
            creator="bcj",
            file_formats=["bmp"],
        )

        filename = tmp_path / "backup.sqlite"
        directory = tmp_path / "subdirectory"

        path_1 = await api.create_backup(filename)
        assert path_1 == filename
        assert path_1.exists()

        before = datetime.now().replace(microsecond=0)
        path_2 = await api.create_backup(directory)
        after = datetime.now()
        assert path_2.parent == directory
        assert path_2.exists()
        match = re.search(
            (
                r"^picpocket-(\d+\.\d+\.\d+(?:\.dev)?)"
                r"-(\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})\.sqlite$"
            ),
            path_2.name,
        )
        assert match
        assert match.group(1) == str(SQLITE_VERSION)
        date = datetime.strptime(match.group(2), "%Y-%m-%d-%H-%M-%S")
        assert before <= date <= after

        assert path_1.read_bytes() == path_2.read_bytes()

        # We probably don't need to be exhaustive here since we know we
        # are just copying the database directly
        with sqlite3.connect(path_1) as connection:
            assert connection.execute("SELECT COUNT(*) FROM tags").fetchone() == (5,)
            assert connection.execute("SELECT COUNT(*) FROM locations").fetchone() == (
                2,
            )
            assert connection.execute("SELECT COUNT(*) FROM images").fetchone() == (4,)
            assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone() == (3,)


@pytest.mark.asyncio
async def test_import_images_batching(load_api, tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    for index in range(9):
        file = root / f"{index}.jpg"
        file.write_text("hi")

    async with load_api(backend="sqlite") as api, await api.connect() as connection:
        root_id = await api.add_location("root", root, destination=True)

        image_ids = []
        importer = await api._import_images(
            root_id, root, batch_size=3, image_ids=image_ids
        )
        query = "SELECT COUNT(*) FROM images;"

        cursor = await connection.cursor()

        await importer.asend(root / "0.jpg")
        assert len(image_ids) == 0
        await cursor.execute(query)
        assert await cursor.fetchone() == (0,)

        await importer.asend(root / "1.jpg")
        assert len(image_ids) == 0
        await cursor.execute(query)
        assert await cursor.fetchone() == (0,)

        await importer.asend(root / "2.jpg")
        assert len(image_ids) == 3
        await cursor.execute(query)
        assert await cursor.fetchone() == (3,)

        await importer.asend(root / "3.jpg")
        assert len(image_ids) == 3
        await cursor.execute(query)
        assert await cursor.fetchone() == (3,)

        await importer.asend(root / "4.jpg")
        assert len(image_ids) == 3
        await cursor.execute(query)
        assert await cursor.fetchone() == (3,)

        await importer.asend(root / "5.jpg")
        assert len(image_ids) == 6
        await cursor.execute(query)
        assert await cursor.fetchone() == (6,)

        await importer.asend(root / "6.jpg")
        assert len(image_ids) == 6
        await cursor.execute(query)
        assert await cursor.fetchone() == (6,)

        await importer.asend(root / "7.jpg")
        assert len(image_ids) == 6
        await cursor.execute(query)
        assert await cursor.fetchone() == (6,)

        with pytest.raises(Exception):
            await importer.asend(root / "-1.jpg")

        assert len(image_ids) == 6
        await cursor.execute(query)
        assert await cursor.fetchone() == (6,)
