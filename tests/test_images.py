# most of these are fairly non-exhaustive.
from datetime import datetime, timedelta, timezone
from pathlib import Path


def test_mime_type(image_files):
    from picpocket.images import mime_type

    for path in image_files:
        mime = mime_type(path)
        match path.suffix.lower():
            case ".bmp":
                assert mime == "image/bmp"
            case ".jpeg" | ".jpg":
                assert mime == "image/jpeg"
            case ".png":
                assert mime == "image/png"
            case _:
                raise NotImplementedError(path.suffix)

        assert mime_type(Path(__file__)) is None


def test_image_info(test_images):
    from picpocket.images import image_info

    test_file = Path(__file__)
    assert image_info(test_file) == (None, None, None, None, None, {})

    width, height, creation_date, creator, description, exif = image_info(
        test_images / "a.bmp"
    )
    assert width == 5
    assert height == 5
    assert creation_date is None
    assert creator is None
    assert description is None
    assert exif == {}

    width, height, creation_date, creator, description, exif = image_info(
        test_images / "exif.jpg"
    )
    assert width == 12
    assert height == 10
    assert creation_date == datetime(2020, 1, 2, 3, 4, 5).astimezone()
    assert creator == "bcj"
    assert description == "a smiley face"
    assert exif == {
        "Artist": "bcj",
        "DateTime": "2001:01:01 01:01:01",
        "DateTimeDigitized": "2020:01:02 03:04:05",
        "DateTimeOriginal": "2020:01:02 03:04:05",
        "ImageDescription": "a smiley face",
        "ExifImageHeight": 10,
        "ExifImageWidth": 12,
    }


def test_parse_exif_date():
    from picpocket.images import parse_exif_date

    assert parse_exif_date("2021:02:03 4:56:01-23:45") == datetime(
        2021, 2, 3, 4, 56, 1, tzinfo=timezone(timedelta(hours=-23, minutes=-45))
    )

    assert (
        parse_exif_date("2021:02:03 4:56:01")
        == datetime(2021, 2, 3, 4, 56, 1).astimezone()
    )
