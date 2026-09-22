---
name: ship-feature
description: Second half of the feature pipeline. Acts as the agent-team lead that executes a split plan (plans/<slug>/ with stages.json) on branch feature/<slug> — one fresh Opus teammate per stage, dependencies respected, independent stages in parallel, one commit per stage — then runs the integration gate, a fresh-context review, and restarts the smoke app for UI testing. Also `smoke` (redeploy), `finish` (merge + live restart) and `abandon` (drop the branch). Use only when the user runs /ship-feature.
argument-hint: <slug> | smoke <slug> | finish <slug> | abandon <slug>
disable-model-invocation: true
---

# Ship feature

Arguments: `$ARGUMENTS`. `smoke <slug>`, `finish <slug>` and `abandon <slug>` are at the bottom; anything else is a slug to run.

You are the **team lead**. You coordinate; you never implement, never fix a stage yourself, and never read stage
files, source files or diffs. Your context must stay small for the whole feature, so your inputs are only:
`plans/<slug>/stages.json`, entries of `plans/<slug>/LOG.md`, `git log`/`git status`, the task list, and teammates'
short messages. Requires agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) and an interactive session.

Teammates inherit **your** effort level and permission mode. This pipeline is designed for the lead at medium
effort. Before spawning anything, tell the user in one line: "Teammates inherit this session's effort — run
`/effort medium` now if you have not." Then continue; do not wait for an answer.

## 1. Preflight (stop with a clear message if any check fails)

1. `plans/<slug>/stages.json` parses; every stage file exists; every `depends_on` exists; every `owns` is non-empty.
2. No other pipeline is active: no `plans/*/.pipeline` for a different slug.
3. **New run** (no `plans/<slug>/.pipeline`):
   - `git status --porcelain` shows nothing outside `plans/<slug>/`. If it does, stop: per-stage commits need a clean
     baseline. Do not commit, stash or discard the user's work; list the paths and ask them to commit first.
   - Record the current branch as `base_branch` and its HEAD as `base_sha`; `git switch -c feature/<slug>`.
   - Add `plans/*/.pipeline` to `.git/info/exclude` if absent; write `plans/<slug>/.pipeline`:
     `{"slug": "...", "branch": "feature/<slug>", "base_branch": "...", "base_sha": "...", "stages": {}}`.
     `stages` is the progress ledger (section 3): one entry per stage keyed by its number.
   - Commit the plan directory: `git add -- plans/<slug>` and `git commit -m "Plans: <slug>" -- plans/<slug>`.
4. **Resumed run** (`.pipeline` exists): be on its branch. A stage counts as done only if LOG has `Status: done` for
   it **and** `git log <base_sha>..HEAD` has a commit whose subject starts `Plan N —` and contains `[<slug>]`.
   Commit a dirty `LOG.md`. Keep the `stages` ledger in `.pipeline` (add `"stages": {}` if an older file lacks it);
   a stage that was `running` when the run died keeps its `started` and gets `notes: "resumed"`. Any other uncommitted change belongs to a stage that died mid-way: show the paths to the
   user and ask whether the new teammate should continue from them or they should be discarded. Never decide alone.

## 2. Tasks

Create one task per stage that is not done, subject exactly `Plan N — <title> [<slug>]` (title from `stages.json`; a
hook keys on this format), description = stage file path + owned paths, dependencies from `depends_on` (dependencies
on done stages are dropped). Create all tasks before spawning anyone.

## 3. Run the stages

Loop until no task can make progress:

- For every unblocked, unowned stage task, up to **3 teammates at once**: spawn a **new** teammate with the Agent
  tool — `subagent_type: "stage-implementer"`, `name: "plan-NN"`, `model: "opus"`. Never give a second stage to an
  existing teammate: a fresh context per stage is the point of the pipeline. Spawn prompt, nothing more:

  ```
  Plan directory: plans/<slug>/. You execute plan N: plans/<slug>/NN_<name>.md.
  Your task subject: "Plan N — <title> [<slug>]". Branch: feature/<slug> (already checked out; do not switch).
  Stages running in parallel with you right now: <plan-NN list, or none>.
  Follow your protocol. Extra pointers for your stage are under "Session N" in plans/<slug>/PROMPTS.md.
  Use the ponytail skill for the implementation itself, as your protocol says.
  ```
