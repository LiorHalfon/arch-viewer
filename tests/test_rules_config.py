"""The rules file: loading, defaults and helpful errors (C1, C11)."""

import textwrap

import pytest

from archview.rules.config import (
    ALL,
    ROOT_ONLY_KEYS,
    Config,
    ConfigError,
    Exemption,
    Forbidden,
    find_config,
    load_config,
    load_nested_config,
    parse_config,
    parse_nested_config,
)


def written(tmp_path, text):
    path = tmp_path / "archview.toml"
    path.write_text(textwrap.dedent(text))
    return load_config(path)


FULL = """
[archview]
package = "shop"
exclude = ["**/tests/**"]
fail_on_cycles = false

[archview.allowed]
api = ["services", "domain"]
domain = []
tests = "all"

[[archview.forbidden]]
from = "domain"
to = "infra"

[[archview.exceptions]]
importer = "shop.services.legacy"
imported = "shop.api.schemas"
reason = "to be removed in TT-123"

[archview.components]
adapters = ["shop.db", "shop.http_*"]
"""


def test_reads_every_table_of_archview_toml(tmp_path):
    (tmp_path / "archview.toml").write_text(FULL)

    config = load_config(tmp_path / "archview.toml")

    assert config.package == "shop"
    assert config.exclude == ("**/tests/**",)
    assert (config.fail_on_violations, config.fail_on_cycles) == (True, False)
    assert config.allowed == {"api": ("services", "domain"), "domain": (), "tests": ALL}
    assert config.forbidden == (Forbidden("domain", "infra"),)
    assert config.exceptions == (
        Exemption("shop.services.legacy", "shop.api.schemas", "to be removed in TT-123"),
    )
    assert config.components == {"adapters": ("shop.db", "shop.http_*")}


def test_reads_the_tool_table_of_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "shop"\n\n[tool.archview.allowed]\napi = ["domain"]\n'
    )

    path = find_config(tmp_path)

    assert path == tmp_path / "pyproject.toml"
    assert load_config(path).allowed == {"api": ("domain",)}


def test_prefers_archview_toml_over_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.archview]\n")
    (tmp_path / "archview.toml").write_text("[archview]\n")

    assert find_config(tmp_path) == tmp_path / "archview.toml"


def test_finds_nothing_when_there_are_no_rules(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')

    assert find_config(tmp_path) is None


def test_defaults_fail_on_everything_and_declare_no_rules():
    assert parse_config({}) == Config()


def test_names_the_key_it_does_not_know_and_suggests_the_right_one():
    with pytest.raises(
        ConfigError, match=r"\[archview\] unknown key 'alowed'; did you mean 'allowed'"
    ):
        parse_config({"alowed": {}})


def test_rejects_an_allowed_entry_that_is_not_a_list():
    with pytest.raises(ConfigError, match=r"archview.allowed.api\] must be a list of strings"):
        parse_config({"allowed": {"api": "domain"}})


def test_a_bad_externals_undeclared_value_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="externals_undeclared"):
        written(tmp_path, '[archview]\npackage = "shop"\nexternals_undeclared = "warn"\n')


def test_requires_a_reason_for_every_exception():
    with pytest.raises(ConfigError, match="needs a non-empty 'reason'"):
        parse_config({"exceptions": [{"importer": "a.b", "imported": "c.d"}]})


def test_an_unknown_exception_kind_is_an_error(tmp_path):
    with pytest.raises(ConfigError, match="kind"):
        written(
            tmp_path,
            """
            [archview]
            package = "web"
            [[archview.exceptions]]
            importer = "web.screens"
            imported = "web.api"
            reason = "why"
            kind = "lazy"
        """,
        )


def test_kind_is_parsed(tmp_path):
    config = written(
        tmp_path,
        """
        [archview]
        package = "web"
        [[archview.exceptions]]
        importer = "web.screens"
        imported = "web.api"
        reason = "prop shapes only"
        kind = "type_only"
    """,
    )
    assert config.exceptions[0].kind == "type_only"


