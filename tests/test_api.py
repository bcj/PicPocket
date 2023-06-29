import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from picpocket.database.types import Image


class FauxImage(Image):
    def __eq__(self, other) -> bool:
        if not isinstance(other, Image):
            return NotImplemented

        ignored = (
            "id",
            "hash",
            "width",
            "height",
            "creation_date",
            "last_modified",
            "exif",
            "full_path",
            "tags",
        )

        for key, value in other.__dict__.items():
            if key not in ignored and self.__dict__[key] != value:
                return False

        return True


def check_tag_dict(actual, expected):
    remaining = [("", actual, expected)]
    while remaining:
        path, a, e = remaining.pop(0)
        if a != e:
            if path:
                print(path)
            assert a.keys() == e.keys()
            for tag, a_data in a.items():
                if path:
                    new_path = f"{path}/{tag}"
                else:
                    new_path = tag

                e_data = e[tag]
                assert a_data["description"] == e_data["description"]
                remaining.append((new_path, a_data["children"], e_data["children"]))


@pytest.mark.asyncio
async def test_add_location(load_api, tmp_path):
    async with load_api() as api:
        # must be at least one of source, destination
        with pytest.raises(ValueError):
            await api.add_location("main", removable=True)

        assert await api.get_location("main") is None

        # non-removable location must have a path
        with pytest.raises(ValueError):
            await api.add_location("main", destination=True, removable=False)

        assert await api.get_location("main") is None

        # path must be a directory
        (tmp_path / "file").write_text("I'm a file")
        for path in (tmp_path / "non-existent", tmp_path / "file"):
            with pytest.raises(ValueError):
                await api.add_location("main", path, destination=True)

            assert await api.get_location("main") is None

        # minimal location
        main_id = await api.add_location("main", destination=True)

        main = await api.get_location("main")
        assert main.id == main_id
        assert main.description is None
        assert main.path is None
        assert not main.source
        assert main.destination
        assert main.removable

        # don't overwrite on add
        with pytest.raises(Exception):
            await api.add_location("main", source=True)

        main = await api.get_location("main")
        assert main.id == main_id
        assert main.description is None
        assert main.path is None
        assert not main.source
        assert main.destination
        assert main.removable

        directory = tmp_path / "camera"
        directory.mkdir()
        camera_id = await api.add_location(
            "camera",
            source=True,
            removable=True,
            path=directory,
            description="A camera",
        )
        assert main_id != camera_id

        camera = await api.get_location("camera")
        assert camera.id == camera_id
        assert camera.description == "A camera"
        assert camera.path == directory
        assert camera.source
        assert not camera.destination
        assert camera.removable


@pytest.mark.asyncio
async def test_edit_location(load_api, tmp_path):
    async with load_api() as api:
        await api.add_location("main", destination=True)
        camera_directory = tmp_path / "camera"
        camera_directory.mkdir()
        camera_id = await api.add_location(
            "camera",
            source=True,
            removable=True,
            path=camera_directory,
            description="A camera",
        )

        main = await api.get_location("main")
        camera = await api.get_location("camera")

        # edits must make changes
        with pytest.raises(ValueError):
            await api.edit_location("main")

        assert await api.get_location("main") == main

        # edits must be on real locations
        with pytest.raises(ValueError):
            await api.edit_location("man", source=True)

        # can't rename to conflicting name
        with pytest.raises(Exception):
            await api.edit_location(camera_id, "main")
        await api.get_location("main") == main
        await api.get_location("camera") == camera

        # can't move to bad path
        (tmp_path / "file").write_text("I'm a file")
        for path in (tmp_path / "non-existent", tmp_path / "file"):
            with pytest.raises(ValueError):
                await api.edit_location("main", path=path)

            assert (await api.get_location("main")).path is None

        # rename
        camera_directory_old = tmp_path / "camera (old)"
        camera_directory_old.mkdir()
        await api.edit_location(
            camera_id,
            "old camera",
            description="My _old_ camera",
            path=camera_directory_old,
        )

        edited = await api.get_location(camera.id)
        assert edited.id == camera.id
        assert edited.name == "old camera"
        assert edited.description == "My _old_ camera"
        assert edited.path == camera_directory_old
        camera = edited

        await api.get_location("main") == main

        # delete values
        await api.edit_location(
            "old camera",
            description=None,
            path=None,
            source=False,
            destination=True,
            removable=False,
        )

        edited = await api.get_location(camera.id)
        assert edited.id == camera.id
        assert edited.name == "old camera"
        assert edited.description is None
        assert edited.path is None
        assert not edited.source
        assert edited.destination
        assert not edited.removable
        camera = edited

        await api.get_location("main") == main


@pytest.mark.asyncio
async def test_remove_location(load_api, tmp_path, image_files):
    from picpocket.database.types import Location

    async with load_api() as api:
        main = tmp_path / "main"
        main.mkdir()
        main_id = await api.add_location(
            "main",
            path=main,
            destination=True,
        )
        (tmp_path / "Camera").mkdir()
        await api.add_location(
            "camera",
            source=True,
            removable=True,
            path=tmp_path / "Camera",
            description="A camera",
        )

        await api.remove_location("camera")

        assert await api.get_location("main") == Location(
            main_id, "main", None, main, False, True, True
        )

        # can't remove a location if it has images
        for name in ("a.jpg", "B.JPEG", "c.png"):
            path = main / name
            shutil.copy2(image_files[0], path)

        await api.import_location(main_id)
        with pytest.raises(Exception):
            await api.remove_location(main_id)
        assert len(list(main.iterdir())) == 3

        assert 3 == await api.count_images()
        assert await api.list_locations() == [
            Location(main_id, "main", None, main, False, True, True)
        ]

        # force should work but not delete actual files
        await api.remove_location(main_id, force=True)
        assert len(list(main.iterdir())) == 3
        assert 0 == await api.count_images()
        assert len(await api.list_locations()) == 0

        # can't remove a non-location
        with pytest.raises(ValueError):
            await api.remove_location("man")


@pytest.mark.asyncio
async def test_list_locations(load_api, tmp_path):
    from picpocket.database.types import Location

    async with load_api() as api:
        assert await api.list_locations() == []

        main_id = await api.add_location("main", destination=True)
        camera_directory = tmp_path / "camera"
        camera_directory.mkdir()
        camera_id = await api.add_location(
            "camera",
            source=True,
            removable=True,
            path=camera_directory,
            description="A camera",
        )

        main = Location(main_id, "main", None, None, False, True, True)
        camera = Location(
            camera_id, "camera", "A camera", camera_directory, True, False, True
        )

        assert await api.list_locations() in ([main, camera], [camera, main])

        # respect mount points
        camera, main = sorted(
            await api.list_locations(), key=lambda location: location.name
        )
        assert main.mount_point is None
        assert camera.mount_point is None

        await api.mount("main", tmp_path)
        camera, main = sorted(
            await api.list_locations(), key=lambda location: location.name
        )
        assert main.mount_point == tmp_path
        assert camera.mount_point is None


@pytest.mark.asyncio
async def test_mount_locations(load_api, tmp_path):
    async with load_api() as api:
        id = await api.add_location("external", destination=True)
        other_id = await api.add_location("other", destination=True)
        assert api.mounts == {}

        # add by id
        await api.mount(id, tmp_path)
        assert api.mounts == {id: tmp_path}
        assert (await api.get_location(id)).mount_point == tmp_path
        assert (await api.get_location(other_id)).mount_point is None

        # remounting should update
        (tmp_path / "new").mkdir()
        await api.mount(id, tmp_path / "new")
        assert api.mounts == {id: tmp_path / "new"}
        assert (await api.get_location(id)).mount_point == tmp_path / "new"
        assert (await api.get_location(other_id)).mount_point is None

        # mounting should fail on non-directories
        with pytest.raises(ValueError):
            await api.mount(id, tmp_path / "fake")
        (tmp_path / "file").write_text("this is a file")
        with pytest.raises(ValueError):
            await api.mount(id, tmp_path / "file")
        assert api.mounts == {id: tmp_path / "new"}

        # mounting should work by name
        (tmp_path / "new2").mkdir()
        await api.mount("external", tmp_path / "new2")
        assert api.mounts == {id: tmp_path / "new2"}
        assert (await api.get_location(id)).mount_point == tmp_path / "new2"
        assert (await api.get_location(other_id)).mount_point is None

        # unmounting should only remove one thing
        await api.mount(other_id, tmp_path)
        await api.unmount(id)
        assert api.mounts == {other_id: tmp_path}
        assert (await api.get_location(id)).mount_point is None
        assert (await api.get_location(other_id)).mount_point == tmp_path

        # unmounting by name should work
        await api.mount("external", tmp_path / "new2")
        await api.unmount("other")
        assert api.mounts == {id: tmp_path / "new2"}
        assert (await api.get_location(id)).mount_point == tmp_path / "new2"
        assert (await api.get_location(other_id)).mount_point is None


