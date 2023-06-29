import os
from datetime import datetime

import pytest


def test_boolean():
    from picpocket.database.logic import Boolean, Comparator, Number, Types

    boolean = Boolean("boolean", True)

    # validation

    # unknown column
    with pytest.raises(ValueError):
        boolean.validate({"other": Types.TEXT})

    # wrong type
    with pytest.raises(TypeError):
        boolean.validate({"boolean": Types.NUMBER})

    # correct type
    columns = {
        "text": Types.TEXT,
        "number": Types.NUMBER,
        "id": Types.ID,
        "boolean": Types.BOOLEAN,
    }
    boolean.validate(columns)

    assert Boolean("col", True) == Boolean("col", True)
    assert Boolean("column", True) != Boolean("col", True)
    assert Boolean("col", True) != Boolean("col", None)
    assert Boolean("col", True) != Boolean("col", True, invert=True)
    assert Boolean("col", None) != Number("col", Comparator.EQUALS, None)

    assert str(Boolean("column", False)) == "Boolean('column', False)"
    assert str(Boolean("col", None, invert=True)) == "Boolean('col', None, invert=True)"


def test_datetime():
    from picpocket.database.logic import Comparator, DateTime, Number, Types

    timestamp = 1234567
    dt = datetime.fromtimestamp(timestamp)
    date = DateTime("date", Comparator.GREATER, dt)

    # validation

    # unknown column
    with pytest.raises(ValueError):
        date.validate({"other": Types.TEXT})

    # wrong type
    with pytest.raises(TypeError):
        date.validate({"date": Types.TEXT})

    # correct type
    date.validate({"date": Types.DATETIME})
    date.validate({"date": Types.NUMBER})

    assert DateTime("col", Comparator.EQUALS, datetime(2021, 1, 2)) == DateTime(
        "col", Comparator.EQUALS, datetime(2021, 1, 2)
    )
    assert DateTime("col", Comparator.EQUALS, datetime(2021, 1, 2)) != DateTime(
        "column", Comparator.EQUALS, datetime(2021, 1, 2)
    )
    assert DateTime("col", Comparator.EQUALS, datetime(2021, 1, 2)) != DateTime(
        "col", Comparator.GREATER_EQUALS, datetime(2021, 1, 2)
    )
    assert DateTime("col", Comparator.EQUALS, datetime(1970, 1, 1)) != Number(
        "col", Comparator.EQUALS, 0
    )

    assert str(DateTime("col", Comparator.LESS, datetime(2021, 1, 2))) == (
        f"DateTime('col', Comparator.LESS, {datetime(2021, 1, 2)!r})"
    )
    assert str(DateTime("column", Comparator.EQUALS, None, invert=True)) == (
        "DateTime('column', Comparator.EQUALS, None, invert=True)"
    )


def test_number():
    from picpocket.database.logic import Comparator, Number, Types

    number = Number("number", Comparator.GREATER, 5)
    id = Number("id", Comparator.EQUALS, 2)

    # validation

    # unknown column
    with pytest.raises(ValueError):
        number.validate({"other": Types.TEXT})

    # wrong type
    with pytest.raises(TypeError):
        number.validate({"number": Types.TEXT})

    # correct type
    columns = {
        "text": Types.TEXT,
        "number": Types.NUMBER,
        "id": Types.ID,
        "boolean": Types.BOOLEAN,
    }
    number.validate(columns)
    id.validate(columns)

    # invalid comparators for ids
    for comparator in (
        Comparator.GREATER,
        Comparator.GREATER_EQUALS,
        Comparator.LESS,
        Comparator.LESS_EQUALS,
    ):
        with pytest.raises(TypeError):
            Number("id", comparator, 1).validate({"id": Types.ID})

    assert str(Number("id", Comparator.LESS, 5)) == "Number('id', Comparator.LESS, 5)"
    assert str(Number("column", Comparator.EQUALS, None, invert=True)) == (
        "Number('column', Comparator.EQUALS, None, invert=True)"
    )


