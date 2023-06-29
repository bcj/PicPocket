"""Utilities for image files"""
import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Optional

from PIL import Image  # type: ignore
from PIL.ExifTags import Base as ExifTag  # type: ignore
from PIL.TiffImagePlugin import IFDRational  # type: ignore

# Eventually, we'll be splitting these up by kind
# these aren't case sensitive
# TODO (1.0): Provide a nice way of checking/updating these in the config
IMAGE_FORMATS = {
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".heic": "image/heic",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".orf": "image/x-olympus-orf",
    ".mp4": "video/mp4",
    ".png": "image/png",
}


PILLOW_FORMATS = {
    extension
    for extension, name in Image.registered_extensions().items()
    if name in Image.OPEN
}


def mime_type(path: Path) -> Optional[str]:
    """Attempt to get a mime type for an image file"""
    mime = IMAGE_FORMATS.get(path.suffix.lower())

    if mime is None:
        try:
            mime = Image.open(path).get_format_mimetype()
        except Exception:
            pass

    return mime


def hash_image(path: Path) -> str:
    """Create a hash representing an image"""
    return sha256(path.read_bytes()).hexdigest()


def image_info(
    path: Path, logger=None
) -> tuple[
    Optional[int],
    Optional[int],
    Optional[datetime],
    Optional[str],
    Optional[str],
    dict[str, Any],
]:
    """Pull image info from a file (if possible)

    This function will not error if image information cannot be fetched.

    .. note::
        This function combines exif and exif ifd

    Args:
        path: The image to pull information from
        logger: Where to log to

    Returns:
        A tuple representing width, height, creation_date, creator,
        description, exif
    """
    width = height = creation_date = creator = description = None
    exif = {}

    image = None
    try:
        if path.suffix in PILLOW_FORMATS:
            image = Image.open(path)
    except Exception:
        if logger:
            logger.exception("Pillow couldn't read image file %s", path)
    else:
        if image:
            width = image.width
            height = image.height

            try:
                exif_data = image._getexif()  # this is also grabbing exif ifd
            except AttributeError:
                pass  # some image types won't have this
            except Exception:
                if logger:
                    logger.exception("Could not read exif data for file %s", path)
            else:
                for tag_number, value in (exif_data or {}).items():
                    tag = None
                    try:
                        tag = ExifTag(tag_number).name

                        match tag:
                            case "Artist":
                                creator = value
                            case "DateTimeOriginal" | "DateTimeDigitized":
                                creation_date = parse_exif_date(value)
                            case "DateTime" if creation_date is None:
                                creation_date = parse_exif_date(value)
                            case "ImageDescription":
                                description = value
                            case "ExifOffset":
                                continue
                            case "ExifVersion" | "FlashPixVersion":
                                value = value.decode()
                            case "LensSpecification":
                                value = [float(val) for val in value]

                        if isinstance(value, bytes):
                            if logger:
                                logger.debug(
                                    "Skipping exif tag with bytes value %s",
                                    tag if tag else f"tag #{tag_number}",
                                )
                            continue
                        elif isinstance(value, IFDRational):
                            value = float(value)

                        try:
                            json.dumps(value)
                        except Exception:
                            if logger:
                                logger.debug(
                                    "Skipping exif tag with unserializable value: %s",
                                    tag if tag else f"tag #{tag_number}",
                                )
                            continue

                        exif[tag] = value
                    except Exception:
                        if logger:
                            logger.debug(
                                "Couldn't parse exif tag %s for file %s",
                                tag if tag else f"tag #{tag_number}",
                                path,
                            )

    return width, height, creation_date, creator, description, exif


def parse_exif_date(date_string: str) -> datetime:
    """Parse a datestring into a timezone-aware date"""
    naive = "%Y:%m:%d %H:%M:%S"

    try:
        return datetime.strptime(date_string, f"{naive}%z")
    except Exception:
        return datetime.strptime(date_string, naive).astimezone(timezone.utc)


__all__ = ("IMAGE_FORMATS", "hash_image", "image_info", "mime_type")
