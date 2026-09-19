# Claude Code agent-teams workflow

The feature pipeline as it runs day to day in Claude Code with agent teams: three skills, three agent roles, one
hook. Plans are files, every stage runs in a fresh context, one commit per stage on `feature/<slug>`.

This is the lightweight sibling of the `relay.py` engine in the repo root. It uses a shared working tree and
Claude's experimental agent teams instead of worktrees and a gate CLI. Pick one per project, not both.

```
/plan-feature <slug> <description>       session 1: plan + critic + fixes, then PAUSE
        │   you review plans/<slug>/SOURCE.md
/plan-feature split <slug>               session 2: fresh-context splitter, stage table, then STOP
        │   you review plans/<slug>/README.md
/effort medium                           session 3
/ship-feature <slug>                     lead + one fresh Opus teammate per stage, gate, review, smoke app
        │   you UI-test on the smoke app
/ship-feature finish <slug>              merge, confirmed live restart, rollback commands
```

`/split-feature <slug> <plan file>` enters at session 2 when the plan already exists.

## Files

| Path | Purpose |
| --- | --- |
| `skills/plan-feature/` | Plan session and `split` session |
| `skills/split-feature/` | Critic + split for a plan you already have |
| `skills/split-plan/` | How stages are cut: small stages, exact owned paths, README/LOG/PROMPTS/stages.json |
| `skills/ship-feature/` | Team lead protocol; `dryrun.sh` builds a toy repo to rehearse a run |
| `agents/` | `plan-critic`, `plan-splitter`, `stage-implementer` role definitions |
| `hooks/stage-gate.py` | `TaskCompleted` hook: a stage closes only with a LOG entry, its commit, and only owned paths touched |
| `examples/pipeline.json` | Per-project smoke/live restart commands (`.claude/pipeline.json`) |
| `examples/settings.hooks.json` | The hook registration for `~/.claude/settings.json` |

## Install

```sh
cp -R skills/* ~/.claude/skills/
cp agents/*.md ~/.claude/agents/
cp hooks/stage-gate.py ~/.claude/hooks/
```

Merge `examples/settings.hooks.json` into `~/.claude/settings.json`, copy `examples/pipeline.json` to your
project's `.claude/pipeline.json` and adapt the commands, and start Claude Code with
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`.

## Stage sizing

Many small stages beat few large ones. A stage is 30 to 90 minutes, at most about four source files, one subsystem,
one deliverable, a brief under about 40 lines. There is no upper cap on the stage count, and stages are never
merged to lower it. The rules live in `skills/split-plan/SKILL.md`.
