Locations
=========

Locations represent directories on your computer where PicPocket can find :doc:`images <images>`.
Locations can either represent :ref:`Sources` to fetch images from, or :ref:`Destinations` where images should be stored.

Kinds of Location
-----------------

Sources
^^^^^^^

A source represents a location where new images come from (e.g., the memory card of your Camera).
PicPocket does not directly keep track of images on a source location.

PicPocket provides :doc:`Tasks <tasks>` as the preferred way to add new images to your computer, and to PicPocket.

Destinations
^^^^^^^^^^^^

A destination represents a location on your computer where you store your images (e.g., the *Pictures* folder).

PicPocket can copy images into your destination using :doc:`Tasks <tasks>`, and can move an image to a new location if you ask it to, but it will make no changes to this directory on its own.

Properties
----------

There are several properties associated with locations in PicPocket:

name
    A unique name that succinctly describes what the location is

description
    A description of what the location is/what it's used for. Descriptions are for your own purposes

path
    The file-path to the root of the location. Locations do not need to always be present (though operations requiring the actual image file will only work when it's present). Unless a device does not attach at a specific location, or the location isn't unique (i.e., another device may sometimes be at that location), you should provide a path.

type
    Either Source or Destination

removable
    Whether the location is expected to always be available (e.g., a folder on your computer), or may not always be present (e.g., a memory card)

Actions
-------

Mount
    If you did not provide a path for a location (or you did, but the location is temporarily accessible at a different path than normal), you will need to 'mount' it, by telling PicPocket where it is currently accessible.

    When using the web version of PicPocket, a location will remain mounted until you unmount it, or until the server is restarted. When using the Python API, a location will be mounted until you mount it or end the API session. On the command line, you will need to pass a mount path with every operation.

Unmount
    Tell PicPocket that a location is no longer available at a temporary location.

Import (destinations only)
    Add any images stored in a destination to PicPocket. PicPocket will not move or modify the images itself, but it will read them and add information about them to its own database.

    PicPocket is written with the assumption that you will do this when you first add a destination to PicPocket, and then not again. It is safe to rerun this, though it will re-add any images you removed from PicPocket and it will be slow on large destinations

Edit
    Edit information about a location

Remove
    Tell PicPocket to forget about a location.

    Removing a location will remove any images from PicPocket stored on that location (but will not touch the image files themselves!). It will also delete any tasks that rely on that location.