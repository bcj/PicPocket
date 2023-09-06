"""Tests for the command-line interface

.. todo::
    break up run tests into individual subcommands
"""
import json
import logging
import os
import shutil
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path

import pytest


class Printer:
    def __init__(self):
        self.printed = []

    def print(self, text: str):
        self.printed.append(str(text))

    def text(self) -> str:
        text = "\n".join(self.printed)
        self.printed = []
        return text

    def lines(self) -> list[str]:
        return self.text().split()

    def json(self) -> dict:
        return json.loads(self.text())


@pytest.mark.asyncio
async def test_mount_requested(load_api, tmp_path):
    from picpocket.cli import mount_requested
    from picpocket.errors import InvalidPathError, UnknownItemError

    async with load_api() as api:
        main_id = await api.add_location("main", destination=True)
        other_id = await api.add_location("other", destination=True)

        await api.mount(main_id, tmp_path)

        # nothing to mount
        assert await mount_requested(api, None) == []
        assert api.mounts == {main_id: tmp_path}

        # mount by id or name + overwrite as necessary
        (tmp_path / "main").mkdir()
        (tmp_path / "other").mkdir()
        ids = await mount_requested(
            api,
            [
                ("main", str(tmp_path / "main")),
                (str(other_id), str(tmp_path / "other")),
            ],
        )
        assert ids == [main_id, other_id]
        assert api.mounts == {main_id: tmp_path / "main", other_id: tmp_path / "other"}

        # bad items should cause a reset
        (tmp_path / "new").mkdir()
        (tmp_path / "fake").mkdir()
        for mounts in (
            [
                ("main", str(tmp_path / "new")),
                (str(other_id), str(tmp_path / "nonexistent")),
            ],
        ):
            with pytest.raises(InvalidPathError):
                await mount_requested(api, mounts)

            assert api.mounts == {
                main_id: tmp_path / "main",
                other_id: tmp_path / "other",
            }

        for mounts in (
            [
                ("main", str(tmp_path / "new")),
                (main_id + other_id, str(tmp_path / "fake")),
            ],
            [("main", str(tmp_path / "new")), ("fake", str(tmp_path / "fake"))],
        ):
            with pytest.raises(UnknownItemError):
                await mount_requested(api, mounts)

            assert api.mounts == {
                main_id: tmp_path / "main",
                other_id: tmp_path / "other",
            }


def test_rating():
    from picpocket.cli import rating
    from picpocket.database.logic import Comparator, Number

    assert rating("1") == Number("rating", Comparator.EQUALS, 1)
    assert rating("<2") == Number("rating", Comparator.LESS, 2)
    assert rating("≤3") == Number("rating", Comparator.LESS_EQUALS, 3)
    assert rating(">4") == Number("rating", Comparator.GREATER, 4)
    assert rating("≥5") == Number("rating", Comparator.GREATER_EQUALS, 5)
    with pytest.raises(ValueError):
        print(rating("six"))


def test_build_meta(create_parser):
    from picpocket.cli import build_meta
    from picpocket.web import DEFAULT_PORT

    parser, subparsers = create_parser()

    # subparser objects don't know their own command but we can parse it
    # from prog.
    prelude = len(parser.prog) + 1
    commands = {subparser.prog[prelude:] for subparser in build_meta(subparsers)}
    assert commands == {"web", "import", "export"}

    # web
    args = parser.parse_args(["web", "--local-actions"])
    assert args == Namespace(
        command="web",
        port=DEFAULT_PORT,
        local_actions=True,
        suggestions=0,
        suggestion_lookback=25,
    )

    args = parser.parse_args(
        [
            "web",
            "--port",
            "1234",
            "--suggestions",
            "3",
            "--suggestion-lookback",
            "4",
        ]
    )
    assert args == Namespace(
        command="web",
        port=1234,
        local_actions=False,
        suggestions=3,
        suggestion_lookback=4,
    )

    # import
    args = parser.parse_args(["import", "backup.json"])
    assert args == Namespace(
        command="import",
        path=Path.cwd() / "backup.json",
        locations=None,
    )

    args = parser.parse_args(
        [
            "import",
            "~/backup.json",
            "--locations",
            "main",
            "camera",
        ]
    )
    assert args == Namespace(
        command="import",
        path=Path.home() / "backup.json",
        locations=["main", "camera"],
    )

    args = parser.parse_args(
        [
            "import",
            "/backup.json",
            "--location",
            "main",
            "/Volumes/main",
            "--location",
            "camera",
            "/Volumes/camera",
        ]
    )
    assert args == Namespace(
        command="import",
        path=Path("/backup.json"),
        locations=[["main", "/Volumes/main"], ["camera", "/Volumes/camera"]],
    )

    with pytest.raises(BaseException):
        parser.parse_args(
            [
                "import",
                "backup.json",
                "--locations",
                "main",
                "--location",
                "other",
                "/path",
            ]
        )

    # export
    args = parser.parse_args(["export", "backup.json"])
    assert args == Namespace(
        command="export",
        path=Path.cwd() / "backup.json",
        locations=None,
    )

    args = parser.parse_args(
        ["export", "~/backup.json", "--locations", "main", "camera"]
    )
    assert args == Namespace(
        command="export",
        path=Path.home() / "backup.json",
        locations=["main", "camera"],
    )


