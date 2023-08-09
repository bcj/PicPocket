"""Tests for the web interface"""
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pytest
import requests
from bs4 import BeautifulSoup


def parse_endpoints(contents: str) -> dict[str, str]:
    """pull endpoints from a PicPocket page"""

    endpoints = {}
    name = None
    parent = BeautifulSoup(contents, "html.parser").find(id="endpoints")
    if parent:
        for child in parent.children:
            if isinstance(child, str):
                continue

            if name is None:
                assert child.name == "dt"
                link = child.contents[0]
                assert link.name == "a"
                path = link["href"]
                assert link.text
                name = link.text
                endpoints[name] = path
            else:
                name = None
                assert child.name == "dd"
                assert child.text

    assert name is None

    return endpoints


def parse_actions(contents: str) -> dict[str, str]:
    """pull actions from a PicPocket page"""

    endpoints = {}
    parent = BeautifulSoup(contents, "html.parser").find(id="action")
    if parent:
        for child in parent.find_all(name="option"):
            endpoints[child.text] = child["value"]

    return endpoints


def parse_form(contents: str) -> dict[str, dict[str, Any]]:
    inputs = {}
    soup = BeautifulSoup(contents, "html.parser")
    for tag in soup.find("form").find_all(["input", "textarea", "select"]):
        if tag.get("name") in inputs:
            raise ValueError(f"Duplicate tag name: {tag}")

        if tag.name == "input":
            if tag["type"] == "submit":
                continue
            elif tag["type"] == "checkbox":
                value = tag.get("checked") is not None
            elif tag["type"] == "number":
                value = tag.get("value") or None
                if value:
                    value = int(value)
            else:
                value = tag.get("value") or None

            inputs[tag["name"]] = {"value": value, "type": tag["type"]}
        elif tag.name == "textarea":
            inputs[tag["name"]] = {"value": tag.text or None, "type": "textarea"}
        else:
            selected = None
            options = []
            for option in tag.find_all("option"):
                if option.get("selected") is not None:
                    selected = option["value"]
                options.append(option["value"])

            inputs[tag["name"]] = {
                "value": selected,
                "options": options,
                "type": "select",
            }

    return inputs


def parse_locations(contents: str) -> list[dict[str, Any]]:
    """pull locations from a PicPocket page"""
    locations = []
    for div in BeautifulSoup(contents, "html.parser").find_all(class_="location-info"):
        location = {}
        for child in div.children:
            if isinstance(child, str):
                continue

            if child.name in ("h1", "h2", "h23"):
                assert "name" not in location
                location["name"] = child.text
            elif child.name == "p":
                assert "description" not in location
                location["description"] = child.text
            elif child.name == "dl":
                title = None
                for item in child.children:
                    if isinstance(item, str):
                        continue

                    if title is None:
                        assert item.name == "dt"
                        title = item.text
                    else:
                        assert item.name == "dd"
                        match title:
                            case "Id:":
                                location["id"] = int(item.text)
                            case "Path:":
                                location["path"] = Path(item.text)
                            case "Mount Point:":
                                location["mount"] = Path(item.text)
                            case "Type:":
                                location["source"] = item.text == "Source"
                                location["destination"] = item.text == "Destination"
                            case "Removable:":
                                assert item.text in ("yes", "no")
                                location["removable"] = item.text == "yes"
                            case _:
                                raise ValueError(f"Unexpected attribute: {title}")

                        title = None

                assert title is None
                locations.append(location)

    return locations


def parse_image_results(contents: str) -> tuple[int, Optional[dict[str, Any]]]:
    """get information from an images page"""

    soup = BeautifulSoup(contents, "html.parser")

    count = int(soup.find("h1").text.split(" ", 1)[0])
    image = parse_image(soup) if count else None

    return count, image


def parse_all_images(contents: str, url_base: str) -> dict[int, dict[str, any]]:
    images = {}

    soup = BeautifulSoup(contents, "html.parser")
    if soup.find("article") is None and soup.find("h1").text.startswith("0 "):
        return images

    while contents:
        image = parse_image(contents)
        contents = None
        images[image["id"]] = image

        if "next" in image:
            response = requests.get(f"{url_base}{image['next']}")
            assert response.status_code == 200
            contents = response.text

    return images


def parse_image(soup: str | BeautifulSoup) -> dict[str, Any]:
    """pull image info from a PicPocket page"""
    if isinstance(soup, str):
        soup = BeautifulSoup(soup, "html.parser")

    image = {}

    image["title"] = (soup.find("h2") or soup.find("h1")).text
    tag = soup.find(class_="image-holder")
    img = tag.find("img")
    if img:
        image["image"] = img["src"]
        if img.get("alt"):
            image["alt"] = img["alt"]
    else:
        source = tag.find("video").find("source")
        image["video"] = source["src"]

    p = tag.find("p")
    if p:
        image["caption"] = p.text

    div = soup.find(class_="image-info")
    actions = div.find(class_="actions")
    image["actions"] = {}
    for link in actions.find_all("a"):
        if "previous" in link.text.lower():
            image["previous"] = link["href"]
        elif "next" in link.text.lower():
            image["next"] = link["href"]
        else:
            image["actions"][link.text] = link["href"]

    name = None
    found = set()
    dl = div.find("dl")
    for tag in dl.children:
        if isinstance(tag, str):
            continue

        if tag.name == "dt":
            if name:
                raise ValueError(f"missing value for {name}")
            elif tag.name in found:
                raise ValueError(f"Duplicate key {name}")
            name = tag.text
            found.add(name)
        else:
            if not name:
                raise ValueError(f"missing key for {tag.text}")

            match name:
                case "Id:":
                    image["id"] = int(tag.text)
                case "Path:":
                    if ": " in tag.text:
                        found.add("Location: ")
                        location, pathstr = tag.text.split(": ")
                        image["location"] = location
                        image["path"] = Path(pathstr)
                    else:
                        image["full_path"] = Path(tag.text)
                case "Location:":
                    image["location"] = tag.text
                case "Creator:":
                    image["creator"] = tag.text
                case "Creation Date:":
                    image["creation_date"] = tag.text
                case "Last-Modified Date:":
                    image["last_modified"] = tag.text
                case "Rating:":
                    image["rating"] = int(tag.text)
                case "Dimensions:":
                    image["dimensions"] = tuple(map(int, tag.text.split("x")))
                case "Tags:":
                    image["tags"] = {}
                    for link in tag.find_all("a"):
                        image["tags"][link.text] = link["href"]
                case _:
                    raise ValueError(f"Unknown attribute: {name}")
            name = None
    assert name is None

    table = soup.find("table")
    if table:
        image["exif"] = {}
        key = None
        for column in table.find_all("td"):
            if key is None:
                key = column.text
            else:
                image["exif"][key] = column.text
                key = None
        assert key is None

    return image


