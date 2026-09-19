#!/bin/bash
# Builds a throwaway repo with a 3-stage toy plan (1 and 2 parallel, 3 depends on both) to try /ship-feature on.
# Usage: bash ~/.claude/skills/ship-feature/dryrun.sh [target dir]   then: cd <dir> && claude  →  /effort medium  →  /ship-feature toy
set -euo pipefail
DIR="${1:-$HOME/pipeline-dryrun}"
[ -e "$DIR" ] && { echo "$DIR already exists; remove it or pass another path" >&2; exit 1; }
mkdir -p "$DIR/calc" "$DIR/tests" "$DIR/plans/toy"
cd "$DIR"
git init -q -b main .

cat > calc/__init__.py <<'EOF'
EOF
cat > tests/test_smoke.py <<'EOF'
import unittest


class Smoke(unittest.TestCase):
    def test_import(self):
        import calc  # noqa: F401


if __name__ == "__main__":
    unittest.main()
EOF
echo "__pycache__/" > .gitignore
git add -A && git commit -qm "Baseline"

cd plans/toy
cat > SOURCE.md <<'EOF'
# Toy calculator
`calc.add(a, b)`, `calc.mul(a, b)` as separate modules, then `calc.cli` with `main(argv)` printing `add|mul a b`.
Python standard library only. Tests with unittest.
EOF
cat > README.md <<'EOF'
# Toy calculator — plan index

Source of truth: `plans/toy/SOURCE.md`. Work happens on branch `feature/toy`, starting from a clean tree.

| # | Plan — deliverable | Estimate | Depends on | Owns |
|---|--------------------|----------|------------|------|
| 1 | `01_add.md` — `calc/add.py` with `add(a, b)` + tests | 5 min | — | `new: calc/add.py`, `new: tests/test_add.py` |
| 2 | `02_mul.md` — `calc/mul.py` with `mul(a, b)` + tests | 5 min | — | `new: calc/mul.py`, `new: tests/test_mul.py` |
| 3 | `03_cli.md` — `calc/cli.py` `main(argv)` using both + tests | 10 min | 1, 2 | `new: calc/cli.py`, `new: tests/test_cli.py` |

Plans 1 and 2 are independent and may run in parallel; 3 needs both.

## Handoff protocol
1. Read this README, then `LOG.md`, then your stage file.
2. Check in `LOG.md` that every plan in your "Depends on" column has `Status: done`. If not, stop and say so.
3. Baseline: `python3 -m unittest discover -s tests`. Record the count.
4. Implement only your own scope and edit only the paths you own. Another path is needed → stop and ask.
5. Finish green: `python3 -m unittest discover -s tests`.
6. Commit only the paths you own and changed: `git add -- <paths>` then
   `git commit -m "Plan N — <title> [toy]" -- <paths>`. Never `git add -A`, never commit `LOG.md`, never amend,
   reset, stash or switch branches. On `index.lock`, wait and retry once.
7. Append one `LOG.md` entry (every line filled). Do not start the next plan.

## Hard constraints
- Python standard library only. Do not edit `calc/__init__.py`.
EOF
cat > LOG.md <<'EOF'
# Toy calculator — execution log

One entry per plan, appended by the session that executed it. Newest at the bottom. Do not edit earlier entries.

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

## Plan 0 — planning — dry run
- Status: done
- Suite: 1 tests, green
- Files changed: plans/toy/
- Commit: none — committed by the lead at preflight
- Deviations from the plan: none
- Decisions the next plan must know: none
- Open issues: none
- Live/user actions still needed: none
EOF
cat > PROMPTS.md <<'EOF'
# Prompts — paste one per fresh session (manual fallback)

## Session 1
```
Read plans/toy/README.md, then LOG.md, then 01_add.md, and execute plan 1 exactly. No extra pointers.
```
## Session 2
```
Read plans/toy/README.md, then LOG.md, then 02_mul.md, and execute plan 2 exactly. No extra pointers.
```
## Session 3
```
Read plans/toy/README.md, then LOG.md (check that Plans 1–2 are done; if not, stop and tell me), then 03_cli.md, and
execute plan 3 exactly. Extra pointers: calc/add.py, calc/mul.py.
```
EOF
cat > 01_add.md <<'EOF'
# Plan 1 — Add (~5 min)
## Goal
`calc/add.py` exposes `add(a, b)` returning `a + b`.
## Steps
1. New `calc/add.py`: `def add(a, b): return a + b`.
2. New `tests/test_add.py`: asserts `add(2, 3) == 5` and `add(-1, 1) == 0`.
## Done when
Suite green with 2 new tests; only owned paths changed.
EOF
cat > 02_mul.md <<'EOF'
# Plan 2 — Mul (~5 min)
## Goal
`calc/mul.py` exposes `mul(a, b)` returning `a * b`.
## Steps
1. New `calc/mul.py`: `def mul(a, b): return a * b`.
2. New `tests/test_mul.py`: asserts `mul(2, 3) == 6` and `mul(0, 9) == 0`.
## Done when
Suite green with 2 new tests; only owned paths changed.
EOF
cat > 03_cli.md <<'EOF'
# Plan 3 — CLI (~10 min)
## Goal
`calc/cli.py` exposes `main(argv)`: `main(["add", "2", "3"])` returns the string `"5"`, `main(["mul", "2", "3"])` returns `"6"`; unknown op raises `ValueError`.
## Steps
1. New `calc/cli.py` importing `calc.add.add` and `calc.mul.mul`; operands parsed with `int`.
2. New `tests/test_cli.py`: the three behaviours above.
## Done when
Suite green with 3 new tests; only owned paths changed.
EOF
cat > stages.json <<'EOF'
{
  "slug": "toy",
  "test_command": "python3 -m unittest discover -s tests",
  "check_command": "python3 -m unittest discover -s tests",
  "stages": [
    {"n": 1, "file": "01_add.md", "title": "Add", "depends_on": [], "owns": ["new: calc/add.py", "new: tests/test_add.py"], "needs_user": false},
    {"n": 2, "file": "02_mul.md", "title": "Mul", "depends_on": [], "owns": ["new: calc/mul.py", "new: tests/test_mul.py"], "needs_user": false},
    {"n": 3, "file": "03_cli.md", "title": "CLI", "depends_on": [1, 2], "owns": ["new: calc/cli.py", "new: tests/test_cli.py"], "needs_user": false}
  ]
}
EOF
echo "Ready: cd $DIR && claude   then   /effort medium   then   /ship-feature toy"
