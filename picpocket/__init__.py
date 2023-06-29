"""A tool for tagging, searching, and organizing your photos

.. todo::
    Add more official support for user-defined backends

.. todo::
    Add support for managing Dockerized Postgres
"""
import base64
import logging
import random
from pathlib import Path
from typing import Any, Callable, Optional, Type, cast

from picpocket.api import PicPocket
from picpocket.configuration import CONFIG_FILE, Configuration
from picpocket.database.sqlite import Sqlite
from picpocket.images import IMAGE_FORMATS
from picpocket.version import VERSION, __version__  # noqa: F401

try:
    from picpocket.database.postgres import Postgres

    postgres: Optional[Type[PicPocket]] = Postgres
except ImportError:
    postgres = None

APIS = {
    "postgres": postgres,
    "sqlite": Sqlite,
}

LOGGER = logging.getLogger("picpocket")


async def initialize(
    directory: Path,
    backend: str = "sqlite",
    /,
    *,
    store_credentials: Optional[bool] = None,
    **connection_info,
) -> PicPocket:
    """Create a new PicPocket store

    .. warning::
        If you're using PostgreSQL, it's expected that you have already
        configured the database server.

    Args:
        directory: Where to save the configuration for PicPocket
        store_credentials: Whether to store the database password in the
            configuration. If None, the password will only be saved if
            it's blank.
    connection_info: See
        picpocket.database.BACKEND.parse_connection_info for valid
        arguments.

    Returns:
        An API instance for the newly-created PicPocket store
    """
    path = directory / CONFIG_FILE

    if path.exists():
        raise ValueError(f"Config already exists at {path}")

    directory.mkdir(parents=True, exist_ok=True)

    api_type = APIS.get(backend)
    if api_type is None:
        raise ValueError(f"Unsupported backend {backend}")

    config: dict[str, dict[str, Any]] = {
        "version": {
            "major": VERSION.major,
            "minor": VERSION.minor,
            "patch": VERSION.patch,
        },
        "backend": {"type": api_type.BACKEND_NAME},
        "files": {"formats": sorted(IMAGE_FORMATS)},
        "web": {
            # TODO: rotate this automatically ever x days
            "secret": base64.encodebytes(random.randbytes(50)).decode().strip(),
            "previous": [],
        },
    }

    if VERSION.label:
        config["version"]["label"] = VERSION.label

    db_info, credentials = api_type.parse_connection_info(
        directory, store_credentials=store_credentials, **connection_info
    )

    config["backend"]["connection"] = db_info

    LOGGER.info("creating config file: %s", path)
    configuration = Configuration.new(directory, config, prompt=lambda: credentials)
    api = api_type.load(configuration)

    LOGGER.info("initializing database")
    await api.initialize()

    return api


def load(directory: Path, prompt: Optional[Callable[[], str]] = None) -> PicPocket:
    """Load PicPocket

    Args:
        directory: The folder where the PicPocket configuration is stored.
        prompt: A function to call to prompt the user for credentials

    Returns:
        An API instance for the PicPocket store
    """
    configuration = Configuration(directory, prompt=prompt)
    # it's fine to cast here since we'll error in a moment regardless
    api_type = APIS.get(cast(str, configuration.backend))
    if api_type is None:
        raise ValueError(f"Unsupported backend {configuration.backend}")

    return api_type.load(configuration)


all = ("__version__", "initialize", "load")
