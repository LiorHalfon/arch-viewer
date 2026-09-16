"""The interchange JSON (A12) and its schema, and determinism (N1)."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from archview.extract.python import build_model
from archview.model.serialize import SCHEMA, dumps, model_from_dict, model_to_dict

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def sample():
    return build_model("sample", FIXTURES)


def test_round_trips_a_model_through_its_dict_form(sample):
    assert model_from_dict(model_to_dict(sample)) == sample


def test_declares_the_schema_version_and_language(sample):
    data = model_to_dict(sample)
    assert (data["schema"], data["language"], data["project"]) == (2, "python", "sample")


def test_json_matches_the_published_schema(sample):
    schema = json.loads(SCHEMA.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(model_to_dict(sample))


def test_the_same_source_always_produces_byte_identical_json():
    first = dumps(build_model("sample", FIXTURES))
    second = dumps(build_model("sample", FIXTURES))
    assert first == second
