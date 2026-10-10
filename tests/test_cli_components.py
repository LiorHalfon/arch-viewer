"""The commands read components the way `check` does (GitHub issues #21 to #25).

Each repo here is the layout its issue reported, written out file by file.
"""

import json
from pathlib import Path

from archview.cli import main

# Issues #21 and #25: loose modules at the package root, one importing a child and
# one imported by it.
SHOP = {
    "shop/__init__.py": "",
    "shop/wiring.py": "from shop.services.orders import place\n",
    "shop/paths.py": 'ROOT = "x"\n',
    "shop/services/__init__.py": "",
    "shop/services/orders.py": "from shop.paths import ROOT\n\n\ndef place():\n    return ROOT\n",
}

GROUPED_ROOT = """\
[archview]
package = "shop"
fail_on_cycles = true

[archview.components]
root = ["shop.wiring", "shop.paths"]

[archview.allowed]
root = ["services"]
services = ["root"]
"""

# Issues #22 and #23: a nested scope that splits one of its children into components.
SPLIT = {
    "archview.toml": '[archview]\npackage = "app"\n\n[archview.allowed]\nshop = []\n',
    "app/__init__.py": "",
    "app/shop/__init__.py": "",
    "app/shop/services/__init__.py": "",
    "app/shop/services/orders.py": "from app.shop.repos.interfaces.orders import OrdersRepo\n",
    "app/shop/repos/__init__.py": '"""Repositories."""\n',
    "app/shop/repos/interfaces/__init__.py": "",
    "app/shop/repos/interfaces/orders.py": "class OrdersRepo:\n    pass\n",
    "app/shop/repos/sql/__init__.py": "",
    "app/shop/repos/sql/orders.py": "from app.shop.repos.interfaces.orders import OrdersRepo\n",
}

SPLIT_RULES = """\
[archview]
fail_on_violations = true

[archview.components]
repos_interfaces = [{interfaces}]
repos_sql = [{sql}]

[archview.allowed]
repos_interfaces = []
repos_sql = ["repos_interfaces"]
services = ["repos_interfaces"]
"""


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


def split(tmp_path: Path, interfaces: str, sql: str) -> Path:
    rules = SPLIT_RULES.format(interfaces=f'"{interfaces}"', sql=f'"{sql}"')
    return write(tmp_path, {**SPLIT, "app/shop/archview.toml": rules})


def test_cycles_reads_the_components_check_reads(tmp_path, capsys):
    repo = write(tmp_path, {**SHOP, "archview.toml": GROUPED_ROOT})

    check_code, check_out, _ = run(capsys, "check", str(repo))
    code, out, _ = run(capsys, "cycles", str(repo))

    assert check_code == 1
    assert "CYCLE root -> services -> root" in check_out
    assert code == 0
    assert out.splitlines()[:3] == [
        "1 cycle",
        "",
        "in shop (components from archview.toml): root -> services -> root",
    ]
    assert "  shop/wiring.py:1  from shop.services.orders import place" in out


def test_cycles_json_names_the_rules_file_behind_the_components(tmp_path, capsys):
    repo = write(tmp_path, {**SHOP, "archview.toml": GROUPED_ROOT})

    _, out, _ = run(capsys, "cycles", str(repo), "--format", "json")

    (cycle,) = json.loads(out)["cycles"]
    assert (cycle["level"], cycle["rules"], cycle["path"]) == (
        "shop",
        "archview.toml",
        ["root", "services", "root"],
    )


def test_cycles_reads_a_nested_scope_by_its_own_components(tmp_path, capsys):
    repo = split(tmp_path, "repos.interfaces", "repos.sql")
    (repo / "app/shop/repos/interfaces/orders.py").write_text(
        "from app.shop.repos.sql.orders import OrdersRepo as Sql\n"
    )

    _, out, _ = run(capsys, "cycles", str(repo))

    assert (
        "in app.shop (components from app/shop/archview.toml): "
        "repos_interfaces -> repos_sql -> repos_interfaces"
    ) in out


def test_cycles_without_rules_still_reads_the_package_tree(tmp_path, capsys):
    repo = write(tmp_path, SHOP)

    _, out, _ = run(capsys, "cycles", str(repo))

    assert out == "no cycles under shop\n"


