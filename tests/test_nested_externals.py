"""What a sub-package's children may import from outside the project (GitHub issue #18).

The plugin's own rules file narrows what the root allows the plugin as a whole.
"""

import json
from pathlib import Path

from archview.cli import main

ROOT_RULES = """\
[archview]
package = "app"

[archview.allowed]
plugin = []

[archview.externals]
plugin = ["openai"]
"""

PLUGIN_RULES = """\
[archview]
externals_undeclared = "error"

[archview.allowed]
language = []
models = []

[archview.externals]
language = ["openai"]
models = []
"""

PLUGIN = {
    "archview.toml": ROOT_RULES,
    "app/__init__.py": "",
    "app/plugin/__init__.py": "",
    "app/plugin/archview.toml": PLUGIN_RULES,
    "app/plugin/language.py": "import openai\n",
    "app/plugin/models.py": "MODEL = 'gpt'\n",
}


def write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_only_the_children_the_plugin_names_may_import_the_sdk(tmp_path, capsys):
    repo = write(tmp_path, PLUGIN)

    assert run(capsys, "check", str(repo))[0] == 0

    (repo / "app/plugin/models.py").write_text("import openai\n")
    code, out, _ = run(capsys, "check", str(repo))

    assert code == 1
    assert "app.plugin (app/plugin/archview.toml)  1 problem" in out
    assert "  OUTSIDE models -> openai (1 import) not allowed by [archview.externals.models]" in out


def test_a_new_child_must_say_what_it_imports_from_outside(tmp_path, capsys):
    repo = write(tmp_path, {**PLUGIN, "app/plugin/images.py": "import openai\n"})

    code, out, _ = run(capsys, "check", str(repo))

    assert code == 1
    assert "UNDECLARED EXTERNALS images is not in [archview.externals]" in out


def test_the_plugin_file_cannot_widen_what_the_root_allows(tmp_path, capsys):
    root = ROOT_RULES.replace('plugin = ["openai"]', "plugin = []")
    repo = write(tmp_path, {**PLUGIN, "archview.toml": root})

    code, out, _ = run(capsys, "check", str(repo))

    assert code == 1
    assert "OUTSIDE plugin -> openai (1 import) not allowed by [archview.externals.plugin]" in out
    assert "app.plugin (app/plugin/archview.toml)  ok" in out


def test_init_root_writes_what_the_children_import_from_outside(tmp_path, capsys):
    files = {k: v for k, v in PLUGIN.items() if k != "app/plugin/archview.toml"}
    repo = write(tmp_path, files)

    code, out, _ = run(capsys, "init", str(repo), "--root", "plugin", "--externals", "--stdout")

    assert code == 0
    assert '[archview.externals]\nlanguage = ["openai"]\nmodels = []\n' in out


def test_a_root_key_naming_part_of_a_component_is_a_config_error(tmp_path, capsys):
    root = ROOT_RULES + '"plugin.language" = ["openai"]\n'
    repo = write(tmp_path, {**PLUGIN, "archview.toml": root})

    code, _, err = run(capsys, "check", str(repo))

    assert code == 2
    assert "give plugin a rules file of its own" in err


def test_graph_shows_the_outside_package_a_scope_fails_on(tmp_path, capsys):
    repo = write(tmp_path, {**PLUGIN, "app/plugin/models.py": "import openai\n"})

    _, out, _ = run(capsys, "graph", str(repo), "--root", "plugin", "--json")

    assert "openai" in [n["id"] for n in json.loads(out)["nodes"]]
