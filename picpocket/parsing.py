"""parsing functions for use with the cli and web api"""
from pathlib import Path


def full_path(raw: str) -> Path:
    """Convert a path string into a path"""
    return Path(raw).expanduser().absolute()


def int_or_str(raw: str) -> int | str:
    """Convert an id to a number as necessary"""
    try:
        return int(raw)
    except ValueError:
        return raw
