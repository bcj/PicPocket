import asyncio
import json
import os
import re
from argparse import ArgumentParser
from contextlib import asynccontextmanager, contextmanager
from multiprocessing import Process
from pathlib import Path
from subprocess import check_call, check_output
from tempfile import TemporaryDirectory
from time import sleep, time
from typing import Any, AsyncGenerator, Callable, Iterator, Optional

import pytest  # type: ignore
import requests

DIRECTORY = Path(__file__).parent.absolute()
CONFIG = DIRECTORY / "pg-config.json"

CURRENT_CONTAINER = None

TEST_IMAGES = Path(__file__).parent / "images"
IMAGE_FILES = [
    TEST_IMAGES / "a.bmp",
    TEST_IMAGES / "b.bmp",
    TEST_IMAGES / "c.bmp",
    TEST_IMAGES / "exif.jpg",
    TEST_IMAGES / "rotated.jpg",
    TEST_IMAGES / "test.jpg",
    TEST_IMAGES / "test.png",
]


@pytest.fixture
def test_images() -> Path:
    return TEST_IMAGES


@pytest.fixture
def image_files() -> list[Path]:
    return IMAGE_FILES


@pytest.fixture
def pg_credentials() -> Iterator[dict[str, str | int]]:
    """
    A fixture supplying information for connecting to a test database,
    and that skips the test if the required information isn't available
    """
    with _get_pg_connection_info() as connection_info:
        yield connection_info


@pytest.fixture
def create_configuration() -> Callable:
    from picpocket.configuration import Configuration

    @asynccontextmanager
    async def function(
        *,
        prompt: Optional[Callable[[], str]] = None,
        backend: Optional[str] = None,
        use_prompt: Optional[bool] = None,
        wipe: bool = True,
    ) -> AsyncGenerator[Configuration, None]:
        if backend is None:
            backend = os.environ["PICPOCKET_BACKEND"]

        if backend == "other":
            with TemporaryDirectory() as directory_name:
                directory = Path(directory_name)
                yield Configuration.new(
                    directory,
                    {"backend": {"type": "other", "connection": {}}},
                    prompt=prompt,
                )
        else:
            async with _load_api(
                prompt=prompt, backend=backend, use_prompt=use_prompt, wipe=wipe
            ) as api:
                configuration = api.configuration

                if prompt or use_prompt:
                    configuration = Configuration(
                        configuration.directory, prompt=prompt
                    )

                yield configuration

    return function


@pytest.fixture
def run_web() -> Callable:
    @asynccontextmanager
    async def run() -> AsyncGenerator[int, None]:
        port = 8000

        async with _load_api() as api:
            process = Process(target=_run_web, args=(port, api.configuration.directory))

            process.start()

            timeout = time() + 2
            while time() < timeout:
                try:
                    requests.get(f"http://localhost:{port}")
                    break
                except Exception:
                    sleep(0.1)
            else:
                raise ValueError("server failed to come up")

            try:
                yield port
            finally:
                process.terminate()

    return run


def _run_web(port: int, directory: Path):
    from picpocket import load
    from picpocket.web import run_server

    api = load(directory)

    with asyncio.Runner() as runner:
        runner.run(run_server(api, port))


@pytest.fixture
def load_api() -> Callable:
    return _load_api


@asynccontextmanager
async def _load_api(
    *,
    prompt: Optional[Callable[[], str]] = None,
    backend: Optional[str] = None,
    use_prompt: Optional[bool] = None,
    wipe: bool = True,
) -> AsyncGenerator[Any, None]:
    """
    Create a configuration file that will allow the user to connect
    to the test database and will be deleted afterward

    prompt: A function to prompt the user for a password
    backend: Which db backend to use
    use_prompt: Whether to prompt the user for a password
        Will default to True if prompt was provided
    wipe: Clear any existing information in the database
    """
    if backend is None:
        backend = os.environ["PICPOCKET_BACKEND"]

    from picpocket import initialize

    with TemporaryDirectory() as directory_name:
        directory = Path(directory_name)

        if use_prompt is None:
            use_prompt = prompt is not None

        store_credentials = not use_prompt

        match backend:
            case "postgres":
                with _get_pg_connection_info() as connection_info:
                    import psycopg

                    if wipe:
                        async with await psycopg.AsyncConnection.connect(
                            **connection_info  # type: ignore
                        ) as connection:
                            await _wipe_async(connection)

                        yield await initialize(
                            directory,
                            "postgres",
                            store_credentials=store_credentials,
                            **connection_info,
                        )
            case "sqlite":
                yield await initialize(directory, "sqlite")
            case _:
                raise ValueError(f"Unsupported backend: {backend}")


