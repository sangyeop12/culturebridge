import shutil
import subprocess
from pathlib import Path

import pytest


def test_real_client_scripts_with_browser_test_doubles():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required for client event contract checks")
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [node, str(root / "scripts/check_web_clients.mjs")],
        cwd=root,
        check=True,
        capture_output=True,
        timeout=20,
    )
