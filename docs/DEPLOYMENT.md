# Deployment, isolation and rollback

## Three checkouts

- **Source:** your original repository, kept on the base branch. Planning happens here. Relay commits the approved
  plan before creating the feature worktree. Unrelated dirty work blocks start/merge.
- **Feature:** `.og-relay/<project>/features/<slug>` next to the project. Serial workers and fixture smoke run here.
  Install dependencies independently from lockfiles. Never copy `.env` or real `.data` here.
- **Release:** `.og-relay/<project>/releases/<merge-sha>`, detached and pinned. Live starts here only after separate
  deployment approval. Retain old releases while processes might still read their static assets.

A Git worktree is filesystem isolation for source, not a container or a data sandbox. Project callbacks must keep
fixtures separate from persistent data. Never share mutable generated code or a source symlink between feature/live.

## Callback contract

Commands are trusted project configuration, not commands derived from user-facing app input. `smoke.restart` and
`smoke.health` run in feature; `live.stop`, `live.backup`, `live.start`, `live.health` run in the pinned release.
`live.isolation_check` runs read-only from source before merge and must reject live processes using the source or feature checkout. All are argv arrays. Environment variables give absolute source/worktree/release/run paths and the expected SHA.

Every callback must exit nonzero on failure. Health should check process ownership, expected version and an app
endpoint. A port responding alone is insufficient. The engine logs stdout/stderr and exit codes. Callbacks must
not commit or edit tracked/untracked source; generated ignored runtime files are allowed.

Backup must succeed before live start. For applications without persistent storage, explicitly document and
configure a no-op backup command. For applications with migrations, retain backups until real-data checks succeed.
Repeated deploy calls rerun stop/backup/start/health, so callbacks must tolerate retries and use new backup names.
The run state retains each attempt, even when a later deployment succeeds.

## Money integration (macOS)

`scripts/configure_money.py /path/to/money` writes only Git-local configuration. `money_runtime.py`:

1. Starts fixture smoke on 8878 with control port 8879, in the feature checkout, with no `.env` or live data links.
2. On an **approved deploy**, stops the recognized live listener on 8765. It checks process command and working
   directory and refuses an unrelated process. An existing legacy Money process in the source checkout is recognized
   for this first cutover only when it has no active child workers; otherwise finish/cancel those jobs first. New releases use a graceful SIGTERM wrapper and the stop callback waits for known workers as well as the listener. Port 8877 remains reserved for frontend tests.
3. Creates a SQLite online-backup copy with an integrity check and restrictive permissions. Its JSON receipt and
   location remain in the run directory and command logs. No database content is printed or included in this repo.
4. Links external `.data` and optional `.env` only into the detached release. Starts `app.py` there and writes an
   expected PID/cwd/SHA manifest outside the release.
5. Verifies the listener PID, process cwd, pinned Git SHA, clean source, and HTTP response before reporting healthy.

The integration assumes the existing gateway/data layout and local app ports. It does not start or reconfigure
the gateway. Updating workflows alone does not cut over an already-running live process. The merge guard blocks while it serves the source checkout. With explicit live restart approval, run `python3 scripts/bootstrap_money.py /path/to/money --confirmed` to deploy the current base into a pinned release first. Its backup and command journal live under `<git-common-dir>/og-relay/bootstrap/<sha>/`. It leaves source code and feature state unchanged. Until cutover, leave the legacy source checkout's implementation files untouched.

## Rollback

For code, inspect `git revert -m 1 <merge-sha>` on the base branch. Verify the resulting candidate and deploy it as
another release; do not edit the current running release directory. A single stage revert can violate dependent
stages and requires review.

Code reversal does **not** reverse database migrations. Choose either backward-compatible code against the newer
schema or an explicitly authorized restore from a known backup, accounting for writes made since that backup.
Do not automatically restore a backup on health failure. Keep the failed release, prior release, merge SHA and
backup receipt available for diagnosis. Rollback deployment is a deliberate operator procedure in v1, not an
unimplemented `rollback` CLI command.
