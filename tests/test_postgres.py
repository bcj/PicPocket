import os
import shutil
from pathlib import Path

import pytest

TEST_IMAGES = Path(__file__).parent / "images"
IMAGE_FILES = [TEST_IMAGES / "a.bmp", TEST_IMAGES / "b.bmp", TEST_IMAGES / "c.bmp"]


def test_parse_connection_info(tmp_path):
    if os.environ["PICPOCKET_BACKEND"] != "postgres":
        pytest.skip("skipping postgres tests")

    from picpocket.database.postgres import Postgres

    config, credentials = Postgres.parse_connection_info(tmp_path)
    assert config == {
        "port": 5432,
        "dbname": "picpocket",
        "user": "picpocket",
        "password": "",
    }
    assert credentials == ""

    config, credentials = Postgres.parse_connection_info(
        tmp_path, store_credentials=False
    )
    assert config == {
        "port": 5432,
        "dbname": "picpocket",
        "user": "picpocket",
        "password": True,
    }
    assert credentials == ""

    config, credentials = Postgres.parse_connection_info(
        tmp_path,
        store_credentials=False,
        host="localhost",
        port=1234,
        dbname="test_db",
        user="user",
        password="password",
    )
    assert config == {
        "host": "localhost",
        "port": 1234,
        "dbname": "test_db",
        "user": "user",
        "password": True,
    }
    assert credentials == "password"

    config, credentials = Postgres.parse_connection_info(
        tmp_path,
        store_credentials=True,
        host="localhost",
        port=1234,
        dbname="test_db",
        user="user",
        password="password",
    )
    assert config == {
        "host": "localhost",
        "port": 1234,
        "dbname": "test_db",
        "user": "user",
        "password": "password",
    }
    assert credentials == "password"

    config, credentials = Postgres.parse_connection_info(
        tmp_path,
        host="localhost",
        port=1234,
        dbname="test_db",
        user="user",
        password="password",
    )
    assert config == {
        "host": "localhost",
        "port": 1234,
        "dbname": "test_db",
        "user": "user",
        "password": True,
    }
    assert credentials == "password"

    for kwargs in (
        {"host": 1},
        {"port": "5432"},
        {"dbname": 1},
        {"user": 1},
        {"password": True},
    ):
        with pytest.raises(TypeError):
            Postgres.parse_connection_info(tmp_path, **kwargs)


# this is async so we can use db_connect
@pytest.mark.asyncio
async def test_get_types(pg_credentials):
    import psycopg

    from picpocket.database.postgres import TYPES_FILE, _get_types

    custom_types = _get_types()
    assert len(custom_types) == TYPES_FILE.read_text().count("CREATE TYPE")

    assert custom_types

    # add types
    async with (
        await psycopg.AsyncConnection.connect(**pg_credentials) as connection,
        psycopg.AsyncClientCursor(connection) as cursor,
    ):
        await cursor.execute("SELECT COUNT(*) FROM pg_type;")
        before_types = (await cursor.fetchone())[0]

        await cursor.execute(TYPES_FILE.read_text())

        await cursor.execute("SELECT COUNT(*) FROM pg_type;")
        after_types = (await cursor.fetchone())[0]

        found_types = set()
        await cursor.execute(
            "SELECT typname FROM pg_type WHERE typname = ANY(%s);",
            (list(custom_types),),
        )
        for (name,) in await cursor.fetchall():
            found_types.add(name)

    assert custom_types == found_types

    # double the types to account for _custom_type, the array variant
    assert before_types + (2 * len(custom_types)) == after_types


# this is async so we can use db_connect
@pytest.mark.asyncio
async def test_get_tables(pg_credentials):
    import psycopg

    from picpocket.database.postgres import SCHEMA_FILE, TYPES_FILE, _get_tables

    tables = _get_tables()
    assert len(tables) == SCHEMA_FILE.read_text().count("CREATE TABLE")

    assert tables

    # add tables
    async with (
        await psycopg.AsyncConnection.connect(**pg_credentials) as connection,
        psycopg.AsyncClientCursor(connection) as cursor,
    ):
        await cursor.execute("SELECT COUNT(*) FROM pg_tables;")
        before_tables = (await cursor.fetchone())[0]

        await cursor.execute(TYPES_FILE.read_text())
        await cursor.execute(SCHEMA_FILE.read_text())

        await cursor.execute("SELECT COUNT(*) FROM pg_tables;")
        after_tables = (await cursor.fetchone())[0]

        found_tables = set()
        await cursor.execute(
            "SELECT tablename FROM pg_tables WHERE tablename = ANY(%s);",
            (list(tables),),
        )
        for (name,) in await cursor.fetchall():
            found_tables.add(name)

    assert found_tables == tables
    assert before_tables + len(tables) == after_tables


