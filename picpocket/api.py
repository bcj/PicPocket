from __future__ import annotations

"""The public API for PicPocket

Both the REST and the CLI interfaces for PicPocket are built atop this API.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol

from picpocket.configuration import Configuration
from picpocket.database.logic import Comparison
from picpocket.database.types import Image, Location, Tag, Task
from picpocket.internal_use import NotSupplied
from picpocket.version import Version

NULL_SYMBOL = "!"


class CredentialType(Enum):
    """Which kind of credentials are required for backend access.

    This enum is used by the API to determine what kind of prompt to
    provide.
    """

    NONE = "n/a"
    PASSWORD = "password"
    USER_PASSWORD = "user_password"
    FILE = "file"


class PicPocket(Protocol):
    """The PicPocket interface"""

    BACKEND_NAME: str
    CREDENTIAL_TYPE: CredentialType

    @classmethod
    def load(cls, configuration: Configuration) -> PicPocket:
        """Load a PicPocket API

        .. warning::
            Instead of calling this directly, you should use
            :func:`picpocket.load`

        Args:
            configuration: An object representing the PicPocket
                configuration to load.

        Returns:
            The API object to interact with PicPocket through
        """

    @property
    def configuration(self) -> Configuration:
        """Fetch the PicPocket configuration file

        Returns:
            An object representing the PicPocket configuration file.
        """

    @property
    def mounts(self) -> dict[int, Path]:
        """The set of mounted locations

        .. note:
            This dict should not be edited directly.

        Returns:
            A dictionary representing mounted locations
        """

    @classmethod
    def parse_connection_info(
        cls, directory: Path, *, store_credentials: Optional[bool] = None
    ) -> tuple[dict[str, str | int | bool], Any]:
        """Parse connection info for the database

        Parse information required for connecting to the underlying
        database PicPocket is built on top of. Backends may take
        whatever argumetns they want as long as they accept `directory`
        and `store_credentials`

        Args:
            directory: The directory that the PicPocket configuration is
                being saved to.
            *args: Any positional arguments required by the database
            store_credentials: Whether PicPocket should save database
                credentials in its config file. While
                implementation-specific, it can generally be assumed
                that leaving this blank will tell PicPocket to only
                prompt for password if a database password exists.
            **kwargs Any positional arguments required by the database.
        """

    async def initialize(self):
        """Create a new PicPocket store.

        Initialize a backend for use as a PicPocket database. This step
        will be where the backend creates and configures the underlying
        database. It can be assumed that this function will raise an
        exception if anything fails.
        """

    def get_api_version(self) -> Version:
        """Get the version of the PicPocket API

        This should always match package version.

        Returns:
            A Version object.
        """

    async def get_version(self) -> Version:
        """Get teh version of the backend API

        Returns:
            The version of the backend interface being used.
        """

    async def matching_version(self) -> bool:
        """Check version compatibility

        Check whether the configured backend is compatible with this API
        """

    async def import_data(
        self,
        path: Path,
        locations: Optional[list[str] | dict[str, Optional[Path]]] = None,
    ):
        """Import a PicPocket backup

        Load data (locations, tasks, images, tags) from a PicPocket
        backup created using :meth:`.export_data`. This is the
        recommended way to migrate between backends.

        This method is safe to rerun as PicPocket will skip duplicates
        instead of overwriting.

        .. note::
            This file will not contain the images themselves, just the
            metadata you've created for the image (tags, captions,
            alt text, etc.).

        Args:
            path: The JSON file to load data from.
            locations: Only import data related to this set of
                locations. This can be supplied either as a list of
                locations or as a dict of location/path pairs. If a
                path is provided, it will be mounted prior to loading
                images and then unmounted afterward. When importing a
                location without a set path, this must be provided as a
                dict. For locations with paths definied within the
                backup, you can pass `None` as the path to use the
                default location.
        """

    async def export_data(
        self, path: Path, locations: Optional[list[str | int]] = None
    ):
        """Create a PicPocket backup

        Export data (locations, tasks, iamges, tags) from PicPocket.
        This is the recommended way to migrate between backends.

        .. warning::
            This file will not contain the images themselves, just the
            metadata you've created for the image (tags, captions,
            alt text, etc.).

        Args:
            path: Where to save teh JSON file to store data to.
            locations: Only export images and task related to this
                location.
        """

    async def add_location(
        self,
        name: str,
        path: Optional[Path] = None,
        *,
        description: Optional[str] = None,
        source: bool = False,
        destination: bool = False,
        removable: bool = False,
    ) -> int:
        """Add a new location to PicPocket.

        Locations represent sources to fetch images from (e.g., cameras)
        and storage locations to store data in. A location must be
        specified either as a source to import images from, a
        destination to import images to, or both.

        Args:
            name: The (unique) name of the location being added. E.g.
                photos, "EOS 6D", phone
            path: The path where the location is/gets mounted. If this
                path is not consistent (or not unique), you may want to
                leave this blank and instead mount/unmount the drive as
                necessary.
            description: A text description of what the location is/how
                it is used. E.g., "main photo storage", "my digital
                camera"
            source: Whether the location is somewhere images may be
                copied from (to a new location)
            destination: Whether the location is somewhere images may be
                compied to.
            removable: Whether the location is a permanent or removable
                storage device.

        Returns:
            The integer id representing the location
        """

    async def edit_location(
        self,
        name_or_id: str | int,
        new_name: Optional[str] = None,
        /,
        *,
        path: Optional[Path | NotSupplied] = NotSupplied(),
        description: Optional[str | NotSupplied] = NotSupplied(),
        source: Optional[bool] = None,
        destination: Optional[bool] = None,
        removable: Optional[bool] = None,
    ):
        """Edit a PicPocket location.

        Edit information about about a PicPocket location.

        Args:
            name/id: the name or id of the location.
            new_name: What to rename the location to.
            path: Where the location gets mounted.
            description: A description of the location.
            source: Whether the location is a place images are imported from
            destination: Whether the location is a place images are imported
                to.
            removable: Whether the location is a permanent or removable
                storage device.
        """

    async def remove_location(
        self,
        name_or_id: int | str,
        /,
        *,
        force: bool = False,
    ) -> bool:
        """Remove a location from PicPocket.

        The location will not be removed if it has images associated
        with it unless explicitly asked. Even in that case, it will not
        touch the image files on disk.

        Args:
            name/id: the name or of the location.
            force: Remove the location even if it currently has images
                associated with it and remove those images from the
                database.

        Returns:
            Whether the location was deleted.
        """

    async def get_location(
        self,
        name_or_id: str | int,
        /,
        *,
        expect: bool = False,
    ) -> Optional[Location]:
        """Get information about a location

        Args:
            name/id: The location to find
            expect: Error if the location doesn't exist

        Returns:
            The matching location if it exists.
        """

    async def list_locations(self) -> list[Location]:
        """Fetch all known locations"""

    async def mount(self, name_or_id: str | int, /, path: Path):
        """Supply a path where a location is currently available

        Mount a location to a specific path. For removable locations
        without unique or consistent mount points, this is how you alert
        PicPocket to its present location. This will also work for
        locations that have set attach points but are temporarily
        available at a different location. Mounting an already-mounted
        location will replace the previous mount point.

        Args:
            name/id: The location to mount
            path: Where to mount the location
        """

    async def unmount(self, name_or_id: str | int):
        """Remove a temporary mount point

        Unmount a location that was previously mounted. Unmounting a
        drive that isn't mounted won't cause an error.

        Args:
            name/id: The location to mount
        """

    async def import_location(
        self,
        name_or_id: str | int,
        /,
        *,
        file_formats: Optional[set[str]] = None,
        batch_size: int = 1000,
        creator: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> list[int]:
        """Import all images from a location

        Import all images that are stored within a location. If an image
        already exists within PicPocket, its user-supplied won't be
        updated but properties of the file itself (such as dimensions or
        exif data) will be updated in PicPocket if its changed on disk.

        Args:
            name/id: The location to import
            file_formats: Only import images that have these suffixes.
                Suffixes can be supplied with or without leading dot.
                If not supplied, the PicPocket default file formats
                will be imported.
            batch_size: How often to commit while importing images.
            creator: Mark all images as having been created by this
                person.
            tags: Apply all these tags to all imported images.

        Returns:
            The ids of all images that were added (or edited)
        """

    async def add_task(
        self,
        name: str,
        source: str | int,
        destination: str | int,
        *,
        description: Optional[str] = None,
        creator: Optional[str] = None,
        tags: Optional[list[str]] = None,
        source_path: Optional[str] = None,
        destination_format: Optional[str] = None,
        file_formats: Optional[set[str]] = None,
        force: bool = False,
    ):
        """Add a repeatable task to PicPocket.

        .. todo::
            Perform operations on images, clean up path stuff, scheduled
            and automatic tasks

        .. warning::
            This method will be changing substantially as support for
            other types of task are added.

        Add a task to PicPocket. Currently, all supported tasks are
        imports from one known location to another. Support for things
        like converting images on import are forthcoming. Images will be
        copied from the source location without modifying the source
        image. Tasks will refuse to overwrite existing files on import.

        see :mod:`picpocket.tasks`

        Args:
            name: What to call the task (must be unique)
            source: The name/id of the location to import images from
            destination: The name/id of the location to copy images to
            creator: Who to list as the creator of all imported images
            tags: Apply these tags to all imported images
            source_path: Where, (relative to the source location's root)
                to start looking for images. If not supplied, root will
                be used. The following dyamic directory names are allowed:

                * {year}: A year
                * {month}: A month
                * {day}: A day
                * {date:FORMAT}: A date in the supplied format
                * {regex:PATTERN}: A name that matches a regex
                * {str:RAW}: A folder name that contains {
            destination_format: Where (relative to the destination root)
                images should be copied to. This is supplied as a format
                string with the following allowed formatters:

                * path: The source filepath (relative to the source) root.
                * file: The file's name
                * name: The file's name (without extension)
                * extension: The file's extension (without the leading
                  dot).
                * uuid: A UUID4 hex
                * date: A date object representing the source image's
                  last modified time. You can supply the format to save
                  the date using strftime formatting (e.g.
                  `date:%Y-%m-%d-%H-%M-%S`)
                * hash: A hash of the image contents
                * index: A 1-indexed number representing the order
                  images are encountered by the running task. PicPocket
                  makes no promised about the order images are added
            file_formats: Only import images that have these suffixes.
                Suffixes can be supplied with or without leading dot.
                If not supplied, the PicPocket default file formats
                will be imported.
            force: Overwrite any previously-existing task with this name
        """

    async def run_task(
        self,
        name: str,
        *,
        since: Optional[datetime] = None,
        full: bool = False,
    ) -> list[int]:
        """Run a task

        .. todo::
            Allow offsets for last ran.

        Running a task will never overwrite an image file, but it will
        re-add images that were deleted if the source image still
        matches all criteria. When running a task, the time the task
        previously ran will be supplied and any specified date-based
        path segments from before that last ran date will be skipped, as
        will any files with last-modified dates that are earlier.

        Args:
            name: The name of the task to run
            since: Ignore files with last-modified dates older than this
                date and in folders representing earlier dates. Ignored
                if full is supplied.
            full: Don't filter directories based on the last-run date
                of the task.

        Returns:
            The ids of all imported images.
        """

    async def remove_task(self, name: str):
        """Remove a task

        Running this on a non-existent task will not error.

        Args:
            name The name of the task to remove
        """

    async def get_task(self, name: str) -> Optional[Task]:
        """Get the definition of an existing task"""

    async def list_tasks(self) -> list[Task]:
        """Get all tasks in PicPocket"""

    async def add_image_copy(
        self,
        source: Path,
        name_or_id: str | int,
        destination: Path,
        /,
        *,
        creator: Optional[str] = None,
        title: Optional[str] = None,
        caption: Optional[str] = None,
        alt: Optional[str] = None,
        rating: Optional[int] = None,
        tags: Optional[list[str]] = None,
    ) -> int:
        """Copy an image into PicPocket

        Create a copy of a supplied image and then add that image to
        PicPocket.

        Args:
            source: The image to create a copy of
            name/id: The location to create a copy of the image in
            destination: The path (relative to the location root) to
                copy the image to
            creator: Who made the image
            title: The title of the image
            caption: A caption of the image
            alt: Descriptive text of the image to be used as alt text
            rating: A numeric rating of the image
            tags: Any number of tags to apply to the image

        Returns:
            The id of the copied image
        """

    async def edit_image(
        self,
        id: int,
        *,
        creator: Optional[str | NotSupplied] = NotSupplied(),
        title: Optional[str | NotSupplied] = NotSupplied(),
        caption: Optional[str | NotSupplied] = NotSupplied(),
        alt: Optional[str | NotSupplied] = NotSupplied(),
        rating: Optional[int | NotSupplied] = NotSupplied(),
    ):
        """Edit information about an image.

        Edit user-supplied metadata about an image. For all properties,
        supplying `None` will erase the existing value of that property

        Args:
            id: The image to edit
            creator: Who made the image
            title: The title of the image
            caption: A caption of the image
            alt: Descriptive text of the image to be used as alt text
            rating: A numeric rating of the image
        """

    async def tag_image(self, id: int, tag: str):
        """Apply a tag to an image

        Tags in PicPocket are nestable, and are supplied as lists of
        strings (e.g., `["bird", "goose", "Canada Goose"]`). When adding
        a tag, it's recommended that you don't add its parents.

        Args:
            id: The image to tag
            tag: The tag to apply
        """

    async def untag_image(self, id: int, tag: str):
        """Remove a tag from an image

        .. todo::
            allow cascading?

        Removing a non-existent tag will not error.

        Args:
            id: The image to untag
            tag: The tag to remove
        """

    async def move_image(self, id: int, path: Path, location: Optional[int] = None):
        """Move an image.

        PicPocket will attempt to move both the on-disk location as well
        as its internal record. If the current file location is empty
        and a file exists at the destination, PicPocket will assume the
        file was already moved on-disk and will update its records. In
        all other cases, if a file exists at the destination (either
        on-disk or in PicPocket), PicPocket will error.

        Args:
            id: the image to move
            path: The new location (relative to the root of its
                destination location).
            location: The id of the location to move the image to. If
                unsupplied, the file will be moved within its source
                location.
        """

    async def remove_image(self, id: int, *, delete: bool = False):
        """Remove an image from PicPocket

        PicPocket will only delete the file on-disk if specifically
        requested.

        Args:
            id: The image to remove from PicPocket
            delete: Delete the image on-disk as well. If `True`, the
                image will only be removed from PicPocket if the
                delete is successful
        """

    async def get_image(self, id: int, tags: bool = False) -> Optional[Image]:
        """Get an image in PicPocket

        Args:
            id: The image to fetch
            tags: Whether to fetch the image's tags

        Returns:
            The image matching the id (if it exists)
        """

    async def find_image(self, path: Path, tags: bool = False) -> Optional[Image]:
        """Attempt to find an image given its path

        Args:
            path: The full path to the image
            tags: Whether to fetch the image's tags

        Returns:
            The image, if it exists in PicPocket
        """

    async def verify_image_files(
        self,
        *,
        location: Optional[int] = None,
        path: Optional[Path] = None,
        reparse_exif: bool = False,
    ) -> list[Image]:
        """Check that images in PicPocket exist on-disk

        Check that images exist on-disk and that stored file information
        is accurate. If file metadata (e.g., dimensiosns, exif data) has
        changed, it will be updated as necessary. PicPocket will not
        remove missing images from its database.

        This method will skip any removable locations that aren't
        currently attached.

        Args:
            location: Only check images in this location
            path: Only scan images within this directory
            reparse_exif: Reread EXIF data even if the image hasn't been
                touched

        Returns:
            All images that exist in PicPocket that can't be found
            on-disk.
        """

    async def count_images(
        self,
        filter: Optional[Comparison] = None,
        tagged: Optional[bool] = None,
        any_tags: Optional[list[str]] = None,
        all_tags: Optional[list[str]] = None,
        no_tags: Optional[list[str]] = None,
        reachable: Optional[bool] = None,
    ) -> int:
        """Count the number of images in PicPocket

        Get the number of images in PicPocket that match a criteria.

        You can filter the result on any of the following properties:
         * name: The name of the image (without extension)
         * extension: The file suffix (without leading dot)
         * creator: Who created the image
         * location: Only include images at this location
         * path: The text path, relative to its location's root
         * title: The title of the image
         * caption: The image caption
         * alt: The image alt text
         * rating: The rating of the image.

        Args:
            filter: Only include images that match this filter
            tagged: Only include images that are(n't) tagged
            any_tags: Only include images that are tagged with at least
                one of the supplied tags
            all_tags: Only include images that are tagged with all of
                the supplied tags
            no_tags: Don't include images that have any of the supplied
                tags
            reachable: Only include images that are currently reachable

        Returns:
            The number of images that match the criteria
        """

    async def get_image_ids(
        self,
        filter: Optional[Comparison] = None,
        *,
        tagged: Optional[bool] = None,
        any_tags: Optional[list[str]] = None,
        all_tags: Optional[list[str]] = None,
        no_tags: Optional[list[str]] = None,
        order: Optional[tuple[str, ...]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        reachable: Optional[bool] = None,
    ) -> list[int]:
        """Get the ids of images in PicPocket

        Get the ids of images in PicPocket that match a criteria.

        You can filter and order the result on any of the following
        properties:

        * name: The name of the image (without extension)
        * extension: The file suffix (without leading dot)
        * creator: Who created the image
        * location: Only include images at this location
        * path: The text path, relative to its location's root
        * title: The title of the image
        * caption: The image caption
        * alt: The image alt text
        * rating: The rating of the image.

        When ordering images, properties will be sorted in ascending
        order by default (e.g., for ratings: Lower rated images will be
        supplied first). Putting a minus sign (-) in front of that
        property will sort in descending order instead. You can also
        use the exclamation mark (!) to specify whether images lacking
        a property (e.g., unrated images) should be sorted at the
        beginning or the end (e.g., !rating will order unrated images
        and then worst-to-best; rating! will order unrated images after
        the best images). When supplying unspecified properties in
        descending order, the exclamation mark should be supplied after
        the minus sign (e.g., -!rating will return untagged images and
        then best-to-worst). As well as above properties, 'random' can
        be used to order images randomly. Random ordering can be done
        after properties (e.g., -!rating,random will return images
        unrated and then best to worst, but with unrated images and
        images with a given rating will be returned in a random order).

        .. note::
            Orderings are not preserved across invocations, so running
            repeatedly with increasing offsets is not guaranteed to
            include all images or supply each images exactly once. That
            said, if you don't add/edit/remove images between
            invocations (and don't use random ordering), it should be
            fine.

        Args:
            filter: Only include images that match this filter
            tagged: Only include images that are(n't) tagged
            any_tags: Only include images that are tagged with at least
                one of the supplied tags
            all_tags: Only include images that are tagged with all of
                the supplied tags
            no_tags: Don't include images that have any of the supplied
                tags
            reachable: Only include images that are currently reachable
            order: how to sort the returned ids as a list of properties
            limit: Only return this many image ids
            offset: If limit is supplied, start returing images from
                this offset.
            reachable: Only include images that are(n't) currently
                reachable

        Returns:
            The ids of all images that match this criteria
        """

    async def search_images(
        self,
        filter: Optional[Comparison] = None,
        *,
        tagged: Optional[bool] = None,
        any_tags: Optional[list[str]] = None,
        all_tags: Optional[list[str]] = None,
        no_tags: Optional[list[str]] = None,
        order: Optional[tuple[str, ...]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        reachable: Optional[bool] = None,
    ) -> list[Image]:
        """Search images in PicPocket

        Get images in PicPocket that match a criteria.

        You can filter and order the result on any of the following
        properties:

         * name: The name of the image (without extension)
         * extension: The file suffix (without leading dot)
         * creator: Who created the image
         * location: Only include images at this location
         * path: The text path, relative to its location's root
         * title: The title of the image
         * caption: The image caption
         * alt: The image alt text
         * rating: The rating of the image.

        When ordering images, properties will be sorted in ascending
        order by default (e.g., for ratings: Lower rated images will be
        supplied first). Putting a minus sign (-) in front of that
        property will sort in descending order instead. You can also
        use the exclamation mark (!) to specify whether images lacking
        a property (e.g., unrated images) should be sorted at the
        beginning or the end (e.g., !rating will order unrated images
        and then worst-to-best; rating! will order unrated images after
        the best images). When supplying unspecified properties in
        descending order, the exclamation mark should be supplied after
        the minus sign (e.g., -!rating will return untagged images and
        then best-to-worst). As well as above properties, 'random' can
        be used to order images randomly. Random ordering can be done
        after properties (e.g., -!rating,random will return images
        unrated and then best to worst, but with unrated images and
        images with a given rating will be returned in a random order).

        .. note::
            Orderings are not preserved across invocations, so running
            repeatedly with increasing offsets is not guaranteed to
            include all images or supply each images exactly once. That
            said, if you don't add/edit/remove images between
            invocations (and don't use random ordering), it should be
            fine.

        Args:
            filter: Only include images that match this filter
            tagged: Only include images that are(n't) tagged
            any_tags: Only include images that are tagged with at least
                one of the supplied tags
            all_tags: Only include images that are tagged with all of
                the supplied tags
            no_tags: Don't include images that have any of the supplied
                tags
            reachable: Only include images that are currently reachable
            order: how to sort the returned ids as a list of properties
            limit: Only return this many image ids
            offset: If limit is supplied, start returing images from
                this offset.
            reachable: Only include images that are(n't) currently reachable

        Returns:
            The images that match this criteria
        """

    async def add_tag(
        self,
        tag: str,
        description: Optional[str | NotSupplied] = NotSupplied(),
    ):
        """Add a tag to PicPocket

        Tags in PicPocket are nestable, and are supplied as lists of
        strings (e.g., `["bird", "goose", "Canada Goose"]`). You don't
        need to explicitly add tags (tagging an image will create that
        tag). You only need to add a tag if you want to have a
        description associated with a tag.

        Adding an existing tag will not error, and if supplied, the
        description will be updated.

        Args:
            tag: The tag to add
            description: A description of the tag
        """

    async def move_tag(self, current: str, new: str, /, cascade: bool = True) -> int:
        """Move a tag to a new name

        If a tag already exists with the same name, the two tags will
        be merged (keeping that tag's description).

        .. note::

            Cascade is always based on the supplied tag, not where the
            change was made in the tag. Even if you edit a parent
            section of the tag's name, it will only cascade to this
            tag's children.

        Args:
            current: The name of the tag
            new: The new name of the tag
            cascade: Whether to move child tags as well.

        Returns:
            The number of moved tags
        """

    async def remove_tag(self, tag: str, cascade: bool = False):
        """Remove a tag from PicPocket

        Args:
            tag: The tag to remove
            cascade: If `True`, also remove any tags that are
                descendents of this tag
        """

    async def get_tag(self, name: str, children: bool = False) -> Tag:
        """Get the description of a tag

        Args:
            name: The tag to get the description of
            children: Fetch children as well

        Returns:
            The tag
        """

    async def all_tag_names(self) -> set[str]:
        """Get the names of all used tags

        Returns:
            The list of tags
        """

    async def all_tags(self) -> dict[str, Any]:
        """Return the tags PicPocket is aware of

        Returns:
            A recursive dict representing the known tag structure within
            PicPocket. The outer level will be the names of root level
            tags and for each tag, their value will be a dict containing
            their description and the dict of their child tags.
        """

    async def create_session(
        self,
        data: dict[str, Any],
        expires: Optional[datetime] = None,
    ) -> int:
        """Store temporary data about a user query

        Args:
            data: The JSON-serializable data
            expires: The expiration date for the data (if not supplied,
                the default will be used).

        Returns:
            the session id
        """

    async def get_session(self, session_id: int) -> Optional[dict[str, Any]]:
        """Fetch session data

        Args:
            session_id: The id of the session

        Returns:
            the session data, if it exists
        """

    async def prune_sessions(self):
        """remove any expired sessions"""


__all__ = ("PicPocket",)
