#!/usr/bin/env python3
"""Claude TaskCompleted adapter; delegates to the same validator used by Codex."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import relay


def main():
    try:
        payload = json.load(sys.stdin)
        match = re.fullmatch(r'Plan (\d+) [—–-] .+ \[([a-z0-9][a-z0-9_-]*)\]', payload.get('task_subject', ''))
        if not match:
            return 0
        root = relay.root_at(payload.get('cwd', '.'))
        n, slug = int(match[1]), match[2]
        path = relay.state_path(root, slug)
        if not path.exists():
            if (root / 'plans' / slug / '.pipeline').exists():
                raise relay.RelayError('Legacy run: use the backed-up original workflow or migrate explicitly; no automatic completion.')
            return 0
        return relay.main(['--repo', str(root), 'validate-stage', slug, str(n)])
    except (ValueError, OSError, relay.RelayError) as e:
        print(f'relay stage gate: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
