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
