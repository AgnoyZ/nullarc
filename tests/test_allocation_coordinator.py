"""Real coordinator/observer/recovery processes; synthetic I/O and file-only commands."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import signal
import tempfile
import time
import unittest
from unittest import mock
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import allocation_capture as capture
import allocation_observer as observer
import allocation_startup as startup
from test_allocation_capture import BOOT, IMAGE, empty, add


@unittest.skipUnless(os.name == 'posix' and hasattr(os, 'fork'), 'POSIX process contracts')
class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        # Commands deliberately reject world-writable ancestors, including /tmp.
        parent = ROOT / 'build'
        parent.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='coordinator-fixture-', dir=parent)
        self.work = Path(self.temp.name).resolve()
        self.addCleanup(self.temp.cleanup)
        self.scope = self.work / 'scope'; self.scope.mkdir(mode=0o700)
        self.root = self.scope / 'run'
        self.reports = self.work / 'reports'; self.reports.mkdir(mode=0o700)
        self.events = self.work / 'events'
        self.shell = str(Path('/bin/sh').resolve())
        self.reader = self.work / 'fake-reader'
        self.reader.write_text('#!/bin/sh\nexit 99\n'); self.reader.chmod(0o700)
        self.spec = {'reader': str(self.reader),
                     'reader_sha256': hashlib.sha256(self.reader.read_bytes()).hexdigest(),
                     'expected_build': 37, 'expected_image_uuid': IMAGE}
        self.identity = {'boot_uuid': BOOT, 'os_build': '25A362', 'service_entry_id': 123,
                         'kext_build': 37, 'loaded_image_uuid': IMAGE}
        self.mode = None
        self.stage_commands = {role: self.command(role) for role in startup.ROLES}
        self.recovery_commands = {role: self.command('recover-' + role)
                                  for role in startup.RECOVERY_ROLES}
        self.host = mock.patch.object(capture, 'host_check')
        self.host.start(); self.addCleanup(self.host.stop)
        self.addCleanup(self.clean_workers)

    def command(self, name, extra='', status=0):
        script = self.work / (name + '.sh')
        text = 'printf "%s\\n" ' + shlex.quote(name) + ' >> ' + shlex.quote(str(self.events)) + '\n'
        # Fixture-only PIDs permit exact cleanup of a deliberately blocked helper.
        text += 'printf "%s\\n" "$$" > ' + shlex.quote(str(self.work / (name + '.pid'))) + '\n'
        if name == 'release': text += ': > ' + shlex.quote(str(self.work / 'released')) + '\n'
        if name == 'monitor': text += ': > ' + shlex.quote(str(self.work / 'panel-open')) + '\n'
        script.write_text(text + extra + '\nexit ' + str(status) + '\n'); script.chmod(0o600)
        pins = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
                for name in (self.shell, str(script))}
        return startup.Command([self.shell, str(script)], pins)

    def boundary(self):
        return {'framebuffer_id': 17, 'held': not (self.work / 'released').exists(),
                'panel_open': (self.work / 'panel-open').exists()}

    def baseline(self, out, *_args):
        out.mkdir(mode=0o700)
        value = {'format': 1, 'phase': 'baseline', 'saved_at': '2026-11-14T00:00:00+00:00',
                 'identity': copy.deepcopy(self.identity), 'spec': copy.deepcopy(self.spec),
                 'snapshot': empty()}
        if self.mode == 'bool-format': value['format'] = True
        if self.mode == 'bool-service': value['identity']['service_entry_id'] = True
        if self.mode == 'bool-build': value['spec']['expected_build'] = True
        if self.mode == 'bad-schema': value['snapshot']['extra'] = 0
        if self.mode == 'exhausted':
            for _ in range(4): add(value['snapshot'])
        capture.write_json(out / 'baseline.json', value)

    def observer_job(self, out, ready):
        (self.work / 'fixture-observer.pid').write_text(str(os.getpid()))
        if self.mode == 'blocked': time.sleep(20)
        if self.mode == 'dead': return
        if self.mode == 'missing':
            ready({'observer_pid': os.getpid()})
            time.sleep(20)
        owner = self

        class Watch:
            def __init__(self, _path): self.scans = 0
            def scan(self):
                self.scans += 1
                if ((owner.mode == 'early-report' and self.scans == 2)
                        or (owner.mode in ('report-after-ready', 'failure-blocked') and self.scans >= 3)
                        or (owner.mode == 'report-after-release' and (owner.work / 'released').exists())):
                    return {'WindowServer-fixture.ips': (1, 2)}
                return {}
            def wait(self, seconds):
                if owner.mode in ('report-after-ready', 'failure-blocked', 'report-after-release'):
                    time.sleep(0.04); return True
                time.sleep(seconds); return False
            def close(self): pass

        def on_ready(value):
            if self.mode == 'missing-file': (out / 'baseline.json').unlink()
            if self.mode == 'changed':
                path = out / 'baseline.json'
                path.write_bytes(path.read_bytes() + b'\n')
            if self.mode == 'late': value['deadline_ns'] = time.monotonic_ns() - 1
            if self.mode == 'short-window': value['deadline_ns'] = time.monotonic_ns() + 100_000_000
            if self.mode == 'bad-pid': value['observer_pid'] += 1
            ready(value)
            if self.mode == 'dies-after-ready':
                time.sleep(0.04)
                os._exit(74)

        def failure(path):
            if self.mode == 'failure-blocked':
                capture.write_file(path / 'failure.started', b'fixture only\n')
                time.sleep(20)
            capture.write_json(path / 'failure.json', {'fixture': True})

        observer.observe(self.reports, out, Path(self.spec['reader']), self.spec['reader_sha256'], 37, IMAGE, 90,
                         watch_factory=Watch, baseline=self.baseline,
                         failure=failure, on_ready=on_ready)

    def run_attempt(self, **changes):
        args = dict(scope=self.scope, spec=self.spec, expected_identity=self.identity,
                    current_identity=lambda: copy.deepcopy(self.identity), boundary=self.boundary,
                    observer_job=self.observer_job, stages=self.stage_commands,
                    recovery_commands=self.recovery_commands, admission_seconds=1,
                    stage_seconds=1, watchdog_seconds=3)
        args.update(changes)
        return startup.supervise(**args)

    def wait_file(self, path, timeout=5):
        deadline = time.monotonic() + timeout
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(path.exists(), path.name)
        return path

    def names(self):
        return self.events.read_text().splitlines() if self.events.exists() else []

    def recovery_result(self):
        path = self.wait_file(self.root / 'recovery.json')
        value = json.loads(path.read_bytes())
        if value['outcome'] == 'recovery-requested':
            self.wait_file(self.work / 'recover-reboot.pid')
        return value

    def clean_workers(self):
        # Every PID comes from this test's actual coordinator or command fixture.
        own = set()
        journal = self.root / 'startup.jsonl'
        if journal.exists():
            for line in journal.read_text().splitlines():
                value = json.loads(line)
                if value['event'] == 'recovery-armed': own.add(value['data']['pid'])
                if value['event'] == 'admitted': own.add(value['data']['ready']['observer_pid'])
        for name in ('startup.json', 'startup-failure.json'):
            path = self.root / name
            if path.exists():
                value = json.loads(path.read_bytes())
                own.update(value.get(key) for key in ('recovery_pid', 'observer_pid') if value.get(key))
        # Allow independently requested recovery to dispatch before cleanup.
        deadline = time.monotonic() + 4
        while own and time.monotonic() < deadline:
            for pid in list(own):
                try:
                    done, _ = os.waitpid(pid, os.WNOHANG)
                    if done: own.remove(pid)
                except ChildProcessError:
                    own.remove(pid)
            if own: time.sleep(0.01)
        self.assertFalse(own, 'owned coordinator workers failed to exit')
        for path in self.work.glob('*.pid'):
            pid = int(path.read_text())
            try: os.kill(pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: os.waitpid(pid, 0)
            except ChildProcessError: pass  # Recovery's children were reparented.
        startup.reap_owned()

    def assert_refused(self, mode=None, expected=None, **changes):
        self.mode = mode
        with self.assertRaises((capture.CaptureError, OSError)) as caught:
            self.run_attempt(**changes)
        if expected and not isinstance(caught.exception, capture.CaptureError):
            raise caught.exception
        if expected: self.assertEqual(expected, str(caught.exception))
        self.assertTrue((self.scope / 'startup.started').exists())
        self.assertEqual('recovery-requested', self.recovery_result()['outcome'])
        return caught.exception

    def test_success_order_full_baseline_and_monotonic_hash_trail(self):
        result = self.run_attempt()
        self.assertFalse(result['hardware_or_desktop_validated'])
        self.assertEqual(list(startup.ROLES), self.names())
        self.assert_success(result)

    def test_stage_specific_deadline_allows_longer_monitor_without_changing_other_stages(self):
        self.stage_commands['monitor'] = self.command('monitor', 'sleep 0.15')
        timeouts = {role: 1 for role in startup.ROLES}
        timeouts['monitor'] = 0.5
        result = self.run_attempt(stage_seconds=0.05, stage_timeouts=timeouts)
        self.assert_success(result)

    def test_recovery_handoff_callback_runs_before_observer_admission(self):
        called = []
        def armed():
            called.append(True)
            self.assertFalse((self.root / 'capture/baseline.json').exists())
            self.assertTrue((self.scope / 'startup.started').exists())
        self.run_attempt(on_recovery_armed=armed)
        self.assertEqual([True], called)

    def test_failed_recovery_handoff_does_not_start_observer_or_stages(self):
        def refused(): raise capture.CaptureError('fixture-handoff-refused')
        self.assert_refused(expected='fixture-handoff-refused', on_recovery_armed=refused)
        self.assertFalse((self.root / 'capture').exists())
        self.assertFalse(any(role in self.names() for role in startup.ROLES))

    def test_metadata_recovery_can_be_bound_to_separate_claim_and_truthful_dismissal(self):
        alternate = self.scope / 'boot-entry.started'
        capture.write_json(alternate, {'metadata_pending': True})
        root = self.scope / 'metadata-recovery'; root.mkdir(mode=0o700)
        recovery = startup.Recovery(root, self.recovery_commands, 2, {'metadata_pending': True},
                                    claim_path=alternate, dismissal_outcome='handed-to-coordinator-recovery')
        try:
            recovery.arm(time.monotonic() + 1)
            recovery.dismiss(time.monotonic() + 1)
            result = json.loads((root / 'recovery.json').read_text())
            self.assertEqual('handed-to-coordinator-recovery', result['outcome'])
            self.assertEqual(hashlib.sha256(alternate.read_bytes()).hexdigest(), result['startup_claim_sha256'])
        finally:
            recovery.close()

    def test_actual_collector_observer_and_coordinator_with_fake_native_commands(self):
        import test_allocation_capture as fixture_module
        fixture = fixture_module.CaptureTests('test_full_sequence_is_two_single_reads_with_private_durable_outputs')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.spec.update(reader=str(fixture.reader), reader_sha256=fixture.digest)

        def real_baseline(out, reader, digest, build, image):
            capture.begin(out, reader, digest, build, image, run=fixture.run_fake)
        self.baseline = real_baseline
        result = self.run_attempt(admission_seconds=8, watchdog_seconds=10)
        self.assertEqual('reviewed-stages-returned', result['outcome'])
        capture_root = self.root / 'capture'
        self.assertEqual(9, len(list((capture_root / 'baseline').glob('*.status.json'))))
        self.assertTrue(all(json.loads(path.read_bytes())['returncode'] == 0
                            for path in (capture_root / 'baseline').glob('*.status.json')))
        self.assertFalse((capture_root / 'failure.started').exists())
        self.assert_success(result)

    def assert_success(self, result):
        recovery = self.recovery_result()
        self.assertEqual('dismissed-after-monitor', recovery['outcome'])
        self.assertEqual(self.identity, recovery['expected_identity'])
        self.assertEqual(result['recovery_pid'], recovery['recovery_pid'])
        self.assertEqual(hashlib.sha256((self.scope / 'startup.started').read_bytes()).hexdigest(),
                         recovery['startup_claim_sha256'])
        previous = '0' * 64
        last_ns = 0
        values = []
        for sequence, raw in enumerate((self.root / 'startup.jsonl').read_bytes().splitlines(keepends=True)):
            value = json.loads(raw); values.append(value)
            self.assertEqual(sequence, value['sequence'])
            self.assertEqual(previous, value['previous_sha256'])
            self.assertEqual(self.identity, value['identity'])
            self.assertGreaterEqual(value['monotonic_ns'], last_ns)
            last_ns = value['monotonic_ns']; previous = hashlib.sha256(raw).hexdigest()
        self.assertEqual(['recovery-armed', 'admitted'] +
                         ['stage-' + suffix for _ in startup.ROLES for suffix in ('request', 'returned')] +
                         ['monitor-completed'], [value['event'] for value in values])
        baseline = self.root / 'capture/baseline.json'
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(), result['baseline_sha256'])
        with self.assertRaises(FileExistsError): self.run_attempt()
        self.assertEqual(list(startup.ROLES), self.names())

    def test_observer_blocked_before_readiness_uses_actual_recovery(self):
        self.assert_refused('blocked', 'startup-not-ready', admission_seconds=0.15)
        self.assertNotIn('initialize', self.names())

    def test_dead_observer_cannot_admit(self):
        self.assert_refused('dead', 'startup-worker-ended')
        self.assertNotIn('initialize', self.names())

    def test_dead_observer_during_stage_prevents_claim_and_release(self):
        self.stage_commands['initialize'] = self.command('initialize', '/bin/sleep 0.3')
        self.assert_refused('dies-after-ready', 'startup-observer-ended')
        self.assertNotIn('claim', self.names()); self.assertNotIn('release', self.names())

    def test_missing_receipt_and_baseline_refused(self):
        self.assert_refused('missing')
        self.assertNotIn('initialize', self.names())

    def test_complete_receipt_with_missing_baseline_refused(self):
        self.assert_refused('missing-file')
        self.assertNotIn('initialize', self.names())

    def test_changed_baseline_refused(self):
        self.assert_refused('changed', 'startup-baseline-changed')
        self.assertNotIn('initialize', self.names())

    def test_late_baseline_refused(self):
        self.assert_refused('late', 'startup-late-baseline')
        self.assertNotIn('initialize', self.names())

    def test_deadline_crossing_during_stage_prevents_next_stage(self):
        self.stage_commands['initialize'] = self.command('initialize', '/bin/sleep 0.3')
        self.assert_refused('short-window', 'startup-late-baseline')
        self.assertNotIn('claim', self.names())

    def test_malformed_snapshot_refused(self):
        self.assert_refused('bad-schema', 'schema')
        self.assertNotIn('initialize', self.names())

    def test_boolean_format_refused(self):
        self.assert_refused('bool-format', 'schema')

    def test_boolean_service_identity_refused(self):
        self.assert_refused('bool-service', 'schema')

    def test_boolean_spec_build_refused(self):
        self.assert_refused('bool-build', 'schema')

    def test_first_four_exhaustion_refused(self):
        self.assert_refused('exhausted', 'startup-detail-capacity')

    def test_early_report_never_issues_readiness(self):
        self.assert_refused('early-report', 'startup-worker-ended')
        self.assertTrue((self.root / 'capture/observer.trigger.json').exists())
        self.assertNotIn('initialize', self.names())

    def test_receipt_wrong_worker_refused(self):
        self.assert_refused('bad-pid', 'startup-worker-identity')

    def test_report_after_ready_refuses_next_stage(self):
        self.stage_commands['initialize'] = self.command('initialize', '/bin/sleep 0.3')
        self.assert_refused('report-after-ready', 'startup-observer-ended')
        self.assertNotIn('claim', self.names())

    def test_first_report_after_release_leaves_crash_thresholds_to_monitor(self):
        self.mode = 'report-after-release'
        self.stage_commands['monitor'] = self.command('monitor', '/bin/sleep 0.2')
        result = self.run_attempt()
        self.assert_success(result)
        self.assertEqual(list(startup.ROLES), self.names())
        self.assertEqual('captured', json.loads((self.root / 'capture/observer.json').read_bytes())['outcome'])

    def test_blocked_failure_collection_never_gates_recovery(self):
        self.stage_commands['initialize'] = self.command('initialize', '/bin/sleep 0.3')
        self.assert_refused('failure-blocked', 'startup-observer-ended')
        self.assertTrue((self.root / 'capture/failure.started').exists())
        self.assertFalse((self.root / 'capture/failure.json').exists())
        self.assertNotIn('claim', self.names())

    def test_baseline_changed_after_initialization_refuses_claim(self):
        self.stage_commands['initialize'] = self.command(
            'initialize', 'printf "changed" >> ' + shlex.quote(str(self.root / 'capture/baseline.json')))
        self.assert_refused(expected='startup-baseline-changed')
        self.assertNotIn('claim', self.names())

    def test_identity_changed_after_initialization_refuses_claim(self):
        changed = dict(self.identity); changed['service_entry_id'] = 456
        self.assert_refused(expected='startup-identity',
                            current_identity=lambda: changed if 'initialize' in self.names() else self.identity)
        self.assertNotIn('claim', self.names())

    def test_live_callback_cannot_mutate_the_admitted_expected_identity(self):
        def current():
            if 'initialize' in self.names(): self.identity['service_entry_id'] = 456
            return self.identity
        self.assert_refused(expected='startup-identity', current_identity=current)
        self.assertNotIn('claim', self.names())

    def test_live_identity_change_refused(self):
        for field, changed in (('boot_uuid', IMAGE), ('service_entry_id', 456),
                               ('loaded_image_uuid', BOOT), ('kext_build', 36)):
            value = dict(self.identity); value[field] = changed
            with self.subTest(field=field), self.assertRaises(capture.CaptureError):
                startup.identity_matches(lambda: value, self.identity, self.spec)
        changed = dict(self.identity); changed['service_entry_id'] = 456
        self.assert_refused(current_identity=lambda: changed, expected='startup-identity')
        self.assertNotIn('initialize', self.names())

    def test_hold_expiry_before_admission_refused(self):
        self.assert_refused(boundary=lambda: {'framebuffer_id': 17, 'held': False, 'panel_open': False},
                            expected='startup-panel-boundary')

    def test_reused_mutable_boundary_cannot_hide_hold_expiry(self):
        state = {'framebuffer_id': 17, 'held': True, 'panel_open': False}
        def current():
            if 'initialize' in self.names(): state['held'] = False
            return state
        self.assert_refused(boundary=current, expected='startup-panel-boundary')
        self.assertNotIn('claim', self.names())

    def test_failed_initialization_skips_claim_display_and_release(self):
        self.stage_commands['initialize'] = self.command('initialize', status=74)
        self.assert_refused(expected='startup-stage-failed')
        self.assertNotIn('claim', self.names()); self.assertNotIn('release', self.names())

    def test_failed_claim_skips_display_and_release(self):
        self.stage_commands['claim'] = self.command('claim', status=75)
        self.assert_refused(expected='startup-stage-failed')
        self.assertNotIn('display', self.names()); self.assertNotIn('release', self.names())

    def test_failed_monitor_does_not_dismiss_recovery(self):
        self.stage_commands['monitor'] = self.command('monitor', status=74)
        self.assert_refused(expected='startup-stage-failed')
        self.assertFalse((self.root / 'startup.json').exists())

    def test_release_without_released_boundary_refuses_monitor(self):
        self.stage_commands['release'] = self.command(
            'release', '/bin/rm ' + shlex.quote(str(self.work / 'released')))
        self.assert_refused(expected='startup-panel-boundary')
        self.assertNotIn('monitor', self.names())

    def test_blocked_initialization_skips_later_stages(self):
        self.stage_commands['initialize'] = self.command('initialize', '/bin/sleep 10')
        self.assert_refused(stage_seconds=0.15, expected='startup-stage-timeout')
        self.assertNotIn('claim', self.names())

    def test_blocked_claim_skips_display_and_release(self):
        self.stage_commands['claim'] = self.command('claim', '/bin/sleep 10')
        self.assert_refused(stage_seconds=0.15, expected='startup-stage-timeout')
        self.assertNotIn('display', self.names()); self.assertNotIn('release', self.names())

    def test_stage_output_is_bounded_and_failure_does_not_release(self):
        self.stage_commands['initialize'] = self.command('initialize', 'while :; do printf "%01024d" 0; done')
        self.assert_refused(expected='startup-output-limit')
        self.assertLessEqual((self.root / 'initialize.stdout').stat().st_size, capture.LIMIT)
        self.assertNotIn('claim', self.names())

    def test_group_signal_error_never_skips_observer_cleanup(self):
        self.stage_commands['initialize'] = self.command('initialize', '/bin/sleep 0.3')
        with mock.patch.object(startup.os, 'killpg', side_effect=PermissionError(1, 'fixture')):
            self.assert_refused(stage_seconds=0.1, expected='startup-stage-timeout')
        value = json.loads((self.root / 'cleanup.json').read_bytes())
        self.assertTrue(any(item['group'] and item['signal_errno'] == 1 for item in value['signal_attempts']))
        self.assertTrue(any(not item['group'] and item['signal_errno'] == 0 for item in value['signal_attempts']))
        self.assertFalse(value['kernel_cancellation_verified'])

    def test_blocked_display_recovery_does_not_gate_disarm_or_reboot(self):
        self.recovery_commands['display'] = self.command('recover-display', 'exec /bin/sleep 10')
        self.assert_refused('dead')
        value = self.recovery_result()
        self.assertTrue(value['disarm_completed'])
        self.assertIsNone(value['children']['display']['returncode'])
        self.assertFalse(value['display_completion_waited_for'])
        self.assertFalse(value['firmware_fallback_verified'])

    def test_refused_disarm_reboots_only_at_original_watchdog_deadline(self):
        self.recovery_commands['disarm'] = self.command('recover-disarm', status=74)
        started = time.monotonic_ns()
        self.assert_refused('dead', watchdog_seconds=0.3)
        value = self.recovery_result()
        self.assertTrue(value['watchdog_expired']); self.assertFalse(value['disarm_completed'])
        self.assertGreaterEqual(value['monotonic_ns'] - started, 300_000_000)

    def test_blocked_disarm_still_reaches_original_watchdog_deadline(self):
        self.recovery_commands['disarm'] = self.command('recover-disarm', 'exec /bin/sleep 10')
        self.assert_refused('dead', watchdog_seconds=0.3)
        value = self.recovery_result()
        self.assertTrue(value['watchdog_expired']); self.assertFalse(value['disarm_completed'])

    def test_pending_recovery_refuses_stage_before_result_file_exists(self):
        # An actual request while baseline admission is in progress; no result
        # file exists yet because the reviewed disarm fixture is blocked.
        self.recovery_commands['disarm'] = self.command('recover-disarm', 'exec /bin/sleep 10')
        original = startup.Recovery.arm
        def arm_and_refuse(owner, deadline):
            original(owner, deadline)
            owner.request()
            self.assertFalse((self.root / 'recovery.json').exists())
        with mock.patch.object(startup.Recovery, 'arm', arm_and_refuse):
            self.assert_refused(watchdog_seconds=0.3, expected='startup-recovery-pending')
        self.assertNotIn('initialize', self.names())

    def test_second_process_cannot_reuse_fixed_attempt_scope(self):
        original = startup.Recovery.arm
        def compete(owner, deadline):
            original(owner, deadline)
            pid = os.fork()
            if pid == 0:
                try: self.run_attempt()
                except FileExistsError: os._exit(0)
                except BaseException: os._exit(74)
                os._exit(99)
            _, status = os.waitpid(pid, 0)
            self.assertEqual(0, os.waitstatus_to_exitcode(status))
        with mock.patch.object(startup.Recovery, 'arm', compete):
            self.run_attempt()
        self.assertEqual(list(startup.ROLES), self.names())

    def test_command_changed_or_shared_parent_refused(self):
        command = self.stage_commands['initialize']
        path = Path(command.argv[1]); path.write_text('exit 0\n')
        with self.assertRaises(capture.CaptureError): command.check()
        with tempfile.TemporaryDirectory(dir='/tmp') as folder:
            shared = Path(folder).resolve() / 'fake'
            shared.write_text('exit 0\n'); shared.chmod(0o700)
            cmd = startup.Command([str(shared)], {str(shared): hashlib.sha256(shared.read_bytes()).hexdigest()})
            with self.assertRaisesRegex(capture.CaptureError, 'startup-command-parent'): cmd.check()

    def test_missing_recovery_input_retains_claim_without_starting_observer(self):
        Path(self.recovery_commands['disarm'].argv[1]).unlink()
        with self.assertRaises(OSError): self.run_attempt()
        self.assertTrue((self.scope / 'startup.started').exists())
        self.assertEqual([], self.names())
        self.assertFalse((self.work / 'fixture-observer.pid').exists())

    def test_observer_fork_failure_closes_both_ready_pipe_fds(self):
        original = os.fork
        calls = []
        pipes = []
        original_pipe = os.pipe
        def pipe():
            value = original_pipe(); pipes.append(value)
            return value
        def fork():
            calls.append(True)
            if len(calls) == 2: raise OSError(11, 'fixture fork failure')
            return original()
        with mock.patch.object(startup.os, 'fork', side_effect=fork), \
                mock.patch.object(startup.os, 'pipe', side_effect=pipe):
            self.assert_refused()
        self.assertEqual(3, len(pipes))
        for fd in pipes[-1]:
            with self.assertRaises(OSError): os.fstat(fd)
        self.assertFalse((self.work / 'fixture-observer.pid').exists())

    def test_coordinator_exit_eof_keeps_independent_recovery_alive(self):
        # Fork an actual coordinator, stop it after the baseline job blocks,
        # and verify recovery proceeds without any request/ack from that PID.
        pid = os.fork()
        if pid == 0:
            self.mode = 'blocked'
            try: self.run_attempt()
            except BaseException: os._exit(74)
            os._exit(99)
        try:
            self.wait_file(self.root / 'startup.jsonl')
            # The observer closes its inherited control pipe before its job.
            time.sleep(0.05)
            os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0); pid = None
            self.assertEqual('coordinator-ended', self.recovery_result()['reason'])
        finally:
            if pid is not None:
                os.kill(pid, signal.SIGKILL); os.waitpid(pid, 0)


if __name__ == '__main__':
    unittest.main()
