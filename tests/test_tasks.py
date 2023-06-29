from datetime import datetime

import pytest


def test_year():
    from picpocket.tasks import Year

    year = Year()

    assert year.matches("folder", {"last_ran": None}) is None
    assert year.matches("2000", {"last_ran": None}) == {"year": 2000}

    # date + year
    assert year.matches("2000", {"last_ran": datetime(1999, 5, 10).astimezone()}) == {
        "year": 2000
    }
    assert (
        year.matches("2000", {"last_ran": datetime(2001, 5, 10).astimezone()}) is None
    )
    assert year.matches("2000", {"last_ran": datetime(2000, 5, 10).astimezone()}) == {
        "year": 2000
    }

    # date + year + day
    assert year.matches(
        "2000",
        {"last_ran": datetime(2000, 5, 10).astimezone(), "day": "5"},
    ) == {"year": 2000}

    # date + year + month + day
    assert year.matches(
        "2000",
        {
            "last_ran": datetime(2000, 5, 10).astimezone(),
            "month": "7",
            "day": "5",
        },
    ) == {"year": 2000}
    assert (
        year.matches(
            "2000",
            {
                "last_ran": datetime(2000, 5, 10).astimezone(),
                "month": "4",
                "day": "11",
            },
        )
        is None
    )
    assert year.matches(
        "2000",
        {
            "last_ran": datetime(2000, 5, 10).astimezone(),
            "month": "5",
            "day": "11",
        },
    ) == {"year": 2000}
    assert year.matches(
        "2000",
        {
            "last_ran": datetime(2000, 5, 10).astimezone(),
            "month": "5",
            "day": "10",
        },
    ) == {"year": 2000}
    assert (
        year.matches(
            "2000",
            {
                "last_ran": datetime(2000, 5, 10).astimezone(),
                "month": "5",
                "day": "9",
            },
        )
        is None
    )

    # date + year + month
    assert year.matches(
        "2000",
        {
            "last_ran": datetime(2000, 5, 10).astimezone(),
            "month": "5",
        },
    ) == {"year": 2000}

    assert str(year) == "{year}"


def test_month():
    from picpocket.tasks import Month

    month = Month()

    for directory in ("folder", "2000", "13", "0"):
        assert month.matches(directory, {"last_ran": None}) is None

    assert month.matches("12", {"last_ran": None}) == {"month": 12}

    # date + month
    assert month.matches("4", {"last_ran": datetime(1999, 5, 10).astimezone()}) == {
        "month": 4
    }

    # date + month + day
    assert month.matches(
        "4", {"last_ran": datetime(1999, 5, 10).astimezone(), "day": 9}
    ) == {"month": 4}

    # date + year + month
    assert month.matches(
        "4", {"last_ran": datetime(1999, 5, 10).astimezone(), "year": "2000"}
    ) == {"month": 4}
    assert (
        month.matches(
            "4", {"last_ran": datetime(1999, 5, 10).astimezone(), "year": "1999"}
        )
        is None
    )
    assert month.matches(
        "4", {"last_ran": datetime(1999, 4, 10).astimezone(), "year": "1999"}
    ) == {"month": 4}

    # date + year + month + day
    assert month.matches(
        "4",
        {
            "last_ran": datetime(1999, 4, 10).astimezone(),
            "year": "1999",
            "day": 11,
        },
    ) == {"month": 4}
    assert month.matches(
        "4",
        {
            "last_ran": datetime(1999, 4, 10).astimezone(),
            "year": "1999",
            "day": 10,
        },
    ) == {"month": 4}
    assert (
        month.matches(
            "4",
            {
                "last_ran": datetime(1999, 4, 10).astimezone(),
                "year": "1999",
                "day": 9,
            },
        )
        is None
    )

    assert str(month) == "{month}"


