"""Temporary files, fake collectors and stub recovery only; never use target services."""
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import allocation_capture as capture
import allocation_observer as observer


@unittest.skipIf(os.name == 'nt', 'POSIX file/process contracts')
class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.reports = self.work / 'reports'; self.reports.mkdir(mode=0o700)
        self.out = self.work / 'private capture'
        self.scans = [{}, {}, {'WindowServer-test.ips': (1, 2)}]
        self.events = [True]
        self.trace = []
        self.now = 0.0
        self.closed = False
        self.scan_count = 0
        self.waits = []
        self.host = mock.patch.object(capture, 'host_check')
        self.host.start(); self.addCleanup(self.host.stop)

    def factory(self, path):
        self.assertEqual(self.reports, path)
        self.trace.append('watch-armed')
        owner = self
        class FakeWatch:
            def scan(self):
                owner.scan_count += 1
                owner.trace.append('scan')
                return dict(owner.scans.pop(0)) if len(owner.scans) > 1 else dict(owner.scans[0])
            def wait(self, seconds):
                owner.waits.append(seconds)
                more = owner.events.pop(0) if owner.events else False
                owner.now += 0.01 if more else seconds
                return more
            def close(self):
                owner.closed = True
                owner.trace.append('closed')
        return FakeWatch()

    def baseline(self, out, *_args):
        self.trace.append('baseline')
        self.assertEqual(self.out, out)
        out.mkdir(mode=0o700)
        capture.write_file(out / 'baseline.json', b'{"fake_baseline":true}\n')

    def failure(self, out):
        self.assertEqual(self.out, out)
        self.trace.append('failure')
        self.assertTrue((out / 'observer.trigger.json').exists())
        capture.write_file(out / 'failure.json', b'{"fake_failure":true}\n')

    def run_observer(self, **changes):
        args = dict(reports=self.reports, out=self.out, reader=self.work / 'unused reader', digest='0'*64,
                    build=37, image='unused by fake collector', window_seconds=90,
                    watch_factory=self.factory, baseline=self.baseline, failure=self.failure,
                    clock=lambda: self.now)
        args.update(changes)
        return observer.observe(**args)

    def test_armed_before_baseline_and_exactly_one_failure_on_first_discovery(self):
        result = self.run_observer()
        self.assertEqual('captured', result['outcome'])
        self.assertEqual(['watch-armed', 'scan', 'baseline', 'scan', 'scan', 'failure', 'closed'], self.trace)
        self.assertEqual(1, result['notifications'])
        self.assertEqual(hashlib.sha256((self.out / 'failure.json').read_bytes()).hexdigest(), result['failure_sha256'])
        self.assertEqual(result, json.loads((self.out / 'observer.json').read_bytes()))
        for path in [self.out, *self.out.rglob('*')]:
            self.assertFalse(path.stat().st_mode & 0o077)

    def test_report_created_during_baseline_is_seen_without_wait(self):
        self.scans = [{}, {'WindowServer-during.spin': (1, 3)}]
        self.assertEqual('captured', self.run_observer()['outcome'])
        self.assertEqual([], self.waits)

    def test_readiness_follows_full_baseline_and_first_post_baseline_scan(self):
        receipts = []
        def ready(value):
            self.assertEqual(['watch-armed', 'scan', 'baseline', 'scan'], self.trace)
            self.assertEqual(hashlib.sha256((self.out / 'baseline.json').read_bytes()).hexdigest(),
                             value['baseline_sha256'])
            self.assertEqual(os.getpid(), value['observer_pid'])
            self.assertLessEqual(value['baseline_completed_ns'], value['ready_ns'])
            self.assertLess(value['ready_ns'], value['deadline_ns'])
            receipts.append(value)
        self.run_observer(on_ready=ready)
        self.assertEqual(1, len(receipts))

    def test_early_report_never_signals_readiness(self):
        self.scans = [{}, {'WindowServer-during.spin': (1, 3)}]
        ready = mock.Mock()
        self.run_observer(on_ready=ready)
        ready.assert_not_called()

    def test_expired_baseline_never_signals_readiness(self):
        def slow(*args):
            self.baseline(*args)
            self.now = 90.0
        ready = mock.Mock()
        self.run_observer(baseline=slow, on_ready=ready)
        ready.assert_not_called()

    def test_old_reports_are_ignored_and_same_name_new_inode_is_new(self):
        self.scans = [{'WindowServer-old.ips': (1, 2)}] * 2 + [{'WindowServer-old.ips': (1, 3)}]
        self.assertEqual('captured', self.run_observer()['outcome'])
        trigger = json.loads((self.out / 'observer.trigger.json').read_bytes())
        self.assertEqual([1, 3], trigger['file_identity'])

    def test_coalesced_reports_are_one_trigger_with_a_deterministic_representative(self):
        self.scans = [{}, {'WindowServer-z.ips': (1, 3), 'WindowServer-a.ips': (1, 4)}]
        self.run_observer()
        trigger = json.loads((self.out / 'observer.trigger.json').read_bytes())
        self.assertEqual('WindowServer-a.ips', trigger['name'])
        self.assertEqual(2, trigger['new_candidate_count'])
        self.assertEqual(1, self.trace.count('failure'))

    def test_no_new_report_expires_without_failure_read(self):
        self.scans = [{'WindowServer-old.ips': (1, 2)}]
        self.events = []
        self.assertEqual('window-expired', self.run_observer()['outcome'])
        self.assertEqual([90], self.waits)
        self.assertNotIn('failure', self.trace)
        self.assertFalse((self.out / 'observer.trigger.json').exists())

    def test_baseline_exhausting_window_does_not_start_another_capture(self):
        def slow(*args):
            self.baseline(*args)
            self.now = 91
        self.assertEqual('window-expired', self.run_observer(baseline=slow)['outcome'])
        self.assertEqual(1, self.scan_count)
        self.assertNotIn('failure', self.trace)
        started = json.loads((self.out / 'observer.started').read_bytes())
        self.assertLess(started['deadline_monotonic'], self.now)
        self.assertEqual(hashlib.sha256((self.out / 'baseline.json').read_bytes()).hexdigest(),
                         started['baseline_sha256'])
        self.assertEqual('window-expired', json.loads((self.out / 'observer.json').read_bytes())['outcome'])

    def test_event_storm_stops_at_fixed_scan_and_notification_caps(self):
        self.scans = [{}]
        self.events = [True] * 1000
        result = self.run_observer()
        self.assertEqual('event-limit', result['outcome'])
        self.assertEqual(observer.MAX_EVENTS, len(self.waits))
        self.assertEqual(observer.MAX_EVENTS + 2, self.scan_count)
        self.assertTrue(all(0 < seconds <= 90 for seconds in self.waits))
        self.assertNotIn('failure', self.trace)

    def test_scan_or_trigger_persistence_crossing_deadline_starts_no_failure_read(self):
        for stage in ('scan', 'trigger'):
            with self.subTest(stage=stage):
                self.out = self.work / stage
                self.scans = [{}, {'WindowServer-late.ips': (1, 2)}]
                self.now = 0
                original_factory = self.factory
                def factory(path):
                    watch = original_factory(path)
                    original_scan = watch.scan
                    def scan():
                        result = original_scan()
                        if result: self.now = 91
                        return result
                    if stage == 'scan': watch.scan = scan
                    return watch
                original_publish = capture.publish_json
                def publish(path, value):
                    original_publish(path, value)
                    if path.name == 'observer.trigger.json': self.now = 91
                with mock.patch.object(capture, 'publish_json', side_effect=publish):
                    result = self.run_observer(watch_factory=factory)
                self.assertEqual('window-expired', result['outcome'])
                self.assertNotIn('failure', self.trace)
                self.assertFalse((self.out / 'failure.json').exists())

    def test_failed_baseline_never_triggers_failure_and_closes_watch(self):
        def fail(*_args): raise capture.CaptureError('fake-baseline')
        with self.assertRaises(capture.CaptureError): self.run_observer(baseline=fail)
        self.assertTrue(self.closed)
        self.assertNotIn('failure', self.trace)
        self.assertFalse(self.out.exists())

    def test_refused_failure_is_not_retried_or_reported_as_complete(self):
        def fail(out):
            self.trace.append('refused')
            capture.write_file(out / 'failure.started', b'fake consumed attempt\n')
            raise capture.CaptureError('fake-reader-refused')
        with self.assertRaises(capture.CaptureError): self.run_observer(failure=fail)
        self.assertEqual(1, self.trace.count('refused'))
        self.assertTrue(self.closed)
        self.assertTrue((self.out / 'observer.trigger.json').exists())
        self.assertFalse((self.out / 'observer.json').exists())

    def test_interruption_closes_watch_and_does_not_call_failure(self):
        def stop(*_args): raise capture.CaptureError('interrupted')
        with self.assertRaises(capture.CaptureError): self.run_observer(baseline=stop)
        self.assertTrue(self.closed)
        self.assertNotIn('failure', self.trace)

    def test_invalid_window_and_host_refusal_precede_all_io(self):
        for window in (0, 301, True, '90'):
            with self.subTest(window=window), self.assertRaises(capture.CaptureError):
                self.run_observer(window_seconds=window)
        self.assertEqual([], self.trace)
        with mock.patch.object(capture, 'host_check', side_effect=capture.CaptureError('host-refused')):
            with self.assertRaises(capture.CaptureError): self.run_observer()
        self.assertEqual([], self.trace)

    def test_existing_output_is_never_reused(self):
        self.out.mkdir(mode=0o700)
        (self.out / 'keep').write_bytes(b'unchanged')
        with self.assertRaises(FileExistsError): self.run_observer()
        self.assertEqual(['keep'], [path.name for path in self.out.iterdir()])
        self.assertTrue(self.closed)

    def test_actual_collector_and_reader_process_with_fake_native_identity(self):
        import test_allocation_capture as fixture_module
        fixture = fixture_module.CaptureTests('test_full_sequence_is_two_single_reads_with_private_durable_outputs')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.out = fixture.out
        def baseline(out, reader, digest, build, image):
            capture.begin(out, reader, digest, build, image, run=fixture.run_fake)
            fixture_module.add(fixture.value, 6)
        result = self.run_observer(reader=fixture.reader, digest=fixture.digest, image=fixture_module.IMAGE,
                                   baseline=baseline, failure=lambda out: capture.finish(out, run=fixture.run_fake))
        self.assertEqual('captured', result['outcome'])
        self.assertEqual(2, sum(label == 'snapshot' for _, label in fixture.calls))
        failure = json.loads((self.out / 'failure.json').read_bytes())
        self.assertEqual(1, failure['comparison'][6]['minimum_new_occurrences'])
        self.assertEqual(2, failure['comparison'][6]['new_records'][0]['status'])

    def test_cli_fixed_errors_and_no_workload_or_recovery_options(self):
        args = ['allocation_observer.py', '--reports', str(self.reports), '--out', str(self.out),
                '--reader', str(self.work / 'unused'), '--reader-sha256', '0'*64,
                '--expected-build', '37', '--expected-image-uuid', 'unused', '--window-seconds', '90']
        for error in (OSError('PRIVATE_PATH'), capture.CaptureError('interrupted')):
            with self.subTest(error=type(error).__name__), mock.patch.object(sys, 'argv', args), \
                    mock.patch.object(observer, 'observe', side_effect=error), \
                    mock.patch.object(observer.signal, 'signal'), \
                    mock.patch.object(sys, 'stderr', new_callable=StringIO) as stderr:
                self.assertEqual(74, observer.main())
                self.assertNotIn('PRIVATE_PATH', stderr.getvalue())
                self.assertNotIn(str(self.work), stderr.getvalue())
        for outcome, expected in (('captured', 0), ('window-expired', 75), ('event-limit', 75)):
            with mock.patch.object(sys, 'argv', args), \
                    mock.patch.object(observer, 'observe', return_value={'outcome': outcome}), \
                    mock.patch.object(observer.signal, 'signal'), mock.patch.object(sys, 'stdout', new_callable=StringIO):
                self.assertEqual(expected, observer.main())

    def test_separate_stub_recovery_runs_with_a_blocked_or_dead_observer(self):
        worker = self.work / 'fake-observer.py'
        worker.write_text('''import pathlib,sys,time
sys.path.insert(0, sys.argv[1])
import allocation_capture as c
import allocation_observer as o
c.host_check=lambda: None
root=pathlib.Path(sys.argv[2])
class Watch:
 def __init__(self, _): self.calls=0
 def scan(self):
  self.calls+=1
  return {} if self.calls==1 else {'WindowServer-fake.ips': (1,2)}
 def wait(self, _): return True
 def close(self): pass
def baseline(out, *_):
 out.mkdir(mode=0o700)
 c.write_file(out/'baseline.json', b'{}')
def blocked(out):
 c.write_file(root/'blocked', b'fake collector blocked')
 time.sleep(30)
o.observe(root, root/'capture', root/'unused-reader', '0'*64, 37, 'fake', 90,
          watch_factory=Watch, baseline=baseline, failure=blocked)
''')
        recovery = self.work / 'stub-recovery.py'
        recovery.write_text('import pathlib,sys,time; time.sleep(0.05); pathlib.Path(sys.argv[1]).write_bytes(b"stub only")')
        for mode in ('blocked', 'dead'):
            with self.subTest(mode=mode):
                root = self.work / mode; root.mkdir(mode=0o700)
                child = subprocess.Popen((sys.executable, str(worker), str(ROOT / 'tools'), str(root)),
                                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                try:
                    deadline = time.monotonic() + 3
                    while not (root / 'blocked').exists() and child.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue((root / 'blocked').exists())
                    if mode == 'dead': child.kill(); child.wait(timeout=3)
                    result = subprocess.run((sys.executable, str(recovery), str(root / 'stub-recovery.complete')),
                                            capture_output=True, timeout=3)
                    self.assertEqual(0, result.returncode)
                    self.assertEqual(b'stub only', (root / 'stub-recovery.complete').read_bytes())
                    if mode == 'blocked': self.assertIsNone(child.poll())
                finally:
                    if child.poll() is None: child.kill(); child.wait(timeout=3)


@unittest.skipIf(os.name == 'nt', 'POSIX directory metadata only')
class DirectoryWatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.reports = self.work / 'reports'; self.reports.mkdir(mode=0o700)

    def scan_watch(self):
        watch = observer.ReportWatch.__new__(observer.ReportWatch)
        watch.fd = os.open(self.reports, os.O_RDONLY | os.O_DIRECTORY)
        watch.queue = None
        watch.path = self.reports
        info = os.fstat(watch.fd)
        watch.identity = (info.st_dev, info.st_ino)
        self.addCleanup(watch.close)
        return watch

    def test_only_new_regular_ips_or_spin_candidates_and_no_content_read(self):
        for name in ('WindowServer-one.ips', 'WindowServer_two.spin', 'WindowServer-tmp.ips.tmp', 'other.ips'):
            (self.reports / name).write_bytes(b'PRIVATE_REPORT_CONTENTS')
        (self.reports / 'WindowServer-directory.ips').mkdir()
        (self.reports / 'WindowServer-link.ips').symlink_to(self.reports / 'other.ips')
        watch = self.scan_watch()
        with mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('report contents must not be read')):
            result = watch.scan()
        self.assertEqual({'WindowServer-one.ips', 'WindowServer_two.spin'}, set(result))
        self.assertTrue(all(len(identity) == 2 for identity in result.values()))

    def test_directory_entry_cap_counts_unrelated_files_too(self):
        for name in ('a', 'b', 'c'): (self.reports / name).touch()
        watch = self.scan_watch()
        with mock.patch.object(observer, 'MAX_ENTRIES', 2):
            with self.assertRaises(capture.CaptureError): watch.scan()

    def test_repeated_scans_retain_old_entries_and_discover_new_ones(self):
        (self.reports / 'WindowServer-old.ips').touch()
        watch = self.scan_watch()
        initial = watch.scan()
        self.assertEqual(initial, watch.scan())
        (self.reports / 'WindowServer-new.spin').touch()
        current = watch.scan()
        self.assertEqual({'WindowServer-old.ips', 'WindowServer-new.spin'}, set(current))
        self.assertEqual(initial['WindowServer-old.ips'], current['WindowServer-old.ips'])

    def test_renamed_replaced_directory_and_links_refused(self):
        watch = self.scan_watch()
        self.reports.rename(self.work / 'old')
        self.reports.mkdir(mode=0o700)
        with self.assertRaises(capture.CaptureError): watch.scan()
        alias = self.work / 'alias'; alias.symlink_to(self.reports, target_is_directory=True)
        with self.assertRaises(capture.CaptureError): observer.ReportWatch(alias)

    def test_failed_kqueue_setup_closes_owned_directory_descriptor(self):
        opened = []
        original = os.open
        def track(*args, **kwargs):
            fd = original(*args, **kwargs); opened.append(fd); return fd
        with mock.patch.object(observer.os, 'open', side_effect=track), \
                mock.patch.object(observer.select, 'kqueue', create=True, side_effect=OSError('fake setup failure')):
            with self.assertRaises(OSError): observer.ReportWatch(self.reports)
        self.assertEqual(1, len(opened))
        with self.assertRaises(OSError): os.fstat(opened[0])

    def test_world_writable_report_directory_is_refused_before_kqueue(self):
        self.reports.chmod(0o777)
        with mock.patch.object(observer.select, 'kqueue', create=True) as queue:
            with self.assertRaises(capture.CaptureError): observer.ReportWatch(self.reports)
            queue.assert_not_called()

    @unittest.skipUnless(hasattr(select, 'kqueue'), 'Native kqueue test runs only on macOS/BSD temporary files')
    def test_native_vnode_notification_on_a_temporary_directory(self):
        watch = observer.ReportWatch(self.reports)
        self.addCleanup(watch.close)
        self.assertEqual({}, watch.scan())
        (self.reports / 'WindowServer-native-fixture.ips').write_bytes(b'fake report, no GPU')
        self.assertTrue(watch.wait(1))
        self.assertEqual({'WindowServer-native-fixture.ips'}, set(watch.scan()))
        watch.close(); watch.close()


if __name__ == '__main__':
    unittest.main()