- Two stages may run together only if `stages.json` gives them disjoint `owns`. If the split got that wrong,
  serialize them; do not edit the plan.
- On every spawn, record the wall-clock start in `.pipeline`: `stages[N] = {"started": "<ISO time>"}`. Then print the
  progress table (below).
- Then **wait**. Teammates' messages and idle notifications arrive on their own; do not poll, and do not start the
  work yourself.
- When a teammate reports done: read only that stage's LOG entry; check `git log -1` shows its commit; commit the log
  (`git commit -m "Log: plan N [<slug>]" -- plans/<slug>/LOG.md`); ask the teammate to shut down; fill the stage's
  ledger entry (`finished`, `seconds`, `tokens`, `commit`, `notes`, see below); print the progress table; spawn
  whatever became unblocked.

### Progress table (the relay to the user)

The user follows the run only through this table. Print it after every spawn, every stage completion, every
`blocked`/`partial` outcome, and whenever the user asks "status". Nothing else about a stage goes to the user mid-run
unless it needs their decision. Columns, in this order:

| Stage | Status | Time | Tokens | Notes |

- **Stage**: `N <title>`. Collapse consecutive stages into one row (`1 to 4`, `7 to 9`) only when they share a status
  and have nothing to show in Time/Tokens/Notes: `waiting` stages, or stages finished before this run with no ledger
  entry. A stage with a ledger entry always gets its own row.
- **Status**: `done, <short sha>` · `running (plan-NN)` · `waiting` · `blocked` · `partial` · `fix round (plan-NN)`
  for the integration stage · `needs user` for a `needs_user` stage whose autonomous part is done.
- **Time**: wall clock from `started` to the teammate's done message, `Xm Ys` (running stages: elapsed so far).
- **Tokens**: from the teammate's completion/task notification, which reports its token count and duration; store it
  in the ledger as an integer and print it as `52.3k`. `n/a` if the notification carried none. If it also carries a
  duration, prefer that over wall clock for finished stages.
- **Notes**: one short line, empty when there is nothing: the first item of the LOG entry's "Open issues" or
  "Live/user actions still needed" when not `none`, the reason for `blocked`/`partial`, "replaced by plan-NN-b",
  "owns extended: <path>", "suite red before start (pre-existing)". Never paste LOG prose.
- Finish with a totals row: `Total | <done>/<all> done | <sum of Time> | <sum of Tokens> |`.

The ledger lives in `.pipeline` so a resumed run prints the same table:
`"stages": {"5": {"started": "...", "finished": "...", "seconds": 812, "tokens": 52300, "commit": "ef2510e",
"notes": "..."}}`. Write it with a one-line `python3 -c` or `jq` edit; never hand-edit other keys. Stages completed
before the ledger existed have no entry and show as a collapsed `done` row.

Example, mid-run:

```
| Stage                                 | Status            | Time   | Tokens | Notes                         |
|---------------------------------------|-------------------|--------|--------|-------------------------------|
| 1 to 4                                | done              |        |        |                               |
| 5 Activity history and inspector      | done, ef2510e     | 13m 32s| 52.3k  | Back to /settings marks none  |
| 6 Kind-aware actions and cleanup move | running (plan-06) | 4m 10s | n/a    |                               |
| 7 to 9                                | waiting           |        |        |                               |
| Total                                 | 5/9 done          | 17m 42s| 52.3k  |                               |
```
- A teammate asks to edit a path it does not own: allow it only if no running or pending-parallel stage owns that
  path; then add the path to that stage's `owns` in `stages.json`, commit that file, and answer. Otherwise answer no
  and have it record the need under "Decisions the next plan must know".
- Status lag: LOG says done and the commit exists but the task is still in progress → mark it completed yourself.
- A teammate stops early or errors without a LOG entry: message it once with what is missing. If that fails, shut it
  down and spawn a replacement `plan-NN-b` whose prompt adds: "A previous attempt stopped mid-way; `git status`
  shows its uncommitted work in your owned paths. Review it before continuing."
- `Status: blocked` or `partial`: no retry. Its dependents stay blocked; independent chains continue.
- `needs_user: true` stages: the teammate does the autonomous part and logs "Live/user actions still needed"; treat
  that as done for scheduling and carry the list to the final report.

