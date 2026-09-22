---
name: split-plan
description: Split a big plan or design doc into ordered, self-contained sub plans, each sized for one fresh agent session, written to plans/<slug>/ with a README (index + shared rules), LOG.md (one entry per executed plan), PROMPTS.md (copy-paste prompt per session) and one numbered plan file per stage. Use when the user says "split this plan", "break this down into stages", "make sub plans", or hands over a plan too large to execute in one context window.
---

# Split plan

Turn one large plan into a directory of stage briefs that separate fresh sessions execute one at a time. The reason for splitting is **context size**: a session that executes one well-scoped stage stays sharp; a session that carries the whole plan degrades. Every artifact you write serves a reader with **zero context** who will read only: the README, the LOG, their own stage file, and the pointers those name.

## Inputs

1. The source plan: a file the user names, a design doc, a HANDOFF.md, or the plan in the current conversation. If it is only in conversation, first write it to a file the README can point at (e.g. `plans/<slug>/SOURCE.md`); stage files must cite a file, not "the discussion".
2. Existing conventions: read one existing `plans/*/README.md` and `LOG.md` (or `PROGRESS_LOG.md`) in the project if any exist and match their style, table columns and logging rules. Read `AGENTS.md` / `CLAUDE.md` for communication and hard constraints and copy the relevant ones verbatim into the README; do not paraphrase constraints.
3. Baseline: run the project's test command once and record the count and state. That number goes into the LOG's "Plan 0" entry.
4. **One research pass, then write from notes.** Read the source plan **once, in full, with one Read call** (never `cat` plus `sed` windows; never reopen it). In one pass, confirm the files, functions and line areas it names (use `grep -n` / `sed -n`, not whole-file reads). Write a short code map to `plans/<slug>/.codemap.md` (path → functions → line numbers → which stage). From then on write the README, the prompts and every brief from the source plan plus that map. Do not reopen source files while writing or checking briefs: the source plan has already been critic-reviewed against the code, and re-verifying per brief is what blows the context budget. Reopen a file only when the plan and the map disagree.

## Two phases

Splitting is done in two phases so that no single context carries both the whole plan and every brief.

**Phase A — outline (the splitter itself).** Inputs 1–4 above, then write, in this order: `stages.json` (the cut is decided here, before any prose), `README.md`, `LOG.md` with its Plan 0 entry, `PROMPTS.md`. Every decision a brief will need (Shared conventions, Owns, dependencies, test file names, error homes) is settled in these files. Do not write any `NN_*.md` in this phase.

**Phase B — briefs (parallel writers).** Group the stages into batches of at most three, grouped by subsystem so one writer sees related stages. For each batch spawn one `stage-brief-writer` agent with the Agent tool, all in one message so they run concurrently, **without a `name`**. Each prompt is exactly:

```
Slug: <slug>. Write stage briefs <N1>, <N2>[, <N3>] only.
Read, in this order: plans/<slug>/README.md, plans/<slug>/stages.json, plans/<slug>/.codemap.md,
then only these sections of plans/<slug>/SOURCE.md: <section headings for these stages>.
Write plans/<slug>/<NN_name>.md for each of your stages and nothing else.
```

