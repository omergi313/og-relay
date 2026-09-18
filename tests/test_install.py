import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallTest(unittest.TestCase):
    def test_install_preserves_other_settings_and_backs_up(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            settings = home / '.claude/settings.json'; settings.parent.mkdir()
            original = {'theme': 'dark', 'hooks': {'Stop': [{'hooks': [{'type': 'command', 'command': 'keep-me'}]}]}}
            settings.write_text(json.dumps(original))
            old = home / '.claude/skills/ship-feature/SKILL.md'; old.parent.mkdir(parents=True); old.write_text('old')
            script = ROOT / 'scripts/install.py'
            for _ in range(2):
                subprocess.run([sys.executable, str(script), '--home', d], check=True, capture_output=True)
            x = json.loads(settings.read_text())
            self.assertEqual(x['theme'], 'dark'); self.assertEqual(x['hooks']['Stop'], original['hooks']['Stop'])
            self.assertEqual(len(x['hooks']['TaskCompleted']), 1)
            self.assertTrue(list((home / '.local/share/og-relay/backups').glob('*/.claude/skills/ship-feature/SKILL.md')))
            for skill in ('relay-plan', 'relay-split', 'relay-ship'):
                body = (home / '.agents/skills' / skill / 'SKILL.md').read_text()
                self.assertNotIn('@RELAY_ROOT@', body)
                self.assertIn(str(ROOT), body)
            self.assertTrue((home / '.local/bin/og-relay').stat().st_mode & 0o111)

    def test_leaf_symlink_replaced_without_modifying_target(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / 'home'; home.mkdir()
            original = Path(d) / 'shared.md'; original.write_text('shared original')
            target = home / '.agents/skills/relay-ship/SKILL.md'; target.parent.mkdir(parents=True)
            target.symlink_to(original)
            subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'), '--home', str(home), '--host', 'codex'], check=True, capture_output=True)
            self.assertEqual(original.read_text(), 'shared original')
            self.assertFalse(target.is_symlink())
            backup = next((home / '.local/share/og-relay/backups').glob('*/.agents/skills/relay-ship/SKILL.md'))
            self.assertTrue(backup.is_symlink())

    def test_symlink_parent_refused(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d) / 'home'; home.mkdir()
            external = Path(d) / 'external'; external.mkdir()
            (home / '.agents').symlink_to(external, target_is_directory=True)
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'), '--home', str(home), '--host', 'codex'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(list(external.iterdir()))


if __name__ == '__main__':
    unittest.main()
