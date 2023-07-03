"""Run PicPocket from the command line"""
import asyncio
import json
import logging
from argparse import ArgumentParser, Namespace
from datetime import datetime, timezone
from enum import Enum
from getpass import getpass
from pathlib import Path
from typing import Optional

from picpocket import initialize, load
from picpocket.api import PicPocket
from picpocket.database import logic
from picpocket.database.types import Image
from picpocket.internal_use import NotSupplied
from picpocket.parsing import full_path, int_or_str
from picpocket.web import DEFAULT_PORT, run_server

DEFAULT_DIRECTORY = Path(".config") / "picpocket"


class Output(Enum):
    NONE = "none"
    COUNT = "count"
    QUIET = "quiet"
    JSON = "json"
    FULL = "full"


def with_default():
    # This is the only place we can safely reference home and be sure
    # that a test won't accidentally wipe out our real PicPocket.
    # For this reason, we should never test the CLI by shelling out.
    main(Path.home())


def main(
    default_directory: Path,
    input_args: Optional[list[str]] = None,
    print=print,
):
    """Run PicPocket from the command line"""
    args = parse_cli(default_directory, input_args)

    logger = logging.getLogger("picpocket")
    logger.setLevel(level=args.log_level)
    logger.addHandler(logging.StreamHandler())

    with asyncio.Runner() as runner:
        if args.command == "initialize":
            kwargs = {}
            if args.backend == "postgres":
                if not (args.password or args.no_password):
                    args.password = prompt_password()

                kwargs = {
                    "host": args.host,
                    "port": args.port,
                    "dbname": args.db,
                    "user": args.user,
                    "password": args.password,
                    "store_password": args.store_password,
                }
            elif args.backend == "sqlite":
                if args.path:
                    kwargs["path"] = args.path
            else:
                args.backend = "sqlite"

            runner.run(initialize(args.directory, args.backend, **kwargs))
        else:
            match args.command:
                case "import" | "export" | "web":
                    function = run_meta
                case "location":
                    function = run_location
                case "task":
                    function = run_task
                case "image":
                    function = run_image
                case "tag":
                    function = run_tag
                case _:
                    raise NotImplementedError(
                        f"Command '{args.command}' not implemented"
                    )

            # We do this outside the run functions, in part, so that
            # during testing our code doesn't even have the option of
            # trying to create a configuration that might point at the
            # user's actual configuration
            picpocket = load(args.config, prompt=prompt_password)
            runner.run(function(picpocket, args, print))


def parse_cli(
    default_directory: Path, input_args: Optional[list[str]] = None
) -> Namespace:
    """Parse command-line arguments

    build the ArgumentParser and then parse the supplied inputs

    args:
        default_directory: Where the PicPocket config is
        input_args: The input arguments to parse

    Returns:
        The produced Namespace
    """
    default_location = default_directory / DEFAULT_DIRECTORY

    parser = ArgumentParser(description="Manage photos")

    subparsers = parser.add_subparsers(
        dest="command", help="Run picpocket from the command line"
    )

    initialize = subparsers.add_parser("initialize", help="Initialize the database")
    initialize.add_argument(
        "--directory",
        type=Path,
        default=default_location,
        help="Where to store configuration information",
    )

    db_subparsers = initialize.add_subparsers(
        dest="backend", required=False, help="Which database to use as a back end"
    )
    sqlite = db_subparsers.add_parser(
        "sqlite",
        help=(
            "The default backend. Sqlite is a small, efficient file-based db. "
            "Sqlite isn't designed for multiple users accessing it at once "
            "and lacks some text search capabilities but should be good "
            "enough for most users"
        ),
    )
    sqlite.add_argument(
        "path",
        nargs="?",
        type=Path,
        help=(
            "Where to save the DB file. "
            "If not specified, the db will be saved in the same "
            "directory as the configuration file"
        ),
    )
    postgres = db_subparsers.add_parser(
        "postgres",
        help=(
            "A more powerful DB server. "
            "Presently, you will need to configure PostgreSQL yourself. "
            "If you want multiple people to access PicPocket at once, "
            "need faster and more powerful search, or want the DB hosted "
            "on another computer, and are fine configuring it, this is "
            "the DB you want"
        ),
    )
    postgres.add_argument("--host", help="The host of the database server")
    postgres.add_argument(
        "--port",
        type=int,
        default=5432,
        help="The port the database server is listening on",
    )
    postgres.add_argument(
        "--db",
        default="picpocket",
        help="The name of the database for picpocket to use",
    )
    postgres.add_argument(
        "--user",
        default="picpocket",
        help="The user for accessing the database",
    )
    init_password_group = postgres.add_mutually_exclusive_group()
    init_password_group.add_argument(
        "--password", help="The password for accessing the database"
    )
    init_password_group.add_argument(
        "--no-password",
        action="store_true",
        help="Don't prompt for a user password, it doesn't exist",
    )
    init_save_password_group = postgres.add_mutually_exclusive_group()
    init_save_password_group.add_argument(
        "--store-password",
        action="store_true",
        help="Save password to the config file",
    )
    init_save_password_group.add_argument(
        "--forget-password",
        dest="store_password",
        action="store_false",
        help="Don't save password to the config file (default unless --no-password)",
    )

    leaves = [initialize]
    leaves.extend(build_meta(subparsers))
    leaves.extend(build_locations(subparsers))
    leaves.extend(build_tasks(subparsers))
    leaves.extend(build_images(subparsers))
    leaves.extend(build_tags(subparsers))

    # we want some flags present on most/all commands but we want them
    # to be given where other flags are passed (after all subcommands)
    for leaf in leaves:
        # init doesn't run on an existing db, so this argument is passed
        # differently
        if leaf != initialize:
            leaf.add_argument(
                "--config",
                type=full_path,
                default=default_location,
                help="Where the configuration directory for PicPocket is",
            )

        leaf.add_argument(
            "--debug",
            dest="log_level",
            default=logging.INFO,
            action="store_const",
            const=logging.DEBUG,
            help="Show debug logs",
        )

    return parser.parse_args(input_args)


