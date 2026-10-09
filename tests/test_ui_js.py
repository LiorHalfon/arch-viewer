"""The viewer's JavaScript modules have Node tests in tests/ui; this runs them with pytest."""

import subprocess
from pathlib import Path

from tests.typescript_support import requires_node

REPO = Path(__file__).parent.parent


@requires_node
def test_the_ui_modules_pass_their_node_tests():
    result = subprocess.run(
        ["node", "--test", "tests/ui/*.test.mjs"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
