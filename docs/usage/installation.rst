Installing PicPocket
====================

.. warning:
    PicPocket is currently only tested on macOS.
    If you are using another OS, you may want to hold off on installing it.

PicPocket requires Python 3.11 or above.
You will need a copy installed in order to use PicPocket

PicPocket is not yet on PyPI.
You will need to clone or download a copy of this repository in order to install it.

.. note::
    By default, PicPocket uses `SQLite <https://www.sqlite.org/index.html>`_ as the backend for storing information about your photos.
    This is easier to manage and, because PicPocket doesn't store the photos themselves in the database, should be well-suited to most use cases.
    If you would like to use PicPocket with a heavier-duty database (and are willing to manage a PostgreSQL server yourself!), see :ref:`PostgreSQL Support`.
    We strongly recommend that you start with SQLite and only migrate to PostgreSQL later if you actually need it.

Once you've downloaded PicPocket and have navigated to the PicPocket directory, you can install it by running:

.. code-block:: bash

    pip install .

You can now access PicPocket on the command line using the `picpocket` command.
See :doc:`quickstart` for details on setting up your PicPocket.

PostgreSQL Support
------------------

If you want to use PicPocket with a PostgreSQL database, you will be responsible for installing and maintaining it yourself.
We recommend you create a database and a user that only has permissions to create, modify, and delete tables within that database.
PicPocket does not yet support using a different user day-to-day than the one needed to perform table changes on version updates.

PicPocket has built-in support for interfacing with PostgreSQL, but it is not installed by default.
To install with PostgreSQL support you'll need to add `[PostgreSQL]`:

.. code-block:: bash

    pip install .[PostgreSQL]

You can now access PicPocket on the command line using the `picpocket` command.
See :doc:`quickstart` for details on setting up your PicPocket.