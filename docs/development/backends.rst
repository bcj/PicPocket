Implementing Your Own Backend
=============================

Support for this is still incredibly provisional.
In theory, all you need to do is implement the :class:`PicPocket <picpocket.api.PicPocket>` protocol and everything should work.
Unfortunately, getting :func:`initialize <picpocket.initialize>` or :func:`load <picpocket.load>` requires modifying the `APIS` dict in the base module, so it can't yet be done in a way that allows use of the `cli <api/cli>`.

See the definition of `testenv:py{311}-tests-postgres` in `tox.ini` for information on how to run all tests against your backend.

Adding Support for a New DBAPI 2.0-Compatible Database
------------------------------------------------------

If you want to support a database that has an asynchronous DBAPI-compatible package, it's fairly straight-forward.
PicPocket's PostgreSQL and SQLite backends use the same code for almost all operations, and should require very little changes to the non-shared code as features are added to PicPocket.

You will need to subclass :class:`picpocket.database.dbapi.DbApi` and :class:`picpocket.database.logic.SQL`.

In practice, this might be slightly more difficult if your database's functionality differs greatly from both PostgreSQL and SQLite.

DbApi
^^^^^

.. autoclass:: picpocket.database.dbapi.DbApi
  :members:

SQL
^^^

.. autoclass:: picpocket.database.logic.Types
  :members:
  :undoc-members:

.. autoclass:: picpocket.database.logic.SQL
  :members: