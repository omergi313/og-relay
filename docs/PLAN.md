# Planning and splitting

Use the host adapter's delegation instructions for fresh critic and splitter sessions. Read the project's
AGENTS.md and CLAUDE.md. A skill invocation authorizes this bounded delegation; no stage implementation starts here.

1. Identify the slug and feature description. In `plan` mode, inspect relevant code and write
   `plans/<slug>/SOURCE.md`: goal, non-goals, current behavior, design, touched paths, compatibility/migrations,
   failure cases, tests, observable acceptance criteria, risks, decisions. In `split` mode, copy the supplied
   plan to SOURCE.md without dropping content. Keep the original untouched. Refuse to overwrite an existing run.
2. Ask a fresh critic to check facts against code, contradictions, missing mechanical work, unverifiable acceptance,
   dependency errors, and project constraints. The critic returns findings without editing code. Verify findings;
   correct factual errors and necessary mechanical omissions. Ask one focused question for unresolved product choices.
   Record accepted/rejected findings in SOURCE.md. `--no-critic` is allowed only when the user explicitly requests it.
3. Ask a fresh splitter to create the files below. Split by independently verifiable deliverable, with exact owned
   paths and bounded scope. Do not force an arbitrary stage count or model. Default to serial execution even for
   independent stages. A large feature can still have a dependency graph; the scheduler simply runs one ready stage.
4. Run `python3 <RELAY_ROOT>/relay.py --repo <project> validate-plan <slug>`. Fix validation errors before presenting
   the stage table and checkpoint. Stop for plan approval. Planning does not authorize implementation or live changes.

## Required artifacts

- `SOURCE.md`: the complete plan and critic dispositions.
- `README.md`: stage table (`# | Deliverable | Depends on | Owns | Estimate`), shared design decisions,
  project constraints, test commands, acceptance checklist, action phases, handoff protocol.
- `stages.json`: version 1, slug, argv arrays `test_command` and `check_command`, and stages with unique positive
  `n`, `file`, `title`, `depends_on`, nonempty `owns`, optional `actions`.
- `NN_name.md`: goal, numbered implementation steps, concrete done-when facts, precise context pointers.
- `PROMPTS.md`: one standalone prompt per stage naming the project/worktree, brief, own paths, dependencies,
  shared stage protocol at `<RELAY_ROOT>/docs/STAGE.md`, commands and commit subject. No conversation references.
- `LOG.md`: initial planning baseline and adopted decisions. After execution starts only the coordinator writes it;
  `sync-log` regenerates the execution portion from validated evidence. Keep planning decisions in SOURCE/README too.

See `<RELAY_ROOT>/examples/stages.json`. Ownership supports exact paths, trailing-directory `/`, `*` within a
path segment, and `**` across segments. Do not use `new:` or broad root globs. Include tests and shared registries.
Control files under `plans/`, `.git*`, and `.relay*` belong to the coordinator, not stage implementers.
The plan validator checks the graph, file existence and schema; a human/critic still evaluates scope and quality.

## User actions

Replace the old `needs_user` flag with named actions:

| Phase | Meaning |
| --- | --- |
| `prerequisite` | Implementation may finish, but dependent stages must wait for this action. |
| `release` | All implementation may run; merge waits for this action on the current candidate. |
| `post_release` | Live may start; closeout waits for this action. |

Put an action on the stage that produces the condition requiring it. If credentials are needed *before* any
implementation can proceed, make a small prerequisite stage or leave that stage blocked. Never mark it implemented
just because its autonomous portion is done. Action IDs are unique within the feature.

## Critic prompt

Read SOURCE.md and the referenced code, plus project rules. Return at most five highest-impact findings first,
with severity, plan section, evidence, failure scenario and suggested correction. Retain additional relevant findings
in a written report when needed. Do not implement. End with ready to split or blockers remain.

## Splitter prompt

Read SOURCE.md and this planning protocol. Write only plans/<slug>/. Produce README, stages.json, stage briefs,
PROMPTS and LOG. Commands must be argv arrays. Stages run serially; preserve true dependencies. Make every prompt
usable in a fresh session. Return the table and any decisions, then stop. Do not commit or start implementation.