def test_rejects_invalid_toml_with_the_file_name(tmp_path):
    (tmp_path / "archview.toml").write_text("[archview\n")

    with pytest.raises(ConfigError, match=r"archview\.toml: not valid TOML"):
        load_config(tmp_path / "archview.toml")


def test_rejects_a_file_without_the_archview_table(tmp_path):
    (tmp_path / "archview.toml").write_text("[other]\n")

    with pytest.raises(ConfigError, match=r"no \[archview\] table"):
        load_config(tmp_path / "archview.toml")


def test_reports_a_rules_file_that_does_not_exist(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "archview.toml")


def test_reads_the_language_and_tsconfig():
    config = parse_config({"language": "typescript", "tsconfig": "server/tsconfig.json"})

    assert (config.language, config.tsconfig) == ("typescript", "server/tsconfig.json")


def test_rejects_an_unknown_language():
    with pytest.raises(ConfigError, match="language must be one of 'python', 'typescript'"):
        parse_config({"language": "java"})


def test_externals_table_is_parsed(tmp_path):
    config = written(
        tmp_path,
        """
        [archview]
        package = "shop"
        [archview.externals]
        ports = []
        llm = ["openai"]
        tools = "all"
    """,
    )
    assert config.externals == {"ports": (), "llm": ("openai",), "tools": "all"}


def test_no_externals_table_means_none(tmp_path):
    config = written(tmp_path, '[archview]\npackage = "shop"\n')
    assert config.externals is None


def test_a_stdlib_target_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="stdlib"):
        written(
            tmp_path,
            """
            [archview]
            package = "shop"
            [archview.externals]
            llm = ["subprocess"]
        """,
        )


def test_a_stdlib_forbidden_target_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="stdlib"):
        written(
            tmp_path,
            """
            [archview]
            package = "shop"
            [[archview.forbidden]]
            from = "domain"
            to = "os"
        """,
        )


def test_typescript_by_language_skips_stdlib_rejection(tmp_path):
    config = written(
        tmp_path,
        """
        [archview]
        package = "shop"
        language = "typescript"
        [archview.externals]
        deps = ["queue"]
    """,
    )
    assert config.externals == {"deps": ("queue",)}


def test_typescript_by_tsconfig_skips_stdlib_rejection(tmp_path):
    config = written(
        tmp_path,
        """
        [archview]
        package = "shop"
        tsconfig = "tsconfig.json"
        [archview.externals]
        deps = ["queue"]
    """,
    )
    assert config.externals == {"deps": ("queue",)}


def test_workspace_table_is_parsed(tmp_path):
    config = written(
        tmp_path,
        """
        [archview.workspace]
        packages = ["core", "plugin"]
        [archview.workspace.allowed]
        core = []
        plugin = ["core"]
    """,
    )
    assert config.workspace.packages == ("core", "plugin")
    assert config.workspace.allowed == {"core": (), "plugin": ("core",)}
    assert config.workspace.fail_on_violations is True
    assert config.workspace.fail_on_cycles is True


def test_no_workspace_table_means_none(tmp_path):
    assert written(tmp_path, '[archview]\npackage = "shop"\n').workspace is None


def test_an_unknown_workspace_key_is_rejected(tmp_path):
    with pytest.raises(ConfigError, match="packagess"):
        written(tmp_path, "[archview.workspace]\npackagess = []\n")


def test_workspace_forbidden_exceptions_and_baseline_are_parsed(tmp_path):
    config = written(
        tmp_path,
        """
        [archview.workspace]
        packages = ["core", "plugin"]
        baseline = "workspace-baseline.json"
        [[archview.workspace.forbidden]]
        from = "plugin"
        to = "core"
        [[archview.workspace.exceptions]]
        importer = "plugin.adapter"
        imported = "core"
        reason = "temporary, TT-1"
    """,
    )
    assert config.workspace.forbidden == (Forbidden("plugin", "core"),)
    assert config.workspace.exceptions == (Exemption("plugin.adapter", "core", "temporary, TT-1"),)
    assert config.workspace.baseline == "workspace-baseline.json"


