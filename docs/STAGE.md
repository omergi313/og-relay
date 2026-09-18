# One stage, one fresh context

The coordinator supplies an absolute feature worktree, slug, stage number and brief path. It has already called
`begin`. Work only in that worktree, never the source checkout or a release checkout.

1. Read project rules, plans/<slug>/README.md, LOG.md, your stage brief, and its precise context pointers.
   Read stages.json for ownership. Run the plan's baseline test command. If baseline failures prevent reliable work,
   report them and stop rather than attributing them to another running stage (there is no parallel writer).
2. Implement only owned paths. Request an ownership change from the coordinator when necessary; the coordinator
   checks scope, updates stages.json and commits only plan files with `Relay plan: <slug>` before work continues. Do not change plan files,
   runtime records, hooks or gates. Never reset, stash, amend, rebase, switch branches, or use `git add -A`.
3. Run appropriate checks. Commit explicitly named owned files with the exact subject
   `Plan N — <title> [<slug>]`. Additional commits use the same subject. Never fabricate a commit SHA or test result.
4. Write a JSON handoff outside the worktree, under the run's evidence directory or a temporary path:
   `{"deviations":"none or explanation","decisions":"none or decisions","issues":"none or issues"}`.
   Report its path and commit SHA to the coordinator. Do not write LOG.md or mark a Claude task completed yet.
   The coordinator runs `complete`, which executes tests itself and validates the full stage commit interval.
5. Stop after this stage. If blocked, report why and any uncommitted paths; the coordinator records `block`.
   A replacement reviews leftover work before continuing. Never silently discard an earlier attempt.

Out-of-scope edits fail validation even if later reverted: preserve evidence and escalate to the coordinator.
Do not follow an old hook's suggestion to add a revert and expect historical ownership violations to disappear.
The coordinator may explicitly revise ownership if the change truly belongs to this stage; otherwise retain the
failed attempt and plan a reviewed recovery. Do not rewrite history automatically.