def test_text():
    from picpocket.database.logic import Comparator, Number, Text, Types

    text = Text("text", Comparator.EQUALS, "value")

    # validation

    # unknown column
    with pytest.raises(ValueError):
        text.validate({"other": Types.TEXT})

    # wrong type
    with pytest.raises(TypeError):
        text.validate({"text": Types.ID})

    # correct type
    columns = {
        "text": Types.TEXT,
        "number": Types.NUMBER,
        "id": Types.ID,
        "boolean": Types.BOOLEAN,
    }
    text.validate(columns)

    assert Text("col", Comparator.EQUALS, "x") == Text("col", Comparator.EQUALS, "x")
    assert Text("col", Comparator.EQUALS) == Text("col", Comparator.EQUALS)
    assert Text("col", Comparator.EQUALS) != Number("col", Comparator.EQUALS)

    assert str(Text("col", Comparator.EQUALS, "val")) == (
        "Text('col', Comparator.EQUALS, 'val')"
    )
    assert str(Text("column", Comparator.EQUALS, None, invert=True)) == (
        "Text('column', Comparator.EQUALS, None, invert=True)"
    )


def test_combinations():
    from picpocket.database.logic import (
        And,
        Boolean,
        Comparator,
        Number,
        Or,
        Text,
        Types,
    )

    # require 2+ things to compar
    with pytest.raises(TypeError):
        And()

    with pytest.raises(TypeError):
        And(Text("text", Comparator.EQUALS, "value"))

    with pytest.raises(TypeError):
        Or()

    with pytest.raises(TypeError):
        Or(Text("text", Comparator.EQUALS, "value"))

    # validation

    # combinations should pass through
    with pytest.raises(TypeError):
        And(
            Or(
                Text("a", Comparator.EQUALS, "value"),
                Text("b", Comparator.EQUALS, "value"),
            ),
            And(
                Text("c", Comparator.EQUALS, "value"),
                Text("d", Comparator.EQUALS, "value"),
            ),
        ).validate(
            {
                "a": Types.TEXT,
                "b": Types.TEXT,
                "c": Types.TEXT,
                "d": Types.ID,
            }
        )

    with pytest.raises(TypeError):
        Or(
            Or(
                Text("a", Comparator.EQUALS, "value"),
                Text("b", Comparator.EQUALS, "value"),
            ),
            And(
                Text("c", Comparator.EQUALS, "value"),
                Text("d", Comparator.EQUALS, "value"),
            ),
        ).validate(
            {
                "a": Types.TEXT,
                "b": Types.TEXT,
                "c": Types.TEXT,
                "d": Types.ID,
            }
        )

    And(
        Or(
            Text("a", Comparator.EQUALS, "value"),
            Text("b", Comparator.EQUALS, "value"),
        ),
        And(
            Text("c", Comparator.EQUALS, "value"),
            Number("d", Comparator.EQUALS, "value"),
        ),
    ).validate(
        {
            "a": Types.TEXT,
            "b": Types.TEXT,
            "c": Types.TEXT,
            "d": Types.ID,
        }
    )

    Or(
        Or(
            Text("a", Comparator.EQUALS, "value"),
            Text("b", Comparator.EQUALS, "value"),
        ),
        And(
            Text("c", Comparator.EQUALS, "value"),
            Number("d", Comparator.EQUALS, "value"),
        ),
    ).validate(
        {
            "a": Types.TEXT,
            "b": Types.TEXT,
            "c": Types.TEXT,
            "d": Types.ID,
        }
    )

    assert And(Boolean("col", True), Boolean("col", False)) == And(
        Boolean("col", True), Boolean("col", False)
    )
    assert And(Boolean("col", True), Boolean("col", False)) != Or(
        Boolean("col", True), Boolean("col", False)
    )
    assert And(Boolean("col", True), Boolean("col", False)) != Boolean("col", True)

    assert str(
        And(
            Text("column", Comparator.EQUALS, "value"),
            Or(Boolean("col1", True), Boolean("col2", False)),
            invert=True,
        )
    ) == (
        "And("
        "*("
        "Text('column', Comparator.EQUALS, 'value'), "
        "Or(*(Boolean('col1', True), Boolean('col2', False)))"
        "), "
        "invert=True"
        ")"
    )


