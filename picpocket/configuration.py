from __future__ import annotations

"""Tools for accessing PicPocket configuration files"""
import tomllib
from pathlib import Path
from typing import Any, Callable, Optional

import tomli_w

CONFIG_FILE = "picpocket-config.toml"


class Configuration:
    """An object representing the PicPocket configuration file."""

    def __init__(
        self,
        directory: Path,
        *,
        prompt: Optional[Callable[[], Optional[str]]] = None,
    ):
        self.directory = directory
        self.file = directory / CONFIG_FILE
        self._contents: Optional[dict] = None

        self._credentials: Any = None
        self._cached = False
        self._prompt = prompt

        self._backend = None

    @property
    def contents(self):
        """The contents of the PicPocket configuration file"""

        if self._contents is None:
            self.reload()

        return self._contents

    @property
    def backend(self) -> Optional[str]:
        """Get the name of the backend configuration"""

        if self._backend is None:
            self._backend = self.contents["backend"]["type"]

        return self._backend

    @property
    def credentials(self) -> Any:
        if not self._cached:
            if self._prompt:
                self._credentials = self._prompt()
            else:
                raise ValueError("Cannot prompt for password")

            self._cached = True

        return self._credentials

    def reload(self):
        """Reload the configuration file"""

        with self.file.open("rb") as stream:
            self._contents = tomllib.load(stream)

        self._backend = None
        self._credentials = None
        self._cached = False

    @classmethod
    def new(
        cls,
        path: Path,
        contents: dict[str, Any],
        *,
        prompt: Optional[Callable[[], Optional[str]]] = None,
    ) -> Configuration:
        with (path / CONFIG_FILE).open("wb") as stream:
            tomli_w.dump(contents, stream)

        return cls(path, prompt=prompt)


__all__ = ("Configuration",)
