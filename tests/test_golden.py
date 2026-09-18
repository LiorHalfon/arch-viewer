"""Golden files: the whole pipeline, pinned byte for byte (N1, N6).

Regenerate deliberately with `UPDATE_GOLDEN=1 uv run pytest`, then read the diff.
"""

import json
import os
from pathlib import Path

import pytest

from archview.extract.python import build_model
from archview.model.serialize import dumps, view_to_dict
from archview.model.view import build_view
from archview.project import open_project
from archview.render.dot import to_dot
from tests.typescript_support import TS_SAMPLE, requires_typescript

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"


@pytest.fixture(scope="module")
def sample():
    return build_model("sample", FIXTURES)


def check(name: str, actual: str) -> None:
    path = GOLDEN / name
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(actual)
    assert path.exists(), f"{name} is missing; run UPDATE_GOLDEN=1 uv run pytest"
    assert actual == path.read_text(), f"{name} changed; UPDATE_GOLDEN=1 to accept"


def test_model_json_matches_the_golden_file(sample):
    check("sample-model.json", dumps(sample))


def test_view_json_matches_the_golden_file(sample):
    view = build_view(sample, "sample")
    check("sample-view.json", json.dumps(view_to_dict(view), indent=2) + "\n")


def test_dot_matches_the_golden_file(sample):
    check("sample.dot", to_dot(build_view(sample, "sample")))


def test_drilled_down_view_matches_the_golden_file(sample):
    view = build_view(sample, "sample.infra")
    check("sample-infra-view.json", json.dumps(view_to_dict(view), indent=2) + "\n")


@requires_typescript
def test_typescript_model_and_view_match_the_golden_files():
    model = open_project(TS_SAMPLE).model
    check("ts-sample-model.json", dumps(model))
    view = build_view(model, "ts-sample")
    check("ts-sample-view.json", json.dumps(view_to_dict(view), indent=2) + "\n")
