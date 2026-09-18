#!/usr/bin/env python3
"""Install local Money runtime configuration; never start or stop either server."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import relay

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    args = parser.parse_args()
    root = relay.root_at(args.project)
    relay.require((root / 'portfolio/web/runtime.py').is_file(), 'Not a recognized Money checkout.')
    target = relay.common(root) / 'config.json'
    runtime = str(ROOT / 'scripts/money_runtime.py')
    c = {'version': 1, 'max_parallel': 1,
         'smoke': {'restart': [sys.executable, runtime, 'smoke-restart'],
                   'health': [sys.executable, runtime, 'smoke-health'], 'url': 'http://127.0.0.1:8878'},
         'live': {name: [sys.executable, runtime, 'live-' + name] for name in ('stop', 'backup', 'start', 'health')}}
    c['live']['isolation_check'] = [sys.executable, runtime, 'isolation-check']
    if target.exists():
        relay.save(target.with_name('config.backup-' + str(__import__('time').time_ns()) + '.json'), relay.load(target))
    relay.save(target, c)
    print(json.dumps({'configuration': str(target), 'servers_changed': False}, indent=2))
