"""
Configure the Postgres Database to use for tests. The options are:
 * fail: Have any test requiring postgres fail
 * skip: Don't test against postgres
 * external: Test against a user-provisioned postgres server
 * docker: Test against a dockerized postgres brought up for tests
 * isolated: Test against a separate dockerized postgres each test
"""
import json
import random
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from subprocess import check_call

DIRECTORY = Path(__file__).parent.absolute()
DOCKERFILE = DIRECTORY / "Dockerfile"
CONFIG = DIRECTORY / "pg-config.json"

IMAGE_NAME = "picpocket-postgres-testing"


def main():
    parser = ArgumentParser("Configure how PicPocket's tests test against PostgreSQL")
    parser.add_argument(
        "strategy",
        default="skip",
        choices=("fail", "skip", "external", "docker", "isolated"),
        help=(
            "Choose how to test against PostgreSQL: "
            "fail (mark any test requiring postgres as failed), "
            "skip (mark any test requiring postgres as skipped), "
            "external (run tests against a server that you have "
            "separately set up), "
            "docker (bring up a PostgreSQL server within a Docker "
            "container. This requires Docker and will be slower than "
            "a natively-running server), "
            "isolated (bring up a separate PostgreSQL with a Docker "
            "container for each individual test. This requires Docker "
            "and will be MUCH slower than reusing the same container)"
        ),
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="The host name of the PostgreSQL server (ignored if not extranl)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5432,
        help=(
            "The port the external server is running on/"
            "the port to run the Docker server on"
        ),
    )
    parser.add_argument(
        "--database",
        default="test-picpocket",
        type=starts_test,
        help=(
            "The name of the database to test against. "
            "The tests will refuse to run against a dabase unless its name "
            "starts with 'test'"
        ),
    )
    parser.add_argument("--user", default="picpocket", help="The PostgreSQL user name")
    parser.add_argument(
        "--password",
        help=(
            "The PostgreSQL user password. "
            "If not supplied, a Docker instance will use a random password"
        ),
    )

    args = parser.parse_args()

    config = {"strategy": args.strategy}

    if args.strategy not in ("fail", "skip"):
        config["host"] = args.host
        config["port"] = args.port
        config["dbname"] = args.database
        config["user"] = args.user

        if args.strategy != "external":
            if args.password is None:
                args.password = sha256(random.randbytes(32)).hexdigest()

            with DOCKERFILE.open("w") as stream:
                stream.write("FROM library/postgres\n")
                stream.write(f"ENV POSTGRES_DB={args.database}\n")
                stream.write(f"ENV POSTGRES_USER={args.user}\n")
                stream.write(f"ENV POSTGRES_PASSWORD={args.password}\n")

            print("building docker image")
            check_call(("docker", "build", "--tag", IMAGE_NAME, str(DIRECTORY)))

            config["image"] = IMAGE_NAME

        config["password"] = args.password

    with CONFIG.open("w") as stream:
        json.dump(config, stream)


def starts_test(name) -> str:
    """
    Confirm that a name starts with 'test''
    """

    if name.startswith("test"):
        return name

    raise ValueError(f"Name must start with 'test': {name}")


if __name__ == "__main__":
    main()