def test_graph_takes_a_root_relative_to_the_package(tmp_path, capsys):
    repo = write(tmp_path, SHOP)

    short = run(capsys, "graph", str(repo), "--root", "services", "--json")
    full = run(capsys, "graph", str(repo), "--root", "shop.services", "--json")

    assert short == full
    assert json.loads(short[1])["root"] == "shop.services"


def test_graph_suggests_a_close_name_for_an_unknown_root(tmp_path, capsys):
    repo = write(tmp_path, SHOP)

    code, _, err = run(capsys, "graph", str(repo), "--root", "servics")

    assert code == 2
    assert "no module or package 'servics' in shop; did you mean shop.services" in err


def test_a_nested_component_pattern_is_read_below_its_scope(tmp_path, capsys):
    repo = split(tmp_path, "repos.interfaces", "repos.sql")

    code, out, _ = run(capsys, "check", str(repo))

    assert code == 0, out
    assert "matches no module" not in out


def test_a_nested_component_pattern_may_still_be_written_in_full(tmp_path, capsys):
    repo = split(tmp_path, "app.shop.repos.interfaces", "app.shop.repos.sql")

    code, out, _ = run(capsys, "check", str(repo))

    assert code == 0, out


def test_a_nested_pattern_that_matches_nothing_says_where_it_was_read(tmp_path, capsys):
    repo = split(tmp_path, "repos.interfaces", "repos.sqll")

    _, out, _ = run(capsys, "check", str(repo))

    assert (
        "[archview.components.repos_sql] pattern 'repos.sqll' matches no module below app.shop"
    ) in out


def test_a_package_split_into_components_leaves_no_undeclared_init(tmp_path, capsys):
    repo = split(tmp_path, "repos.interfaces", "repos.sql")

    _, out, _ = run(capsys, "check", str(repo), "--format", "json")

    (scope,) = json.loads(out)["scopes"]
    assert scope["components"] == ["repos_interfaces", "repos_sql", "services"]
    assert scope["problems"] == []


def test_the_init_left_by_a_split_needs_a_rule_once_it_imports(tmp_path, capsys):
    repo = split(tmp_path, "repos.interfaces", "repos.sql")
    (repo / "app/shop/repos/__init__.py").write_text(
        "from app.shop.repos.interfaces.orders import OrdersRepo\n"
    )

    code, out, _ = run(capsys, "check", str(repo))

    assert code == 1
    assert "UNDECLARED repos is not in [archview.allowed]" in out
    assert (
        "repos is only the __init__ of app.shop.repos; its modules belong to "
        "repos_interfaces and repos_sql"
    ) in out


def test_a_rule_kept_for_the_left_over_init_gets_a_notice(tmp_path, capsys):
    repo = split(tmp_path, "repos.interfaces", "repos.sql")
    rules = repo / "app/shop/archview.toml"
    rules.write_text(rules.read_text() + "repos = []\n")

    code, out, _ = run(capsys, "check", str(repo))

    assert code == 0
    assert (
        "[archview.allowed.repos] names 'repos', which is only the __init__ of "
        "app.shop.repos; it needs no rule while it imports nothing and nothing imports it"
    ) in out


def test_folding_root_modules_shows_the_cycle_through_the_package_root(tmp_path, capsys):
    repo = write(tmp_path, SHOP)

    _, plain, _ = run(capsys, "cycles", str(repo))
    _, folded, _ = run(capsys, "cycles", str(repo), "--fold-root-modules")

    assert plain == "no cycles under shop\n"
    assert "in shop: shop -> shop.services -> shop" in folded
    assert "  shop/wiring.py:1  from shop.services.orders import place" in folded


def test_folding_root_modules_draws_them_as_one_box(tmp_path, capsys):
    repo = write(tmp_path, SHOP)

    _, out, _ = run(capsys, "graph", str(repo), "--fold-root-modules", "--json")

    view = json.loads(out)
    assert [(n["id"], n["module_count"]) for n in view["nodes"]] == [
        ("shop", 3),
        ("shop.services", 2),
    ]
    assert view["cycles"] == [["shop", "shop.services"]]


def test_folding_root_modules_applies_to_the_components_of_a_rules_file(tmp_path, capsys):
    rules = '[archview]\npackage = "shop"\n\n[archview.allowed]\npaths = []\n'
    repo = write(tmp_path, {**SHOP, "archview.toml": rules})

    _, out, _ = run(capsys, "cycles", str(repo), "--fold-root-modules")

    assert "in shop (components from archview.toml): services -> shop -> services" in out
