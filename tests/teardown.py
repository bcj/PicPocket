import json
import os
from subprocess import check_call, check_output

from tests.conftest import CONFIG

if os.environ["PICPOCKET_BACKEND"] == "postgres" and CONFIG.exists():
    with CONFIG.open("r") as stream:
        config = json.load(stream)

    image = config.get("image")
    if image:
        for container in check_output(
            ("docker", "ps", "--all", "--filter", f"ancestor={image}", "--quiet"),
            text=True,
        ).split():
            check_call(("docker", "rm", "--force", container), text=True)
