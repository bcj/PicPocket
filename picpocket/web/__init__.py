"""A basic web interface

.. todo::
    Web stuff will probably be reworked pretty extensively. This
    represents a minimal version that is usable enough to test how the
    rest of PicPocket works in pracice
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from subprocess import check_call
from tempfile import TemporaryDirectory
from typing import Any, Optional, cast

import tornado
from tornado.escape import url_escape
from tornado.web import Application, HTTPError, RequestHandler, UIModule

from picpocket.api import PicPocket
from picpocket.database import logic
from picpocket.database.types import Image
from picpocket.images import mime_type
from picpocket.parsing import full_path, int_or_str
from picpocket.version import WEB_VERSION
from picpocket.web.colors import DARK, LIGHT

DEFAULT_MIME = "image/unknown"
DEFAULT_PORT = 8888
TEMPLATE_DIRECTORY = str(Path(__file__).absolute().parent / "templates")
URL_BASE = f"/v{WEB_VERSION}"


@dataclass(frozen=True)
class Endpoint:
    path: str
    title: str
    description: str
    submit: Optional[str] = None
    parameters: Optional[list[dict[str, Any]]] = None
    handler: Optional[type[BaseHandler]] = None


class BaseHandler(RequestHandler):
    def render_web(
        self,
        template: str,
        *,
        image: Optional[Image] = None,
        back: Optional[str] = None,
        forward: Optional[str] = None,
        query: Optional[str] = None,
        **kwargs,
    ):
        """Render an html template.

        Args:
            template: The template to use for rendering
            image: An image to display
            back: The path to the previous page in a set
            forward: The path to the next page in a set
            query: Any query parameters to add to related paths
            kwargs: Any arguments to pass through
        """
        self.render(
            template,
            image=image,
            back=back or "",
            forward=forward or "",
            query=query or "",
            **kwargs,
        )

    def write_form(
        self,
        template: str,
        endpoint: Endpoint,
        options: Optional[dict[str, list[str]]] = None,
        existing: Optional[dict[str, Any]] = None,
        known_tags: Optional[list[str]] = None,
        **kwargs,
    ):
        if options is None:
            options = {}

        if existing is None:
            existing = {}

        self.render_web(
            template,
            title=endpoint.title,
            description=endpoint.description,
            parameters=endpoint.parameters,
            submit=endpoint.submit,
            options=options,
            existing=existing,
            known_tags=known_tags,
            **kwargs,
        )

    def join_filters(
        self,
        filters: dict[str, logic.Comparison],
        strategy: str,
        pattern: Optional[str] = None,
    ) -> Optional[logic.Comparison]:
        if strategy != "pattern":
            if not filters:
                return None
            elif len(filters) == 1:
                return list(filters.values())[0]

            match strategy.lower():
                case "any":
                    combiner: type[logic.Combination] = logic.Or
                case "all":
                    combiner = logic.And
                case _:
                    raise HTTPError(400, f"Unknown join strategy: {strategy}")

            return combiner(*filters.values())

        raise HTTPError(500, "TODO: pattern support. sorry!")

    def text_filter(
        self,
        index: str,
        parameter: str,
        comparison: Optional[str],
        value: Optional[str],
    ) -> logic.Comparison:
        """Parse a filter for a text parameter"""

        if comparison in ("is set", "isn't set"):
            return logic.Text(
                parameter,
                logic.Comparator.EQUALS,
                None,
                invert=comparison == "is set",
            )

        if value is None:
            raise HTTPError(400, f"Missing parameter: filter{index}-value")

        match comparison:
            # we might get the wrong one if noscript
            case "=" | "is":
                return logic.Text(parameter, logic.Comparator.EQUALS, value)
            case "≠" | "is not":
                return logic.Text(
                    parameter, logic.Comparator.EQUALS, value, invert=True
                )
            case "starts with":
                return logic.Text(parameter, logic.Comparator.STARTS_WITH, value)
            case "doesn't start with":
                return logic.Text(
                    parameter,
                    logic.Comparator.STARTS_WITH,
                    value,
                    invert=True,
                )
            case "ends with":
                return logic.Text(parameter, logic.Comparator.STARTS_WITH, value)
            case "doesn't end with":
                return logic.Text(
                    parameter,
                    logic.Comparator.ENDS_WITH,
                    value,
                    invert=True,
                )
            case "contains":
                return logic.Text(parameter, logic.Comparator.CONTAINS, value)
            case "doesn't contain":
                return logic.Text(
                    parameter,
                    logic.Comparator.CONTAINS,
                    value,
                    invert=True,
                )
            case _:
                raise HTTPError(
                    400, f"Invalid comparison filter{index}-comparison: {comparison}"
                )

    def number_filter(
        self,
        index: str,
        parameter: str,
        comparison: Optional[str],
        value: Optional[str],
    ) -> logic.Comparison:
        """Parse a filter for a text parameter"""

        if comparison in ("is set", "isn't set"):
            return logic.Number(
                parameter,
                logic.Comparator.EQUALS,
                None,
                invert=comparison == "is set",
            )

        if value is None:
            raise HTTPError(400, f"Missing parameter: filter{index}-value")

        try:
            number = int(value)
        except Exception:
            raise HTTPError(400, f"Invalid parameter: filter{index}-value: {value}")

        match comparison:
            # we might get the wrong one if noscript
            case "=" | "is":
                return logic.Number(parameter, logic.Comparator.EQUALS, number)
            case "≠" | "is not":
                return logic.Number(
                    parameter, logic.Comparator.EQUALS, number, invert=True
                )
            case "<" | "≤" | "≥" | ">":
                if comparison == "≤":
                    comparison = "<="
                elif comparison == "≥":
                    comparison = ">="

                return logic.Number(parameter, logic.Comparator(comparison), number)
            case _:
                raise HTTPError(
                    400, f"Invalid comparison filter{index}-comparison: {comparison}"
                )

    def date_filter(
        self,
        index: str,
        parameter: str,
        comparison: Optional[str],
        value: Optional[str],
    ) -> logic.Comparison:
        """Parse a filter for a text parameter"""

        if comparison in ("is set", "isn't set"):
            return logic.DateTime(
                parameter,
                logic.Comparator.EQUALS,
                None,
                invert=comparison == "is set",
            )

        if value is None:
            raise HTTPError(400, f"Missing parameter: filter{index}-value")

        try:
            date = datetime.strptime(value, "%Y-%m-%d").astimezone()
        except Exception:
            raise HTTPError(400, f"Invalid parameter: filter{index}-value: {value}")

        match comparison:
            # we might get the wrong one if noscript
            case "=" | "is":
                return logic.DateTime(parameter, logic.Comparator.EQUALS, date)
            case "≠" | "is not":
                return logic.DateTime(
                    parameter, logic.Comparator.EQUALS, date, invert=True
                )
            case "<" | "≤" | "≥" | ">":
                if comparison == "≤":
                    comparison = "<="
                elif comparison == "≥":
                    comparison = ">="

                return logic.DateTime(parameter, logic.Comparator(comparison), date)
            case _:
                raise HTTPError(
                    400, f"Invalid comparison filter{index}-comparison: {comparison}"
                )


class BaseApiHandler(BaseHandler):
    def initialize(
        self,
        endpoint: Endpoint,
        picpocket: PicPocket,
        local_actions: set[str],
    ):
        self.endpoint = endpoint
        self.api = picpocket
        self.local_actions = local_actions

    async def display_images(
        self,
        images: list[int] | list[Image],
        action: str = "Found",
    ):
        query = ""
        forward = ""
        image = None
        location_name = None
        if images:
            if isinstance(images[0], int):
                # mypy doesn't trust the above isinstance check
                ids = cast(list[int], images)
                image = await self.api.get_image(ids[0], tags=True)
            else:
                # mypy doesn't trust the above isinstance check
                images = cast(list[Image], images)
                ids = [image.id for image in images]
                image = images[0]

            if image:
                location = await self.api.get_location(image.location)
                if location:
                    location_name = location.name

            if len(ids) > 1:
                session_id = await self.api.create_session({"ids": ids})
                query = f"?set={session_id}"
                forward = self.reverse_url("images-get", ids[1])
        else:
            ids = []

        self.render_web(
            "image.html",
            action=action,
            image_ids=ids,
            image=image,
            location_name=location_name,
            query=query,
            forward=forward,
            local_actions=self.local_actions,
        )


class StyleHandler(BaseHandler):
    def get(self):
        self.set_header("Content-Type", "text/css")
        self.render("style.css", light=LIGHT, dark=DARK)


class ScriptHandler(BaseHandler):
    def get(self):
        self.set_header("Content-Type", "application/javascript")
        self.render("scripts.js")


class RootHandler(BaseHandler):
    def get(self):
        self.redirect(self.reverse_url("home"))


class ApiRootHandler(BaseHandler):
    def get(self):
        self.render_web(
            "index.html",
            title="PicPocket",
            description="A place for your photos",
            endpoints=NAVBAR,
            actions=None,
        )


class LocationsHandler(BaseHandler):
    def get(self):
        self.render_web(
            "index.html",
            title="Locations",
            description="Places to store images & places to import images from",
            endpoints=ENDPOINTS["locations"],
            actions=ACTIONS["locations"],
            id_name="{id}",
            id_type="text",
        )


class LocationsAddHandler(BaseApiHandler):
    def get(self):
        self.write_form("form.html", self.endpoint)

    async def post(self):
        data = {}
        for key in ("name", "description", "path"):
            data[key] = self.get_body_argument(key, None)

        location_type = self.get_body_argument("type")
        data["source"] = location_type == "Source"
        data["destination"] = location_type == "Destination"
        data["removable"] = self.get_body_argument("removable", None) == "on"

        if data.get("path"):
            data["path"] = full_path(data["path"])
        else:
            data["path"] = None

        try:
            name_or_id = await self.api.add_location(**data)
        except Exception:
            raise HTTPError(400, "Adding location failed")

        self.redirect(self.reverse_url("locations-get", name_or_id))


class LocationsListHandler(BaseApiHandler):
    async def get(self):
        locations = await self.api.list_locations()
        self.render_web("location.html", locations=locations)


class LocationsGetHandler(BaseApiHandler):
    async def get(self, name_or_id):
        name_or_id = int_or_str(name_or_id)

        location = await self.api.get_location(name_or_id)

        if location is None:
            raise HTTPError(404, f"Unknown location: {name_or_id}")

        self.render_web(
            "location.html",
            locations=[location],
            edit_path=ACTIONS["locations"]["edit"].path,
            remove_path=ACTIONS["locations"]["remove"].path,
            mount_path=ACTIONS["locations"]["mount"].path,
            unmount_path=ACTIONS["locations"]["unmount"].path,
            import_path=ACTIONS["locations"]["import"].path,
        )


class LocationsMountHandler(BaseApiHandler):
    async def get(self, name_or_id):
        location = await self.api.get_location(int_or_str(name_or_id))

        if location is None:
            raise HTTPError(404, f"Unknown location: {name_or_id}")

        self.write_form("form.html", self.endpoint, existing=location.serialize())

    async def post(self, name_or_id):
        name_or_id = int_or_str(name_or_id)

        try:
            path = full_path(self.get_body_argument("path"))
        except Exception:
            raise HTTPError(400, f"Bad path: {self.get_body_argument('path')}")

        try:
            await self.api.mount(name_or_id, path)
        except Exception:
            raise HTTPError(400, f"Mounting location failed: {name_or_id}")

        self.redirect(self.reverse_url("locations-get", name_or_id))


class LocationsUnmountHandler(BaseApiHandler):
    async def get(self, name_or_id):
        location = await self.api.get_location(int_or_str(name_or_id))

        if location is None:
            raise HTTPError(404, f"Unknown location: {name_or_id}")

        self.write_form("form.html", self.endpoint, existing=location.serialize())

    async def post(self, name_or_id):
        name_or_id = int_or_str(name_or_id)

        try:
            await self.api.unmount(name_or_id)
        except Exception:
            raise HTTPError(400, f"Unmounting location failed: {name_or_id}")

        self.redirect(self.reverse_url("locations-get", name_or_id))


class LocationsImportHandler(BaseApiHandler):
    async def get(self, name_or_id):
        location = await self.api.get_location(int_or_str(name_or_id))

        if location is None:
            raise HTTPError(404, f"Unknown location: {name_or_id}")

        known_tags = sorted(await self.api.all_tag_names())

        self.write_form("form.html", self.endpoint, known_tags=known_tags)

    async def post(self, name_or_id):
        name_or_id = int_or_str(name_or_id)
        creator = self.get_body_argument("creator", None) or None
        kwargs = {}

        batch_str = self.get_body_argument("batch_size")
        if batch_str:
            try:
                kwargs["batch_size"] = int(batch_str)
            except Exception:
                raise HTTPError(400, f"Invalid batch size: {batch_str}")

        tags = self.get_body_arguments("tags", None)
        if not tags:
            tagsstr = self.get_body_argument("tags-list", None)
            if tagsstr:
                tags = tagsstr.splitlines()

        formats = []
        formats_string = self.get_body_argument("file_formats")
        if formats_string:
            for file_format in formats_string.splitlines():
                if file_format:
                    formats.append(file_format)

        if not formats:
            formats = None

        try:
            imported = await self.api.import_location(
                name_or_id,
                file_formats=formats,
                creator=creator,
                tags=tags,
                **kwargs,
            )
        except Exception:
            raise HTTPError(400, f"Importing location failed: {name_or_id}")

        await self.display_images(imported, "Imported")


class LocationsEditHandler(BaseApiHandler):
    async def get(self, name_or_id):
        location = await self.api.get_location(int_or_str(name_or_id))

        if location is None:
            raise HTTPError(404, f"Unknown location: {name_or_id}")

        existing = location.serialize()
        existing["new_name"] = existing["name"]
        existing["type"] = "Source" if existing["source"] else "Destination"

        self.write_form("form.html", self.endpoint, existing=existing)

    async def post(self, name_or_id):
        name_or_id = int_or_str(name_or_id)

        data = {}
        for key in ("new_name", "description", "path"):
            data[key] = self.get_body_argument(key, None)

        data["removable"] = self.get_body_argument("removable", None) == "on"

        location_type = self.get_body_argument("type")
        data["source"] = location_type == "Source"
        data["destination"] = location_type == "Destination"

        if data.get("path"):
            data["path"] = full_path(data["path"])

        new_name = data.pop("new_name", None)

        try:
            await self.api.edit_location(name_or_id, new_name, **data)
        except Exception:
            raise HTTPError(400, f"Editing location failed: {name_or_id}")

        self.redirect(self.reverse_url("locations-get", name_or_id))


class LocationsRemoveHandler(BaseApiHandler):
    async def get(self, name_or_id):
        location = await self.api.get_location(int_or_str(name_or_id))

        # this is a niceity until we add proper error flow from package
        # to api. the location could still be deleted between this
        # check and the POST
        if location is None:
            raise HTTPError(404, f"Unknown location: {name_or_id}")

        self.write_form("form.html", self.endpoint)

    async def post(self, name_or_id):
        name_or_id = int_or_str(name_or_id)

        force = self.get_body_argument("force", None) == "on"

        try:
            await self.api.remove_location(name_or_id, force=force)
        except Exception:
            raise HTTPError(400, "Removing location failed")

        self.redirect(self.reverse_url("locations"))


class ImagesHandler(BaseHandler):
    def get(self):
        self.render_web(
            "index.html",
            title="Images",
            description="Your Images",
            endpoints=ENDPOINTS["images"],
            actions=ACTIONS["images"],
            id_name="{id}",
            id_type="text",
        )


class ImagesSearchHandler(BaseApiHandler):
    def initialize(
        self,
        endpoint: Endpoint,
        picpocket: PicPocket,
        local_actions: set[str],
    ):
        self.endpoint = endpoint
        self.api = picpocket
        self.local_actions = local_actions
        self.parameters: list[dict[str, Any]] = []
        self.properties = None
        self.order: list[str] = []

    async def get(self):
        if not self.properties:
            for parameter in self.endpoint.parameters:
                if parameter["name"] == "filter":
                    self.properties = parameter["properties"]
                elif parameter["name"] == "order":
                    self.order = parameter["options"]
                else:
                    self.parameters.append(parameter)

        locations = ["any"]
        for location in await self.api.list_locations():
            locations.append(location.name)

        for filter_property in self.properties:
            if filter_property[0] == "location":
                filter_property[1]["options"] = locations

        self.render_web(
            "search.html",
            title=self.endpoint.title,
            description=self.endpoint.description,
            submit=self.endpoint.submit,
            parameters=self.properties,
            other_parameters=self.parameters,
            order=self.order,
            properties=self.properties,
        )

    async def post(self):
        join = {"strategy": "all", "pattern": ""}
        filter_info = {
            "parameter": {},
            "comparison": {},
            "value": {},
        }
        indices = set()

        for key in self.request.body_arguments:
            match = re.search(r"^join-(strategy|patten)$", key)

            if match:
                join[match.group(1)] = self.get_body_argument(key)
            else:
                match = re.search(r"^filter(\d+)-(parameter|comparison|value)$", key)

                if match:
                    index = match.group(1)
                    indices.add(index)

                    kind = match.group(2)
                    value = self.get_body_argument(key)

                    filter_info[kind][index] = value

        filters = {}

        for index in indices:
            if not filter_info["parameter"].get(index):
                continue

            parameter = filter_info["parameter"].get(index)
            comparison = filter_info["comparison"].get(index)
            value = filter_info["value"].get(index)
            match parameter:
                case "name" | "creator" | "path" | "title" | "caption" | "alt":
                    filters[index] = self.text_filter(
                        index,
                        parameter,
                        comparison,
                        value,
                    )
                case "extension":
                    filters[index] = self.text_filter(
                        index,
                        parameter,
                        comparison,
                        value.lower().lstrip("."),
                    )
                case "rating":
                    filters[index] = self.number_filter(
                        index,
                        parameter,
                        comparison,
                        value,
                    )
                case "location":
                    match comparison:
                        case "option" | "is" | "is not" | "=" | "≠":
                            location = await self.api.get_location(int_or_str(value))
                            if location is None:
                                raise HTTPError(400, f"Unknown location: {value}")

                            filters[index] = logic.Number(
                                "location",
                                logic.Comparator.EQUALS,
                                location.id,
                                invert=comparison in ("≠", "is not"),
                            )
                        case _:
                            raise HTTPError(
                                400,
                                (
                                    f"Invalid value for filter{index}-comparison: "
                                    f"{comparison}"
                                ),
                            )
                case "creation_date" | "last_modified":
                    filters[index] = self.date_filter(
                        index,
                        parameter,
                        comparison,
                        value,
                    )
                case _:
                    raise HTTPError(
                        400,
                        f"Invalid value for filter{index}-parameter: {parameter}",
                    )

        filter = self.join_filters(filters, join["strategy"], join["pattern"])

        order = []
        index = 1
        while True:
            column = self.get_body_argument(f"order{index}-property", "")
            if not column:
                break
            elif column == "random":
                order.append(column)
                break

            blanks = self.get_body_argument(f"order{index}-nulls", "last")
            if blanks == "first":
                column = f"!{column}"
            elif blanks == "last":
                column = f"{column}!"
            else:
                raise HTTPError(f"Invalid blank position: {blanks}")

            direction = self.get_body_argument(f"order{index}-direction", "ascending")
            if direction == "descending":
                column = f"-{column}"
            elif direction != "ascending":
                raise HTTPError(f"Invalid sort direction: {direction}")

            order.append(column)
            index += 1

        if not order:
            order = None

        limitstr = self.get_body_argument("limit", None)
        if limitstr:
            try:
                limit = int(limitstr)
            except Exception:
                raise HTTPError(f"Invalid limit: {limitstr}")
        else:
            limit = None

        offsetstr = self.get_body_argument("offset", None)
        if offsetstr:
            try:
                offset = int(offsetstr)
            except Exception:
                raise HTTPError(f"Invalid offset: {offsetstr}")
        else:
            offset = None

        reachablestr = self.get_body_argument("reachable", None)
        if reachablestr:
            if reachablestr.lower() == "yes":
                reachable = True
            elif reachablestr.lower() == "no":
                reachable = False
            else:
                raise HTTPError(f"Invalid reachable value: {reachablestr}")
        else:
            reachable = None

        taggedstr = self.get_body_argument("tagged", None)
        if taggedstr:
            if taggedstr.lower() == "yes":
                tagged = True
            elif taggedstr.lower() == "no":
                tagged = False
            else:
                raise HTTPError(f"Invalid tagged value: {taggedstr}")
        else:
            tagged = None

        tag_kwargs = {}
        for option in ("any_tags", "all_tags", "no_tags"):
            text = self.get_body_argument(option, None)
            if text:
                tag_kwargs[option] = list(text.splitlines())

        ids = await self.api.get_image_ids(
            filter,
            reachable=reachable,
            order=order,
            limit=limit,
            offset=offset,
            tagged=tagged,
            **tag_kwargs,
        )

        await self.display_images(ids)


class ImagesUploadHandler(BaseApiHandler):
    async def get(self):
        locations = await self.api.list_locations()
        options = {"location": []}
        for location in sorted(locations, key=lambda location: location.name):
            if location.destination:
                options["location"].append(location.name)

        if not options["location"]:
            raise HTTPError(400, "Create a destination location first")

        known_tags = sorted(await self.api.all_tag_names())

        self.write_form(
            "form.html",
            self.endpoint,
            options=options,
            known_tags=known_tags,
        )

    async def post(self):
        try:
            file = self.request.files["file"][0]
        except Exception:
            raise HTTPError(400, "You must supply a file")

        path = Path(self.get_body_argument("path", "."))
        if not path.suffix:
            path = path / file["filename"]

        location = self.get_body_argument("location", None)
        if not location:
            raise HTTPError(400, "A location must be supported")
        location = int_or_str(location)

        data = {}
        for key in ("creator", "title", "caption", "alt"):
            data[key] = self.get_body_argument(key, None) or None

        rating = self.get_body_argument("rating", None)
        if rating:
            data["rating"] = int(rating)
        else:
            data["rating"] = None

        data["tags"] = self.get_body_arguments("tags", None)
        if not data["tags"]:
            tagsstr = self.get_body_argument("tags-list", None)
            if tagsstr:
                data["tags"] = tagsstr.splitlines()

        with TemporaryDirectory() as directory_name:
            source = Path(directory_name) / file["filename"]
            source.write_bytes(file["body"])

            try:
                image_id = await self.api.add_image_copy(source, location, path, **data)
            except Exception:
                raise HTTPError(400, "Copying image failed ")

        self.redirect(self.reverse_url("images-get", image_id))


class ImagesFindHandler(BaseApiHandler):
    async def get(self):
        self.write_form("form.html", self.endpoint)

    async def post(self):
        try:
            path = full_path(self.get_body_argument("path"))
        except Exception:
            raise HTTPError(400, "Missing path")

        try:
            image = await self.api.find_image(path, tags=True)
        except Exception:
            raise HTTPError(400, f"Finding image failed: {path}")

        if image is None:
            raise HTTPError(404, f"Finding image failed: {path}")

        self.redirect(self.reverse_url("images-get", image.id))


class ImagesVerifyHandler(BaseApiHandler):
    async def get(self):
        locations = await self.api.list_locations()
        options = {"location": [None]}
        for location in sorted(locations, key=lambda location: location.name):
            options["location"].append(location.name)

        self.write_form(
            "form.html",
            self.endpoint,
            existing={"location": None},
            options=options,
            none="any",
        )

    async def post(self):
        pathstr = self.get_body_argument("path", None)
        if pathstr:
            path = full_path(pathstr)
        else:
            path = None

        location_id = None
        location_name = self.get_body_argument("location", None)
        if location_name and location_name != "any":
            location = await self.api.get_location(location_name)

            if not location:
                raise HTTPError(400, f"Unknown location: {location_name}")

            location_id = location.id

        reparse_exif = self.get_body_argument("exif", "off") == "on"

        try:
            images = await self.api.verify_image_files(
                location=location_id,
                path=path,
                reparse_exif=reparse_exif,
            )
        except Exception:
            raise HTTPError(400, "Verifying images failed ")

        await self.display_images(images, "Missing")


class ImagesGetHandler(BaseApiHandler):
    async def get(self, image_id):
        image_id = int(image_id)

        image = await self.api.get_image(image_id, tags=True)

        if image is None:
            raise HTTPError(404, f"Unknown image: {image_id}")

        location_name = None
        location = await self.api.get_location(image.location)
        if location:
            location_name = location.name

        back = forward = None
        query = ""
        try:
            session_id = self.get_query_argument("set", None)

            if session_id:
                data = await self.api.get_session(int(session_id))

                if data:
                    query = f"?set={session_id}"
                    index = data["ids"].index(image_id)

                    if index > 0:
                        back = self.reverse_url("images-get", data["ids"][index - 1])

                    if index + 1 < len(data["ids"]):
                        forward = self.reverse_url("images-get", data["ids"][index + 1])
        except Exception:
            pass

        self.render_web(
            "image.html",
            image_ids=None,
            image=image,
            location_name=location_name,
            back=back,
            forward=forward,
            query=query,
            local_actions=self.local_actions,
        )


class ImagesFileHandler(BaseApiHandler):
    async def get(self, image_id):
        image_id = int(image_id)

        image = await self.api.get_image(image_id, tags=True)

        if image is None:
            raise HTTPError(404, f"Unknown image: {image_id}")

        if image.full_path is None:
            raise HTTPError(500, f"Image on unmounted location: {id}")

        self.write(image.full_path.read_bytes())
        self.set_header("Content-Type", mime_type(image.full_path) or DEFAULT_MIME)


class ImagesEditHandler(BaseApiHandler):
    async def get(self, image_id):
        image = await self.api.get_image(int(image_id), tags=True)

        if image is None:
            raise HTTPError(404, f"Unknown image: {image_id}")

        known_tags = sorted(await self.api.all_tag_names())

        existing = image.serialize()
        if "tags" in existing:
            existing["tags"] = image.tags
            existing["existing-tags"] = json.dumps(image.tags)
        self.write_form(
            "form.html",
            self.endpoint,
            existing=existing,
            image=image,
            known_tags=known_tags,
        )

    async def post(self, image_id):
        data = {}
        for key in ("creator", "title", "caption", "alt"):
            data[key] = self.get_body_argument(key, None) or None

        rating = self.get_body_argument("rating")
        if rating:
            data["rating"] = int(rating)
        else:
            data["rating"] = None

        existing = set()
        existingstr = self.get_body_argument("existing-tags", None)
        if existingstr:
            existing = set(json.loads(existingstr))

        tags = set()
        tags_list = self.get_body_arguments("tags", None)
        if tags_list:
            tags = set(tags_list)
        else:
            tagsstr = self.get_body_argument("tags-list", None)
            if tagsstr:
                tags = set(tagsstr.splitlines())

        try:
            id = int(image_id)
            await self.api.edit_image(id, **data)
        except Exception:
            raise HTTPError(400, f"Editing image failed: {image_id}")

        for tag in existing - tags:
            try:
                await self.api.untag_image(id, tag)
            except Exception:
                raise HTTPError(400, f"Removing tag failed: {image_id}, {tag}")

        for tag in tags - existing:
            try:
                await self.api.tag_image(id, tag)
            except Exception:
                raise HTTPError(400, f"Add tag failed: {image_id}, {tag}")

        url = self.reverse_url("images-get", image_id)
        try:
            session_id = self.get_query_argument("set", None)
            if session_id:
                url = f"{url}?set={session_id}"
        except Exception:
            pass

        self.redirect(url)


class ImagesMoveHandler(BaseApiHandler):
    async def get(self, image_id):
        image = await self.api.get_image(int(image_id), tags=True)

        if image is None:
            raise HTTPError(404, f"Unknown image: {image_id}")

        existing = image.serialize()

        locations = await self.api.list_locations()
        options = {"location": []}
        for location in sorted(locations, key=lambda location: location.name):
            options["location"].append(location.name)
            if location.id == image.location:
                existing["location"] = location.name

        self.write_form(
            "form.html",
            self.endpoint,
            options=options,
            existing=existing,
            image=image,
        )

    async def post(self, image_id):
        path = Path(self.get_body_argument("path"))
        location_name = int_or_str(self.get_body_argument("location"))

        location = await self.api.get_location(location_name)
        if location is None:
            raise HTTPError(400, f"Unknown location: {location_name}")

        location_id = location.id

        try:
            await self.api.move_image(image_id, path, location=location_id)
        except Exception:
            raise HTTPError(400, f"Moving image failed: {image_id}")

        url = self.reverse_url("images-get", image_id)
        try:
            session_id = self.get_query_argument("set", None)
            if session_id:
                url = f"{url}?set={session_id}"
        except Exception:
            pass

        self.redirect(url)


class ImagesRemoveHandler(BaseApiHandler):
    async def get(self, image_id):
        image = await self.api.get_image(int(image_id), tags=True)

        if image is None:
            raise HTTPError(404, f"Unknown image: {image_id}")

        self.write_form(
            "form.html",
            self.endpoint,
            image=image,
        )

    async def post(self, image_id):
        delete = self.get_body_argument("delete", False) == "on"

        try:
            await self.api.remove_image(image_id, delete=delete)
        except Exception:
            raise HTTPError(400, f"Removing image failed: {image_id}")

        url = None
        try:
            session_id = self.get_query_argument("set", None)
            if session_id:
                data = await self.api.get_session(int(session_id))

                if len(data["ids"]) > 1:
                    index = data["ids"].index(int(image_id))
                    if index is not None:
                        del data["ids"][index]
                        index = min(index, len(data["ids"]) - 1)

                        url = self.reverse_url("images-get", data["ids"][index])

                        if len(data["ids"]) > 1:
                            set_id = await self.api.create_session(data)
                            url = f"{url}?set={set_id}"
        except Exception:
            pass

        if url is None:
            url = self.reverse_url("images")

        self.redirect(url)


class TagsHandler(BaseHandler):
    def get(self):
        self.render_web(
            "index.html",
            title="Tags",
            description=(
                "Labels applied to images in PicPocket that can be used to "
                "categorize and sort images. Tags in PicPocket are hierarchical: "
                "'plants/flowers' is a subcategory of 'plants', and "
                "'plants/flowers/Hyacinth' is a subcategory of both of them. "
                "When searching for images based on tags, any more-specific "
                "tags will be included as well. When tagging images, you do "
                "not need to include any broader-category tags (i.e., if "
                "you tag an image 'plants/flowers/Hyacinth', it is unnecessary "
                "to tag it 'plants' or 'plants/flowers')."
            ),
            endpoints=ENDPOINTS["tags"],
            actions=None,
            id_name="{tag}",
            id_type="text",
        )


class TagsAddHandler(BaseApiHandler):
    async def get(self):
        self.write_form("form.html", self.endpoint)

    async def post(self):
        name = self.get_body_argument("name")
        description = self.get_body_argument("description", None)

        try:
            await self.api.add_tag(name, description=description)
        except Exception:
            raise HTTPError(400, f"Moving tag failed: {name}")

        self.redirect(f"{self.reverse_url('tags-get')}?name={url_escape(name)}")


class TagsListHandler(BaseApiHandler):
    async def get(self):
        self.render_web("tags.html", tags=await self.api.all_tags())


class TagsGetHandler(BaseApiHandler):
    async def get(self):
        name = self.get_query_argument("name")

        if not name:
            raise HTTPError(400, "Please supply a tag name")

        tag = await self.api.get_tag(name, children=True)

        self.render_web("tag.html", tag=tag)


class TagsMoveHandler(BaseApiHandler):
    async def get(self):
        name = self.get_query_argument("name")

        if not name:
            raise HTTPError(400, "Please supply a tag name")

        self.write_form(
            "form.html",
            self.endpoint,
            existing={"new": name, "cascade": True},
        )

    async def post(self):
        current = self.get_query_argument("name")

        if not current:
            raise HTTPError(400, "Please supply a tag name")

        new = self.get_body_argument("new")
        cascade = self.get_body_argument("cascade", "off") == "on"

        try:
            await self.api.move_tag(current, new, cascade=cascade)
        except Exception:
            raise HTTPError(400, f"Moving tag failed: {current}")

        self.redirect(f"{self.reverse_url('tags-get')}?name={url_escape(new)}")


class TagsEditHandler(BaseApiHandler):
    async def get(self):
        name = self.get_query_argument("name")

        if not name:
            raise HTTPError(400, "Please supply a tag name")

        tag = await self.api.get_tag(name)

        self.write_form(
            "form.html",
            self.endpoint,
            existing={"description": tag.description},
        )

    async def post(self):
        name = self.get_query_argument("name")

        if not name:
            raise HTTPError(400, "Please supply a tag name")

        description = self.get_body_argument("description", None)

        try:
            await self.api.add_tag(name, description=description)
        except Exception:
            raise HTTPError(400, f"Editing tag failed: {name}")

        self.redirect(f"{self.reverse_url('tags-get')}?name={url_escape(name)}")


class TagsRemoveHandler(BaseApiHandler):
    async def get(self):
        name = self.get_query_argument("name")

        if not name:
            raise HTTPError(400, "Please supply a tag name")

        self.write_form("form.html", self.endpoint)

    async def post(self):
        name = self.get_query_argument("name")

        if not name:
            raise HTTPError(400, "Please supply a tag name")

        cascade = self.get_body_argument("cascade", None) == "on"

        try:
            await self.api.remove_tag(name, cascade=cascade)
        except Exception:
            raise HTTPError(400, f"Removing tag failed: {name}")

        self.redirect(self.reverse_url("tags"))


class TagsImagesHandler(BaseApiHandler):
    async def get(self):
        name = self.get_query_argument("name")

        if not name:
            raise HTTPError(400, "Please supply a tag name")

        try:
            ids = await self.api.get_image_ids(all_tags=[name])
        except Exception:
            raise HTTPError(500, "Finding tagged images failed")

        await self.display_images(ids, "Tagged")


class TasksHandler(BaseHandler):
    def get(self):
        self.render_web(
            "index.html",
            title="Tasks",
            description=(
                "preconfigured jobs for importing images from your "
                "devices to the places you store them. "
                "Tasks can automatically apply information to the images "
                "they copy."
            ),
            endpoints=ENDPOINTS["tasks"],
            actions=ACTIONS["tasks"],
            id_name="{name}",
            id_type="text",
        )


class TasksAddHandler(BaseApiHandler):
    async def get(self):
        source = []
        destination = []

        for location in await self.api.list_locations():
            if location.source:
                source.append(location.name)

            if location.destination:
                destination.append(location.name)

        options = {}
        if source:
            options["source"] = sorted(source)
        else:
            raise HTTPError(400, "Create a source location first")

        if destination:
            options["destination"] = sorted(destination)
        else:
            raise HTTPError(400, "Create a destination location first")

        self.write_form(
            "form.html",
            self.endpoint,
            options=options,
            none="any",
        )

    async def post(self):
        data = {}

        for key in ("name", "source", "destination"):
            data[key] = self.get_body_argument(key)

        for key in ("description", "creator", "source_path", "destination_format"):
            data[key] = self.get_body_argument(key, None)

        for key in ("tags", "file_formats"):
            group = self.get_body_argument(key, None)
            if group:
                data[key] = list(group.splitlines())

        try:
            await self.api.add_task(**data)
        except Exception:
            raise HTTPError(400, "Creating task failed")

        self.redirect(self.reverse_url("tasks-get", data["name"]))


class TasksListHandler(BaseApiHandler):
    async def get(self):
        tasks = await self.api.list_tasks()
        location_names = {}

        for task in tasks:
            for location_id in (task.source, task.destination):
                if location_id not in location_names:
                    location = await self.api.get_location(location_id)
                    if location:
                        location_names[location_id] = location.name
                    else:
                        location_names[location_id] = location.name

        self.render_web("task.html", tasks=tasks, location_names=location_names)


class TasksRunHandler(BaseApiHandler):
    async def get(self, name):
        task = await self.api.get_task(name)

        if task is None:
            raise HTTPError(404, f"Unknown task: {name}")

        existing = {}
        if task.last_ran:
            existing["since"] = task.last_ran.strftime("%Y-%m-%dT%H:%M")

        self.write_form("form.html", self.endpoint, existing=existing)

    async def post(self, name):
        since = None
        datestr = self.get_body_argument("since", None)
        if datestr:
            since = datetime.strptime(datestr, "%Y-%m-%dT%H:%M").astimezone()

        full = self.get_body_argument("full", "off") == "on"

        try:
            ids = await self.api.run_task(name, since=since, full=full)
        except Exception as exception:
            raise HTTPError(400, repr(exception))
            raise HTTPError(400, "Running task failed")

        await self.display_images(ids, "Copied")


class TasksGetHandler(BaseApiHandler):
    async def get(self, name):
        task = await self.api.get_task(name)

        if task is None:
            raise HTTPError(404, f"Unknown task: {name}")

        location_names = {}
        for location_id in (task.source, task.destination):
            if location_id not in location_names:
                location = await self.api.get_location(location_id)
                if location:
                    location_names[location_id] = location.name
                else:
                    location_names[location_id] = location.name

        self.render_web("task.html", tasks=[task], location_names=location_names)


class TasksEditHandler(BaseApiHandler):
    async def get(self, name):
        task = await self.api.get_task(name)

        if task is None:
            raise HTTPError(404, f"Unknown task: {name}")

        existing = task.serialize()
        configuration = existing.pop("configuration", {})
        if "creator" in configuration:
            existing["creator"] = configuration["creator"]

        if "source" in configuration:
            existing["source_path"] = configuration["source"]

        if "destination" in configuration:
            existing["destination_format"] = configuration["destination"]

        if "tags" in configuration:
            existing["tags"] = "\n".join(configuration["tags"])

        if "formats" in configuration:
            existing["file_formats"] = "\n".join(configuration["formats"])

        source = []
        destination = []

        for location in await self.api.list_locations():
            if location.source:
                source.append(location.name)

            if location.destination:
                destination.append(location.name)

            if location.id == task.source:
                existing["source"] = location.name

            if location.id == task.destination:
                existing["destination"] = location.name

        options = {}
        if source:
            options["source"] = sorted(source)
        else:
            raise HTTPError(400, "Create a source location first")

        if destination:
            options["destination"] = sorted(destination)
        else:
            raise HTTPError(400, "Create a destination location first")

        self.write_form(
            "form.html",
            self.endpoint,
            existing=existing,
            options=options,
            none="any",
        )

    async def post(self, name):
        data = {}

        for key in ("source", "destination"):
            data[key] = self.get_body_argument(key)

        for key in ("description", "creator", "source_path", "destination_format"):
            data[key] = self.get_body_argument(key, None)

        for key in ("tags", "file_formats"):
            group = self.get_body_argument(key, None)
            if group:
                data[key] = list(group.splitlines())

        try:
            await self.api.add_task(name, **data, force=True)
        except Exception:
            raise HTTPError(400, "Editing task failed")

        self.redirect(self.reverse_url("tasks-get", name))


class TasksRemoveHandler(BaseApiHandler):
    async def get(self, name):
        task = await self.api.get_task(name)

        if task is None:
            raise HTTPError(404, f"Unknown task: {name}")

        self.write_form("form.html", self.endpoint)

    async def post(self, name):
        try:
            await self.api.remove_task(name)
        except Exception:
            raise HTTPError(400, "Removing task failed")

        self.redirect(self.reverse_url("tasks"))


# 'special' handlers


class ShowInFinderHandler(RequestHandler):
    def initialize(self, picpocket: PicPocket):
        self.api = picpocket

    async def get(self, text_id: str):
        try:
            image_id = int(text_id)
        except Exception:
            raise HTTPError(400, f"Invalid image id: {text_id}")

        image = await self.api.get_image(image_id)

        if image is None:
            raise HTTPError(404, f"Unknown image: {image_id}")

        if not image.full_path:
            raise HTTPError(400, "Image path not known")

        try:
            check_call(["open", "-R", str(image.full_path)])
        except Exception:
            raise HTTPError(500, "opening image failed")

        self.write("done")


# UI modules


class NavBarHandler(UIModule):
    """The page navbar"""

    def render(self):
        return self.render_string("modules/navbar.html", navbar=NAVBAR)


class ImageDisplayHandler(UIModule):
    """A Picpocket image"""

    def render(self, image: Optional[Image] = None, thumbnail: bool = False):
        if image and image.full_path:
            mime = mime_type(image.full_path)
        else:
            mime = None

        return self.render_string(
            "modules/image.html",
            image=image,
            mime=mime,
        )


class TagDisplayHandler(UIModule):
    """A Picpocket tag and children"""

    def render(self, tags: dict[str, dict], parent: Optional[str] = None):
        return self.render_string(
            "modules/tags.html",
            tags=tags,
            parent=parent,
        )


NAVBAR = {
    "home": Endpoint(
        f"{URL_BASE}",
        "It's PicPocket!",
        "The root of the PicPocket API",
        handler=ApiRootHandler,
    ),
    "locations": Endpoint(
        f"{URL_BASE}/locations",
        "Image Sources & Destinations",
        (
            "Sources you can import images from (e.g., your camera), "
            "and destinations you store images (e.g., your Pictures directory)."
        ),
        handler=LocationsHandler,
    ),
    "images": Endpoint(
        f"{URL_BASE}/images",
        "Your Images",
        (
            "Search through and view your images, tag them, and add "
            "metadata that makes them easier to find and categorize."
        ),
        handler=ImagesHandler,
    ),
    "tags": Endpoint(
        f"{URL_BASE}/tags",
        "Image Tags",
        (
            "Browse the tags you've applied to the images in your collection, "
            "Add/update tag descriptions, or move tags to keep them better "
            "organized."
        ),
        handler=TagsHandler,
    ),
    "tasks": Endpoint(
        f"{URL_BASE}/tasks",
        "Import Images",
        (
            "preconfigured jobs for importing images from your "
            "devices to the places you store them. "
            "Tasks can automatically apply information to the images "
            "they copy."
        ),
        handler=TasksHandler,
    ),
}


ENDPOINTS: dict[str, dict[str, Endpoint]] = {
    "locations": {
        "add": Endpoint(
            f"{NAVBAR['locations'].path}/add",
            "Add a new location",
            (
                "Add a new source to import images from, or a new "
                "destination to PicPocket."
            ),
            handler=LocationsAddHandler,
            submit="Create",
            parameters=[
                {
                    "name": "name",
                    "description": (
                        "What to call your location. Location names must be unique."
                    ),
                    "required": True,
                    "input": "text",
                    "label": "Name:",
                },
                {
                    "name": "description",
                    "description": "A brief explanation of what the location is",
                    "required": False,
                    "input": "textarea",
                    "label": "Description:",
                },
                {
                    "name": "path",
                    "description": (
                        "Where the location is on your computer. "
                        "This should be left blank if the location isn't "
                        "mounted in a consistent location, or if multiple "
                        "devices share this path. This must be supplied if "
                        "the location isn't removable."
                    ),
                    "required": False,
                    "input": "text",
                    "label": "Path:",
                },
                {
                    "name": "type",
                    "description": (
                        "A source is a location images are imported from "
                        "(e.g., a camera) or a destination that images are "
                        "copied to (e.g., your Pictures directory). "
                    ),
                    "required": True,
                    "input": "select",
                    "options": ["Source", "Destination"],
                    "label": "Type:",
                },
                {
                    "name": "removable",
                    "description": (
                        "Whether the location is permanently mounted "
                        "or removable media."
                    ),
                    "required": False,
                    "default": True,
                    "input": "checkbox",
                    "label": "Removable:",
                },
            ],
        ),
        "list": Endpoint(
            f"{NAVBAR['locations'].path}/list",
            "List Locatoins",
            "See the locations PicPocket knows about.",
            handler=LocationsListHandler,
        ),
    },
    "images": {
        "search": Endpoint(
            f"{NAVBAR['images'].path}/search",
            "Search Images",
            "Find images stored in PicPocket",
            handler=ImagesSearchHandler,
            submit="Search",
            parameters=[
                {
                    "name": "filter",
                    "description": "Filter results based on one or more property.",
                    "required": False,
                    "type": "filter",
                    "properties": [
                        ["name", {"label": "Name", "type": "text"}],
                        ["extension", {"label": "Extension", "type": "text"}],
                        ["creator", {"label": "Creator", "type": "text"}],
                        ["location", {"label": "Location", "type": "option"}],
                        ["path", {"label": "Path", "type": "text"}],
                        ["title", {"label": "Title", "type": "text"}],
                        ["caption", {"label": "Caption", "type": "text"}],
                        ["alt", {"label": "Alt", "type": "text"}],
                        ["rating", {"label": "Rating", "type": "number"}],
                        ["creation_date", {"label": "Creation Date", "type": "date"}],
                        [
                            "last_modified",
                            {"label": "Last-Modified Date", "type": "date"},
                        ],
                    ],
                },
                {
                    "name": "order",
                    "description": "The order to sort images.",
                    "required": False,
                    "type": "order",
                    "options": [
                        ["Name", "name"],
                        ["Extension", "extension"],
                        ["Creator", "creator"],
                        ["Location", "location"],
                        ["Path", "path"],
                        ["Title", "title"],
                        ["Caption", "caption"],
                        ["Alt", "alt"],
                        ["Rating", "rating"],
                        ["Creation Date", "creation_date"],
                        ["Last-Modified Date", "last_modified"],
                    ],
                },
                {
                    "name": "reachable",
                    "description": "Whether the image file is currently accessible",
                    "required": False,
                    "type": "select",
                    "input": "select",
                    "options": ["", "No", "Yes"],
                    "label": "Reachable:",
                },
                {
                    "name": "tagged",
                    "description": "Whether the image has been tagged.",
                    "required": False,
                    "type": "select",
                    "input": "select",
                    "options": ["", "No", "Yes"],
                    "label": "Tagged:",
                },
                {
                    "name": "any_tags",
                    "description": "Only return images with at least one matching tag.",
                    "required": False,
                    "type": "text",
                    "input": "textarea",
                    "label": "Any Tags (one per line):",
                },
                {
                    "name": "all_tags",
                    "description": "Only return images with all supplied tags",
                    "required": False,
                    "type": "text",
                    "input": "textarea",
                    "label": "All Tags (one per line):",
                },
                {
                    "name": "no_tags",
                    "description": "Only return images without any supplied tags",
                    "required": False,
                    "type": "text",
                    "input": "textarea",
                    "label": "No Tags (one per line):",
                },
            ],
        ),
        "upload": Endpoint(
            f"{NAVBAR['images'].path}/upload",
            "Upload Image",
            "Add a copy of an image to PicPocket.",
            handler=ImagesUploadHandler,
            submit="Upload",
            parameters=[
                {
                    "name": "location",
                    "description": "The location to copy the image to",
                    "required": True,
                    "input": "select",
                    "label": "Location:",
                },
                {
                    "name": "path",
                    "description": (
                        "Where to save the image copy (relative to location)"
                    ),
                    "required": False,
                    "input": "text",
                    "label": "Path:",
                },
                {
                    "name": "file",
                    "description": "The image to add",
                    "required": True,
                    "input": "file",
                    "label": "Choose File:",
                },
                {
                    "name": "creator",
                    "description": "Who created the image",
                    "required": False,
                    "input": "text",
                    "label": "Creator:",
                },
                {
                    "name": "title",
                    "description": "The title of the image",
                    "required": False,
                    "input": "text",
                    "label": "Title:",
                },
                {
                    "name": "caption",
                    "description": "The caption of the image",
                    "required": False,
                    "input": "text",
                    "label": "Caption:",
                },
                {
                    "name": "alt",
                    "description": "A description of the image",
                    "required": False,
                    "input": "text",
                    "label": "Alt Text:",
                },
                {
                    "name": "rating",
                    "description": "Your rating of the image",
                    "required": False,
                    "input": "number",
                    "label": "Rating:",
                },
                {
                    "name": "tags",
                    "description": "Tags to apply to the image.",
                    "required": False,
                    "input": "tags",
                    "label": "Tags:",
                },
            ],
        ),
        "find": Endpoint(
            f"{NAVBAR['images'].path}/find",
            "Find an image",
            "Find an image from its full path.",
            handler=ImagesFindHandler,
            submit="Find",
            parameters=[
                {
                    "name": "path",
                    "description": "The full path to the image.",
                    "required": True,
                    "input": "text",
                    "label": "Path:",
                },
            ],
        ),
        "verify": Endpoint(
            f"{NAVBAR['images'].path}/verify",
            "Verify Images",
            "Check that images in PicPocket match images on-disk.",
            handler=ImagesVerifyHandler,
            submit="Verify",
            parameters=[
                {
                    "name": "location",
                    "description": "Only include images at this location",
                    "required": False,
                    "input": "select",
                    "label": "Location:",
                },
                {
                    "name": "path",
                    "description": "Only include images within this directory.",
                    "required": False,
                    "input": "text",
                    "label": "Path:",
                },
                {
                    "name": "exif",
                    "description": (
                        "Update EXIF data info even if images haven't been modified."
                    ),
                    "required": False,
                    "input": "checkbox",
                    "label": "Reparse EXIF:",
                },
            ],
        ),
    },
    "tags": {
        "add": Endpoint(
            f"{NAVBAR['tags'].path}/add",
            "Add Tag",
            "Create a New Tag (you can create tags when tagging images too).",
            handler=TagsAddHandler,
            submit="Create",
            parameters=[
                {
                    "name": "name",
                    "description": "The name of the tag",
                    "required": True,
                    "input": "text",
                    "label": "Name:",
                },
                {
                    "name": "description",
                    "description": "A description of the tag",
                    "required": False,
                    "input": "textarea",
                    "label": "Description:",
                },
            ],
        ),
        "list": Endpoint(
            f"{NAVBAR['tags'].path}/list",
            "Tags",
            "Get the list of all tags in PicPocket.",
            handler=TagsListHandler,
        ),
    },
    "tasks": {
        "add": Endpoint(
            f"{NAVBAR['tasks'].path}/add",
            "Create Task",
            "Create a new image import task",
            handler=TasksAddHandler,
            submit="Create",
            parameters=[
                {
                    "name": "name",
                    "description": (
                        "What to call your location. Location names must be unique."
                    ),
                    "required": True,
                    "input": "text",
                    "label": "Name:",
                },
                {
                    "name": "source",
                    "description": "Where to copy images from",
                    "required": True,
                    "input": "select",
                    "label": "Source:",
                },
                {
                    "name": "destination",
                    "description": "Where to save images to",
                    "required": True,
                    "input": "select",
                    "label": "Destination:",
                },
                {
                    "name": "description",
                    "description": "An explanation of what the task does",
                    "required": False,
                    "input": "textarea",
                    "label": "Description:",
                },
                {
                    "name": "creator",
                    "description": "Who to list as the creator of imorted images",
                    "required": False,
                    "input": "text",
                    "label": "Creator:",
                },
                {
                    "name": "tags",
                    "description": "What tags to apply to imported images",
                    "required": False,
                    "input": "textarea",
                    "label": "Tags:",
                },
                {
                    "name": "source_path",
                    "description": "Where to look for images",
                    "required": False,
                    "input": "text",
                    "label": "Source Path (relative to source root):",
                },
                {
                    "name": "destination_format",
                    "description": "Where to save copied images",
                    "required": False,
                    "input": "text",
                    "label": "Destination Format (relative to source root):",
                },
                {
                    "name": "file_formats",
                    "description": "What kinds of files to fetch",
                    "required": False,
                    "input": "textarea",
                    "label": "File Formats (one per line):",
                },
            ],
        ),
        "list": Endpoint(
            f"{NAVBAR['tasks'].path}/list",
            "List Tasks",
            "List all tasks.",
            handler=TasksListHandler,
        ),
    },
}


ACTIONS: dict[str, dict[str, Endpoint]] = {
    "locations": {
        "get": Endpoint(
            f"{URL_BASE}/location/{{id}}",
            "Get Location",
            "Get information about an existing location.",
            handler=LocationsGetHandler,
        ),
        "mount": Endpoint(
            f"{URL_BASE}/location/{{id}}/mount",
            "Mount Location",
            "Set the current path to a location.",
            handler=LocationsMountHandler,
            submit="Mount",
            parameters=[
                {
                    "name": "path",
                    "description": "Where the location should be mounted",
                    "required": True,
                    "input": "text",
                    "label": "Path:",
                },
            ],
        ),
        "unmount": Endpoint(
            f"{URL_BASE}/location/{{id}}/unmount",
            "Unmount Location",
            "Unset the mount point for a location.",
            handler=LocationsUnmountHandler,
            submit="Unmount",
            parameters=[],
        ),
        "import": Endpoint(
            f"{URL_BASE}/location/{{id}}/import",
            "Import Location",
            (
                "Add images stored in a destination to PicPocket. "
                "Your image files will not be moved. "
                "This action may take a while and will not give any feedback "
                "until it is complete."
            ),
            handler=LocationsImportHandler,
            submit="Import",
            parameters=[
                {
                    "name": "creator",
                    "description": "Who made the images being imported",
                    "required": False,
                    "input": "text",
                    "label": "Creator:",
                },
                {
                    "name": "tags",
                    "description": "Tags to apply to all imported images.",
                    "required": False,
                    "input": "tags",
                    "label": "Tags:",
                },
                {
                    "name": "batch_size",
                    "description": "Have PicPocket save changes after this many images",
                    "required": False,
                    "input": "text",
                    "label": "Batch Size:",
                },
                {
                    "name": "file_formats",
                    "description": (
                        "Only import files of these types. If not supplied, "
                        "all of PicPocket's default file types will be included."
                    ),
                    "required": False,
                    "input": "textarea",
                    "label": "File Formats to install (one per line):",
                },
            ],
        ),
        "edit": Endpoint(
            f"{URL_BASE}/location/{{id}}/edit",
            "Edit Location",
            "Update information on an existing location.",
            handler=LocationsEditHandler,
            submit="Edit",
            parameters=[
                {
                    "name": "new_name",
                    "description": (
                        "What to call your location. Location names must be unique."
                    ),
                    "required": False,
                    "input": "text",
                    "label": "Name:",
                },
                {
                    "name": "description",
                    "description": "A brief explanation of what the location is",
                    "required": False,
                    "input": "textarea",
                    "label": "Description:",
                },
                {
                    "name": "path",
                    "description": (
                        "Where the location is on your computer. "
                        "This should be left blank if the location isn't "
                        "mounted in a consistent location, or if multiple "
                        "devices share this path. This must be supplied if "
                        "the location isn't removable."
                    ),
                    "required": False,
                    "input": "text",
                    "label": "Path:",
                },
                {
                    "name": "type",
                    "description": (
                        "A source is a location images are imported from "
                        "(e.g., a camera) or a destination that images are "
                        "copied to (e.g., your Pictures directory). "
                    ),
                    "required": True,
                    "input": "select",
                    "options": ["Source", "Destination"],
                    "label": "Type:",
                },
                {
                    "name": "removable",
                    "description": (
                        "Whether the location is permanently mounted "
                        "or removable media."
                    ),
                    "required": False,
                    "input": "checkbox",
                    "label": "Removable:",
                },
            ],
        ),
        "remove": Endpoint(
            f"{URL_BASE}/location/{{id}}/remove",
            "Remove Location",
            "Remove a location from PicPocket (your files will not be touched).",
            handler=LocationsRemoveHandler,
            submit="Remove",
            parameters=[
                {
                    "name": "force",
                    "description": (
                        "Remove the location even if images exist at this "
                        "location in PicPocket. Image files will not be touched."
                    ),
                    "required": False,
                    "input": "checkbox",
                    "label": "Force (remove associated images from PicPocket):",
                },
            ],
        ),
    },
    "images": {
        "get": Endpoint(
            f"{URL_BASE}/image/{{id}}",
            "Get Image",
            "View an image and its information.",
            handler=ImagesGetHandler,
        ),
        "edit": Endpoint(
            f"{URL_BASE}/image/{{id}}/edit",
            "Edit image attributes",
            "Edit information about an image",
            handler=ImagesEditHandler,
            submit="Edit",
            parameters=[
                {
                    "name": "creator",
                    "description": "Who created the image",
                    "required": False,
                    "input": "text",
                    "label": "Creator:",
                },
                {
                    "name": "title",
                    "description": "The title of the image",
                    "required": False,
                    "input": "text",
                    "label": "Title:",
                },
                {
                    "name": "caption",
                    "description": "The caption of the image",
                    "required": False,
                    "input": "text",
                    "label": "Caption:",
                },
                {
                    "name": "alt",
                    "description": "A description of the image",
                    "required": False,
                    "input": "text",
                    "label": "Alt Text:",
                },
                {
                    "name": "rating",
                    "description": "Your rating of the image",
                    "required": False,
                    "input": "number",
                    "label": "Rating:",
                },
                {
                    "name": "existing-tags",
                    "description": "Tags to apply to all imported images.",
                    "required": False,
                    "input": "hidden",
                    "label": "",
                },
                {
                    "name": "tags",
                    "description": "Tags to apply to all imported images.",
                    "required": False,
                    "input": "tags",
                    "label": "Tags:",
                },
            ],
        ),
        "move": Endpoint(
            f"{URL_BASE}/image/{{id}}/move",
            "Move Image",
            "Move an image file.",
            handler=ImagesMoveHandler,
            submit="Move",
            parameters=[
                {
                    "name": "path",
                    "description": "The path (relative to the new location)",
                    "required": True,
                    "input": "text",
                    "label": "Path:",
                },
                {
                    "name": "location",
                    "description": "The location to move the image to",
                    "required": True,
                    "input": "select",
                    "label": "Location:",
                },
            ],
        ),
        "remove": Endpoint(
            f"{URL_BASE}/image/{{id}}/remove",
            "Remove Image",
            "Remove an image from PicPocket.",
            handler=ImagesRemoveHandler,
            submit="Remove",
            parameters=[
                {
                    "name": "delete",
                    "description": "Delete the image file",
                    "required": False,
                    "input": "checkbox",
                    "label": "Delete:",
                },
            ],
        ),
        "file": Endpoint(
            f"{URL_BASE}/file/{{id}}",
            "Get Image File",
            "View an image file.",
            handler=ImagesFileHandler,
        ),
    },
    "tags": {
        "get": Endpoint(
            f"{URL_BASE}/tag",
            "Get Tag",
            "Get information about a tag.",
            handler=TagsGetHandler,
        ),
        "move": Endpoint(
            f"{URL_BASE}/tag/move",
            "Move Tag",
            "Move a tag to a new location.",
            handler=TagsMoveHandler,
            submit="move",
            parameters=[
                {
                    "name": "new",
                    "description": "The new name",
                    "required": True,
                    "input": "text",
                    "label": "New Name:",
                },
                {
                    "name": "cascade",
                    "description": "Move child tags too",
                    "required": False,
                    "input": "checkbox",
                    "label": "Cascade:",
                },
            ],
        ),
        "edit": Endpoint(
            f"{URL_BASE}/tag/edit",
            "Edit Tag",
            "Edit the description of a tag.",
            handler=TagsEditHandler,
            submit="edit",
            parameters=[
                {
                    "name": "description",
                    "description": "A description of the tag",
                    "required": False,
                    "input": "textarea",
                    "label": "Description:",
                },
            ],
        ),
        "remove": Endpoint(
            f"{URL_BASE}/tag/remove",
            "Remove Tag",
            "Remove a tag form PicPocket.",
            handler=TagsRemoveHandler,
            submit="remove",
            parameters=[
                {
                    "name": "cascade",
                    "description": "Delete all descendents too",
                    "required": False,
                    "input": "checkbox",
                    "label": "Cascade:",
                },
            ],
        ),
        "images": Endpoint(
            f"{URL_BASE}/tag/images",
            "Get Tagged Images",
            "Get images tagged with a tag (or its descendents).",
            handler=TagsImagesHandler,
        ),
    },
    "tasks": {
        "get": Endpoint(
            f"{URL_BASE}/task/{{name}}",
            "Get Task",
            "Get information about an existing task.",
            handler=TasksGetHandler,
        ),
        "run": Endpoint(
            f"{URL_BASE}/task/{{name}}/run",
            "Run Task",
            (
                "Run an import task. "
                "Import tasks will copy matching images "
                "from the source to the destination "
                "(without modifying the source location), "
                "adding metadata as required. By default, import tasks "
                "will only look for images created since the last time "
                "they ran."
            ),
            handler=TasksRunHandler,
            submit="run",
            parameters=[
                {
                    "name": "since",
                    "description": "Only import images since this date",
                    "required": False,
                    "input": "datetime-local",
                    "label": "Since:",
                },
                {
                    "name": "full",
                    "description": "Ignore since/last-ran date when importing",
                    "required": False,
                    "input": "checkbox",
                    "label": "Full:",
                },
            ],
        ),
        "edit": Endpoint(
            f"{URL_BASE}/task/{{name}}/edit",
            "Edit Task",
            "Edit a task",
            handler=TasksEditHandler,
            submit="Edit",
            parameters=[
                {
                    "name": "source",
                    "description": "Where to copy images from",
                    "required": True,
                    "input": "select",
                    "label": "Source:",
                },
                {
                    "name": "destination",
                    "description": "Where to save images to",
                    "required": True,
                    "input": "select",
                    "label": "Destination:",
                },
                {
                    "name": "description",
                    "description": "A description of the task",
                    "required": False,
                    "input": "textarea",
                    "label": "Description:",
                },
                {
                    "name": "creator",
                    "description": "Who to list as the creator of imorted images",
                    "required": False,
                    "input": "text",
                    "label": "Creator:",
                },
                {
                    "name": "tags",
                    "description": "What to tag imorted images",
                    "required": False,
                    "input": "textarea",
                    "label": "Tags:",
                },
                {
                    "name": "source_path",
                    "description": "Where to look for images",
                    "required": False,
                    "input": "text",
                    "label": "Source Path (relative to source root):",
                },
                {
                    "name": "destination_format",
                    "description": "Where to save copied images",
                    "required": False,
                    "input": "text",
                    "label": "Destination Format (relative to source root):",
                },
                {
                    "name": "file_formats",
                    "description": "What kinds of files to fetch",
                    "required": False,
                    "input": "textarea",
                    "label": "File Formats (one per line):",
                },
            ],
        ),
        "remove": Endpoint(
            f"{URL_BASE}/task/{{name}}/remove",
            "Remove Task",
            "Delete a task.",
            handler=TasksRemoveHandler,
            submit="Remove",
        ),
    },
}

REPLACEMENTS: dict[str, dict[str, str]] = {
    "images": {"id": r"([^/]+)"},
    "locations": {"id": r"([^/]+)"},
    "tags": {},
    "tasks": {"name": r"([^/]+)"},
}


def make_app(picpocket: PicPocket, local_actions: bool = False) -> Application:
    """Make a tornado Application with all expected routing

    Args:
        picpocket: The API
        local_actions: Include endpoints designed for people only
            accessing PicPocket from their local machine.

    Returns:
        An instantiated tornado Application
    """
    # tornado is expecting optional list, not optional sequence and in
    # python lists are invariant, so we can't just pass list[Rule].
    # we could pass sequence[Rule] but we want to optionally call
    # append, which sequences don't have. oh well
    routes: list[
        tornado.routing.Rule
        | list[Any]
        | tuple[str | tornado.routing.Matcher, Any]
        | tuple[str | tornado.routing.Matcher, Any, dict[str, Any]]
        | tuple[str | tornado.routing.Matcher, Any, dict[str, Any], str]
    ] = [
        tornado.web.url(r"/style\.css", StyleHandler),
        tornado.web.url(r"/scripts\.js", ScriptHandler),
        tornado.web.url(r"/", RootHandler, name="root"),
    ]

    special_actions = set()
    if local_actions:
        match sys.platform:
            case "darwin":
                special_actions.add("show-in-finder")
                routes.append(
                    tornado.web.url(
                        rf"{URL_BASE}/show-in-finder/(\d+)",
                        ShowInFinderHandler,
                        {"picpocket": picpocket},
                        name="show-in-finder",
                    )
                )

    for group, group_endpoint in NAVBAR.items():
        if group_endpoint.handler:
            routes.append(
                tornado.web.url(
                    f"{group_endpoint.path}/",
                    group_endpoint.handler,
                )
            )
            routes.append(
                tornado.web.url(
                    f"{group_endpoint.path}",
                    group_endpoint.handler,
                    name=group,
                )
            )

        if group in ENDPOINTS:
            for name, endpoint in ENDPOINTS[group].items():
                if endpoint.handler:
                    routes.append(
                        tornado.web.url(
                            f"{endpoint.path}/",
                            endpoint.handler,
                            {
                                "endpoint": endpoint,
                                "picpocket": picpocket,
                                "local_actions": special_actions,
                            },
                        )
                    )
                    routes.append(
                        tornado.web.url(
                            endpoint.path,
                            endpoint.handler,
                            {
                                "endpoint": endpoint,
                                "picpocket": picpocket,
                                "local_actions": special_actions,
                            },
                            name=f"{group}-{name}",
                        )
                    )

        if group in ACTIONS:
            for name, endpoint in ACTIONS[group].items():
                if endpoint.handler:
                    routes.append(
                        tornado.web.url(
                            f"{endpoint.path.format(**REPLACEMENTS[group])}/",
                            endpoint.handler,
                            {
                                "endpoint": endpoint,
                                "picpocket": picpocket,
                                "local_actions": special_actions,
                            },
                        )
                    )
                    routes.append(
                        tornado.web.url(
                            endpoint.path.format(**REPLACEMENTS[group]),
                            endpoint.handler,
                            {
                                "endpoint": endpoint,
                                "picpocket": picpocket,
                                "local_actions": special_actions,
                            },
                            name=f"{group}-{name}",
                        )
                    )

    return Application(
        routes,
        template_path=TEMPLATE_DIRECTORY,
        ui_modules={
            "DisplayImage": ImageDisplayHandler,
            "DisplayTags": TagDisplayHandler,
            "NavBar": NavBarHandler,
        },
    )


async def run_server(
    picpocket: PicPocket, port: int = DEFAULT_PORT, local_actions: bool = False
):
    """Run a PicPocket web server

    Run the web interface for PicPocket. Once started, this function
    will hang, continuing to host the server until a shutdown is requrested

    Args:
        picpocket: The instantiated API
        port: The port to run the server on
        local_actions: Include endpoints designed for people only
            accessing PicPocket from their local machine.
    """

    shutdown = asyncio.Event()
    application = make_app(picpocket, local_actions=local_actions)
    application.listen(port)
    await shutdown.wait()