def build_meta(action) -> list[ArgumentParser]:
    """Add commands related to the PicPocket store"""

    web = action.add_parser("web", description="Run the PicPocket web app")
    web.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help="The port to run the server on",
    )

    importer = action.add_parser("import", description="Import a PicPocket backup")
    importer.add_argument("path", type=full_path, help="The backup to import")
    importer_locations_group = importer.add_mutually_exclusive_group()
    importer_locations_group.add_argument(
        "--locations", nargs="*", help="Only import these locations"
    )
    importer_locations_group.add_argument(
        "--location",
        dest="locations",
        nargs=2,
        action="append",
        metavar=("NAME", "PATH"),
        help="Provide the path to the mount point of a location",
    )

    exporter = action.add_parser("export", description="Create a PicPocket backup")
    exporter.add_argument("path", type=full_path, help="where to save the backup")
    exporter.add_argument("--locations", nargs="*", help="Only export these locations")

    return [web, importer, exporter]


async def run_meta(picpocket: PicPocket, args: Namespace, print=print):
    """Run commands related to PicPocket itself"""
    match args.command:
        case "web":
            try:
                # force the password prompt
                # TODO: prompt user on the web side
                await picpocket.list_locations()

                print("press ^c to stop server")
                await run_server(picpocket, args.port)
            except KeyboardInterrupt:
                print("shutting down")
        case "import":
            if args.locations:
                if isinstance(args.locations[0], list):
                    args.locations = {
                        location: full_path(pathstr)
                        for location, pathstr in args.locations
                    }

            await picpocket.import_data(args.path, locations=args.locations)
        case "export":
            await picpocket.export_data(args.path, locations=args.locations)
        case _:
            raise NotImplementedError(f"Command '{args.command}' not implemented")


