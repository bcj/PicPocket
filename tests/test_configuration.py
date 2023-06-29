import tomllib
from typing import Optional

import pytest
import tomli_w


@pytest.mark.asyncio
async def test_configuration(create_configuration):
    from picpocket.configuration import CONFIG_FILE

    count = 0

    password = None

    def prompt() -> Optional[str]:
        nonlocal count

        count += 1
        return password

    async with create_configuration(backend="postgres", prompt=prompt) as configuration:
        password = configuration.contents["backend"]["connection"]["password"]
        assert configuration.credentials == password
        assert count == 1
        assert configuration.credentials == password
        assert count == 1

        configuration.reload()

        assert configuration.credentials == password
        assert count == 2

        assert configuration.file == configuration.directory / CONFIG_FILE

        with configuration.file.open("rb") as stream:
            contents = tomllib.load(stream)

        assert configuration.contents == contents

        assert configuration.backend == "postgres"

        # contents should be cached until explicit reload (is this good?)
        contents["dog"] = "woof"
        with configuration.file.open("wb") as stream:
            tomli_w.dump(contents, stream)

        assert configuration.contents != contents
        configuration.reload()
        assert configuration.contents == contents

    async with create_configuration(use_prompt=True) as configuration:
        with pytest.raises(ValueError):
            configuration.credentials
