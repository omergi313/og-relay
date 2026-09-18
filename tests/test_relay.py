import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import relay


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'project'
        self.root.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Test')
        (self.root / 'code.txt').write_text('before')
        self.git('add', 'code.txt'); self.git('commit', '-qm', 'Initial')
        p = self.root / 'plans' / 'toy'; p.mkdir(parents=True)
        for name in ('SOURCE.md', 'README.md', 'PROMPTS.md', 'LOG.md', '01_code.md'):
            (p / name).write_text('# Test\n')
        self.plan = {'version': 1, 'slug': 'toy', 'test_command': [sys.executable, '-c', 'print("pass")'],
                     'check_command': [sys.executable, '-c', 'print("check")'], 'stages': [
                         {'n': 1, 'title': 'Code', 'file': '01_code.md', 'depends_on': [], 'owns': ['code.txt'], 'actions': []}]}
        relay.save(p / 'stages.json', self.plan)
        ok = [sys.executable, '-c', 'print("ok")']
        relay.save(relay.common(self.root) / 'config.json', {'version': 1, 'max_parallel': 1,
                   'smoke': {'restart': ok, 'health': ok},
                   'live': {k: ok for k in ('isolation_check', 'stop', 'backup', 'start', 'health')}})
        self.report = Path(self.temp.name) / 'report.json'
        relay.save(self.report, {'deviations': 'none', 'decisions': 'none', 'issues': 'none'})

    def git(self, *args, root=None):
        return relay.git(root or self.root, *args)

    def cli(self, *args, ok=True):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            result = relay.main(['--repo', str(self.root), *map(str, args)])
        self.assertEqual(result, 0 if ok else 2, err.getvalue() + out.getvalue())
        return out.getvalue() + err.getvalue()

    def state(self):
        return relay.state(self.root, 'toy')

    def start(self):
        self.cli('start', 'toy', '--approved')
        self.w = Path(self.state()['worktree'])

    def implement(self):
        self.start(); self.cli('begin', 'toy', '1')
        (self.w / 'code.txt').write_text('after')
        self.git('add', 'code.txt', root=self.w)
        self.git('commit', '-qm', 'Plan 1 — Code [toy]', root=self.w)
        self.cli('complete', 'toy', 1, '--report', self.report)

    def verified(self):
        self.implement(); self.cli('check', 'toy')
        review = Path(self.temp.name) / 'review.json'
        relay.save(review, {'sha': relay.head(self.w), 'reviewer': 'independent', 'summary': 'Reviewed', 'findings': []})
        self.cli('review', 'toy', '--report', review)
        self.cli('smoke', 'toy'); self.cli('accept', 'toy', '--confirmed', '--evidence', 'UI checked')

    def test_complete_lifecycle_and_isolation(self):
        self.verified(); self.cli('ready', 'toy')
        self.assertNotEqual(self.w, self.root)
        self.assertEqual((self.root / 'code.txt').read_text(), 'before')
        self.cli('finish', 'toy', '--confirmed')
        self.assertEqual(self.state()['phase'], 'merged')
        self.cli('deploy', 'toy', '--confirmed'); self.cli('close', 'toy')
        self.assertEqual(self.state()['phase'], 'released')
        release = Path(self.state()['release_dir'])
        (self.w / 'code.txt').write_text('new edit')
        self.assertEqual((release / 'code.txt').read_text(), 'after')
        self.assertEqual(self.git('branch', '--show-current', root=release), '')

    def test_missing_report_fields_refused(self):
        self.start(); self.cli('begin', 'toy', 1)
        relay.save(self.report, {'status': 'done'})
        self.cli('complete', 'toy', 1, '--report', self.report, ok=False)

    def test_forged_commit_or_test_evidence_refused_on_resume(self):
        self.implement()
        s = self.state(); s['stages']['1']['commit'] = 'a' * 40; relay.persist(self.root, s)
        self.cli('status', 'toy', ok=False)
        self.cli('validate-stage', 'toy', 1, ok=False)

    def test_modified_test_log_refused(self):
        self.implement(); s = self.state()
        Path(s['stages']['1']['test']['log']).write_text('altered')
        self.cli('validate-stage', 'toy', 1, ok=False)

    def test_owned_paths_enforced_even_after_revert(self):
        self.start(); self.cli('begin', 'toy', 1)
        (self.w / 'wrong.txt').write_text('x'); self.git('add', 'wrong.txt', root=self.w)
        self.git('commit', '-qm', 'Plan 1 — Code [toy]', root=self.w)
        (self.w / 'wrong.txt').unlink(); self.git('add', 'wrong.txt', root=self.w)
        self.git('commit', '-qm', 'Plan 1 — Code [toy]', root=self.w)
        self.cli('complete', 'toy', 1, '--report', self.report, ok=False)

    def test_stale_verification_blocks_manual_fix(self):
        self.verified()
        (self.w / 'code.txt').write_text('manual fix'); self.git('add', 'code.txt', root=self.w)
        self.git('commit', '-qm', 'Manual fix', root=self.w)
        self.cli('ready', 'toy', ok=False); self.cli('smoke', 'toy', ok=False)
        self.cli('finish', 'toy', '--confirmed', ok=False)

    def test_incomplete_run_cannot_finish(self):
        self.start(); self.cli('finish', 'toy', '--confirmed', ok=False)

    def test_review_blockers_prevent_smoke(self):
        self.implement(); self.cli('check', 'toy')
        relay.save(self.report, {'sha': relay.head(self.w), 'reviewer': 'reviewer', 'summary': 'bad',
                                'findings': [{'severity': 'major', 'status': 'open', 'description': 'bug'}]})
        self.cli('review', 'toy', '--report', self.report, ok=False); self.cli('smoke', 'toy', ok=False)

    def test_prerequisite_action_blocks_dependents(self):
        self.plan['stages'][0]['actions'] = [{'id': 'access', 'phase': 'prerequisite', 'description': 'Enable access'}]
        self.plan['stages'].append({'n': 2, 'title': 'Next', 'file': '01_code.md', 'depends_on': [1], 'owns': ['next.txt']})
        relay.save(self.root / 'plans/toy/stages.json', self.plan)
        self.implement(); self.cli('begin', 'toy', 2, ok=False)
        self.cli('resolve', 'toy', 'access', '--confirmed', '--evidence', 'Access enabled')
        self.cli('begin', 'toy', 2)

    def test_serial_stage_guard(self):
        self.start(); self.cli('begin', 'toy', 1); self.cli('begin', 'toy', 1, ok=False)

    def test_cycle_rejected(self):
        self.plan['stages'][0]['depends_on'] = [2]
        self.plan['stages'].append({'n': 2, 'title': 'Other', 'file': '01_code.md', 'depends_on': [1], 'owns': ['next.txt']})
        relay.save(self.root / 'plans/toy/stages.json', self.plan)
        self.cli('validate-plan', 'toy', ok=False)

    def test_base_moved_needs_reconcile_and_new_checks(self):
        self.verified()
        (self.root / 'base.txt').write_text('base'); self.git('add', 'base.txt'); self.git('commit', '-qm', 'Base change')
        self.cli('ready', 'toy', ok=False); self.cli('reconcile', 'toy')
        self.cli('ready', 'toy', ok=False); self.cli('check', 'toy')

    def test_deployment_failure_keeps_merge_and_can_resume(self):
        self.verified(); self.cli('finish', 'toy', '--confirmed')
        s = self.state(); s['config']['live']['health'] = [sys.executable, '-c', 'raise SystemExit(1)']; relay.persist(self.root, s)
        self.cli('deploy', 'toy', '--confirmed', ok=False)
        self.assertEqual(self.state()['phase'], 'deployment_failed')
        self.assertTrue(self.state()['merge_sha']); self.assertTrue(self.state()['events'])
        s = self.state(); s['config']['live']['health'] = [sys.executable, '-c', 'print("healthy")']; relay.persist(self.root, s)
        self.cli('deploy', 'toy', '--confirmed'); self.cli('close', 'toy')

    def test_merge_crash_recovery(self):
        self.verified(); s = self.state()
        s.update(phase='merging', candidate_sha=relay.head(self.w)); relay.persist(self.root, s)
        self.git('merge', '--no-ff', s['branch'], '-m', 'Feature: toy')
        self.cli('status', 'toy'); self.assertEqual(self.state()['phase'], 'merged')

    def test_post_release_action_required_for_close(self):
        self.plan['stages'][0]['actions'] = [{'id': 'live-test', 'phase': 'post_release', 'description': 'Test live'}]
        relay.save(self.root / 'plans/toy/stages.json', self.plan)
        self.verified(); self.cli('finish', 'toy', '--confirmed'); self.cli('deploy', 'toy', '--confirmed')
        self.cli('close', 'toy', ok=False)
        self.cli('resolve', 'toy', 'live-test', '--confirmed', '--evidence', 'Works on live')
        self.cli('close', 'toy')

    def test_release_action_is_bound_to_candidate(self):
        self.plan['stages'][0]['actions'] = [{'id': 'approval', 'phase': 'release', 'description': 'Approval'}]
        relay.save(self.root / 'plans/toy/stages.json', self.plan)
        self.verified(); self.cli('ready', 'toy', ok=False)
        self.cli('resolve', 'toy', 'approval', '--confirmed', '--evidence', 'Approved candidate')
        self.cli('ready', 'toy')

    def test_live_on_source_blocks_merge(self):
        self.verified()
        s = self.state(); s['config']['live']['isolation_check'] = [sys.executable, '-c', 'raise SystemExit(1)']; relay.persist(self.root, s)
        self.cli('finish', 'toy', '--confirmed', ok=False)
        self.assertNotIn('merge_sha', self.state())

    def test_unrelated_task_hook_passes(self):
        hook = Path(__file__).resolve().parents[1] / 'scripts/stage_gate.py'
        p = subprocess.run([sys.executable, str(hook)], input=json.dumps({'task_subject': 'Other task'}), text=True, capture_output=True)
        self.assertEqual(p.returncode, 0)

    def test_gate_hook_uses_same_validator(self):
        self.implement()
        hook = Path(__file__).resolve().parents[1] / 'scripts/stage_gate.py'
        payload = json.dumps({'task_subject': 'Plan 1 — Code [toy]', 'cwd': str(self.w)})
        p = subprocess.run([sys.executable, str(hook)], input=payload, text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        s = self.state(); del s['stages']['1']['test']; relay.persist(self.root, s)
        p = subprocess.run([sys.executable, str(hook)], input=payload, text=True, capture_output=True)
        self.assertEqual(p.returncode, 2)


if __name__ == '__main__':
    unittest.main()
