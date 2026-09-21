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

Loading the repo's `typescript` means running code from its `node_modules` (the one
carve-out from "static analysis only", N2; the repo's own sources are parsed, never
executed). Analyse repos you trust, as you would before running `npm install` or
`tsc` in them. In a hoisted monorepo the package need not be in that package's own
`node_modules` — the lookup walks up the directories, as Node's does.

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
type_checking_imports = "include"     # default; "ignore" checks runtime imports only
fail_on_violations = true
fail_on_cycles = true
layers = ["api", ["billing", "shipping"], "domain"]   # no importing upwards; peers independent
independent = [["billing", "shipping"]]               # these may not import each other
# baseline = "archview-baseline.json"                 # default location, used when present

[archview.allowed]                    # component -> components it may import ("all" = anything)
api = ["domain", "billing", "shipping"]
domain = []

[archview.externals]                  # component -> packages *outside* the project it may import
llm = ["openai"]                      # a missing component here is unconstrained - no error
ports = []                            # "may reach nothing outside the project"
externals_undeclared = "error"        # optional: close the table (default "allow")

[[archview.forbidden]]                # checked even when `allowed` says "all"
from = "domain"
to = "api"

[[archview.forbidden]]                # "from" also takes "*" (every component); "to" may
from = "*"                            # name a package outside the project, PyPI or npm
to = "openai"

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

Unknown keys are errors with a suggestion.

`[archview.allowed]` and `[archview.externals]` sit next to each other in every rules
file and mean opposite things for the same shape of gap. **A component missing from
`allowed` fails the check** - a new top-level package is a human decision, so an agent
that adds one has to ask. **A component missing from `externals` is unconstrained** -
no error, nothing reported, that component may import anything outside the project.
`[archview.externals]` reads like a fence; it is an opt-in allow-list, live only for
the components you have already listed. `check` narrows that gap where it can: a
package that *is* named in the table for some component, but is also reached by a
component that is not a key at all, gets a `partial_externals` notice naming both -
"`[archview.externals]` allows `openai` for `llm`, but `checkout` also imports it and
is unconstrained." The notice only fires for a package the table already names, so a
repo with thirty third-party dependencies and two constrained components gets at most
two lines, not thirty; a package nothing imports yet is invisible to it regardless.

Set `externals_undeclared = "error"` beside the table once adoption is done, and the
asymmetry above goes away: every component that imports anything outside the project
must then be a key of `[archview.externals]`, exactly as `allowed` already requires -
a component that is not gets a failing `undeclared_externals` problem. The default
stays `"allow"` so a repo can adopt `[externals]` one component at a time instead of
having to enumerate every third-party package on day one; any other value is a
`ConfigError`, so a typo cannot read as "off".

A rule may also name a package outside the project - a PyPI or npm dependency, or a
sibling package in a workspace; archview cannot tell those two apart from one
package's model alone (ADR 0011). `[[archview.forbidden]]` can target one too, and the
rule is enforced whether or not `[archview.externals]` declares anything. `from`
always names a component (or `"*"`); an outside name there is a `ConfigError`, since
nothing archview can see imports *out of* a third-party package. Naming a stdlib
module in `to` is a separate `ConfigError` at load time, since the extractor already
drops stdlib imports from the graph and such a rule could never fire; that check is
skipped for a repo that has declared `language = "typescript"` or a `tsconfig`, since
npm has packages named `queue` or `string` that collide with Python stdlib module
names. `archview init --externals` writes `[archview.externals]` from today's
imports, the same freeze-then-delete starting point `init` already gives
`[archview.allowed]`; a plain `archview init` leaves the table out.

`type_checking_imports` defaults to `"include"`: a type-only import (`if
TYPE_CHECKING:` in Python, `import type` in TypeScript) is checked exactly like a
runtime one, because it is still a reason one file cannot be understood without the
other. Set it to `"ignore"` to check runtime imports only. In a workspace, set it in
each package's own rules file - the root's bare `[archview]` table is a `ConfigError`
if it names this key, since the root config is never consulted per-package.

## Workspace mode

A `[archview.workspace]` table at the repo root turns several packages — Python,
TypeScript, or a mix — into one architecture: each keeps its own rules file for what
happens inside it, and a second table declares what may cross between them.

