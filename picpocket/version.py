"""
Versioning information for various interfaces within PicPocket.

Version doubles as both the version of the package and the version of
the frontend API and will at least largely be following SemVer.

The plan is to keep the DB and the REST API major versions in line with
the package version.
"""
from typing import NamedTuple, Optional


class Version(NamedTuple):
    major: int
    minor: int
    patch: int
    label: Optional[str] = None

    def as_dict(self) -> dict[str, Optional[str | int]]:
        return {
            "major": self.major,
            "minor": self.minor,
            "patch": self.patch,
            "label": self.label,
        }

    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"

        if self.label:
            version = f"{version}-{self.label}"

        return version


VERSION = Version(0, 1, 0, label="dev")
POSTGRES_VERSION = Version(0, 1, 0, label="dev")
SQLITE_VERSION = Version(0, 1, 0, label="dev")
WEB_VERSION = Version(0, 1, 0, label="dev")

__version__ = str(VERSION)


all = (
    "__version__",
    "POSTGRES_VERSION",
    "SQLITE_VERSION",
    "VERSION",
    "WEB_VERSION",
)
