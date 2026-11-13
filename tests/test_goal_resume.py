from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import goal_resume as resume
fcntl = resume.fcntl


@unittest.skipIf(os.name == 'nt', 'POSIX lock and permission contract')
class GoalResumeTests(unittest.TestCase):
    @contextmanager
    def fixture(self, status='active'):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            root.chmod(0o700)
            repo = root / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', '--initial-branch=continuation-test', str(repo)],
                           check=True)
            binary = root / 'fake-codex'
            binary.write_text('#!/bin/sh\nexit 0\n')
            binary.chmod(0o700)
            goaldb = root / 'goals.sqlite'
            with sqlite3.connect(goaldb) as db:
                db.execute('CREATE TABLE thread_goals (thread_id TEXT, goal_id TEXT, status TEXT)')
                db.execute('INSERT INTO thread_goals VALUES (?,?,?)', ('test-thread', 'test-goal', status))
            statedb = root / 'state.sqlite'
            with sqlite3.connect(statedb) as db:
                db.execute('CREATE TABLE threads (id TEXT, archived INTEGER)')
                db.execute('INSERT INTO threads VALUES (?,0)', ('test-thread',))
            checkpoint = root / 'checkpoint.json'
            checkpoint.write_text(json.dumps({'thread_id': 'test-thread', 'goal_id': 'test-goal'}))
            checkpoint.chmod(0o600)
            config = {'version': 1, 'thread_id': 'test-thread', 'goal_id': 'test-goal',
                      'repository': str(repo), 'branch': 'continuation-test', 'codex': str(binary),
                      'codex_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                      'goals_database': str(goaldb), 'state_database': str(statedb),
                      'checkpoint': str(checkpoint), 'armed_boot': 'installation-boot',
                      'prompt': 'Resume the saved source-only investigation.'}
            path = root / 'config.json'
            path.write_text(json.dumps(config))
            path.chmod(0o600)
            yield root, path, config

    def run_fake(self, path, boot='next-boot', code=0, calls=None, **kwargs):
        def execute(command, **options):
            if calls is not None:
                calls.append((command, options))
            return subprocess.CompletedProcess(command, code)
        return resume.run_once(path, boot=boot, runner=execute, **kwargs)

    def test_new_boot_resumes_exact_thread_without_permission_or_model_overrides(self):
        with self.fixture() as (root, path, config):
            calls = []
            result = self.run_fake(path, calls=calls)
            self.assertEqual(0, result['returncode'])
            command, options = calls[0]
            self.assertEqual([config['codex'], 'exec', '--cd', config['repository'],
                              'resume', config['thread_id'], config['prompt']], command)
            self.assertEqual(config['repository'], options['cwd'])
            self.assertEqual(subprocess.DEVNULL, options['stdin'])
            for file in (root / 'attempts').iterdir():
                self.assertEqual(0o600, file.stat().st_mode & 0o777)

    def test_installation_boot_is_deferred_without_starting_another_agent(self):
        with self.fixture() as (_, path, _):
            calls = []
            result = self.run_fake(path, boot='installation-boot', calls=calls)
            self.assertEqual('armed-for-next-boot', result['status'])
            self.assertEqual([], calls)

    def test_explicit_resume_now_still_claims_only_once(self):
        with self.fixture() as (_, path, _):
            calls = []
            self.run_fake(path, boot='installation-boot', allow_current_boot=True, calls=calls)
            result = self.run_fake(path, boot='installation-boot', allow_current_boot=True, calls=calls)
            self.assertEqual('boot-already-claimed', result['status'])
            self.assertEqual(1, len(calls))

    def test_completed_attempt_is_not_replayed_on_relogin(self):
        with self.fixture() as (_, path, _):
            calls = []
            self.run_fake(path, calls=calls)
            self.assertEqual('boot-already-claimed', self.run_fake(path, calls=calls)['status'])
            self.assertEqual(1, len(calls))

    def test_nonzero_exit_keeps_claim_and_error_receipt(self):
        with self.fixture() as (root, path, _):
            self.assertEqual(7, self.run_fake(path, code=7)['returncode'])
            self.assertEqual(7, json.loads((root / 'last-result.json').read_text())['returncode'])
            self.assertEqual('boot-already-claimed', self.run_fake(path)['status'])

    def test_launch_exception_does_not_allow_an_automatic_retry(self):
        with self.fixture() as (root, path, _):
            def fail(*args, **kwargs):
                raise OSError('fake launch failure')
            with self.assertRaises(OSError):
                resume.run_once(path, boot='next-boot', runner=fail)
            self.assertEqual('launch-interrupted-or-failed',
                             json.loads((root / 'last-result.json').read_text())['status'])
            self.assertEqual('boot-already-claimed', self.run_fake(path)['status'])

    def test_active_process_lock_prevents_a_second_launch(self):
        with self.fixture() as (root, path, _):
            with (root / 'resume.lock').open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual('already-running', self.run_fake(path)['status'])

    def test_inactive_goal_is_never_reactivated(self):
        for status in ['paused', 'blocked', 'complete', 'budget_limited', 'usage_limited']:
            with self.subTest(status=status), self.fixture(status) as (_, path, _):
                self.assertEqual('goal-inactive', self.run_fake(path)['status'])

    def test_disabled_marker_prevents_resume(self):
        with self.fixture() as (root, path, _):
            (root / 'disabled').touch()
            self.assertEqual('disabled', self.run_fake(path)['status'])

    def test_goal_identity_replacement_refuses(self):
        with self.fixture() as (_, path, config):
            with sqlite3.connect(config['goals_database']) as db:
                db.execute("UPDATE thread_goals SET goal_id='different'")
            with self.assertRaisesRegex(resume.ResumeError, 'goal-identity'):
                self.run_fake(path)

    def test_archived_session_refuses(self):
        with self.fixture() as (_, path, config):
            with sqlite3.connect(config['state_database']) as db:
                db.execute('UPDATE threads SET archived=1')
            with self.assertRaisesRegex(resume.ResumeError, 'thread-unavailable'):
                self.run_fake(path)

    def test_checkpoint_mismatch_refuses(self):
        with self.fixture() as (_, path, config):
            for value in ['{}', '[]']:
                Path(config['checkpoint']).write_text(value)
                with self.assertRaisesRegex(resume.ResumeError, 'checkpoint-identity'):
                    self.run_fake(path)

    def test_real_subprocess_transport_runs_only_the_fixture_executable(self):
        with self.fixture() as (root, path, _):
            result = resume.run_once(path, boot='next-boot')
            self.assertEqual(0, result['returncode'])
            self.assertEqual('exited', json.loads((root / 'last-result.json').read_text())['status'])

    def test_changed_binary_refuses(self):
        with self.fixture() as (_, path, config):
            Path(config['codex']).write_text('changed binary')
            with self.assertRaisesRegex(resume.ResumeError, 'executable-pin'):
                self.run_fake(path)

    def test_changed_branch_refuses_without_touching_repository(self):
        with self.fixture() as (_, path, config):
            subprocess.run(['git', '-C', config['repository'], 'symbolic-ref',
                            'HEAD', 'refs/heads/other-branch'], check=True)
            with self.assertRaisesRegex(resume.ResumeError, 'repository'):
                self.run_fake(path)

    def test_private_config_and_symlink_constraints(self):
        with self.fixture() as (root, path, _):
            path.chmod(0o644)
            with self.assertRaisesRegex(resume.ResumeError, 'file-permissions'):
                self.run_fake(path)
            path.chmod(0o600)
            link = root / 'linked-config'
            link.symlink_to(path)
            with self.assertRaisesRegex(resume.ResumeError, 'path'):
                self.run_fake(link)

    def test_check_mode_creates_no_claim_or_child(self):
        with self.fixture() as (root, path, _):
            calls = []
            self.assertEqual('ready', self.run_fake(path, check=True, calls=calls)['status'])
            self.assertEqual([], calls)
            self.assertEqual([], list((root / 'attempts').iterdir()))


if __name__ == '__main__':
    unittest.main()
