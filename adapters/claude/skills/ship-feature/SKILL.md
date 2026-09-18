---
name: ship-feature
description: Execute or resume an OG Relay feature pipeline with isolated worktrees, fresh stage workers, verified release gates, smoke testing and explicit live deployment.
argument-hint: <slug> <description-or-path> | status/smoke/finish/deploy/abandon <slug>
disable-model-invocation: true
---

# OG Relay ship

Package root: `@RELAY_ROOT@`. Use absolute paths below.
Arguments come from `$ARGUMENTS`.
Read `@RELAY_ROOT@/docs/SHIP.md` and follow it in ship mode.
Run the shared engine with `python3 "@RELAY_ROOT@/relay.py" --repo <project> <command>`.

Use the Agent tool for a fresh subagent per critic, splitter, implementer or reviewer. Use the installed
`relay-critic`, `relay-splitter`, and `relay-implementer` definitions where appropriate, without a teammate name.
Regular subagents are sufficient; agent teams and experimental team flags are not required. Pass explicit
worktree paths and bounded file pointers. Preserve the user-selected model/effort; do not assume inheritance rules.
Wait for the subagent result before advancing. If teams are explicitly requested, keep one writer and let the
coordinator validate completion before closing tasks; the installed hook uses the same engine.

`finish <slug>` means merge, then offer the separately authorized live deploy. `deploy <slug>` resumes
a merged run. A bare slug starts/resumes implementation. Other supported modes are status, smoke and abandon.