def test_build_locations(create_parser):
    from picpocket.cli import Output, build_locations

    parser, subparsers = create_parser()

    # subparser objects don't know their own command but we can parse it
    # from prog.
    prelude = len(parser.prog) + 1
    commands = {subparser.prog[prelude:] for subparser in build_locations(subparsers)}
    assert commands == {
        "location get",
        "location list",
        "location add",
        "location edit",
        "location remove",
    }

    # get
    args = parser.parse_args(["location", "get", "1"])
    assert args == Namespace(
        command="location",
        subcommand="get",
        name=1,
        output=Output.FULL,
    )

    args = parser.parse_args(["location", "get", "one", "--quiet"])
    assert args == Namespace(
        command="location",
        subcommand="get",
        name="one",
        output=Output.QUIET,
    )

    args = parser.parse_args(["location", "get", "won", "--json"])
    assert args == Namespace(
        command="location",
        subcommand="get",
        name="won",
        output=Output.JSON,
    )

    with pytest.raises(BaseException):
        parser.parse_args(["location", "get", "wan", "--quiet", "--json"])

    # list
    args = parser.parse_args(["location", "list"])
    assert args == Namespace(
        command="location",
        subcommand="list",
        output=Output.FULL,
    )

    args = parser.parse_args(["location", "list", "--count"])
    assert args == Namespace(
        command="location",
        subcommand="list",
        output=Output.COUNT,
    )

    args = parser.parse_args(["location", "list", "--quiet"])
    assert args == Namespace(
        command="location",
        subcommand="list",
        output=Output.QUIET,
    )

    args = parser.parse_args(["location", "list", "--json"])
    assert args == Namespace(
        command="location",
        subcommand="list",
        output=Output.JSON,
    )

    # add
    # minimal
    args = parser.parse_args(
        [
            "location",
            "add",
            "camera",
        ]
    )
    assert args == Namespace(
        command="location",
        subcommand="add",
        name="camera",
        path=None,
        description=None,
        source=False,
        destination=False,
        removable=True,
        skip_import=False,
        import_path=None,
        creator=None,
        tags=None,
        output=Output.FULL,
    )

    args = parser.parse_args(
        [
            "location",
            "add",
            "camera",
            "/Volumes/camera",
            "--description",
            "My camera",
            "--source",
            "--skip-import",
            "--quiet",
        ]
    )
    assert args == Namespace(
        command="location",
        subcommand="add",
        name="camera",
        path=Path("/Volumes/camera"),
        description="My camera",
        source=True,
        destination=False,
        removable=True,
        skip_import=True,
        import_path=None,
        creator=None,
        tags=None,
        output=Output.QUIET,
    )

    args = parser.parse_args(
        [
            "location",
            "add",
            "photos",
            "~/Photos",
            "--destination",
            "--non-removable",
            "--creator",
            "bcj",
            "--tag",
            "a/b/c",
            "--json",
        ]
    )
    assert args == Namespace(
        command="location",
        subcommand="add",
        name="photos",
        path=Path.home() / "Photos",
        description=None,
        source=False,
        destination=True,
        removable=False,
        skip_import=False,
        import_path=None,
        creator="bcj",
        tags=["a/b/c"],
        output=Output.JSON,
    )

    args = parser.parse_args(
        [
            "location",
            "add",
            "photos",
            "--destination",
            "--import-path",
            "/Volumes/photos",
            "--creator",
            "bcj",
            "--tag",
            "a/b/c",
            "--tag",
            "d",
        ]
    )
    assert args == Namespace(
        command="location",
        subcommand="add",
        name="photos",
        path=None,
        description=None,
        source=False,
        destination=True,
        removable=True,
        skip_import=False,
        import_path=Path("/Volumes/photos"),
        creator="bcj",
        tags=["a/b/c", "d"],
        output=Output.FULL,
    )

    # edit
    # minimal
    args = parser.parse_args(
        [
            "location",
            "edit",
            "camera",
        ]
    )
    assert args == Namespace(
        command="location",
        subcommand="edit",
        name="camera",
        new_name=None,
        path=None,
        description=None,
        source=None,
        destination=None,
        removable=None,
    )

    args = parser.parse_args(
        [
            "location",
            "edit",
            "5",
            "old camera",
            "--path",
            "/Volumes/old",
            "--remove-description",
            "--source",
            "--non-destination",
            "--removable",
        ]
    )
    assert args == Namespace(
        command="location",
        subcommand="edit",
        name=5,
        new_name="old camera",
        path=Path("/Volumes/old"),
        description=False,
        source=True,
        destination=False,
        removable=True,
    )

    args = parser.parse_args(
        [
            "location",
            "edit",
            "photos",
            "--path",
            "~/Pictures",
            "--description",
            "My photos",
            "--non-source",
            "--destination",
            "--non-removable",
        ]
    )
    assert args == Namespace(
        command="location",
        subcommand="edit",
        name="photos",
        new_name=None,
        path=Path.home() / "Pictures",
        description="My photos",
        source=False,
        destination=True,
        removable=False,
    )

    # remove
    args = parser.parse_args(
        [
            "location",
            "remove",
            "3",
        ]
    )
    assert args == Namespace(
        command="location",
        subcommand="remove",
        name=3,
        force=False,
    )

    args = parser.parse_args(
        [
            "location",
            "remove",
            "camera",
            "--force",
        ]
    )
    assert args == Namespace(
        command="location",
        subcommand="remove",
        name="camera",
        force=True,
    )


def test_build_tasks(create_parser):
    from picpocket.cli import Output, build_tasks

    parser, subparsers = create_parser()

    # subparser objects don't know their own command but we can parse it
    # from prog.
    prelude = len(parser.prog) + 1
    commands = {subparser.prog[prelude:] for subparser in build_tasks(subparsers)}
    assert commands == {
        "task get",
        "task list",
        "task add",
        "task run",
        "task remove",
    }

    # get
    args = parser.parse_args(["task", "get", "import-camera"])
    assert args == Namespace(
        command="task",
        subcommand="get",
        name="import-camera",
        output=Output.FULL,
    )

    args = parser.parse_args(["task", "get", "import-camera", "--json"])
    assert args == Namespace(
        command="task",
        subcommand="get",
        name="import-camera",
        output=Output.JSON,
    )

    # list
    args = parser.parse_args(["task", "list"])
    assert args == Namespace(command="task", subcommand="list", output=Output.FULL)

    args = parser.parse_args(["task", "list", "--json"])
    assert args == Namespace(command="task", subcommand="list", output=Output.JSON)

    # add
    args = parser.parse_args(["task", "add", "import-camera", "camera", "main"])
    assert args == Namespace(
        command="task",
        subcommand="add",
        name="import-camera",
        source="camera",
        destination="main",
        description=None,
        creator=None,
        tags=None,
        path=None,
        format=None,
        file_formats=None,
        force=False,
    )

    args = parser.parse_args(
        [
            "task",
            "add",
            "import-raw",
            "camera",
            "main",
            "--description",
            "import raw photos",
            "--creator",
            "bcj",
            "--tag",
            "a/b/c",
            "--tag",
            "d",
            "--path",
            "DCIM/{str:Camera}/{year}/{month}/{day}/{regex:^a.b.*$}",
            "--format",
            "raw/{file}",
            "--file-formats",
            "raw",
            ".orf",
            "--force",
        ]
    )
    assert args == Namespace(
        command="task",
        subcommand="add",
        name="import-raw",
        source="camera",
        destination="main",
        description="import raw photos",
        creator="bcj",
        tags=["a/b/c", "d"],
        path="DCIM/{str:Camera}/{year}/{month}/{day}/{regex:^a.b.*$}",
        format="raw/{file}",
        file_formats=["raw", ".orf"],
        force=True,
    )

    # run
    args = parser.parse_args(["task", "run", "import-camera"])
    assert args == Namespace(
        command="task",
        subcommand="run",
        name="import-camera",
        since=None,
        full=False,
        mounts=None,
        tags=None,
        output=Output.FULL,
    )
    args = parser.parse_args(
        ["task", "run", "import", "--tag", "dogs", "--tag", "cats", "--full", "--json"]
    )
    assert args == Namespace(
        command="task",
        subcommand="run",
        name="import",
        since=None,
        full=True,
        mounts=None,
        tags=["dogs", "cats"],
        output=Output.JSON,
    )
    args = parser.parse_args(
        [
            "task",
            "run",
            "import",
            "--count",
            "--mount",
            "source",
            "/path/to/source",
            "--mount",
            "2",
            "~/destination",
            "--since",
            "2020/01/02 3:04",
        ]
    )
    assert args == Namespace(
        command="task",
        subcommand="run",
        name="import",
        since=datetime(2020, 1, 2, 3, 4).astimezone(),
        full=False,
        mounts=[["source", "/path/to/source"], ["2", "~/destination"]],
        tags=None,
        output=Output.COUNT,
    )

    # remove
    args = parser.parse_args(["task", "remove", "import-camera"])
    assert args == Namespace(command="task", subcommand="remove", name="import-camera")


def test_build_images(create_parser):
    from picpocket.cli import Output, build_images
    from picpocket.database import logic
    from picpocket.internal_use import NotSupplied

    parser, subparsers = create_parser()

    # subparser objects don't know their own command but we can parse it
    # from prog.
    prelude = len(parser.prog) + 1
    commands = {subparser.prog[prelude:] for subparser in build_images(subparsers)}
    assert commands == {
        "image search",
        "image find",
        "image copy",
        "image edit",
        "image tag",
        "image untag",
        "image move",
        "image remove",
        "image verify",
    }

    # search
    # no args should make everything None
    args = parser.parse_args(["image", "search"])
    assert args == Namespace(
        command="image",
        subcommand="search",
        location=None,
        skip_location=None,
        conditions=None,
        between=None,
        creator=None,
        skip_creator=None,
        tagged=None,
        any_tags=None,
        all_tags=None,
        no_tags=None,
        reachable=None,
        mounts=None,
        limit=None,
        offset=None,
        order=None,
        output=Output.FULL,
    )

    args = parser.parse_args(
        [
            "image",
            "search",
            "--location",
            "main",
            "--location",
            "2",
            "--skip-location",
            "other",
            "--skip-location",
            "3",
            "--type",
            "jpeg",
            "--type",
            "jpg",
            "--skip-type",
            "png",
            "--skip-type",
            "bmp",
            "--rating",
            "≥3",
            "--since",
            "2023/01/02",
            "--before",
            "2000/02/03",
            "--year",
            "2002",
            "--between",
            "1970/03/04",
            "1999/12/31",
            "--has-creator",
            "--creator",
            "bcj",
            "--creator",
            "pablo",
            "--skip-creator",
            "gus",
            "--skip-creator",
            "sug",
            "--tagged",
            "--any-tag",
            "a/b/c",
            "--any-tag",
            "d",
            "--all-tag",
            "ef/g",
            "--all-tag",
            "hi",
            "--no-tag",
            "jk/l",
            "--no-tag",
            "mnop",
            "--reachable",
            "--mount",
            "main",
            "~/Pictures",
            "--mount",
            "portable",
            "/Volumes/portable",
            "--limit",
            "12",
            "--offset",
            "9",
            "--quiet",
            "--order=-id",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="search",
        location=["main", 2],
        skip_location=["other", 3],
        conditions=[
            logic.Text("extension", logic.Comparator.EQUALS, "jpeg"),
            logic.Text("extension", logic.Comparator.EQUALS, "jpg"),
            logic.Or(
                logic.Text("extension", logic.Comparator.EQUALS, None),
                logic.Text("extension", logic.Comparator.EQUALS, "png", invert=True),
            ),
            logic.Or(
                logic.Text("extension", logic.Comparator.EQUALS, None),
                logic.Text("extension", logic.Comparator.EQUALS, "bmp", invert=True),
            ),
            logic.Number("rating", logic.Comparator.GREATER_EQUALS, 3),
            logic.DateTime(
                "creation_date",
                logic.Comparator.GREATER_EQUALS,
                datetime(2023, 1, 2).astimezone(timezone.utc),
            ),
            logic.DateTime(
                "creation_date",
                logic.Comparator.LESS_EQUALS,
                datetime(2000, 2, 3).astimezone(timezone.utc),
            ),
            logic.And(
                logic.DateTime(
                    "creation_date",
                    logic.Comparator.GREATER_EQUALS,
                    datetime(2002, 1, 1).astimezone(timezone.utc),
                ),
                logic.DateTime(
                    "creation_date",
                    logic.Comparator.LESS,
                    datetime(2003, 1, 1).astimezone(timezone.utc),
                ),
            ),
            logic.Text("creator", logic.Comparator.EQUALS, None, invert=True),
        ],
        between=[
            datetime(1970, 3, 4).astimezone(timezone.utc),
            datetime(1999, 12, 31).astimezone(timezone.utc),
        ],
        creator=["bcj", "pablo"],
        skip_creator=["gus", "sug"],
        tagged=True,
        any_tags=["a/b/c", "d"],
        all_tags=["ef/g", "hi"],
        no_tags=["jk/l", "mnop"],
        reachable=True,
        mounts=[["main", "~/Pictures"], ["portable", "/Volumes/portable"]],
        limit=12,
        offset=9,
        order=["-id"],
        output=Output.QUIET,
    )

    args = parser.parse_args(
        [
            "image",
            "search",
            "--location",
            "main",
            "--skip-location",
            "3",
            "--type",
            "jpeg",
            "--skip-type",
            "png",
            "--rated",
            "--anonymous",
            "--unreachable",
            "--untagged",
            "--limit",
            "1000",
            "--order",
            "creation_date",
            "id",
            "--json",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="search",
        location=["main"],
        skip_location=[3],
        conditions=[
            logic.Text("extension", logic.Comparator.EQUALS, "jpeg"),
            logic.Or(
                logic.Text("extension", logic.Comparator.EQUALS, None),
                logic.Text("extension", logic.Comparator.EQUALS, "png", invert=True),
            ),
            logic.Number("rating", logic.Comparator.EQUALS, None, invert=True),
            logic.Text("creator", logic.Comparator.EQUALS, None),
        ],
        between=None,
        creator=None,
        skip_creator=None,
        tagged=False,
        any_tags=None,
        all_tags=None,
        no_tags=None,
        reachable=False,
        mounts=None,
        limit=1000,
        offset=None,
        order=["creation_date", "id"],
        output=Output.JSON,
    )

    args = parser.parse_args(["image", "find", "./image.png"])
    assert args == Namespace(
        command="image",
        subcommand="find",
        path=Path("image.png"),
        mounts=None,
        output=Output.FULL,
    )

    args = parser.parse_args(["image", "find", "./image.png", "--json"])
    assert args == Namespace(
        command="image",
        subcommand="find",
        path=Path("image.png"),
        mounts=None,
        output=Output.JSON,
    )

    args = parser.parse_args(
        [
            "image",
            "find",
            "/image.png",
            "--mount",
            "portable",
            "/Volumes/portable",
            "--mount",
            "other",
            "/other",
            "--quiet",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="find",
        path=Path("/image.png"),
        mounts=[["portable", "/Volumes/portable"], ["other", "/other"]],
        output=Output.QUIET,
    )

    args = parser.parse_args(
        [
            "image",
            "copy",
            "~/Downloads/new.jpg",
            "main",
            "downloaded/new.jpg",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="copy",
        source=Path.home() / "Downloads" / "new.jpg",
        location="main",
        destination=Path("downloaded") / "new.jpg",
        creator=None,
        title=None,
        caption=None,
        alt=None,
        rating=None,
        tag=None,
        mount=None,
    )

    args = parser.parse_args(
        [
            "image",
            "copy",
            "new.jpg",
            "2",
            "downloaded/new.jpg",
            "--creator",
            "bcj",
            "--title",
            "A title",
            "--caption",
            "A caption",
            "--alt",
            "descriptive text",
            "--rating",
            "4",
            "--tag",
            "a/bc",
            "--tag",
            "def",
            "--mount",
            "~/",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="copy",
        source=Path.cwd() / "new.jpg",
        location=2,
        destination=Path("downloaded") / "new.jpg",
        creator="bcj",
        title="A title",
        caption="A caption",
        alt="descriptive text",
        rating=4,
        tag=["a/bc", "def"],
        mount=Path.home(),
    )

    args = parser.parse_args(
        [
            "image",
            "edit",
            "1",
            "--no-creator",
            "--no-caption",
            "--no-alt",
            "--no-rating",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="edit",
        id=1,
        creator=None,
        title=NotSupplied(),
        caption=None,
        alt=None,
        rating=None,
    )

    args = parser.parse_args(
        [
            "image",
            "edit",
            "2",
            "--creator",
            "bcj",
            "--alt",
            "an image",
            "--title",
            "My Image",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="edit",
        id=2,
        creator="bcj",
        title="My Image",
        caption=NotSupplied(),
        alt="an image",
        rating=NotSupplied(),
    )

    args = parser.parse_args(
        [
            "image",
            "edit",
            "3",
            "--caption",
            "lens cap",
            "--rating",
            "1",
            "--no-title",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="edit",
        id=3,
        title=None,
        creator=NotSupplied(),
        caption="lens cap",
        alt=NotSupplied(),
        rating=1,
    )

    args = parser.parse_args(
        [
            "image",
            "move",
            "1",
            "new/path.jpg",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="move",
        id=1,
        path=Path("new") / "path.jpg",
        location=None,
        mounts=None,
    )

    args = parser.parse_args(
        [
            "image",
            "move",
            "2",
            "path.jpg",
            "main",
            "--mount",
            "main",
            "/home/main",
            "--mount",
            "1",
            "/path/other",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="move",
        id=2,
        path=Path("path.jpg"),
        location="main",
        mounts=[["main", "/home/main"], ["1", "/path/other"]],
    )

    args = parser.parse_args(
        [
            "image",
            "move",
            "3",
            "path.jpg",
            "1",
            "--mount",
            "1",
            "/path/other",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="move",
        id=3,
        path=Path("path.jpg"),
        location=1,
        mounts=[["1", "/path/other"]],
    )

    args = parser.parse_args(
        [
            "image",
            "remove",
            "1",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="remove",
        id=1,
        delete=False,
        mounts=None,
    )

    args = parser.parse_args(
        [
            "image",
            "remove",
            "2",
            "--delete",
            "--mount",
            "main",
            "/home/main",
            "--mount",
            "1",
            "/path/other",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="remove",
        id=2,
        delete=True,
        mounts=[["main", "/home/main"], ["1", "/path/other"]],
    )

    args = parser.parse_args(["image", "verify"])
    assert args == Namespace(
        command="image",
        subcommand="verify",
        location=None,
        path=None,
        exif=False,
        mounts=None,
        output=Output.FULL,
    )

    args = parser.parse_args(
        [
            "image",
            "verify",
            "--location",
            "1",
            "--mount",
            "1",
            "/Volumes",
            "--json",
            "--exif",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="verify",
        location=1,
        path=None,
        exif=True,
        mounts=[["1", "/Volumes"]],
        output=Output.JSON,
    )

    args = parser.parse_args(
        [
            "image",
            "verify",
            "--location",
            "main",
            "--path",
            "~/",
            "--quiet",
        ]
    )
    assert args == Namespace(
        command="image",
        subcommand="verify",
        location="main",
        path=Path.home(),
        exif=False,
        mounts=None,
        output=Output.QUIET,
    )


def test_build_tags(create_parser):
    from picpocket.cli import Output, build_tags
    from picpocket.internal_use import NotSupplied

    parser, subparsers = create_parser()

    # subparser objects don't know their own command but we can parse it
    # from prog.
    prelude = len(parser.prog) + 1
    commands = {subparser.prog[prelude:] for subparser in build_tags(subparsers)}
    assert commands == {
        "tag add",
        "tag move",
        "tag remove",
        "tag list",
    }

    # add
    args = parser.parse_args(["tag", "add", "abc/def"])
    assert args == Namespace(
        command="tag",
        subcommand="add",
        name="abc/def",
        description=NotSupplied(),
    )

    args = parser.parse_args(["tag", "add", "tag", "--description", "a tag"])
    assert args == Namespace(
        command="tag",
        subcommand="add",
        name="tag",
        description="a tag",
    )

    args = parser.parse_args(["tag", "add", "tag/subtag", "--remove-description"])
    assert args == Namespace(
        command="tag",
        subcommand="add",
        name="tag/subtag",
        description=None,
    )

    # move
    args = parser.parse_args(["tag", "move", "old", "new"])
    assert args == Namespace(
        command="tag",
        subcommand="move",
        current="old",
        new="new",
        cascade=True,
    )

    args = parser.parse_args(
        ["tag", "move", "old/position", "new/position", "--no-cascade"]
    )
    assert args == Namespace(
        command="tag",
        subcommand="move",
        current="old/position",
        new="new/position",
        cascade=False,
    )

    # remove
    args = parser.parse_args(["tag", "remove", "abc/def"])
    assert args == Namespace(
        command="tag",
        subcommand="remove",
        name="abc/def",
        cascade=False,
    )

    args = parser.parse_args(["tag", "remove", "tag", "--cascade"])
    assert args == Namespace(
        command="tag",
        subcommand="remove",
        name="tag",
        cascade=True,
    )

    # list
    args = parser.parse_args(["tag", "list"])
    assert args == Namespace(command="tag", subcommand="list", output=Output.FULL)

    args = parser.parse_args(["tag", "list", "--json"])
    assert args == Namespace(
        command="tag",
        subcommand="list",
        output=Output.JSON,
    )


# these namespaces are tested above. just check we can call something
# from every subcommand
def test_parse_cli(tmp_path):
    from picpocket.cli import DEFAULT_DIRECTORY, Output, parse_cli

    # initialize
    args = parse_cli(tmp_path, ["initialize"])
    assert args == Namespace(
        log_level=logging.INFO,
        log_directory=None,
        command="initialize",
        directory=tmp_path / DEFAULT_DIRECTORY,
        backend=None,
    )

    args = parse_cli(
        tmp_path, ["initialize", "--directory", "photo/directory", "sqlite"]
    )
    assert args == Namespace(
        log_level=logging.INFO,
        log_directory=None,
        command="initialize",
        directory=Path("photo/directory"),
        backend="sqlite",
        path=None,
    )

    args = parse_cli(
        tmp_path,
        ["initialize", "sqlite", "other/directory"],
    )
    assert args == Namespace(
        log_level=logging.INFO,
        log_directory=None,
        command="initialize",
        directory=tmp_path / DEFAULT_DIRECTORY,
        backend="sqlite",
        path=Path("other/directory"),
    )

    args = parse_cli(
        tmp_path,
        ["initialize", "--directory", "photo/directory", "postgres"],
    )
    assert args == Namespace(
        log_level=logging.INFO,
        log_directory=None,
        command="initialize",
        directory=Path("photo/directory"),
        backend="postgres",
        host=None,
        port=5432,
        db="picpocket",
        user="picpocket",
        password=None,
        no_password=False,
        store_password=False,
    )

    # meta
    args = parse_cli(tmp_path, ["import", "backup.json"])
    assert args == Namespace(
        log_level=logging.INFO,
        log_directory=None,
        config=tmp_path / DEFAULT_DIRECTORY,
        command="import",
        path=Path.cwd() / "backup.json",
        locations=None,
    )

    # location
    args = parse_cli(
        tmp_path,
        [
            "location",
            "remove",
            "3",
        ],
    )
    assert args == Namespace(
        log_level=logging.INFO,
        log_directory=None,
        config=tmp_path / DEFAULT_DIRECTORY,
        command="location",
        subcommand="remove",
        name=3,
        force=False,
    )

    # task
    args = parse_cli(tmp_path, ["task", "remove", "import-camera"])
    assert args == Namespace(
        log_level=logging.INFO,
        log_directory=None,
        config=tmp_path / DEFAULT_DIRECTORY,
        command="task",
        subcommand="remove",
        name="import-camera",
    )

    # image
    args = parse_cli(tmp_path, ["image", "find", "./image.png"])
    assert args == Namespace(
        log_level=logging.INFO,
        log_directory=None,
        config=tmp_path / DEFAULT_DIRECTORY,
        command="image",
        subcommand="find",
        path=Path("image.png"),
        mounts=None,
        output=Output.FULL,
    )

    # tag
    args = parse_cli(
        tmp_path,
        ["tag", "add", "a/nested/tag", "--description", "hi"],
    )
    assert args == Namespace(
        log_level=logging.INFO,
        log_directory=None,
        config=tmp_path / DEFAULT_DIRECTORY,
        command="tag",
        subcommand="add",
        name="a/nested/tag",
        description="hi",
    )


# the run tests probably aren't going to be exhaustive
@pytest.mark.asyncio
async def test_run_meta(load_api, tmp_path, image_files):
    from picpocket.cli import run_meta

    def compare_json_files(a: Path, b: Path):
        with a.open() as stream:
            a_data = json.load(stream)

        with b.open() as stream:
            b_data = json.load(stream)

        assert a_data == b_data

    async with load_api() as picpocket:
        printer = Printer()

        main = tmp_path / "main"
        main.mkdir()
        shutil.copy2(image_files[0], (main / "a.jpg"))
        shutil.copy2(image_files[1], (main / "b.jpg"))

        id = await picpocket.add_location("main", main, destination=True)
        await picpocket.import_location(id)

        other = tmp_path / "other"
        other.mkdir()
        shutil.copy2(image_files[0], (other / "a.jpg"))
        shutil.copy2(image_files[1], (other / "b.jpg"))

        id = await picpocket.add_location("other", other, destination=True)
        await picpocket.import_location(id)

        portable = tmp_path / "portable"
        portable.mkdir()
        shutil.copy2(image_files[0], (portable / "a.jpg"))
        shutil.copy2(image_files[1], (portable / "b.jpg"))

        id = await picpocket.add_location("portable", destination=True)
        await picpocket.mount(id, portable)
        await picpocket.import_location(id)
        await picpocket.unmount(id)

        api_backup = tmp_path / "api.json"
        cli_backup = tmp_path / "cli.json"

        # only some locations
        await picpocket.export_data(api_backup, locations=["main", "portable"])
        await run_meta(
            picpocket,
            Namespace(
                command="export",
                path=cli_backup,
                locations=["main", "portable"],
            ),
            print=printer.print,
        )
        compare_json_files(api_backup, cli_backup)

        # full backup
        await picpocket.export_data(api_backup)
        await run_meta(
            picpocket,
            Namespace(
                command="export",
                path=cli_backup,
                locations=None,
            ),
            print=printer.print,
        )
        compare_json_files(api_backup, cli_backup)

    # partial import
    async with load_api() as picpocket:
        await run_meta(
            picpocket,
            Namespace(
                command="import",
                path=cli_backup,
                locations=["main"],
            ),
            print=printer.print,
        )
        ids = [location.id for location in await picpocket.list_locations()]
        assert len(ids) == 1
        location = await picpocket.get_location(ids[0])
        assert location.name == "main"
        assert location.path == main
        assert await picpocket.count_images() == 2

    # 'full' import
    async with load_api() as picpocket:
        await run_meta(
            picpocket,
            Namespace(
                command="import",
                path=cli_backup,
                locations=None,
            ),
            print=printer.print,
        )
        # portable will exist but its images can't be imported
        assert len(await picpocket.list_locations()) == 3
        assert await picpocket.count_images() == 4

    async with load_api() as picpocket:
        await run_meta(
            picpocket,
            Namespace(
                command="import",
                path=cli_backup,
                locations=[["portable", str(portable)]],
            ),
            print=printer.print,
        )
        assert len(await picpocket.list_locations()) == 1
        assert await picpocket.count_images() == 2

        # unknown command
        with pytest.raises(NotImplementedError):
            await run_meta(
                picpocket,
                Namespace(command="this is not a command and it never will be"),
            )


@pytest.mark.asyncio
async def test_run_location(load_api, tmp_path, image_files):
    from picpocket.cli import Output, run_location

    async with load_api() as picpocket:
        printer = Printer()

        # search should give back an empty response
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="list",
                output=Output.FULL,
            ),
            print=printer.print,
        )
        assert not printer.text()

        # add a location
        directory = tmp_path / "main"
        directory.mkdir()
        shutil.copy2(image_files[0], (directory / "a.jpg"))
        shutil.copy2(image_files[1], (directory / "b.jpg"))

        await run_location(
            picpocket,
            Namespace(
                subcommand="add",
                name="main",
                description=None,
                path=directory,
                source=False,
                destination=True,
                removable=False,
                skip_import=False,
                import_path=None,
                creator="bcj",
                tags=[["abc", "def"], ["g"]],
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert data.keys() == {"location", "images"}
        id = data["location"]
        images = data["images"]
        location = await picpocket.get_location(id)
        assert location.name == "main"
        assert location.path == directory
        assert not location.source
        assert location.destination
        assert not location.removable

        for image_id in images:
            assert await picpocket.get_image(image_id)

        assert await picpocket.count_images() == 2

        # search should now give back input
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="list",
                output=Output.JSON,
            ),
            print=printer.print,
        )
        assert printer.json() == {
            "locations": [
                {
                    "id": id,
                    "name": "main",
                    "description": None,
                    "path": str(directory),
                    "source": False,
                    "destination": True,
                    "removable": False,
                    "mount_point": None,
                }
            ]
        }

        # quiet should just give back ids
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="list",
                output=Output.QUIET,
            ),
            print=printer.print,
        )
        assert int(printer.text().strip()) == id

        # count should be a count, duh
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="list",
                output=Output.COUNT,
            ),
            print=printer.print,
        )
        assert int(printer.text().strip()) == 1

        # add a removable location
        directory = tmp_path / "removable_directory"
        directory.mkdir()
        shutil.copy2(image_files[0], (directory / "a.jpg"))
        shutil.copy2(image_files[1], (directory / "b.jpg"))

        await run_location(
            picpocket,
            Namespace(
                subcommand="add",
                name="removable_directory",
                description=None,
                path=None,
                source=False,
                destination=True,
                removable=True,
                skip_import=False,
                import_path=directory,
                creator="bcj",
                tags=None,
                output=Output.QUIET,
            ),
            print=printer.print,
        )
        removable_id = int(printer.text().strip())
        location = await picpocket.get_location(removable_id)
        assert location.name == "removable_directory"
        assert location.path is None
        assert not location.source
        assert location.destination
        assert location.removable

        assert await picpocket.count_images() == 4

        # add location without importing
        directory = tmp_path / "other"
        directory.mkdir()
        shutil.copy2(image_files[0], (directory / "a.jpg"))
        shutil.copy2(image_files[1], (directory / "b.jpg"))

        await run_location(
            picpocket,
            Namespace(
                subcommand="add",
                name="other",
                description=None,
                path=directory,
                source=False,
                destination=True,
                removable=True,
                skip_import=True,
                import_path=None,
                creator="bcj",
                tags=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        other_id = int(printer.lines()[0].strip())

        assert other_id != id

        location = await picpocket.get_location(other_id)
        assert location.name == "other"
        assert location.path == directory
        assert not location.source
        assert location.destination
        assert location.removable

        assert await picpocket.count_images() == 4

        # adding combo source/dest shouldn't import
        directory = tmp_path / "source"
        directory.mkdir()
        shutil.copy2(image_files[0], (directory / "a.jpg"))
        shutil.copy2(image_files[1], (directory / "b.jpg"))

        await run_location(
            picpocket,
            Namespace(
                subcommand="add",
                name="source",
                description="My camera",
                path=directory,
                source=True,
                destination=True,
                removable=True,
                skip_import=False,
                import_path=None,
                creator="bcj",
                tags=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        source_id = data["location"]
        assert not data.get("images")

        location = await picpocket.get_location(source_id)
        assert location.name == "source"
        assert location.description == "My camera"
        assert location.path == directory
        assert location.source
        assert location.destination
        assert location.removable

        assert await picpocket.count_images() == 4

        # edit a location
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="edit",
                name="source",
                new_name="camera",
                path=False,
                description=False,
                source=True,
                destination=False,
                removable=None,
            ),
            print=printer.print,
        )

        assert not printer.text()
        location = await picpocket.get_location(source_id)
        assert location.name == "camera"
        assert location.description is None
        assert location.path is None
        assert location.source
        assert not location.destination
        assert location.removable

        # edit a location by id
        (tmp_path / "src").mkdir()
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="edit",
                name=location.id,
                new_name=None,
                path=tmp_path / "src",
                description="This is my camera",
                source=True,
                destination=False,
                removable=None,
            ),
            print=printer.print,
        )

        assert not printer.text()
        location = await picpocket.get_location(source_id)
        assert location.description == "This is my camera"

        # check list output
        another_location = tmp_path / "another"
        another_location.mkdir()
        await picpocket.mount("main", another_location)
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="list",
                conditions=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        await picpocket.unmount("main")
        output = printer.text()
        assert "main" in output
        assert "removable_directory" in output
        assert "other" in output
        assert "camera" in output
        assert output.count("source") == 1
        assert output.count("destination") == 3
        assert output.count("removable") == 3 + 1  # removable_directory
        assert "This is my camera" in output
        assert "another" in output
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="list",
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {location["name"] for location in data["locations"]} == {
            "main",
            "removable_directory",
            "other",
            "camera",
        }

        # remove a location
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="remove",
                name=location.id,
                force=False,
            ),
            print=printer.print,
        )

        assert not printer.text()
        assert await picpocket.get_location(source_id) is None

        # can't delete a location with images without force
        with pytest.raises(Exception):
            await run_location(
                picpocket,
                Namespace(
                    command="location",
                    subcommand="remove",
                    name="main",
                    force=False,
                ),
                print=printer.print,
            )

        assert not printer.text()
        assert await picpocket.get_location(id) is not None
        assert await picpocket.count_images() == 4

        # force delete
        await run_location(
            picpocket,
            Namespace(
                command="location",
                subcommand="remove",
                name="main",
                force=True,
            ),
            print=printer.print,
        )

        assert not printer.text()
        assert await picpocket.get_location(id) is None
        assert await picpocket.count_images() == 2

        # import text check
        directory = tmp_path / "xxx"
        directory.mkdir()
        shutil.copy2(image_files[0], (directory / "a.jpg"))
        shutil.copy2(image_files[1], (directory / "b.jpg"))

        await run_location(
            picpocket,
            Namespace(
                subcommand="add",
                name="xxx",
                description=None,
                path=directory,
                source=False,
                destination=True,
                removable=True,
                skip_import=False,
                import_path=None,
                creator=None,
                tags=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        assert "imported 2 images" in printer.text()

        # unknown command
        with pytest.raises(NotImplementedError):
            await run_location(
                picpocket,
                Namespace(
                    command="location",
                    subcommand="this is not a command and it never will be",
                ),
            )


@pytest.mark.asyncio
async def test_run_task(load_api, tmp_path, image_files):
    from picpocket.cli import Output, run_task
    from picpocket.errors import InvalidPathError, UnknownItemError

    async with load_api() as picpocket:
        printer = Printer()

        source = tmp_path / "source"
        subdirectory = source / "abc" / "def" / "ghi"
        subdirectory.mkdir(parents=True)
        shutil.copy2(image_files[0], (subdirectory / "a.jpg"))
        shutil.copy2(image_files[1], (subdirectory / "b.jpg"))
        skip = source / "abc" / "123"
        skip.mkdir(parents=True)
        shutil.copy2(image_files[0], (skip / "c.jpg"))
        shutil.copy2(image_files[1], (skip / "d.jpg"))

        await picpocket.add_location("source", source, source=True)

        destination = tmp_path / "destination"
        destination.mkdir()

        await picpocket.add_location("destination", destination, destination=True)

        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="add",
                name="import",
                source="source",
                destination="destination",
                description="my import task",
                creator="bcj",
                tags=["ab/cd"],
                path="abc/def/{regex:^gh.$}",
                format="{file}",
                file_formats=None,
                force=False,
            ),
        )

        task = await picpocket.get_task("import")
        assert task

        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="get",
                name="import",
                output=Output.JSON,
            ),
            print=printer.print,
        )
        assert task.serialize() == printer.json()

        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="list",
                output=Output.JSON,
            ),
            print=printer.print,
        )
        assert {"tasks": [task.serialize()]} == printer.json()

        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="run",
                name="import",
                since=None,
                full=False,
                mounts=None,
                tags=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        ids = printer.json()
        assert len(ids) == 2
        assert await picpocket.count_images() == 2
        assert {(await picpocket.get_image(id)).path.stem for id in ids} == {"a", "b"}

        # rerun shouldn't import anything
        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="run",
                name="import",
                since=None,
                full=False,
                mounts=None,
                tags=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        assert " 0 " in printer.text()

        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="run",
                name="import",
                since=None,
                full=False,
                mounts=None,
                tags=None,
                output=Output.COUNT,
            ),
            print=printer.print,
        )
        assert int(printer.text().strip()) == 0

        # task should now have last_run date
        task = await picpocket.get_task("import")
        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="get",
                name="import",
                output=Output.FULL,
            ),
            print=printer.print,
        )
        assert task.last_ran.strftime("%Y-%m-%d %H:%M") in printer.text()

        # mounting drives and editing tasks
        await picpocket.edit_location("source", path=None)

        with pytest.raises(InvalidPathError):
            await run_task(
                picpocket,
                Namespace(
                    command="task",
                    subcommand="run",
                    name="import",
                    since=None,
                    full=False,
                    mounts=None,
                    tags=None,
                    output=Output.COUNT,
                ),
            )

        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="run",
                name="import",
                since=None,
                full=False,
                mounts=[["source", source]],
                tags=["dogs", "cats"],
                output=Output.COUNT,
            ),
            print=printer.print,
        )
        assert int(printer.text().strip()) == 0

        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="add",
                name="import",
                source="source",
                destination="destination",
                description="my import task",
                creator="bcj",
                tags=["ab/cd"],
                path="abc/123",
                format="{file}",
                file_formats=None,
                force=True,
            ),
        )

        await run_task(
            picpocket,
            Namespace(
                command="task",
                subcommand="run",
                name="import",
                since=None,
                full=False,
                mounts=[["source", source]],
                tags=None,
                output=Output.COUNT,
            ),
            print=printer.print,
        )
        assert int(printer.text().strip()) == 2

        # remove
        await run_task(
            picpocket,
            Namespace(command="task", subcommand="remove", name="import"),
            print=printer.print,
        )

        with pytest.raises(UnknownItemError):
            await run_task(
                picpocket,
                Namespace(
                    command="task",
                    subcommand="get",
                    name="import",
                    output=Output.JSON,
                ),
                print=printer.print,
            )
            print(printer.text())

        # unknown command
        with pytest.raises(NotImplementedError):
            await run_task(
                picpocket,
                Namespace(subcommand="this is not a command and it never will be"),
            )


