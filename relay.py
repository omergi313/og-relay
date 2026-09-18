#!/usr/bin/env python3
"""OG Relay: deterministic, local feature/release gates. Python 3.10+, stdlib only."""
import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

VERSION = 1
SLUG = re.compile(r'^[a-z0-9][a-z0-9_-]{0,63}$')
TERMINAL = {'released', 'abandoned'}


class RelayError(Exception):
    pass


def require(ok, message):
    if not ok:
        raise RelayError(message)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run(argv, cwd, **kwargs):
    p = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, **kwargs)
    require(p.returncode == 0, f'{argv[0]} failed: {p.stderr.strip() or p.stdout.strip()}')
    return p.stdout.strip()


def git(root, *args):
    return run(['git', *args], root)


def root_at(path):
    return Path(git(path, 'rev-parse', '--show-toplevel')).resolve()


def common(root):
    return Path(git(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')).resolve() / 'og-relay'


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise RelayError(f'Cannot read {path}: {e}') from e


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.relay-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


@contextlib.contextmanager
def lock(root):
    directory = common(root)
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'lock').open('a') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RelayError('Another Relay command is running; retry after it finishes.')
        yield


def slug_ok(slug):
    require(bool(SLUG.fullmatch(slug)), 'Slug must use lowercase letters, digits, _ or - (maximum 64).')


def state_path(root, slug):
    slug_ok(slug)
    return common(root) / 'runs' / slug / 'state.json'


def state(root, slug):
    s = load(state_path(root, slug))
    require(s.get('version') == VERSION, 'Unsupported run version; do not guess a migration.')
    return s


def persist(root, s):
    s['updated_at'] = now()
    save(state_path(root, s['slug']), s)


def safe_relative(value):
    require(isinstance(value, str) and value and not value.startswith(('/', ':')) and
            '..' not in Path(value).parts and '\\' not in value,
            f'Unsafe relative path: {value!r}')
    return value


def command_ok(command):
    require(isinstance(command, list) and command and all(isinstance(v, str) and v for v in command),
            'Commands must be nonempty argv arrays, e.g. ["make", "check"].')


def plan(root, slug):
    slug_ok(slug)
    directory = Path(root) / 'plans' / slug
    p = load(directory / 'stages.json')
    require(p.get('version') == VERSION and p.get('slug') == slug, 'Plan version/slug mismatch.')
    for name in ('test_command', 'check_command'):
        command_ok(p.get(name))
    stages = p.get('stages')
    require(isinstance(stages, list) and stages, 'Plan needs at least one stage.')
    ids = [s.get('n') for s in stages]
    require(all(type(n) is int and n > 0 for n in ids) and len(ids) == len(set(ids)), 'Stage IDs must be unique positive integers.')
    actions = set()
    for s in stages:
        require(isinstance(s.get('title'), str) and s['title'].strip(), 'Stage title is required.')
        brief = directory / safe_relative(s.get('file'))
        require(brief.is_file() and brief.resolve().is_relative_to(directory.resolve()), f'Missing/escaping brief: {brief}')
        require(isinstance(s.get('owns'), list) and s['owns'], f'Stage {s["n"]} needs owns.')
        for pattern in s['owns']:
            safe_relative(pattern)
            require(not pattern.startswith(('plans/', '.git', '.relay')) and pattern not in ('*', '**', '**/*'),
                    'Stages cannot own plan/control files or the entire repository.')
        require(isinstance(s.get('depends_on'), list) and all(n in ids and n != s['n'] for n in s['depends_on']), 'Invalid dependency.')
        for a in s.get('actions', []):
            require(isinstance(a.get('id'), str) and SLUG.fullmatch(a['id']) and a['id'] not in actions, 'Action IDs must be unique slugs.')
            require(a.get('phase') in ('prerequisite', 'release', 'post_release') and a.get('description'), 'Action needs phase and description.')
            actions.add(a['id'])
    by_id = {s['n']: s for s in stages}
    visiting, visited = set(), set()
    def visit(n):
        require(n not in visiting, 'Dependency cycle in stages.json.')
        if n in visited:
            return
        visiting.add(n)
        for dep in by_id[n]['depends_on']:
            visit(dep)
        visiting.remove(n)
        visited.add(n)
    for n in ids:
        visit(n)
    for filename in ('SOURCE.md', 'README.md', 'PROMPTS.md', 'LOG.md'):
        require((directory / filename).is_file(), f'Missing {filename}.')
    return p


def config(root):
    path = Path(root) / 'relay.json'
    if not path.exists():
        path = common(root) / 'config.json'
    c = load(path)
    require(c.get('version') == VERSION, 'Config version must be 1.')
    require(c.get('max_parallel', 1) == 1, 'This version supports serial execution only.')
    for kind in ('smoke', 'live'):
        require(isinstance(c.get(kind), dict), f'Config needs {kind}.')
    for k in ('restart', 'health'):
        command_ok(c['smoke'].get(k))
    for k in ('stop', 'backup', 'start', 'health'):
        command_ok(c['live'].get(k))
    return c


def dirty(root):
    return git(root, 'status', '--porcelain', '--untracked-files=all')


def clean(root):
    require(not dirty(root), f'Working tree is not clean: {root}\n{dirty(root)}')


def head(root):
    return git(root, 'rev-parse', 'HEAD')


def ancestor(root, older, newer='HEAD'):
    return subprocess.run(['git', 'merge-base', '--is-ancestor', older, newer], cwd=root, capture_output=True).returncode == 0


def work(s):
    p = Path(s['worktree'])
    require(p.is_dir(), f'Feature worktree is missing: {p}')
    require(git(p, 'branch', '--show-current') == s['branch'], 'Feature branch changed unexpectedly.')
    return p


def active(s):
    require(s['phase'] not in TERMINAL | {'merged', 'deploying', 'deployment_failed', 'live_healthy'},
            f'Run is {s["phase"]}; implementation is closed.')


def get_stage(p, n):
    found = next((s for s in p['stages'] if s['n'] == n), None)
    require(found is not None, f'Unknown stage {n}.')
    return found


def owned(path, patterns):
    for pattern in patterns:
        if pattern.endswith('/') and path.startswith(pattern):
            return True
        # Match * within a path segment; ** can span directories.
        escaped = re.escape(pattern).replace(r'\*\*', '.*').replace(r'\*', '[^/]*').replace(r'\?', '[^/]')
        if re.fullmatch(escaped, path):
            return True
    return False


def changed(root, start, end):
    return [p for p in git(root, 'diff', '--no-renames', '--name-only', '-z', start, end).split('\0') if p]


def audit_stage(root, s, stage, result):
    required = {'status', 'start_sha', 'commit', 'test', 'deviations', 'decisions', 'issues'}
    require(isinstance(result, dict) and required <= result.keys(), f'Stage {stage["n"]}: incomplete result.')
    require(result['status'] == 'implemented', f'Stage {stage["n"]} is not implemented.')
    for key in ('deviations', 'decisions', 'issues'):
        require(isinstance(result[key], str) and result[key].strip(), f'Missing {key}.')
    for sha in (result['start_sha'], result['commit']):
        require(isinstance(sha, str) and re.fullmatch('[0-9a-f]{40,64}', sha), 'Invalid commit SHA.')
        require(ancestor(root, sha), 'Stage commit is not on the feature history.')
    require(ancestor(root, result['start_sha'], result['commit']), 'Stage commit does not follow its start.')
    intervals = result.get('attempts', []) + [{'start_sha': result['start_sha'], 'end_sha': result['commit']}]
    commits = []
    previous_end = None
    for interval in intervals:
        first, last = interval['start_sha'], interval['end_sha']
        require(ancestor(root, first, last) and ancestor(root, last, result['commit']), 'Invalid attempt boundaries.')
        if previous_end:
            require(ancestor(root, previous_end, first), 'Overlapping/out-of-order attempts.')
        previous_end = last
        commits.extend(git(root, 'rev-list', '--reverse', f'{first}..{last}').splitlines())
    implementation_commits = 0
    for sha in commits:
        require(len(git(root, 'rev-list', '--parents', '-n', '1', sha).split()) == 2, 'Stage history must be linear.')
        subject = git(root, 'show', '-s', '--format=%s', sha)
        paths = changed(root, sha + '^', sha)
        if subject == f'Relay plan: {s["slug"]}' and paths and all(p.startswith(f'plans/{s["slug"]}/') for p in paths):
            continue  # Explicit coordinator metadata commit; never count it as implementation.
        require(subject == f'Plan {stage["n"]} — {stage["title"]} [{s["slug"]}]', 'Unexpected stage commit subject.')
        implementation_commits += 1
        require(paths and all(owned(p, stage['owns']) for p in paths), f'Stage {stage["n"]} commit touches unowned paths: {paths}')
    require(implementation_commits, 'Stage has no implementation commit.')
    evidence = result['test']
    require(isinstance(evidence, dict) and evidence.get('sha') == result['commit'] and evidence.get('exit_code') == 0,
            'Missing passing test evidence for stage commit.')
    require(evidence.get('command') == plan(root, s['slug'])['test_command'], 'Stage test command changed.')
    log = Path(evidence.get('log', ''))
    require(log.is_file() and hashlib.sha256(log.read_bytes()).hexdigest() == evidence.get('log_sha256'), 'Missing/modified test log.')


def stage_satisfied(s, stage):
    result = s['stages'].get(str(stage['n']), {})
    return result.get('status') == 'implemented' and all(
        a['id'] in s['actions'] for a in stage.get('actions', []) if a['phase'] == 'prerequisite')


def validate_all(s):
    w = work(s)
    p = plan(w, s['slug'])
    for stage in p['stages']:
        result = s['stages'].get(str(stage['n']))
        require(result is not None, f'Stage {stage["n"]} is incomplete.')
        audit_stage(w, s, stage, result)
        require(stage_satisfied(s, stage), f'Stage {stage["n"]} has an unresolved prerequisite action.')
    return p


def execute(root, s, command, label, cwd=None, extra=None):
    command_ok(command)
    directory = state_path(root, s['slug']).parent
    path = directory / (label + '-' + dt.datetime.now().strftime('%Y%m%d%H%M%S%f') + '.log')
    env = os.environ.copy()
    env.update({'RELAY_SOURCE_DIR': s['source'], 'RELAY_WORKTREE': s['worktree'],
                'RELAY_RUN_DIR': str(directory), 'RELAY_SHA': head(s['worktree']),
                'RELAY_RELEASE_DIR': s.get('release_dir', '')})
    env.update(extra or {})
    with path.open('w') as f:
        p = subprocess.run(command, cwd=cwd or s['worktree'], env=env, stdout=f, stderr=subprocess.STDOUT)
    return {'sha': head(s['worktree']), 'command': command, 'exit_code': p.returncode,
            'log': str(path), 'log_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'at': now()}


def invalidate(s):
    s['verification'] = {}
    s['phase'] = 'implementing'


def write_log(root, s):
    w = work(s)
    p = plan(w, s['slug'])
    lines = ['# Relay execution log', '', 'Generated by the coordinator from validated run evidence.', '']
    for stage in p['stages']:
        r = s['stages'].get(str(stage['n']), {})
        lines += [f'## Plan {stage["n"]} — {stage["title"]}', f'- Status: {r.get("status", "pending")}',
                  f'- Commit: {r.get("commit", "none")}', f'- Decisions: {r.get("decisions", "none")}',
                  f'- Deviations: {r.get("deviations", "none")}', f'- Issues: {r.get("issues", "none")}', '']
    path = w / 'plans' / s['slug'] / 'LOG.md'
    path.write_text('\n'.join(lines))
    relative = str(path.relative_to(w))
    if git(w, 'status', '--porcelain', '--', relative):
        git(w, 'add', '--', relative)
        git(w, 'commit', '-m', f'Log: {s["slug"]}', '--', relative)


def start(root, args):
    slug = args.slug
    require(not state_path(root, slug).exists(), 'Run already exists; use status to resume.')
    require(not list(root.glob('plans/*/.pipeline')), 'Legacy Relay run exists. Finish/archive it with the original workflow before upgrading.')
    p = plan(root, slug)
    c = config(root)
    # Permit the new plan, but never carry unrelated working changes into a run.
    outside = git(root, 'status', '--porcelain', '--', '.', f':(exclude)plans/{slug}')
    require(not outside, f'Commit unrelated changes first:\n{outside}')
    require(args.approved, 'Plan approval is required: --approved after user approval.')
    base_branch = git(root, 'branch', '--show-current')
    require(base_branch, 'Start from a named base branch.')
    for path in (common(root) / 'runs').glob('*/state.json'):
        other = load(path)
        require(other.get('phase') in TERMINAL, f'Run {other.get("slug")} is still active.')
    # Commit the approved plan on the base so the source checkout stays clean.
    git(root, 'add', '--', f'plans/{slug}')
    if git(root, 'diff', '--cached', '--name-only'):
        git(root, 'commit', '-m', f'Plans: {slug}', '--', f'plans/{slug}')
    base = head(root)
    parent = root.parent / '.og-relay' / root.name
    w = parent / 'features' / slug
    branch = f'codex/relay/{slug}' if args.host == 'codex' else f'feature/{slug}'
    require(not w.exists(), f'Worktree already exists: {w}')
    w.parent.mkdir(parents=True, exist_ok=True)
    s = {'version': VERSION, 'slug': slug, 'source': str(root), 'worktree': str(w), 'branch': branch,
         'base_branch': base_branch, 'base_sha': base, 'plan_sha': base, 'host': args.host,
         'phase': 'initializing', 'stages': {}, 'actions': {}, 'verification': {}, 'config': c,
         'created_at': now(), 'events': []}
    persist(root, s)  # Intent precedes branch/worktree creation, so status can recover a crash.
    initialize(root, s)
    print(json.dumps({'worktree': str(w), 'branch': branch}, indent=2))


def initialize(root, s):
    w = Path(s['worktree'])
    if not w.exists():
        exists = subprocess.run(['git', 'show-ref', '--verify', '--quiet', 'refs/heads/' + s['branch']], cwd=s['source']).returncode == 0
        if exists:
            require(git(s['source'], 'rev-parse', s['branch']) == s['base_sha'], 'Initialization branch has unexpected changes.')
            git(s['source'], 'worktree', 'add', str(w), s['branch'])
        else:
            git(s['source'], 'worktree', 'add', '-b', s['branch'], str(w), s['base_sha'])
    require(root_at(w) == w.resolve() and common(w) == common(root), 'Initialization path is not the expected worktree.')
    work(s); clean(w)
    require(head(w) == s['base_sha'], 'Initialization worktree has unexpected changes; inspect before recovery.')
    plan(w, s['slug'])
    s['phase'] = 'implementing'
    persist(root, s)


def begin(root, s, args):
    active(s)
    w = work(s)
    clean(w)
    p = plan(w, s['slug'])
    stage = get_stage(p, args.stage)
    for other in s['stages'].values():
        require(other.get('status') != 'running', 'Another stage is running; stop it and record its outcome first.')
    old = s['stages'].get(str(args.stage), {})
    require(old.get('status') != 'implemented', 'Stage already implemented.')
    for dep in stage['depends_on']:
        previous = get_stage(p, dep)
        audit_stage(w, s, previous, s['stages'].get(str(dep)))
        require(stage_satisfied(s, previous), f'Dependency {dep} still needs a prerequisite action.')
    invalidate(s)
    # Retry starts a new interval; closed attempts retain their own ownership audit.
    s['stages'][str(args.stage)] = {'status': 'running', 'start_sha': head(w), 'attempts': old.get('attempts', []), 'started_at': now()}
    persist(root, s)
    print(json.dumps({'stage': stage, 'worktree': str(w), 'start_sha': s['stages'][str(args.stage)]['start_sha']}, indent=2))


def complete(root, s, args):
    active(s)
    w = work(s)
    clean(w)
    p = plan(w, s['slug'])
    stage = get_stage(p, args.stage)
    old = s['stages'].get(str(args.stage), {})
    require(old.get('status') == 'running', 'Use begin before completing a stage.')
    report = load(args.report)
    for key in ('deviations', 'decisions', 'issues'):
        require(isinstance(report.get(key), str) and report[key].strip(), f'Report needs nonempty {key}; use "none" when appropriate.')
    sha = head(w)
    evidence = execute(root, s, p['test_command'], f'stage-{args.stage}')
    require(head(w) == sha and not dirty(w), 'Tests changed the commit or tracked/untracked files; commit/fix and rerun complete.')
    result = dict(report, status='implemented', start_sha=old['start_sha'], attempts=old.get('attempts', []), commit=sha, test=evidence)
    audit_stage(w, s, stage, result)
    s['stages'][str(args.stage)] = result
    invalidate(s)
    persist(root, s)  # Crash before LOG commit is recoverable with sync-log.
    write_log(root, s)
    persist(root, s)
    print(f'Stage {args.stage}: implemented; dependency satisfied: {stage_satisfied(s, stage)}')


def gate(root, s):
    active(s)
    p = validate_all(s)
    w = work(s)
    clean(w)
    sha = head(w)
    # A failed/repeated gate invalidates smoke/review acceptance too.
    s['verification'] = {}
    persist(root, s)
    evidence = execute(root, s, p['check_command'], 'integration')
    evidence['sha'] = sha
    if head(w) != sha or dirty(w):
        evidence['exit_code'] = 2
        evidence['invalid_reason'] = 'Integration modified the candidate; resolve changes and rerun.'
    s['verification']['check'] = evidence
    persist(root, s)
    require(evidence['exit_code'] == 0, f'Integration failed or changed the candidate; see {evidence["log"]}.')
    print(f'Integration passed at {sha}')


def check_evidence(s, kind):
    e = s['verification'].get(kind, {})
    require(e.get('sha') == head(work(s)) and e.get('exit_code') == 0, f'Missing/stale passing {kind} evidence.')
    if 'log' in e:
        f = Path(e['log'])
        require(f.is_file() and hashlib.sha256(f.read_bytes()).hexdigest() == e.get('log_sha256'), f'{kind} log missing/modified.')
    return e


def review(root, s, args):
    active(s)
    clean(work(s))
    check_evidence(s, 'check')
    report = load(args.report)
    require(report.get('sha') == head(work(s)), 'Review must name the current candidate SHA.')
    require(report.get('reviewer') and report.get('summary') and isinstance(report.get('findings'), list), 'Review needs reviewer, summary, findings.')
    for item in report['findings']:
        require(item.get('severity') in ('blocker', 'major', 'minor') and item.get('status') in ('open', 'resolved') and item.get('description'), 'Invalid review finding.')
    blockers = [f for f in report['findings'] if f['severity'] in ('blocker', 'major') and f['status'] == 'open']
    evidence = dict(report, exit_code=1 if blockers else 0, at=now())
    s['verification']['review'] = evidence
    s['verification'].pop('smoke', None)
    s['verification'].pop('acceptance', None)
    save(state_path(root, s['slug']).parent / 'review.json', report)
    persist(root, s)
    require(not blockers, 'Review has unresolved blocker/major findings. Repair, check, and re-review.')
    print('Review accepted for current candidate.')


def smoke(root, s):
    active(s)
    validate_all(s)
    w = work(s)
    clean(w)
    check_evidence(s, 'check')
    check_evidence(s, 'review')
    s['verification'].pop('smoke', None)
    s['verification'].pop('acceptance', None)
    persist(root, s)
    for command in ('restart', 'health'):
        e = execute(root, s, s['config']['smoke'][command], 'smoke-' + command)
        require(e['exit_code'] == 0, f'Smoke {command} failed; see {e["log"]}')
    clean(w)
    check_evidence(s, 'check')
    s['verification']['smoke'] = e
    persist(root, s)
    print(s['config']['smoke'].get('url', 'Smoke ready.'))


def resolve(root, s, args):
    p = plan(work(s), s['slug'])
    action = next((a for stage in p['stages'] for a in stage.get('actions', []) if a['id'] == args.action), None)
    require(action is not None, 'Unknown action.')
    require(args.confirmed and args.evidence.strip(), 'Record the user confirmation and evidence.')
    if action['phase'] == 'post_release':
        require(s['phase'] in ('live_healthy', 'released'), 'Post-release actions require healthy live deployment.')
    s['actions'][args.action] = {'evidence': args.evidence, 'at': now(), 'sha': head(work(s))}
    persist(root, s)


def ready(s):
    validate_all(s)
    w = work(s)
    clean(w)
    for kind in ('check', 'review', 'smoke', 'acceptance'):
        check_evidence(s, kind)
    for stage in plan(w, s['slug'])['stages']:
        for a in stage.get('actions', []):
            if a['phase'] == 'release':
                require(s['actions'].get(a['id'], {}).get('sha') == head(w), f'Release action {a["id"]} missing/stale.')
    source = Path(s['source'])
    require(git(source, 'rev-parse', s['base_branch']) == s['base_sha'], 'Base branch moved. Reconcile it and validate a new candidate; merge is blocked.')


def finish(root, s, args):
    require(args.confirmed, 'Merge requires explicit user approval: --confirmed.')
    if s['phase'] in ('merged', 'deploying', 'deployment_failed', 'live_healthy', 'released'):
        print(f'Already merged: {s["merge_sha"]}; use deploy or close.'); return
    ready(s)
    source = Path(s['source'])
    require(git(source, 'branch', '--show-current') == s['base_branch'], 'Source checkout must be on its recorded base branch.')
    clean(source)
    s['phase'] = 'merging'
    s['candidate_sha'] = head(work(s))
    persist(root, s)
    git(source, 'merge', '--no-ff', s['branch'], '-m', f'Feature: {s["slug"]}')
    s['merge_sha'] = head(source)
    s['phase'] = 'merged'
    persist(root, s)
    print(f'Merged {s["merge_sha"]}. Live is unchanged. Explicit deploy approval is separate.')


def deploy(root, s, args):
    require(args.confirmed, 'Live deployment requires explicit user approval: --confirmed.')
    require(s['phase'] in ('merged', 'deployment_failed', 'deploying'), 'Merge first (or resume a failed deploy).')
    source = Path(s['source'])
    sha = s['merge_sha']
    release = source.parent / '.og-relay' / source.name / 'releases' / sha
    require(release.resolve() != source.resolve() and release.resolve() != work(s).resolve(), 'Live checkout must be isolated.')
    if not release.exists():
        release.parent.mkdir(parents=True, exist_ok=True)
        git(source, 'worktree', 'add', '--detach', str(release), sha)
    require(head(release) == sha and not git(release, 'branch', '--show-current'), 'Release checkout is not pinned to the merge SHA.')
    clean(release)
    s.update(phase='deploying', release_dir=str(release))
    persist(root, s)
    try:
        # Retry stop/backup/start deliberately; never overwrite an earlier backup record.
        for name in ('stop', 'backup', 'start', 'health'):
            e = execute(root, s, s['config']['live'][name], 'live-' + name, cwd=release, extra={'RELAY_SHA': sha})
            e['sha'] = sha
            s['events'].append({'phase': name, 'evidence': e})
            persist(root, s)
            require(e['exit_code'] == 0, f'Live {name} failed; see {e["log"]}. Run record and backups retained.')
        require(head(release) == sha and not dirty(release), 'Deployment modified release sources.')
        s['phase'] = 'live_healthy'
        persist(root, s)
        print('Live is healthy. Complete post-release actions, then run close.')
    except (RelayError, OSError):
        s['phase'] = 'deployment_failed'
        persist(root, s)
        raise


def close(root, s):
    require(s['phase'] == 'live_healthy', 'Live health check has not passed.')
    for stage in plan(work(s), s['slug'])['stages']:
        for a in stage.get('actions', []):
            require(a['id'] in s['actions'], f'Outstanding action: {a["id"]}')
    s['phase'] = 'released'
    persist(root, s)
    print(f'Released. State retained at {state_path(root, s["slug"])}')


def status(root, s):
    if s['phase'] == 'initializing':
        initialize(root, s)
    # Recover the narrow crash window between successful merge and state persistence.
    if s['phase'] == 'merging':
        base = git(s['source'], 'rev-parse', s['base_branch'])
        parents = git(s['source'], 'rev-list', '--parents', '-n', '1', base).split()[1:]
        if parents == [s['base_sha'], s.get('candidate_sha')]:
            s.update(phase='merged', merge_sha=base)
            persist(root, s)
    failures = []
    p = plan(work(s), s['slug'])
    for st in p['stages']:
        r = s['stages'].get(str(st['n']), {})
        if r.get('status') == 'implemented':
            try:
                audit_stage(work(s), s, st, r)
            except RelayError as e:
                failures.append(str(e))
    print(json.dumps({'slug': s['slug'], 'phase': s['phase'], 'worktree': s['worktree'],
                      'stages': {k: v['status'] for k, v in s['stages'].items()},
                      'validation_errors': failures, 'state': str(state_path(root, s['slug']))}, indent=2))
    require(not failures, 'Recovery validation failed; do not schedule dependent stages.')


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', default='.', help='Any checkout of the project')
    sub = p.add_subparsers(dest='command', required=True)
    for command in ('validate-plan', 'start', 'status', 'begin', 'complete', 'validate-stage', 'check', 'review', 'smoke', 'accept', 'resolve', 'ready', 'finish', 'deploy', 'close', 'block', 'sync-log', 'abandon', 'reconcile'):
        q = sub.add_parser(command)
        q.add_argument('slug')
        if command in ('begin', 'complete', 'validate-stage', 'block'):
            q.add_argument('stage', type=int)
        if command in ('complete', 'review'):
            q.add_argument('--report', required=True)
        if command == 'start':
            q.add_argument('--host', choices=('claude', 'codex'), default='codex')
            q.add_argument('--approved', action='store_true')
        if command in ('finish', 'deploy', 'accept', 'resolve', 'abandon'):
            q.add_argument('--confirmed', action='store_true')
        if command in ('accept', 'resolve'):
            q.add_argument('--evidence', required=True)
        if command == 'resolve':
            q.add_argument('action')
        if command == 'block':
            q.add_argument('--reason', required=True)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        root = root_at(args.repo)
        slug_ok(args.slug)
        with lock(root):
            if args.command == 'validate-plan':
                plan(root, args.slug); print('Plan valid.'); return 0
            if args.command == 'start':
                start(root, args); return 0
            s = state(root, args.slug)
            cmd = args.command
            if cmd == 'status': status(root, s)
            elif cmd == 'begin': begin(root, s, args)
            elif cmd == 'complete': complete(root, s, args)
            elif cmd == 'validate-stage':
                st = get_stage(plan(work(s), s['slug']), args.stage)
                audit_stage(work(s), s, st, s['stages'].get(str(args.stage))); clean(work(s)); print('Stage valid.')
            elif cmd == 'sync-log':
                clean(work(s)); write_log(root, s)
            elif cmd == 'reconcile':
                active(s); clean(work(s))
                require(not any(r.get('status') == 'running' for r in s['stages'].values()), 'Finish the running stage first.')
                base = git(s['source'], 'rev-parse', s['base_branch'])
                require(ancestor(s['source'], s['base_sha'], base), 'Base history was rewritten; manual recovery required.')
                invalidate(s); persist(root, s)
                git(work(s), 'merge', '--no-edit', base)
                s['base_sha'] = base; persist(root, s)
                print('Base reconciled. Rerun check, review, smoke, and acceptance.')
            elif cmd == 'check': gate(root, s)
            elif cmd == 'review': review(root, s, args)
            elif cmd == 'smoke': smoke(root, s)
            elif cmd == 'accept':
                require(args.confirmed and args.evidence.strip(), 'Smoke acceptance requires user confirmation and evidence.')
                clean(work(s)); check_evidence(s, 'smoke')
                s['verification']['acceptance'] = {'sha': head(work(s)), 'exit_code': 0, 'evidence': args.evidence, 'at': now()}
                persist(root, s)
            elif cmd == 'resolve': resolve(root, s, args)
            elif cmd == 'ready': ready(s); print('Ready to merge.')
            elif cmd == 'finish': finish(root, s, args)
            elif cmd == 'deploy': deploy(root, s, args)
            elif cmd == 'close': close(root, s)
            elif cmd == 'block':
                active(s)
                r = s['stages'].get(str(args.stage), {})
                require(r.get('status') == 'running', 'Stage is not running.')
                r.setdefault('attempts', []).append({'start_sha': r['start_sha'], 'end_sha': head(work(s))})
                r.update(status='blocked', reason=args.reason)
                persist(root, s)
            elif cmd == 'abandon':
                active(s); require(args.confirmed, 'Abandon requires user confirmation.')
                clean(work(s)); s['phase'] = 'abandoned'; persist(root, s)
                print('Abandoned. Branch, worktree, plans, and evidence retained; inspect before manual deletion.')
        return 0
    except (RelayError, OSError, KeyError, TypeError, ValueError) as e:
        print(f'relay: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