@pytest.mark.asyncio
async def test_import_locations(load_api, tmp_path, image_files, test_images):
    from picpocket.database import logic

    files = {}
    for root in ("main", "removable", "removable2"):
        root_directory = tmp_path / root

        for index, (directory, name, extension) in enumerate(
            (
                (root_directory / "text.txt", "caps", ".TXT"),
                (root_directory / "text.txt", "lower", ".txt"),
                (root_directory / "text.txt", "other", ".rtf"),
                (root_directory / "images", "image", ".jpg"),
                (root_directory / "images" / "subdirectory", "image", ".jpg"),
                (root_directory / "images", "BIG IMAGE", ".JPG"),
                (root_directory / "images", "image", ".JPEG"),
                (root_directory / "images", "image", ".png"),
                (root_directory / "images" / "raw", "raw", ".ORF"),
                (root_directory / "images", "vector", ".svg"),
            )
        ):
            directory.mkdir(parents=True, exist_ok=True)

            info = {"name": name, "extension": extension[1:].lower()}
            path = directory / f"{name}{extension}"
            shutil.copy2(image_files[index % 3], path)
            info["hash"] = sha256(path.read_bytes()).hexdigest()
            files[root, path.relative_to(root_directory)] = info

    async with load_api() as api:
        await api.add_location("removable", destination=True, removable=True)
        await api.add_location("main", path=tmp_path / "main", destination=True)

        main = await api.get_location("main")

        await api.add_tag("d", "this tag has a description")

        ids = await api.import_location("main", tags=["a/b/c", "d", "efg"])
        assert len(ids) == 6
        assert len(set(ids)) == 6
        assert (await api.get_tag("d")).description == "this tag has a description"

        images = await api.search_images()
        assert len(images) == 6
        for image in images:
            assert image.id in ids
            assert image.location == main.id
            assert ("main", image.path) in files
            assert sorted(image.tags) == ["a/b/c", "d", "efg"]

        # re-import should import no new images
        assert await api.import_location("main") == []

        assert images == await api.search_images()

        # re-import should find file changes though
        shutil.copy2(
            test_images / "test.jpg",
            tmp_path / "main" / "images" / "image.png",
        )
        image_ids = await api.import_location("main")
        assert len(image_ids) == 1

        # re-import should apply a creator name where none exists
        image_id = image_ids[0]
        await api.edit_image(image_id, creator="manually set")
        image_ids = await api.import_location("main", creator="reimport")
        assert len(image_ids) == 5
        assert (await api.get_image(image_id)).creator == "manually set"
        for id in image_ids:
            assert (await api.get_image(id)).creator == "reimport"

        ids = await api.import_location("main", file_formats={"txt"}, creator="bcj")
        assert len(ids) == 2

        images = await api.search_images(
            filter=logic.Text("extension", logic.Comparator.EQUALS, "txt")
        )
        assert len(images) == 2
        for image in images:
            assert image.id in ids
            assert image.creator == "bcj"
            assert image.location == main.id
            assert ("main", image.path) in files

        # make sure creator only applied to new images
        for image in await api.search_images(
            filter=logic.Text("extension", logic.Comparator.EQUALS, "txt", invert=True),
        ):
            if image.id == image_id:
                assert image.creator == "manually set"
            else:
                assert image.creator == "reimport"

        # unknown location
        with pytest.raises(ValueError):
            await api.import_location("fake")

        removable = await api.get_location("removable")

        # path must be given
        with pytest.raises(ValueError):
            await api.import_location("removable")

        # path must exist
        with pytest.raises(ValueError):
            await api.mount("removable", tmp_path / "fake")
            await api.import_location("removable")

        # path can't be a file
        with pytest.raises(ValueError):
            await api.mount("removable", Path(__file__))
            await api.import_location("removable")

        # NB this isn't a proper test of batch size
        await api.mount("removable", tmp_path / "removable")
        ids = await api.import_location(removable.id, batch_size=2)
        await api.unmount("removable")
        assert len(ids) == 6

        assert await api.count_images() == 14
        images = await api.search_images(
            filter=logic.Number("location", logic.Comparator.EQUALS, removable.id)
        )
        assert len(images) == 6
        for image in images:
            assert image.id in ids
            assert image.location == removable.id
            assert ("removable", image.path) in files

        # separate path shouldn't change anything
        await api.mount(removable.id, tmp_path / "removable2")
        assert not await api.import_location(removable.id)

        ids = await api.import_location("removable", file_formats={".txt"})
        await api.unmount(removable.id)
        assert len(ids) == 2
        images = await api.search_images(
            filter=logic.And(
                logic.Number("location", logic.Comparator.EQUALS, removable.id),
                logic.Text("extension", logic.Comparator.EQUALS, "txt"),
            )
        )
        assert len(images) == 2
        for image in images:
            assert image.id in ids
            assert image.location == removable.id
            assert ("removable", image.path) in files

        # check exif parsing
        image_directory = tmp_path / "images"
        image_directory.mkdir()
        shutil.copy2(test_images / "test.jpg", image_directory)
        shutil.copy2(test_images / "exif.jpg", image_directory)

        location = await api.add_location("images", image_directory, destination=True)
        ids = await api.import_location(location, creator="somebody")
        assert len(ids) == 2
        images = {}
        for id in ids:
            image = await api.get_image(id)
            images[image.path.name] = image

        assert len(images) == 2
        image = images["test.jpg"]
        assert image.last_modified == image.creation_date
        mtime = datetime.fromtimestamp(
            int((image_directory / image.path).stat().st_mtime)
        ).astimezone(timezone.utc)
        assert image.last_modified == mtime
        assert image.creator == "somebody"
        assert image.caption is None
        assert image.width == 12
        assert image.height == 10
        image = images["exif.jpg"]
        mtime = datetime.fromtimestamp(
            int((image_directory / image.path).stat().st_mtime)
        ).astimezone(timezone.utc)
        assert image.last_modified == mtime
        assert image.creation_date != mtime
        assert image.creation_date == datetime(2020, 1, 2, 3, 4, 5).astimezone()
        assert image.creator == "somebody"
        assert image.caption == "a smiley face"
        assert image.width == 12
        assert image.height == 10

        # invalid paths
        dne = tmp_path / "does not exit"
        dne.mkdir()
        id = await api.add_location("fake-path", dne, destination=True)
        dne.rmdir()
        with pytest.raises(ValueError):
            await api.import_location(id)

        file = tmp_path / "filename"
        file.mkdir()
        id = await api.add_location("filename", file, destination=True)
        file.rmdir()
        file.write_text("I'm a file!")
        with pytest.raises(ValueError):
            await api.import_location(id)


@pytest.mark.asyncio
async def test_tasks(load_api, tmp_path, image_files):
    from picpocket.database.types import Task
    from picpocket.images import hash_image

    async with load_api() as api:
        source = tmp_path / "source"
        source.mkdir()
        source_id = await api.add_location("source", source, source=True)

        destination = tmp_path / "destination"
        destination.mkdir()
        destination_id = await api.add_location(
            "destination", destination, destination=True
        )

        # invalid locations
        with pytest.raises(ValueError):
            await api.add_task("invalid", "fake", "destination")
        await api.get_task("invalid") is None

        with pytest.raises(ValueError):
            await api.add_task("invalid", "source", "fake")
        await api.get_task("invalid") is None

        with pytest.raises(ValueError):
            await api.run_task("invalid")

        assert [] == await api.list_tasks()

        # a basic task
        await api.add_task("basic", source_id, destination_id)
        basic = await api.get_task("basic")
        assert basic == Task(
            name="basic",
            source=source_id,
            destination=destination_id,
            configuration={},
            last_ran=None,
        )
        assert [basic] == await api.list_tasks()

        ajpg = source / "a.jpg"
        shutil.copy2(image_files[0], ajpg)

        bjpg = source / "b.jpg"
        shutil.copy2(image_files[1], bjpg)

        before = datetime.now().astimezone().replace(microsecond=0)

        image_ids = await api.run_task("basic")
        assert len(image_ids) == 2
        assert ajpg.is_file()
        assert (destination / "a.jpg").is_file()
        assert bjpg.is_file()
        assert (destination / "b.jpg").is_file()

        after = datetime.now().astimezone().replace(microsecond=0)
        after += timedelta(seconds=1)

        assert before <= (await api.get_task("basic")).last_ran <= after

        assert await api.find_image(ajpg) is None
        a = await api.find_image(destination / "a.jpg")
        assert a is not None
        assert a.id in image_ids
        b = await api.find_image(destination / "b.jpg")
        assert b is not None
        assert b.id in image_ids

        # rerun should find nothing
        assert await api.run_task("basic") == []

        # rerun should find new images
        shutil.copy2(image_files[2], source / "c.jpg")
        shutil.copy2(image_files[0], source / "d.jpg")
        timestamp = after.timestamp()
        os.utime((source / "c.jpg"), (timestamp, timestamp))
        definitely_before = before - timedelta(seconds=1)  # only second precision
        timestamp = definitely_before.timestamp()
        os.utime((source / "d.jpg"), (timestamp, timestamp))
        assert len(await api.run_task("basic")) == 1

        # rerun with since should find earlier image
        assert len(await api.run_task("basic")) == 0
        assert len(await api.run_task("basic", since=definitely_before)) == 1

        await api.add_task(
            "complicated",
            "source",
            "destination",
            description="A more complicated task",
            creator="bcj",
            tags=["a", "a/b/c"],
            source_path="subdirectory/{year}/{month}",
            destination_format="{date:%Y-%m}-{name}-{hash}.{extension}",
            file_formats={".jpg"},
        )

        complicated = await api.get_task("complicated")
        assert complicated == Task(
            name="complicated",
            source=source_id,
            destination=destination_id,
            description="A more complicated task",
            configuration={
                "source": "subdirectory/{year}/{month}",
                "destination": "{date:%Y-%m}-{name}-{hash}.{extension}",
                "creator": "bcj",
                "tags": ["a", "a/b/c"],
                "formats": [".jpg"],
            },
            last_ran=None,
        )

        assert await api.list_tasks() in ([basic, complicated], [complicated, basic])

        subdirectory = source / "subdirectory"
        subdirectory.mkdir()

        def get_directory(date: datetime) -> Path:
            return subdirectory / str(date.year) / str(date.month)

        index = 0

        def get_file(path: Path, date: datetime) -> Path:
            nonlocal index

            source = image_files[index]
            index = (index + 1) % len(image_files)

            path.parent.mkdir(exist_ok=True, parents=True)
            shutil.copy2(source, path)
            # we don't want to worry about filtering on modified date
            modified = date + timedelta(days=1_000)
            timestamp = modified.timestamp()
            os.utime(path, (timestamp, timestamp))
            hashed = hash_image(path)

            return destination / f"{modified:%Y-%m}-{path.stem}-{hashed}{path.suffix}"

        now = datetime.now().astimezone()
        ignored = [
            get_file(path, now)
            for path in (
                subdirectory / "ignored-a.jpg",  # not in year/month
                subdirectory / str(now.year) / "ignored-b.jpg",  # not in year/month
                subdirectory / str(now.year) / "13" / "ignored-c.jpg",  # invalid month
                get_directory(now) / "ignored-d.bmp",  # ignored filetype
            )
        ]

        dates = [
            now - timedelta(days=366),
            now - timedelta(days=30),
            now - timedelta(days=1),
            now,
            now + timedelta(days=1),
            now + timedelta(days=30),
            now + timedelta(days=366),
        ]

        filenames = {}
        for date in dates:
            filenames[(date, 0)] = get_file(
                get_directory(date) / f"0-{int(date.timestamp())}.jpg", date
            )
            filenames[(date, 1)] = get_file(
                get_directory(date) / "a" / "b" / f"1-{int(date.timestamp())}.jpg", date
            )

        # no previous run so we expect it to look at old directories
        ids = await api.run_task("complicated")
        assert len(ids) == 14

        for path in ignored:
            assert await api.find_image(path) is None

        for path in filenames.values():
            image = await api.find_image(path, tags=True)

            assert image.hash == image.path.stem.rsplit("-", 1)[-1]
            assert image.creator == "bcj"
            assert sorted(image.tags) == ["a", "a/b/c"]

        # we're not freezing dates so we should update now in case it
        # is a new day now
        dates[3] = now = datetime.now().astimezone()

        for date in dates:
            filenames[(date, 2)] = get_file(
                # sometimes auto-format is bad
                get_directory(date)
                / "a"
                / "b"
                / "c"
                / f"2-{int(date.timestamp())}.jpg",
                date,
            )
            filenames[(date, 3)] = get_file(
                get_directory(date) / f"3-{int(date.timestamp())}.png", date
            )

        ids = await api.run_task("complicated")

        expected = 0
        for date in dates:
            image = await api.find_image(filenames[(date, 2)], tags=True)
            if (date.year, date.month) >= (now.year, now.month):
                expected += 1
                assert image is not None
            else:
                assert image is None
            assert await api.find_image(filenames[(date, 3)], tags=True) is None

        assert len(ids) == expected

        # full=True should go back and find old images
        assert len(await api.run_task("complicated", full=True)) == 7 - expected

        # add task shouldn't overwrite by default
        with pytest.raises(ValueError):
            await api.add_task(
                "complicated",
                source_id,
                destination_id,
                description="A more complicated task (now with pngs)",
                creator="someone",
                tags=["a", "a/b/c"],
                source_path="subdirectory/{year}/{month}",
                destination_format="{date:%Y-%m}-{name}-{hash}.{extension}",
                file_formats={".jpg", ".png"},
            )

        task = await api.get_task("complicated")
        assert task == Task(
            name="complicated",
            source=source_id,
            destination=destination_id,
            description="A more complicated task",
            configuration={
                "source": "subdirectory/{year}/{month}",
                "destination": "{date:%Y-%m}-{name}-{hash}.{extension}",
                "creator": "bcj",
                "tags": ["a", "a/b/c"],
                "formats": [".jpg"],
            },
        )
        assert task.last_ran is not None

        # force update
        await api.add_task(
            "complicated",
            source_id,
            destination_id,
            description="A more complicated task (now with pngs!)",
            creator="someone",
            tags=["a", "a/b/c"],
            source_path="subdirectory/{year}/{month}",
            destination_format="{date:%Y-%m}-{name}-{hash}.{extension}",
            file_formats=[".jpg", ".png"],
            force=True,
        )

        task = await api.get_task("complicated")
        assert task == Task(
            name="complicated",
            source=source_id,
            destination=destination_id,
            description="A more complicated task (now with pngs!)",
            configuration={
                "source": "subdirectory/{year}/{month}",
                "destination": "{date:%Y-%m}-{name}-{hash}.{extension}",
                "creator": "someone",
                "tags": ["a", "a/b/c"],
                "formats": [".jpg", ".png"],
            },
        )
        assert task.last_ran is None

        ids = await api.run_task("complicated")
        assert len(ids) == 7

        for (_, index), path in filenames.items():
            image = await api.find_image(path)
            assert image is not None

            if index in (0, 1, 2):
                assert image.creator == "bcj"
            else:
                assert image.creator == "someone"
                assert image.id in ids

        # mountable drives
        rsource = tmp_path / "rsource"
        rsource.mkdir()
        rsource_id = await api.add_location("rsource", source=True)

        a = rsource / "a" / "b" / "a.jpg"
        a.parent.mkdir(parents=True)
        shutil.copy2(image_files[0], a)

        b = rsource / "b" / "b" / "b.jpg"
        b.parent.mkdir(parents=True)
        shutil.copy2(image_files[1], b)

        rdestination = tmp_path / "rdestination"
        rdestination.mkdir()
        rdestination_id = await api.add_location("rdestination", destination=True)

        await api.add_task(
            "removable",
            rsource_id,
            rdestination_id,
            source_path="a/b",
            destination_format="x.jpg",
        )

        await api.mount("rdestination", rdestination)

        # source unmounted
        with pytest.raises(ValueError):
            await api.run_task("removable")

        assert (await api.get_task("removable")).last_ran is None

        await api.mount("rsource", rsource)
        (id,) = await api.run_task("removable")
        image = await api.get_image(id)
        assert image.path == Path("x.jpg")
        assert image.full_path == rdestination / Path("x.jpg")
        assert image.hash == hash_image(a)
        assert (rdestination / "x.jpg").is_file()

        # skip files that would overwrite
        c = rsource / "a" / "b" / "c.jpg"
        shutil.copy2(image_files[2], c)

        assert not await api.run_task("removable")

        image = await api.get_image(id)
        assert image.path == Path("x.jpg")
        assert image.hash == hash_image(a)
        assert (rdestination / "x.jpg").is_file()

        last_ran = (await api.get_task("removable")).last_ran

        # destination unmounted
        await api.unmount("rdestination")
        with pytest.raises(ValueError):
            await api.run_task("removable")
        assert (await api.get_task("removable")).last_ran == last_ran

        await api.remove_task("removable")
        assert await api.get_task("removable") is None


