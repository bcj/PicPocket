Testing
=======

Tests are all run in isolated environments using `tox <https://tox.wiki/en/latest/>`.

With `tox` installed, you can run tests by running:

.. code-block:: bash

    tox

And run individual test environments with the `-e` flag:

.. code-block:: bash

    tox py311-tests-postgres

All tests against PostgreSQL will be skipped unless it is manually configured.
Configuring can be done with the `pg-conf.py` script in the `tests` directory.

Your options are:

* fail: Mark all tests as failed
* skip: Mark all tests as skipped (the default)
* external: Run PostgreSQL tests against a server you have set up
    * You will need to supply information on how to connect to the server.
      tests will only be run against a database if it has 'test' at the beginning of its name.
      That database will be erased repeatedly during testing.
* docker: Run PostgreSQL tests against a Docker container that is brought up
    at the beginning of testing and torn down at the end.
* isolated: Run PostgreSQL tests against a Docker container that is brought up
    at the beginning of each individual test and torn down afterward.

Running against a natively running database is faster than a Docker container and significantly faster than running against a new Docker container for each test case.
The official recommendation is just use `docker` unless you need to be running significant amounts of tests and need those tests to be running against PostgreSQL every time.

That said, an idle PostgreSQL server may be less resource-intensive on your machine than Docker is, so your mileage may vary.

If you are using an external PostgreSQL database, you should create a test user:

.. code-block:: bash

    createuser --no-createdb test-user

And then create a database that user has access to:

.. code-block:: bash

    createdb --owner test-user test-picpocket