@pytest.mark.asyncio
async def test_run_image(load_api, tmp_path, image_files, test_images):
    from picpocket.cli import Output, run_image
    from picpocket.database import logic
    from picpocket.errors import UnknownItemError

    printer = Printer()

    async with load_api() as picpocket:
        # shouldn't find any images yet
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        assert not printer.text()

        # add images
        main = tmp_path / "main"
        main.mkdir()
        shutil.copy2(image_files[0], (main / "a.JPEG"))
        shutil.copy2(image_files[1], (main / "b.png"))

        mtime = datetime(1970, 1, 1).timestamp()
        os.utime((main / "a.JPEG"), (mtime, mtime))
        mtime = datetime(2000, 1, 2).timestamp()
        os.utime((main / "b.png"), (mtime, mtime))

        main_id = await picpocket.add_location("main", main, destination=True)
        await picpocket.import_location(main_id)

        other = tmp_path / "other"
        other.mkdir()
        shutil.copy2(image_files[2], (other / "c.JPEG"))

        mtime = datetime(2020, 2, 20).timestamp()
        os.utime((other / "c.JPEG"), (mtime, mtime))

        other_id = await picpocket.add_location("other", destination=True)
        await picpocket.mount(other_id, other)
        (c_id,) = await picpocket.import_location(other_id)
        await picpocket.unmount(other_id)

        # should now find images
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {Path(image["path"]).name for image in data["images"]} == {
            "a.JPEG",
            "b.png",
            "c.JPEG",
        }
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.COUNT,
            ),
            print=printer.print,
        )
        assert int(printer.text()) == 3

        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="find",
                path=other / "c.JPEG",
                mounts=[["other", str(other)]],
                output=Output.QUIET,
            ),
            print=printer.print,
        )
        id = int(printer.text())
        assert id == c_id

        with pytest.raises(UnknownItemError):
            await run_image(
                picpocket,
                Namespace(
                    command="image",
                    subcommand="find",
                    path=other / "d.JPEG",
                    mounts=[["other", str(other)]],
                    output=Output.QUIET,
                ),
            )

        # edit image
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="edit",
                id=id,
                creator="bcj",
                title="My Picture",
                caption="A picture",
                alt="A description of a picture",
                rating=4,
            ),
        )

        image = await picpocket.get_image(id)
        assert image.creator == "bcj"
        assert image.title == "My Picture"
        assert image.caption == "A picture"
        assert image.alt == "A description of a picture"
        assert image.rating == 4

        # move image
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="move",
                id=id,
                path=Path("new") / "path.jpeg",
                location=None,
                mounts=[["other", str(other)]],
            ),
        )

        image = await picpocket.get_image(id)
        assert image.path == Path("new") / "path.jpeg"

        # bad filter checks on search (& confirmed with json)
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "a.JPEG" in output
        assert "b.png" in output
        assert "c.JPEG" not in output
        assert "path.jpeg" in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.COUNT,
            ),
            print=printer.print,
        )
        assert int(printer.text()) == 3
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {Path(image["path"]).name for image in data["images"]} == {
            "a.JPEG",
            "b.png",
            "path.jpeg",
        }

        # 1 filter (non-condition)
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=["main"],
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "a.JPEG" in output
        assert "b.png" in output
        assert "path.jpeg" not in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=["main"],
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {Path(image["path"]).name for image in data["images"]} == {
            "a.JPEG",
            "b.png",
        }

        # 1 filter (condition)
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=[
                    logic.Number("rating", logic.Comparator.EQUALS, None, invert=True)
                ],
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "a.JPEG" not in output
        assert "b.png" not in output
        assert "path.jpeg" in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=[
                    logic.Number("rating", logic.Comparator.EQUALS, None, invert=True)
                ],
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {Path(image["path"]).name for image in data["images"]} == {"path.jpeg"}

        # multiple filters
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=[logic.Number("rating", logic.Comparator.EQUALS, None)],
                between=[
                    datetime(2000, 1, 1).astimezone(timezone.utc),
                    datetime(2002, 1, 1).astimezone(timezone.utc),
                ],
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "a.JPEG" not in output
        assert "b.png" in output
        assert "path.jpeg" not in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=[logic.Number("rating", logic.Comparator.EQUALS, None)],
                between=[
                    datetime(2000, 1, 1).astimezone(timezone.utc),
                    datetime(2002, 1, 1).astimezone(timezone.utc),
                ],
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {Path(image["path"]).name for image in data["images"]} == {"b.png"}

        # limit/offset
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=1,
                offset=None,
                order=["name"],
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "a.JPEG" in output
        assert "b.png" not in output
        assert "path.jpeg" not in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=1,
                offset=None,
                order=["name"],
                reachable=None,
                mounts=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {Path(image["path"]).name for image in data["images"]} == {"a.JPEG"}

        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=1,
                offset=1,
                order=["name"],
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "a.JPEG" not in output
        assert "b.png" in output
        assert "path.jpeg" not in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=1,
                offset=1,
                order=["name"],
                reachable=None,
                mounts=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {Path(image["path"]).name for image in data["images"]} == {"b.png"}

        # creator/skip_creator
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=["bcj", "fake person"],
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "a.JPEG" not in output
        assert "b.png" not in output
        assert "path.jpeg" in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=["bcj", "fake person"],
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {Path(image["path"]).name for image in data["images"]} == {"path.jpeg"}

        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=["bcj", "fake person"],
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "a.JPEG" in output
        assert "b.png" in output
        assert "path.jpeg" not in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=["bcj", "fake person"],
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert {Path(image["path"]).name for image in data["images"]} == {
            "a.JPEG",
            "b.png",
        }

        # unknown location
        with pytest.raises(UnknownItemError):
            await run_image(
                picpocket,
                Namespace(
                    command="image",
                    subcommand="search",
                    location=["unknown location"],
                    skip_location=None,
                    conditions=None,
                    between=None,
                    creator=None,
                    skip_creator=None,
                    tagged=None,
                    any_tags=None,
                    all_tags=None,
                    no_tags=None,
                    limit=None,
                    offset=None,
                    order=None,
                    reachable=None,
                    mounts=None,
                    output=Output.FULL,
                ),
            )

        # remove image
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="remove",
                id=id,
                delete=False,
                mounts=None,
            ),
        )
        assert await picpocket.get_image(id) is None
        assert (other / "new" / "path.jpeg").is_file()

        # tagging
        a_id = (await picpocket.find_image(main / "a.JPEG")).id
        b_id = (await picpocket.find_image(main / "b.png")).id
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="tag",
                id=a_id,
                name="a/b/c",
            ),
        )
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=True,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.QUIET,
            ),
            print=printer.print,
        )
        assert int(printer.text()) == a_id
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=["a/b/d", "x"],
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.QUIET,
            ),
            print=printer.print,
        )
        assert printer.lines() == [str(a_id), str(b_id)]
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="tag",
                id=b_id,
                name="a/b/c",
            ),
        )
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="tag",
                id=b_id,
                name="a/b/see",
            ),
        )
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=["a/b/c", "a/b/see"],
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.QUIET,
            ),
            print=printer.print,
        )
        assert printer.lines() == [str(a_id), str(b_id)]
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=["a/b/c", "a/b/see"],
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.QUIET,
            ),
            print=printer.print,
        )
        assert printer.text() == str(b_id)
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=["a/b/c", "a/b/see"],
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert str(b_id) in output
        assert "b.png" in output
        assert "a/b/c" in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="untag",
                id=b_id,
                name="a/b/see",
            ),
        )
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=["a/b/c", "a/b/see"],
                no_tags=None,
                limit=None,
                offset=None,
                order=None,
                reachable=None,
                mounts=None,
                output=Output.COUNT,
            ),
            print=printer.print,
        )
        assert int(printer.text()) == 0

        # copy (+ mounting)
        portable_id = await picpocket.add_location("portable", destination=True)
        portable = tmp_path / "portable"
        portable.mkdir()
        # minimal (should populate from exif data)
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="copy",
                source=test_images / "rotated.jpg",
                location="portable",
                destination="x.jpg",
                creator=None,
                title=None,
                caption=None,
                alt=None,
                rating=None,
                tags=None,
                mount=portable,
            ),
            print=printer.print,
        )
        x_id = int(printer.text())
        assert (portable / "x.jpg").is_file()
        image = await picpocket.get_image(x_id, tags=True)
        assert image.creator == "BCJ"
        assert image.title is None
        assert image.caption == "a sideways smiley face"
        assert image.alt is None
        assert image.rating is None
        assert image.tags == []

        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="copy",
                source=test_images / "rotated.jpg",
                location="portable",
                destination="y.jpg",
                creator="anon",
                title="smile",
                caption=":)",
                alt="a sideways smiley",
                rating=2,
                tags=["face/smiling", "emoji"],
                mount=portable,
            ),
            print=printer.print,
        )
        y_id = int(printer.text())
        assert (portable / "y.jpg").is_file()
        image = await picpocket.get_image(y_id, tags=True)
        assert image.creator == "anon"
        assert image.title == "smile"
        assert image.caption == ":)"
        assert image.alt == "a sideways smiley"
        assert image.rating == 2
        assert image.tags == ["face/smiling", "emoji"]

        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=None,
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=("name",),
                reachable=False,
                mounts=None,
                output=Output.QUIET,
            ),
            print=printer.print,
        )
        assert printer.lines() == [str(x_id), str(y_id)]

        with pytest.raises(UnknownItemError):
            await run_image(
                picpocket,
                Namespace(
                    command="image",
                    subcommand="find",
                    path=portable / "x.jpg",
                    mounts=None,
                    output=Output.FULL,
                ),
            )

        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="find",
                path=portable / "x.jpg",
                mounts=[["portable", str(portable)]],
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "x.jpg" in output
        assert "a sideways smiley face" in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="find",
                path=portable / "y.jpg",
                mounts=[["portable", str(portable)]],
                output=Output.JSON,
            ),
            print=printer.print,
        )
        image_data = printer.json()
        assert image_data["path"] == "y.jpg"
        assert image_data["location"] == portable_id
        assert image_data["caption"] == ":)"

        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="search",
                location=None,
                skip_location=None,
                conditions=None,
                between=None,
                creator=None,
                skip_creator=None,
                tagged=None,
                any_tags=["emoji"],
                all_tags=None,
                no_tags=None,
                limit=None,
                offset=None,
                order=("name",),
                reachable=True,
                mounts=[["portable", str(portable)]],
                output=Output.JSON,
            ),
            print=printer.print,
        )
        data = printer.json()
        assert len(data["images"]) == 1
        assert data["images"][0] == image_data

        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="remove",
                id=x_id,
                mounts=[["portable", str(portable)]],
                delete=True,
            ),
        )
        assert not (portable / "x.jpg").exists()
        assert await picpocket.get_image(x_id) is None

        # verify (can't look at unmounted)
        (main / "a.JPEG").unlink()
        (portable / "y.jpg").unlink()
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="verify",
                location=None,
                path=None,
                exif=False,
                mounts=None,
                output=Output.QUIET,
            ),
            print=printer.print,
        )
        assert printer.lines() == [str(a_id)]

        # verify (mounted, location)
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="verify",
                location=portable_id,
                path=None,
                exif=True,
                mounts=[["portable", str(portable)]],
                output=Output.JSON,
            ),
            print=printer.print,
        )
        image_data["tags"] = None
        assert printer.json() == {"missing": [image_data]}
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="verify",
                location=portable_id,
                path=None,
                exif=False,
                mounts=[["portable", str(portable)]],
                output=Output.FULL,
            ),
            print=printer.print,
        )
        output = printer.text()
        assert "y.jpg" in output
        assert "a.JPEG" not in output
        await run_image(
            picpocket,
            Namespace(
                command="image",
                subcommand="verify",
                location=portable_id,
                path=tmp_path / "portable" / "fake-subdirectory",
                exif=False,
                mounts=[["portable", str(portable)]],
                output=Output.FULL,
            ),
            print=printer.print,
        )
        assert printer.text() == "no missing images"

        # unknown command
        with pytest.raises(NotImplementedError):
            await run_image(
                picpocket,
                Namespace(
                    command="image",
                    subcommand="this is not a command and it never will be",
                ),
            )


