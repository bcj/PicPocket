import tomllib
from pathlib import Path


def test_version():
    from picpocket.version import __version__

    # test that version matches pyproject.toml
    project_file = Path(__file__).parent.parent / "pyproject.toml"

    with project_file.open("rb") as stream:
        data = tomllib.load(stream)

    assert __version__ == data["project"]["version"]