@pytest.mark.asyncio
async def test_matching_version(load_api):
    if os.environ["PICPOCKET_BACKEND"] != "postgres":
        pytest.skip("skipping postgres tests")

    import psycopg

    from picpocket.database.postgres import SCHEMA_FILE, SCHEMA_VERSION, TYPES_FILE
    from picpocket.version import Version
    from tests.conftest import _wipe

    async with load_api(backend="postgres") as api, await api.connect() as connection:
        assert api.get_api_version() == SCHEMA_VERSION

        _wipe(api.configuration.contents["backend"]["connection"])

        assert not await api.matching_version()

        # no rows
        async with psycopg.AsyncClientCursor(connection) as cursor:
            await cursor.execute(TYPES_FILE.read_text())
            await cursor.execute(SCHEMA_FILE.read_text())
            await connection.commit()

        assert not await api.matching_version()

        with pytest.raises(ValueError):
            await api.get_version()

        # matching version
        async with connection.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO version (version) VALUES (%s);",
                (SCHEMA_VERSION,),
            )
            await connection.commit()

        assert await api.matching_version()
        assert await api.get_version() == SCHEMA_VERSION

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
                async with connection.cursor() as cursor:
                    await cursor.execute(
                        "INSERT INTO version (version) VALUES (%s);",
                        (version,),
                    )
                    await connection.commit()

                assert not await api.matching_version()
                assert await api.get_version() == version

        # make sure it's looking at the last
        async with connection.cursor() as cursor:
            await cursor.execute(
                "INSERT INTO version (version) VALUES (%s);",
                (SCHEMA_VERSION,),
            )
            await connection.commit()

        assert await api.matching_version()