def test_day():
    from picpocket.tasks import Day

    day = Day()

    for directory in ("folder", "2000", "32", "0"):
        assert day.matches(directory, {"last_ran": None}) is None

    assert day.matches("12", {"last_ran": None}) == {"day": 12}

    # date + day
    assert day.matches("4", {"last_ran": datetime(1999, 5, 10).astimezone()}) == {
        "day": 4
    }

    # date + year + day
    assert day.matches(
        "4", {"last_ran": datetime(1999, 5, 10).astimezone(), "year": "1998"}
    ) == {"day": 4}

    # date + month + day
    assert day.matches(
        "4", {"last_ran": datetime(1999, 5, 10).astimezone(), "month": "3"}
    ) == {"day": 4}

    # date + year + month + day
    assert day.matches(
        "4",
        {
            "last_ran": datetime(1999, 5, 10).astimezone(),
            "year": "2000",
            "month": "3",
        },
    ) == {"day": 4}
    assert day.matches(
        "4",
        {
            "last_ran": datetime(1999, 5, 10).astimezone(),
            "year": "1999",
            "month": "6",
        },
    ) == {"day": 4}
    assert day.matches(
        "11",
        {
            "last_ran": datetime(1999, 5, 10).astimezone(),
            "year": "1999",
            "month": "5",
        },
    ) == {"day": 11}
    assert day.matches(
        "10",
        {
            "last_ran": datetime(1999, 5, 10).astimezone(),
            "year": "1999",
            "month": "5",
        },
    ) == {"day": 10}
    assert (
        day.matches(
            "9",
            {
                "last_ran": datetime(1999, 5, 10).astimezone(),
                "year": "1999",
                "month": "5",
            },
        )
        is None
    )

    assert str(day) == "{day}"


def test_date():
    from picpocket.tasks import Date

    date = Date("%Y-%m-%d %H:%M")

    for directory in ("folder", "2000-01-01"):
        assert date.matches(directory, {"last_ran": None}) is None

    assert date.matches("2000-01-02 3:04", {"last_ran": None}) == {
        "date": datetime(2000, 1, 2, 3, 4).astimezone()
    }

    assert date.matches(
        "2000-02-03 4:56",
        {"last_ran": datetime(1999, 5, 10).astimezone()},
    ) == {"date": datetime(2000, 2, 3, 4, 56).astimezone()}
    assert date.matches(
        "2000-02-03 4:56",
        {"last_ran": datetime(2000, 1, 10).astimezone()},
    ) == {"date": datetime(2000, 2, 3, 4, 56).astimezone()}
    assert date.matches(
        "2000-02-03 4:56",
        {"last_ran": datetime(2000, 2, 3, 4, 56).astimezone()},
    ) == {"date": datetime(2000, 2, 3, 4, 56).astimezone()}
    assert (
        date.matches(
            "2000-02-03 4:56",
            {"last_ran": datetime(2000, 2, 3, 4, 57).astimezone()},
        )
        is None
    )

    assert str(date) == "{date:%Y-%m-%d %H:%M}"


def test_regex():
    from picpocket.tasks import Regex

    regex = Regex(r"^(.)\.(\1*)$")

    assert regex.matches("a.aaaaaaa", {}) == {}
    assert regex.matches("a.aaaaaaab", {}) is None

    assert str(regex) == r"{regex:^(.)\.(\1*)$}"

    regex = Regex(r"^(?P<abc>.)\.(?:(?P=abc)*)$")

    assert regex.matches("a.aaaaaaa", {}) == {"abc": "a"}
    assert regex.matches("a.aaaaaaab", {}) is None

    assert str(regex) == r"{regex:^(?P<abc>.)\.(?:(?P=abc)*)$}"


def test_load_serialize_path():
    from picpocket.tasks import Date, Day, Month, Regex, Year, load_path, serialize_path

    assert load_path("text") == ["text"]
    assert serialize_path(["text"]) == "text"
    assert load_path("text/{str:{wow}") == ["text", "{wow"]
    assert serialize_path(["text", "{wow"]) == r"text/{str:{wow}"

    loaded = load_path("text/{year}")
    assert len(loaded) == 2
    assert loaded[0] == "text"
    assert isinstance(loaded[1], Year)
    assert serialize_path(["text", Year()]) == "text/{year}"

    loaded = load_path("text/{year}/{month}")
    assert len(loaded) == 3
    assert loaded[0] == "text"
    assert isinstance(loaded[1], Year)
    assert isinstance(loaded[2], Month)
    assert serialize_path(["text", Year(), Month()]) == "text/{year}/{month}"

    loaded = load_path("{month}/string/{day}")
    assert len(loaded) == 3
    assert isinstance(loaded[0], Month)
    assert loaded[1] == "string"
    assert isinstance(loaded[2], Day)
    assert serialize_path([Month(), "string", Day()]) == "{month}/string/{day}"

    assert load_path(r"{date:%Y-%m-%d}/{regex:^pattern.*$}") == [
        Date("%Y-%m-%d"),
        Regex(r"^pattern.*$"),
    ]
    assert r"{date:%Y-%m-%d}/{regex:^pattern.*$}" == serialize_path(
        [Date("%Y-%m-%d"), Regex(r"^pattern.*$")]
    )

    with pytest.raises(ValueError):
        load_path("{unknown:wow}")