```toml
[archview.workspace]
packages = ["core", "plugins/openai", "server", "web"]   # paths relative to this file
fail_on_violations = true            # default true
fail_on_cycles = true                # cycles *between* packages; default true
baseline = "archview-baseline.json"  # optional, for the cross-package rules only

[archview.workspace.allowed]         # keyed by package name (each package's own Project.package)
core    = []
openai  = ["core"]
server  = ["core", "openai"]
web     = []

[[archview.workspace.forbidden]]
from = "web"
to   = "openai"

[[archview.workspace.exceptions]]
importer = "server.wiring"
imported = "openai"
reason   = "the composition root builds the plugins from settings"
```

`allowed`, `forbidden` and `exceptions` are the same tables as a single package's
rules file, just keyed by package name instead of component name; `"all"` and the
`from = "*"` wildcard work the same way.

A cross-package import is an M7 outside edge — each package already sees a sibling as
a plain external, since it cannot tell a workspace sibling from a third-party
dependency on its own. archview attributes that outside name back to the sibling by
matching it against the sibling's aliases: its top-level module name (Python), its
`package.json` `name` with and without the `@scope/` prefix (TypeScript), or, for a
TypeScript `../`-relative import, the sibling whose directory contains the resolved
file. A name that matches no sibling is an ordinary third-party dependency, governed
by that package's own `[archview.externals]` if it has one.

### What a package publishes

By default a sibling may reach any part of a package it is allowed to import. A
package narrows that by naming its contract in **its own** rules file:

```toml
# core/archview.toml
[archview]
package = "core"
public  = ["ports", "types"]   # component names, as in [archview.allowed]
```

Now `openai = ["core"]` at the root means core's `ports` and `types` only. Reaching
anything else is a `PRIVATE` problem naming the file, the line, and what core does
publish. The contract lives with the package that owns it, so adding a sixth plugin
needs no new rule.

Three things follow from that:

- **No `public` key means the whole package is public**, so every workspace written
  before this keeps its meaning. `public = []` means it publishes nothing.
- **A grant may narrow further** with a qualified name — `server = ["core.ports"]`
  allows core's ports and nothing else of core.
- **A grant may not widen.** Naming a component its owner does not publish is an
  error at load time, not a silent no-op, because `public` would override it. Use
  `[[archview.workspace.exceptions]]`, which requires a written reason, for a
  deliberate one-off.

Outside a workspace `public` does nothing, and `check` says so rather than ignoring it.

The component an import reaches is resolved, never guessed: for Python by analysing
the sibling packages together, which sees past the squashing grimp applies to an
external import; for TypeScript from the path tsc resolved. An import tsc cannot
resolve — usually a monorepo with no tsconfig `paths` mapping for its siblings — is
reported as unplaced rather than assumed public. See ADR 0013.

**`undeclared` applies here, unlike `[archview.externals]`.** A package missing from
`[archview.workspace.allowed]` fails the check: the set of workspace packages is
closed and every one of them was added on purpose, so a new one is exactly the kind
of decision ADR 0006 says an agent must not make quietly. This is the opposite of
`[archview.externals]`, where the universe of third-party packages is open and large
and a missing entry is deliberately left unconstrained.

**A package listed without its own rules file is unconstrained inside it.** Its
model is still built (the cross-package edges need it), but its own check does not
run at all — not even for cycles — so a workspace can be adopted one package's rules
file at a time.

```bash
archview check                       # every package's own check, plus the rules between them
archview check --format json         # {"workspace": ..., "ok": ..., "packages": [...], "between": {...}}
archview check --package core        # exactly like `archview check` inside core/ itself
archview graph                       # the workspace: packages as boxes, cross-package imports as edges
archview graph --package web         # drills into one package's own view
archview cycles                      # cycles between packages
```

`--update-baseline` at the root writes every configured package's own baseline plus
the workspace baseline, in one run. `metrics`, `why`, `deps` and `rdeps` do not read
`[archview.workspace]` at all; point them at a member's own directory
(`archview metrics core`), exactly as you would if it were not part of a workspace.
`graph` and `cycles`'s `--root` and `--hide-tests`, and `graph`'s `--externals`, need
a single package; at a workspace root they fail with a usage error naming `--package`
rather than silently doing nothing.

`archview init` never writes a `[archview.workspace]` table: which packages exist and
what may depend on what is the architectural decision a human is making, not one to
infer from imports. See ADR 0012.

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