@pytest.mark.asyncio
async def test_add_image_copy(load_api, tmp_path, image_files):
    from picpocket.database.types import Image
    from picpocket.images import hash_image

    async with load_api() as api:
        image = tmp_path / "image.jpg"
        shutil.copy2(image_files[0], image)

        directory = tmp_path / "location"
        directory.mkdir()

        location = await api.add_location("location", directory, destination=True)

        # minimal image
        image_id = await api.add_image_copy(image, "location", "copied-image.jpg")
        copied = directory / "copied-image.jpg"

        assert image.is_file()
        assert copied.is_file()
        assert hash_image(image) == hash_image(copied)

        assert await api.get_image(image_id, tags=True) == Image(
            image_id, location, Path("copied-image.jpg")
        )

        # can't copy to an existing location
        source = tmp_path / "other.jpg"
        shutil.copy2(image_files[1], source)
        with pytest.raises(ValueError):
            await api.add_image_copy(source, "location", "copied-image.jpg")
        assert hash_image(copied) == hash_image(image)

        # can't copy even if the source file no longer exists (but is in
        # the db)
        copied.unlink()
        with pytest.raises(ValueError):
            await api.add_image_copy(source, "location", "copied-image.jpg")
        assert hash_image(image) == (await api.get_image(image_id)).hash

        # image
        image_id = await api.add_image_copy(
            image,
            "location",
            Path("subdirectory") / "copied-image.jpg",
            creator="bcj",
            title="Title",
            caption="A description",
            alt="alt text",
            rating=5,
            tags=["wow", "another/tag", "nested/tag"],
        )
        copied = directory / "subdirectory" / "copied-image.jpg"

        assert image.is_file()
        assert copied.is_file()
        assert hash_image(image) == hash_image(copied)

        assert await api.get_image(image_id, tags=True) == Image(
            image_id,
            location,
            Path("subdirectory") / "copied-image.jpg",
            creator="bcj",
            title="Title",
            caption="A description",
            alt="alt text",
            rating=5,
            tags=["wow", "another/tag", "nested/tag"],
        )

        # unmounted drive
        remote = await api.add_location("remote", destination=True)
        remote_dir = tmp_path / "remote"
        remote_dir.mkdir()
        destination = remote_dir / "test.jpg"
        with pytest.raises(ValueError):
            await api.add_image_copy(image_files[0], remote, destination, caption="no")

        await api.mount("remote", remote_dir)
        image_id = await api.add_image_copy(
            image_files[0], remote, destination, caption="yes"
        )

        image = await api.get_image(image_id)
        assert image.id == image_id
        assert image.path == destination.relative_to(remote_dir)
        assert image.caption == "yes"


@pytest.mark.asyncio
async def test_edit_image(load_api, tmp_path, image_files):
    from picpocket.database import logic

    async with load_api() as api:
        ids = {}
        hashes = {}
        filename = "file.jpg"

        for index, (name, save_path, removable) in enumerate(
            (
                ("main", True, False),
                ("other", True, False),
                ("and another", True, False),
                ("external", False, True),
            )
        ):
            directory = tmp_path / name
            directory.mkdir()

            ids[name] = await api.add_location(
                name,
                directory if save_path else None,
                destination=True,
                removable=removable,
            )

            path = directory / filename
            path.parent.mkdir(exist_ok=True, parents=True)
            shutil.copy2(image_files[index % len(image_files)], path)
            hashes[name] = sha256(path.read_bytes()).hexdigest()

        await api.import_location(ids["main"])
        await api.mount(ids["external"], tmp_path / "external")
        await api.import_location(ids["external"])
        await api.unmount(ids["external"])

        min_id = max_id = None
        for image in await api.search_images(
            logic.Number("location", logic.Comparator.EQUALS, ids["main"])
        ):
            min_id = image.id

        for image in await api.search_images(
            logic.Number("location", logic.Comparator.EQUALS, ids["external"])
        ):
            max_id = image.id

        assert min_id is not None
        assert max_id is not None

        # non-existent image
        with pytest.raises(Exception):
            await api.edit_image(max_id + 1, caption="I don't exist")

        # no changes
        with pytest.raises(Exception):
            await api.edit_image(max_id)

        # illegal change
        with pytest.raises(Exception):
            await api.edit_image(max_id, rating="★★★")

        await api.edit_image(min_id, caption="first image")
        await api.edit_image(max_id, caption="last image")

        images = await api.search_images(
            logic.Text("caption", logic.Comparator.EQUALS, invert=True),
            order=("id",),
        )
        assert len(images) == 2
        assert images[0].caption == "first image"
        assert images[0].id == min_id
        assert images[1].caption == "last image"
        assert images[1].id == max_id
        assert images[1].rating is None


@pytest.mark.asyncio
async def test_tag_untag_image(load_api, tmp_path, image_files):
    async with load_api() as api:
        location = await api.add_location("main", tmp_path, destination=True)

        a_path = tmp_path / "a.jpg"
        shutil.copy2(image_files[0], a_path)

        b_path = tmp_path / "b.jpg"
        shutil.copy2(image_files[1], b_path)

        await api.import_location(location)

        a = await api.find_image(a_path)
        b = await api.find_image(b_path)

        # tag as string
        await api.tag_image(a.id, "string")
        await api.tag_image(a.id, "list")

        # nested tag
        await api.tag_image(b.id, "nested/list")

        # tag that already exists
        await api.tag_image(b.id, "list")

        assert sorted((await api.get_image(a.id, tags=True)).tags) == [
            "list",
            "string",
        ]
        assert sorted((await api.get_image(b.id, tags=True)).tags) == [
            "list",
            "nested/list",
        ]

        # duplicate add should be fine
        await api.tag_image(a.id, "string")
        assert sorted((await api.get_image(a.id, tags=True)).tags) == [
            "list",
            "string",
        ]

        # removal (string)
        await api.untag_image(a.id, "string")
        assert sorted((await api.get_image(a.id, tags=True)).tags) == ["list"]
        assert sorted((await api.get_image(b.id, tags=True)).tags) == [
            "list",
            "nested/list",
        ]

        # removal (list)
        await api.untag_image(b.id, "list")
        assert sorted((await api.get_image(a.id, tags=True)).tags) == ["list"]
        assert sorted((await api.get_image(b.id, tags=True)).tags) == ["nested/list"]

        # removal (nested list)
        await api.untag_image(b.id, "nested/list")
        assert sorted((await api.get_image(a.id, tags=True)).tags) == ["list"]
        assert sorted((await api.get_image(b.id, tags=True)).tags) == []