The section list is the one thing the outline must get right: name the SOURCE headings each stage derives from (the README's stage table carries a "Design" column for this). Writers do not read other briefs, other plan directories, or source code. If the Agent tool is unavailable, write the briefs yourself, one batch at a time, in stage order.

When all writers return, run "After writing" below. A writer that reports a conflict with the README (an Owns path it needs but does not have, a convention missing) is fixed by editing the README or `stages.json`, then re-sent to that writer; never by letting the brief diverge from the table.

## Where to write

`plans/<slug>/` where `<slug>` is a short snake_case name for the feature (e.g. `indicators_and_incremental_fetch`). Files:

```
plans/<slug>/
  README.md        index: source of truth, stage table, shared rules, handoff protocol
  LOG.md           execution log: template + "Plan 0 — planning" entry
  PROMPTS.md       one self-contained prompt per session, in order
  stages.json      the stage table for machines: dependencies and owned paths (read by /ship-feature and its hook)
  01_<name>.md     stage briefs, two-digit prefix, snake_case
  02_<name>.md
  ...
```

Never put the plans anywhere else and never merge these files. The stages are executed either by `/ship-feature <slug>` (an agent team: one fresh teammate per stage, driven by `stages.json`) or by hand (the user copies prompts from PROMPTS.md into a new agent each time), so PROMPTS.md must be complete on its own and `stages.json` must agree with the README table.

## How to cut stages

- **Small stages, and more of them.** A stage is 30–90 minutes of focused work for one agent that has read only the README, LOG and its stage file. More small stages beat fewer large ones: a small stage finishes in one context window, reviews in minutes and, if it fails, costs one retry. **No stage may be large.** Split a stage when any of these holds: it touches more than about four source files, or more than one subsystem (e.g. storage and UI); its brief needs more than about 40 lines; it has more than one deliverable a stranger would test separately; you cannot name the files it will touch. When in doubt, split.
- **Not too small either.** A stage must produce something verifiable on its own: at least one new or changed test, command result or file. Fold a stage that would be a single trivial edit with no check of its own into the stage that needs it. A stage below about 20 minutes is usually that.
- **Order by dependency, not by topic.** Foundations (types, migrations, pure functions) first; API/storage next; UI last; live checks and hardening at the end. Mark stages that are independent so the user can reorder or parallelize.
- **Every stage owns its files.** For each stage list the paths it may create or edit ("Owns"): exact paths or globs, `new:` prefix for files it creates, a trailing `/` for a whole directory. Stages run in one shared working tree, so two stages may be marked parallel only if their Owns sets are disjoint. Shared registries (route tables, asset lists, migration indexes, security regression lists, package manifests) are the usual collision: give the registry to one stage of the parallel group and make the other depend on it, or serialize them. A stage's tests and fixtures are part of its Owns.
- **Every stage ends green and verifiable.** Each stage must have a concrete "Done when" that a stranger can check: test count, a command that passes, a file that exists, a payload shape. "Works well" is not a done criterion.
- **Pure before integrated.** Prefer a pure-code stage plus an integration stage over one stage that does both; pure stages are cheap to review and rarely block.
- **The last stage is the closeout** if the plan touches user-facing behavior: live/manual checks the agent cannot do alone, doc updates (README, HANDOFF, status docs), and a fresh HANDOFF for whatever is next.
- **Decide once, in the README.** Anything two stages both need (naming, versions, error shapes, rounding, payload keys) is decided in the README's "Shared conventions" so no stage re-decides it. If the source plan left a choice open, pick the default, mark it as a decision, and say which stage it must be changed before.
- **Count:** typically 6–15 stages; there is no upper cap and `/ship-feature` runs any number. Never merge stages to bring the count down. Fewer than 3 means the plan did not need splitting.

## File contents

### README.md

**Size cap: about 120 lines.** The README is an index, not a second copy of the plan. Anything already in the source plan (design, payload shapes, error cases, decisions D1..Dn) is cited by section heading, never pasted. A README past the cap is duplicating SOURCE.md; cut it.

1. Title and source of truth: the exact file and date the plans derive from. State: "Execute in order, one per fresh session: paste the matching prompt from PROMPTS.md; each session appends its entry to LOG.md."
2. Stage table: `# | File — deliverable | Design | Estimate | Depends on | Owns`. `Design` lists the source plan section headings the stage derives from (this is what Phase B writers read). Add other columns the source doc supports (owner). Below the table, one sentence naming the chains that may run in parallel.
3. Handoff protocol, numbered: read README → LOG → stage file; verify prerequisites in LOG, stop if missing; run baseline tests; implement only own scope and edit only owned paths (another path is needed → stop and ask); finish green; commit; append one LOG entry; do not start the next stage; how to leave a note for a later stage. The commit step, verbatim: "Commit only the paths you own and changed: `git add -- <paths>` then `git commit -m "Plan N — <title> [<slug>]" -- <paths>`. Never `git add -A`, never commit `LOG.md` (the lead or the user commits it), never amend, reset, stash or switch branches. On `index.lock`, wait and retry once." State that the work happens on branch `feature/<slug>` starting from a clean tree.
4. Hard constraints: copied from the repo's rules verbatim (language/version, no new deps, security guards, files that must not move, communication style).
5. Shared conventions and adopted decisions (see above): **only the choices the source plan left open**, one line each, plus a one-line pointer to the source plan's own decisions section. Do not restate decisions the source plan already made.

### LOG.md

Header: "One entry per plan, appended by the session that executed it. Newest at the bottom. Do not edit earlier entries. A plan is done only when the suite is green and the entry is written." Then the entry template in a fenced block, then the Plan 0 entry you write now.

```
## Plan N — <title> — <YYYY-MM-DD>
- Status: done | partial | blocked
- Suite: <N> tests, <green|failures: names>
- Files changed: <paths>
- Commit: <sha(s) | none — why>
- Deviations from the plan: <none | what and why>
- Decisions the next plan must know: <none | list>
- Open issues: <none | list>
- Live/user actions still needed: <none | list>
```

Every line must be filled; "Decisions the next plan must know" is the line that carries context between sessions, so the protocol must say it is mandatory. If the project has a global progress log (e.g. `plans/<other>/PROGRESS_LOG.md`), stages also add one line there; say so in the README and prompts.

### PROMPTS.md

Header: "Paste one per fresh session, in order. Wait for each session to finish before starting the next. Every prompt is self-contained." Then `## Session N` with one fenced block each. Each prompt, in this order:

1. Read `plans/<slug>/README.md`, then `LOG.md` (and the prerequisite check: "check that Plans X–Y are done; if not, stop and tell me"), then `NN_<name>.md`, and execute plan N exactly.
2. Context beyond the plan: specific sections of specific files (`HANDOFF.md §5`, `docs/X.md`), never "read the codebase".
3. Communication rule for the project, if any.
4. Rules: the hard limits for this stage (stdlib only, files that must not change and how to prove it, e.g. `sha256sum` before/after; "do not start plan N+1").
5. Finish by: the test command, the commit command with this stage's exact subject `Plan N — <title> [<slug>]` and owned paths, the log line(s) to write, any docs to update.
6. "If you are blocked, still write the LOG.md entry with Status: blocked and what is needed."

Prompts for stages that need the user (live checks, credentials, browser) say to do the autonomous part first, then walk the user through the rest one check at a time.

### stages.json

```json
{
  "slug": "<slug>",
  "test_command": "<baseline/suite command>",
  "check_command": "<full project gate, e.g. make check>",
  "stages": [
    {"n": 1, "file": "01_<name>.md", "title": "<title>", "depends_on": [], "owns": ["pkg/module.py", "new: pkg/migrations/m0012_*.py", "tests/test_module.py"], "needs_user": false}
  ]
}
```

`title` is exactly the title used in the stage file heading, the prompt's commit subject and the LOG entry. `depends_on` and `owns` repeat the README table. `needs_user: true` marks stages an unattended agent cannot finish (live checks, credentials, browser); `/ship-feature` runs their autonomous part and leaves the rest to the user.

### NN_<name>.md (stage brief)

```
# Plan N — <title> (~<estimate>)

## Goal
Two to four sentences: the end state, what must not change.

## Steps
Numbered. Each names the file (with approximate line or function), what to add or change, and any signature or payload shape in a code block. Tests are a step, not an afterthought: name the test file and what it asserts.

## Done when
Checkable facts: suite green with expected new tests, fixtures unchanged, payload shape, docs line added.

## Notes for later plans (optional)
```

Keep a stage brief to about 25–40 lines. A brief that needs more than that is carrying context that belongs in the README or is two stages.

## After writing

1. Re-read each stage file as a stranger: can it be executed with only README + LOG + this file + the pointers it names? Fix anything that assumes conversation context. Check size: a brief over about 40 lines goes back to its writer with the instruction to cut, or the stage is split in `stages.json` and the README first.
2. Check that every file named in a stage exists (or is marked "new") with `ls`/`test -e` only, never by reading it; that every file a stage's steps touch is inside its Owns; that dependencies in the table match the prompts' prerequisite checks and `stages.json`; and that no two stages without a dependency path between them share an owned path. Validate the JSON (`python3 -m json.tool plans/<slug>/stages.json`). This step is a consistency check between the files you wrote, not a second code review.
3. Confirm the Plan 0 LOG entry written in Phase A still matches (status done, baseline suite, files changed = this directory, decisions made while splitting); amend only the decisions line if Phase B added one.
4. Keep `plans/<slug>/.codemap.md`; it is small and the ship lead may cite it. It is not a stage input and no prompt names it.
5. Tell the user: the directory path, the stage count with one line each, which stages can run in parallel, and that they start either with `/ship-feature <slug>` in a fresh session at medium effort, or by pasting Session 1 from PROMPTS.md into a fresh session.