@pytest.mark.asyncio
async def test_postgres(load_api):
    if os.environ["PICPOCKET_BACKEND"] != "postgres":
        pytest.skip("skipping postgres tests")

    from picpocket.database.logic import (
        And,
        Boolean,
        Comparator,
        DateTime,
        Number,
        Or,
        Text,
    )
    from picpocket.database.postgres import PostgreSQL

    sql = PostgreSQL()

    # as_string requires a connection
    async with load_api() as api, await api.connect() as connection:
        text = Text("column", Comparator.EQUALS, "value")

        values = {"column2": 2}
        assert (
            text.prepare(sql, values).as_string(connection) == '"column" = %(column)s'
        )
        assert values == {"column": "value", "column2": 2}

        # names shouldn't be clobbered
        values["column"] = "don't overwrite me"
        assert (
            text.prepare(sql, values, table="my_table").as_string(connection)
            == '"my_table.column" = %(column1)s'
        )
        assert values == {
            "column": "don't overwrite me",
            "column1": "value",
            "column2": 2,
        }

        assert (
            text.prepare(sql, values).as_string(connection) == '"column" = %(column3)s'
        )
        assert values == {
            "column": "don't overwrite me",
            "column1": "value",
            "column2": 2,
            "column3": "value",
        }

        # invert
        values = {}
        text = Text("col", Comparator.EQUALS, "val", invert=True)
        assert text.prepare(sql, values).as_string(connection) == '"col" != %(col)s'
        assert values == {"col": "val"}

        # null
        text = Text("col", Comparator.EQUALS, None)
        assert text.prepare(sql, values).as_string(connection) == '"col" IS NULL'
        assert values == {"col": "val"}
        text = Text("col", Comparator.EQUALS, None, invert=True)
        assert (
            text.prepare(sql, values, table="table").as_string(connection)
            == '"table.col" IS NOT NULL'
        )
        assert values == {"col": "val"}

        # any
        values = {}
        text = Text("col", Comparator.EQUALS, ["val", "val2"])
        assert text.prepare(sql, values).as_string(connection) == '"col" = ANY(%(col)s)'
        assert values == {"col": ["val", "val2"]}
        text = Text("col", Comparator.EQUALS, ["val2", "val1"], invert=True)
        assert (
            text.prepare(sql, values).as_string(connection)
            == '"col" NOT IN (%(col1)s, %(col2)s)'
        )
        assert values == {"col": ["val", "val2"], "col1": "val2", "col2": "val1"}

        # startswith
        values = {}
        text = Text("col", Comparator.STARTS_WITH, "val")
        assert (
            text.prepare(sql, values).as_string(connection)
            == "\"col\" LIKE %(col)s ESCAPE '#'"
        )
        assert values == {"col": "val%"}
        text = Text("col", Comparator.STARTS_WITH, "val%")
        assert (
            text.prepare(sql, values).as_string(connection)
            == "\"col\" LIKE %(col1)s ESCAPE '#'"
        )
        assert values == {"col": "val%", "col1": "val#%%"}
        text = Text("col", Comparator.STARTS_WITH, "%val", invert=True)
        assert (
            text.prepare(sql, values).as_string(connection)
            == "\"col\" NOT LIKE %(col2)s ESCAPE '#'"
        )
        assert values == {"col": "val%", "col1": "val#%%", "col2": "#%val%"}
        for value in (None, ["val", "val2"]):
            with pytest.raises(TypeError):
                Text("col", Comparator.STARTS_WITH, value).prepare(sql, values)
        assert values == {"col": "val%", "col1": "val#%%", "col2": "#%val%"}

        # endswith
        values = {}
        text = Text("col", Comparator.ENDS_WITH, "val")
        assert (
            text.prepare(sql, values).as_string(connection)
            == "\"col\" LIKE %(col)s ESCAPE '#'"
        )
        assert values == {"col": "%val"}
        text = Text("col", Comparator.ENDS_WITH, "val%")
        assert (
            text.prepare(sql, values).as_string(connection)
            == "\"col\" LIKE %(col1)s ESCAPE '#'"
        )
        assert values == {"col": "%val", "col1": "%val#%"}
        text = Text("col", Comparator.ENDS_WITH, "%val#", invert=True)
        assert (
            text.prepare(sql, values).as_string(connection)
            == "\"col\" NOT LIKE %(col2)s ESCAPE '#'"
        )
        assert values == {"col": "%val", "col1": "%val#%", "col2": "%#%val##"}
        for value in (None, ["val", "val2"]):
            with pytest.raises(TypeError):
                Text("col", Comparator.ENDS_WITH, value).prepare(sql, values)
        assert values == {"col": "%val", "col1": "%val#%", "col2": "%#%val##"}

        # contains
        values = {}
        text = Text("col", Comparator.CONTAINS, "val")
        assert (
            text.prepare(sql, values).as_string(connection)
            == "\"col\" LIKE %(col)s ESCAPE '#'"
        )
        assert values == {"col": "%val%"}
        text = Text("col", Comparator.CONTAINS, "val%")
        assert (
            text.prepare(sql, values).as_string(connection)
            == "\"col\" LIKE %(col1)s ESCAPE '#'"
        )
        assert values == {"col": "%val%", "col1": "%val#%%"}
        text = Text("col", Comparator.CONTAINS, "%val", invert=True)
        assert (
            text.prepare(sql, values).as_string(connection)
            == "\"col\" NOT LIKE %(col2)s ESCAPE '#'"
        )
        assert values == {"col": "%val%", "col1": "%val#%%", "col2": "%#%val%"}
        for value in (None, ["val", "val2"]):
            with pytest.raises(TypeError):
                Text("col", Comparator.CONTAINS, value).prepare(sql, values)
        assert values == {"col": "%val%", "col1": "%val#%%", "col2": "%#%val%"}

        # invalid comparator
        with pytest.raises(TypeError):
            Text("col", Comparator.GREATER, "val").prepare(sql, values)

        # numbers
        number = Number("number", Comparator.GREATER, 5)
        id = Number("id", Comparator.EQUALS, 2)

        values = {"number2": 2}
        assert (
            number.prepare(sql, values).as_string(connection) == '"number" > %(number)s'
        )
        assert (
            id.prepare(sql, values, table="t").as_string(connection)
            == '"t.id" = %(id)s'
        )
        assert values == {
            "id": 2,
            "number": 5,
            "number2": 2,
        }

        # names shouldn't be clobbered
        assert (
            number.prepare(sql, values).as_string(connection)
            == '"number" > %(number1)s'
        )
        assert (
            number.prepare(sql, values).as_string(connection)
            == '"number" > %(number3)s'
        )
        assert id.prepare(sql, values).as_string(connection) == '"id" = %(id1)s'
        assert values == {
            "id": 2,
            "id1": 2,
            "number": 5,
            "number1": 5,
            "number2": 2,
            "number3": 5,
        }

        # symbol & invert
        assert (
            Number("num", Comparator.EQUALS, 5)
            .prepare(sql, {}, table="table")
            .as_string(connection)
            == '"table.num" = %(num)s'
        )
        assert (
            Number("num", Comparator.EQUALS, 5, invert=True)
            .prepare(sql, {})
            .as_string(connection)
            == '"num" != %(num)s'
        )
        assert (
            Number("num", Comparator.EQUALS, [5, 6])
            .prepare(sql, {})
            .as_string(connection)
            == '"num" = ANY(%(num)s)'
        )
        assert (
            Number("num", Comparator.GREATER, 5).prepare(sql, {}).as_string(connection)
            == '"num" > %(num)s'
        )
        assert (
            Number("num", Comparator.GREATER, [5, 6], invert=True)
            .prepare(sql, {})
            .as_string(connection)
            == '"num" <= ANY(%(num)s)'
        )
        assert (
            Number("num", Comparator.GREATER_EQUALS, 5)
            .prepare(sql, {})
            .as_string(connection)
            == '"num" >= %(num)s'
        )
        assert (
            Number("num", Comparator.GREATER_EQUALS, 5, invert=True)
            .prepare(sql, {})
            .as_string(connection)
            == '"num" < %(num)s'
        )
        assert (
            Number("num", Comparator.LESS, 5).prepare(sql, {}).as_string(connection)
            == '"num" < %(num)s'
        )
        assert (
            Number("num", Comparator.LESS, 5, invert=True)
            .prepare(sql, {})
            .as_string(connection)
            == '"num" >= %(num)s'
        )
        assert (
            Number("num", Comparator.LESS_EQUALS, 5)
            .prepare(sql, {})
            .as_string(connection)
            == '"num" <= %(num)s'
        )
        assert (
            Number("num", Comparator.LESS_EQUALS, 5, invert=True)
            .prepare(sql, {})
            .as_string(connection)
            == '"num" > %(num)s'
        )

        # null
        values = {}
        assert (
            Number("num", Comparator.EQUALS, None)
            .prepare(sql, values)
            .as_string(connection)
            == '"num" IS NULL'
        )
        assert (
            Number("num", Comparator.EQUALS, None, invert=True)
            .prepare(sql, values)
            .as_string(connection)
            == '"num" IS NOT NULL'
        )
        assert values == {}
        for comparator in (
            Comparator.GREATER,
            Comparator.GREATER_EQUALS,
            Comparator.LESS,
            Comparator.LESS_EQUALS,
        ):
            for invert in (False, True):
                with pytest.raises(ValueError):
                    print(comparator, invert)
                    Number("num", comparator, None, invert=invert).prepare(sql, values)

                assert values == {}

        with pytest.raises(ValueError):
            Number("num", Comparator.STARTS_WITH, 1).prepare(sql, values)

        with pytest.raises(ValueError):
            Number("num", Comparator.STARTS_WITH, 1, invert=True).prepare(sql, values)

        assert values == {}

        # boolean
        values = {"column1": 1}
        assert (
            Boolean("column", True)
            .prepare(sql, values, table="tbl")
            .as_string(connection)
            == '"tbl.column" = %(column)s'
        )
        assert values == {"column": True, "column1": 1}
        assert (
            Boolean("column", False, invert=True)
            .prepare(sql, values)
            .as_string(connection)
            == '"column" != %(column2)s'
        )
        assert values == {"column": True, "column1": 1, "column2": False}
        assert (
            Boolean("column", None).prepare(sql, values).as_string(connection)
            == '"column" IS NULL'
        )
        assert values == {"column": True, "column1": 1, "column2": False}
        assert (
            Boolean("column", None, invert=True)
            .prepare(sql, values)
            .as_string(connection)
            == '"column" IS NOT NULL'
        )
        assert values == {"column": True, "column1": 1, "column2": False}

        # combinations
        values = {}
        assert And(
            Text("a", Comparator.EQUALS, "A"),
            Text("b", Comparator.EQUALS, None, invert=True),
            Text("c", Comparator.EQUALS, "C"),
        ).prepare(sql, values, table="my_table").as_string(connection) == (
            '"my_table.a" = %(a)s '
            'AND "my_table.b" IS NOT NULL '
            'AND "my_table.c" = %(c)s'
        )
        assert values == {"a": "A", "c": "C"}
        assert (
            Or(
                Text("a", Comparator.EQUALS, "A"),
                Text("b", Comparator.EQUALS, None, invert=True),
                Text("c", Comparator.EQUALS, "C"),
            )
            .prepare(sql, values, table="t")
            .as_string(connection)
            == '"t.a" = %(a1)s OR "t.b" IS NOT NULL OR "t.c" = %(c1)s'
        )
        assert values == {"a": "A", "a1": "A", "c": "C", "c1": "C"}

        values = {}
        assert (
            And(
                Text("a", Comparator.EQUALS, "A"),
                Text("b", Comparator.EQUALS, None, invert=True),
                Text("c", Comparator.EQUALS, "C"),
                invert=True,
            )
            .prepare(sql, values)
            .as_string(connection)
            == 'NOT ("a" = %(a)s AND "b" IS NOT NULL AND "c" = %(c)s)'
        )
        assert values == {"a": "A", "c": "C"}
        assert (
            Or(
                Text("a", Comparator.EQUALS, "A"),
                Text("b", Comparator.EQUALS, None, invert=True),
                Text("c", Comparator.EQUALS, "C"),
                invert=True,
            )
            .prepare(sql, values)
            .as_string(connection)
            == 'NOT ("a" = %(a1)s OR "b" IS NOT NULL OR "c" = %(c1)s)'
        )
        assert values == {"a": "A", "a1": "A", "c": "C", "c1": "C"}

        assert And(
            Text("a", Comparator.EQUALS, "A"),
            Text("b", Comparator.EQUALS, None, invert=True),
            Or(
                Text("c", Comparator.EQUALS, "C"),
                And(
                    Text("d", Comparator.EQUALS, "D"),
                    Number("e", Comparator.EQUALS, 2.71828),
                ),
            ),
        ).prepare(sql, {}).as_string(connection) == (
            '"a" = %(a)s AND "b" IS NOT NULL AND ('
            '"c" = %(c)s OR ("d" = %(d)s AND "e" = %(e)s)'
            ")"
        )

        # dates
        timestamp = 1234567
        dt = datetime.utcfromtimestamp(timestamp)
        date = DateTime("col", Comparator.GREATER_EQUALS, dt)
        values = {}
        assert date.prepare(sql, values).as_string(connection) == ('"col" >= %(col)s')
        assert values == {"col": dt}
        values = {"col": 7}
        assert date.prepare(sql, values).as_string(connection) == ('"col" >= %(col1)s')
        assert values == {"col": 7, "col1": dt}

        values = {}
        dt2 = datetime.utcfromtimestamp(timestamp + 1)
        assert (
            DateTime("a", Comparator.LESS_EQUALS, [dt, dt2], invert=True)
            .prepare(sql, {})
            .as_string(connection)
            == '"a" > ANY(%(a)s)'
        )
        values = {"a": [dt, dt2]}


