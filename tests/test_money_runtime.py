import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('money_runtime', ROOT / 'scripts/money_runtime.py')
money = importlib.util.module_from_spec(spec); spec.loader.exec_module(money)


class MoneyRuntimeTest(unittest.TestCase):
    def test_stop_refuses_unrecognized_process(self):
        with mock.patch.object(money, 'listeners', return_value={123}), mock.patch.object(money, 'cwd_of', return_value=Path('/unrelated')):
            with mock.patch.object(money.subprocess, 'run', return_value=mock.Mock(stdout='python app.py')):
                with mock.patch.object(money.os, 'kill') as kill:
                    with self.assertRaises(money.relay.RelayError):
                        money.stop(8765, {Path('/approved')})
                    kill.assert_not_called()

    def test_live_data_link_refuses_existing_directory(self):
        with tempfile.TemporaryDirectory() as d:
            target, source = Path(d) / 'target', Path(d) / 'source'
            target.mkdir(); source.mkdir()
            with self.assertRaises(money.relay.RelayError):
                money.link_external(target, source)
            target.rmdir(); money.link_external(target, source)
            self.assertEqual(target.resolve(), source.resolve())
            money.link_external(target, source)

    def test_backup_preserves_data_and_records_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); source = root / 'source'; source.mkdir()
            data = source / '.data'; data.mkdir()
            db = sqlite3.connect(data / 'portfolio.sqlite3')
            db.execute('CREATE TABLE example(value TEXT)'); db.execute("INSERT INTO example VALUES ('saved')"); db.commit(); db.close()
            work = root / 'feature'; work.mkdir(); release = root / 'release'; release.mkdir(); evidence = root / 'evidence'; evidence.mkdir()
            env = {'RELAY_SOURCE_DIR': str(source), 'RELAY_WORKTREE': str(work), 'RELAY_RELEASE_DIR': str(release), 'RELAY_RUN_DIR': str(evidence), 'RELAY_SHA': 'a' * 40}
            with mock.patch.dict(os.environ, env), mock.patch.object(sys, 'argv', ['runtime', 'live-backup']):
                with mock.patch.object(money.relay, 'common', return_value=root / 'common'), mock.patch.object(money.relay, 'head', return_value='a' * 40), mock.patch.object(money.relay, 'git', return_value=''), mock.patch.object(money, 'listeners', return_value=set()):
                    with contextlib.redirect_stdout(io.StringIO()): money.main()
            receipt = json.loads(next(evidence.glob('backup-*.json')).read_text())
            backup = Path(receipt['path'])
            connection = sqlite3.connect(backup)
            self.assertEqual(connection.execute('SELECT value FROM example').fetchone()[0], 'saved'); connection.close()
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
            self.assertTrue((data / 'portfolio.sqlite3').exists())

    def test_health_rejects_wrong_running_version(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); manifest = p / 'manifest.json'
            manifest.write_text(json.dumps({'sha': 'old', 'cwd': d, 'pid': 123}))
            with mock.patch.object(money.urllib.request, 'urlopen') as request:
                with self.assertRaises(money.relay.RelayError):
                    money.health(8765, p, 'new', manifest)
                request.assert_not_called()

    def test_legacy_server_with_children_is_not_killed(self):
        with mock.patch.object(money, 'listeners', return_value={123}), mock.patch.object(money, 'cwd_of', return_value=Path('/approved')):
            with mock.patch.object(money.subprocess, 'run', return_value=mock.Mock(stdout='python app.py')):
                with mock.patch.object(money, 'process_table', return_value={123: (1, 'S'), 124: (123, 'S')}), mock.patch.object(money.os, 'kill') as kill:
                    with self.assertRaises(money.relay.RelayError): money.stop(8765, {Path('/approved')})
                    kill.assert_not_called()

    def test_graceful_wrapper_runs_finally_on_termination(self):
        import subprocess
        import time
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); script = p / 'app.py'; ready = p / 'ready'; closed = p / 'closed'
            script.write_text('import time,pathlib\ntry:\n pathlib.Path(' + repr(str(ready)) + ').touch()\n while True: time.sleep(.05)\nfinally:\n pathlib.Path(' + repr(str(closed)) + ').touch()\n')
            process = subprocess.Popen([sys.executable, str(ROOT / 'scripts/money_app.py'), str(script)])
            try:
                deadline = time.monotonic() + 3
                while not ready.exists() and time.monotonic() < deadline: time.sleep(.01)
                self.assertTrue(ready.exists())
                process.terminate(); process.wait(timeout=3)
                self.assertTrue(closed.exists())
            finally:
                if process.poll() is None: process.kill(); process.wait()


if __name__ == '__main__':
    unittest.main()
