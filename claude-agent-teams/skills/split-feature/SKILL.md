---
name: split-feature
description: Entry point to the feature pipeline when the full implementation plan already exists. Takes a plan file (or a plan pasted in the conversation), has a fresh-context critic attack it, then has a fresh-context splitter cut it into plans/<slug>/ stage briefs (README, LOG, PROMPTS, stages.json, NN_*.md) ready for /ship-feature. Use only when the user runs /split-feature.
argument-hint: <slug> <path to the plan file> [--no-critic]
disable-model-invocation: true
---

# Split feature

The user already has the full implementation plan and wants the rest of the pipeline: **critic → split → checkpoint**,
then `/ship-feature`. You write no plan of your own and you implement nothing. This session stays light: the critic
and the splitter run in their own fresh contexts at their own effort level, so this session's effort does not matter.

Arguments: `$ARGUMENTS` — first word = slug (short snake_case; propose one from the plan's title if missing), then the
path to the plan file, optionally `--no-critic`. If no path is given, use the plan pasted or written earlier in this
conversation; if there is none, ask for it.

## 1. Put the plan where the stages can cite it

Every later reader sees only files, so the plan must be `plans/<slug>/SOURCE.md`.

- Plan file already inside `plans/<slug>/`: use it as is (its name replaces SOURCE.md everywhere below).
- Plan file elsewhere: copy it to `plans/<slug>/SOURCE.md` unchanged (`cp`, not retyped) and put one line at the top:
  `> Copied from <original path> on <date>; this copy is the source of truth for plans/<slug>/.`
- Plan only in the conversation: write it to `plans/<slug>/SOURCE.md` verbatim, without summarizing or improving it.

If `plans/<slug>/` already holds stage files or a `.pipeline`, stop and ask: a split or a run already exists there.

## 2. Critic pass (skip with `--no-critic`)

Spawn the `plan-critic` agent type with the Agent tool: prompt = the path of the plan file and one line on what the
feature is. **Do not pass a `name`** (with agent teams enabled a named agent becomes a teammate and loses the
definition's effort and skills). Wait for it.

The plan is the user's, and you did not write it, so handle findings by kind:

- **Wrong facts about the code** (a file, function, column, route, migration number or test that does not exist or
  behaves differently): verify against the code yourself; if the finding holds, correct the plan.
- **Missing mechanical work** the project's rules require (registrations, tests, docs lines): add it.
- **Design questions** (contradictions, open choices, scope, ordering that changes the design): do not decide. Ask
  the user, blockers first, one focused question at a time, each with your recommended answer.

Record everything in a "Review notes" section at the end of the plan file: what was changed, what the user decided,
what was rejected and why. If the verdict was "fix blockers first", do not split until the blockers are resolved.

## 3. Split

Spawn the `plan-splitter` agent type (again without a `name`): prompt = "Source plan: plans/<slug>/SOURCE.md. Slug:
<slug>. Cut small stages: many small stages beat few large ones, and no stage may be large (see the split-plan
skill's sizing rules)." Wait for it. Do not split in this session.

Then check the result without reading the stage files in full: `python3 -m json.tool plans/<slug>/stages.json`
parses; every stage in `stages.json` has a file that exists, a non-empty `owns`, and dependencies that exist; the
README table matches it; no two stages without a dependency path between them share an owned path; no stage brief
is longer than about 40 lines and no stage owns more than about four source files (`wc -l plans/<slug>/*.md` and
the `owns` lists are enough to see this). Send the splitter back (SendMessage) to fix what fails, naming the stage
to split further when one is too big.

## 4. Checkpoint

Do not create branches, do not commit, do not start implementation. Tell the user, briefly:

1. the stage table (number, deliverable, depends on, owns) and which chains run in parallel;
2. the decisions the critic pass and the splitter made for them;
3. next action: review `plans/<slug>/README.md`, then open a **fresh session**, run `/effort medium`, and run
   `/ship-feature <slug>`.
