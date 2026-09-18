#!/usr/bin/env python3
"""One-time approved cutover of the current Money base to an isolated release."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import relay


def bootstrap(project, confirmed):
    relay.require(confirmed, 'Moving the live app requires explicit approval; pass --confirmed only after it is given.')
    root = relay.root_at(project)
    with relay.lock(root):
        relay.clean(root)
        relay.require((root / 'portfolio/web/runtime.py').is_file(), 'Not a recognized Money project.')
        sha = relay.head(root)
        release = root.parent / '.og-relay' / root.name / 'releases' / sha
        if not release.exists():
            release.parent.mkdir(parents=True, exist_ok=True)
            relay.git(root, 'worktree', 'add', '--detach', str(release), sha)
        relay.require(relay.head(release) == sha and not relay.git(release, 'branch', '--show-current'), 'Unexpected release checkout.')
        relay.clean(release)
        # Bootstrap has a separate journal and never becomes a feature run.
        evidence = relay.common(root) / 'bootstrap' / sha
        evidence.mkdir(parents=True, exist_ok=True)
        journal_path = evidence / 'state.json'
        journal = relay.load(journal_path) if journal_path.exists() else {'sha': sha, 'release': str(release), 'attempts': []}
        runtime = str(ROOT / 'scripts/money_runtime.py')
        env = __import__('os').environ.copy()
        env.update(RELAY_SOURCE_DIR=str(root), RELAY_WORKTREE=str(root), RELAY_RELEASE_DIR=str(release), RELAY_RUN_DIR=str(evidence), RELAY_SHA=sha)
        import subprocess
        for action in ('live-stop', 'live-backup', 'live-start', 'live-health'):
            stamp = str(__import__('time').time_ns())
            path = evidence / (action + '-' + stamp + '.log')
            journal['phase'] = action; relay.save(journal_path, journal)
            with path.open('w') as log:
                result = subprocess.run([sys.executable, runtime, action], cwd=release, env=env, stdout=log, stderr=subprocess.STDOUT)
            journal['attempts'].append({'action': action, 'exit_code': result.returncode, 'log': str(path)})
            relay.save(journal_path, journal)
            relay.require(result.returncode == 0, f'{action} failed; inspect {path}. State and backups retained; rerun after resolving the cause.')
        journal['phase'] = 'healthy'; relay.save(journal_path, journal)
        print(f'Live now serves pinned release {sha}; feature merges cannot change its files.')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('project', type=Path); p.add_argument('--confirmed', action='store_true')
    args = p.parse_args()
    try:
        bootstrap(args.project, args.confirmed)
    except (relay.RelayError, OSError) as e:
        print(f'bootstrap: {e}', file=sys.stderr); sys.exit(2)