## 4. Integration gate (only when every stage is done)

1. Run `check_command` from `stages.json` yourself (this is the one heavy command the lead runs). Parallel stages
   that were each green can be red together.
2. Spawn one teammate `reviewer` (general-purpose type, `model: "opus"`): "Review the diff `<base_sha>...HEAD` of
   branch feature/<slug> against plans/<slug>/SOURCE.md and the README's hard constraints, using the code-review
   skill at high effort. Do not change code. Write findings to plans/<slug>/REVIEW.md, most severe first, each with
   file:line, the failure scenario, and the plan stage that owns the file. Message me the counts by severity."
3. Gate failures and confirmed blocker/major findings become **one** new stage: append `N+1` to `stages.json`
   (title "Integration and review fixes", `owns` = the files named, `depends_on` = all), write a short
   `plans/<slug>/NN_integration_fixes.md` listing the failures and the REVIEW.md items by reference, commit both, and
   run it like any other stage (it appears in the progress table as `fix round (plan-NN)`). One round only; what
   remains goes to the report.
4. Commit `REVIEW.md` and `LOG.md`.

The integration gate's frontend tests start their own fixture server on their own port; the smoke app must not sit on
that port (in this project it does not: 8877 for tests, 8878 for smoke).

## 5. Smoke deploy

The user UI-tests on the **smoke app**: a fixture server on its own port that serves the working tree, so "deploying"
the branch means restarting it while `feature/<slug>` is checked out. The commands live in the project's
`.claude/pipeline.json`:

```json
{"smoke": {"restart": "<cmd>", "status": "<cmd>", "url": "<url>", "notes": "<what it serves>"},
 "live":  {"restart": "<cmd>", "status": "<cmd>", "url": "<url>", "notes": "<what it serves>"}}
```

Require a clean tree (commit `LOG.md`/`REVIEW.md` first). Run `smoke.restart`, then `smoke.status`; if it fails,
show the last log lines and stop — do not touch `live`. If the file or its `smoke` entry is missing, skip the step
and say what to add. `/ship-feature smoke <slug>` repeats only this step (after a manual fix, for instance).

## 6. Report and stop

Shut down all teammates. Report: the final progress table (every stage on its own row, with its commit sha, time,
tokens and notes, plus the totals row); gate result; review counts and what was
fixed; blocked stages and what they need; every "Live/user actions still needed" line; deviations worth knowing;
the smoke URL and `smoke.notes`. If any stage owns a migration path, add: "Back up your database file before
running this branch against real data — reverting code does not revert a schema version." Next action for the user:
UI-test on the smoke app, then `/ship-feature finish <slug>` or `/ship-feature abandon <slug>`. Do not merge on
your own.

## finish <slug>

Read `.pipeline`. Require a clean tree on `feature/<slug>`. Show `git log --oneline <base_sha>..HEAD` and ask the
user to confirm the merge. Then `git switch <base_branch>`, `git merge --no-ff feature/<slug> -m "Feature: <slug>"`,
delete `plans/<slug>/.pipeline`, keep the branch unless the user asks to delete it.

Then the **live deploy**, the second test with real data. With a `live` entry in `.claude/pipeline.json`: show
`live.notes`, add the migration warning above if the feature added one, and ask the user to confirm the restart
(it serves their real data; never restart it unasked). On yes, run `live.restart` then `live.status` and give them
the URL. On failure show the last log lines; the merge stays, and they can roll back with the commands below.
Without a `live` entry, tell them to restart their app on `<base_branch>` themselves.

Finish with the rollback commands: the whole feature with `git revert -m 1 <merge sha>`, one stage with
`git revert <stage sha>`, then restart live again.

## smoke <slug>

Section 5 only: clean tree on `feature/<slug>`, `smoke.restart`, `smoke.status`, print the URL.

## abandon <slug>

Show what will be lost (`git log --oneline <base_sha>..HEAD`, `git status --short`) and ask the user to confirm,
naming the branch. After that explicit confirmation, in this order: delete `plans/<slug>/.pipeline`;
`git switch <base_branch>`; keep the plans and the log, which were committed only on the branch:
`git checkout feature/<slug> -- plans/<slug>` then `git commit -m "Plans: <slug> (abandoned)" -- plans/<slug>`;
finally `git branch -D feature/<slug>`.
