#!/usr/bin/env python3
"""Install both host adapters without replacing unrelated user configuration."""
import argparse
import datetime
import json
import os
import tempfile
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def install(home, hosts):
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = home / '.local/share/og-relay/backups' / stamp
    changes = []
    def write(target, data):
        for parent in target.parents:
            if parent == home:
                break
            if parent.is_symlink():
                raise RuntimeError(f'Refusing a symlinked install parent: {parent}; choose a real installation directory.')
        if target.exists() or target.is_symlink():
            original = backup / target.relative_to(home)
            original.parent.mkdir(parents=True, exist_ok=True)
            if target.is_dir() and not target.is_symlink():
                shutil.copytree(target, original, symlinks=True)
            else:
                shutil.copy2(target, original, follow_symlinks=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix='.relay-install-', dir=target.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(data.replace('@RELAY_ROOT@', str(ROOT)))
            os.chmod(tmp, 0o644)
            os.replace(tmp, target)  # Replace the entry, never follow an existing leaf symlink.
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        changes.append(str(target))
    for host in hosts:
        source = ROOT / 'adapters' / host
        destination = home / ('.claude' if host == 'claude' else '.agents')
        for path in sorted((source / 'skills').rglob('*')):
            if path.is_file():
                write(destination / 'skills' / path.relative_to(source / 'skills'), path.read_text())
        if host == 'claude':
            for path in (source / 'agents').glob('*.md'):
                write(home / '.claude/agents' / path.name, path.read_text())
            for old, new in {'stage-implementer': 'relay-implementer', 'plan-critic': 'relay-critic', 'plan-splitter': 'relay-splitter'}.items():
                body = (source / 'agents' / (new + '.md')).read_text().replace('name: ' + new, 'name: ' + old)
                write(home / '.claude/agents' / (old + '.md'), body)
            # Replace the registered old hook path with a shim; preserve all other hooks/settings.
            shim = 'import runpy\nrunpy.run_path(' + repr(str(ROOT / 'scripts/stage_gate.py')) + ', run_name="__main__")\n'
            write(home / '.claude/hooks/stage-gate.py', shim)
            settings_path = home / '.claude/settings.json'
            settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
            hooks = settings.setdefault('hooks', {}).setdefault('TaskCompleted', [])
            target = str(home / '.claude/hooks/stage-gate.py')
            exists = any(target in h.get('command', '') for group in hooks for h in group.get('hooks', []))
            if not exists:
                hooks.append({'hooks': [{'type': 'command', 'command': f'{shlex.quote(sys.executable)} {shlex.quote(target)}'}]})
            write(settings_path, json.dumps(settings, indent=2) + '\n')
    launcher = home / '.local/bin/og-relay'
    write(launcher, '#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(ROOT / 'relay.py')) + ' "$@"\n')
    launcher.chmod(0o755)
    print(json.dumps({'installed': changes, 'backup': str(backup), 'package': str(ROOT)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home(), help='Override only for isolated installer tests.')
    parser.add_argument('--host', choices=('both', 'claude', 'codex'), default='both')
    args = parser.parse_args()
    install(args.home.resolve(), ('claude', 'codex') if args.host == 'both' else (args.host,))