def build_locations(action) -> list[ArgumentParser]:
    """Add commands for location-related functions"""
    parser = action.add_parser(
        "location",
        description=(
            "Functions related to PicPocket locations "
            "(places to import images from/to)"
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="location commands")

    # get a location
    get = subparsers.add_parser("get", help="Get an existing location")
    get.add_argument("name", type=int_or_str, help="The location to fetch")
    get_output_group = get.add_mutually_exclusive_group()
    get_output_group.add_argument(
        "--quiet",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.QUIET,
        help="Just output the id",
    )
    get_output_group.add_argument(
        "--json",
        dest="output",
        action="store_const",
        const=Output.JSON,
        help="Output location as json",
    )

    # list existing locations
    list_all = subparsers.add_parser("list", help="List all locations in PicPocket")
    list_all_output_group = list_all.add_mutually_exclusive_group()
    list_all_output_group.add_argument(
        "--count",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.COUNT,
        help="Just output the number of locations",
    )
    list_all_output_group.add_argument(
        "--quiet",
        dest="output",
        action="store_const",
        const=Output.QUIET,
        help="Just output ids",
    )
    list_all_output_group.add_argument(
        "--json",
        dest="output",
        action="store_const",
        const=Output.JSON,
        help="Output locations as json",
    )

    # add a new location
    add = subparsers.add_parser(
        "add",
        help=(
            "Add a location (either a source or a destination). "
            "If the location is a destination, exising images will be added."
        ),
    )
    add.add_argument("name", help="How to refer to the location")
    add.add_argument(
        "path",
        type=full_path,
        nargs="?",
        help=(
            "The path to the location. "
            "If unsupplied, the path will need to be supplied each time "
            "this location is used."
        ),
    )
    add.add_argument(
        "--description",
        help="A description of what this location is and what it's used for",
    )
    add.add_argument(
        "--source",
        action="store_true",
        help=(
            "Whether the location is a source for images to import from. "
            "E.g., A camera"
        ),
    )
    add.add_argument(
        "--destination",
        action="store_true",
        help=(
            "Whether the location is a destination for images to import to. "
            "E.g., The Pictures directory on your computer"
        ),
    )
    add.add_argument(
        "--non-removable",
        dest="removable",
        action="store_false",
        help=(
            "Whether the location represents a removable storage device. "
            "E.g., An SD card"
        ),
    )
    import_group = add.add_mutually_exclusive_group()
    import_group.add_argument(
        "--skip-import",
        action="store_true",
        help="Do not import existing files from this destination",
    )
    import_group.add_argument(
        "--import-path",
        type=Path,
        help=(
            "The current path for the media "
            "(use if location isn't always mounted at the same place)"
        ),
    )
    add.add_argument("--creator", help="A creator to list when importing")
    add.add_argument(
        "--tag",
        dest="tags",
        action="append",
        help="A tag to apply when importing",
    )
    add_output_group = add.add_mutually_exclusive_group()
    add_output_group.add_argument(
        "--quiet",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.QUIET,
        help="Just output location id",
    )
    add_output_group.add_argument(
        "--json",
        dest="output",
        action="store_const",
        const=Output.JSON,
        help="Output location (and imported images) as json",
    )

    # edit an existing location
    edit = subparsers.add_parser("edit", help="Edit an existing location")
    edit.add_argument("name", type=int_or_str, help="The location to edit")
    edit.add_argument(
        "new_name",
        type=str,
        nargs="?",
        help="What to rename the location to",
    )

    edit_path_group = edit.add_mutually_exclusive_group()
    edit_path_group.add_argument(
        "--path",
        type=full_path,
        help="The permanent path to the root of the location",
    )
    edit_path_group.add_argument(
        "--remove-path",
        dest="path",
        action="store_false",
        help="Remove the path currently set for the location",
    )

    edit_description_group = edit.add_mutually_exclusive_group()
    edit_description_group.add_argument(
        "--description",
        help="A description of what this location is and what it's used for",
    )
    edit_description_group.add_argument(
        "--remove-description",
        dest="description",
        action="store_false",
        help="Remove the description currently set for the location",
    )

    edit_source_group = edit.add_mutually_exclusive_group()
    edit_source_group.add_argument(
        "--source",
        default=None,
        action="store_true",
        help=(
            "Whether the location is a source for images to import from. "
            "E.g., A camera"
        ),
    )
    edit_source_group.add_argument(
        "--non-source",
        dest="source",
        action="store_false",
        help=(
            "Whether the location is a source for images to import from. "
            "E.g., A camera"
        ),
    )

    edit_destination_group = edit.add_mutually_exclusive_group()
    edit_destination_group.add_argument(
        "--destination",
        default=None,
        action="store_true",
        help=(
            "Whether the location is a destination for images to import to. "
            "E.g., The Pictures directory on your computer"
        ),
    )
    edit_destination_group.add_argument(
        "--non-destination",
        dest="destination",
        action="store_false",
        help=(
            "Whether the location is a destination for images to import to. "
            "E.g., The Pictures directory on your computer"
        ),
    )

    edit_removable_group = edit.add_mutually_exclusive_group()
    edit_removable_group.add_argument(
        "--removable",
        default=None,
        action="store_true",
        help=(
            "Whether the location is a destination for images to import to. "
            "E.g., The Pictures directory on your computer"
        ),
    )
    edit_removable_group.add_argument(
        "--non-removable",
        dest="removable",
        action="store_false",
        help=(
            "Whether the location represents a removable storage device. "
            "E.g., An SD card"
        ),
    )

    # remove an existing location
    remove = subparsers.add_parser("remove", help="Remove an existing location")
    remove.add_argument("name", type=int_or_str, help="The location to remove")
    remove.add_argument("--force", action="store_true", help="Remove any images")

    return [get, list_all, add, edit, remove]


def prompt_password() -> str:
    """prompt the user for the DB password"""
    return getpass("DB Password: ")


async def run_location(picpocket: PicPocket, args: Namespace, print=print):
    """Run location commands"""
    match args.subcommand:
        case "list":
            locations = await picpocket.list_locations()

            match args.output:
                case Output.COUNT:
                    print(len(locations))
                case Output.QUIET:
                    for location in locations:
                        print(location.id)
                case Output.JSON:
                    serialized = [location.serialize() for location in locations]
                    print(json_dump({"locations": serialized}))
                case Output.FULL:
                    for location in locations:
                        print(f"{location.name} ({location.id}):")

                        if location.mount_point:
                            print(f"\t{location.mount_point}")
                        elif location.path:
                            print(f"\t{location.path}")

                        if location.description:
                            print(f"\t{location.description}\n")

                        if location.source:
                            print("\tsource")

                        if location.destination:
                            print("\tdestination")

                        if location.removable:
                            print("\tremovable")
        case "add":
            id = await picpocket.add_location(
                args.name,
                description=args.description,
                path=args.path,
                source=args.source,
                destination=args.destination,
                removable=args.removable,
            )

            if args.output in (Output.FULL, Output.QUIET):
                print(id)
            elif args.output == Output.JSON:
                info = {"location": id, "images": []}

            if args.destination and not args.source and not args.skip_import:
                path = args.import_path or args.path

                if path:
                    if args.output == Output.FULL:
                        print("importing images")
                    await picpocket.mount(id, path)
                    images = await picpocket.import_location(
                        args.name, creator=args.creator
                    )
                    if args.output == Output.FULL:
                        print(f"imported {len(images)} images")
                    elif args.output == Output.JSON:
                        info["images"] = images
                    await picpocket.unmount(id)

            if args.output == Output.JSON:
                print(json_dump(info))
        case "edit":
            kwargs: dict[str, Optional[Path | str]] = {}

            if args.description is False:
                kwargs["description"] = None
            elif args.description:
                kwargs["description"] = args.description

            if args.path is False:
                kwargs["path"] = None
            elif args.path:
                kwargs["path"] = args.path

            await picpocket.edit_location(
                args.name,
                args.new_name,
                source=args.source,
                destination=args.destination,
                removable=args.removable,
                **kwargs,  # type: ignore[arg-type]
            )
        case "remove":
            await picpocket.remove_location(args.name, force=args.force)
        case _:
            raise NotImplementedError(
                f"Command 'location {args.subcommand}' not implemented"
            )


def build_tasks(action) -> list[ArgumentParser]:
    """Add commands for task-related functions"""
    parser = action.add_parser(
        "task",
        description=(
            "Functions related to PicPocket tasks (operations to import images)"
        ),
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="task commands")

    add = subparsers.add_parser("add", help="Create a new task")
    add.add_argument("name", help="The name of the task")
    add.add_argument("source", type=int_or_str, help="The location to import from")
    add.add_argument("destination", type=int_or_str, help="The location to copy to")
    add.add_argument("--description", help="A description of the task")
    add.add_argument("--creator", help="Who to list as creator of imported images")
    add.add_argument(
        "--tag",
        dest="tags",
        action="append",
        help="A tag to apply when importing",
    )
    add.add_argument(
        "--path",
        help=(
            "The base directory of the source location to search in. "
            "Each section of the path should either be the string "
            "representing the name of that path or any of the following "
            "dynamic directory names: {year} (the year the photo was taken), "
            "{month} (the month the photo was taken), "
            "{day} (the day the photo was taken), "
            "{date:FORMAT} (the date the photo was taken, with FORMAT "
            "being a strftime formatter), "
            "{regex:PATTERN} (a regex matching a directory name), "
            "{str:TEXT} (how to pass directory names starting with {)"
        ),
    )
    add.add_argument(
        "--format",
        help=(
            "The format to use for files copied in. If not provided, "
            "files will be copied to locations relative to the source "
            "and destination (e.g., source/a/b/c/d.jpg will copy to "
            "destination/a/b/c/d.jpg). The name can use the following "
            "format values: path (the file path relative to the source), "
            "file (the file's name), name (the file's name without extension), "
            "extension (the extension without leading dot), "
            "uuid (a uuid hex), "
            "date (the date the file was last modified. yo ucan pass a "
            "format string [e.g., {date:%Y-%m-%D}]), "
            "hash (a hash of the file's contents), "
            "index (a 1-indexed number representing the order images "
            "were encountered [PicPocket makes no guarantee on the "
            "order that images will be encountered])."
        ),
    )
    add.add_argument(
        "--file-formats",
        nargs="+",
        help=(
            "The file extensions to import as part of the task. "
            "If not supplied, all default filetypes will be imported."
        ),
    )
    add.add_argument("--force", action="store_true", help="Overwrite any existing task")

    run = subparsers.add_parser("run", help="Run an existing task")
    run.add_argument("name", help="The name of the task to run")
    filter_group = run.add_mutually_exclusive_group()
    filter_group.add_argument(
        "--since",
        type=date,
        help="Only fetch files since this date",
    )
    filter_group.add_argument(
        "--full",
        action="store_true",
        help="Don't filter directories based on the last-run date",
    )
    run.add_argument(
        "--mount",
        dest="mounts",
        nargs=2,
        action="append",
        metavar=("NAME_OR_ID", "PATH"),
        help="Provide the path to the mount point of a location",
    )
    run_output_group = run.add_mutually_exclusive_group()
    run_output_group.add_argument(
        "--count",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.COUNT,
        help="Print just the count",
    )

    run_output_group.add_argument(
        "--json",
        dest="output",
        action="store_const",
        const=Output.JSON,
        help="Output full list of ids as json",
    )

    remove = subparsers.add_parser("remove", help="Delete a task")
    remove.add_argument("name", help="The name of the task to delete")

    # get a task
    get = subparsers.add_parser("get", help="Get an existing task")
    get.add_argument("name", help="The task to fetch")
    get.add_argument(
        "--json",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.JSON,
        help="Output task as json",
    )

    get_all = subparsers.add_parser("list", help="List existing tasks")
    get_all.add_argument(
        "--json",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.JSON,
        help="Output tasks as json",
    )

    return [add, run, remove, get, get_all]


async def run_task(picpocket: PicPocket, args: Namespace, print=print):
    """Run task commands"""
    match args.subcommand:
        case "get":
            task = await picpocket.get_task(args.name)

            if task is None:
                raise ValueError(f"Unknown task: {args.name}")

            if args.output == Output.JSON:
                print(json_dump(task.serialize()))
            else:
                print(
                    f"{task.name}:\n"
                    f"\t{task.description}\n"
                    f"\tsource: {task.source}\n"
                    f"\tdestination: {task.destination}"
                )
                if task.last_ran:
                    print(f"\tlast ran: {task.last_ran:%Y-%m-%d %H:%M:%S}")
                print("\tconfiguration:")
                for line in json_dump(task.serialize()).splitlines():
                    print(f"\t\t{line}")
        case "list":
            tasks = await picpocket.list_tasks()

            if args.output == Output.JSON:
                print(json_dump({"tasks": [task.serialize() for task in tasks]}))
            else:
                for task in tasks:
                    print(
                        f"{task.name}:\n"
                        f"\t{task.description}\n"
                        f"\tsource: {task.source}\n"
                        f"\tdestination: {task.destination}"
                    )
                    if task.last_ran:
                        print(f"\tlast ran: {task.last_ran:%Y-%m-%d %H:%M:%S}")
                    print("\tconfiguration:")
                    for line in json_dump(task.serialize()).splitlines():
                        print(f"\t\t{line}")
                    print()
        case "add":
            await picpocket.add_task(
                args.name,
                args.source,
                args.destination,
                description=args.description,
                creator=args.creator,
                tags=args.tags,
                source_path=args.path,
                destination_format=args.format,
                file_formats=args.file_formats,
                force=args.force,
            )
        case "run":
            mounted = await mount_requested(picpocket, args.mounts)
            try:
                ids = await picpocket.run_task(
                    args.name, since=args.since, full=args.full
                )
            finally:
                for id in mounted:
                    await picpocket.unmount(id)
            if args.output == Output.JSON:
                print(json_dump(ids))
            elif args.output == Output.COUNT:
                print(len(ids))
            else:
                print(f"imported {len(ids)} images")
        case "remove":
            await picpocket.remove_task(args.name)
        case _:
            raise NotImplementedError(
                f"Command 'task {args.subcommand}' not implemented"
            )


def build_images(action) -> list[ArgumentParser]:
    """Add commands for image-related functions"""

    parser = action.add_parser(
        "image",
        description=("Functions related to PicPocket images"),
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="image commands")

    # search images
    search = subparsers.add_parser("search", help="Search images in PicPocket")

    search.add_argument(
        "--location",
        action="append",
        type=int_or_str,
        help=(
            "A location the images should be stored. "
            "The location will be interpretted as an ID if it's a number. "
            "Can be supplied multiple times"
        ),
    )
    search.add_argument(
        "--skip-location",
        action="append",
        type=int_or_str,
        help=(
            "Skip items stored in this location. "
            "The location will be interpretted as an ID if it's a number. "
            "Can be supplied multiple times"
        ),
    )
    search.add_argument(
        "--type",
        dest="conditions",
        action="append",
        type=lambda extension: logic.Text(
            "extension", logic.Comparator.EQUALS, extension
        ),
        help=(
            "Include files with this filetype. "
            "Type should be provided without the leading dot, e.g. 'jpg'. "
            "Can be supplied multiple times"
        ),
    )
    search.add_argument(
        "--skip-type",
        dest="conditions",
        action="append",
        type=lambda extension: logic.Or(
            logic.Text("extension", logic.Comparator.EQUALS, None),
            logic.Text("extension", logic.Comparator.EQUALS, extension, invert=True),
        ),
        help=(
            "Skip files of this filetype. "
            "Type should be provided without the leading dot, e.g. 'jpg'. "
            "Can be supplied multiple times"
        ),
    )
    rating_group = search.add_mutually_exclusive_group()
    rating_group.add_argument(
        "--rating",
        dest="conditions",
        action="append",
        type=rating,
        help="The rating the photo has. You can include </>/≤/≥ in front of the number",
    )
    rating_group.add_argument(
        "--rated",
        dest="conditions",
        action="append_const",
        const=logic.Number("rating", logic.Comparator.EQUALS, None, invert=True),
        help="Only include images that have been rated",
    )
    rating_group.add_argument(
        "--unrated",
        dest="conditions",
        action="append_const",
        const=logic.Number("rating", logic.Comparator.EQUALS, None),
        help="Only include images that have not been rated",
    )

    search.add_argument(
        "--since",
        dest="conditions",
        action="append",
        type=lambda datestr: logic.DateTime(
            "creation_date", logic.Comparator.GREATER_EQUALS, date(datestr)
        ),
        help=(
            "Don't show photos taken before this time. "
            "Date should be in YYYY/MM/DD format."
        ),
    )
    search.add_argument(
        "--before",
        dest="conditions",
        action="append",
        type=lambda datestr: logic.DateTime(
            "creation_date", logic.Comparator.LESS_EQUALS, date(datestr)
        ),
        help=(
            "Don't show photos taken after this time. "
            "Date should be in YYYY/MM/DD format."
        ),
    )
    search.add_argument(
        "--year",
        dest="conditions",
        action="append",
        type=lambda year: logic.And(
            logic.DateTime(
                "creation_date",
                logic.Comparator.GREATER_EQUALS,
                datetime(int(year), 1, 1).astimezone(timezone.utc),
            ),
            logic.DateTime(
                "creation_date",
                logic.Comparator.LESS,
                datetime(int(year) + 1, 1, 1).astimezone(timezone.utc),
            ),
        ),
        help=(
            "Only show photos taken in a given year. "
            "Filtering is done based on current timezone"
        ),
    )
    search.add_argument(
        "--between",
        type=date,
        nargs=2,
        help=(
            "Only show photos taken between two dates (inclusive). "
            "Date should be in YYYY/MM/DD format."
        ),
    )

    creator_group = search.add_mutually_exclusive_group()
    creator_group.add_argument(
        "--has-creator",
        dest="conditions",
        action="append_const",
        const=logic.Text("creator", logic.Comparator.EQUALS, None, invert=True),
        help="Only include images that have a listed creator",
    )
    creator_group.add_argument(
        "--anonymous",
        dest="conditions",
        action="append_const",
        const=logic.Text("creator", logic.Comparator.EQUALS, None),
        help="Only include images that have not been credited",
    )
    search.add_argument(
        "--creator",
        action="append",
        help="Include images by this creator. Can be supplied multiple times",
    )
    search.add_argument(
        "--skip-creator",
        action="append",
        help="Skip images by this creator. Can be supplied multiple times",
    )
    search_tag_group = search.add_mutually_exclusive_group()
    search_tag_group.add_argument(
        "--tagged",
        dest="tagged",
        default=None,
        action="store_true",
        help="Only include tagged images",
    )
    search_tag_group.add_argument(
        "--untagged",
        dest="tagged",
        action="store_false",
        help="Only include images without any tags",
    )

    search.add_argument(
        "--any-tag",
        dest="any_tags",
        action="append",
        help=(
            "A tag in the set of tags where an image must contain "
            "one or more of the supplied tags. "
            "Can be supplied multiple times"
        ),
    )
    search.add_argument(
        "--all-tag",
        dest="all_tags",
        action="append",
        help=(
            "A tag in the set of tags where an image must contain "
            "all of the supplied tags. "
            "Can be supplied multiple times"
        ),
    )
    search.add_argument(
        "--no-tag",
        dest="no_tags",
        action="append",
        help=(
            "A tag in the set of tags where an image must not contain "
            "any of the supplied tags. "
            "Can be supplied multiple times"
        ),
    )
    search.add_argument(
        "--reachable",
        action="store_true",
        default=None,
        help="Only display images whose files are currently accessible",
    )
    search.add_argument(
        "--unreachable",
        dest="reachable",
        action="store_false",
        help="Only display images whose files are currently inaccessible",
    )
    search.add_argument(
        "--mount",
        dest="mounts",
        nargs=2,
        action="append",
        metavar=("NAME_OR_ID", "PATH"),
        help="Provide the path to the mount point of a location",
    )

    search.add_argument(
        "--order",
        nargs="+",
        help=(
            "How to order the results returned. "
            "One or more columns can be given "
            "(valid columns: id, name, extension, creator, location, "
            "path, title, description, alt, rating) and/or random. "
            "Columns default to ascending order, "
            "for descending order, add a minus sign (-), e.g. -rating. "
            "To control which side empty values are returned on, "
            "put an at either the beginning (but after any minus sign) "
            "or end of a column name (e.g.: creator!, -!rating)"
        ),
    )
    search.add_argument("--limit", type=int, help="How many images to return")
    search.add_argument(
        "--offset",
        type=int,
        help="If a limited is provided, where to start returning images from.",
    )
    search_output_group = search.add_mutually_exclusive_group()
    search_output_group.add_argument(
        "--count",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.COUNT,
        help="Just output the number of images",
    )
    search_output_group.add_argument(
        "--quiet",
        dest="output",
        action="store_const",
        const=Output.QUIET,
        help="Just output ids",
    )
    search_output_group.add_argument(
        "--json",
        dest="output",
        action="store_const",
        const=Output.JSON,
        help="Output images as json",
    )

    find = subparsers.add_parser("find", help="Find an image given its path")
    find.add_argument("path", type=Path, help="The full path to the image")
    find.add_argument(
        "--mount",
        dest="mounts",
        nargs=2,
        action="append",
        metavar=("NAME_OR_ID", "PATH"),
        help="Provide the path to the mount point of a location",
    )
    find_output_group = find.add_mutually_exclusive_group()
    find_output_group.add_argument(
        "--quiet",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.QUIET,
        help="Just output ids",
    )
    find_output_group.add_argument(
        "--json",
        dest="output",
        action="store_const",
        const=Output.JSON,
        help="Output images as json",
    )

    copy = subparsers.add_parser("copy", help="Add a copy of an image to PicPocket")
    copy.add_argument("source", type=full_path, help="The image to copy in")
    copy.add_argument(
        "location", type=int_or_str, help="The location to copy the image to"
    )
    copy.add_argument(
        "destination",
        type=Path,
        help="Where (relative to laction root) to copy the image to",
    )
    copy.add_argument("--creator", help="Who to list as the image creator")
    copy.add_argument("--title", help="what to title the image")
    copy.add_argument("--caption", help="A caption of the image")
    copy.add_argument(
        "--alt", help="Descriptive text of the image to be used as alt text"
    )
    copy.add_argument("--rating", type=int, help="A rating of the image")
    copy.add_argument("--tag", action="append", help="Apply a tag to the image")
    copy.add_argument(
        "--mount",
        type=full_path,
        metavar=("PATH"),
        help="Where the specified location is mounted",
    )

    edit = subparsers.add_parser("edit", help="Edit an existing image")
    edit.add_argument("id", type=int, help="The image to modify")

    creator_group = edit.add_mutually_exclusive_group()
    creator_group.add_argument(
        "--creator",
        default=NotSupplied(),
        help="The creator of the image",
    )
    creator_group.add_argument(
        "--no-creator",
        dest="creator",
        action="store_const",
        const=None,
        help="Remove the listed creator of the image",
    )

    title_group = edit.add_mutually_exclusive_group()
    title_group.add_argument(
        "--title",
        default=NotSupplied(),
        help="A text title of the image",
    )
    title_group.add_argument(
        "--no-title",
        dest="title",
        action="store_const",
        const=None,
        help="Remove the listed title of the image",
    )

    caption_group = edit.add_mutually_exclusive_group()
    caption_group.add_argument(
        "--caption",
        default=NotSupplied(),
        help="A caption for the image",
    )
    caption_group.add_argument(
        "--no-caption",
        dest="caption",
        action="store_const",
        const=None,
        help="Remove the image caption",
    )

    alt_group = edit.add_mutually_exclusive_group()
    alt_group.add_argument(
        "--alt",
        default=NotSupplied(),
        help="Alt text for the image",
    )
    alt_group.add_argument(
        "--no-alt",
        dest="alt",
        action="store_const",
        const=None,
        help="Remove the existing alt text",
    )

    rating_group = edit.add_mutually_exclusive_group()
    rating_group.add_argument(
        "--rating",
        type=int,
        default=NotSupplied(),
        help="A rating of the image's quality",
    )
    rating_group.add_argument(
        "--no-rating",
        dest="rating",
        action="store_const",
        const=None,
        help="Remove the rating for the image",
    )

    tag = subparsers.add_parser("tag", help="Tag an image")
    tag.add_argument("id", type=int, help="The id of the image")
    tag.add_argument("name", help="The name of the tag")

    untag = subparsers.add_parser("untag", help="Remove a tag from an image")
    untag.add_argument("id", type=int, help="The id of the image")
    untag.add_argument("name", help="The name of the tag")

    move = subparsers.add_parser("move", help="Move an image")
    move.add_argument("id", type=int, help="The image to move")
    move.add_argument("path", type=Path, help="The new path (relative to the location)")
    move.add_argument(
        "location",
        nargs="?",
        type=int_or_str,
        help="The location to move the image to",
    )
    move.add_argument(
        "--mount",
        dest="mounts",
        nargs=2,
        action="append",
        metavar=("NAME_OR_ID", "PATH"),
        help="Provide the path to the mount point of a location",
    )

    remove = subparsers.add_parser("remove", help="Remove an image")
    remove.add_argument("id", type=int, help="The image to remove")
    remove.add_argument("--delete", action="store_true", help="Also delete the image")
    remove.add_argument(
        "--mount",
        dest="mounts",
        nargs=2,
        action="append",
        metavar=("NAME_OR_ID", "PATH"),
        help="Provide the path to the mount point of a location",
    )

    verify = subparsers.add_parser(
        "verify", help="Check that images in PicPocket exist on-disk"
    )
    verify.add_argument("--location", type=int_or_str, help="Only check this location")
    verify.add_argument(
        "--path", type=full_path, help="Only check files within this directory"
    )
    verify.add_argument(
        "--exif",
        action="store_true",
        help="reparse EXIF on all images",
    )
    verify.add_argument(
        "--mount",
        dest="mounts",
        nargs=2,
        action="append",
        metavar=("NAME_OR_ID", "PATH"),
        help="Provide the path to the mount point of a location",
    )
    verify_output_group = verify.add_mutually_exclusive_group()
    verify_output_group.add_argument(
        "--quiet",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.QUIET,
        help="Just output ids",
    )
    verify_output_group.add_argument(
        "--json",
        dest="output",
        action="store_const",
        const=Output.JSON,
        help="Output images as json",
    )

    return [search, find, copy, edit, tag, untag, move, remove, verify]


async def run_image(picpocket: PicPocket, args: Namespace, print=print):
    """
    Run image commands
    """

    match args.subcommand:
        case "search":
            comparisons: list[logic.Comparison] = args.conditions or []

            for group, invert in ((args.location, False), (args.skip_location, True)):
                if not group:
                    continue

                ids = []
                for location in group:
                    if isinstance(location, str):
                        response = await picpocket.get_location(location)
                        if response is None:
                            raise ValueError(f"Unknown location, {location}")
                        location = response.id

                    ids.append(location)

                comparisons.append(
                    logic.Number(
                        "location",
                        logic.Comparator.EQUALS,
                        ids,
                        invert=invert,
                    )
                )

            if args.between:
                comparisons.append(
                    logic.DateTime(
                        "creation_date",
                        logic.Comparator.GREATER_EQUALS,
                        args.between[0],
                    )
                )
                comparisons.append(
                    logic.DateTime(
                        "creation_date", logic.Comparator.LESS_EQUALS, args.between[1]
                    )
                )

            if args.creator:
                comparisons.append(
                    logic.Text("creator", logic.Comparator.EQUALS, args.creator)
                )

            if args.skip_creator:
                comparisons.append(
                    logic.Or(
                        logic.Text("creator", logic.Comparator.EQUALS, None),
                        logic.Text(
                            "creator",
                            logic.Comparator.EQUALS,
                            args.skip_creator,
                            invert=True,
                        ),
                    )
                )

            if comparisons:
                if len(comparisons) == 1:
                    comparison = comparisons[0]
                else:
                    comparison = logic.And(*comparisons)
            else:
                comparison = None

            mounted = await mount_requested(picpocket, args.mounts)
            try:
                match args.output:
                    case Output.COUNT:
                        print(
                            await picpocket.count_images(
                                comparison,
                                tagged=args.tagged,
                                any_tags=args.any_tags,
                                all_tags=args.all_tags,
                                no_tags=args.no_tags,
                                reachable=args.reachable,
                            )
                        )
                    case Output.QUIET:
                        for id in await picpocket.get_image_ids(
                            comparison,
                            tagged=args.tagged,
                            any_tags=args.any_tags,
                            all_tags=args.all_tags,
                            no_tags=args.no_tags,
                            order=args.order or None,
                            limit=args.limit,
                            offset=args.offset,
                            reachable=args.reachable,
                        ):
                            print(id)
                    case Output.JSON:
                        images = await picpocket.search_images(
                            comparison,
                            tagged=args.tagged,
                            any_tags=args.any_tags,
                            all_tags=args.all_tags,
                            no_tags=args.no_tags,
                            order=args.order or None,
                            limit=args.limit,
                            offset=args.offset,
                            reachable=args.reachable,
                        )
                        print(
                            json_dump(
                                {"images": [image.serialize() for image in images]}
                            )
                        )
                    case _:
                        for image in await picpocket.search_images(
                            comparison,
                            tagged=args.tagged,
                            any_tags=args.any_tags,
                            all_tags=args.all_tags,
                            no_tags=args.no_tags,
                            order=args.order or None,
                            limit=args.limit,
                            offset=args.offset,
                            reachable=args.reachable,
                        ):
                            print_image(image, print=print)
            finally:
                for id in mounted:
                    await picpocket.unmount(id)
        case "find":
            mounted = await mount_requested(picpocket, args.mounts)

            try:
                maybe_image = await picpocket.find_image(
                    args.path, tags=args.output != Output.QUIET
                )

                if maybe_image is None:
                    raise ValueError(f"Could not find image: {args.path}")

                match args.output:
                    case Output.QUIET:
                        print(maybe_image.id)
                    case Output.JSON:
                        print(json_dump(maybe_image.serialize()))
                    case _:
                        print_image(maybe_image, print=print)
            finally:
                for id in mounted:
                    await picpocket.unmount(id)
        case "copy":
            if args.mount:
                await picpocket.mount(args.location, args.mount)

            try:
                id = await picpocket.add_image_copy(
                    args.source,
                    args.location,
                    args.destination,
                    creator=args.creator,
                    title=args.title,
                    caption=args.caption,
                    alt=args.alt,
                    rating=args.rating,
                    tags=args.tags,
                )
                print(id)
            finally:
                if args.mount:
                    await picpocket.unmount(args.location)
        case "edit":
            await picpocket.edit_image(
                args.id,
                creator=args.creator,
                title=args.title,
                caption=args.caption,
                alt=args.alt,
                rating=args.rating,
            )
        case "tag":
            await picpocket.tag_image(args.id, args.name)
        case "untag":
            await picpocket.untag_image(args.id, args.name)
        case "move":
            mounted = await mount_requested(picpocket, args.mounts)

            try:
                await picpocket.move_image(args.id, args.path, location=args.location)
            finally:
                for id in mounted:
                    await picpocket.unmount(id)
        case "remove":
            mounted = await mount_requested(picpocket, args.mounts)

            try:
                await picpocket.remove_image(args.id, delete=args.delete)
            finally:
                for id in mounted:
                    await picpocket.unmount(id)
        case "verify":
            mounted = await mount_requested(picpocket, args.mounts)

            try:
                images = await picpocket.verify_image_files(
                    location=args.location, path=args.path, reparse_exif=args.exif
                )

                match args.output:
                    case Output.QUIET:
                        for image in images:
                            print(image.id)
                    case Output.JSON:
                        print(
                            json_dump(
                                {"missing": [image.serialize() for image in images]}
                            )
                        )
                    case _:
                        if images:
                            print("missing images:")
                            for image in images:
                                print_image(image, print=print)
                        else:
                            print("no missing images")
            finally:
                for id in mounted:
                    await picpocket.unmount(id)
        case _:
            raise NotImplementedError(
                f"Command 'image {args.subcommand}' not implemented"
            )


def build_tags(action) -> list[ArgumentParser]:
    """
    Add commands for tag-related functions
    """
    parser = action.add_parser(
        "tag",
        description=("Functions related to PicPocket tags"),
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="tag commands")

    # create a tag
    add = subparsers.add_parser("add", help="Create a new tag")
    add.add_argument("name", help="The name of the tag")
    description_group = add.add_mutually_exclusive_group()
    description_group.add_argument(
        "--description",
        default=NotSupplied(),
        help="A description of the tag",
    )
    description_group.add_argument(
        "--remove-description",
        dest="description",
        action="store_const",
        const=None,
        help="Remove any existing description exists for this tag",
    )

    # move a tag
    move = subparsers.add_parser("move", help="Move a tag to a new location")
    move.add_argument("current", help="The current name of the tag")
    move.add_argument("new", help="The new name of the tag")
    move.add_argument(
        "--no-cascade",
        dest="cascade",
        action="store_false",
        help="Don't move child tags",
    )

    # remove a tag
    remove = subparsers.add_parser("remove", help="Remove an existing tag")
    remove.add_argument("name", help="The name of the tag")
    remove.add_argument(
        "--cascade", action="store_true", help="Also delete any of the tags descendents"
    )

    listing = subparsers.add_parser("list", help="List all existing tags")
    listing.add_argument(
        "--json",
        dest="output",
        default=Output.FULL,
        action="store_const",
        const=Output.JSON,
        help="Output tags as json",
    )

    return [add, move, remove, listing]


async def run_tag(picpocket: PicPocket, args: Namespace, print=print):
    """
    Run tag commands
    """
    match args.subcommand:
        case "add":
            await picpocket.add_tag(args.name, description=args.description)
        case "move":
            count = await picpocket.move_tag(
                args.current, args.new, cascade=args.cascade
            )
            print(f"{count} tags moved")
        case "remove":
            await picpocket.remove_tag(args.name, cascade=args.cascade)
        case "list":
            tags = await picpocket.all_tags()
            if args.output == Output.JSON:
                print(json_dump(tags))
            else:
                for tag in sorted(tags):
                    print_tags(tags, print=print)
        case _:
            raise NotImplementedError(
                f"Command 'tag {args.subcommand}' not implemented"
            )


def print_image(image: Image, *, print=print):
    if image.full_path:
        print(f"{image.id} ({image.full_path})")
        print(f"\tlocation: {image.location}")
    else:
        print(f"{image.id} ({image.location} {image.path})")

    if image.title:
        print(f"\ttitle: {image.title}")

    if image.creator:
        print(f"\tcreator: {image.creator}")

    if image.caption:
        print(f"\tcaption: {image.caption}")

    if image.alt:
        print(f"\talt: {image.alt}")

    if image.rating is not None:
        print(f"\trating: {image.rating}")

    if image.width:
        print(f"\tdimensions: {image.width}x{image.height}")

    if image.creation_date:
        print(f"\tcreated: {image.creation_date:%Y-%m-%d %H:%M}")

    if image.tags:
        print("\ttags:")
        for tag in image.tags:
            print(f"\t\t{tag}")

    if image.exif:
        print("\texif:")

        for key, value in image.exif.items():
            print(f"\t\t{key}: {value}")


def print_tags(tags: dict, print=print, parents=""):
    for name, value in sorted(tags.items(), key=lambda pair: pair[0]):
        if parents:
            name = f"{parents}:{name}"

        line = name
        if value["description"]:
            line = f"{line}: {value['description']}"

        print(line)
        print_tags(value["children"], print=print, parents=name)


def rating(raw: str) -> logic.Number:
    match raw[0]:
        case "<":
            comparison = logic.Comparator.LESS
            number = int(raw[1:])
        case "≤":
            comparison = logic.Comparator.LESS_EQUALS
            number = int(raw[1:])
        case ">":
            comparison = logic.Comparator.GREATER
            number = int(raw[1:])
        case "≥":
            comparison = logic.Comparator.GREATER_EQUALS
            number = int(raw[1:])
        case _:
            comparison = logic.Comparator.EQUALS
            number = int(raw)

    return logic.Number("rating", comparison, number)


def date(raw: str) -> datetime:
    try:
        return datetime.strptime(raw, "%Y/%m/%d").astimezone(timezone.utc)
    except Exception:
        try:
            return datetime.strptime(raw, "%Y/%m/%d %H:%M").astimezone(timezone.utc)
        except Exception:
            return datetime.strptime(raw, "%Y/%m/%d %H:%M:%S").astimezone(timezone.utc)


async def mount_requested(
    api: PicPocket, mounts: Optional[list[tuple[str, str]]]
) -> list[int]:
    """Mount requested drives

    Args:
        api: The PicPocket API
        mounts: the location name/id, path string pair

    Returns:
        the id of the location that was mounted
    """
    ids = []

    current_mounts = dict(api.mounts)
    if mounts:
        try:
            for locationstr, pathstr in mounts:
                location = await api.get_location(int_or_str(locationstr))
                if location is None:
                    raise ValueError(f"Unknown location: {locationstr}")
                path = full_path(pathstr)

                await api.mount(location.id, path)

                ids.append(location.id)
        except Exception:
            for id, path in current_mounts.items():
                await api.mount(id, path)
            raise

    return ids


def json_dump(data) -> str:
    """Dump data to a json string with nice formatting"""

    return json.dumps(
        data,
        sort_keys=True,
        indent=2,
    )