def test_public_is_parsed(tmp_path):
    config = written(
        tmp_path,
        """
        [archview]
        package = "core"
        public = ["ports", "types"]
        """,
    )
    assert config.public == ("ports", "types")


def test_no_public_key_means_none(tmp_path):
    assert written(tmp_path, '[archview]\npackage = "core"\n').public is None


def test_an_empty_public_list_is_not_none(tmp_path):
    """`public = []` publishes nothing; an absent key publishes everything."""
    assert written(tmp_path, '[archview]\npackage = "core"\npublic = []\n').public == ()


NESTED_ROOT = Config(type_checking_imports="ignore", exclude=("**/gen/**",))
NESTED_FILE = "shop/services/archview.toml"
ROOT_ONLY_VALUES = {
    "package": "shop",
    "language": "python",
    "tsconfig": "tsconfig.json",
    "source_roots": ["src"],
    "exclude": ["x"],
    "type_checking_imports": "ignore",
    "externals": {},
    "externals_undeclared": "allow",
    "public": [],
    "workspace": {},
}


def test_a_nested_file_takes_the_rule_keys_and_inherits_the_model_keys():
    c = parse_nested_config(
        {"allowed": {"print": ["pricing"]}, "fail_on_cycles": False},
        NESTED_ROOT,
        NESTED_FILE,
        "shop.services",
    )
    assert c.allowed == {"print": ("pricing",)}
    assert (c.type_checking_imports, c.exclude, c.fail_on_cycles) == (
        "ignore",
        ("**/gen/**",),
        False,
    )
    assert c.path == NESTED_FILE


def test_every_root_only_key_has_a_test_value():
    assert set(ROOT_ONLY_VALUES) == ROOT_ONLY_KEYS


@pytest.mark.parametrize("key", sorted(ROOT_ONLY_KEYS))
def test_a_nested_file_rejects_every_root_only_key(key):
    message = (
        rf"^{NESTED_FILE.replace('.', r'\.')}: \[archview\] {key} belongs in the root rules file"
    )
    with pytest.raises(ConfigError, match=message):
        parse_nested_config({key: ROOT_ONLY_VALUES[key]}, NESTED_ROOT, NESTED_FILE, "shop.services")


def test_a_nested_typo_still_gets_a_suggestion():
    with pytest.raises(
        ConfigError, match=r"^shop/services/archview\.toml: .*did you mean 'allowed'"
    ):
        parse_nested_config({"alowed": {}}, NESTED_ROOT, NESTED_FILE, "shop.services")


def test_load_nested_config_reads_a_file_holding_only_allowed(tmp_path):
    path = tmp_path / "archview.toml"
    path.write_text('[archview.allowed]\nprint = ["pricing"]\n')
    c = load_nested_config(path, NESTED_ROOT, NESTED_FILE, "shop.services")
    assert c.allowed == {"print": ("pricing",)}


def test_load_nested_config_names_the_file_by_its_shown_path(tmp_path):
    path = tmp_path / "archview.toml"
    path.write_text("[archview\n")
    with pytest.raises(ConfigError, match=r"^shop/services/archview\.toml: not valid TOML"):
        load_nested_config(path, NESTED_ROOT, NESTED_FILE, "shop.services")


def test_load_nested_config_names_a_missing_table_by_its_shown_path(tmp_path):
    path = tmp_path / "archview.toml"
    path.write_text("[other]\n")
    with pytest.raises(ConfigError, match=r"^shop/services/archview\.toml: no \[archview\] table"):
        load_nested_config(path, NESTED_ROOT, NESTED_FILE, "shop.services")
