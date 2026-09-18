"""The TypeScript tests need Node, and the fixture needs `npm ci`; without them the
tests skip - unless ARCHVIEW_REQUIRE_TS is set (CI), where a missing setup is an error."""

import os
import shutil
from pathlib import Path

import pytest

TS_SAMPLE = Path(__file__).parent / "fixtures" / "ts-sample"
HAS_NODE = shutil.which("node") is not None
READY = HAS_NODE and (TS_SAMPLE / "node_modules" / "typescript").is_dir()

if os.environ.get("ARCHVIEW_REQUIRE_TS") and not READY:
    raise RuntimeError(
        "ARCHVIEW_REQUIRE_TS is set but node or the fixture's node_modules is missing; "
        "run npm ci --prefix tests/fixtures/ts-sample"
    )

requires_node = pytest.mark.skipif(not HAS_NODE, reason="node is not installed")
requires_typescript = pytest.mark.skipif(
    not READY, reason="run npm ci --prefix tests/fixtures/ts-sample"
)
