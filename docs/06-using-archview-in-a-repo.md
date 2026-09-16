# Using archview in a repo (requirement G3)

## Adopt it

```bash
cd ~/git/some-repo
uvx --from ~/git/arch-viewer archview init            # writes archview.toml from today's imports
uvx --from ~/git/arch-viewer archview check           # passes straight away
```

Then open `archview.toml` and **delete the dependencies that should not exist**. From
then on the check fails until the code matches the design. To try rules without
touching a repo, keep them elsewhere: `archview init <repo> --config /tmp/rules.toml`
and `archview check <repo> --config /tmp/rules.toml`.

Exit codes: `0` pass, `1` failing problems, `2` the check could not run.

## Rules reference

```toml
[archview]
package = "shop"                      # default: the only package found
source_roots = ["src"]                # default: discovered
exclude = ["**/migrations/**"]        # file globs left out of everything
ignored = ["scripts"]                 # components not checked
type_checking_imports = "ignore"      # or "include": check `if TYPE_CHECKING:` imports too
fail_on_violations = true
fail_on_cycles = true
layers = ["api", ["billing", "shipping"], "domain"]   # no importing upwards; peers independent
independent = [["billing", "shipping"]]               # these may not import each other
# baseline = "archview-baseline.json"                 # default location, used when present

[archview.allowed]                    # component -> components it may import ("all" = anything)
api = ["domain", "billing", "shipping"]
domain = []

[[archview.forbidden]]                # checked even when `allowed` says "all"
from = "domain"
to = "api"

[[archview.exceptions]]               # module-level exemptions, always with a reason
importer = "shop.billing.legacy"
imported = "shop.api.schemas"
reason = "TT-123"

[archview.components]                 # dotted globs; a package pattern covers its subtree
adapters = ["shop.db", "shop.http_*"]

[archview.metrics]
threshold = 0.3                       # distance from the main sequence counted as healthy
fail_on_zones = ["pain"]              # optional: fail when a component enters a zone
ignore = ["common"]
```

Unknown keys are errors with a suggestion. A component that is not in `allowed` fails
the check, because a new top-level package is a human decision.

## Legacy code: baseline

```bash
archview check --update-baseline      # record today's failing problems in archview-baseline.json
archview check                        # known problems pass; new imports, new cycles and grown cycles fail
```

Commit the baseline. Once problems are fixed, the check warns that entries are
stale; run `--update-baseline` again so the baseline only shrinks.

## Looking at it

```bash
archview serve --watch                # browser viewer, redraws when files change
archview graph --mermaid              # paste into a PR description
archview metrics                      # Ca, Ce, I, A, D and zone per component
```

## Paragraph for the repo's CLAUDE.md / AGENTS.md

```markdown
## Architecture rules

`archview.toml` declares which top-level packages may import which. Before handing
off, run `archview check` (or `archview check --format json`). If it fails, restore
the dependency direction: invert the dependency (declare the interface in the
higher-level package, implement it in the lower-level one), move the code, or split
the module. Never edit `archview.toml` to make the check pass, and never add a new
top-level package to it yourself. Ask the human.
```

## Claude Code hook (optional)

In `.claude/settings.json`, run the check when the agent stops, and feed failures back:

```json
{
  "hooks": {
    "Stop": [
      { "hooks": [ { "type": "command", "command": "archview check >&2 || exit 2" } ] }
    ]
  }
}
```

## pre-commit (optional)

```yaml
- repo: local
  hooks:
    - id: archview
      name: archview check
      entry: archview check
      language: system
      pass_filenames: false
      types: [python]
```
