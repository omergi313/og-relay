import json
from pathlib import Path
import sys
from unittest import mock

from test_relay import PipelineTest
import relay


class RecoveryTest(PipelineTest):
    # Reuse helpers only, without collecting the parent test methods twice.
    def test_check_mutating_head_never_creates_passing_evidence(self):
        self.plan['check_command'] = [sys.executable, '-c',
            'import pathlib,subprocess; pathlib.Path("mutation").write_text("x"); subprocess.run(["git","add","mutation"],check=True); subprocess.run(["git","commit","-qm","mutation"],check=True)']
        relay.save(self.root / 'plans/toy/stages.json', self.plan)
        self.implement(); self.cli('check', 'toy', ok=False)
        relay.save(self.report, {'sha': relay.head(self.w), 'reviewer': 'reviewer', 'summary': 'Review', 'findings': []})
        self.cli('review', 'toy', '--report', self.report, ok=False)
        self.cli('smoke', 'toy', ok=False)

    def test_blocked_retry_after_independent_stage(self):
        self.plan['stages'].append({'n': 2, 'title': 'Independent', 'file': '01_code.md', 'depends_on': [], 'owns': ['other.txt']})
        relay.save(self.root / 'plans/toy/stages.json', self.plan)
        self.start(); self.cli('begin', 'toy', 1)
        (self.w / 'code.txt').write_text('partial'); self.git('add', 'code.txt', root=self.w)
        self.git('commit', '-qm', 'Plan 1 — Code [toy]', root=self.w)
        self.cli('block', 'toy', 1, '--reason', 'waiting')
        self.cli('begin', 'toy', 2)
        (self.w / 'other.txt').write_text('done'); self.git('add', 'other.txt', root=self.w)
        self.git('commit', '-qm', 'Plan 2 — Independent [toy]', root=self.w)
        self.cli('complete', 'toy', 2, '--report', self.report)
        self.cli('begin', 'toy', 1)
        (self.w / 'code.txt').write_text('done'); self.git('add', 'code.txt', root=self.w)
        self.git('commit', '-qm', 'Plan 1 — Code [toy]', root=self.w)
        self.cli('complete', 'toy', 1, '--report', self.report); self.cli('check', 'toy')

    def test_coordinator_ownership_revision(self):
        self.start(); self.cli('begin', 'toy', 1)
        self.plan['stages'][0]['owns'].append('extra.txt')
        relay.save(self.w / 'plans/toy/stages.json', self.plan)
        self.git('add', 'plans/toy/stages.json', root=self.w)
        self.git('commit', '-qm', 'Relay plan: toy', root=self.w)
        (self.w / 'extra.txt').write_text('x'); self.git('add', 'extra.txt', root=self.w)
        self.git('commit', '-qm', 'Plan 1 — Code [toy]', root=self.w)
        self.cli('complete', 'toy', 1, '--report', self.report)

    def test_initialization_recovers_after_worktree_creation(self):
        real_persist = relay.persist
        def fail_second(root, s):
            if s['phase'] == 'implementing':
                raise OSError('simulated crash')
            return real_persist(root, s)
        with mock.patch.object(relay, 'persist', side_effect=fail_second):
            self.cli('start', 'toy', '--approved', ok=False)
        self.assertEqual(self.state()['phase'], 'initializing')
        self.cli('status', 'toy'); self.assertEqual(self.state()['phase'], 'implementing')

    def test_initialization_recovers_before_worktree_creation(self):
        real_git = relay.git
        def fail_add(root, *args):
            if args[:2] == ('worktree', 'add'):
                raise OSError('simulated crash')
            return real_git(root, *args)
        with mock.patch.object(relay, 'git', side_effect=fail_add):
            self.cli('start', 'toy', '--approved', ok=False)
        self.cli('status', 'toy'); self.assertEqual(self.state()['phase'], 'implementing')


# unittest's inheritance discovers base methods too; remove them from this subclass's test view.
def load_tests(loader, tests, pattern):
    import unittest
    suite = unittest.TestSuite()
    for name in RecoveryTest.__dict__:
        if name.startswith('test_'):
            suite.addTest(RecoveryTest(name))
    return suite
