Quick Start
===========

Once PicPocket is :doc:`Installed <installation>`, you can create your PicPocket database using the `initialize` command:

.. code-block:: bash

    picpocket initialize

This will store PicPocket's configuration data (and its SQLite) within the directory `~/.config/picpocket`.
You can specify a directory to save this information, but you will then need to specify that directory whenever you run PicPocket.

If you are using the PostgreSQL backend, you will need to specify the backend and credentials:

.. code-block:: bash

    picpocket initialize postgres \
        --user picpocket \
        --host localhost  \
        --port 5432 \
        --db picpocket

Once the store is created, you can access the web interface by running:

.. code-block:: bash

    picpocket web --port 8080

You can reach the web interface at `http://localhost:8080`.

.. warning::
    Your connection is not encrypted, no password is required, and you can use PicPocket to delete files on your computer.
    Until several of those change, you should not make it generally accessible.

Locations
---------

Locations in PicPocket represent either sources to import images from (e.g., a camera's memory card), or a destination to copy images to (e.g., the Pictures directory on your computer).

The following information can be provided for a location:

* name: The unique name of the location (e.g., camera, EM1 Mark III, pictures, external storage). The level of specificity needed depends on how many devices you have. If you only have one camera and are storing photos in one place, *camera* and *storage* are probably specific enough. You can always rename locations later.
* path: Where this location is on the file system. The location doesn't need to be always present, but you should leave this blank if the location isn't mounted in a consistent place or you have multiple devices that mount to the same location (e.g., memory cards in multiple cameras that are named the same way). If the path isn't supplied, you will need to :ref:`mount <Mounting Locations>` it before use
* description: A text description of the location
* source: Whether this location represents a source to import images from
* destination: Whether this location represents a place images are stored
* removable: Whether this device is removable storage

On the command line, you can add a location with the `locations add` command:

.. code-block:: bash

    picpocket locations add camera \
        --description "My camera" \
        --source \
        --removable \
        --path /Volumes/camera

.. code-block:: bash

    picpocket locations add main \
        --description "Main photo storage" \
        --destination \
        --path ~/Pictures

In both the web and the command-line interfaces, destinations will have all images currently in them imported by default.

Mounting Locations
^^^^^^^^^^^^^^^^^^

If you have added a location without a set path (or need to override the default path for a location), you will need to mount it.

On the web interface, find the location and select 'mount' (probably).

On the command line, commands requiring file access will all support the `--mount` flag that takes two arguments (location, path).

Tasks
-----

Tasks are ways of automatically copying images from a source to a destination.
Tasks (currently) have the following properties:

* name: The unique name of the task
* source: The location to import images from
* destination: The location to copy images to
* creator: Who to list as the creator of the imported images
* tags: Any number of tags to apply to all imported images
* source_path: Where (relative to the source location's root) to start looking for images. If a path is supplied, any file within that directory (or a subdirectory thereof) will be added. For each level of the path, the path can either be a literal directory name or one of the following segments:
    * year: The year the photo was taken
    * month: The month the photo was taken
    * day: The day the photo was taken
    * date (along with a format): the date the photo was taken
    * regex (along with a pattern): A regex the directory must match
* destination_format: Where (relative to the destination root) to copy image to. By default, photos are copied to a directory mirroring the source's strcture. The following formatters are allowed when specifying this path:
    * path: The source filepath (relative to the source root).
    * file: The file name (with extension)
    * name: The file name (without extension)
    * extension The file extension (without leading dot)
    * uuid: a UUID4 hex
    * date: A date object representing the source image's last-modified date. You can supply the format to save the date using strftime formatting (e.g. `date:%Y-%m-%d-%H-%M-%S`)
    * hash: A hash of the image's contents
    * index: A 1-indexed number representing the order the images were imported (PicPocket does not guarantee import order. This may add images in a non-chronological order)

 When running a task, photos will never be copied over top of existing photos. If a date-based source path is provided, subsequent runs of the task will only look at directories representing later dates than the last run time

 In the web interface, tasks can be created by selecting tasks and clicking add.
 They can then be run by pressing the task's run button.

 On the command line, you can create tasks with the `tasks add` command:

 .. code-block:: bash

    picpocket tasks add camera-import \
        camera \
        storage \
        --path images "{year}" "{month}" "{day}" \
        --destination "from-camera/{date:%Y}/{date:%m}/{file}"

What's Next
-----------

Your PicPocket is now set up.
You can now start `managing your images <images>`