def test_sqlite():
    from picpocket.database.logic import (
        And,
        Boolean,
        Comparator,
        DateTime,
        Number,
        Or,
        Text,
    )
    from picpocket.database.sqlite import SqliteSQL

    sql = SqliteSQL()

    # invalid columns
    for column in ("", '"dogs"', "'dogs'", "dogs;"):
        with pytest.raises(ValueError):
            Text(column, Comparator.EQUALS, "value").prepare(sql, {})

    text = Text("column", Comparator.EQUALS, "value")

    values = {"column2": 2}
    assert text.prepare(sql, values) == '"column" = :column'
    assert values == {"column": "value", "column2": 2}

    # names shouldn't be clobbered
    values["column"] = "don't overwrite me"
    assert text.prepare(sql, values, table="my_table") == '"my_table.column" = :column1'
    assert values == {
        "column": "don't overwrite me",
        "column1": "value",
        "column2": 2,
    }

    assert text.prepare(sql, values) == '"column" = :column3'
    assert values == {
        "column": "don't overwrite me",
        "column1": "value",
        "column2": 2,
        "column3": "value",
    }

    # invert
    values = {}
    text = Text("col", Comparator.EQUALS, "val", invert=True)
    assert text.prepare(sql, values) == '"col" != :col'
    assert values == {"col": "val"}

    # null
    text = Text("col", Comparator.EQUALS, None)
    assert text.prepare(sql, values) == '"col" IS NULL'
    assert values == {"col": "val"}
    text = Text("col", Comparator.EQUALS, None, invert=True)
    assert text.prepare(sql, values, table="table") == '"table.col" IS NOT NULL'
    assert values == {"col": "val"}

    # any
    values = {}
    text = Text("col", Comparator.EQUALS, ["val", "val2"])
    assert text.prepare(sql, values) == '"col" IN (:col, :col1)'
    assert values == {"col": "val", "col1": "val2"}
    text = Text("col", Comparator.EQUALS, ["val2", "val1"], invert=True)
    assert text.prepare(sql, values) == '"col" NOT IN (:col2, :col3)'
    assert values == {"col": "val", "col1": "val2", "col2": "val2", "col3": "val1"}

    # startswith/endsfwith/contains
    values = {}
    text = Text("col", Comparator.STARTS_WITH, "val").prepare(sql, values)
    assert text == "\"col\" LIKE :col ESCAPE '#'"
    assert values == {"col": "val%"}

    values = {}
    text = Text("col", Comparator.ENDS_WITH, "val").prepare(sql, values)
    assert text == "\"col\" LIKE :col ESCAPE '#'"
    assert values == {"col": "%val"}

    values = {}
    text = Text("col", Comparator.CONTAINS, "val").prepare(sql, values)
    assert text == "\"col\" LIKE :col ESCAPE '#'"
    assert values == {"col": "%val%"}

    values = {}
    text = Text("col", Comparator.STARTS_WITH, "v_a#l%").prepare(sql, values)
    assert text == "\"col\" LIKE :col ESCAPE '#'"
    assert values == {"col": "v#_a##l#%%"}

    values = {}
    text = Text("col", Comparator.ENDS_WITH, "v_a#l%").prepare(sql, values)
    assert text == "\"col\" LIKE :col ESCAPE '#'"
    assert values == {"col": "%v#_a##l#%"}

    values = {}
    text = Text("col", Comparator.CONTAINS, "v_a#l%").prepare(sql, values)
    assert text == "\"col\" LIKE :col ESCAPE '#'"
    assert values == {"col": "%v#_a##l#%%"}

    # invalid comparator
    values = {}
    with pytest.raises(TypeError):
        Text("col", Comparator.GREATER, "val").prepare(sql, values)
    assert values == {}

    # numbers
    number = Number("number", Comparator.GREATER, 5)
    id = Number("id", Comparator.EQUALS, 2)

    values = {"number2": 2}
    assert number.prepare(sql, values) == '"number" > :number'
    assert id.prepare(sql, values, table="t") == '"t.id" = :id'
    assert values == {
        "id": 2,
        "number": 5,
        "number2": 2,
    }

    # names shouldn't be clobbered
    assert number.prepare(sql, values) == '"number" > :number1'
    assert number.prepare(sql, values) == '"number" > :number3'
    assert id.prepare(sql, values) == '"id" = :id1'
    assert values == {
        "id": 2,
        "id1": 2,
        "number": 5,
        "number1": 5,
        "number2": 2,
        "number3": 5,
    }

    # symbol & invert
    assert (
        Number("num", Comparator.EQUALS, 5).prepare(sql, {}, table="table")
        == '"table.num" = :num'
    )
    values = {}
    assert (
        Number("num", Comparator.EQUALS, [5], invert=True).prepare(sql, values)
        == '"num" != :num'
    )
    assert values == {"num": 5}
    values = {}
    assert (
        Number("num", Comparator.EQUALS, [], invert=True).prepare(sql, values)
        == "1 = 2"
    )
    assert values == {}
    assert (
        Number("num", Comparator.EQUALS, [5, 6]).prepare(sql, values)
        == '("num" = :num OR "num" = :num1)'
    )
    assert values == {"num": 5, "num1": 6}
    assert Number("num", Comparator.GREATER, 5).prepare(sql, {}) == '"num" > :num'
    assert (
        Number("num", Comparator.GREATER, [5, 6], invert=True).prepare(sql, values)
        == '("num" <= :num2 OR "num" <= :num3)'
    )
    assert values == {"num": 5, "num1": 6, "num2": 5, "num3": 6}
    assert (
        Number("num", Comparator.GREATER_EQUALS, 5).prepare(sql, {}) == '"num" >= :num'
    )
    assert (
        Number("num", Comparator.GREATER_EQUALS, 5, invert=True).prepare(sql, {})
        == '"num" < :num'
    )
    assert Number("num", Comparator.LESS, 5).prepare(sql, {}) == '"num" < :num'
    assert (
        Number("num", Comparator.LESS, 5, invert=True).prepare(sql, {})
        == '"num" >= :num'
    )
    assert Number("num", Comparator.LESS_EQUALS, 5).prepare(sql, {}) == '"num" <= :num'
    assert (
        Number("num", Comparator.LESS_EQUALS, 5, invert=True).prepare(sql, {})
        == '"num" > :num'
    )

    # null
    values = {}
    assert (
        Number("num", Comparator.EQUALS, None).prepare(sql, values) == '"num" IS NULL'
    )
    assert (
        Number("num", Comparator.EQUALS, None, invert=True).prepare(sql, values)
        == '"num" IS NOT NULL'
    )
    assert values == {}
    for comparator in (
        Comparator.GREATER,
        Comparator.GREATER_EQUALS,
        Comparator.LESS,
        Comparator.LESS_EQUALS,
    ):
        for invert in (False, True):
            with pytest.raises(ValueError):
                print(comparator, invert)
                Number("num", comparator, None, invert=invert).prepare(sql, values)

            assert values == {}

    with pytest.raises(ValueError):
        Number("num", Comparator.STARTS_WITH, 1).prepare(sql, values)

    with pytest.raises(ValueError):
        Number("num", Comparator.STARTS_WITH, 1, invert=True).prepare(sql, values)

    assert values == {}

    # boolean
    values = {"column1": 1}
    assert (
        Boolean("column", True).prepare(sql, values, table="tbl")
        == '"tbl.column" = :column'
    )
    assert values == {"column": True, "column1": 1}
    assert (
        Boolean("column", False, invert=True).prepare(sql, values)
        == '"column" != :column2'
    )
    assert values == {"column": True, "column1": 1, "column2": False}
    assert Boolean("column", None).prepare(sql, values) == '"column" IS NULL'
    assert values == {"column": True, "column1": 1, "column2": False}
    assert (
        Boolean("column", None, invert=True).prepare(sql, values)
        == '"column" IS NOT NULL'
    )
    assert values == {"column": True, "column1": 1, "column2": False}

    # combinations
    values = {}
    assert And(
        Text("a", Comparator.EQUALS, "A"),
        Text("b", Comparator.EQUALS, None, invert=True),
        Text("c", Comparator.EQUALS, "C"),
    ).prepare(sql, values, table="my_table") == (
        '"my_table.a" = :a AND "my_table.b" IS NOT NULL AND "my_table.c" = :c'
    )
    assert values == {"a": "A", "c": "C"}
    assert (
        Or(
            Text("a", Comparator.EQUALS, "A"),
            Text("b", Comparator.EQUALS, None, invert=True),
            Text("c", Comparator.EQUALS, "C"),
        ).prepare(sql, values, table="t")
        == '"t.a" = :a1 OR "t.b" IS NOT NULL OR "t.c" = :c1'
    )
    assert values == {"a": "A", "a1": "A", "c": "C", "c1": "C"}

    values = {}
    assert (
        And(
            Text("a", Comparator.EQUALS, "A"),
            Text("b", Comparator.EQUALS, None, invert=True),
            Text("c", Comparator.EQUALS, "C"),
            invert=True,
        ).prepare(sql, values)
        == 'NOT ("a" = :a AND "b" IS NOT NULL AND "c" = :c)'
    )
    assert values == {"a": "A", "c": "C"}
    assert (
        Or(
            Text("a", Comparator.EQUALS, "A"),
            Text("b", Comparator.EQUALS, None, invert=True),
            Text("c", Comparator.EQUALS, "C"),
            invert=True,
        ).prepare(sql, values)
        == 'NOT ("a" = :a1 OR "b" IS NOT NULL OR "c" = :c1)'
    )
    assert values == {"a": "A", "a1": "A", "c": "C", "c1": "C"}

    assert And(
        Text("a", Comparator.EQUALS, "A"),
        Text("b", Comparator.EQUALS, None, invert=True),
        Or(
            Text("c", Comparator.EQUALS, "C"),
            And(
                Text("d", Comparator.EQUALS, "D"),
                Number("e", Comparator.EQUALS, 2.71828),
            ),
        ),
    ).prepare(sql, {}) == (
        '"a" = :a AND "b" IS NOT NULL AND ("c" = :c OR ("d" = :d AND "e" = :e))'
    )

    # dates
    timestamp = 1234567
    dt = datetime.fromtimestamp(timestamp)
    date = DateTime("col", Comparator.GREATER_EQUALS, dt)
    values = {}
    assert date.prepare(sql, values) == '"col" >= :col'
    assert values == {"col": timestamp}
    values = {"col": 7}
    assert date.prepare(sql, values) == '"col" >= :col1'
    assert values == {"col": 7, "col1": timestamp}

    values = {}
    dt2 = datetime.fromtimestamp(timestamp + 1)
    assert (
        DateTime("a", Comparator.LESS_EQUALS, [dt, dt2], invert=True).prepare(sql, {})
        == '("a" > :a OR "a" > :a1)'
    )
    values = {"a": timestamp, "a1": timestamp + 1}

    # literal checks
    assert sql.literal(None) == "NULL"
    assert sql.literal(1) == "1"
    assert sql.literal(1.5) == "1.5"
    assert sql.literal(False) == "FALSE"
    assert sql.literal(True) == "TRUE"
    assert sql.literal("don't quote me") == "'don''t quote me'"

    # we don't have any backends that support arrays but not dates,
    # but let's make sure conversion is written correctly
    class ArraySqliteSQL(SqliteSQL):
        @property
        def arrays(self) -> bool:
            return True

        @property
        def escape(self):
            return None

    values = {}
    assert (
        DateTime("a", Comparator.EQUALS, [dt, dt2]).prepare(ArraySqliteSQL(), values)
        == '"a" = ANY(:a)'
    )
    assert values == {"a": [timestamp, timestamp + 1]}

    # while we're at it, let's make sure like escaping is handled properly
    values = {}
    assert (
        Text("col", Comparator.CONTAINS, ":wow:").prepare(ArraySqliteSQL(), values)
        == '"col" LIKE :col'
    )
    assert values == {"col": "%:wow:%"}