@pytest.mark.asyncio
async def test_move_image(load_api, tmp_path, image_files):
    async with load_api() as api:
        ids = {}
        filename = "a.jpg"

        for name, save_path, removable in (
            ("main", True, False),
            ("other", True, False),
            ("missing", True, False),
            ("moved", True, True),
            ("external", False, True),
            ("unmounted", True, True),
        ):
            directory = tmp_path / name
            directory.mkdir()

            ids[name] = await api.add_location(
                name,
                directory if save_path else None,
                destination=True,
                removable=removable,
            )

            path = directory / filename
            path.parent.mkdir(exist_ok=True, parents=True)
            shutil.copy2(image_files[0], path)

        await api.import_location(ids["main"])
        await api.import_location(ids["other"])
        await api.import_location(ids["unmounted"])
        await api.mount(ids["external"], tmp_path / "external")
        await api.import_location(ids["external"])
        await api.unmount(ids["external"])
        shutil.move(tmp_path / "moved", tmp_path / "was-moved")
        shutil.rmtree(tmp_path / "missing")
        shutil.rmtree(tmp_path / "unmounted")

        # can't move an unknown image
        image = (await api.search_images(order=("-id",)))[0]
        with pytest.raises(Exception):
            await api.move_image(image.id + 1, "fake.jpg")

        image = await api.find_image(tmp_path / "main" / filename)
        assert image is not None

        # can't move image to same location
        main = tmp_path / "main"
        with pytest.raises(Exception):
            await api.move_image(image.id, image.path)

        assert (main / filename).exists()
        await api.find_image(tmp_path / "main" / filename) == image

        # can't move image to a taken location
        taken = main / "taken.jpg"
        shutil.copy2(image_files[1], taken)
        with pytest.raises(Exception):
            await api.move_image(image.id, taken.name)

        assert (main / filename).exists()
        assert (main / filename).read_bytes() == image_files[0].read_bytes()
        assert taken.exists()
        assert taken.read_bytes() == image_files[1].read_bytes()

        # move image
        await api.move_image(image.id, Path("1.jpg"))
        assert not (main / filename).exists()
        assert (main / "1.jpg").exists()
        assert await api.find_image(tmp_path / "main" / filename) is None
        new_image = await api.find_image(tmp_path / "main" / "1.jpg")
        assert image.id == new_image.id
        assert new_image.path == Path("1.jpg")
        image = new_image

        # supply location
        await api.move_image(image.id, Path("2.jpg"), location=ids["main"])
        assert not (main / "1.jpg").exists()
        assert (main / "2.jpg").exists()

        # create directories if necessary
        await api.move_image(image.id, Path("1") / "2" / "3.jpg")
        assert not (main / "2.jpg").exists()
        assert (main / "1" / "2" / "3.jpg").exists()
        assert await api.find_image(tmp_path / "main" / filename) is None
        assert await api.find_image(tmp_path / "main" / "1.jpg") is None
        new_image = await api.find_image(tmp_path / "main" / "1" / "2" / "3.jpg")
        assert image.id == new_image.id
        assert new_image.path == Path("1") / "2" / "3.jpg"
        image = new_image

        # move to an unknown location
        with pytest.raises(ValueError):
            await api.move_image(
                image.id,
                Path("new.jpg"),
                location=max(ids.values()) + 1,
            )
        assert (main / "1" / "2" / "3.jpg").exists()

        # can't move to an existing image
        with pytest.raises(Exception):
            await api.move_image(image.id, filename, location=ids["other"])

        assert (main / "1" / "2" / "3.jpg").exists()
        assert (tmp_path / "other" / filename).exists()

        # even if the physical file doesn't exist
        (tmp_path / "other" / filename).unlink()
        with pytest.raises(Exception):
            await api.move_image(image.id, filename, location=ids["other"])

        assert (main / "1" / "2" / "3.jpg").exists()
        assert not (tmp_path / "other" / filename).exists()

        # moving to a new location
        await api.move_image(
            image.id,
            Path("new.jpg"),
            location=ids["other"],
        )
        assert not (main / "1.jpg").exists()
        assert (tmp_path / "other" / "new.jpg").exists()
        new_image = await api.find_image(tmp_path / "other" / "new.jpg")
        assert image.id == new_image.id
        assert new_image.path == Path("new.jpg")
        image = new_image

        # passing a name of a directory should fail
        subdirectory = tmp_path / "other" / "subdirectory"
        subdirectory.mkdir()
        with pytest.raises(Exception):
            await api.move_image(image.id, subdirectory)
        assert (tmp_path / "other" / "new.jpg").exists()
        assert subdirectory.is_dir()
        assert not (subdirectory / "new.jpg").exists()

        # passing an unmounted location should fail
        with pytest.raises(ValueError):
            await api.move_image(image.id, Path("new.jpg"), location=ids["unmounted"])

        assert (tmp_path / "other" / "new.jpg").exists()
        assert not (tmp_path / "external" / "new.jpg").exists()

        with pytest.raises(ValueError):
            await api.move_image(image.id, Path("new.jpg"), location=ids["external"])

        assert (tmp_path / "other" / "new.jpg").exists()
        assert not (tmp_path / "external" / "new.jpg").exists()

        # use mounted locations
        await api.mount(ids["external"], tmp_path / "external")
        await api.move_image(image.id, Path("new.jpg"), location=ids["external"])
        assert not (tmp_path / "other" / "new.jpg").exists()
        assert (tmp_path / "external" / "new.jpg").exists()

        # neither source nor destination exist
        new_path = tmp_path / "main" / "was-moved.jpg"
        shutil.move(tmp_path / "external" / "new.jpg", new_path)
        with pytest.raises(ValueError):
            await api.move_image(
                image.id, Path("wrong-location.jpg"), location=ids["main"]
            )
        await api.mount(ids["external"], tmp_path / "external")
        new_image = await api.find_image(tmp_path / "external" / image.path)
        assert image.id == new_image.id

        # image was moved outside the db
        await api.move_image(image.id, Path("was-moved.jpg"), location=ids["main"])
        assert new_path.exists()
        new_image = await api.find_image(new_path)
        assert image.id == new_image.id
        image = new_image

        # move from an unmounted location should fail
        image = await api.find_image(tmp_path / "external" / filename)
        await api.unmount(ids["external"])
        with pytest.raises(ValueError):
            await api.move_image(image.id, Path("can't-move.jpg"))
        assert (tmp_path / "external" / filename).exists()

        # path known but not present
        unmounted_image = await api.find_image(path)
        with pytest.raises(ValueError):
            await api.move_image(unmounted_image.id, Path("can't-move.jpg"))
        assert unmounted_image == await api.find_image(
            tmp_path / "unmounted" / filename
        )

        # can't move to impossible destinations
        (tmp_path / "external" / "file.txt").write_text("hello")
        await api.mount(ids["external"], tmp_path / "external")
        with pytest.raises(Exception):
            await api.move_image(image.id, Path("file.txt") / "oops.jpg")
        assert (tmp_path / "external" / filename).exists()
        assert (tmp_path / "external" / "file.txt").read_text() == "hello"
        assert image == await api.find_image(tmp_path / "external" / filename)


@pytest.mark.asyncio
async def test_remove_image(load_api, tmp_path, image_files):
    async with load_api() as api:
        ids = {}
        filenames = ("a.jpg", "b.JPEG", "c.d/e.png", "f.bmp", "g.gif")

        for name, save_path, removable in (
            ("main", True, False),
            ("external", False, True),
            ("unmounted", True, True),
        ):
            directory = tmp_path / name
            directory.mkdir()

            ids[name] = await api.add_location(
                name,
                directory if save_path else None,
                destination=True,
                removable=removable,
            )

            for filename in filenames:
                path = directory / filename
                path.parent.mkdir(exist_ok=True, parents=True)
                shutil.copy2(image_files[0], path)

        await api.import_location(ids["main"])
        await api.import_location(ids["unmounted"])
        await api.mount(ids["external"], tmp_path / "external")
        await api.import_location(ids["external"])
        await api.unmount(ids["external"])
        shutil.rmtree(tmp_path / "unmounted")

        # remove an image
        image = await api.find_image(tmp_path / "main" / "a.jpg")
        await api.remove_image(image.id, delete=True)
        assert not (tmp_path / "main" / "a.jpg").exists()
        assert await api.find_image(tmp_path / "main" / "a.jpg") is None

        # non-existent image
        with pytest.raises(Exception):
            await api.remove_image(image.id, delete=True)

        # not mounted
        image = await api.find_image(tmp_path / "unmounted" / "a.jpg")
        with pytest.raises(Exception):
            await api.remove_image(image.id, delete=True)
        assert image == await api.find_image(tmp_path / "unmounted" / "a.jpg")

        await api.mount(ids["external"], tmp_path / "external")
        image = await api.find_image(tmp_path / "external" / "a.jpg")
        await api.unmount(ids["external"])
        assert image is not None
        with pytest.raises(Exception):
            await api.remove_image(image.id, delete=True)
        await api.mount(ids["external"], tmp_path / "external")
        assert image == await api.find_image(tmp_path / "external" / "a.jpg")
        await api.unmount(ids["external"])
        assert (tmp_path / "external" / "a.jpg").exists()

        # location supplied
        await api.mount(ids["external"], tmp_path / "external")
        await api.remove_image(image.id, delete=True)
        assert await api.find_image(tmp_path / "external" / "a.jpg") is None
        await api.unmount(ids["external"])
        assert not (tmp_path / "external" / "a.jpg").exists()

        # don't delete
        image = await api.find_image(tmp_path / "main" / "b.JPEG")
        await api.remove_image(image.id, delete=False)
        assert (tmp_path / "main" / "b.JPEG").exists()
        assert await api.find_image(tmp_path / "main" / "b.JPEG") is None

        # file already deleted
        image = await api.find_image(tmp_path / "main" / "g.gif")
        (tmp_path / "main" / "g.gif").unlink()
        await api.remove_image(image.id, delete=True)
        assert await api.find_image(tmp_path / "main" / "g.gif") is None


@pytest.mark.asyncio
async def test_find_image(load_api, tmp_path, image_files):
    async with load_api() as api:
        # non-existent
        assert await api.find_image(tmp_path / "fake.image") is None

        ids = {}
        hashes = {}
        filenames = ("a.jpg", "b.JPEG", "c.d/e.png", "f.bmp", "g.gif")

        for name, save_path, removable in (
            ("main", True, False),
            ("external", False, True),
        ):
            directory = tmp_path / name
            directory.mkdir()

            ids[name] = await api.add_location(
                name,
                directory if save_path else None,
                destination=True,
                removable=removable,
            )

            for index, filename in enumerate(filenames):
                path = directory / filename
                path.parent.mkdir(exist_ok=True, parents=True)
                shutil.copy2(image_files[index % len(image_files)], path)
                hashes[(name, filename)] = sha256(path.read_bytes()).hexdigest()

        await api.import_location(ids["main"])

        # not in db
        assert await api.find_image(tmp_path / "fake.image") is None

        await api.mount(ids["external"], tmp_path / "external")
        await api.import_location(ids["external"])

        # file on main
        image = await api.find_image(tmp_path / "main" / "a.jpg")
        await api.unmount(ids["external"])
        assert image is not None
        assert image.location == ids["main"]
        assert image.path.name == "a.jpg"
        assert image.last_modified == datetime.fromtimestamp(
            int((tmp_path / "main" / "a.jpg").stat().st_mtime)
        ).astimezone(timezone.utc)

        # check tags
        assert image.tags is None
        await api.tag_image(image.id, "a/nested/tag")
        await api.tag_image(image.id, "another/tag")
        image = await api.find_image(tmp_path / "main" / "a.jpg")
        assert image.tags is None
        image = await api.find_image(tmp_path / "main" / "a.jpg", tags=True)
        assert sorted(image.tags) == ["a/nested/tag", "another/tag"]

        # unmounted
        assert await api.find_image(tmp_path / "external" / "a.jpg") is None

        # mounted (moveable)
        await api.mount(ids["external"], tmp_path / "external")
        image = await api.find_image(tmp_path / "external" / "a.jpg")
        await api.tag_image(image.id, "tag a")
        await api.tag_image(image.id, "tag/b/c")
        image = await api.find_image(tmp_path / "external" / "a.jpg")
        assert image is not None
        assert image.location == ids["external"]
        assert image.path.name == "a.jpg"
        assert image.tags is None
        image = await api.find_image(tmp_path / "external" / "a.jpg", tags=True)
        # this is an unfortunate sorting issue
        assert sorted(image.tags) == ["tag a", "tag/b/c"]


