# Migrating the original Relay workflow

The installer backs up replaced Claude skills, hook, agent aliases and settings before installing. It preserves
unrelated hooks. It adds Codex skills under `~/.agents/skills` and does not rewrite Codex configuration or model choices.

## Changes

| Original | OG Relay v1 |
| --- | --- |
| Up to three writers in one tree | One writer in a dedicated feature worktree |
| Stage-written shared LOG | Coordinator-generated LOG from validated results |
| Matching commit subject + text status | Structured results, reachable commit intervals, ownership and executed test logs |
| Review fixes followed by smoke | Integration + independent re-review after fixes |
| Manual fix followed by smoke restart | New commit requires check, review, smoke and acceptance |
| `needs_user: true` counts as done | Prerequisite / release / post-release actions with separate gates |
| `.pipeline` removed after merge | Git-local durable run state retained through deployment and closeout |
| Live serves the development checkout | Live serves a detached release at the merge SHA |
| Claude-only tasks/hooks | Shared engine, Claude adapter, Codex adapter and manual fresh-session prompts |

## Existing plans and active runs

Do not silently convert a running legacy feature. The new start command detects legacy `plans/*/.pipeline` markers;
the replacement completion hook refuses to treat those runs as new-format runs. Finish an active legacy run using
the backed-up original skills/hook, or explicitly archive it while preserving work and evidence. Do not delete a
marker just to bypass the check. The installer itself does not alter project branches or runtime data.

For an unstarted legacy plan, use split-feature / relay-split with its SOURCE.md in a **new slug** and inspect the
result. Changes include `version: 1`, argv command arrays, removal of `new:` ownership prefixes, required action
phases, and fresh prompts referencing the new stage protocol. No existing feature commits are retroactively marked
verified. Resume an OG Relay run on either host with the same slug; do not create another run to switch hosts.

## Restoring installation files

The install output names a timestamped backup directory. Restore only the corresponding files you intend to revert;
do not replace your whole settings file if it has changed since installation. Old backups are never published in
this repository. Newly installed names can be removed separately if you uninstall; project run state remains intact.
