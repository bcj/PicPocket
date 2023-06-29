from __future__ import annotations

"""Utilities for filtering columns"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Generator, Iterable, Optional


class Types(Enum):
    """Types of PicPocket property"""

    BOOLEAN = "boolean"
    DATETIME = "datetime"
    ID = "id"
    JSON = "json"
    NUMBER = "number"
    TEXT = "text"


class Comparator(Enum):
    """Comparisons that may be made on PicPocket properties"""

    EQUALS = "="
    STARTS_WITH = "=%"
    ENDS_WITH = "%="
    CONTAINS = "%=%"
    GREATER = ">"
    GREATER_EQUALS = ">="
    LESS = "<"
    LESS_EQUALS = "<="


TEXT_COMPARATORS = {
    Comparator.EQUALS,
    Comparator.STARTS_WITH,
    Comparator.ENDS_WITH,
    Comparator.CONTAINS,
}

NUMERIC_COMPARATORS = {
    Comparator.EQUALS,
    Comparator.GREATER,
    Comparator.GREATER_EQUALS,
    Comparator.LESS,
    Comparator.LESS_EQUALS,
}


# TODO (1.0):
# It feels kind of weird that this lives here.
# There's a 3-way dependency between Comparison, SQL, and Types so
# separating them seems hard but Comparison is exposed to users and SQL
# is an implementation detail.
# The only real way of fixing the dependency issue is to move prepare
# from Comparison objects (making them structs essentially) to a method
# on SQL, move SQL, and have it import from here.
# The real goal here is to make it so that someone could implement their
# own backend and have code work without trying to get changes back into
# base.
# Having prepare on the Comparisons means that someone could create a
# new one or subclass one and have that logic work with the built-in
# databases too.
# Someone implementing a non-SQL DB can't really use prepare anyway,
# so Comparisons already are just structs for them. Maybe just leave
# things?
class SQL(ABC):
    """A class for configuring how to manage SQL for a given database.

    This includes some checks for what features the database supports as
    well as methods for crafting safe query strings the database will
    accept. The latter are modelled on psycopg's
    `sql <https://www.psycopg.org/psycopg3/docs/api/sql.html>` module
    with the default implementations providing the support SQLite would
    require.
    """

    @property
    @abstractmethod
    def types(self) -> set[Types]:
        """The supported data types"""

    @property
    def arrays(self) -> bool:
        """Whether the database supports arrays"""
        return False

    @property
    @abstractmethod
    def param(self) -> str:
        """The symbol the database uses for positional paramaters.

        We can't just use 'paramstyle' because APIs are inconsistent
        on whether they use that to refer to their positional or named
        param style.

        .. warning::
            This method should not be used in conjunction with any of
            the below formatting methods!

        Returns:
            a symbol to use when generating SQL that uses positional
            placeholders.
        """

    def format(self, statement: str, *parts):
        """add sections (e.g., identifiers, placeholders) to a statement

        The base statement should be using {} for positional formatting
        and each part being formatted in should represent
        already-formatted sql (using either format or any of the other
        sql methods).

        Args:
            statment: The statement to format
            parts: the sections to add to the statement

        Returns:
            The formatted statement.
        """
        return statement.format(*parts)

    def join(self, joiner: str, parts: Iterable):
        """join together several sections of a statement

        Parts should already be formatted by another sql format method
        before being passed in to join.

        Args:
            joiner: The string to use to join the sections
            parts: The sections to join together

        Returns:
            The formatted section
        """
        return joiner.join(parts)

    def identifier(self, identifier: str):
        """Format an identifier (i.e., table, column names)

        .. Warning::
            The default implementation is written with the assumption
            that identifiers will only be passed in from a reliable
            source (i.e., PicPocket's own API) and not from user
            input. This method is not thorough enough to be trusted
            with user-supplied identifiers.

        Args:
            identifier: the table/column name

        Returns:
            A formatted version of the identifier
        """
        if not re.search(r"^(?:\w+(?:\.\w+)*)$", identifier):
            raise ValueError(f"Refusing use identifier: {identifier}")

        return f'"{identifier}"'

    def literal(self, literal: Any):
        """Format a literal (e.g., a number or string)

        Args:
            literal: the literal to format

        Returns:
            A formatted version of that literal
        """
        if literal is None:
            return "NULL"
        elif isinstance(literal, bool):
            return str(literal).upper()
        elif isinstance(literal, (int, float)):
            return str(literal)

        return "'{}'".format(str(literal).replace("'", "''"))

    @abstractmethod
    def placeholder(self, placeholder: str):
        """Format a named placeholder

        Args:
            placeholder: the placeholder to format

        Returns:
            A formatted version of that placeholder
        """

    @property
    def escape(self) -> Optional[str]:
        """The symbol used to escape search terms for LIKE queries"""
        # picked fairly arbitrarily on the basis that it's somewhat
        # unlikely to show up in tags so we probably will need to do
        # less unnecessary escaping
        return "#"


class Comparison(ABC):
    """A logical comparison being made on a column"""

    def _next_free_name(
        self, name: str, values: dict[str, Any]
    ) -> Generator[str, None, None]:
        if name not in values:
            yield name

        index = 1
        while True:
            while (key := f"{name}{index}") in values:
                index += 1

            yield key

    @abstractmethod
    def validate(self, columns: dict[str, Types]):
        """Ensure that comparison matches table constraints

        Args:
            columns: The dict representing a table
        """

    @abstractmethod
    def prepare(
        self,
        sql: SQL,
        values: dict[str, Any],
        *,
        table: Optional[str] = None,
    ):
        """Compose SQL representing the comparison

        Args:
            sql: The SQL object to compose against
            values: A dict of values being passed in as placeholders
                for the statement this comparison will be included in.
                prepare will add any placeholders it requires (without
                clobbering any existing placeholders)
            table: The name of the table this query is being performed
                on.

        Returns:
            The comparison, as formatted by the sql object
        """


class Combination(Comparison):
    """An operation that joins together comparisons"""

    @property
    @abstractmethod
    def comparisons(self) -> tuple[Comparison, ...]:
        """The comparisons the Comination combines together"""

    @property
    @abstractmethod
    def invert(self) -> bool:
        """Whether to invert the expression"""

    @property
    @abstractmethod
    def joiner(self) -> str:
        """The symbol used to represent the comparison"""

    def validate(self, columns: dict[str, Types]):
        for comparison in self.comparisons:
            comparison.validate(columns)

    def prepare(
        self,
        sql: SQL,
        values: dict[str, Any],
        *,
        table: Optional[str] = None,
    ):
        parts = []
        for comparison in self.comparisons:
            text = comparison.prepare(sql, values, table=table)

            if isinstance(comparison, Combination):
                text = sql.format("({})", text)

            parts.append(text)

        combination = sql.join(f" {self.joiner} ", parts)

        if self.invert:
            combination = sql.format("NOT ({})", combination)

        return combination

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Combination):
            return NotImplemented

        return (
            self.joiner == other.joiner
            and self.comparisons == other.comparisons
            and self.invert == other.invert
        )

    def __repr__(self) -> str:
        if self.invert:
            return (
                f"{type(self).__name__}("
                f"*({', '.join(map(repr, self.comparisons))}), "
                "invert=True"
                ")"
            )
        else:
            return f"{type(self).__name__}(*({', '.join(map(repr, self.comparisons))}))"


@dataclass
class Boolean(Comparison):
    """A comparison against a boolean property

    column: The property being compared
    value: The expected value of the property
    invert: Whether to invert the comparison
    """

    column: str
    value: Optional[bool] = None
    invert: bool = False

    def validate(self, columns: dict[str, Types]):
        if self.column not in columns:
            raise ValueError(f"Unknown column: {self.column}")

        column_type = columns[self.column]
        if column_type != Types.BOOLEAN:
            raise TypeError(
                f"{self.column} is expected to be boolean not {column_type.value}"
            )

    def prepare(
        self,
        sql: SQL,
        values: dict[str, Any],
        *,
        table: Optional[str] = None,
    ):
        if table is None:
            column = self.column
        else:
            column = f"{table}.{self.column}"

        if self.value is None:
            if self.invert:
                return sql.format("{} IS NOT NULL", sql.identifier(column))
            else:
                return sql.format("{} IS NULL", sql.identifier(column))

        placeholder = next(self._next_free_name(self.column, values))

        values[placeholder] = self.value

        return sql.format(
            "{} {} {}",
            sql.identifier(column),
            sql.format("!=" if self.invert else "="),
            sql.placeholder(placeholder),
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Boolean):
            return NotImplemented

        return (
            self.column == other.column
            and self.value == other.value
            and self.invert == other.invert
        )

    def __repr__(self) -> str:
        if self.invert:
            return f"Boolean({self.column!r}, {self.value!r}, invert=True)"
        else:
            return f"Boolean({self.column!r}, {self.value!r})"


@dataclass
class Text(Comparison):
    """A comparison against a text property

    column: The property being compared
    comparison: The comparison being made to the provided value
    value: The expected value of the property
    invert: Whether to invert the comparison
    """

    column: str
    comparison: Comparator
    value: Optional[str | list[str]] = None
    invert: bool = False

    def validate(self, columns: dict[str, Types]):
        if self.column not in columns:
            raise ValueError(f"Unknown column: {self.column}")

        column_type = columns[self.column]
        if column_type != Types.TEXT:
            raise TypeError(
                f"{self.column} is expected to be text not {column_type.value}"
            )

    def prepare(
        self,
        sql: SQL,
        values: dict[str, Any],
        *,
        table: Optional[str] = None,
    ):
        if table is None:
            column = self.column
        else:
            column = f"{table}.{self.column}"

        value: str | list[str]
        use_any = False

        iterator = self._next_free_name(self.column, values)

        suffix = sql.format("")

        match self.comparison:
            case Comparator.EQUALS:
                if self.value is None:
                    if self.invert:
                        return sql.format("{} IS NOT NULL", sql.identifier(column))
                    else:
                        return sql.format("{} IS NULL", sql.identifier(column))
                elif isinstance(self.value, list):
                    # TODO: does postgres have a proper way of handling != ANY?
                    # Any + invert produced unexpected results
                    if not sql.arrays or self.invert:
                        comparator = sql.format("NOT IN" if self.invert else "IN")
                        placeholders = []
                        for value in self.value:
                            placeholder = next(iterator)
                            values[placeholder] = value
                            placeholders.append(sql.placeholder(placeholder))

                        return sql.format(
                            "{} {} ({})",
                            sql.identifier(column),
                            comparator,
                            sql.join(", ", placeholders),
                        )

                    use_any = True
                value = self.value
                comparator = sql.format("!=" if self.invert else "=")
            case Comparator.STARTS_WITH:
                if not isinstance(self.value, str):
                    raise TypeError("cannot start with value {self.value!r}")

                symbol = sql.escape
                value = f"{escape(self.value, symbol)}%"

                comparator = sql.format("NOT LIKE" if self.invert else "LIKE")
                if symbol:
                    suffix = sql.format(" ESCAPE {}", sql.literal(symbol))
            case Comparator.ENDS_WITH:
                if not isinstance(self.value, str):
                    raise TypeError("cannot end with value {self.value!r}")

                symbol = sql.escape
                value = f"%{escape(self.value, symbol)}"

                comparator = sql.format("NOT LIKE" if self.invert else "LIKE")
                if symbol:
                    suffix = sql.format(" ESCAPE {}", sql.literal(symbol))
            case Comparator.CONTAINS:
                if not isinstance(self.value, str):
                    raise TypeError("cannot contain value {self.value!r}")

                symbol = sql.escape
                value = f"%{escape(self.value, symbol)}%"

                comparator = sql.format("NOT LIKE" if self.invert else "LIKE")
                if symbol:
                    suffix = sql.format(" ESCAPE {}", sql.literal(symbol))
            case _:
                raise TypeError(f"Unknown comparison: {self.comparison}")

        key = next(iterator)

        values[key] = value

        placeholder = sql.placeholder(key)
        if use_any:
            placeholder = sql.format("ANY({})", placeholder)

        return sql.format(
            "{} {} {}{}",
            sql.identifier(column),
            comparator,
            placeholder,
            suffix,
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Text):
            return NotImplemented

        return (
            self.column == other.column
            and self.comparison == other.comparison
            and self.value == other.value
            and self.invert == other.invert
        )

    def __repr__(self) -> str:
        if self.invert:
            return (
                f"Text("
                f"{self.column!r}, "
                f"{self.comparison}, "
                f"{self.value!r}, "
                f"invert=True"
                ")"
            )
        else:
            return f"Text({self.column!r}, {self.comparison}, {self.value!r})"


class Numeric(Comparison):
    """An abstract class for broadly numeric types"""

    @abstractmethod
    def __init__(
        self,
        column: str,
        comparison: Comparator,
        value: Optional[Any | list[Any]] = None,
        invert: bool = False,
    ):
        """Initialize a numeric type"""

    @property
    @abstractmethod
    def column(self) -> str:
        """The column being checked"""

    @property
    @abstractmethod
    def comparison(self) -> Comparator:
        """The comparison being made"""

    @property
    @abstractmethod
    def value(self) -> Optional[Any | list[Any]]:
        """The value being compared against"""

    @property
    @abstractmethod
    def invert(self) -> bool:
        """Whether to invert the comparison"""

    def process_value(self, sql: SQL, value):
        """Any formatting required to add a value to values"""
        return self.value

    def prepare(
        self,
        sql: SQL,
        values: dict[str, Any],
        *,
        table: Optional[str] = None,
    ):
        if table is None:
            column = self.column
        else:
            column = f"{table}.{self.column}"

        if self.value is None:
            if self.comparison == Comparator.EQUALS:
                if self.invert:
                    return sql.format("{} IS NOT NULL", sql.identifier(column))
                else:
                    return sql.format("{} IS NULL", sql.identifier(column))
            else:
                raise ValueError("cannot compare to NULL")
        elif isinstance(self.value, list):
            if not sql.arrays:
                match len(self.value):
                    case 0:
                        return sql.format("1 = 2")
                    case 1:
                        value = self.value[0]
                    case _:
                        comparison = Or(
                            *(
                                self.__class__(
                                    self.column, self.comparison, value, self.invert
                                )
                                for value in self.value
                            )
                        ).prepare(sql, values, table=table)

                        if not str(comparison).startswith("("):
                            comparison = sql.format("({})", comparison)

                        return comparison
            else:
                value = self.process_value(sql, self.value)

        else:
            value = self.process_value(sql, self.value)

        comparator = self.comparison.value

        if self.invert:
            match self.comparison:
                case Comparator.EQUALS:
                    comparator = "!="
                case Comparator.GREATER:
                    comparator = Comparator.LESS_EQUALS.value
                case Comparator.GREATER_EQUALS:
                    comparator = Comparator.LESS.value
                case Comparator.LESS:
                    comparator = Comparator.GREATER_EQUALS.value
                case Comparator.LESS_EQUALS:
                    comparator = Comparator.GREATER.value
                case _:
                    raise ValueError(f"Unknown comparison: {self.comparison}")
        elif self.comparison not in NUMERIC_COMPARATORS:
            raise ValueError(f"Unknown comparison: {self.comparison}")

        if self.column in values:
            index = 1
            while (key := f"{self.column}{index}") in values:
                index += 1
        else:
            key = self.column

        values[key] = value

        placeholder = sql.placeholder(key)
        if isinstance(value, list):
            placeholder = sql.format("ANY({})", placeholder)

        return sql.format(
            "{} {} {}", sql.identifier(column), sql.format(comparator), placeholder
        )

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Numeric):
            return NotImplemented

        return (
            self.column == other.column
            and self.comparison == other.comparison
            and self.value == other.value
            and self.invert == other.invert
        )

    def __repr__(self) -> str:
        type_name = type(self).__name__
        if self.invert:
            return (
                f"{type_name}("
                f"{self.column!r}, "
                f"{self.comparison}, "
                f"{self.value!r}, "
                f"invert=True"
                ")"
            )
        else:
            return f"{type_name}({self.column!r}, {self.comparison}, {self.value!r})"


class Number(Numeric):
    """A comparison against an integer/real property

    column: The property being compared
    comparison: The comparison being made to the provided value
    value: The expected value of the property
    invert: Whether to invert the comparison
    """

    def __init__(
        self,
        column: str,
        comparison: Comparator,
        value: Optional[int | list[int]] = None,
        invert: bool = False,
    ):
        self._column = column
        self._comparison = comparison
        self._value = value
        self._invert = invert

    @property
    def column(self) -> str:
        return self._column

    @property
    def comparison(self) -> Comparator:
        return self._comparison

    @property
    def value(self) -> Optional[int | list[int]]:
        return self._value

    @property
    def invert(self) -> bool:
        return self._invert

    def validate(self, columns: dict[str, Types]):
        if self.column not in columns:
            raise ValueError(f"Unknown column: {self.column}")

        column_type = columns[self.column]
        if column_type != Types.NUMBER:
            if column_type == Types.ID:
                if self.comparison != Comparator.EQUALS:
                    raise TypeError(
                        f"{self.column} is an identifier. "
                        f"Only equality comparisons allowed, found {self.comparison}"
                    )
            else:
                raise TypeError(
                    f"{self.column} is expected to be number not {column_type.value}"
                )


class DateTime(Numeric):
    """A comparison against a date property

    column: The property being compared
    comparison: The comparison being made to the provided value
    value: The expected value of the property
    invert: Whether to invert the comparison
    """

    def __init__(
        self,
        column: str,
        comparison: Comparator,
        value: Optional[datetime | list[datetime]] = None,
        invert: bool = False,
    ):
        self._column = column
        self._comparison = comparison
        self._value = value
        self._invert = invert

    @property
    def column(self) -> str:
        return self._column

    @property
    def comparison(self) -> Comparator:
        return self._comparison

    @property
    def value(self) -> Optional[datetime | list[datetime]]:
        return self._value

    @property
    def invert(self) -> bool:
        return self._invert

    def validate(self, columns: dict[str, Types]):
        if self.column not in columns:
            raise ValueError(f"Unknown column: {self.column}")

        column_type = columns[self.column]
        if column_type not in (Types.DATETIME, Types.NUMBER):
            raise TypeError(
                f"{self.column} is expected to be date not {column_type.value}"
            )

    def process_value(self, sql: SQL, value):
        if Types.DATETIME not in sql.types:
            if isinstance(value, list):
                return [int(item.timestamp()) for item in value]

            return int(value.timestamp())

        return value


class And(Combination):
    """Require two or more comparisons to evaluate as True"""

    def __init__(
        self,
        comparison1: Comparison,
        comparison2: Comparison,
        /,
        *comparisons: Comparison,
        invert: bool = False,
    ):
        self._comparisons = (comparison1, comparison2, *comparisons)
        self._invert = invert

    @property
    def comparisons(self) -> tuple[Comparison, ...]:
        return self._comparisons

    @property
    def invert(self) -> bool:
        return self._invert

    @property
    def joiner(self) -> str:
        return "AND"


class Or(Combination):
    """Require at least one of two or more comparisons to evaluate as True"""

    def __init__(
        self,
        comparison1: Comparison,
        comparison2: Comparison,
        /,
        *comparisons: Comparison,
        invert: bool = False,
    ):
        self._comparisons = (comparison1, comparison2, *comparisons)
        self._invert = invert

    @property
    def comparisons(self) -> tuple[Comparison, ...]:
        return self._comparisons

    @property
    def invert(self) -> bool:
        return self._invert

    @property
    def joiner(self) -> str:
        return "OR"


def escape(text: str, symbol: Optional[str]) -> str:
    """Escape a value being used in a LIKE comparison

    Args:
        text: The text to escape
        symbol: The escape symbol

    Returns:
        The escaped text
    """
    if not symbol:
        return text

    return (
        text.replace(symbol, symbol * 2)
        .replace("%", f"{symbol}%")
        .replace("_", f"{symbol}_")
    )


__all__ = (
    "And",
    "Boolean",
    "Comparator",
    "Comparison",
    "DateTime",
    "Number",
    "Or",
    "Text",
    "Types",
)
