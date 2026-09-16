"""`archview why | deps | rdeps | cycles` and `check --stop-hook` end to end (G1, G3, ADR 0009)."""

import io
import json
from pathlib import Path

import pytest

from archview.cli import main
from tests.test_golden import check as golden

FIXTURES = Path(__file__).parent / "fixtures"
REPO = str(FIXTURES)
RULES = str(Path(__file__).parent / "golden" / "sample-archview.toml")


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_why_shows_the_direct_import_and_marks_it_type_checking(capsys):
    code, out, _ = run(capsys, "why", "api", "infra", REPO)

    assert code == 0
    assert "sample.api -> sample.infra: 1 direct import" in out
    assert "sample/api/routes.py:14  from sample.infra.db import Session  [TYPE_CHECKING]" in out


def test_why_without_type_checking_imports_follows_the_chain(capsys):
    code, out, _ = run(capsys, "why", "sample.api", "sample.infra", REPO, "--runtime-only")

    assert code == 0
    assert "no direct import; shortest chain of 2" in out
    assert out.index("sample.api.routes -> sample.services.pricing") < out.index(
        "sample.services.pricing -> sample.infra.cache"
    )
    assert "from sample.infra.cache import get_rate  [lazy]" in out


def test_why_exits_1_when_there_is_no_dependency(capsys):
    code, out, _ = run(capsys, "why", "domain", "api", REPO)

    assert code == 1
    assert out == "sample.domain does not depend on sample.api\n"


def test_why_json_matches_the_golden_file(capsys):
    code, out, _ = run(capsys, "why", "api", "infra", REPO, "--runtime-only", "--format", "json")

    assert code == 0
    golden("sample-why.json", out)


def test_an_unknown_name_is_a_usage_error_with_a_suggestion(capsys):
    code, _, err = run(capsys, "why", "api.route", "infra", REPO)

    assert code == 2
    assert "did you mean sample.api.routes" in err


def test_overlapping_names_are_a_usage_error(capsys):
    code, _, err = run(capsys, "why", "api", "api.routes", REPO)

    assert code == 2
    assert "sample.api contains sample.api.routes" in err


def test_deps_lists_sibling_packages_with_their_imports(capsys):
    code, out, _ = run(capsys, "deps", "services", REPO)

    assert code == 0
    assert out.splitlines()[0] == "sample.services depends on 2:"
    assert "  sample.domain  (1 import)" in out
    assert "  sample.infra  (1 import)" in out
    assert "sample/services/pricing.py:3  from ..domain import model  [sample.domain.model]" in out


def test_rdeps_lists_dependents_and_works_for_externals(capsys):
    _, out, _ = run(capsys, "rdeps", "services", REPO, "--format", "json")
    assert [d["name"] for d in json.loads(out)["dependents"]] == ["sample.api", "sample.infra"]

    _, out, _ = run(capsys, "rdeps", "grimp", REPO)
    assert out.splitlines()[:2] == ["grimp has 1 dependent:", "  sample.api.routes  (1 import)"]


def test_deps_of_a_name_with_none(capsys):
    code, out, _ = run(capsys, "deps", "domain.model", REPO)

    assert code == 0
    assert out == "sample.domain.model depends on nothing\n"


def test_cycles_lists_a_path_with_the_imports_behind_each_step(capsys):
    code, out, _ = run(capsys, "cycles", REPO)

    assert code == 0
    assert out.splitlines()[:3] == [
        "1 cycle",
        "",
        "in sample: sample.infra -> sample.services -> sample.infra",
    ]
    assert "  sample.infra -> sample.services  (1 import)" in out


def test_cycles_json_matches_the_golden_file(capsys):
    _, out, _ = run(capsys, "cycles", REPO, "--format", "json")

    golden("sample-cycles.json", out)


def test_no_cycles_in_a_subtree(capsys):
    code, out, _ = run(capsys, "cycles", REPO, "--root", "sample.api")

    assert code == 0
    assert out == "no cycles under sample.api\n"


def test_graph_accepts_format_as_well_as_the_old_flags(capsys):
    _, new, _ = run(capsys, "graph", REPO, "--format", "json")
    _, old, _ = run(capsys, "graph", REPO, "--json")

    assert new == old
    assert json.loads(new)["root"] == "sample"


def hook(monkeypatch, capsys, payload: dict | None, *argv: str) -> tuple[int, str, str]:
    stdin = io.StringIO("" if payload is None else json.dumps(payload))
    monkeypatch.setattr("sys.stdin", stdin)
    return run(capsys, "check", "--stop-hook", *argv)


@pytest.fixture
def failing_rules(tmp_path):
    text = Path(RULES).read_text().replace("fail_on_cycles = false", "fail_on_cycles = true")
    path = tmp_path / "archview.toml"
    path.write_text(text)
    return str(path)


def test_stop_hook_blocks_with_the_report_on_stderr(monkeypatch, capsys, failing_rules):
    code, out, err = hook(monkeypatch, capsys, {}, REPO, "--config", failing_rules)

    assert code == 2
    assert out == ""
    assert "CYCLE infra -> services -> infra" in err


def test_stop_hook_lets_the_agent_stop_the_second_time(monkeypatch, capsys, failing_rules):
    payload = {"stop_hook_active": True}
    code, out, err = hook(monkeypatch, capsys, payload, REPO, "--config", failing_rules)

    assert (code, out, err) == (0, "", "")


def test_stop_hook_passes_quietly_when_the_check_passes(monkeypatch, capsys):
    code, out, err = hook(monkeypatch, capsys, None, REPO, "--config", RULES)

    assert (code, out, err) == (0, "", "")


def test_stop_hook_does_not_block_when_the_check_cannot_run(monkeypatch, capsys, tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")

    code, _, err = hook(monkeypatch, capsys, {}, str(tmp_path))

    assert code == 0
    assert "archview:" in err and "not blocking" in err