@pytest.mark.asyncio
async def test_verify_image_files(load_api, tmp_path, image_files, test_images):
    async with load_api() as api:
        ids = {}
        images = {}
        hashes = {}
        filenames = ("modified.jpg", "deleted.JPEG", "untouched.png")

        for name, save_path, removable in (
            ("main", True, False),
            ("missing", True, False),
            ("external", False, True),
            ("unmounted", True, True),
        ):
            directory = tmp_path / name
            directory.mkdir()

            ids[name] = await api.add_location(
                name,
                directory if save_path else None,
                destination=True,
                removable=removable,
            )

            for folder in (directory, directory / "subdirectory", directory / "other"):
                for filename in filenames:
                    path = folder / filename
                    path.parent.mkdir(exist_ok=True, parents=True)
                    shutil.copy2(image_files[0], path)
                    hashes[path] = sha256(path.read_bytes()).hexdigest()

            await api.mount(ids[name], directory)
            await api.import_location(ids[name])
            await api.unmount(ids[name])
            for folder in (directory, directory / "subdirectory", directory / "other"):
                for filename in filenames:
                    path = folder / filename
                    await api.mount(ids[name], directory)
                    images[path] = await api.find_image(path)
                    await api.unmount(ids[name])

                modified = folder / "modified.jpg"
                shutil.copy2(image_files[1], path)
                # our test runs too quickly for the last_modified time
                # to have changed at the 1s precision we're storing it at
                # that resolution is more than good enough for practical uses,
                # so we'll just cheat the mtime in the test instead.
                new_time = int(modified.stat().st_mtime) + 1
                os.utime(modified, (new_time, new_time))
                hashes[(modified, "new")] = sha256(modified.read_bytes()).hexdigest()

                (folder / "deleted.JPEG").unlink()

        shutil.rmtree(tmp_path / "unmounted")
        shutil.rmtree(tmp_path / "missing")

        # one directory of one location
        image = images[(tmp_path / "main" / "subdirectory" / "deleted.JPEG")]
        assert [image] == await api.verify_image_files(
            location=ids["main"], path=tmp_path / "main" / "subdirectory"
        )
        for location in ("main", "missing", "external", "unmounted"):
            directory = tmp_path / location
            if directory.is_dir():
                await api.mount(ids[location], directory)
            for folder in (directory, directory / "subdirectory", directory / "other"):
                # nothing should be deleted
                assert await api.find_image(folder / "modified.jpg") is not None
                assert await api.find_image(folder / "deleted.JPEG") is not None
                path = folder / "modified.jpg"
                if folder == tmp_path / "main" / "subdirectory":
                    expected = hashes[(path, "new")]
                else:
                    expected = hashes[path]

                image = await api.get_image(images[path].id)
                assert image.hash == expected

            if directory.is_dir():
                await api.unmount(ids[location])

        # unknown location
        with pytest.raises(ValueError):
            await api.verify_image_files(location=max(ids.values()) + 1)

        # missing location
        with pytest.raises(ValueError):
            await api.verify_image_files(location=ids["missing"])

        # unattached (provided)
        with pytest.raises(ValueError):
            await api.verify_image_files(location=ids["unmounted"])

        # unattached (not provided)
        with pytest.raises(ValueError):
            await api.verify_image_files(location=ids["external"])

        # mounted eternal
        missing = {
            images[path / "deleted.JPEG"].path: images[path / "deleted.JPEG"]
            for path in (
                tmp_path / "external",
                tmp_path / "external" / "subdirectory",
                tmp_path / "external" / "other",
            )
        }
        await api.mount(ids["external"], tmp_path / "external")
        actual = {
            image.path: image
            for image in await api.verify_image_files(location=ids["external"])
        }
        await api.unmount(ids["external"])
        assert actual == missing

        for location in ("main", "missing", "external", "unmounted"):
            directory = tmp_path / location

            if directory.is_dir():
                await api.mount(ids[location], directory)
            for folder in (directory, directory / "subdirectory", directory / "other"):
                # nothing should be deleted

                assert await api.find_image(folder / "modified.jpg") is not None
                assert await api.find_image(folder / "deleted.JPEG") is not None
                path = folder / "modified.jpg"
                if (
                    location == "external"
                    or folder == tmp_path / "main" / "subdirectory"
                ):
                    expected = hashes[(path, "new")]
                else:
                    expected = hashes[path]

                image = await api.get_image(images[path].id)
                assert image.hash == expected

            if directory.is_dir():
                await api.unmount(ids[location])

        # path only, no location
        image = images[(tmp_path / "main" / "other" / "deleted.JPEG")]
        assert [image] == await api.verify_image_files(path=tmp_path / "main" / "other")

        # 'all' (only mounted)
        missing = {
            (
                images[path / "deleted.JPEG"].location,
                images[path / "deleted.JPEG"].path,
            ): images[path / "deleted.JPEG"]
            for directory in ("main", "external")
            for path in (
                tmp_path / directory,
                tmp_path / directory / "subdirectory",
                tmp_path / directory / "other",
            )
        }
        await api.mount(ids["external"], tmp_path / "external")
        actual = await api.verify_image_files()
        await api.unmount(ids["external"])
        assert {(image.location, image.path): image for image in actual} == missing

        # should error if there's nothing to search
        shutil.rmtree(tmp_path / "main")
        with pytest.raises(ValueError):
            print(await api.verify_image_files())

        # check exif parsing
        image_directory = tmp_path / "images"
        image_directory.mkdir()
        shutil.copy2(test_images / "test.jpg", image_directory)
        shutil.copy2(test_images / "exif.jpg", image_directory)

        location = await api.add_location("images", image_directory, destination=True)
        ids = await api.import_location(location)
        assert len(ids) == 2

        rotated = test_images / "rotated.jpg"
        mtime = datetime.fromtimestamp(int(rotated.stat().st_mtime)).astimezone(
            timezone.utc
        )
        shutil.copy2(rotated, image_directory / "test.jpg")
        shutil.copy2(rotated, image_directory / "exif.jpg")

        assert await api.verify_image_files(location=location) == []

        image = await api.find_image(image_directory / "test.jpg")
        assert image.last_modified == mtime
        assert image.creation_date == datetime(2020, 1, 2, 3, 4, 6).astimezone()
        assert image.creator == "BCJ"
        assert image.caption == "a sideways smiley face"
        assert image.width == 10
        assert image.height == 12

        image = await api.find_image(image_directory / "exif.jpg")
        assert image.last_modified == mtime
        assert image.creation_date == datetime(2020, 1, 2, 3, 4, 6).astimezone()
        assert image.creator == "bcj"  # don't overwrite these!
        assert image.caption == "a smiley face"  # don't overwrite these!
        assert image.width == 10
        assert image.height == 12


@pytest.mark.asyncio
async def test_search_images(load_api, tmp_path, image_files):
    from picpocket.database import logic

    async with load_api() as api:
        # nothing to find
        assert await api.count_images() == 0
        assert await api.get_image_ids() == []
        assert await api.search_images() == []

        ids = {}
        hashes = {}
        mtimes = {
            "a.jpg": datetime(2021, 2, 3, 4, 56, 8),
            "b.JPEG": datetime(2021, 2, 3, 4, 56, 7),
            "c.d/e.png": datetime(2021, 2, 3, 4, 56, 7),
            "f.bmp": datetime(2021, 2, 3, 4, 6, 7),
            "g.gif": datetime(2020, 2, 3, 4, 56, 7),
        }
        filenames = list(sorted(mtimes.keys()))

        for name, save_path, removable in (
            ("main", True, False),
            ("missing", True, False),
            ("external", False, True),
        ):
            directory = tmp_path / name
            directory.mkdir()

            ids[name] = await api.add_location(
                name,
                directory if save_path else None,
                destination=True,
                removable=removable,
            )

            for index, (filename, date) in enumerate(mtimes.items()):
                path = directory / filename
                path.parent.mkdir(exist_ok=True, parents=True)
                shutil.copy2(image_files[index % 3], path)
                mtime = date.timestamp()
                os.utime(path, (mtime, mtime))
                hashes[(name, filename)] = sha256(path.read_bytes()).hexdigest()

        await api.import_location(ids["main"])
        await api.import_location(ids["missing"])
        await api.mount(ids["external"], tmp_path / "external")
        await api.import_location(ids["external"])
        await api.unmount(ids["external"])
        shutil.rmtree(tmp_path / "missing")

        expected_images = 3 * len(filenames)
        assert await api.count_images() == expected_images
        image_ids = await api.get_image_ids()
        assert len(image_ids) == expected_images
        assert len(set(image_ids)) == expected_images
        images = {}
        for image in await api.search_images():
            images[(image.location, image.path)] = image
            assert image.id in image_ids

        assert images == {
            (ids[name], Path(filename)): FauxImage(
                None, ids[name], Path(filename), None, None, None, None
            )
            for name in ("external", "main", "missing")
            for filename in filenames
        }

        images = []
        expected_ids = []
        for image in await api.search_images(limit=7, order=("-name", "location")):
            expected_ids.append(image.id)
            images.append(image)
        expected = [
            FauxImage(None, id, Path(filename), None, None, None, None)
            for filename in sorted(filenames, reverse=True)
            for id in sorted(ids.values())
        ][:7]
        assert images == expected
        assert expected_ids == await api.get_image_ids(
            limit=7, order=("-name", "location")
        )

        # sort by last_modified
        images = []
        expected_ids = []
        for image in await api.search_images(order=("last_modified", "name", "id")):
            expected_ids.append(image.id)
            images.append(image)
        assert images == [
            FauxImage(None, id, Path(filename), None, None, None, None)
            for filename, _ in sorted(mtimes.items(), key=lambda p: (p[1], p[0]))
            for id in sorted(ids.values())
        ]
        assert expected_ids == await api.get_image_ids(
            order=("last_modified", "name", "id")
        )

        # external not mounted
        # missing should be ignored
        comparison = logic.Text("extension", logic.Comparator.STARTS_WITH, "j")
        expected = {
            (ids["main"], Path(filename)): FauxImage(
                None, ids["main"], Path(filename), None, None, None, None
            )
            for filename in filenames
            if Path(filename).suffix[1:].lower().startswith("j")
        }
        assert await api.count_images(comparison, reachable=True) == len(expected)
        images = {}
        image_ids = set()
        for image in await api.search_images(comparison, reachable=True):
            images[(image.location, image.path)] = image
            image_ids.add(image.id)
        assert images == expected
        assert len(image_ids) == len(expected)
        assert set(await api.get_image_ids(comparison, reachable=True)) == image_ids

        # unmounted (missing should be listed here)
        expected = {
            (ids[location], Path(filename)): FauxImage(
                None, ids[location], Path(filename), None, None, None, None
            )
            for location in ("external", "missing")
            for filename in filenames
            if Path(filename).suffix[1:].lower().startswith("j")
        }
        assert await api.count_images(comparison, reachable=False) == len(expected)
        images = {}
        image_ids = set()
        for image in await api.search_images(comparison, reachable=False):
            images[(image.location, image.path)] = image
            image_ids.add(image.id)
        assert images == expected
        assert len(image_ids) == len(expected)
        assert set(await api.get_image_ids(comparison, reachable=False)) == image_ids

        # external mounted
        await api.mount(ids["external"], tmp_path / "external")
        expected = {
            (ids[location], Path(filename)): FauxImage(
                None, ids[location], Path(filename), None, None, None, None
            )
            for filename in filenames
            for location in ("external", "main")
            if Path(filename).suffix[1:].lower().startswith("j")
        }
        assert await api.count_images(comparison, reachable=True) == len(expected)
        images = {}
        image_ids = set()
        for image in await api.search_images(comparison, reachable=True):
            images[(image.location, image.path)] = image
            image_ids.add(image.id)
        assert images == expected
        assert len(image_ids) == len(expected)
        assert set(await api.get_image_ids(comparison, reachable=True)) == image_ids

        # mount check without other comparison
        expected = {
            (ids[location], Path(filename)): FauxImage(
                None, ids[location], Path(filename), None, None, None, None
            )
            for filename in filenames
            for location in ("external", "main")
        }
        assert await api.count_images(reachable=True) == len(expected)
        images = {}
        image_ids = set()
        for image in await api.search_images(reachable=True):
            images[(image.location, image.path)] = image
            image_ids.add(image.id)
        assert images == expected
        assert len(image_ids) == len(expected)
        assert set(await api.get_image_ids(reachable=True)) == image_ids
        await api.unmount(ids["external"])

        # ordering
        image_count = await api.count_images()
        image_ids = await api.get_image_ids(order=("id",))
        assert image_ids == sorted(image_ids)
        assert len(image_ids) == image_count
        images = await api.search_images(order=("id",))
        assert len(image_ids) == len(images)
        for id, image in zip(image_ids, images):
            assert image.id == id

        min_id = image_ids[0]
        max_id = image_ids[1]

        await api.edit_image(min_id, caption="first image")
        await api.edit_image(max_id, caption="last image")

        # null ordering
        image_ids = await api.get_image_ids(order=("!caption", "-id"))
        assert len(image_ids) == image_count
        images = await api.search_images(order=("!caption", "-id"))
        assert len(images) == image_count
        assert images[-2].caption == "first image"
        assert images[-2].id == image_ids[-2] == min_id
        assert images[-1].caption == "last image"
        assert images[-1].id == image_ids[-1] == max_id
        expected = sorted([image.id for image in images[:-2]], reverse=True)
        assert image_ids[:-2] == expected
        assert [image.id for image in images[:-2]] == expected

        image_ids = await api.get_image_ids(order=("-!caption", "id"))
        assert len(image_ids) == image_count
        images = await api.search_images(order=("-!caption", "id"))
        assert len(images) == image_count
        assert images[-2].caption == "last image"
        assert images[-2].id == image_ids[-2] == max_id
        assert images[-1].caption == "first image"
        assert images[-1].id == image_ids[-1] == min_id
        expected = sorted([image.id for image in images[:-2]])
        assert image_ids[:-2] == expected
        assert [image.id for image in images[:-2]] == expected

        image_ids = await api.get_image_ids(order=("caption!", "-id"))
        assert len(image_ids) == image_count
        images = await api.search_images(order=("caption!", "-id"))
        assert len(images) == image_count
        assert images[0].caption == "first image"
        assert images[0].id == image_ids[0] == min_id
        assert images[1].caption == "last image"
        assert images[1].id == image_ids[1] == max_id
        expected = sorted([image.id for image in images[2:]], reverse=True)
        assert image_ids[2:] == expected
        assert [image.id for image in images[2:]] == expected
        # limits/offsets
        image_ids = await api.get_image_ids(
            order=("caption!", "-id"), limit=image_count - 2
        )
        assert len(image_ids) == image_count - 2
        assert image_ids[2:] == expected[:-2]
        assert expected == await api.get_image_ids(
            order=("caption!", "-id"), limit=image_count - 2, offset=2
        )

        image_ids = await api.get_image_ids(order=("-caption!", "id"))
        assert len(image_ids) == image_count
        images = await api.search_images(order=("-caption!", "id"))
        assert len(images) == image_count
        assert images[0].caption == "last image"
        assert images[0].id == image_ids[0] == max_id
        assert images[1].caption == "first image"
        assert images[1].id == image_ids[1] == min_id
        expected = sorted([image.id for image in images[2:]])
        assert image_ids[2:] == expected
        assert [image.id for image in images[2:]] == expected

        # you can't have nulls first and last
        with pytest.raises(ValueError):
            await api.get_image_ids(order=("!rating!",))

        # 15! should be more than safe from the random order matching
        # our sorted order on repeated testing but add some wiggle room
        # in case we change our test without updating this check
        for _ in range(10):
            if images != await api.search_images(order=("random",)):
                break
        else:
            assert images != await api.search_images(order=("random",))

        for _ in range(10):
            if image_ids != await api.get_image_ids(order=("random",)):
                break
        else:
            assert image_ids != await api.get_image_ids(order=("random",))

        # non-existent row
        with pytest.raises(ValueError):
            await api.search_images(order=("nft",))

    # tag search
    async with load_api() as api:
        directory = tmp_path / "tag-testing"
        directory.mkdir()
        shutil.copy2(image_files[0], directory / "a.jpg")
        shutil.copy2(image_files[1], directory / "b.jpg")
        shutil.copy2(image_files[2], directory / "a.png")
        location = await api.add_location("main", directory, destination=True)
        await api.import_location(location)
        [ajpg, bjpg, apng] = await api.get_image_ids(order=("extension", "name"))

        await api.tag_image(ajpg, "aaa")
        await api.tag_image(ajpg, "abc")
        await api.tag_image(apng, "aaa")

        # tagged
        assert await api.count_images(tagged=True) == 2
        assert await api.get_image_ids(tagged=True, order=("extension", "name")) == [
            ajpg,
            apng,
        ]
        images = await api.search_images(tagged=True, order=("extension", "name"))
        assert [image.id for image in images] == [ajpg, apng]

        # untagged
        assert await api.count_images(tagged=False) == 1
        assert await api.get_image_ids(tagged=False, order=("extension", "name")) == [
            bjpg,
        ]
        images = await api.search_images(tagged=False, order=("extension", "name"))
        assert [image.id for image in images] == [bjpg]

        # tagging + other filter
        filter = logic.Text("extension", logic.Comparator.EQUALS, "jpg")
        assert await api.count_images(filter, tagged=True) == 1
        assert await api.get_image_ids(
            filter, tagged=True, order=("extension", "name")
        ) == [ajpg]
        images = await api.search_images(
            filter, tagged=True, order=("extension", "name")
        )
        assert [image.id for image in images] == [ajpg]

        # any_tags
        assert await api.count_images(any_tags=["abc", "bbb"]) == 1
        assert await api.get_image_ids(
            any_tags=["abc", "bbb"], order=("extension", "name")
        ) == [ajpg]
        images = await api.search_images(any_tags=["abc", "bbb"])
        assert [image.id for image in images] == [ajpg]

        # all_tags
        assert await api.count_images(all_tags=["abc", "aaa"]) == 1
        assert await api.get_image_ids(
            all_tags=["abc", "aaa"], order=("extension", "name")
        ) == [ajpg]
        images = await api.search_images(all_tags=["abc", "aaa"])
        assert [image.id for image in images] == [ajpg]

        assert await api.count_images(all_tags=["abc", "aaa", "bbb"]) == 0
        assert (
            await api.get_image_ids(
                all_tags=["abc", "aaa", "bbb"], order=("extension", "name")
            )
            == []
        )
        assert await api.search_images(all_tags=["abc", "aaa", "bbb"]) == []

        # no_tags
        assert await api.count_images(no_tags=["abc", "bbb"]) == 2
        assert await api.get_image_ids(
            no_tags=["abc", "bbb"], order=("extension", "name")
        ) == [bjpg, apng]
        images = await api.search_images(no_tags=["abc", "bbb"])
        assert [image.id for image in images] == [bjpg, apng]

        # any + no
        assert await api.count_images(any_tags=["aaa"], no_tags=["abc", "bbb"]) == 1
        assert await api.get_image_ids(
            any_tags=["aaa"], no_tags=["abc", "bbb"], order=("extension", "name")
        ) == [apng]
        images = await api.search_images(any_tags=["aaa"], no_tags=["abc", "bbb"])
        assert [image.id for image in images] == [apng]


