#!/usr/bin/env python3
"""Money-specific smoke/live callbacks. Invoked only by an approved Relay command.

Live sources are pinned releases; .data/.env remain external. No secrets enter this package.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import relay


def listeners(port):
    p = subprocess.run(['lsof', '-nP', '-t', f'-iTCP:{port}', '-sTCP:LISTEN'], capture_output=True, text=True)
    return set(int(n) for n in p.stdout.split())


def cwd_of(pid):
    p = subprocess.run(['lsof', '-a', '-p', str(pid), '-d', 'cwd', '-Fn'], capture_output=True, text=True)
    return next((Path(line[1:]).resolve() for line in p.stdout.splitlines() if line.startswith('n')), None)


def process_table():
    p = subprocess.run(['ps', '-axo', 'pid=,ppid=,stat='], capture_output=True, text=True, check=True)
    return {int(parts[0]): (int(parts[1]), parts[2]) for line in p.stdout.splitlines() if len(parts := line.split()) == 3}


def descendants(table, parents):
    found = set(parents)
    while True:
        more = {pid for pid, (ppid, status) in table.items() if ppid in found and not status.startswith('Z')}
        if more <= found:
            return found - set(parents)
        found |= more


def stop(port, allowed):
    watched = set()
    for pid in listeners(port):
        cwd = cwd_of(pid)
        command = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True).stdout
        relay.require(cwd in allowed and ('app.py' in command or 'tests.frontend.server' in command),
                      f'Port {port} belongs to an unrecognized process {pid}; inspect it, do not kill it automatically.')
        children = descendants(process_table(), {pid})
        graceful = 'money_app.py' in command
        relay.require(graceful or not children,
                      'Legacy server has active child workers. Finish/cancel those jobs before the first release cutover.')
        watched |= {pid} | children
        # New releases have a SIGTERM handler that runs the application's finally/worker cleanup.
        # A legacy server is only stopped when no child workers exist; never force-kill a tree.
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 55
    while time.monotonic() < deadline:
        table = process_table()
        watched |= descendants(table, watched)
        alive = {pid for pid in watched if pid in table and not table[pid][1].startswith('Z')}
        if not listeners(port) and not alive:
            return
        time.sleep(.2)
    raise relay.RelayError(f'Port {port} or workers {sorted(alive)} did not stop within 55 seconds; backup/start blocked.')


def health(port, cwd, sha, manifest):
    m = relay.load(manifest)
    relay.require(m.get('sha') == sha and Path(m.get('cwd', '')).resolve() == cwd.resolve(), 'Running version manifest does not match the candidate.')
    relay.require(m.get('pid') in listeners(port) and cwd_of(m['pid']) == cwd.resolve(), 'The expected release process does not own the port.')
    relay.require(relay.head(cwd) == sha and not relay.dirty(cwd), 'Running checkout changed since launch.')
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=3) as response:
        relay.require(response.status == 200, 'HTTP health failed.')
    print(json.dumps({'healthy': True, 'sha': sha, 'cwd': str(cwd), 'port': port}))


def launch(argv, cwd, env, port, sha, manifest, log):
    relay.require(not listeners(port), f'Port {port} is already occupied.')
    with log.open('ab') as out:
        p = subprocess.Popen(argv, cwd=cwd, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    relay.save(manifest, {'pid': p.pid, 'cwd': str(cwd), 'sha': sha, 'port': port})
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        relay.require(p.poll() is None, f'App exited; read {log}')
        try:
            health(port, cwd, sha, manifest)
            return
        except (relay.RelayError, OSError):
            time.sleep(.3)
    raise relay.RelayError(f'App did not become healthy; read {log}')


def link_external(target, source):
    if target.is_symlink():
        relay.require(target.resolve() == source.resolve(), f'Unexpected symlink: {target}')
    elif target.exists():
        raise relay.RelayError(f'Refusing to replace existing release data: {target}')
    else:
        target.symlink_to(source.resolve(), target_is_directory=source.is_dir())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['isolation-check', 'smoke-restart', 'smoke-health', 'live-stop', 'live-backup', 'live-start', 'live-health'])
    args = parser.parse_args()
    source = Path(os.environ['RELAY_SOURCE_DIR']).resolve()
    work = Path(os.environ['RELAY_WORKTREE']).resolve()
    runtime = relay.common(source) / 'money-runtime'; runtime.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if args.action == 'isolation-check':
        for pid in listeners(8765):
            cwd = cwd_of(pid)
            relay.require(cwd is not None and cwd not in (source, work),
                          'Live still serves a development checkout. Approve scripts/bootstrap_money.py PROJECT --confirmed, or stop legacy live before merging.')
        print('Live does not serve source or feature files.')
        return
    if args.action.startswith('smoke-'):
        relay.require(not (work / '.data').is_symlink() and not (work / '.env').exists(), 'Smoke must not link live data or load .env.')
        sha = relay.head(work)
        manifest = runtime / 'smoke.json'
        if args.action == 'smoke-restart':
            allowed = {work, source}
            if manifest.exists(): allowed.add(Path(relay.load(manifest)['cwd']).resolve())
            stop(8878, allowed)
            launch([sys.executable, '-m', 'tests.frontend.server', '--port', '8878', '--control-port', '8879'],
                   work, env, 8878, sha, manifest, runtime / 'smoke.log')
        else:
            health(8878, work, sha, manifest)
        return
    release = Path(os.environ['RELAY_RELEASE_DIR']).resolve()
    sha = os.environ['RELAY_SHA']
    relay.require(release not in (source, work) and relay.head(release) == sha and not relay.git(release, 'branch', '--show-current'),
                  'Live requires a detached, pinned release checkout.')
    manifest = runtime / 'live.json'
    if args.action == 'live-stop':
        allowed = {source, release}
        if manifest.exists(): allowed.add(Path(relay.load(manifest)['cwd']).resolve())
        stop(8765, allowed)
    elif args.action == 'live-backup':
        relay.require(not listeners(8765), 'Stop live before backing up.')
        database = source / '.data/portfolio.sqlite3'
        relay.require(database.is_file(), 'Existing live database is missing; refusing to initialize a replacement.')
        directory = source / '.data/backups'; directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = directory / f'relay-{stamp}-{sha[:12]}.sqlite3'
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600); os.close(fd)
        src = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        dst = sqlite3.connect(backup)
        try:
            src.backup(dst)
            relay.require(dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'Backup integrity check failed.')
        finally:
            src.close(); dst.close()
        receipt = {'path': str(backup), 'sha': sha, 'created_at': relay.now()}
        relay.save(Path(os.environ['RELAY_RUN_DIR']) / f'backup-{stamp}.json', receipt)
        print(json.dumps(receipt))
    elif args.action == 'live-start':
        link_external(release / '.data', source / '.data')
        if (source / '.env').is_file(): link_external(release / '.env', source / '.env')
        env['IBKR_GATEWAY_URL'] = 'https://localhost:5001/v1/api'
        env['IBKR_CA_FILE'] = str(source / '.data/runtime/gateway/root/local-cert.pem')
        launch([sys.executable, str(Path(__file__).with_name('money_app.py')), str(release / 'app.py'), '--port', '8765'], release, env, 8765, sha, manifest, runtime / 'live.log')
    else:
        health(8765, release, sha, manifest)


if __name__ == '__main__':
    try:
        main()
    except (relay.RelayError, OSError, KeyError) as e:
        print(f'money runtime: {e}', file=sys.stderr)
        sys.exit(2)