@pytest.mark.asyncio
async def test_connect(create_configuration, pg_credentials):
    from picpocket.configuration import Configuration
    from picpocket.database.postgres import Postgres

    async with create_configuration(use_prompt=True) as configuration:
        # no prompt
        with pytest.raises(ValueError):
            await Postgres(configuration).connect()

        # prompt
        password = pg_credentials.get("password")
        postgres = Postgres(
            Configuration(configuration.directory, prompt=lambda: password)
        )
        async with (
            await postgres.connect() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute("SELECT 1 + 1;")
            assert await cursor.fetchone() == (2,)

    async with create_configuration(backend="other") as configuration:
        # wrong backend specified
        with pytest.raises(ValueError):
            await Postgres(configuration).connect()

    async with create_configuration() as configuration:
        # password provided
        async with (
            await Postgres(configuration).connect() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute("SELECT 1 + 1;")
            assert await cursor.fetchone() == (2,)

        # ensure prompt not called
        def do_not_call():
            raise ValueError("Function called")

        postgres = Postgres(Configuration(configuration.directory, prompt=do_not_call))
        async with (
            await postgres.connect() as connection,
            connection.cursor() as cursor,
        ):
            await cursor.execute("SELECT 1 + 1;")
            assert await cursor.fetchone() == (2,)


@pytest.mark.asyncio
async def test_initialize(pg_credentials, tmp_path):
    import psycopg

    from picpocket.configuration import Configuration
    from picpocket.database.postgres import SCHEMA_VERSION, Postgres, _get_tables

    # basic test + make sure changes are commited
    configuration = Configuration.new(
        tmp_path,
        {
            "backend": {
                "type": "postgres",
                "connection": {
                    key: value or "" for key, value in pg_credentials.items()
                },
            }
        },
    )

    postgres = Postgres(configuration)
    await postgres.initialize()

    # separate connection to confirm commit
    async with (
        await psycopg.AsyncConnection.connect(**pg_credentials) as connection,
        connection.cursor() as cursor,
    ):
        await cursor.execute(
            "SELECT COUNT(tablename) FROM pg_tables WHERE tablename = ANY(%s)",
            (list(_get_tables()),),
        )
        assert await cursor.fetchone() == (len(_get_tables()),)

        await cursor.execute(
            """
            SELECT
                (version).major,
                (version).minor,
                (version).patch,
                (version).label
            FROM version;
            """
        )
        assert await cursor.fetchone() == (
            SCHEMA_VERSION.major,
            SCHEMA_VERSION.minor,
            SCHEMA_VERSION.patch,
            SCHEMA_VERSION.label,
        )

        # can't reinitialize
        with pytest.raises(ValueError):
            await postgres.initialize()


@pytest.mark.asyncio
async def test_import_images(load_api, tmp_path):
    from picpocket.images import hash_image

    async with (
        load_api(backend="postgres") as api,
        await api.connect() as test_connection,
        test_connection.cursor() as cursor,
    ):
        location_id = await api.add_location("main", destination=True)

        root = tmp_path / "main"
        root.mkdir()
        (root / "birds").mkdir()
        goose = root / "birds" / "goose.jpg"
        shutil.copy2(IMAGE_FILES[0], goose)
        dogs = root / "dogs.jpg"
        shutil.copy2(IMAGE_FILES[1], dogs)
        cat = root / "cat.JPEG"
        shutil.copy2(IMAGE_FILES[2], cat)

        importer = await api._import_images(location_id, root)

        await importer.asend(goose)
        await importer.asend(root / "birds" / "goose.JPG")
        await importer.asend(dogs)
        await importer.asend(cat)

        # should not be committed yet
        await cursor.execute(
            "SELECT id, hash, name, extension, location, path FROM images ORDER BY id;",
        )
        await cursor.fetchall() == []

        await importer.aclose()

        await cursor.execute(
            "SELECT hash, name, extension, location, path FROM images ORDER BY id;",
        )
        await cursor.fetchall() == [
            (
                hash_image(goose),
                "goose",
                "jpg",
                location_id,
                "birds/goose.jpg",
            ),
            (hash_image(dogs), "dogs", "jpg", location_id, "dogs.jpg"),
            (hash_image(cat), "cat", "jpeg", location_id, "birds/cat.jpg"),
        ]

        # batching and returning results
        location_id = await api.add_location("other", destination=True)

        root = tmp_path / "other"
        root.mkdir()

        image_ids = []
        importer = await api._import_images(
            location_id,
            root,
            batch_size=2,
            image_ids=image_ids,
        )

        for i in range(0, 100, 2):
            file = root / f"{i}.jpg"
            shutil.copy2(IMAGE_FILES[i % len(IMAGE_FILES)], file)
            await importer.asend(file)

            # don't see changes until batch count hit
            assert len(image_ids) == i
            await cursor.execute(
                "SELECT count(1) FROM images WHERE location = %s;", (location_id,)
            )
            assert await cursor.fetchall() == [(i,)]

            file1 = root / f"{i + 1}.jpg"
            shutil.copy2(IMAGE_FILES[(i + 1) % len(IMAGE_FILES)], file1)
            await importer.asend(file1)

            # don't see changes until batch count hit
            assert len(image_ids) == i + 2
            await cursor.execute(
                "SELECT count(1) FROM images WHERE location = %s;", (location_id,)
            )
            assert await cursor.fetchall() == [(i + 2,)]

        # commit should happen even if no changes
        file = root / "101.jpg"
        shutil.copy2(IMAGE_FILES[101 % len(IMAGE_FILES)], file)
        await importer.asend(file)
        assert len(image_ids) == 100
        await importer.asend(file)
        assert len(image_ids) == 101

        # commit should still happen on close
        file = root / "102.jpg"
        shutil.copy2(IMAGE_FILES[102 % len(IMAGE_FILES)], file)
        await importer.asend(file)
        assert len(image_ids) == 101
        await importer.aclose()
        assert len(image_ids) == 102

        await cursor.execute(
            "SELECT count(1) FROM images WHERE location = %s;", (location_id,)
        )
        assert await cursor.fetchall() == [(102,)]


@pytest.mark.asyncio
async def test_import_images_batching(load_api, tmp_path):
    root = tmp_path / "root"
    root.mkdir()

    for index in range(9):
        file = root / f"{index}.jpg"
        file.write_text("hi")

    async with (
        load_api(backend="postgres") as api,
        await api.connect() as connection,
        connection.cursor() as cursor,
    ):
        root_id = await api.add_location("root", root, destination=True)

        image_ids = []
        importer = await api._import_images(
            root_id, root, batch_size=3, image_ids=image_ids
        )
        query = "SELECT COUNT(*) FROM images;"

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
