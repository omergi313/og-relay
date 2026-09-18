# Command reference

Run `python3 /path/to/og-relay/relay.py --repo /path/to/project COMMAND ...`.
`--repo` may name the source or feature checkout; run state uses their shared Git directory.
All mutating engine commands take a repository lock. Nonzero exit (usually 2) means the transition did not pass.
Agents must read the error, not infer success from a log file existing.

| Command | Behavior |
| --- | --- |
| `validate-plan SLUG` | Validate version, required files, owned paths, unique stages/actions and acyclic dependencies. |
| `start SLUG --host claude\|codex --approved` | Commit approved plan on base; record initialization intent; create isolated feature checkout. |
| `status SLUG` | Recover interrupted initialization/merge, validate completed stages, show durable state. |
| `begin SLUG N` | Validate dependencies; reserve the only implementation slot and start an attempt interval. |
| `complete SLUG N --report FILE` | Validate handoff, execute tests, audit attempt commits, save result, commit generated LOG. |
| `validate-stage SLUG N` | Recheck structured evidence, commits, ownership and clean worktree. |
| `block SLUG N --reason TEXT` | Close the current attempt interval and record the blocker; never discard working changes. |
| `sync-log SLUG` | Rebuild LOG from state after a crash; requires a clean tree. |
| `check SLUG` | Run integration checks; reject mutated candidates; invalidate previous downstream evidence. |
| `review SLUG --report FILE` | Record an independent review report for current SHA; reject open blocker/major findings. |
| `smoke SLUG` | Restart and health-check fixtures after current integration/review pass. |
| `accept SLUG --confirmed --evidence TEXT` | Record actual user smoke acceptance for current SHA. |
| `resolve SLUG ACTION --confirmed --evidence TEXT` | Record an actual prerequisite, release or post-release action. |
| `reconcile SLUG` | Merge advanced base into feature and invalidate downstream evidence. No history rewriting. |
| `ready SLUG` | Enforce all merge requirements and the live isolation callback without merging. |
| `finish SLUG --confirmed` | Merge --no-ff after all gates; retain state; never restart live. |
| `deploy SLUG --confirmed` | Create pinned release, run stop/backup/start/health, retain every command result. |
| `close SLUG` | Mark released after live health and all action requirements; retain records. |
| `abandon SLUG --confirmed` | Mark abandoned; preserve plans, branch, worktree and evidence. |

Confirmation flags are attestations to authorization already obtained in the host session, not a way to bypass it.

## Reports

Stage handoff fields are `deviations`, `decisions`, `issues`: each a nonempty string, with `none` for no findings.
The engine supplies commit, status, attempt intervals and test evidence. Workers do not self-report test success.

Review fields are `sha` (full current candidate SHA), `reviewer`, `summary`, `findings` (array). Each finding needs
`severity` (`blocker`, `major`, `minor`), `status` (`open`, `resolved`) and `description`; also include file/line and
failure scenario where applicable. A fresh re-review is required after fixes; changing an old JSON status alone
is not an independent review. Reports live outside the working tree so recording evidence does not change HEAD.

## Recovery details

`status` validates evidence, but never launches workers. Confirm any old worker is stopped before replacing it.
A running stage can continue its attempt. A blocked stage starts a new attempt with `begin` once its cause is
resolved; prior intervals are still audited, while intervening independent-stage commits are excluded.

If LOG is dirty after a crash, inspect it and preserve relevant content before committing the coordinator's LOG
change. Do not discard work to make `sync-log` happy. A coordinator ownership adjustment during a running stage
uses a plan-only commit with exact subject `Relay plan: SLUG`; it is excluded from implementation commit counts.
Never change the title/identity of an already implemented stage; add a repair stage instead.

If `reconcile` conflicts, the gate evidence is already invalid. Resolve/commit the merge with a bounded worker,
then rerun reconcile (to update the recorded base), integration, review, smoke and acceptance. On a rewritten base
history the engine stops for explicit recovery rather than forcing Git changes.

If the source branch advances after merge, deployment still uses the recorded merge SHA. It does not deploy whatever
happens to be at HEAD later. A failed deploy keeps all previous backup receipts and can be explicitly retried.
