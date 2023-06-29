"""Types representing tables within PicPocket"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


# would love to freeze this but there doesn't seem to be a good way to
# do that and still accept str paths
@dataclass(unsafe_hash=False)
class Location:
    """A Location stored in PicPocket"""

    id: int
    name: str
    description: Optional[str]
    path: Optional[Path]
    source: bool
    destination: bool
    removable: bool
    mount_point: Optional[Path] = field(compare=False)

    def __init__(
        self,
        id: int,
        name: str,
        description: Optional[str],
        path: Optional[Path],
        source: bool,
        destination: bool,
        removable: bool,
        *,
        mount_point: Optional[Path] = None,
    ):
        self.id = id
        self.name = name
        self.description = description
        self.path = Path(path) if path else None
        self.source = source
        self.destination = destination
        self.removable = removable
        self.mount_point = mount_point

    def serialize(self) -> dict[str, Optional[int | str | bool]]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "path": str(self.path) if self.path else None,
            "source": self.source,
            "destination": self.destination,
            "removable": self.removable,
            "mount_point": str(self.mount_point) if self.mount_point else None,
        }


# would love to freeze this but there doesn't seem to be a good way to
# do that and still accept str hashes
@dataclass(unsafe_hash=False)
class Image:
    """An image stored in PicPocket"""

    id: int
    location: int
    path: Path
    creator: Optional[str]
    title: Optional[str]
    caption: Optional[str]
    alt: Optional[str]
    rating: Optional[int]
    # these are attributes of the file itself and can be changed
    # outside of PicPocket, so we don't compare on them
    hash: Optional[str] = field(compare=False)
    width: Optional[int] = field(compare=False)
    height: Optional[int] = field(compare=False)
    creation_date: Optional[datetime] = field(compare=False)
    last_modified: Optional[datetime] = field(compare=False)
    exif: Optional[dict[str, str]] = field(compare=False)
    # these require extra operations to fetch so they are also optional
    full_path: Optional[Path] = field(compare=False)
    tags: Optional[list[str]] = field(compare=False)

    def __init__(
        self,
        id: int,
        location: int,
        path: str | Path,
        creator: Optional[str] = None,
        title: Optional[str] = None,
        caption: Optional[str] = None,
        alt: Optional[str] = None,
        rating: Optional[int] = None,
        *,
        width: Optional[int] = None,
        height: Optional[int] = None,
        hash: Optional[str] = None,
        creation_date: Optional[int | datetime] = None,
        last_modified: Optional[int | datetime] = None,
        exif: Optional[dict[str, Any]] = None,
        location_path: Optional[Path] = None,
        tags: Optional[list[str]] = None,
    ):
        self.id = id
        self.location = location
        self.path = Path(path)
        self.full_path = location_path / self.path if location_path else None
        self.creator = creator
        self.title = title
        self.caption = caption
        self.alt = alt
        self.rating = rating
        self.hash = hash
        self.width = width
        self.height = height
        self.exif = exif
        self.tags = tags

        if creation_date is not None:
            if isinstance(creation_date, (int, float)):
                creation_date = datetime.fromtimestamp(creation_date).astimezone(
                    timezone.utc
                )

        self.creation_date = creation_date

        if last_modified is not None:
            if isinstance(last_modified, (int, float)):
                last_modified = datetime.fromtimestamp(last_modified).astimezone(
                    timezone.utc
                )

        self.last_modified = last_modified

    def serialize(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "location": self.location,
            "path": str(self.path),
            "full_path": str(self.full_path) if self.full_path else None,
            "creator": self.creator,
            "title": self.title,
            "caption": self.caption,
            "alt": self.alt,
            "rating": self.rating,
            "hash": self.hash,
            "width": self.width,
            "height": self.height,
            "creation_date": (
                self.creation_date.strftime("%Y-%m-%d %H:%M:%S")
                if self.creation_date
                else None
            ),
            "last_modified": (
                self.last_modified.strftime("%Y-%m-%d %H:%M:%S")
                if self.last_modified
                else None
            ),
            "exif": self.exif,
            "tags": self.tags,
        }


@dataclass
class Tag:
    """A descriptive tag"""

    name: str
    description: Optional[str]
    children: frozenset[str] = field(compare=False)

    def __init__(
        self,
        name: str,
        description: Optional[str] = None,
        children: Optional[Iterable[str]] = None,
    ):
        self.name = name
        self.description = description

        if children:
            self.children = frozenset(children)
        else:
            self.children = frozenset()

    def serialize(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "children": sorted(self.children),
        }


@dataclass(frozen=True)
class Task:
    """An image stored in PicPocket"""

    name: str
    source: int
    destination: int
    configuration: dict[str, Any]
    description: Optional[str] = None
    last_ran: Optional[datetime] = field(compare=False, default=None)

    def serialize(self) -> dict[str, Any]:
        if self.last_ran:
            last_ran = self.last_ran.strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_ran = None

        return {
            "name": self.name,
            "source": self.source,
            "destination": self.destination,
            "configuration": self.configuration,
            "description": self.description,
            "last_ran": last_ran,
        }


__all__ = ("Image", "Location", "Tag", "Task")
