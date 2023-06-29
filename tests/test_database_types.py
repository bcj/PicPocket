from datetime import datetime, timezone
from pathlib import Path


def test_image():
    from picpocket.database.types import Image

    photo = Image(
        1,
        1,
        Path("image.jpg"),
        None,
        "Photo",
        "A photo",
        "a description of a photo",
        3,
    )
    drawing = Image(
        2,
        1,
        Path("drawings/image.PNG"),
        "person",
        "Drawing",
        "We just drew this",
        "A drawing in pencil of something",
        5,
    )

    # should equal itself
    assert photo == photo

    # images are different
    assert photo != drawing

    # different types are different
    assert photo != (
        1,
        1,
        Path("image.jpg"),
        None,
        "Photo",
        "A photo",
        "a description of a photo",
        3,
    )

    # should equal a recreation
    assert drawing == Image(
        2,
        1,
        "drawings/image.PNG",
        "person",
        "Drawing",
        "We just drew this",
        "A drawing in pencil of something",
        5,
    )

    # should not match on a different id
    assert drawing != Image(
        3,
        1,
        "drawings/image.PNG",
        "person",
        "Drawing",
        "We just drew this",
        "A drawing in pencil of something",
        5,
    )

    # should convert types
    creation_date = datetime(1999, 1, 1).astimezone(timezone.utc)
    last_modified = datetime(2000, 1, 1).astimezone(timezone.utc)
    image = Image(3, 1, "drawings/image.PNG", 9, 5, creation_date=creation_date)
    assert image.path == Path("drawings") / "image.PNG"
    assert image.creation_date == creation_date
    assert image.last_modified is None
    image = Image(
        3,
        1,
        "drawings/image.PNG",
        9,
        5,
        creation_date=creation_date.timestamp(),
        last_modified=last_modified,
    )
    assert image.creation_date == creation_date
    assert image.last_modified == last_modified
    image = Image(
        3,
        1,
        "drawings/image.PNG",
        last_modified=last_modified.timestamp(),
    )
    assert image.creation_date is None
    assert image.last_modified == last_modified

    # serialize
    print(photo.serialize())
    assert photo.serialize() == {
        "id": 1,
        "location": 1,
        "path": "image.jpg",
        "full_path": None,
        "creator": None,
        "title": "Photo",
        "caption": "A photo",
        "alt": "a description of a photo",
        "rating": 3,
        "hash": None,
        "width": None,
        "height": None,
        "creation_date": None,
        "last_modified": None,
        "exif": None,
        "tags": None,
    }


def test_location():
    from picpocket.database.types import Location

    main = Location(1, "main", "the main drive", "/Volumes/main", False, True, False)
    camera = Location(2, "camera", "your camera", None, True, False, True)

    # should equal itself
    assert main == main

    # different locations are different
    assert main != camera

    # different types are different
    assert main != (1, "main", "the main drive", "/Volumes/main", False, True, False)

    # should equal a recreation
    assert main == Location(
        1, "main", "the main drive", Path("/Volumes/main"), False, True, False
    )

    # should not equal on id mismatch
    assert main != Location(
        2, "main", "the main drive", Path("/Volumes/main"), False, True, False
    )

    assert main.serialize() == {
        "id": 1,
        "name": "main",
        "description": "the main drive",
        "path": "/Volumes/main",
        "mount_point": None,
        "source": False,
        "destination": True,
        "removable": False,
    }


def test_tag():
    from picpocket.database.types import Tag

    assert Tag("a/b/c", "a tag") == Tag("a/b/c", "a tag")
    assert Tag("a/b/c", "a tag") == Tag("a/b/c", "a tag", children={"d", "dee"})
    assert Tag("a/b/c", "a tag") != Tag("a/b/c", "a different description")
    assert Tag("a/b/c", "a tag") != Tag("a/b/d", "a tag")

    assert Tag("a/b/c", "a tag", children={"d", "dee"}).serialize() == {
        "name": "a/b/c",
        "description": "a tag",
        "children": ["d", "dee"],
    }
