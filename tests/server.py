"""Run an interactive test server using a temporary configuration"""
import asyncio

from picpocket.web import DEFAULT_PORT, run_server
from tests.conftest import _load_api


def main():
    with asyncio.Runner() as runner:
        runner.run(temporary_server(DEFAULT_PORT))


async def temporary_server(port: int):
    async with _load_api() as api:
        try:
            await run_server(api, port)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
