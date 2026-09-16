# 5. MCP server is optional

Date: 2026-09-16 (before M2)

## Status

Accepted.

## Context

M5 listed an MCP server (`archview mcp`, requirement G2) next to the query CLI
(`why`, `deps`, `rdeps`, `cycles`). The M5 exit test is that Claude Code answers "why
does X depend on Y" through the tool. Claude Code has a shell, so the CLI already
meets that test. The agent's main loop (run `check` before hand-off, read the
failures, fix the code) needs only the CLI, a hook and the CLAUDE.md snippet.

An MCP server would add three things: access for agents that can't run commands,
typed tools the agent can find without reading `--help`, and a process that builds
the graph once and answers many queries. It would also cost a second interface to
keep in step with the CLI, plus tool definitions that use context in every session
where it is enabled.

## Decision

M5 ships the CLI queries, `check --format json`, the hook, the CLAUDE.md snippet and
baseline mode. The MCP server is optional and unscheduled (G2 moves to **Later**).
Build it only if one of these holds:

- we need a client that has no shell (for example Claude Desktop or an IDE agent);
- timing on `tiny-tale-backend` shows repeated CLI queries are too slow for the agent
  loop, even with grimp's cache.

## Consequences

The CLI is the only agent interface we maintain. If the MCP server is built later,
it wraps the same functions the CLI calls and adds no queries of its own.
