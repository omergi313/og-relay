---
name: split-feature
description: Turn an existing implementation plan into validated OG Relay stage briefs and a checkpoint.
argument-hint: <slug> <description-or-path> | status/smoke/finish/deploy/abandon <slug>
disable-model-invocation: true
---

# OG Relay split

Package root: `@RELAY_ROOT@`. Use absolute paths below.
Arguments come from `$ARGUMENTS`.
Read `@RELAY_ROOT@/docs/PLAN.md` and follow it in split mode.
Run the shared engine with `python3 "@RELAY_ROOT@/relay.py" --repo <project> <command>`.

Use the Agent tool for a fresh subagent per critic, splitter, implementer or reviewer. Use the installed
`relay-critic`, `relay-splitter`, and `relay-implementer` definitions where appropriate, without a teammate name.
Regular subagents are sufficient; agent teams and experimental team flags are not required. Pass explicit
worktree paths and bounded file pointers. Preserve the user-selected model/effort; do not assume inheritance rules.
Wait for the subagent result before advancing. If teams are explicitly requested, keep one writer and let the
coordinator validate completion before closing tasks; the installed hook uses the same engine.