def parse_tag(contents: str) -> dict[str, Any]:
    """get information from a tag"""

    tag = {"description": None, "children": {}, "actions": {}}

    soup = BeautifulSoup(contents, "html.parser")

    tag["name"] = soup.find("h1").text

    p = soup.find("p")
    if p:
        tag["description"] = p.text

    for item in soup.find_all("li"):
        link = item.find("a")
        tag["children"][link.text] = link["href"]

    for link in soup.find_all("a", class_="action-link"):
        tag["actions"][link.text] = link["href"]

    return tag


def parse_tasks(contents: str) -> list[dict[str, Any]]:
    """pull locations from a PicPocket page"""
    tasks = []
    for div in BeautifulSoup(contents, "html.parser").find_all(class_="task-info"):
        task = {}
        for child in div.children:
            if isinstance(child, str):
                continue

            if child.name in ("h1", "h2", "h23"):
                assert "name" not in task
                task["name"] = child.text
            elif child.name == "p":
                assert "description" not in task
                task["description"] = child.text
            elif child.name == "div":
                assert "actions" in child["class"]
                task["actions"] = {}
                for link in child.find_all("a"):
                    task["actions"][link.text] = link["href"]
            elif child.name == "dl":
                title = None
                for item in child.children:
                    if isinstance(item, str):
                        continue

                    if title is None:
                        assert item.name == "dt"
                        title = item.text
                    else:
                        assert item.name == "dd"
                        assert title not in task
                        match title:
                            case "Last Ran:":
                                task["last-ran"] = item.text
                            case "Source:":
                                task["source"] = item.text
                            case "Destination:":
                                task["destination"] = item.text
                            case "Configuration:":
                                configuration = {}
                                config_title = None
                                for tag in item.find("dl").find_all(["dt", "dd"]):
                                    if config_title is None:
                                        assert tag.name == "dt"
                                        config_title = tag.text
                                    else:
                                        assert config_title
                                        assert config_title not in configuration
                                        if config_title in ("tags", "formats"):
                                            value = []
                                            for item in tag.find_all("li"):
                                                try:
                                                    # this still could be tricked but
                                                    # this is just for testing
                                                    value.append(json.loads(item.text))
                                                except Exception:
                                                    value.append(item.text)
                                        else:
                                            value = tag.text.strip()
                                        configuration[config_title] = value
                                        config_title = None
                                task["configuration"] = configuration
                            case _:
                                raise ValueError(f"Unexpected attribute: {title}")

                        title = None

                assert title is None
                tasks.append(task)

    return tasks


@pytest.mark.asyncio
async def test_root(run_web):
    async with run_web() as port:
        base = f"http://localhost:{port}"

        for url in (base, f"{base}/"):
            response = requests.get(url, allow_redirects=False)
            assert response.status_code == 302


@pytest.mark.asyncio
async def test_api_root(run_web):
    async with run_web() as port:
        base = f"http://localhost:{port}"

        response = requests.get(f"{base}")
        assert response.status_code == 200
        endpoints = parse_endpoints(response.text)

        assert endpoints.keys() == {"locations", "tasks", "images", "tags"}
        assert BeautifulSoup(response.text, "html.parser").find(id="actions") is None


@pytest.mark.asyncio
async def test_locations(run_web, tmp_path, image_files, test_images):
    async with run_web() as port:
        base = f"http://localhost:{port}"

        response = requests.get(base)
        assert response.status_code == 200
        endpoints = parse_endpoints(response.text)

        assert "locations" in endpoints
        response = requests.get(f"{base}{endpoints['locations']}")
        assert response.status_code == 200

        endpoints = parse_endpoints(response.text)
        assert endpoints.keys() == {"add", "list"}

        actions = parse_actions(response.text)
        assert actions.keys() == {"get", "mount", "unmount", "import", "edit", "remove"}

        # add
        main = tmp_path / "main"
        main.mkdir()

        response = requests.post(
            f"{base}{endpoints['add']}",
            data={
                "name": "main",
                "path": str(main),
                "description": "my main image storage",
                "type": "Destination",
            },
            allow_redirects=False,
        )
        assert response.status_code == 302
        main_id = int(response.headers["Location"].rsplit("/", 1)[-1])
        response = requests.get(f"{base}{response.headers['Location']}")
        assert response.status_code == 200

        locations = parse_locations(response.text)
        assert len(locations) == 1
        assert locations[0] == {
            "name": "main",
            "id": main_id,
            "description": "my main image storage",
            "path": main,
            "source": False,
            "destination": True,
            "removable": False,
        }
        main_info = locations[0]

        minimal = tmp_path / "minimal"
        minimal.mkdir()

        response = requests.post(
            f"{base}{endpoints['add']}",
            data={
                "name": "minimal",
                "path": str(minimal),
                "type": "Source",
            },
        )
        assert response.status_code == 200

        locations = parse_locations(response.text)
        assert len(locations) == 1
        minimal_id = int(response.url.rsplit("/", 1)[-1])
        assert locations[0] == {
            "name": "minimal",
            "id": minimal_id,
            "path": minimal,
            "source": True,
            "destination": False,
            "removable": False,
        }
        minimal_info = locations[0]

        response = requests.get(f"{base}{endpoints['list']}")
        assert response.status_code == 200
        locations = parse_locations(response.text)

        assert locations in ([main_info, minimal_info], [minimal_info, main_info])

        # edit
        response = requests.get(f"{base}{actions['edit'].format(id=main_id)}")
        response.status_code == "200"

        inputs = parse_form(response.text)

        assert inputs == {
            "new_name": {"type": "text", "value": "main"},
            "description": {"type": "textarea", "value": "my main image storage"},
            "path": {"type": "text", "value": str(main)},
            "type": {
                "type": "select",
                "value": "Destination",
                "options": ["Source", "Destination"],
            },
            "removable": {"type": "checkbox", "value": False},
        }

        # we need to pass all values. form preloads current values
        response = requests.post(
            f"{base}{actions['edit'].format(id=main_id)}",
            data={
                "new_name": "pictures",
                "description": "my pictures",
                "path": str(main),
                "type": "Destination",
                "removable": "on",
            },
        )
        assert response.status_code == 200
        assert response.url == f"{base}{actions['get'].format(id=main_id)}"
        locations = parse_locations(response.text)
        assert len(locations) == 1
        assert locations[0] == {
            "id": main_id,
            "name": "pictures",
            "description": "my pictures",
            "path": main,
            "source": False,
            "destination": True,
            "removable": True,
        }
        main_info = locations[0]

        # mount
        main2 = tmp_path / "main2"
        main2.mkdir()
        response = requests.post(
            f"{base}{actions['mount'].format(id=main_id)}",
            data={"path": str(main2)},
        )
        assert response.status_code == 200
        assert response.url == f"{base}{actions['get'].format(id=main_id)}"
        locations = parse_locations(response.text)
        assert len(locations) == 1
        assert locations[0] == {
            "id": main_id,
            "name": "pictures",
            "description": "my pictures",
            "path": main,
            "mount": main2,
            "source": False,
            "destination": True,
            "removable": True,
        }
        new_main = locations[0]
        response = requests.get(f"{base}{actions['get'].format(id=main_id)}")
        assert response.status_code == 200
        locations = parse_locations(response.text)
        assert len(locations) == 1
        assert locations[0] == new_main

        # unmount
        response = requests.post(f"{base}{actions['unmount'].format(id=main_id)}")
        assert response.status_code == 200
        assert response.url == f"{base}{actions['get'].format(id=main_id)}"
        locations = parse_locations(response.text)
        assert len(locations) == 1
        assert locations[0] == main_info
        new_main = locations[0]
        response = requests.get(f"{base}{actions['get'].format(id=main_id)}")
        assert response.status_code == 200
        locations = parse_locations(response.text)
        assert len(locations) == 1
        assert locations[0] == main_info

        # remove
        response = requests.post(f"{base}{actions['remove'].format(id=minimal_id)}")
        assert response.status_code == 200

        response = requests.get(f"{base}{actions['get'].format(id=minimal_id)}")
        assert response.status_code == 404

        # import
        for path in image_files:
            shutil.copy2(path, main)

        response = requests.post(
            f"{base}{actions['import'].format(id=main_id)}",
            {
                "batch_size": 100,
                "file_formats": "",
                "creator": "bcj",
                "tags": "tag\nnested/tag\nnested/too\n\n",
            },
        )
        assert response.status_code == 200
        count, _ = parse_image_results(response.text)

        assert count == len(image_files)


