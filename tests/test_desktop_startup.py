"""Actual desktop adapters with fake native I/O; never opens a live service."""
import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import allocation_capture as capture
import desktop_startup as desktop


def held_history():
    return dict(zip(desktop.HISTORY_FIELDS, (
        1, 144, 17, 1, 10, 20, 120_000_000_020, 0, 0, 1, 0, 0, 0, 0, 0, 50, 1, 0)))


READY = dict(format=1, baseline_completed_ns=30, ready_ns=40, deadline_ns=180_000_000_000, observer_pid=1,
             baseline_sha256='a' * 64)
RELEASE = dict(before_ns=55, after_ns=65, reports_before=4, frames_before=10)


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang++')
        if not compiler:
            raise RuntimeError('Clang is required for actual display CPU contracts')
        cls.temp = tempfile.TemporaryDirectory(prefix='phx-display-cpu-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        source = (ROOT / 'src/phxaccel/accel/phxagdc.cpp').read_text()
        start = source.index('static IOService *gHoldFB')
        end = source.index('\nvoid phxHoldInit', start)
        (folder / 'display-bridge.inc').write_text(source[start:end])
        source = (ROOT / 'src/phxaccel/accel/phxfb.cpp').read_text()
        matches = re.findall(r'    IOReturn newUserClient\(.*?^    }', source, re.S | re.M)
        if len(matches) != 1:
            raise RuntimeError('Actual framebuffer server override missing or ambiguous')
        (folder / 'display-server.inc').write_text(matches[0])
        cls.binary = folder / 'history-fake'
        p = subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra', '-Wno-unused-parameter',
                            '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                            '-I' + str(ROOT / 'src/phxaccel'), '-I' + str(folder),
                            str(ROOT / 'tests/test_display_history.cpp'), '-o', str(cls.binary)],
                           capture_output=True, text=True, timeout=60)
        if p.returncode:
            raise RuntimeError(p.stderr)

    def test_actual_kernel_bridge_retains_release_timeout_rearm_restart_and_server_history(self):
        for case in ('release', 'timeout', 'rearm', 'restart', 'server'):
            with self.subTest(case=case):
                p = subprocess.run([str(self.binary), case], capture_output=True, timeout=10)
                self.assertEqual(0, p.returncode, p.stderr.decode())

    def test_history_wire_and_held_admission(self):
        value = held_history()
        raw = struct.pack('<18Q', *(value[name] for name in desktop.HISTORY_FIELDS))
        self.assertEqual(value, desktop.history(raw))
        self.assertEqual(dict(framebuffer_id=17, held=True, panel_open=False), desktop.check_history(value, READY))
        for bad in (raw[:-1], raw + b'\0'):
            with self.assertRaises(capture.CaptureError): desktop.history(bad)

    def test_no_early_open_timeout_reset_or_ambiguous_baseline_is_admitted(self):
        for changes in (dict(first_release_ns=25, release_count=1), dict(server_requests=1, first_server_request_ns=25),
                        dict(read_ns=120_000_000_020), dict(held=0)):
            with self.subTest(changes=changes), self.assertRaises(capture.CaptureError):
                desktop.check_history({**held_history(), **changes}, READY)
        for changes in (dict(preparations=2), dict(hold_on_count=2), dict(invalid=1), dict(version=2),
                        dict(hold_deadline_ns=130_000_000_020), dict(server_successes=1)):
            value = {**held_history(), **changes}
            raw = struct.pack('<18Q', *(value[name] for name in desktop.HISTORY_FIELDS))
            with self.subTest(changes=changes), self.assertRaises(capture.CaptureError): desktop.history(raw)
        with self.assertRaises(capture.CaptureError):
            desktop.check_history(held_history(), {**READY, 'baseline_completed_ns': 15})

    def test_released_order_requires_explicit_sysctl_before_any_server_open(self):
        value = {**held_history(), 'held': 0, 'first_release_ns': 60, 'release_count': 1,
                 'release_reason': 1, 'read_ns': 90, 'first_server_request_ns': 70,
                 'server_requests': 1, 'first_server_success_ns': 80, 'server_successes': 1}
        self.assertTrue(desktop.check_history(value, READY, RELEASE)['panel_open'])
        for changes in (dict(release_reason=2), dict(first_release_ns=54), dict(first_release_ns=66),
                        dict(first_server_request_ns=59), dict(first_server_success_ns=69), dict(release_count=2)):
            with self.subTest(changes=changes), self.assertRaises(capture.CaptureError):
                desktop.check_history({**value, **changes}, READY, RELEASE)

    def test_prepare_precedes_base_start_and_agdc_remains_asynchronous(self):
        source = (ROOT / 'src/phxaccel/accel/phxfb.cpp').read_text()
        self.assertLess(source.index('    phxDisplayHistoryPrepare(this);'), source.index('    if (!IOFramebuffer::start(provider))'))
        source = (ROOT / 'src/phxaccel/accel/phxagdc.cpp').read_text()
        handler = source[source.index('static int phxagdc_sysctl'):source.index('SYSCTL_PROC(_debug, OID_AUTO, phxagdc,')]
        self.assertIn('thread_call_enter(gCall);', handler)
        self.assertNotIn('agdcWork(', handler)
        self.assertIn('if (req->newptr) return EPERM;', source)
        self.assertIn('phxHoldInit(this, kBootHoldSec);', (ROOT / 'src/phxaccel/accel/phxfb.cpp').read_text())


