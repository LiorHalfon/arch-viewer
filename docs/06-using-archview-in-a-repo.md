# Using archview in a repo (requirement G3)

## Install once

```bash
uv tool install --editable ~/git/arch-viewer     # puts `archview` on the PATH; edits stay live
cd ~/git/some-repo && archview .                 # opens the viewer (same as `archview serve .`)
```

Without a checkout, install a release from GitHub. The floating tag `v0.1` always
points at the latest 0.1.x release; a minor bump (0.2.0) gets its own `v0.2`. A moved
tag is only picked up on reinstall or with `uvx --refresh`:

```bash
uv tool install --reinstall git+https://github.com/LiorHalfon/arch-viewer@v0.1
uvx --refresh --from git+https://github.com/LiorHalfon/arch-viewer@v0.1 archview check
```

## TypeScript

A `tsconfig.json` at the repo root makes archview read TypeScript (or `language =
"typescript"` / `--language typescript`). It needs Node.js on the PATH and the
project's own dependencies installed (`npm install`): archview uses the repo's
`typescript` package, so imports resolve exactly as `tsc` resolves them.

- Another tsconfig: `tsconfig = "server/tsconfig.json"` or `--tsconfig`.
- Monorepos: point archview at one package (`archview packages/core`).
- Names are paths with their extension: `archview why components/ui utils`,
  `archview graph --root myapp/components`, `[archview.components]` patterns like
  `"myapp/features/**"`, and file components are quoted keys (`"i18n.ts" = []`).
- `type_checking_imports` applies to `import type`.

A stray root `tsconfig.json` in an otherwise-Python repo (a monorepo with a JS
frontend, say) is enough to make archview read it as TypeScript; say `language =
"python"` or `--language python` to override. This is a footgun worth knowing about
before it surprises you.

Only what the tsconfig's `include` covers is analysed — build scripts, sandboxes and
anything else outside it are invisible to archview. That is intentional (it is what
`tsc` itself would compile), but it is easy to forget when a file "should" show up
and does not.

Abstractness (`A` in `archview metrics`) reads low across a React/TypeScript app: it
counts abstract classes and type-only modules, and a UI-heavy codebase has almost
none of either outside a `types/` directory, so most components land in the "zone of
pain". That is expected for this kind of app, not a defect — the useful signal is the
direction of dependencies and the cycles, not the zone column.

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

## Asking it (agents and humans)

```bash
archview why domain infra             # the imports behind domain -> infra, or the shortest chain
archview deps services                # what services imports (--externals adds third-party packages)
archview rdeps services.pricing       # who imports it; also works for externals: rdeps requests
archview cycles [--root webapp]       # every cycle at every level, as a path with its imports
```

Names can be full (`pkg.domain`) or relative to the package (`domain`). Every query
takes `--format json`, `--hide-tests` and `--runtime-only` (leave out TYPE_CHECKING
imports). `why` exits 1 when there is no dependency. See ADR 0009.

## Paragraph for the repo's CLAUDE.md / AGENTS.md

```markdown
## Architecture rules

`archview.toml` declares which top-level packages may import which. Before handing
off, run `archview check` (or `archview check --format json`). If it fails, restore
the dependency direction: invert the dependency (declare the interface in the
higher-level package, implement it in the lower-level one), move the code, or split
the module. Never edit `archview.toml` to make the check pass, and never add a new
top-level package to it yourself. Ask the human.

To understand the structure, ask the tool instead of guessing: `archview why A B`
(the imports behind A -> B), `archview deps X` / `archview rdeps X` (what X imports /
who imports X) and `archview cycles [--root X]`.
```

## Claude Code hook (optional)

In `.claude/settings.json`, run the check when the agent stops, and feed failures back:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "command -v archview >/dev/null || exit 0; archview check --stop-hook"
          }
        ]
      }
    ]
  }
}
```

`--stop-hook` blocks the stop only when the check fails, and sends the report back
to the agent. It lets the agent stop the second time in a row (`stop_hook_active`),
so a problem that needs a human cannot trap it, and it never blocks when the check
cannot run (no rules, a broken rules file). Without archview installed, the hook
does nothing.

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
