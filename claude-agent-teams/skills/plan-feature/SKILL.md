---
name: plan-feature
description: First half of the feature pipeline, in two sessions. `/plan-feature <slug> <description>` turns a feature description into a full implementation plan file and has a fresh-context critic attack it, then pauses so the user can review the plan. `/plan-feature split <slug>`, run in a fresh session, has a fresh-context splitter cut the plan into plans/<slug>/ stage briefs (README, LOG, PROMPTS, stages.json, NN_*.md) ready for /ship-feature. Use only when the user runs /plan-feature.
argument-hint: <slug> [path to the feature description, or paste it after the slug] | split <slug>
disable-model-invocation: true
---

# Plan feature

You are the planner of a three-part pipeline: **plan → split → ship**. Each part runs in its own session, and the
user starts each one by hand. The user has already discussed the feature elsewhere and chose this session's model
and effort for planning depth. Your output is files, because every later step runs in a fresh context that sees
only files.

Arguments: `$ARGUMENTS`.

- `split <slug>` → this is the **split session**: skip to section 4.
- Anything else → this is the **plan session** (sections 1 to 3): the first word is the slug (short snake_case;
  propose one if missing), the rest is the feature description or a path to it. If there is no description in the
  arguments or the conversation, ask for it.

## 1. Write the full plan

Research the code as deeply as the feature needs, then write `plans/<slug>/SOURCE.md`: goal and non-goals, the
current behaviour with file/function references, the design (data model and migrations, API/payload shapes, UI,
error cases), every file to change or create, tests, acceptance criteria a stranger can check, risks, and the choices
you made where the description left them open (marked as decisions). Ask the user only what you cannot decide from
the description, the code, or a sensible default.

## 2. Critic pass

Spawn the `plan-critic` agent type with the Agent tool: prompt = the path of SOURCE.md and one line on what the
feature is. **Do not pass a `name`** (with agent teams enabled a named agent becomes a teammate and loses the
definition's effort and skills). Wait for it.

Verify each blocker and major finding against the code yourself, fix the ones that hold in SOURCE.md, and add a
short "Review notes" section at the end of SOURCE.md listing what was changed and what was rejected and why. Show
the user only findings that need their decision.

## 3. Pause (end of the plan session)

**Stop here. Do not split in this session**, even if the user asks in passing: your context is full of planning
detail, and the split must be written for readers who have none. Do not create branches, do not commit, do not
start implementation. Tell the user, briefly:

1. the plan's goal in one line, and the path `plans/<slug>/SOURCE.md`;
2. the decisions the critic pass made for them, and any finding you rejected;
3. next action: read and edit `plans/<slug>/SOURCE.md` as they like, then open a **fresh session** and run
   `/plan-feature split <slug>`.

If the user replies with changes to the plan, apply them to SOURCE.md and repeat the pause message. Do not re-run
the critic unless they ask.

## 4. Split (the split session, `split <slug>`)

Require `plans/<slug>/SOURCE.md` to exist and `plans/<slug>/stages.json` not to; if the split already exists, tell
the user and stop (they can delete the stage files and rerun). Do not read SOURCE.md yourself beyond its first
heading: this session exists so that the split is judged with an empty context.

Spawn the `plan-splitter` agent type with the Agent tool (**without a `name`**, see section 2): prompt =
"Source plan: plans/<slug>/SOURCE.md. Slug: <slug>. Cut small stages: many small stages beat few large ones, and no
stage may be large (see the split-plan skill's sizing rules)." Wait for it.

Then check the result without reading the stage files in full: `python3 -m json.tool plans/<slug>/stages.json`
parses; every stage in `stages.json` has a file, a non-empty `owns`, and dependencies that exist; the README table
matches it; no two stages without a dependency path between them share an owned path; no stage brief is longer
than about 40 lines and no stage owns more than about four source files (`wc -l plans/<slug>/*.md` and the `owns`
lists are enough to see this). Send the splitter back (SendMessage) to fix what fails, naming the stage to split
further when one is too big.

## 5. Checkpoint (end of the split session)

Do not create branches, do not commit, do not start implementation. Tell the user, briefly:

1. the stage table (number, deliverable, depends on, owns) and which chains run in parallel;
2. the decisions the splitter made for them;
3. next action: review `plans/<slug>/README.md`, then open a **fresh session**, run `/effort medium`, and run
   `/ship-feature <slug>`.