@pytest.mark.asyncio
async def test_images(run_web, tmp_path, image_files, test_images):
    from picpocket.images import image_info, mime_type

    async with run_web() as port:
        base = f"http://localhost:{port}"

        response = requests.get(base)
        assert response.status_code == 200
        root_endpoints = parse_endpoints(response.text)

        assert "images" in root_endpoints
        response = requests.get(f"{base}{root_endpoints['images']}")
        assert response.status_code == 200

        endpoints = parse_endpoints(response.text)
        assert endpoints.keys() == {"search", "find", "upload", "verify"}

        actions = parse_actions(response.text)
        assert actions.keys() == {"edit", "file", "get", "move", "remove"}

        # setup images
        main = tmp_path / "main"
        main.mkdir()

        other = tmp_path / "other"
        other.mkdir()

        response = requests.get(f"{base}{root_endpoints['locations']}")
        assert response.status_code == 200
        location_endpoints = parse_endpoints(response.text)
        location_actions = parse_actions(response.text)

        response = requests.post(
            f"{base}{location_endpoints['add']}",
            data={
                "name": "main",
                "path": str(main),
                "description": "my main image storage",
                "type": "Destination",
            },
            allow_redirects=False,
        )
        assert response.status_code == 302
        main_id = int(response.headers["Location"].rsplit("/", 1)[-1])

        response = requests.post(
            f"{base}{location_endpoints['add']}",
            data={
                "name": "other",
                "path": str(other),
                "type": "Destination",
            },
            allow_redirects=False,
        )
        assert response.status_code == 302

        for path in image_files:
            shutil.copy2(path, main)

        response = requests.post(
            f"{base}{location_actions['import'].format(id=main_id)}",
            {
                "batch_size": 100,
                "file_formats": "",
                "creator": "bcj",
                "tags": ["tag", "nested/tag", "nested/too"],
            },
        )
        assert response.status_code == 200
        count, image = parse_image_results(response.text)

        names = set()
        index = 0
        while image:
            guaranteed_keys = {
                "actions",
                "creation_date",
                "creator",
                "dimensions",
                "full_path",
                "id",
                "image",
                "last_modified",
                "location",
                "tags",
                "title",  # will be the default one
            }
            for key in guaranteed_keys:
                assert key in image

            assert image["title"] == f"Image {image['id']}"
            assert image["full_path"].parent == main
            names.add(image["full_path"].name)
            assert image["location"] == "main"
            assert image["creator"] == "bcj"
            datetime.strptime(image["creation_date"], "%Y-%m-%d %H:%M:%S")
            datetime.strptime(image["last_modified"], "%Y-%m-%d %H:%M:%S")
            assert len(image["dimensions"]) == 2
            assert isinstance(image["dimensions"][0], int)
            assert isinstance(image["dimensions"][1], int)
            assert image["tags"].keys() == {"tag", "nested/tag", "nested/too"}
            names.add(image["full_path"].name)

            *_, exif = image_info(test_images / image["full_path"].name)
            if exif:
                assert image["exif"]

                if "ImageDescription" in exif:
                    assert "ImageDescription" in image["exif"]
                    assert image["caption"]
                else:
                    assert "caption" not in image
            else:
                assert "exif" not in image
                assert "caption" not in image

            assert image["image"] == actions["file"].format(id=image["id"])
            response = requests.get(f"{base}{image['image']}")
            assert response.status_code == 200
            path = image["full_path"]
            assert response.headers["content-type"] == mime_type(path)
            assert response.content == path.read_bytes()

            if index > 0:
                assert "previous" in image

            if (index + 1) < count:
                assert "next" in image

            assert image["actions"].keys() == {"Edit", "Move", "Remove"}

            if index == 1:  # we only need to test this once
                image1 = image

            if image.get("next"):
                response = requests.get(f"{base}{image['next']}")
                assert response.status_code == 200
                image = parse_image(response.text)
            else:
                image = None

            index += 1

        assert len(names) == count

        # edit
        url = f"{base}{image1['actions']['Edit']}"
        response = requests.get(url)
        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")
        assert soup.find("img") is not None
        inputs = parse_form(response.text)

        assert inputs.keys() == {
            "alt",
            "caption",
            "creator",
            "existing-tags",
            "rating",
            "tags-list",
            "title",
        }
        assert inputs["alt"] == {"type": "text", "value": None}
        assert inputs["caption"] == {"type": "text", "value": None}
        assert inputs["creator"] == {"type": "text", "value": "bcj"}
        assert inputs["existing-tags"]["type"] == "text"
        assert set(inputs["tags-list"]["value"].splitlines()) == {
            "tag",
            "nested/tag",
            "nested/too",
        }
        assert set(json.loads(inputs["existing-tags"]["value"])) == {
            "tag",
            "nested/tag",
            "nested/too",
        }
        assert inputs["rating"] == {"type": "number", "value": None}
        assert inputs["title"] == {"type": "text", "value": None}

        response = requests.post(
            url,
            {
                "alt": "a description of the image",
                "caption": "a pithy description",
                "title": "My good image",
                "existing-tags": inputs["existing-tags"]["value"],
                "tags-list": "new\nnested/tag\nalso/new",
                "rating": 5,
                "creator": "me",
            },
        )
        assert response.status_code == 200
        new_image = parse_image(response.text)

        assert new_image.keys() == {
            "actions",
            "alt",
            "caption",
            "creation_date",
            "creator",
            "dimensions",
            "full_path",
            "id",
            "image",
            "last_modified",
            "location",
            "next",
            "previous",
            "rating",
            "tags",
            "title",
        }

        for key in (
            "actions",
            "creation_date",
            "dimensions",
            "full_path",
            "id",
            "image",
            "last_modified",
            "location",
            "next",
            "previous",
        ):
            assert image1[key] == new_image[key]

        assert new_image["alt"] == "a description of the image"
        assert new_image["caption"] == "a pithy description"
        assert new_image["title"] == "My good image"
        assert new_image["rating"] == 5
        assert new_image["creator"] == "me"
        assert new_image["tags"].keys() == {"nested/tag", "new", "also/new"}

        url = f"{base}{new_image['actions']['Move']}"
        response = requests.get(url)

        assert response.status_code == 200
        inputs = parse_form(response.text)

        assert inputs.keys() == {"path", "location"}
        assert inputs["path"]["type"] == "text"
        assert main / inputs["path"]["value"] == image1["full_path"]
        assert inputs["location"] == {
            "type": "select",
            "value": "main",
            "options": ["main", "other"],
        }

        name = new_image["full_path"].name
        moved_path = other / "my" / "new" / name
        response = requests.post(url, {"path": f"my/new/{name}", "location": "other"})
        assert response.status_code == 200
        moved_image = parse_image(response.text)
        assert moved_image.keys() == new_image.keys()
        for key, value in moved_image.items():
            if key == "location":
                assert value == "other"
            elif key == "full_path":
                assert value == moved_path
            else:
                assert value == new_image[key]
        assert not new_image["full_path"].exists()
        assert moved_path.exists()

        # find
        image = moved_image

        response = requests.get(f"{base}{endpoints['find']}")
        assert response.status_code == 200
        inputs = parse_form(response.text)
        assert inputs == {"path": {"type": "text", "value": None}}

        response = requests.post(
            f"{base}{endpoints['find']}", {"path": str(image["full_path"])}
        )
        assert response.status_code == 200
        assert parse_image(response.text)["id"] == image["id"]

        # deleting images
        response = requests.get(f"{base}{image['actions']['Remove']}")
        assert response.status_code == 200
        inputs = parse_form(response.text)

        assert inputs == {"delete": {"type": "checkbox", "value": False}}

        response = requests.post(
            f"{base}{image['actions']['Remove']}", {"delete": "on"}
        )
        assert response.status_code == 200
        assert not image["full_path"].exists()
        assert (
            requests.get(f"{base}{actions['get'].format(id=image['id'])}").status_code
            == 404
        )
        deleted = {image["full_path"].name}

        assert (
            requests.post(
                f"{base}{endpoints['find']}", {"path": str(image["full_path"])}
            ).status_code
            == 404
        )

        while "previous" in image or "next" in image:
            image = parse_image(response.text)
            response = requests.post(f"{base}{image['actions']['Remove']}")
            assert response.status_code == 200
            assert image["full_path"].exists()
            deleted.add(image["full_path"].name)
            assert (
                requests.get(
                    f"{base}{actions['get'].format(id=image['id'])}"
                ).status_code
                == 404
            )

        assert names == deleted

        # reimport files so we can test verify
        response = requests.post(
            f"{base}{location_actions['import'].format(id=main_id)}",
            {
                "batch_size": 100,
                "file_formats": "",
                "creator": "bcj",
                "tags": "tag\nnested/tag\nnested/too\n\n",
            },
        )
        assert response.status_code == 200
        path1, path2 = list(main.iterdir())[:2]
        response = requests.post(f"{base}{endpoints['find']}", {"path": str(path1)})
        assert response.status_code == 200
        parse_image(response.text)["id"]
        response = requests.post(f"{base}{endpoints['find']}", {"path": str(path2)})
        assert response.status_code == 200
        image_id2 = parse_image(response.text)["id"]

        path2 = main / "subdirectory" / path2.name
        response = requests.post(
            f"{base}{actions['move'].format(id=image_id2)}",
            {"path": f"subdirectory/{path2.name}", "location": "main"},
        )
        assert response.status_code == 200

        response = requests.get(f"{base}{endpoints['verify']}")
        assert response.status_code == 200
        inputs = parse_form(response.text)

        assert inputs == {
            "path": {"type": "text", "value": None},
            "location": {
                "type": "select",
                "value": None,
                "options": ["", "main", "other"],
            },
            "exif": {"type": "checkbox", "value": False},
        }

        response = requests.post(f"{base}{endpoints['verify']}")
        assert response.status_code == 200
        assert parse_image_results(response.text) == (0, None)

        path1.unlink()
        path2.unlink()

        response = requests.post(
            f"{base}{endpoints['verify']}",
            {"path": main / "subdirectory"},
        )
        assert response.status_code == 200
        count, image = parse_image_results(response.text)
        assert count == 1
        assert image["id"] == image_id2

        response = requests.post(
            f"{base}{endpoints['verify']}",
            {"location": "other"},
        )
        assert response.status_code == 200
        assert parse_image_results(response.text) == (0, None)

        response = requests.post(
            f"{base}{endpoints['verify']}",
            {"location": "main"},
        )
        assert response.status_code == 200
        count, image = parse_image_results(response.text)

        assert count == 2

        # upload
        response = requests.get(f"{base}{endpoints['upload']}")
        assert response.status_code == 200
        inputs = parse_form(response.text)

        assert inputs == {
            "alt": {"type": "text", "value": None},
            "caption": {"type": "text", "value": None},
            "creator": {"type": "text", "value": None},
            "file": {"type": "file", "value": None},
            "location": {
                "type": "select",
                "value": None,
                "options": ["main", "other"],
            },
            "path": {"type": "text", "value": None},
            "rating": {"type": "number", "value": None},
            "tags-list": {"type": "textarea", "value": None},
            "title": {"type": "text", "value": None},
        }

        files = {}
        for destination in (
            "123.abc",
            "456.abc",
            "123.xyz",
            "789.xyz",
        ):
            title = f"title {destination.split('.', 1)[0]}"
            caption = None if destination.startswith("123") else "pithy description"
            response = requests.post(
                f"{base}{endpoints['upload']}",
                {
                    "location": "other",
                    "path": destination,
                    "creator": "bcj",
                    "title": title,
                    "alt": "my description",
                    "caption": caption,
                    "rating": 3,
                    "tags": ["tag/1", "tag/2", "three"],
                },
                files={"file": image_files[0].open("rb")},
            )
            assert response.status_code == 200
            image = parse_image(response.text)
            assert image["full_path"] == other / destination
            assert image["title"] == title
            assert image["alt"] == "my description"
            if caption:
                assert image["caption"] == caption
            else:
                assert "caption" not in image
            assert image["rating"] == 3
            assert image["tags"].keys() == {"tag/1", "tag/2", "three"}

            files[destination] = image["id"]

        # search
        response = requests.get(f"{base}{endpoints['search']}")
        assert response.status_code == 200
        inputs = parse_form(response.text)

        expected_keys = {
            "join-strategy",
            "tagged",
            "any_tags-list",
            "all_tags-list",
            "no_tags-list",
            "reachable",
            "limit",
            "offset",
        }
        for index in range(5):
            for part in ("parameter", "comparison", "value"):
                expected_keys.add(f"filter{index + 1}-{part}")

        properties = {
            "name",
            "extension",
            "location",
            "path",
            "creator",
            "title",
            "caption",
            "alt",
            "rating",
            "creation_date",
            "last_modified",
        }
        for index in range(len(properties)):
            for part in ("property", "direction", "nulls"):
                expected_keys.add(f"order{index + 1}-{part}")

        assert inputs.keys() == expected_keys
        assert inputs["join-strategy"] == {
            "type": "select",
            "value": "all",
            "options": ["all", "any"],
        }
        assert inputs["tagged"] == {
            "type": "select",
            "value": None,
            "options": ["", "No", "Yes"],
        }
        assert inputs["any_tags-list"] == {"type": "textarea", "value": None}
        assert inputs["all_tags-list"] == {"type": "textarea", "value": None}
        assert inputs["no_tags-list"] == {"type": "textarea", "value": None}
        assert inputs["reachable"] == {
            "type": "select",
            "value": None,
            "options": ["", "No", "Yes"],
        }
        assert inputs["limit"] == {"type": "number", "value": None}
        assert inputs["offset"] == {"type": "number", "value": 0}
        for index in range(5):
            input = inputs[f"filter{index + 1}-parameter"]
            assert input["type"] == "select"
            assert set(input["options"]) == properties | {""}

        for index in range(len(properties)):
            input = inputs[f"order{index + 1}-property"]
            assert input["type"] == "select"
            assert set(input["options"]) == properties | {"", "random"}

            assert inputs[f"order{index + 1}-direction"] == {
                "type": "select",
                "value": "ascending",
                "options": ["ascending", "descending"],
            }

            assert inputs[f"order{index + 1}-nulls"] == {
                "type": "select",
                "value": "last",
                "options": ["first", "last"],
            }

        response = requests.post(
            f"{base}{endpoints['search']}",
            {
                "filter1-parameter": "location",
                "filter1-comparison": "is",
                "filter1-value": "other",
            },
        )
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert set(images.keys()) == set(files.values())

        # all
        response = requests.post(
            f"{base}{endpoints['search']}",
            {
                "join-strategy": "all",
                "filter1-parameter": "name",
                "filter1-comparison": "is",
                "filter1-value": "123",
                "filter2-parameter": "extension",
                "filter2-comparison": "is",
                "filter2-value": ".XYZ",
                "filter3-parameter": "last_modified",
                "filter3-comparison": "≥",
                "filter3-value": "1901-02-03",
            },
        )
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert images.keys() == {files["123.xyz"]}

        # any
        response = requests.post(
            f"{base}{endpoints['search']}",
            {
                "join-strategy": "any",
                "filter1-parameter": "name",
                "filter1-comparison": "is",
                "filter1-value": "123",
                "filter2-parameter": "extension",
                "filter2-comparison": "is",
                "filter2-value": ".XYZ",
            },
        )
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert images.keys() == {
            files["123.abc"],
            files["123.xyz"],
            files["789.xyz"],
        }

        # limiting
        response = requests.post(
            f"{base}{endpoints['search']}",
            {
                "join-strategy": "any",
                "filter1-parameter": "name",
                "filter1-comparison": "is",
                "filter1-value": "123",
                "filter2-parameter": "extension",
                "filter2-comparison": "is",
                "filter2-value": ".XYZ",
                "limit": 2,
                "order1-property": "caption",
                "order1-direction": "ascending",
                "order1-nulls": "last",
                "order2-property": "name",
                "order2-direction": "ascending",
                "order2-nulls": "last",
                "order3-property": "extension",
                "order3-direction": "descending",
                "order3-nulls": "last",
            },
        )
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert images.keys() == {
            files["789.xyz"],
            files["123.xyz"],
        }

        response = requests.post(
            f"{base}{endpoints['search']}",
            {
                "join-strategy": "any",
                "filter1-parameter": "name",
                "filter1-comparison": "is",
                "filter1-value": "123",
                "filter2-parameter": "extension",
                "filter2-comparison": "is",
                "filter2-value": ".XYZ",
                "limit": 2,
                "order1-property": "caption",
                "order1-direction": "ascending",
                "order1-nulls": "first",
                "order2-property": "name",
                "order2-direction": "ascending",
                "order2-nulls": "last",
            },
        )
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert images.keys() == {
            files["123.abc"],
            files["123.xyz"],
        }


