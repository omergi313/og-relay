#!/usr/bin/env python3
"""Run the pinned Money entry point with graceful SIGTERM cleanup."""
from pathlib import Path
import runpy
import signal
import sys


def shutdown(signum, frame):
    # Ignore repeated termination signals while application's finally blocks stop workers.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise SystemExit(0)


if __name__ == '__main__':
    entry = Path(sys.argv[1]).resolve()
    sys.argv = [str(entry), *sys.argv[2:]]
    sys.path.insert(0, str(entry.parent))
    signal.signal(signal.SIGTERM, shutdown)
    runpy.run_path(str(entry), run_name='__main__')