class MonitorTests(unittest.TestCase):
    def test_initial_one_or_two_reports_do_not_trigger_fallback(self):
        policy = desktop.CrashPolicy(7)
        self.assertFalse(policy.initial(8)); self.assertFalse(policy.initial(9)); self.assertTrue(policy.initial(10))

    def test_later_watch_retains_two_report_window_and_reference_test_order(self):
        policy = desktop.CrashPolicy(7)
        self.assertFalse(policy.later(8, 100))
        self.assertFalse(policy.later(8, 400))
        self.assertTrue(policy.later(9, 415))
        policy = desktop.CrashPolicy(7)
        self.assertFalse(policy.later(8, 100))
        self.assertFalse(policy.later(8, 401))
        self.assertEqual(8, policy.baseline)
        self.assertFalse(policy.later(9, 410)); self.assertTrue(policy.later(10, 420))

    def test_initial_and_later_report_patterns_are_distinct(self):
        with tempfile.TemporaryDirectory() as name:
            for filename in ('WindowServer-one.ips', 'WindowServer_two.spin', 'WindowServer-x.spin', 'other.ips'):
                (Path(name) / filename).write_text('fixture')
            self.assertEqual(3, desktop.count_reports(name))
            self.assertEqual(1, desktop.count_reports(name, later=True))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'build'; base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='desktop-fixture-', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.scope = Path(self.temp.name).resolve()
        self.packet = dict(scope=str(self.scope), phxctl='/fixture/phxctl', mesboot='/fixture/mesboot',
                           firmware_dir='/fixture/fw', psp_layout=[1, 2, 3, 4, 5], desktop_layout=list(range(12)),
                           reports=str(self.scope), spec={})
        self.native = desktop.Native(self.packet, {}, self.scope / 'packet')
        self.calls = []
        def call(label, argv, **kwargs):
            self.calls.append((label, argv, kwargs))
            if label == 'accelerator': return plistlib.dumps([{}])
            if label == 'framebuffer': return plistlib.dumps([dict(IORegistryEntryID=17)])
            return b'0\n'
        self.native.call = mock.Mock(side_effect=call)
        self.native.guard = mock.Mock()
        self.native.syswrite = mock.Mock()
        self.native.sysread = mock.Mock(return_value=1)
        capture.write_json(self.scope / 'observer-ready.json', READY)

    def completed(self, role, value=None):
        capture.write_json(self.scope / (role + '-completed.json'), value or dict(format=1))

    def test_actual_initialize_passes_exact_layouts_and_propagates_firmware_failure(self):
        self.native.initialize()
        self.assertEqual(['firmware-power', 'desktop-init'], [c[0] for c in self.calls])
        self.assertEqual(['1', '2', '3', '4', '5'], self.calls[0][1][-5:])
        self.assertEqual(list(map(str, range(12))), self.calls[1][1][-12:])
        self.native.call.side_effect = capture.CaptureError('fixture-firmware-failed')
        with self.assertRaisesRegex(capture.CaptureError, 'fixture-firmware-failed'): self.native.initialize()
        self.assertEqual(3, self.native.call.call_count)

    def test_claim_requires_completed_initialization_and_exact_native_command(self):
        with self.assertRaises(OSError): self.native.claim()
        self.native.call.assert_not_called()
        self.completed('initialize'); self.native.claim()
        self.assertEqual('desktop-claim', self.calls[0][1][1])
        self.assertEqual(list(map(str, range(12))), self.calls[0][1][-12:])

    def test_display_checks_each_gate_and_asynchronous_agdc_result(self):
        self.completed('claim')
        with mock.patch.object(desktop.time, 'sleep'): self.native.display()
        self.assertEqual([mock.call('phxbos_flush', 0), mock.call('nvaccelfb', 1, expected=1),
                          mock.call('nvaccel_iop', 1), mock.call('nvaccelfb', 3, expected=1),
                          mock.call('nvaccel_iop_sse', 1), mock.call('nvaccel_iop_vsync', 1)],
                         self.native.syswrite.call_args_list)
        self.native.sysread.return_value = -6
        with mock.patch.object(desktop.time, 'sleep'), self.assertRaisesRegex(capture.CaptureError, 'agdc-not-up'):
            self.native.display()

    def test_gate_failure_stops_later_display_writes(self):
        self.completed('claim')
        self.native.syswrite.side_effect = capture.CaptureError('fixture-gate')
        with self.assertRaises(capture.CaptureError): self.native.display()
        self.assertEqual([mock.call('phxbos_flush', 0)], self.native.syswrite.call_args_list)
        self.native.call.assert_not_called()

    def test_monitor_runs_full_ninety_seconds_and_first_reports_only_collect(self):
        self.completed('release', RELEASE)
        clock = [100.0]
        def sleep(seconds): clock[0] += seconds
        with mock.patch.object(desktop.time, 'monotonic', side_effect=lambda: clock[0]), \
             mock.patch.object(desktop.time, 'sleep', side_effect=sleep), \
             mock.patch.object(desktop, 'count_reports', return_value=6):
            value = self.native.monitor()
        self.assertEqual(90, value['seconds']); self.assertEqual(2, value['report_delta'])
        self.assertFalse(value['usable_accelerated_desktop_proven'])
        self.assertTrue(any(c[0] == 'windowserver' for c in self.calls))

    def test_monitor_third_report_refuses_without_claiming_success(self):
        self.completed('release', RELEASE)
        with mock.patch.object(desktop.time, 'sleep'), mock.patch.object(desktop, 'count_reports', return_value=7), \
             self.assertRaisesRegex(capture.CaptureError, 'three-reports'):
            self.native.monitor()
        self.assertFalse(any(c[0] == 'windowserver' for c in self.calls))

    def test_current_panel_state_does_not_infer_open_from_a_closed_historical_client(self):
        value = {**held_history(), 'held': 0, 'first_release_ns': 60, 'release_count': 1,
                 'release_reason': 1, 'read_ns': 90, 'server_requests': 1, 'first_server_request_ns': 70,
                 'server_successes': 1, 'first_server_success_ns': 80}
        raw = struct.pack('<18Q', *(value[name] for name in desktop.HISTORY_FIELDS))
        self.native.call.side_effect = [raw, plistlib.dumps([dict(IORegistryEntryID=17)])]
        self.completed('release', RELEASE)
        self.assertFalse(self.native.boundary()['panel_open'])

    def test_current_panel_and_history_must_agree(self):
        value = held_history()
        raw = struct.pack('<18Q', *(value[name] for name in desktop.HISTORY_FIELDS))
        self.native.call.side_effect = [raw, plistlib.dumps([dict(IORegistryEntryID=17,
            IORegistryEntryChildren=[dict(IOObjectClass='IOFramebufferUserClient')])])]
        with self.assertRaisesRegex(capture.CaptureError, 'history-invalid'): self.native.read_history()

    def test_stage_claims_are_durable_single_use_and_need_coordinator(self):
        with self.assertRaises(OSError): self.native.claim_role('initialize')
        capture.write_json(self.scope / 'startup.started', {'format': 1})
        self.native.claim_role('initialize')
        with self.assertRaises(FileExistsError): self.native.claim_role('initialize')

    def test_stage_specific_deadline_has_room_for_unchanged_monitor(self):
        self.assertEqual(100, desktop.STAGE_TIMEOUTS['monitor'])
        self.assertGreater(desktop.STAGE_TIMEOUTS['monitor'], 90)
        self.assertEqual(set(desktop.startup.ROLES), set(desktop.STAGE_TIMEOUTS))

    def test_actual_disarm_records_absence_and_preserves_other_control_files(self):
        controls = self.scope / 'controls'; controls.mkdir()
        (controls / 'phxboot-m2').write_text('')
        (controls / 'unrelated').write_text('keep')
        def call(label, argv, **kwargs):
            self.calls.append((label, argv, kwargs))
            self.native.last_returncode = 1 if label == 'check-nvram' else 0
            self.native.last_stderr = b'phxfb-boot: data was not found'
            return b''
        self.native.call.side_effect = call
        with mock.patch.object(desktop, 'CONTROL_DIR', controls): self.native.disarm()
        self.assertTrue((controls / 'phxboot-off').exists())
        self.assertFalse((controls / 'phxboot-m2').exists())
        self.assertEqual('keep', (controls / 'unrelated').read_text())
        self.assertEqual([['/usr/sbin/nvram', '-d', 'phxfb-boot'],
                          ['/usr/sbin/nvram', 'IONVRAM-FORCESYNCNOW-PROPERTY=phxfb'],
                          ['/usr/sbin/nvram', 'phxfb-boot']], [c[1] for c in self.calls])

    def test_disarm_cannot_mistake_permission_error_for_absent_arming(self):
        controls = self.scope / 'controls'; controls.mkdir()
        def call(*_args, **_kwargs):
            self.native.last_returncode = 1
            self.native.last_stderr = b'permission denied'
            return b''
        self.native.call.side_effect = call
        with mock.patch.object(desktop, 'CONTROL_DIR', controls), self.assertRaisesRegex(capture.CaptureError, 'disarm-readback'):
            self.native.disarm()

    def test_fallback_reboot_dispatch_is_single_use(self):
        self.native.reboot()
        with self.assertRaises(FileExistsError): self.native.reboot()
        self.assertEqual([('fallback-reboot', ['/sbin/shutdown', '-r', 'now'], {})], self.calls)

    def test_boot_kill_switch_refuses_before_service_or_gpu_calls(self):
        controls = self.scope / 'controls'; controls.mkdir()
        (controls / 'phxboot-off').write_text('')
        with mock.patch.object(desktop, 'CONTROL_DIR', controls), \
             mock.patch.object(desktop, 'PENDING_MARKER', self.scope / 'legacy.pending'), \
             self.assertRaisesRegex(capture.CaptureError, 'desktop-boot-control'):
            self.native.await_services()
        self.native.call.assert_not_called()

    def test_real_ioreg_zero_byte_absence_is_waited_for_but_malformed_plist_refuses(self):
        self.native.p['spec'] = {'expected_build': 39}
        self.native.call.side_effect = [b'', b'', plistlib.dumps([{'phx-build': 39}]), plistlib.dumps([{}]), b'']
        with mock.patch.object(desktop, 'CONTROL_DIR', self.scope), \
             mock.patch.object(desktop, 'PENDING_MARKER', self.scope / 'legacy.pending'), \
             mock.patch.object(desktop.time, 'sleep') as sleep:
            self.native.await_services()
        sleep.assert_called_once_with(1)
        self.assertEqual([], desktop.ioreg_nodes(b''))
        with self.assertRaises(ValueError): desktop.ioreg_nodes(b'<broken>')
        with self.assertRaises(capture.CaptureError): desktop.ioreg_nodes(plistlib.dumps({'wrong': 'shape'}))


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'build'; base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='desktop-runtime-fixture-', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.scope = Path(self.temp.name).resolve(); self.scope.chmod(0o700)
        self.runtime = self.scope / 'python'; self.runtime.mkdir(mode=0o700)
        self.interpreter = self.runtime / 'python3.13'
        self.interpreter.write_bytes(b'fixture interpreter'); self.interpreter.chmod(0o700)
        self.manifest = self.scope / 'runtime.json'
        self.files = {'python3.13': hashlib.sha256(self.interpreter.read_bytes()).hexdigest()}
        capture.write_json(self.manifest, dict(format=1, root=str(self.runtime), files=self.files))

    def check(self):
        with mock.patch.object(desktop.sys, 'executable', str(self.interpreter)):
            desktop.check_runtime(self.manifest, str(self.interpreter))

    def test_exact_interpreter_tree_and_file_set(self):
        self.check()
        (self.runtime / 'extra.py').write_text('unexpected import')
        with self.assertRaises(capture.CaptureError): self.check()

    def test_runtime_file_tamper_symlink_or_writable_file_is_refused(self):
        self.interpreter.write_bytes(b'drift')
        with self.assertRaises(capture.CaptureError): self.check()
        self.interpreter.write_bytes(b'fixture interpreter')
        self.interpreter.chmod(0o722)
        with self.assertRaises(capture.CaptureError): self.check()
        self.interpreter.chmod(0o700)
        self.interpreter.unlink(); self.interpreter.symlink_to(self.manifest)
        with self.assertRaises(capture.CaptureError): self.check()

    def test_packet_refuses_process_relative_python_before_reading_or_native_work(self):
        with mock.patch.object(desktop.sys, 'version_info', (3, 9, 6)), \
             self.assertRaisesRegex(capture.CaptureError, 'desktop-clock-runtime'):
            desktop.load_packet(self.scope / 'does-not-exist')

    def test_packet_exact_pins_and_recovery_subset(self):
        entry = self.scope / 'entry.py'; entry.write_text('# fixture')
        entry.chmod(0o600)
        pins = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (self.interpreter, self.manifest, entry)}
        packet = dict(format=1, request_sha256='a' * 64, scope=str(self.scope),
                      preparation_boot_uuid='AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE', os_build='25G332',
                      accel_image_uuid='11111111-2222-3333-4444-555555555555', interpreter=str(self.interpreter),
                      runtime_manifest=str(self.manifest), entrypoint=str(entry), phxctl=str(self.interpreter),
                      mesboot=str(self.interpreter), firmware_dir=str(self.scope), reports=str(self.scope),
                      psp_layout=[1, 2, 3, 4, 5], desktop_layout=list(range(12)), pins=pins, recovery_pins=pins.copy(),
                      spec=dict(reader=str(self.interpreter), reader_sha256=pins[str(self.interpreter)], expected_build=39,
                                expected_image_uuid='11111111-2222-3333-4444-555555555555'))
        path = self.scope / 'packet.json'; capture.write_json(path, packet)
        with mock.patch.object(desktop.sys, 'executable', str(self.interpreter)), \
             mock.patch.object(desktop.sys, 'version_info', (3, 13, 18)):
            loaded, got = desktop.load_packet(path)
            self.assertEqual(packet, loaded)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), got[str(path)])
        packet['recovery_pins'].pop(str(self.manifest))
        bad = self.scope / 'bad-packet.json'; capture.write_json(bad, packet)
        with mock.patch.object(desktop.sys, 'version_info', (3, 13, 18)), self.assertRaises(capture.CaptureError):
            desktop.load_packet(bad, recovery_only=True)


class ProcessIntegrationTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'build'; base.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='desktop-chain-fixture-', dir=base)
        self.addCleanup(self.temp.cleanup)
        self.scope = Path(self.temp.name).resolve()
        self.scope.chmod(0o700)
        (self.scope / 'controls').mkdir(mode=0o700)
        reports = self.scope / 'reports'; reports.mkdir(mode=0o700)
        interpreter = str(Path(sys.executable).resolve())
        entry = str(ROOT / 'tests/desktop_startup_fixture.py')
        names = [interpreter, entry, *map(str, (ROOT / 'tools').glob('allocation_*.py')), str(ROOT / 'tools/desktop_startup.py')]
        pins = {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in names}
        image = '11111111-2222-3333-4444-555555555555'
        self.packet = dict(scope=str(self.scope), interpreter=interpreter, entrypoint=entry, pins=pins, recovery_pins=pins,
                           request_sha256='a' * 64, preparation_boot_uuid='AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE',
                           os_build='25G332', phxctl='/fixture/phxctl', mesboot='/fixture/mesboot', firmware_dir='/fixture/fw',
                           psp_layout=[1, 2, 3, 4, 5], desktop_layout=list(range(12)), reports=str(reports),
                           fixture_identity=dict(boot_uuid='99999999-8888-7777-6666-555555555555', os_build='25G332',
                                                 service_entry_id=42, kext_build=39, loaded_image_uuid=image),
                           fixture_hold_ns=(time.clock_gettime_ns(time.CLOCK_UPTIME_RAW)
                                            if sys.platform == 'darwin' and sys.version_info < (3, 13)
                                            else time.monotonic_ns()), fixture_mode='success',
                           spec=dict(reader='/fixture/reader', reader_sha256='b' * 64, expected_build=39, expected_image_uuid=image))
        self.addCleanup(self.clean_workers)

    def clean_workers(self):
        for path in self.scope.glob('*.pid'):
            pid = int(path.read_text())
            try: os.kill(pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: os.waitpid(pid, os.WNOHANG)
            except ChildProcessError: pass

    def run_chain(self, mode):
        self.packet['fixture_mode'] = mode
        packet_path = self.scope / 'packet.json'
        capture.write_json(packet_path, self.packet)
        command = [self.packet['interpreter'], '-I', '-S', self.packet['entrypoint'], '--packet', str(packet_path), '--role', 'run']
        p = subprocess.run(command, capture_output=True, timeout=25)
        return p

    def test_actual_adapters_coordinator_observer_and_two_recovery_owners_complete_in_order(self):
        p = self.run_chain('success')
        self.assertEqual(0, p.returncode, p.stderr.decode())
        journal = [json.loads(line) for line in (self.scope / 'run/startup.jsonl').read_text().splitlines()]
        self.assertEqual(list(desktop.startup.ROLES), [row['data']['role'] for row in journal if row['event'] == 'stage-request'])
        metadata = json.loads((self.scope / 'metadata-recovery/recovery.json').read_text())
        final = json.loads((self.scope / 'run/recovery.json').read_text())
        self.assertEqual('handed-to-coordinator-recovery', metadata['outcome'])
        self.assertEqual('dismissed-after-monitor', final['outcome'])
        armed = next(row for row in journal if row['event'] == 'recovery-armed')
        initial = json.loads((self.scope / 'metadata-recovery-armed.json').read_text())
        self.assertLessEqual(armed['data']['deadline_monotonic'], initial['deadline_monotonic'])
        self.assertTrue((self.scope / 'fixture-later-watch-entered').exists())
        self.assertFalse((self.scope / 'fixture-reboot-requested').exists())

    def test_failed_real_initialize_adapter_skips_claim_release_and_requests_independent_recovery(self):
        p = self.run_chain('init-fail')
        self.assertEqual(74, p.returncode, p.stderr.decode())
        deadline = time.monotonic() + 5
        while not (self.scope / 'fixture-reboot-requested').exists() and time.monotonic() < deadline: time.sleep(0.01)
        self.assertTrue((self.scope / 'fixture-reboot-requested').exists())
        self.assertFalse((self.scope / 'claim.started').exists())
        self.assertFalse((self.scope / 'release.started').exists())
        self.assertNotIn('desktop-init', (self.scope / 'calls-initialize').read_text())

    def test_actual_recovery_adapters_reboot_while_display_helper_stays_blocked(self):
        p = self.run_chain('recovery-display-blocked')
        self.assertEqual(74, p.returncode, p.stderr.decode())
        deadline = time.monotonic() + 5
        while not (self.scope / 'fixture-reboot-requested').exists() and time.monotonic() < deadline: time.sleep(0.01)
        self.assertTrue((self.scope / 'fixture-reboot-requested').exists())
        self.assertTrue((self.scope / 'recovery-display-blocked').exists())
        pid = int((self.scope / 'recover-display.pid').read_text())
        os.kill(pid, 0)
        self.assertTrue((self.scope / 'controls/phxboot-off').exists())


if __name__ == '__main__':
    unittest.main()
