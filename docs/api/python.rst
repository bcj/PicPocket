Python API
==========

Loading PicPocket
-----------------

PicPocket provides different API objects for each supported backend.
It is recommended that you always use the base module's :func:`initialize` and :func:`load` functions for loading the API::

    from picpocket import initialize, load

.. autofunction:: picpocket.initialize

.. autofunction:: picpocket.load

The API Protocol
----------------

.. autoclass:: picpocket.api.PicPocket
  :members:

Custom Returned Types
---------------------

Many PicPocket methods return locations, images, and tasks as custom objects.

.. automodule:: picpocket.database.types
  :members:

Filtering Tools
---------------

Several PicPocket methods allow filtering of items.
These methods will accept a filter of any of the following types:

.. autoclass:: picpocket.database.logic.Boolean
  :members:

.. autoclass:: picpocket.database.logic.Text
  :members:

.. autoclass:: picpocket.database.logic.Number
  :members:

.. autoclass:: picpocket.database.logic.DateTime
  :members:

.. autoclass:: picpocket.database.logic.And
  :members:

.. autoclass:: picpocket.database.logic.Or
  :members:

The above filters (excluding :class:`Boolean picpocket.database.logic.Boolean`, :class:`And picpocket.database.logic.And`, and :class:`Or picpocket.database.logic.Or`) have the user also supply the comparison being made. The supplied comparison should be the following Enum:

.. autoclass:: picpocket.database.logic.Comparator
  :members:
  :undoc-members:

Path Components for Tasks
-------------------------

:class:`PathPart` objects allow you to dynamically restrict which directories get searched when running a task.
All date-related :class:`PathPart`\ s will be compared against the last-ran date for the task and any directories matching dates *before* the last-ran date will be skipped.

.. automodule:: picpocket.tasks
  :members: PathPart, Year, Month, Day, Date, Regex