@pytest.mark.asyncio
async def test_run_tag(load_api):
    from picpocket.cli import Output, run_tag

    async with load_api() as picpocket:
        printer = Printer()

        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="list",
                output=Output.FULL,
            ),
            print=printer.print,
        )
        assert not printer.text().strip()

        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="list",
                output=Output.JSON,
            ),
            print=printer.print,
        )
        assert not printer.json()

        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="add",
                name="name",
                description=None,
            ),
        )

        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="list",
                output=Output.JSON,
            ),
            print=printer.print,
        )
        assert printer.json() == {"name": {"description": None, "children": {}}}

        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="add",
                name="a/deeply/nested/tag",
                description="A tag description",
            ),
        )

        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="list",
                output=Output.JSON,
            ),
            print=printer.print,
        )
        assert printer.json() == {
            "a": {
                "description": None,
                "children": {
                    "deeply": {
                        "description": None,
                        "children": {
                            "nested": {
                                "description": None,
                                "children": {
                                    "tag": {
                                        "description": "A tag description",
                                        "children": {},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "name": {"description": None, "children": {}},
        }

        # remove
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="add",
                name="name",
                description="name's description",
            ),
        )
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="add",
                name="name/child",
                description="child's description",
            ),
        )
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="remove",
                name="name",
                cascade=False,
            ),
        )
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="list",
                output=Output.JSON,
            ),
            print=printer.print,
        )
        assert printer.json() == {
            "a": {
                "description": None,
                "children": {
                    "deeply": {
                        "description": None,
                        "children": {
                            "nested": {
                                "description": None,
                                "children": {
                                    "tag": {
                                        "description": "A tag description",
                                        "children": {},
                                    },
                                },
                            },
                        },
                    },
                },
            },
            "name": {
                "description": None,
                "children": {
                    "child": {"description": "child's description", "children": {}}
                },
            },
        }
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="remove",
                name="name",
                cascade=True,
            ),
        )
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="list",
                output=Output.JSON,
            ),
            print=printer.print,
        )
        assert printer.json() == {
            "a": {
                "description": None,
                "children": {
                    "deeply": {
                        "description": None,
                        "children": {
                            "nested": {
                                "description": None,
                                "children": {
                                    "tag": {
                                        "description": "A tag description",
                                        "children": {},
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }

        # move tag
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="add",
                name="alpha",
                description=None,
            ),
        )
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="add",
                name="alpha/bravo",
                description=None,
            ),
        )
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="add",
                name="alpha/bravo/alpha",
                description=None,
            ),
        )
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="move",
                current="alpha/bravo",
                new="a/b",
                cascade=False,
            ),
            print=printer.print,
        )
        assert printer.text().split(" ", 1)[0] == "1"
        await run_tag(
            picpocket,
            Namespace(
                command="tag",
                subcommand="move",
                current="alpha",
                new="a",
                cascade=True,
            ),
            print=printer.print,
        )
        assert printer.text().split(" ", 1)[0] == "2"

        # unknown command
        with pytest.raises(NotImplementedError):
            await run_tag(
                picpocket,
                Namespace(subcommand="this is not a command and it never will be"),
            )


