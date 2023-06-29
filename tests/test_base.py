import os
import tomllib

import pytest


@pytest.mark.asyncio
async def test_initialize_postgres(pg_credentials, tmp_path):
    from tests.conftest import _wipe

    async def wipe_db():
        _wipe(pg_credentials)

    await _initialize("postgres", wipe_db, pg_credentials, tmp_path)


@pytest.mark.asyncio
async def test_initialize_sqlite(tmp_path):
    path = tmp_path / "test.db"
    connection_info = {"path": path}

    async def wipe_db():
        if path.exists():
            path.unlink()

    await _initialize("sqlite", wipe_db, connection_info, tmp_path)


async def _initialize(backend, wipe_db, connection_info, tmp_path):
    from picpocket import initialize
    from picpocket.configuration import CONFIG_FILE
    from picpocket.images import IMAGE_FORMATS
    from picpocket.version import VERSION

    config_file = tmp_path / CONFIG_FILE

    # error without creating anything on an invalid backend
    with pytest.raises(ValueError):
        await initialize(tmp_path, "other", **connection_info)

    assert list(tmp_path.iterdir()) == []

    # remember password
    # don't overwrite
    config_file.write_text("hi")
    with pytest.raises(ValueError):
        await initialize(tmp_path, backend, store_credentials=True, **connection_info)

    assert config_file.read_text() == "hi"
    config_file.unlink()

    api = await initialize(tmp_path, backend, store_credentials=True, **connection_info)

    assert api.configuration.directory == tmp_path
    assert config_file.exists()

    with config_file.open("rb") as stream:
        config = tomllib.load(stream)

    assert config["version"]["major"] == VERSION.major
    assert config["version"]["minor"] == VERSION.minor
    assert config["version"]["patch"] == VERSION.patch
    if VERSION.label:
        config["version"]["label"] == VERSION.label
    else:
        assert "label" not in config["version"]

    assert config["backend"]["type"] == backend

    assert config["files"] == {"formats": list(sorted(IMAGE_FORMATS))}

    await wipe_db()

    # forget password
    config_file.unlink()
    api = await initialize(
        tmp_path, backend, store_credentials=False, **connection_info
    )

    assert api.configuration.directory == tmp_path

    assert config_file.exists()

    with config_file.open("rb") as stream:
        config = tomllib.load(stream)

    assert config["version"]["major"] == VERSION.major
    assert config["version"]["minor"] == VERSION.minor
    assert config["version"]["patch"] == VERSION.patch
    if VERSION.label:
        config["version"]["label"] == VERSION.label
    else:
        assert "label" not in config["version"]

    assert config["backend"]["type"] == backend


@pytest.mark.asyncio
async def test_load(create_configuration):
    from picpocket import APIS, load

    backend_type = APIS[os.environ["PICPOCKET_BACKEND"]]

    async with create_configuration(backend=backend_type.BACKEND_NAME) as configuration:
        api = load(configuration.directory)
        assert isinstance(api, backend_type)

    async with create_configuration(backend="other") as configuration:
        with pytest.raises(ValueError):
            load(configuration.directory)
