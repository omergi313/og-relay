---
name: relay-plan
description: Plan a feature with a fresh critic and splitter, producing an approved stage checkpoint for OG Relay.
---

# OG Relay plan

Package root: `@RELAY_ROOT@`. Use absolute paths below.
Read the slug and requested action from the user message.
Read `@RELAY_ROOT@/docs/PLAN.md` and follow it in plan mode.
Run the shared engine with `python3 "@RELAY_ROOT@/relay.py" --repo <project> <command>`.

This skill explicitly requests fresh subagents for critic, splitter, each stage, and review. Use the
available native subagent tool, with a fresh/minimal context (for example `fork_turns="none"` when supported).
Pass explicit worktree and protocol paths. Keep the configured model unless the user chooses another; do not
translate Claude model names or `/effort` commands. Wait for the result and validate with the shared engine.
Do not use app `create_thread` for internal workers. If native delegation is unavailable, provide the matching
PROMPTS.md entry for a fresh user session or use an authorized fresh `codex exec -C <worktree>` invocation.
Never use resume/fork as a substitute for a fresh worker; never disable sandbox or approvals.
