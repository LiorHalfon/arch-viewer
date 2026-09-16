# 1. No timestamp in the model JSON

Date: 2026-09-06 (M1)

## Status

Accepted.

## Context

The model JSON sketch in `docs/05-approach-and-roadmap.md` carries a `generated_at`
field. Requirement N1 says the same source must produce byte-identical JSON, so that
CI can diff it and agents can cache it.

Those two cannot both hold: a timestamp changes on every run.

## Decision

The model JSON carries `schema`, `language`, `project`, `nodes` and `imports` — no
timestamp, and no absolute paths (every `file` is relative to the analysed project
root). Determinism wins; the file system already records when a file was written.

## Consequences

`archview graph --json` is safe to commit, to diff and to cache. Anything that wants
a generation time records it outside the model. `tests/test_serialize.py` pins this
with a test that builds the same model twice and compares the bytes.