@pytest.mark.asyncio
async def test_tags(run_web, tmp_path, image_files):
    async with run_web() as port:
        base = f"http://localhost:{port}"

        response = requests.get(base)
        assert response.status_code == 200
        root_endpoints = parse_endpoints(response.text)

        response = requests.get(f"{base}{root_endpoints['locations']}")
        assert response.status_code == 200
        location_endpoints = parse_endpoints(response.text)

        main = tmp_path / "main"
        main.mkdir()

        response = requests.post(
            f"{base}{location_endpoints['add']}",
            data={
                "name": "main",
                "path": str(main),
                "description": "my main image storage",
                "type": "Destination",
            },
            allow_redirects=False,
        )
        assert response.status_code == 302
        int(response.headers["Location"].rsplit("/", 1)[-1])

        assert "images" in root_endpoints
        response = requests.get(f"{base}{root_endpoints['images']}")
        assert response.status_code == 200
        image_endpoints = parse_endpoints(response.text)

        ids = []
        links = {}
        for index, tags in enumerate(
            ("", "a\nabc/123", "a/b\nabc/def", "abc", "abc/1234", "abc/123/4")
        ):
            response = requests.post(
                f"{base}{image_endpoints['upload']}",
                {
                    "location": "main",
                    "path": f"{index}.jpg",
                    "tags-list": tags,
                },
                files={"file": image_files[0].open("rb")},
            )
            assert response.status_code == 200
            image = parse_image(response.text)
            ids.append(image["id"])

            for tag, path in image.get("tags", {}).items():
                if tag in links:
                    assert links[tag] == path
                links[tag] = path

        response = requests.get(f"{base}{root_endpoints['tags']}")
        assert response.status_code == 200
        endpoints = parse_endpoints(response.text)
        actions = parse_actions(response.text)

        assert endpoints.keys() == {"add", "list"}
        assert actions == {}

        children = {
            "a": {"b"},
            "abc": {"123", "1234", "def"},
            "abc/123": {"4"},
        }
        tagged = {
            "a": {ids[1], ids[2]},
            "a/b": {ids[2]},
            "abc": {ids[1], ids[2], ids[3], ids[4], ids[5]},
            "abc/123": {ids[1], ids[5]},
            "abc/123/4": {ids[5]},
            "abc/1234": {ids[4]},
            "abc/def": {ids[2]},
        }

        remove_abc = remove_abc_123 = None
        list_abc = list_abc_123 = list_abc_123_4 = None
        for name, path in links.items():
            response = requests.get(f"{base}{path}")
            assert response.status_code == 200
            tag = parse_tag(response.text)
            assert tag["name"] == name
            assert tag["description"] is None
            assert tag["children"].keys() == children.get(name, set())
            for child, child_link in tag["children"].items():
                assert child_link == links[f"{name}/{child}"]
            assert tag["actions"].keys() == {"Move", "Edit", "Remove", "Tagged Images"}

            response = requests.get(f"{base}{tag['actions']['Tagged Images']}")
            assert response.status_code == 200
            images = parse_all_images(response.text, base)
            assert images.keys() == tagged[name]

            if name == "abc":
                remove_abc = tag["actions"]["Remove"]
                list_abc = tag["actions"]["Tagged Images"]
            elif name == "abc/123":
                remove_abc_123 = tag["actions"]["Remove"]
                list_abc_123 = tag["actions"]["Tagged Images"]
            elif name == "abc/123/4":
                list_abc_123_4 = tag["actions"]["Tagged Images"]

            response = requests.get(f"{base}{tag['actions']['Edit']}")
            assert response.status_code == 200
            inputs = parse_form(response.text)
            assert inputs == {"description": {"type": "textarea", "value": None}}

            description = f"{name}'s description"
            response = requests.post(
                f"{base}{tag['actions']['Edit']}", {"description": description}
            )
            assert response.status_code == 200
            tag = parse_tag(response.text)
            assert tag["name"] == name
            assert tag["description"] == description

            response = requests.get(f"{base}{tag['actions']['Edit']}")
            assert response.status_code == 200
            inputs = parse_form(response.text)
            assert inputs == {"description": {"type": "textarea", "value": description}}

        response = requests.get(f"{base}{remove_abc_123}")
        assert response.status_code == 200
        inputs = parse_form(response.text)
        assert inputs == {"cascade": {"type": "checkbox", "value": False}}

        response = requests.post(f"{base}{remove_abc_123}")
        assert response.status_code == 200

        response = requests.get(f"{base}{list_abc_123}")
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert images.keys() == {ids[5]}  # children still exist

        response = requests.get(f"{base}{list_abc_123_4}")
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert images.keys() == {ids[5]}

        response = requests.post(f"{base}{remove_abc}", {"cascade": "on"})
        assert response.status_code == 200

        response = requests.get(f"{base}{list_abc}")
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert images.keys() == set()

        response = requests.get(f"{base}{list_abc_123}")
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert images.keys() == set()

        response = requests.get(f"{base}{list_abc_123_4}")
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert images.keys() == set()

        response = requests.get(f"{base}{endpoints['list']}")
        assert response.status_code == 200
        tags = {}
        list_tag = BeautifulSoup(response.text, "html.parser").find("ul")
        for link in list_tag.find_all("a"):
            tags[link.text] = link["href"]

        assert tags.keys() == {"a", "b"}

        # add and move
        response = requests.get(f"{base}{endpoints['add']}")
        assert response.status_code == 200
        inputs = parse_form(response.text)
        assert inputs == {
            "name": {"type": "text", "value": None},
            "description": {"type": "textarea", "value": None},
        }

        response = requests.post(
            f"{base}{endpoints['add']}", {"name": "abc", "description": "123"}
        )
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["name"] == "abc"
        assert tag["description"] == "123"
        abc_move = tag["actions"]["Move"]

        response = requests.post(
            f"{base}{endpoints['add']}", {"name": "abc/def", "description": "mos"}
        )
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["name"] == "abc/def"
        assert tag["description"] == "mos"
        abc_def_move = tag["actions"]["Move"]

        response = requests.post(
            f"{base}{endpoints['add']}",
            {"name": "abc/def/ghi", "description": "bli"},
        )
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["name"] == "abc/def/ghi"
        assert tag["description"] == "bli"

        response = requests.get(f"{base}{abc_def_move}")
        assert response.status_code == 200
        inputs = parse_form(response.text)
        assert inputs == {
            "new": {"type": "text", "value": "abc/def"},
            "cascade": {"type": "checkbox", "value": True},
        }

        response = requests.post(f"{base}{abc_def_move}", {"new": "abc/fed"})
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["name"] == "abc/fed"
        assert tag["description"] == "mos"

        # TODO: you gotta do better with tag actions
        get = f"{base}{abc_move.split('?', 1)[0].rsplit('/', 1)[0]}?name={{}}"

        response = requests.get(get.format("abc"))
        print(get.format("abc"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] == "123"

        response = requests.get(get.format("abc/def"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] is None

        response = requests.get(get.format("abc/fed"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] == "mos"

        response = requests.get(get.format("abc/def/ghi"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] == "bli"

        response = requests.get(get.format("abc/fed/ghi"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] is None

        response = requests.post(f"{base}{abc_move}", {"new": "cba", "cascade": "on"})
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["name"] == "cba"
        assert tag["description"] == "123"

        response = requests.get(get.format("abc"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] is None

        response = requests.get(get.format("abc/fed"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] is None

        response = requests.get(get.format("cba/fed"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] == "mos"

        response = requests.get(get.format("cba/def/ghi"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] == "bli"

        response = requests.get(get.format("abc/def/ghi"))
        assert response.status_code == 200
        tag = parse_tag(response.text)
        assert tag["description"] is None


@pytest.mark.asyncio
async def test_tasks(run_web, tmp_path, image_files):
    async with run_web() as port:
        base = f"http://localhost:{port}"

        response = requests.get(base)
        assert response.status_code == 200
        root_endpoints = parse_endpoints(response.text)

        response = requests.get(f"{base}{root_endpoints['locations']}")
        assert response.status_code == 200
        location_endpoints = parse_endpoints(response.text)

        main = tmp_path / "main"
        main.mkdir()

        response = requests.post(
            f"{base}{location_endpoints['add']}",
            data={
                "name": "main",
                "path": str(main),
                "description": "my main image storage",
                "type": "Destination",
            },
        )
        assert response.status_code == 200

        camera = tmp_path / "camera"
        camera.mkdir()

        response = requests.post(
            f"{base}{location_endpoints['add']}",
            data={
                "name": "camera",
                "path": str(camera),
                "description": "my camera",
                "type": "Source",
            },
        )
        assert response.status_code == 200

        response = requests.post(
            f"{base}{location_endpoints['add']}",
            data={
                "name": "other-source",
                "description": "my other camera",
                "type": "Source",
                "removable": "on",
            },
        )
        assert response.status_code == 200

        response = requests.post(
            f"{base}{location_endpoints['add']}",
            data={
                "name": "other-destination",
                "description": "my other hard drive",
                "type": "Destination",
                "removable": "on",
            },
        )
        assert response.status_code == 200

        response = requests.get(f"{base}{root_endpoints['tasks']}")
        assert response.status_code == 200
        endpoints = parse_endpoints(response.text)
        actions = parse_actions(response.text)

        assert endpoints.keys() == {"add", "list"}
        assert actions.keys() == {"run", "get", "edit", "remove"}

        response = requests.get(f"{base}{endpoints['add']}")
        assert response.status_code == 200
        inputs = parse_form(response.text)
        assert inputs.keys() == {
            "name",
            "source",
            "destination",
            "description",
            "creator",
            "tags",
            "source_path",
            "destination_format",
            "file_formats",
        }
        assert inputs["name"] == {"type": "text", "value": None}
        assert inputs["source"] == {
            "type": "select",
            "value": None,
            "options": ["camera", "other-source"],
        }
        assert inputs["destination"] == {
            "type": "select",
            "value": None,
            "options": ["main", "other-destination"],
        }
        assert inputs["description"] == {"type": "textarea", "value": None}
        assert inputs["creator"] == {"type": "text", "value": None}
        assert inputs["tags"] == {"type": "textarea", "value": None}
        assert inputs["source_path"] == {"type": "text", "value": None}
        assert inputs["destination_format"] == {"type": "text", "value": None}
        assert inputs["file_formats"] == {"type": "textarea", "value": None}

        # minimal task
        response = requests.post(
            f"{base}{endpoints['add']}",
            {
                "name": "minimal",
                "source": "camera",
                "destination": "main",
            },
        )
        assert response.status_code == 200
        tasks = parse_tasks(response.text)
        assert len(tasks) == 1
        minimal_task = task = tasks[0]
        assert task.keys() == {
            "name",
            "actions",
            "source",
            "destination",
        }
        assert task["name"] == "minimal"
        assert task["actions"].keys() == {"Run", "Edit", "Remove"}
        assert task["source"] == "camera"
        assert task["destination"] == "main"
        assert not task.get("configuration")

        response = requests.post(
            f"{base}{endpoints['add']}",
            {
                "name": "real-task",
                "description": "my more-complicated task",
                "source": "camera",
                "destination": "main",
                "creator": "bcj",
                "tags": "abc\n1/2/3\n",
                "file_formats": ".JPG",
                "source_path": (
                    "path/{year}/{month}/{day}/{date:%Y-%m}/{regex:a.b}/{str:{hi}}"
                ),
                "destination_format": "a/b/{file}",
            },
        )
        assert response.status_code == 200
        tasks = parse_tasks(response.text)
        assert len(tasks) == 1
        real_task = task = tasks[0]
        assert task.keys() == {
            "name",
            "description",
            "actions",
            "source",
            "destination",
            "configuration",
        }
        assert task["name"] == "real-task"
        assert task["description"] == "my more-complicated task"
        assert task["actions"].keys() == {"Run", "Edit", "Remove"}
        assert task["source"] == "camera"
        assert task["destination"] == "main"
        assert task["configuration"] == {
            "creator": "bcj",
            "formats": [".JPG"],
            "tags": ["abc", "1/2/3"],
            "source": "path/{year}/{month}/{day}/{date:%Y-%m}/{regex:a.b}/{str:{hi}}",
            "destination": "a/b/{file}",
        }

        response = requests.get(f"{base}{endpoints['list']}")
        assert response.status_code == 200
        tasks = parse_tasks(response.text)
        assert tasks in ([minimal_task, real_task], [real_task, minimal_task])

        response = requests.get(f"{base}{actions['edit'].format(name='minimal')}")
        assert response.status_code == 200
        inputs = parse_form(response.text)
        assert inputs.keys() == {
            "source",
            "destination",
            "description",
            "creator",
            "tags",
            "source_path",
            "destination_format",
            "file_formats",
        }
        assert inputs["source"] == {
            "type": "select",
            "value": "camera",
            "options": ["camera", "other-source"],
        }
        assert inputs["destination"] == {
            "type": "select",
            "value": "main",
            "options": ["main", "other-destination"],
        }
        assert inputs["description"] == {"type": "textarea", "value": None}
        assert inputs["creator"] == {"type": "text", "value": None}
        assert inputs["tags"] == {"type": "textarea", "value": None}
        assert inputs["source_path"] == {"type": "text", "value": None}
        assert inputs["destination_format"] == {"type": "text", "value": None}
        assert inputs["file_formats"] == {"type": "textarea", "value": None}

        response = requests.get(f"{base}{actions['edit'].format(name='real-task')}")
        assert response.status_code == 200
        inputs = parse_form(response.text)
        assert inputs.keys() == {
            "source",
            "destination",
            "description",
            "creator",
            "tags",
            "source_path",
            "destination_format",
            "file_formats",
        }
        assert inputs["source"] == {
            "type": "select",
            "value": "camera",
            "options": ["camera", "other-source"],
        }
        assert inputs["destination"] == {
            "type": "select",
            "value": "main",
            "options": ["main", "other-destination"],
        }
        assert inputs["description"] == {
            "type": "textarea",
            "value": "my more-complicated task",
        }
        assert inputs["creator"] == {"type": "text", "value": "bcj"}
        assert inputs["tags"] == {"type": "textarea", "value": "abc\n1/2/3"}
        assert inputs["source_path"] == {
            "type": "text",
            "value": "path/{year}/{month}/{day}/{date:%Y-%m}/{regex:a.b}/{str:{hi}}",
        }
        assert inputs["destination_format"] == {"type": "text", "value": "a/b/{file}"}
        assert inputs["file_formats"] == {"type": "textarea", "value": ".JPG"}

        response = requests.post(
            f"{base}{actions['edit'].format(name='minimal')}",
            {
                "source": "camera",
                "destination": "main",
                "creator": "somebody",
                "tags": "hi/hello\nanother/tag",
                "source_path": "minimal",
            },
        )
        assert response.status_code == 200
        tasks = parse_tasks(response.text)
        assert len(tasks) == 1
        task = tasks[0]

        assert task["name"] == "minimal"
        assert task["actions"].keys() == {"Run", "Edit", "Remove"}
        assert task["source"] == "camera"
        assert task["destination"] == "main"
        assert task["configuration"] == {
            "creator": "somebody",
            "tags": ["hi/hello", "another/tag"],
            "source": "minimal",
        }

        response = requests.post(
            f"{base}{actions['edit'].format(name='real-task')}",
            {
                "source": "camera",
                "destination": "main",
                "creator": "somebody else",
                "tags": "hi/hello\nanother/tag",
                "file_formats": ".jpeg\n.png",
                "source_path": (
                    "{year}/{month}/{day}/{date:%Y-%m}/{regex:a.b}/{str:{hi}}"
                ),
                "destination_format": "a/{file}",
            },
        )
        assert response.status_code == 200
        tasks = parse_tasks(response.text)
        assert len(tasks) == 1
        task = tasks[0]

        assert task["name"] == "real-task"
        assert not task.get("description")
        assert task["actions"].keys() == {"Run", "Edit", "Remove"}
        assert task["source"] == "camera"
        assert task["destination"] == "main"
        assert task["configuration"] == {
            "creator": "somebody else",
            "formats": [".jpeg", ".png"],
            "tags": ["hi/hello", "another/tag"],
            "source": "{year}/{month}/{day}/{date:%Y-%m}/{regex:a.b}/{str:{hi}}",
            "destination": "a/{file}",
        }

        response = requests.get(f"{base}{actions['remove'].format(name='minimal')}")
        assert response.status_code == 200
        inputs = parse_form(response.text)
        assert inputs == {}

        response = requests.post(f"{base}{actions['remove'].format(name='minimal')}")
        assert response.status_code == 200

        response = requests.get(f"{base}{actions['get'].format(name='minimal')}")
        assert response.status_code == 404

        # run
        response = requests.get(f"{base}{actions['run'].format(name='real-task')}")
        assert response.status_code == 200
        inputs = parse_form(response.text)
        assert inputs == {
            "since": {"type": "datetime-local", "value": None},
            "full": {"type": "checkbox", "value": False},
            "tags-list": {"type": "textarea", "value": None},
        }

        a = camera / "2020" / "1" / "2" / "2020-01" / "aab" / "{hi}"
        a.mkdir(parents=True)
        shutil.copy2(image_files[0], a / "a.png")
        shutil.copy2(image_files[0], a / "a.jpeg")
        shutil.copy2(image_files[0], a / "a.jpg")

        now = datetime.now()
        b = (
            camera
            / str(now.year)
            / str(now.month)
            / str(now.day)
            / now.strftime("%Y-%m")
            / "abb"
            / "{hi}"
        )
        b.mkdir(parents=True)
        shutil.copy2(image_files[0], b / "b.png")
        shutil.copy2(image_files[0], b / "b.jpeg")
        shutil.copy2(image_files[0], b / "b.jpg")

        response = requests.post(
            f"{base}{actions['run'].format(name='real-task')}",
            {"since": "2020-02-01T00:00"},
        )
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert len(images) == 2
        assert not (main / "a" / "a.png").is_file()
        assert not (main / "a" / "a.jpg").is_file()
        assert not (main / "a" / "a.jpeg").is_file()
        assert (main / "a" / "b.png").is_file()
        assert not (main / "a" / "b.jpg").is_file()
        assert (main / "a" / "b.jpeg").is_file()
        assert {image["full_path"].name for image in images.values()} == {
            "b.png",
            "b.jpeg",
        }

        response = requests.post(f"{base}{actions['run'].format(name='real-task')}")
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert len(images) == 0
        assert not (main / "a" / "a.png").is_file()
        assert not (main / "a" / "a.jpg").is_file()
        assert not (main / "a" / "a.jpeg").is_file()
        assert (main / "a" / "b.png").is_file()
        assert not (main / "a" / "b.jpg").is_file()
        assert (main / "a" / "b.jpeg").is_file()

        response = requests.post(
            f"{base}{actions['run'].format(name='real-task')}",
            {"full": "on"},
        )
        assert response.status_code == 200
        images = parse_all_images(response.text, base)
        assert len(images) == 2
        assert (main / "a" / "a.png").is_file()
        assert not (main / "a" / "a.jpg").is_file()
        assert (main / "a" / "a.jpeg").is_file()
        assert (main / "a" / "b.png").is_file()
        assert not (main / "a" / "b.jpg").is_file()
        assert (main / "a" / "b.jpeg").is_file()
        assert {image["full_path"].name for image in images.values()} == {
            "a.png",
            "a.jpeg",
        }