def test_main(tmp_path, image_files):
    from picpocket.cli import DEFAULT_DIRECTORY, main
    from picpocket.configuration import CONFIG_FILE
    from picpocket.database.sqlite import DEFAULT_FILENAME

    printer = Printer()

    main(tmp_path, ["initialize"])

    config_directory = tmp_path / DEFAULT_DIRECTORY
    database = config_directory / DEFAULT_FILENAME
    assert config_directory.is_dir()
    assert database.is_file()

    fake_path = tmp_path / "fake"
    main_dir = tmp_path / "main"
    main_dir.mkdir()
    shutil.copy2(image_files[0], (main_dir / "a.jpg"))
    shutil.copy2(image_files[1], (main_dir / "b.jpg"))

    main(
        fake_path,
        [
            "location",
            "add",
            "--config",
            str(config_directory),
            "main",
            str(main_dir),
            "--destination",
            "--json",
        ],
        print=printer.print,
    )
    data = printer.json()
    main_id = data["location"]
    assert len(data["images"]) == 2
    ids = data["images"]

    main(
        tmp_path,
        [
            "image",
            "find",
            str(main_dir / "a.jpg"),
            "--json",
        ],
        print=printer.print,
    )
    data = printer.json()
    assert data["location"] == main_id
    assert data["id"] in ids
    a_id = data["id"]

    main(
        tmp_path,
        [
            "image",
            "find",
            str(main_dir / "b.jpg"),
            "--json",
        ],
        print=printer.print,
    )
    data = printer.json()
    assert data["location"] == main_id
    assert data["id"] in ids
    assert data["id"] != a_id

    main(
        tmp_path,
        [
            "tag",
            "add",
            "nested/tag",
            "--description",
            "A nested tag",
        ],
    )

    main(tmp_path, ["task", "add", "my task", "main", "main"])

    backup = tmp_path / "backup.json"
    main(tmp_path, ["export", str(backup)])

    with backup.open("r") as stream:
        data = json.load(stream)

    assert data["tags"] == {"nested/tag": "A nested tag"}
    assert len(data["tasks"]) == 1

    assert backup.is_file()

    new = tmp_path / "new"
    new.mkdir()
    database = tmp_path / "specified.sqlite"

    main(
        tmp_path,
        [
            "initialize",
            "--directory",
            str(new),
            "sqlite",
            str(database),
        ],
    )
    assert (new / CONFIG_FILE).is_file()
    assert database.is_file()


def test_main_postgres(pg_credentials, tmp_path):
    from picpocket.cli import main

    printer = Printer()

    args = ["initialize", "postgres"]

    if pg_credentials.get("dbname"):
        args.extend(["--db", pg_credentials["dbname"]])

    for key in ("host", "port", "user", "password"):
        if pg_credentials.get(key):
            args.extend([f"--{key}", str(pg_credentials[key])])

    if not pg_credentials.get("password"):
        args.append("--no-password")

    main(tmp_path, args, print=printer.print)

    main(
        tmp_path,
        ["location", "add", "src", "--description", "a source", "--source", "--quiet"],
        print=printer.print,
    )
    id = int(printer.text())

    main(tmp_path, ["location", "list", "--json"], print=printer.print)
    data = printer.json()
    assert data["locations"][0] == {
        "name": "src",
        "id": id,
        "description": "a source",
        "path": None,
        "source": True,
        "destination": False,
        "removable": True,
        "mount_point": None,
    }
