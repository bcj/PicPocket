Quick Start
===========

Once PicPocket is :doc:`Installed <installation>`, you can create your PicPocket database using the `initialize` command:

.. code-block:: bash

    picpocket initialize

This will store PicPocket's configuration data (and its SQLite database) within the directory `~/.config/picpocket`.
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

If you are only using PicPocket on the same machine, you can pass the `--local-actions` flag to provide some additional functionality:

.. code-block:: bash

    picpocket web --port 8080 --local-actions

At present, all this adds is the ability to show an image file in Finder on macOS, but other functionality (e.g., open in Image Editor) may eventually be added.

Setting up Locations
--------------------

You can store you images wherever you want, but you do need to tell PicPocket where they can be found.
To do that, you will need to set up some :doc:`locations <locations>`.

Setting up a Destination
^^^^^^^^^^^^^^^^^^^^^^^^

A destination represents a place on your computer where images are stored (e.g., *My Pictures*).
If you store images on multiple places on your computer, you will need to create a separate destination for each place).

To create a destination:

 * navigate to 'locations' and click 'add'
 * fill out information about your destination:
   * Name: should be short and distinct. If you're only storing photos in one place, this name could be broad like *photos* or *storage*
   * Description (optional): A brief description of the location to make it clear to you what it represents
   * Path (optional): The path to your location (e.g., `/Users/name/Pictures`, `~/Pictures`). Sorry that you have to type this out manually. You should provide a path
   * Type: Select 'Destination'
   * Removable: Uncheck if you expect that location to be available any time PicPocket is running
 * click 'create'

Once the location is created, you can now import the images already at the location into PicPocket:

* click 'import'
* options:
  * Creator: If all images are created by the same person, you can automatically label them as the creator at import
  * Tags: Any tags to apply to all images being imported. To add, fill in the text box and click 'add'. To remove a tag, select it and click 'remove'
  * Batch Size: If you enter a number here, PicPocket will save every time it attempts to add that many images during the import. If no number is provided, PicPocket will wait until all images are imported before saving.
  * File Formats: If you only want to import images of certain types into PicPocket, provide the file extension (with or without leading dot) one per line. If not provided, PicPocket will import its default image types
* click 'Import' and wait. Once the import is complete, you will be taken to a view of all imported images.

Importing can be slow, and PicPocket currently doesn't give any feedback while importing so it will look like your page has frozen.
Give it some time.

If you want to add a destination on the command line, you can use the `locations add` command.

.. code-block:: bash

    picpocket locations add main \
        --description "Main photo storage" \
        --destination \
        --path ~/Pictures

By default, the command line interface will import automatically when a new destination is added.

Setting up a Source
^^^^^^^^^^^^^^^^^^^

A source represents a place to copy images from (such as a camera memory card).
The process for adding a source is the same as adding a destination, but with one caveat: If you have multiple devices that mount at the same location (e.g., all your camera memory cards mount at `/Volumes/mount/<YOUR PHONE NUMBER>`), or your device doesn't get mounted in a consistent location, you'll want to leave the path blank and 'mount' the location before using it.

* navigate to 'locations' and click 'add'
* fill out information about your source
* click 'create'

If you have multiple sources, you'll need to repeat for each one.

On the command line:

.. code-block:: bash

    picpocket locations add camera \
        --description "My camera" \
        --source \
        --removable \
        --path /Volumes/camera

Mounting Locations
^^^^^^^^^^^^^^^^^^

If you didn't provide a path for one of your sources or destinations, you will need to do the following every time you use it:

* navigate to 'locations' and find the desired location
  * this can either be done by selecting 'list' and scrolling down to the appropriate location or entering the name in the text box on the location page
* select 'mount'
* enter the path to the location

On the command line, commands that require access to files will have a `--mount` flag that either takes the path, or the name of the location and the path (depending on how many locations the command interfaces with).
See `--help` for any given command for details.

Creating Import Tasks
---------------------

:doc:`Tasks <tasks>` are ways of automatically copying images from a source to a destination.

Currently, PicPocket makes the assumption that tasks are how you are adding new images (the alternative is re-importing a destination each time you add images and this method will be slow).

You will want to create a task for each camera/image source you plan on managing through PicPocket.
To create a task:

* navigate to 'tasks' and select add
* fill out information about your task
  * If you just want to mirror the structure of your source device, all you need to do is add a name, and set the source and destination appropriately
  * If you only want to copy images in some locations of your source device, or, you want to change image paths/names, you will need to read the source and destination formatting guides on the :doc:`tasks <tasks>` guide.
* click 'create'

Once your task is created, you'll want run it by finding the task and selecting 'run'.
The first time a task is run, it will copy all images in the specified location on the device.
After that, by default, the task will only look for images with last-modified dates from after it last ran.

Whenever you run a task, you will be taken to the set of imported images.

On the command line, you can create tasks with the `tasks add` command:

 .. code-block:: bash

    picpocket tasks add camera-import \
        camera \
        storage \
        --path "images/{year}/{month}/{day}" \
        --destination "from-camera/{date:%Y}/{date:%m}/{file}"

You can then run tasks using `tasks run`

.. code-block:: bash

    picpocket tasks run camera-import


What's Next
-----------

Your PicPocket is now set up.
You can now start viewing and managing your :doc:`images <images>`, and adding :doc:`tags <tags>`.

Enjoy!