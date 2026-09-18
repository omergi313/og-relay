# Shipping and recovery

`R` below means `python3 <RELAY_ROOT>/relay.py --repo <project>`; substitute the installed absolute path.
The host adapter defines how to create fresh workers. The coordinator handles metadata and runtime commands;
implementation and review use new, bounded contexts. Read source/diffs only when a concrete coordination decision
requires evidence; prefer a fresh diagnostic worker for large investigations. Never widen permissions automatically.

## Start / resume

1. Read configuration and validate the plan. `R start <slug> --host claude|codex --approved` is allowed after plan
   approval; an explicit user request to ship the presented plan counts. It commits the approved plan on the current
   base branch and creates a dedicated feature worktree. It leaves unrelated changes alone and refuses a dirty base.
   Capture the returned worktree and use it for every implementation command. Do not run live from it.
2. For an existing run, call `R status <slug>`; do not call start again. State is in the Git common directory at
   `og-relay/runs/<slug>/state.json`, shared across worktrees and hosts. No task-list history is authoritative.
   Status recovers interrupted worktree initialization and revalidates every implemented stage. If a stage is still running after a crash, verify the previous worker
   is stopped, inspect its owned working changes with a fresh replacement, and continue that attempt. Do not begin
   a second writer. A known blocked stage is not automatically retried; resolve the cause before beginning again. Closed attempt intervals remain auditable; unrelated stages between retries are not attributed to the retry.
3. Choose one ready stage. `R begin <slug> N` checks dependencies and ensures no other writer is running. Spawn a
   new implementer with only its worktree, stage brief, this package's STAGE.md and context pointers. Never reuse a
   completed implementer. Independent chains can proceed after a blocked stage, but still one at a time.
4. When it returns, call `R complete <slug> N --report <handoff.json>`. This executes the suite, validates commits
   and ownership, saves evidence, and writes/commits LOG.md. Only then mark the corresponding task completed.
   `R validate-stage <slug> N` is the same validator used by Claude's TaskCompleted hook and recovery.
   If a crash saved evidence before writing LOG, use `R sync-log <slug>`; first resolve any dirty LOG carefully.
5. Display a compact stage/status/commit/blocker table after each transition. Distinguish implemented, waiting for
   prerequisite, release action, and post-release action. Report measured time/token usage only when available;
   unavailable is not zero. Do not sum parallel time as elapsed time (this version is serial).

## Candidate verification

1. After every stage is implemented and prerequisites are satisfied, `R check <slug>` runs the integration command
   on a clean candidate. It invalidates previous review, smoke and acceptance evidence, even when repeated.
2. Spawn a fresh reviewer with SOURCE.md, constraints, base SHA, candidate SHA, and read-only access to the diff.
   Request JSON like examples/review.json outside the worktree, with explicit severity and open/resolved status.
   Preserve the report in runtime evidence with `R review <slug> --report <review.json>`.
   Neither implementer self-review nor a coordinator claiming a review occurred counts as independent review.
3. Confirmed blockers or gate failures get one bounded repair round by default. The coordinator adds a new stage
   (new ID, explicit owns, dependencies), brief and prompt, commits the plan change, then runs begin/complete.
   Rerun **check and fresh review after fixes**. If still failing, report blocked; the retry budget never waives gates.
4. `R smoke <slug>` requires a current passing integration check and review, restarts the fixture app and checks
   health. Give the user its URL and the feature-specific acceptance checklist. After actual user acceptance,
   `R accept <slug> --confirmed --evidence '<what the user tested/approved>'` binds it to the current candidate.
   A manual fix must be committed and must go through check, review, smoke and acceptance again.
5. `R resolve <slug> <action-id> --confirmed --evidence '<user action/evidence>'` records an actual user action.
   Prerequisite actions unblock dependents. Release actions are commit-bound. Post-release actions wait for healthy live.

## Finish and live deployment

1. `R ready <slug>` checks all stages, current integration/review/smoke/acceptance, release actions and base SHA.
   If the base moved, `R reconcile <slug>` merges the new base into the feature without rewriting its stage history.
   Resolve conflicts through a bounded worker; rerun all candidate verification and acceptance. Never force the base.
2. Present the candidate, review result and merge target. Honor explicit approval already given for that candidate;
   otherwise ask once. `R finish <slug> --confirmed` merges --no-ff, retains the state and leaves live unchanged.
   No confirmation flag substitutes for actual user authorization. A changed candidate requires fresh acceptance.
3. Present the exact live target and backup/rollback behavior. After explicit live approval, run
   `R deploy <slug> --confirmed`. It creates a **new detached release worktree at the merge SHA**, then executes
   configured stop, backup, start, health commands there. Never repoint a running release checkout or start live from
   the source/feature checkout. Persistent data may live outside releases; smoke must never share it.
4. A failure retains phase, merge SHA, release path, command logs and backup outputs. `R status` recovers a merge that
   completed just before a crash. `R deploy ... --confirmed` retries deployment with explicit authorization; callbacks
   must support repeated stop/backup/start. Preserve each backup. Do not automatically restore databases.
5. Complete post-release actions, then `R close <slug>`. It marks released and retains the run record permanently.
   Provide `git revert -m 1 <merge-sha>` as the code rollback starting point; subsequent verification/redeployment and
   schema compatibility still matter. A single stage revert may break dependents; review before using it.

## Abandon

`R abandon <slug> --confirmed` requires authorization and a clean feature tree. It marks the run abandoned while
retaining the branch, worktree, plan and logs. It never force-deletes unfinished work. Offer deliberate cleanup only
when requested. The source checkout stays on its original branch.

## Scope and limitations

This is a cooperative workflow guard, not a security boundary against an agent editing its own state/scripts.
Git checkouts share object storage but not working files. Only one active run per repository and one stage at a time
are supported. Do not claim parallel worktree scheduling exists. Host sandbox/approval requirements remain in force.
Old `.pipeline` runs are not silently migrated: finish them with backed-up originals or archive them explicitly first.