@pytest.mark.asyncio
async def test_tags(load_api, tmp_path, image_files):
    async with load_api() as api:
        assert await api.all_tags() == {}

        # this should never fail
        tag = await api.get_tag("unknown/tag")
        assert tag.description is None
        assert tag.children == frozenset()

        await api.add_tag("string")
        await api.add_tag("list")

        # re-adding should add description
        await api.add_tag("list", description="a list")
        assert (await api.get_tag("list")).description == "a list"

        tag = await api.get_tag("list")
        assert tag.description == "a list"
        assert tag.children == frozenset()

        # updating description should update
        await api.add_tag("list", description="a tag passed as a list")
        assert (await api.get_tag("list")).description == "a tag passed as a list"

        # blank description shouldn't erase
        await api.add_tag("list")
        assert (await api.get_tag("list")).description == "a tag passed as a list"

        # none description should erase though
        await api.add_tag("list", description=None)
        assert (await api.get_tag("list")).description is None

        await api.add_tag("nested/tag", "a nested tag")
        await api.add_tag("nested/tag/further")
        await api.add_tag("nested/tag/much/much/further", "description 2")

        tag = await api.get_tag("nested/tag")
        assert tag.description == "a nested tag"
        assert tag.children == frozenset()

        tag = await api.get_tag("nested/tag", children=True)
        assert tag.description == "a nested tag"
        assert tag.children == {"further", "much"}

        for tag in ("", "/" "/a/b", "a/b/" "a//b"):
            with pytest.raises(ValueError):
                await api.add_tag(tag, "illegal tag name")

        assert await api.all_tags() == {
            "string": {"description": None, "children": {}},
            "list": {"description": None, "children": {}},
            "nested": {
                "description": None,
                "children": {
                    "tag": {
                        "description": "a nested tag",
                        "children": {
                            "further": {"description": None, "children": {}},
                            "much": {
                                "description": None,
                                "children": {
                                    "much": {
                                        "description": None,
                                        "children": {
                                            "further": {
                                                "description": "description 2",
                                                "children": {},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }

        location = await api.add_location("main", tmp_path, destination=True)
        shutil.copy2(image_files[0], tmp_path)
        [id] = await api.import_location(
            location,
            tags=[
                "nested/tag",
                "nested/tag/much/much/further",
                "string",
            ],
        )

        await api.remove_tag("string")
        assert await api.all_tags() == {
            "list": {"description": None, "children": {}},
            "nested": {
                "description": None,
                "children": {
                    "tag": {
                        "description": "a nested tag",
                        "children": {
                            "further": {"description": None, "children": {}},
                            "much": {
                                "description": None,
                                "children": {
                                    "much": {
                                        "description": None,
                                        "children": {
                                            "further": {
                                                "description": "description 2",
                                                "children": {},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        assert sorted(await api.all_tag_names()) == [
            "list",
            "nested/tag",
            "nested/tag/further",
            "nested/tag/much/much/further",
        ]
        assert sorted((await api.get_image(id, tags=True)).tags) == [
            "nested/tag",
            "nested/tag/much/much/further",
        ]

        # removing a tag should remove its children by default but it
        # should untag
        await api.remove_tag("nested/tag")
        assert await api.all_tags() == {
            "list": {"description": None, "children": {}},
            "nested": {
                "description": None,
                "children": {
                    "tag": {
                        "description": None,
                        "children": {
                            "further": {"description": None, "children": {}},
                            "much": {
                                "description": None,
                                "children": {
                                    "much": {
                                        "description": None,
                                        "children": {
                                            "further": {
                                                "description": "description 2",
                                                "children": {},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        assert (await api.get_image(id, tags=True)).tags == [
            "nested/tag/much/much/further",
        ]

        # cascade should cascade, don't need to pick a tag in the db
        await api.remove_tag("nested/tag/much", cascade=True)
        assert await api.all_tags() == {
            "list": {"description": None, "children": {}},
            "nested": {
                "description": None,
                "children": {
                    "tag": {
                        "description": None,
                        "children": {"further": {"description": None, "children": {}}},
                    },
                },
            },
        }
        assert (await api.get_image(id, tags=True)).tags == []


@pytest.mark.asyncio
async def test_move_tag(load_api, tmp_path, image_files):
    async with load_api() as api:
        # is this even the correct order for the greek alphabet?
        # write in and let me know
        await api.add_tag("alpha", "ɑ")
        await api.add_tag("alpha/beta", "β")
        await api.add_tag("alpha/beta/gamma", "ɣ")
        await api.add_tag("alpha/beta/gamma/delta", "δ")
        await api.add_tag("alpha/beta/gamma/delta/epsilon", "ε")

        await api.add_tag("alpha/bravo", "b")
        await api.add_tag("alpha/bravo/charlie", "c")
        await api.add_tag("alpha/bravo/charlie/delta", "d")
        await api.add_tag("alpha/bravo/charlie/delta/echo", "e")
        await api.add_tag("alpha/bravo/gamma/delta/echo", "E")

        # we want to make sure image tags are moved appropriately so we
        # need a location and images
        location = await api.add_location("location", tmp_path, destination=True)
        alpha = await api.add_image_copy(
            image_files[0], location, "alpha.jpg", tags=["alpha"]
        )
        beta = await api.add_image_copy(
            image_files[0], location, "beta.jpg", tags=["alpha/beta"]
        )
        gamma = await api.add_image_copy(
            image_files[0], location, "gamma.jpg", tags=["alpha/beta/gamma"]
        )
        delta = await api.add_image_copy(
            image_files[0], location, "delta.jpg", tags=["alpha/beta/gamma/delta"]
        )
        epsilon = await api.add_image_copy(
            image_files[0],
            location,
            "epsilon.jpg",
            tags=["alpha/beta/gamma/delta/epsilon"],
        )
        bravo = await api.add_image_copy(
            # beta too to test a later move doesn't break things
            image_files[0],
            location,
            "bravo.jpg",
            tags=["alpha/bravo", "alpha/beta"],
        )
        charlie = await api.add_image_copy(
            image_files[0], location, "charlie.jpg", tags=["alpha/bravo/charlie"]
        )
        delta2 = await api.add_image_copy(
            image_files[0], location, "delta2.jpg", tags=["alpha/bravo/charlie/delta"]
        )
        echo = await api.add_image_copy(
            image_files[0],
            location,
            "echo.jpg",
            tags=["alpha/bravo/charlie/delta/echo"],
        )

        assert 1 == await api.move_tag(
            "alpha/bravo/charlie", "alpha/beta/charlie", cascade=False
        )
        actual = await api.all_tags()
        expected = {
            "alpha": {
                "description": "ɑ",
                "children": {
                    "beta": {
                        "description": "β",
                        "children": {
                            "charlie": {"description": "c", "children": {}},
                            "gamma": {
                                "description": "ɣ",
                                "children": {
                                    "delta": {
                                        "description": "δ",
                                        "children": {
                                            "epsilon": {
                                                "description": "ε",
                                                "children": {},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                    "bravo": {
                        "description": "b",
                        "children": {
                            # our tag was moved but this is implicit because children
                            "charlie": {
                                "description": None,
                                "children": {
                                    "delta": {
                                        "description": "d",
                                        "children": {
                                            "echo": {"description": "e", "children": {}}
                                        },
                                    },
                                },
                            },
                            "gamma": {
                                "description": None,
                                "children": {
                                    "delta": {
                                        "description": None,
                                        "children": {
                                            "echo": {"description": "E", "children": {}}
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        check_tag_dict(actual, expected)
        assert (await api.get_image(alpha, tags=True)).tags == ["alpha"]
        assert (await api.get_image(beta, tags=True)).tags == ["alpha/beta"]
        assert (await api.get_image(gamma, tags=True)).tags == ["alpha/beta/gamma"]
        assert (await api.get_image(delta, tags=True)).tags == [
            "alpha/beta/gamma/delta"
        ]
        assert (await api.get_image(epsilon, tags=True)).tags == [
            "alpha/beta/gamma/delta/epsilon"
        ]
        assert (await api.get_image(bravo, tags=True)).tags == [
            "alpha/beta",
            "alpha/bravo",
        ]
        assert (await api.get_image(charlie, tags=True)).tags == ["alpha/beta/charlie"]
        assert (await api.get_image(delta2, tags=True)).tags == [
            "alpha/bravo/charlie/delta"
        ]
        assert (await api.get_image(echo, tags=True)).tags == [
            "alpha/bravo/charlie/delta/echo"
        ]

        assert 4 == await api.move_tag("alpha/bravo", "alpha/beta")
        actual = await api.all_tags()
        expected = {
            "alpha": {
                "description": "ɑ",
                "children": {
                    "beta": {
                        "description": "β",
                        "children": {
                            "charlie": {
                                "description": "c",
                                "children": {
                                    "delta": {
                                        "description": "d",
                                        "children": {
                                            "echo": {"description": "e", "children": {}}
                                        },
                                    },
                                },
                            },
                            "gamma": {
                                "description": "ɣ",
                                "children": {
                                    "delta": {
                                        "description": "δ",
                                        "children": {
                                            "echo": {
                                                "description": "E",
                                                "children": {},
                                            },
                                            "epsilon": {
                                                "description": "ε",
                                                "children": {},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        check_tag_dict(actual, expected)
        assert (await api.get_image(alpha, tags=True)).tags == ["alpha"]
        assert (await api.get_image(beta, tags=True)).tags == ["alpha/beta"]
        assert (await api.get_image(gamma, tags=True)).tags == ["alpha/beta/gamma"]
        assert (await api.get_image(delta, tags=True)).tags == [
            "alpha/beta/gamma/delta"
        ]
        assert (await api.get_image(epsilon, tags=True)).tags == [
            "alpha/beta/gamma/delta/epsilon"
        ]
        assert (await api.get_image(bravo, tags=True)).tags == ["alpha/beta"]
        assert (await api.get_image(charlie, tags=True)).tags == ["alpha/beta/charlie"]
        assert (await api.get_image(delta2, tags=True)).tags == [
            "alpha/beta/charlie/delta"
        ]
        assert (await api.get_image(echo, tags=True)).tags == [
            "alpha/beta/charlie/delta/echo"
        ]

        await api.remove_tag("alpha", cascade=True)

        # what if a new tag is also an old tag
        await api.add_tag("alpha", "a")
        await api.add_tag("alpha/bravo", "ab")
        await api.add_tag("alpha/bravo/alpha", "aba")
        await api.add_tag("alpha/bravo/alpha/bravo", "abab")
        await api.add_tag("alpha/bravo/alpha/bravo/alpha", "ababa")
        await api.add_tag("alpha/bravo/alpha/bravo/alpha/bravo", "ababab")
        await api.add_tag("alpha/bravo/alpha/bravo/alpha/bravo/charlie", "abababc")

        a = await api.add_image_copy(image_files[0], location, "a.jpg", tags=["alpha"])
        ab = await api.add_image_copy(
            image_files[0], location, "ab.jpg", tags=["alpha/bravo"]
        )
        aba = await api.add_image_copy(
            image_files[0], location, "aba.jpg", tags=["alpha/bravo/alpha"]
        )
        abab = await api.add_image_copy(
            image_files[0],
            location,
            "abab.jpg",
            tags=["alpha/bravo/alpha/bravo"],
        )
        ababa = await api.add_image_copy(
            image_files[0],
            location,
            "ababa.jpg",
            tags=["alpha/bravo/alpha/bravo/alpha"],
        )
        ababab = await api.add_image_copy(
            image_files[0],
            location,
            "ababab.jpg",
            tags=["alpha/bravo/alpha/bravo/alpha/bravo"],
        )
        abababc = await api.add_image_copy(
            image_files[0],
            location,
            "abababc.jpg",
            tags=["alpha/bravo/alpha/bravo/alpha/bravo/charlie"],
        )

        assert 5 == await api.move_tag("alpha/bravo/alpha", "alpha")
        actual = await api.all_tags()
        expected = {
            "alpha": {
                "description": "a",
                "children": {
                    "bravo": {
                        "description": "ab",
                        "children": {
                            "alpha": {
                                "description": "ababa",
                                "children": {
                                    "bravo": {
                                        "description": "ababab",
                                        "children": {
                                            "charlie": {
                                                "description": "abababc",
                                                "children": {},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        check_tag_dict(actual, expected)
        assert (await api.get_image(a, tags=True)).tags == ["alpha"]
        assert (await api.get_image(ab, tags=True)).tags == ["alpha/bravo"]
        assert (await api.get_image(aba, tags=True)).tags == ["alpha"]
        assert (await api.get_image(abab, tags=True)).tags == ["alpha/bravo"]
        assert (await api.get_image(ababa, tags=True)).tags == ["alpha/bravo/alpha"]
        assert (await api.get_image(ababab, tags=True)).tags == [
            "alpha/bravo/alpha/bravo"
        ]
        assert (await api.get_image(abababc, tags=True)).tags == [
            "alpha/bravo/alpha/bravo/charlie"
        ]

        # old tag is new tag the other way
        await api.remove_tag("alpha", cascade=True)

        await api.add_tag("a", "a")
        await api.add_tag("a/b", "ab")
        await api.add_tag("a/b/a", "aba")
        await api.add_tag("a/b/a/b", "abab")
        await api.add_tag("a/b/a/b/a", "ababa")
        await api.add_tag("a/b/a/b/a/b", "ababab")
        await api.add_tag("a/b/a/b/a/b/c", "abababc")

        a = await api.add_image_copy(image_files[0], location, "a.png", tags=["a"])
        ab = await api.add_image_copy(image_files[0], location, "ab.png", tags=["a/b"])
        aba = await api.add_image_copy(
            image_files[0], location, "aba.png", tags=["a/b/a"]
        )
        abab = await api.add_image_copy(
            image_files[0], location, "abab.png", tags=["a/b/a/b"]
        )
        ababa = await api.add_image_copy(
            image_files[0], location, "ababa.png", tags=["a/b/a/b/a"]
        )
        ababab = await api.add_image_copy(
            image_files[0], location, "ababab.png", tags=["a/b/a/b/a/b"]
        )
        abababc = await api.add_image_copy(
            image_files[0], location, "abababc.png", tags=["a/b/a/b/a/b/c"]
        )

        assert 7 == await api.move_tag("a", "a/b/a")
        actual = await api.all_tags()
        expected = {
            "a": {
                "description": None,
                "children": {
                    "b": {
                        "description": None,
                        "children": {
                            "a": {
                                "description": "a",
                                "children": {
                                    "b": {
                                        "description": "ab",
                                        "children": {
                                            "a": {
                                                "description": "aba",
                                                "children": {
                                                    "b": {
                                                        "description": "abab",
                                                        "children": {
                                                            "a": {
                                                                "description": "ababa",
                                                                "children": {
                                                                    "b": {
                                                                        "description": "ababab",  # noqa: E501
                                                                        "children": {
                                                                            "c": {
                                                                                "description": "abababc",  # noqa: E501
                                                                                "children": {},  # noqa: E501
                                                                            },
                                                                        },
                                                                    },
                                                                },
                                                            },
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        }
        check_tag_dict(actual, expected)
        assert (await api.get_image(a, tags=True)).tags == ["a/b/a"]
        assert (await api.get_image(ab, tags=True)).tags == ["a/b/a/b"]
        assert (await api.get_image(aba, tags=True)).tags == ["a/b/a/b/a"]
        assert (await api.get_image(abab, tags=True)).tags == ["a/b/a/b/a/b"]
        assert (await api.get_image(ababa, tags=True)).tags == ["a/b/a/b/a/b/a"]
        assert (await api.get_image(ababab, tags=True)).tags == ["a/b/a/b/a/b/a/b"]
        assert (await api.get_image(abababc, tags=True)).tags == ["a/b/a/b/a/b/a/b/c"]


@pytest.mark.asyncio
async def test_import_export(load_api, tmp_path, image_files):
    from picpocket import VERSION
    from picpocket.database import logic

    async with load_api() as api:
        await api.add_tag("dogs", "dogs are cool")
        await api.add_tag("tag", "a tag")
        await api.add_tag("tag/that/is/nested", "another tag")

        main = tmp_path / "main"
        main.mkdir()
        shutil.copy2(image_files[0], main / "a.jpg")
        shutil.copy2(image_files[1], main / "b.jpg")

        portable = tmp_path / "portable"
        portable.mkdir()
        (portable / "subdirectory").mkdir()
        shutil.copy2(image_files[0], portable / "a.jpg")
        shutil.copy2(image_files[1], portable / "subdirectory" / "b.jpg")

        main_id = await api.add_location(
            "main",
            main,
            description="main storage",
            source=True,
            destination=True,
            removable=False,
        )
        await api.import_location(main_id, creator="bcj", tags=["tag/that", "other"])
        ajpg = await api.find_image(main / "a.jpg")
        await api.edit_image(
            ajpg.id,
            caption="a description",
            title="Title",
            alt="alt text",
            rating=5,
        )

        portable_id = await api.add_location(
            "portable", destination=True, removable=True
        )
        await api.mount("portable", portable)
        await api.import_location("portable")
        await api.unmount("portable")

        await api.add_task(
            "my task",
            description="a task description",
            source="portable",
            destination="main",
            source_path="subdirectory/{year}/{month}",
            destination_format="from_portable/{file}",
            tags=["a", "b/c"],
        )
        await api.add_task(
            "reversed",
            source="main",
            destination="portable",
            source_path="directory",
            destination_format="from_main/{file}",
        )
        await api.add_task(
            "portable task",
            description="a task that only touches portable",
            source="portable",
            destination="portable",
            creator="bcj",
            file_formats=["bmp"],
        )

        path = tmp_path / "picpocket.json"
        await api.export_data(path)

        with path.open("r") as stream:
            exported = json.load(stream)

        assert exported.keys() == {"version", "tags", "locations", "tasks"}
        assert exported["version"] == VERSION.as_dict()
        assert exported["tags"] == {
            "dogs": "dogs are cool",
            "tag": "a tag",
            "tag/that/is/nested": "another tag",
        }
        assert exported["locations"].keys() == {"main", "portable"}

        info = exported["locations"]["main"]
        assert info.keys() == {
            "description",
            "path",
            "source",
            "destination",
            "removable",
            "images",
        }
        assert info["description"] == "main storage"
        assert info["path"] == str(main)
        assert info["source"]
        assert info["destination"]
        assert not info["removable"]
        assert len(info["images"]) == 2
        assert sorted(info["images"], key=lambda image: image["path"]) == [
            {
                "path": "a.jpg",
                "creator": "bcj",
                "caption": "a description",
                "title": "Title",
                "alt": "alt text",
                "rating": 5,
                "tags": ["other", "tag/that"],
            },
            {
                "path": "b.jpg",
                "creator": "bcj",
                "caption": None,
                "title": None,
                "alt": None,
                "rating": None,
                "tags": ["other", "tag/that"],
            },
        ]

        info = exported["locations"]["portable"]
        assert info.keys() == {
            "description",
            "path",
            "source",
            "destination",
            "removable",
            "images",
        }
        assert info["description"] is None
        assert info["path"] is None
        assert not info["source"]
        assert info["destination"]
        assert info["removable"]
        assert len(info["images"]) == 2
        assert sorted(info["images"], key=lambda image: image["path"]) == [
            {
                "path": "a.jpg",
                "creator": None,
                "caption": None,
                "title": None,
                "alt": None,
                "rating": None,
                "tags": [],
            },
            {
                "path": str(Path("subdirectory") / "b.jpg"),
                "creator": None,
                "caption": None,
                "title": None,
                "alt": None,
                "rating": None,
                "tags": [],
            },
        ]

        assert exported["tasks"].keys() == {"my task", "reversed", "portable task"}
        assert exported["tasks"]["my task"] == {
            "description": "a task description",
            "source": "portable",
            "destination": "main",
            "configuration": {
                "tags": ["a", "b/c"],
                "source": "subdirectory/{year}/{month}",
                "destination": "from_portable/{file}",
            },
        }
        assert exported["tasks"]["reversed"] == {
            "description": None,
            "source": "main",
            "destination": "portable",
            "configuration": {
                "source": "directory",
                "destination": "from_main/{file}",
            },
        }
        assert exported["tasks"]["portable task"] == {
            "description": "a task that only touches portable",
            "source": "portable",
            "destination": "portable",
            "configuration": {
                "creator": "bcj",
                "formats": [".bmp"],
            },
        }

        # only some locations
        del exported["locations"]["main"]
        del exported["tasks"]["my task"]
        del exported["tasks"]["reversed"]

        portable_only = tmp_path / "portable.json"
        await api.export_data(portable_only, locations=[portable_id])

        with portable_only.open("r") as stream:
            new_exported = json.load(stream)

        assert exported == new_exported

    # also force postgres to import into sqlite to check cross-db works
    # we're forcing sql to be last so that we can then export from
    # sqlite back into postgres
    for new_backend in sorted({os.environ["PICPOCKET_BACKEND"], "sqlite"}):
        async with load_api(backend=new_backend) as api:
            await api.import_data(path)

            await api.all_tags() == {
                "dogs": {"description": "dogs are cool", "children": {}},
                "other": {"description": None, "children": {}},
                "tag": {
                    "description": "a tag",
                    "children": {
                        "that": {
                            "description": None,
                            "children": {
                                "is": {
                                    "description": None,
                                    "children": {
                                        "nested": {
                                            "description": "another tag",
                                            "children": {},
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            }

            main = await api.get_location("main")
            assert main
            assert main.name == "main"
            assert main.path == tmp_path / "main"
            assert main.description == "main storage"
            assert main.source
            assert main.destination
            assert not main.removable

            assert (
                await api.count_images(
                    logic.Number("location", logic.Comparator.EQUALS, main.id)
                )
                == 2
            )

            ajpg = await api.find_image(main.path / "a.jpg", tags=True)
            assert ajpg is not None
            assert ajpg.creator == "bcj"
            assert ajpg.caption == "a description"
            assert ajpg.title == "Title"
            assert ajpg.alt == "alt text"
            assert ajpg.rating == 5
            assert sorted(ajpg.tags) == ["other", "tag/that"]

            bjpg = await api.find_image(main.path / "b.jpg", tags=True)
            assert bjpg is not None
            assert bjpg.creator == "bcj"
            assert bjpg.caption is None
            assert bjpg.title is None
            assert bjpg.alt is None
            assert bjpg.rating is None
            assert sorted(bjpg.tags) == ["other", "tag/that"]

            portable = await api.get_location("portable")
            assert portable
            assert portable.name == "portable"
            assert portable.path is None
            assert portable.description is None
            assert not portable.source
            assert portable.destination
            assert portable.removable

            # path wasn't supplied so how would it know?
            assert (
                await api.count_images(
                    logic.Number("location", logic.Comparator.EQUALS, portable.id)
                )
                == 0
            )

            task = await api.get_task("my task")
            assert task is not None
            assert task.source == portable.id
            assert task.destination == main.id
            assert task.description == "a task description"
            assert task.configuration == {
                "source": "subdirectory/{year}/{month}",
                "destination": "from_portable/{file}",
                "tags": ["a", "b/c"],
            }

            task = await api.get_task("reversed")
            assert task is not None
            assert task.source == main.id
            assert task.destination == portable.id
            assert task.description is None
            assert task.configuration == {
                "source": "directory",
                "destination": "from_main/{file}",
            }

            task = await api.get_task("portable task")
            assert task is not None
            assert task.source == portable.id
            assert task.destination == portable.id
            assert task.description == "a task that only touches portable"
            assert task.configuration == {
                "creator": "bcj",
                "formats": [".bmp"],
            }

            # re-import with path should:
            # * import locations, not break on a None path
            await api.remove_image(bjpg.id)
            # we expect our mount to override this
            (tmp_path / "fake-location").mkdir(exist_ok=True)
            await api.mount(portable.id, tmp_path / "fake-location")
            await api.import_data(
                path, {"main": None, "portable": tmp_path / "portable"}
            )

            # bjpg should be readded
            assert (
                await api.count_images(
                    logic.Number("location", logic.Comparator.EQUALS, main.id)
                )
                == 2
            )

            bjpg = await api.find_image(main.path / "b.jpg", tags=True)
            assert bjpg is not None
            assert bjpg.creator == "bcj"
            assert bjpg.caption is None
            assert bjpg.title is None
            assert bjpg.alt is None
            assert bjpg.rating is None
            assert sorted(bjpg.tags) == ["other", "tag/that"]

            # path should have merely been mounted
            portable = await api.get_location("portable")
            assert portable.path is None
            # mounts should be back to pre-run condition
            assert api.mounts == {portable.id: tmp_path / "fake-location"}

            assert (
                await api.count_images(
                    logic.Number("location", logic.Comparator.EQUALS, portable.id)
                )
                == 2
            )

            await api.mount(portable.id, tmp_path / "portable")
            ajpg = await api.find_image(tmp_path / "portable" / "a.jpg", tags=True)
            assert ajpg is not None
            assert ajpg.creator is None
            assert ajpg.caption is None
            assert ajpg.title is None
            assert ajpg.alt is None
            assert ajpg.rating is None
            assert ajpg.tags == []

            bjpg = await api.find_image(
                tmp_path / "portable" / "subdirectory" / "b.jpg", tags=True
            )
            assert bjpg is not None
            assert bjpg.creator is None
            assert bjpg.caption is None
            assert bjpg.title is None
            assert bjpg.alt is None
            assert bjpg.rating is None
            assert bjpg.tags == []

            await api.export_data(path)

    async with load_api() as api:
        # path mismatches
        # different path
        (tmp_path / "fake-main").mkdir()
        main_id = await api.add_location("main", tmp_path / "fake-main", source=True)

        with pytest.raises(ValueError):
            await api.import_data(path, locations=["main"])

        assert len(await api.list_locations()) == 1
        main = await api.get_location("main")
        assert main
        assert main.name == "main"
        assert main.path == tmp_path / "fake-main"
        assert main.description is None
        assert main.source
        assert not main.destination
        assert main.removable

        # missing path
        await api.edit_location("main", path=None)

        with pytest.raises(ValueError):
            await api.import_data(path, locations=["main"])

        assert len(await api.list_locations()) == 1
        main = await api.get_location("main")
        assert main
        assert main.name == "main"
        assert main.path is None
        assert main.description is None
        assert main.source
        assert not main.destination
        assert main.removable

        # expected missing path
        await api.remove_location(main_id)
        portable_id = await api.add_location("portable", tmp_path, source=True)

        with pytest.raises(ValueError):
            await api.import_data(path, locations=["portable"])

        assert len(await api.list_locations()) == 1
        portable = await api.get_location("portable")
        assert portable
        assert portable.name == "portable"
        assert portable.path == tmp_path
        assert portable.description is None
        assert portable.source
        assert not portable.destination
        assert portable.removable

        # only portable should be imported and location shouldn't be overwritten
        await api.edit_location(
            portable.id, path=None, description="a", removable=False
        )
        await api.import_data(path, {"portable": tmp_path / "portable"})
        assert api.mounts == {}
        portable = await api.get_location("portable")
        assert portable
        assert portable.name == "portable"
        assert portable.path is None
        assert portable.description == "a"
        assert portable.source
        assert not portable.destination
        assert not portable.removable
        assert await api.count_images() == 2

    async with load_api() as api:
        with path.open("r") as stream:
            data = json.load(stream)

        data["version"]["major"] += 1

        with path.open("w") as stream:
            json.dump(data, stream)

        with pytest.raises(ValueError):
            await api.import_data(path)

        assert await api.all_tags() == {}
        assert len(await api.list_locations()) == 0

        # error on restricting export on an unknown location
        path = tmp_path / "totally-new-file.json"
        with pytest.raises(ValueError):
            await api.export_data(path, locations=["this is a fake location"])
        assert not path.is_file()


@pytest.mark.asyncio
async def test_session(load_api):
    async with load_api() as api:
        data = {"a": 1, "b": ["a", True, None, {}]}

        id = await api.create_session(data)

        assert await api.get_session(id) == data

        # if you set the default expiry to less than a second you deserve
        # for this test to fail
        await api.prune_sessions()
        assert await api.get_session(id) == data

        # missing data
        assert await api.get_session(id + 1) is None

        # fixed expiration (it should be fine it's already expired [probably])
        data2 = {"new": "data", "wow": False}

        new_id = await api.create_session(
            data2,
            expires=datetime.utcnow().astimezone(timezone.utc) - timedelta(hours=1),
        )
        assert new_id != id

        assert await api.get_session(id) == data
        assert await api.get_session(new_id) == data2

        # pruning should remove expired session
        await api.prune_sessions()

        assert await api.get_session(id) == data
        assert await api.get_session(new_id) is None
