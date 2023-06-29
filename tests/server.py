"""Run an interactive test server using a temporary configuration"""
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from picpocket.web import DEFAULT_PORT, run_server
from tests.conftest import IMAGE_FILES, _load_api


def main():
    with asyncio.Runner() as runner:
        runner.run(temporary_server(DEFAULT_PORT))


async def temporary_server(port: int):
    async with _load_api() as api:
        with TemporaryDirectory() as dirname:
            directory = Path(dirname)

            await api.add_location("camera", source=True, removable=True)
            main_id = await api.add_location("main", directory, destination=True)

            try:
                await run_server(api, port)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
