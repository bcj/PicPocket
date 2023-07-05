Tasks
=====

Tasks represent repeatable actions for copying :doc:`images <images>` from a source :doc:``location <locations>` to a destination location.
Tasks provide some (limited) abilities to rename images when they're copied in.

Properties
----------

name
    A unique name that succinctly describes the task

description
    A description of what the task is/does. Descriptions are for your own purposes

source
    The location you are copying images from. The task will not modify the source location in any way

destination
    The location you are copying images to. The task will create files and folders at this location, but will not overwrite existing files (even if those files aren't files in PicPocket).

    .. note::
        One slight caveat to the above: PicPocket tasks check if a file exists at that location prior to writing but the check and the write are not atomic (they do not happen in a single file system call), so it is theoretically possible to overwrite a file that was created in between that check and PicPocket copying the file. As long as you aren't running something else that is copying a bunch of files to conflicting locations at the same time, this won't be a problem

creator
    If all images imported by this task are created by the same person, you can have the task add that creator to all images stored. This information is stored within PicPocket, and will not be added to the image's EXIF data.

tags
    Any number of tags to apply to all imported images

source path
    Where to look for images on the source location (relative to that location's root). If not supplied, all directories will be searched through. If a path is supplied, all subdirectories of that path will be explored too.

    PicPocket provides some functionality for dynamic values in paths. See :ref:`Source Path Formatting` for details.

destination formats
    Where to save the image copies (relative to the destination root). If not supplied, the path used will mirror the path the file was found at *relative to the source root*.

    E.g.: If the source location root is `/Volumes/camera`, and the source path is `dcim`, and the destination root is `~/Pictures`, then an image found at `/Volumes/camera/dcim/2023/01/01/123.jpg` would be copied to `~/Pictures/dcim/2023/01/01/123.jpg`.

    PicPocket provides some functionality for dynamic values in paths. See :ref:`Destination Path Formatting` for details.

formats
    Which kinds of image to copy. If not supplied, PicPocket will copy all image types it knows about.

Source Path Formatting
^^^^^^^^^^^^^^^^^^^^^^

PicPocket provides some limited functionality for dynamically describing a source path.
This is done to make importing images from a device quicker (if you last imported from the device a day ago, there's no point in it rechecking the 100 GB of photos you have in the 2010 folder). There are 6 special functions that exist, and they can be supplied by putting their name in angle brackets (e.g., `directory/{year}/subdirectory`). Only one special function can be given for a given directory in a path (i.e., `directory/{year}{month}/subdirectory` is not allowed).

When a task runs (and isn't run with the 'full' flag), any date-based directories representing a date older than the last-run date (or, if you supply one, a custom date) will be skipped.

Custom Path Functions:

year
    Will match against any directory name that looks like a year that isn't older than the supplied year.

    E.g., `directory/{year}` would ignore any images in `directory/2022` if the supplied date was January 1st 2023 or later. Even if no date was supplied, it would ignore `directory/subdirectory` as 'subdirectory' doesn't look like a year

month
    Will match against any directory name that looks like a month (currently only a number!). If 'year' has been supplied as well, then folders representing older dates than that year/month combo will be ignored.

    E.g., `directory/{year}/{month}` would ignore any images in `directory/2023/02` unless the supplied date was February 28th, 2023 or earlier. If your directory structure has year as a subdirectory of month (e.g., `directory/{month}/{year}`) it will still work

day
    Will match against any directory name that looks like a day (i.e., is a number between 1 and 31 inclusive, with or without leading 0). If 'year' and 'month' have been supplied as well, then folders representing older dates than that year/month/day combo will be ignored.

    E.g., `directory/{year}/{month}/{day}` would ignore any images in `directory/2023/02/28` unless the supplied date was February 28th, 2023 or earlier. This will work for any arbitrary ordering of year/month/day (e.g., `directory/{day}/{month}/{year}`). If your images are stored in day/month/year format, you should message me to tell me about why that is most useful (tracking weather/star positions over years?). If your images are stored in some scrambled date format, I would be happier not knowing but I'm glad PicPocket can help.

date **requires a supplied date format**
    Will match against directories if they are in the correct date format and the date isn't older than the supplied date.

    Date formats are provided using Python's `Strftime <https://strftime.org/>`_ date format, and are supplied after a colon (:) in the name.

    E.g., `directory/{date:%Y-%m-%dT%H%M}` would ignore `directory/2023-02-28T1623` unless the supplied date was 4:23 PM on February 28th, 2023 or earlier.

regex **requires a supplied pattern**
    Will match against directories if they match a (Perl Compatible) `Regular Expression <https://en.wikipedia.org/wiki/Perl_Compatible_Regular_Expressions>`_. Patterns are supplied after a colon (:) in the name.

    E.g., `directory/{regex:photo[s]?}` would match against `directory/photo` and `directory/photos` and no other directories.

str **requires supplied text**
    If you want to tell a task to look in a directory with a `{` in it, PicPocket will assume you instead mistyped when trying to use any of the above special dynamic names. The str function is a way of passing that directory in a way that doesn't confuse PicPocket.

    E.g., `directory/{str:{my directory{}` will match against `directory/{my directory{`

Destination Path Formatting
^^^^^^^^^^^^^^^^^^^^^^^^^^^

PicPocket also has some limited functionality for renaming files when copying them over.
This is done by supplied a path with any of the following placeholders:

directory
    The directory the image was found in, relative to the source location root

    E.g., if the source root is `/Volumes/camera` and the image is found at `Volumes/camera/abc/2023/02/28/123.jpg`, 'directory' will be `abc/2023/02/28`

file
    The name of the image file.

    E.g., if the image is found at `Volumes/camera/abc/2023/02/28/123.jpg`, 'file' will be `123.jpg`

name
    The name of the image (without extension).

    E.g., if the image is found at `Volumes/camera/abc/2023/02/28/123.jpg`, 'name' will be `123`

extension
    The image file suffix (without leading dot).

    E.g., if the image is found at `Volumes/camera/abc/2023/02/28/123.jpg`, 'extension' will be `jpg`

uuid
    A UUID4 Hex (a hexadecimal number of the form `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

date
    The last-modified date of the image in the `Strftime <https://strftime.org/>`_ date format of your choosing.

    E.g., if the image was last modifed at 4:23 PM on February 28th, 2023, `{date:%Y}` would be `2023` and `{date:%B %-d, %Y}` would be `February 28, 2023`

hash
    A hexidecimal number representing the image's contents that `should <https://en.wikipedia.org/wiki/Secure_Hash_Algorithms#Comparison_of_SHA_functions>`_ uniquely represent that image.

    At present, the hash is a SHA-256 hash and will be 64 characters long. PicPocket reserves the right to modify this between versions

index
    A 1-indexed number representing the order images are encountered by the task. PicPocket makes no promises about the order images are added in

Running Tasks
-------------

By default, PicPocket tasks will only attempt to copy images with last-modified dates that are newer than the time the task last ran.

You can manually supply an older or newer date to manually set the cutoff, or pass the 'full' flag to ignore last-modified date.

PicPocket doesn't look at the modified dates of directories, as they do not tend to accurately reflect changes in further subdirectories.