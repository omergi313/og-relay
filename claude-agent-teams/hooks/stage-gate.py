#!/usr/bin/env python3
"""TaskCompleted gate for the /ship-feature pipeline.

A task whose subject is "Plan N — <title> [<slug>]" may only be completed when, in the repo that holds
plans/<slug>/.pipeline:
  1. plans/<slug>/LOG.md has a "## Plan N" entry with "Status: done" and every "- Key:" line filled;
  2. the current branch is the pipeline's feature branch;
  3. at least one commit since the pipeline's base sha has a subject starting "Plan N —" and containing "[<slug>]";
  4. those commits touch only paths the stage owns (stages.json "owns");
  5. nothing the stage owns is left uncommitted or untracked.
Anything else (other subjects, repos with no active pipeline) passes untouched. Exit 2 = refuse, stderr = feedback.
Cheap checks only: the test suite runs in the stage itself and again at the integration gate.
"""
import fnmatch
import json
import os
import re
import subprocess
import sys

SUBJECT = re.compile(r"^Plan\s+(\d+)\s+[—–-]\s+.*\[([A-Za-z0-9_-]+)\]\s*$")


def git(root, *args):
    out = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), out.stderr.strip()))
    return out.stdout


def refuse(message):
    sys.stderr.write("stage-gate: " + message + "\n")
    sys.exit(2)


def clean(pattern):
    pattern = pattern.strip()
    if pattern.startswith("new:"):
        pattern = pattern[4:].strip()
    return pattern


def owned(path, patterns):
    for pattern in patterns:
        if pattern.endswith("/**"):
            pattern = pattern[:-2]
        if pattern.endswith("/"):
            if path.startswith(pattern):
                return True
        elif path == pattern or fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def pathspec(pattern):
    return ":(glob)" + pattern if any(c in pattern for c in "*?[") else pattern


def log_entry(text, number):
    """Return the lines of the last '## Plan N' section outside fenced blocks, or None."""
    sections, current, fenced = [], None, False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        if line.startswith("## "):
            current = [] if re.match(r"^## Plan\s+%d\b" % number, line) else None
            if current is not None:
                sections.append(current)
            continue
        if current is not None:
            current.append(line)
    return sections[-1] if sections else None


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    match = SUBJECT.match(payload.get("task_subject") or "")
    if not match:
        return
    number, slug = int(match.group(1)), match.group(2)
    cwd = payload.get("cwd") or os.getcwd()
    try:
        root = git(cwd, "rev-parse", "--show-toplevel").strip()
    except (RuntimeError, OSError):
        return
    plan_dir = os.path.join(root, "plans", slug)
    marker = os.path.join(plan_dir, ".pipeline")
    if not os.path.isfile(marker):
        return

    try:
        with open(marker) as handle:
            pipeline = json.load(handle)
        with open(os.path.join(plan_dir, "stages.json")) as handle:
            stages = json.load(handle)["stages"]
    except (OSError, ValueError, KeyError) as error:
        refuse("cannot read plans/%s/.pipeline or stages.json: %s" % (slug, error))
    stage = next((s for s in stages if int(s.get("n", -1)) == number), None)
    if stage is None:
        refuse("plan %d is not in plans/%s/stages.json; the lead must add it (n, file, title, depends_on, owns)." % (number, slug))
    patterns = [clean(p) for p in stage.get("owns", []) if clean(p)]
    if not patterns:
        refuse("plan %d has an empty 'owns' list in stages.json." % number)

    # 1. LOG entry
    try:
        with open(os.path.join(plan_dir, "LOG.md")) as handle:
            entry = log_entry(handle.read(), number)
    except OSError as error:
        refuse("cannot read LOG.md: %s" % error)
    if entry is None:
        refuse("plans/%s/LOG.md has no '## Plan %d' entry. Append it from the template (every line filled)." % (slug, number))
    fields = {}
    for line in entry:
        field = re.match(r"^- ([^:]+):\s*(.*)$", line)
        if field:
            fields[field.group(1).strip()] = field.group(2).strip()
    status = fields.get("Status", "").lower()
    if status.startswith(("blocked", "partial")):
        refuse(
            "LOG says plan %d is '%s', so the task must not be completed (dependent stages would start). "
            "Set the task back to pending with TaskUpdate, message the lead with what is needed, then stop." % (number, status)
        )
    if not status.startswith("done"):
        refuse("the Plan %d LOG entry needs 'Status: done' (found '%s')." % (number, fields.get("Status", "")))
    empty = [key for key, value in fields.items() if not value or re.fullmatch(r"<[^>]*>", value)]
    if empty:
        refuse("fill these lines in the Plan %d LOG entry: %s." % (number, ", ".join(empty)))

    # 2. branch
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != pipeline.get("branch"):
        refuse("current branch is '%s' but the pipeline runs on '%s'. Do not switch branches." % (branch, pipeline.get("branch")))

    # 3. stage commits
    commits = []
    for line in git(root, "log", "%s..HEAD" % pipeline["base_sha"], "--format=%H%x09%s").splitlines():
        sha, _, subject = line.partition("\t")
        found = SUBJECT.match(subject)
        if found and int(found.group(1)) == number and found.group(2) == slug:
            commits.append(sha)
    if not commits:
        refuse(
            "no commit for this stage. Commit only the paths you own:\n"
            '  git add -- <owned paths> && git commit -m "Plan %d — %s [%s]" -- <owned paths>\n'
            "then put the sha in the LOG entry's Commit line." % (number, stage.get("title", "<title>"), slug)
        )

    # 4. commits stay inside owned paths
    outside = set()
    for sha in commits:
        for path in git(root, "show", "--name-only", "--format=", sha).splitlines():
            if path and not owned(path, patterns):
                outside.add(path)
    if outside:
        refuse(
            "the stage commit(s) touch paths outside this plan's Owns: %s. Revert those paths in a follow-up stage commit, "
            "or message the lead if the plan really needs them (the lead updates stages.json)." % ", ".join(sorted(outside))
        )

    # 5. nothing owned is left uncommitted
    dirty = git(root, "status", "--porcelain", "--", *[pathspec(p) for p in patterns]).strip()
    if dirty:
        refuse("owned paths still have uncommitted or untracked changes:\n%s\nCommit them as part of this stage." % dirty)


if __name__ == "__main__":
    main()
