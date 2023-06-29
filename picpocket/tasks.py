"""Utilities related to PicPocket tasks"""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


class PathPart(ABC):
    """A dynamic directory name"""

    @classmethod
    def name(cls) -> str:
        """the part's name"""

        return cls.__name__.lower()

    @abstractmethod
    def matches(
        self, directory: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        """Check whether a directory name matches a requirement

        args:
            directory: The directory name
            params: parameters created by other path parts. guaranteed
            parameters:

            * last_ran: Optional[datetime]

        Returns:
            A dict of new paramaters if the supplied directory is valid,
            otherwise `None`
        """

    def __str__(self) -> str:
        return f"{'{'}{self.name()}{'}'}"


@dataclass(frozen=True)
class Year(PathPart):
    """A directory name with a year in it.

    .. todo::
        Allow users to pass a format string for parsing out the year

    If used on its own, this component will match if the last-ran date
    is not after this year. If month or month and day are present in the
    passed params, that combined date will be compared against the
    last-ran date.
    """

    def matches(
        self, directory: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        try:
            year = int(directory)
        except ValueError:
            return None

        date = params["last_ran"]

        if date:
            if year < date.year:
                return None
            elif year == date.year:
                month = params.get("month")

                if month:
                    month = int(month)

                    if month < date.month:
                        return None
                    elif month == date.month:
                        day = params.get("day")

                        if day and int(day) < date.day:
                            return None

        return {"year": year}


@dataclass(frozen=True)
class Month(PathPart):
    """A directory name with a month in it.

    .. todo::
        Allow users to pass a format string for parsing out the month

    If year or year and day are present in the passed params, that
    combined date will be compared against the last-ran date. If year is
    not present, this component will provisionally accept the directory
    """

    def matches(
        self, directory: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        try:
            month = int(directory)
        except ValueError:
            return None

        if month < 1 or month > 12:
            return None

        date = params["last_ran"]

        if date:
            year = params.get("year")

            if year:
                year = int(year)

                if (year, month) < (date.year, date.month):
                    return None
                elif (year, month) == (date.year, date.month):
                    day = params.get("day")

                    if day and int(day) < date.day:
                        return None

        return {"month": month}


@dataclass(frozen=True)
class Day(PathPart):
    """A directory name with a day in it.

    .. todo::
        Allow users to pass a format string for parsing out the day

    If year and month are present in the passed params, that combined
    date will be compared against the last-ran date. If either is not
    present, this component will provisionally accept the directory.
    """

    def matches(
        self, directory: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        try:
            day = int(directory)
        except ValueError:
            return None

        if day < 1 or day > 31:
            return None

        date = params["last_ran"]

        if date:
            year = params.get("year")
            month = params.get("month")

            if year and month:
                if (int(year), int(month), day) < (date.year, date.month, date.day):
                    return None

        return {"day": day}


@dataclass(frozen=True)
class Date(PathPart):
    """A directory matching a full date"""

    format: str

    def matches(
        self, directory: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        try:
            date = datetime.strptime(directory, self.format).astimezone()
        except ValueError:
            return None

        last_run = params["last_ran"]

        if last_run and date < last_run:
            return None

        return {"date": date}

    def __str__(self) -> str:
        return f"{{{self.name()}:{self.format}}}"


@dataclass(frozen=True)
class Regex(PathPart):
    """A directory matching a regex

    If named groups exist in the pattern, they will be added to the
    params.
    """

    pattern: str

    def matches(
        self, directory: str, params: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        match = re.search(self.pattern, directory)

        if match:
            return match.groupdict()

        return None

    def __str__(self) -> str:
        return f"{{{self.name()}:{self.pattern}}}"


PATH_PARTS = {
    "year": Year,
    "month": Month,
    "day": Day,
    "date": Date,
    "regex": Regex,
}


def load_path(serialized: str) -> list[str | PathPart]:
    """Desearialize a path that may contain PathParts

    args:
        serialized: A string representation of the path
    """
    parts = []
    for part in serialized.split("/"):
        match = re.search(r"^\{(\w+)(?::(.*?))?}$", part)
        if match:
            function = match.group(1)
            argument = match.group(2)

            if function == "str":
                parts.append(argument)
            elif function in PATH_PARTS:
                if argument:
                    parts.append(PATH_PARTS[function](argument))
                else:
                    parts.append(PATH_PARTS[function]())
            else:
                raise ValueError(f"Unsupported dynamic path: {part}")
        else:
            parts.append(part)

    return parts


def serialize_path(path: list[str | PathPart]) -> str:
    """Serialize a path that may contain PathParts

    args:
        path: The path
    """
    parts = []
    for part in path:
        if isinstance(part, PathPart):
            parts.append(str(part))
        elif "{" in part:
            parts.append(f"{{str:{part}}}")
        else:
            parts.append(part)

    return "/".join(parts)


__all__ = (
    "PathPart",
    "Date",
    "Day",
    "Month",
    "Regex",
    "Year",
    "load_path",
    "serialize_path",
)