@pytest.fixture
def create_parser() -> Callable[[str], tuple[ArgumentParser, Any]]:
    """
    A fixture that returns a function for creating a parser with
    a prebuild subparsers. The function takes one argument, dest which
    defaults to 'command'
    """

    def create(dest="command") -> tuple[ArgumentParser, Any]:
        parser = ArgumentParser()
        subparsers = parser.add_subparsers(dest=dest)

        return parser, subparsers

    return create


@contextmanager
def _get_pg_connection_info() -> Iterator[dict[str, str | int]]:
    if os.environ["PICPOCKET_BACKEND"] != "postgres":
        pytest.skip("skipping postgres tests")

    if not CONFIG.exists():
        pytest.skip("DB not configured: See tests/pg-conf.py")

    with CONFIG.open("r") as stream:
        config = json.load(stream)

    strategy = config.pop("strategy")
    match strategy:
        case "fail":
            raise AssertionError("Postgres tests set to FAIL")
        case "skip":
            pytest.skip("Postgres tests set to SKIP")
        case "external":
            if not config["dbname"].startswith("test"):
                pytest.skip("Refusing to run against a DB not named test...")

            _wipe(config)
            yield config
        case "docker" | "isolated":
            if not config["dbname"].startswith("test"):
                pytest.skip("Refusing to run against a DB not named test...")

            image = config.pop("image")

            # bring up the container if it doesn't exist (or a new one
            # if we're running isolated)
            container = CURRENT_CONTAINER
            if container:
                if strategy == "isolated":
                    delete_container(container)
                    container = start_container(image, config["port"], config)
            else:
                container = start_container(image, config["port"], config)

            _wipe(config)
            yield config

            if strategy == "isolated":
                delete_container(container)
        case _:
            raise ValueError(f"Postgres testing misconfigured: {strategy}")


def start_container(image: str, port: int, connection_info=None) -> str:
    global CURRENT_CONTAINER

    container = check_output(
        ("docker", "create", "-p", f"{port}:5432", image), text=True
    ).strip()
    check_call(("docker", "start", container))
    CURRENT_CONTAINER = container
    timeout = time() + 5
    while time() < timeout:
        if check_output(("docker", "ps", "--filter", f"id={container}", "--quiet")):
            break
    else:
        print(f"container {container} didn't come up in time")

    if connection_info:
        import psycopg

        timeout = time() + 10
        while time() < timeout:
            try:
                psycopg.Connection.connect(**connection_info)
                break
            except Exception:
                sleep(0.1)
        else:
            print("db probably didn't come up in time")
    return container


def delete_container(container: str):
    global CURRENT_CONTAINER

    if check_output(("docker", "ps", "--filter", f"id={container}", "--quiet")):
        check_call(("docker", "stop", container))

    if check_output(
        ("docker", "ps", "--all", "--filter", f"id={container}", "--quiet")
    ):
        check_call(("docker", "rm", "--force", container))

    if CURRENT_CONTAINER:
        CURRENT_CONTAINER = None


def _wipe(connection_info):
    import psycopg

    from picpocket.database.postgres import _get_tables, _get_types

    with (
        psycopg.Connection.connect(**connection_info) as connection,
        connection.cursor() as cursor,
    ):
        # remove tables
        for table in _get_tables():
            # TODO: does psycopg.sql.SQL & .Identifier not work here?
            # in the mean time do a quick check on custom_type
            re.search(r"^[a-z0-9_]+$", table)

            cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

        # remove types
        for custom_type in _get_types():
            # TODO: does psycopg.sql.SQL & .Identifier not work here?
            # in the mean time do a quick check on custom_type
            re.search(r"^[a-z0-9_]+$", custom_type)

            cursor.execute(f"DROP TYPE IF EXISTS {custom_type} CASCADE;")

        connection.commit()


async def _wipe_async(connection):
    from picpocket.database.postgres import _get_tables, _get_types

    async with connection.cursor() as cursor:
        # remove tables
        for table in _get_tables():
            # TODO: does psycopg.sql.SQL & .Identifier not work here?
            # in the mean time do a quick check on custom_type
            assert re.search(r"^[a-z0-9_]+$", table)

            await cursor.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

        # remove types
        for custom_type in _get_types():
            # TODO: does psycopg.sql.SQL & .Identifier not work here?
            # in the mean time do a quick check on custom_type
            assert re.search(r"^[a-z0-9_]+$", custom_type)

            await cursor.execute(f"DROP TYPE IF EXISTS {custom_type} CASCADE;")

    await connection.commit()
