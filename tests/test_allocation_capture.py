"""Fake processes only: this suite never invokes the native snapshot reader or host probes."""
import copy
import hashlib
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import allocation_capture as capture

BOOT = '00000000-0000-4000-8000-000000000001'
IMAGE = '00000000-0000-4000-8000-000000000002'


def empty():
    return {'version': 1, 'kext_build': 37, 'observed': 0, 'samples_per_reason': 4,
            'reasons': [{'reason': reason, 'count': 0, 'records': []} for reason in capture.REASONS]}


def add(value, reason=0, ordinal=None):
    value['observed'] = min(capture.U64, value['observed'] + 1)
    bucket = value['reasons'][reason]
    bucket['count'] = min(capture.U64, bucket['count'] + 1)
    status = 2 if reason >= 5 else 0xe00002d5
    if len(bucket['records']) < 4:
        bucket['records'].append({
            'ordinal': ordinal or value['observed'], 'status': status, 'status_hex': f'0x{status:08x}',
            'bytes': 4096 if reason >= 4 else 0, 'last_seq': 0, 'submitted': 0, 'retired': 0,
            'observation_valid': 0,
            'queues': [{'reason': 'unobserved', 'fence_read': 0, 'done': 0,
                        'floor': 0, 'count': 0, 'first_pending': 0} for _ in range(2)]})
    return value


class SnapshotParsingTests(unittest.TestCase):
    def test_empty_and_all_categories_retain_raw_codes(self):
        value = empty()
        for i in range(7):
            add(value, i)
        self.assertEqual(value, capture.snapshot(json.dumps(value).encode(), 37))
        self.assertEqual(2, value['reasons'][6]['records'][0]['status'])

    def test_malformed_schema_and_unknown_fields_refused(self):
        for field, wrong in (('version', True), ('version', 2), ('kext_build', 36),
                             ('samples_per_reason', 3), ('observed', -1), ('observed', capture.U64 + 1),
                             ('reasons', {}), ('reasons', []), ('extra', 'PRIVATE')):
            with self.subTest(field=field, wrong=wrong):
                value = empty(); value[field] = wrong
                with self.assertRaises(capture.CaptureError):
                    capture.snapshot(json.dumps(value).encode(), 37)
        for raw in (b'{}', b'[]', b'null', b'{', b'{"version":1,"version":1}', b'NaN', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(capture.CaptureError):
                capture.snapshot(raw, 37)

    def test_records_counts_ordinals_status_and_queues_refused(self):
        for fault in ('total', 'count', 'missing-record', 'extra-record', 'order', 'duplicate',
                      'status', 'negative', 'bool', 'queue', 'queue-extra', 'queue-count', 'ordinal'):
            with self.subTest(fault=fault):
                value = add(add(empty()), 0)
                reason = value['reasons'][0]; record = reason['records'][0]
                if fault == 'total': value['observed'] += 1
                elif fault == 'count': reason['count'] = capture.U64
                elif fault == 'missing-record': reason['records'].pop()
                elif fault == 'extra-record': reason['records'].append(copy.deepcopy(record))
                elif fault == 'order': reason['records'].reverse()
                elif fault == 'duplicate': reason['records'][1]['ordinal'] = record['ordinal']
                elif fault == 'status': record['status_hex'] = '0x00000002'
                elif fault == 'negative': record['bytes'] = -1
                elif fault == 'bool': record['observation_valid'] = True
                elif fault == 'queue': record['queues'][0]['reason'] = 'PRIVATE'
                elif fault == 'queue-extra': record['queues'][0]['address'] = 1
                elif fault == 'queue-count': record['queues'].pop()
                else: record['ordinal'] = 0
                with self.assertRaises(capture.CaptureError):
                    capture.snapshot(json.dumps(value).encode(), 37)

    def test_first_four_are_baseline_records_and_later_details_can_be_absent(self):
        before = empty()
        for _ in range(8): add(before)
        after = copy.deepcopy(before)
        add(after); add(after, 6)
        delta = capture.comparison(before, after)
        self.assertEqual(1, delta[0]['minimum_new_occurrences'])
        self.assertEqual([], delta[0]['new_records'])
        self.assertTrue(delta[0]['detail_capacity_exhausted'])
        self.assertEqual([after['reasons'][6]['records'][0]], delta[6]['new_records'])
        self.assertEqual(2, delta[6]['new_records'][0]['status'])

    def test_counter_and_history_replacement_refused(self):
        before = add(empty())
        for fault in ('counter', 'record', 'old-ordinal'):
            with self.subTest(fault=fault):
                after = copy.deepcopy(before)
                if fault == 'counter': after['reasons'][0]['count'] = 0
                elif fault == 'record': after['reasons'][0]['records'][0]['bytes'] = 4096
                else: add(after, 6, ordinal=1)
                with self.assertRaises(capture.CaptureError): capture.comparison(before, after)
        with self.assertRaises(capture.CaptureError): capture.comparison(before, empty())

    def test_saturation_is_a_lower_bound_and_allows_repeated_max_ordinals(self):
        before = add(empty())
        before['observed'] = before['reasons'][0]['count'] = capture.U64 - 1
        before['reasons'][0]['records'] *= 4
        # Distinct early records; only newly recorded saturated ordinals may repeat.
        for i, record in enumerate(copy.deepcopy(before['reasons'][0]['records'])):
            before['reasons'][0]['records'][i] = dict(record, ordinal=i+1)
        after = copy.deepcopy(before)
        for _ in range(2): add(after, 6)
        add(after)
        capture.snapshot(json.dumps(after).encode(), 37)
        delta = capture.comparison(before, after)
        self.assertFalse(delta[0]['delta_exact'])
        self.assertEqual(1, delta[0]['minimum_new_occurrences'])
        self.assertEqual(2, delta[6]['minimum_new_occurrences'])


@unittest.skipIf(os.name == 'nt', 'POSIX process/file boundaries; no live macOS commands')
class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name).resolve()
        self.out = self.work / 'private capture'
        self.reader = self.work / 'fake reader'
        self.value = empty()
        self.source = self.work / 'fake-source'
        self.fake = self.work / 'fake-process.py'
        self.fake.write_text('import pathlib,sys,time\n'
                             'mode=sys.argv[1]\n'
                             'if mode=="hang": time.sleep(10)\n'
                             'if mode=="fail": sys.stderr.write("PRIVATE_STDERR"); sys.exit(77)\n'
                             'if mode=="large": sys.stdout.buffer.write(b"X"*262144); sys.exit(0)\n'
                             'sys.stdout.buffer.write(pathlib.Path(sys.argv[2]).read_bytes())\n')
        self.reader.write_text('#!' + sys.executable + '\nimport pathlib,sys\n'
                               f'sys.stdout.buffer.write(pathlib.Path({str(self.source)!r}).read_bytes())\n')
        self.reader.chmod(0o700)
        self.digest = hashlib.sha256(self.reader.read_bytes()).hexdigest()
        self.calls = []
        self.fault = None
        self.host = mock.patch.object(capture, 'host_check')
        self.host.start(); self.addCleanup(self.host.stop)

    def run_fake(self, args, folder, label, deadline):
        self.calls.append((tuple(args), label))
        raw = {
            'boot': (BOOT + '\n').encode(), 'os': b'25A362\n',
            'service': plistlib.dumps([{'phx-build': 37, 'IORegistryEntryID': 123}]),
            'image': f'  99 0 0xffffff 0x123 0x1000 org.drip.PhxBringup (1.0) {IMAGE} <1 2>\n'.encode(),
            'snapshot': json.dumps(self.value).encode(),
        }[label.split('-')[0]]
        if self.fault:
            raw = self.fault(label, raw)
        self.source.write_bytes(raw)
        if label == 'snapshot':
            self.assertEqual((str(self.reader),), tuple(args))
            call = args  # This is the fake executable, never the native reader.
        else:
            self.assertEqual(capture.COMMANDS[label.split('-')[0]], tuple(args))
            call = (sys.executable, str(self.fake), 'ok', str(self.source))
        return capture.run_command(call, folder, label, deadline)

    def baseline(self):
        return capture.begin(self.out, self.reader, self.digest, 37, IMAGE, run=self.run_fake)

    def test_full_sequence_is_two_single_reads_with_private_durable_outputs(self):
        baseline = self.baseline()
        add(self.value, 6)
        result = capture.finish(self.out, run=self.run_fake)
        expected = ['boot-before', 'os-before', 'service-before', 'image-before', 'snapshot',
                    'boot-after', 'os-after', 'service-after', 'image-after']
        self.assertEqual(expected * 2, [label for _, label in self.calls])
        self.assertEqual(baseline['identity'], result['identity'])
        self.assertEqual(1, result['comparison'][6]['minimum_new_occurrences'])
        self.assertEqual(2, result['comparison'][6]['new_records'][0]['status'])
        self.assertEqual(hashlib.sha256((self.out / 'baseline.json').read_bytes()).hexdigest(),
                         result['baseline_sha256'])
        self.assertEqual(b'*\n', (self.out / '.gitignore').read_bytes())
        for path in [self.out, *self.out.rglob('*')]:
            self.assertFalse(path.stat().st_mode & 0o077)
        self.assertEqual(result, json.loads((self.out / 'failure.json').read_bytes()))

    def test_phase_cannot_be_repeated_even_after_reader_failure(self):
        self.baseline()
        with self.assertRaises(FileExistsError): self.baseline()
        self.fault = lambda label, raw: b'{}' if label == 'snapshot' else raw
        with self.assertRaises(capture.CaptureError): capture.finish(self.out, run=self.run_fake)
        self.assertTrue((self.out / 'failure.started').exists())
        self.assertFalse((self.out / 'failure.json').exists())
        calls = len(self.calls)
        with self.assertRaises(FileExistsError): capture.finish(self.out, run=self.run_fake)
        self.assertEqual(calls, len(self.calls))

    def test_different_boot_service_build_or_image_refuses_before_reader(self):
        self.baseline()
        for label, raw in (
            ('boot-before', b'00000000-0000-4000-8000-000000000003\n'),
            ('service-before', plistlib.dumps([{'phx-build': 37, 'IORegistryEntryID': 456}])),
            ('service-before', plistlib.dumps([{'phx-build': 36, 'IORegistryEntryID': 123}])),
            ('image-before', b'org.drip.PhxBringup 00000000-0000-4000-8000-000000000004')):
            with self.subTest(label=label):
                # Separate offline fixture, never a way to retry a consumed live attempt.
                target = self.work / ('copy-' + str(len(self.calls)))
                import shutil
                shutil.copytree(self.out, target)
                self.fault = lambda seen, data: raw if seen == label else data
                index = len(self.calls)
                with self.assertRaises(capture.CaptureError): capture.finish(target, run=self.run_fake)
                self.assertNotIn('snapshot', [name for _, name in self.calls[index:]])
                self.assertFalse((target / 'failure.json').exists())

    def test_identity_change_during_capture_never_marks_complete(self):
        self.fault = lambda label, raw: b'00000000-0000-4000-8000-000000000003' if label == 'boot-after' else raw
        with self.assertRaises(capture.CaptureError): self.baseline()
        self.assertTrue((self.out / 'baseline/snapshot.stdout').exists())
        self.assertFalse((self.out / 'baseline.json').exists())

    def test_ambiguous_missing_or_malformed_metadata_refused(self):
        bad = (('service-before', b'not a plist'), ('service-before', plistlib.dumps([])),
               ('service-before', plistlib.dumps([{}, {}])),
               ('service-before', plistlib.dumps([{'phx-build': 37}])),
               ('image-before', b'org.drip.PhxBringup no UUID'),
               ('image-before', (f'org.drip.PhxBringup {IMAGE}\n' * 2).encode()),
               ('boot-before', b'PRIVATE'), ('os-before', b'PRIVATE'))
        for i, (label, raw) in enumerate(bad):
            with self.subTest(label=label):
                self.out = self.work / str(i)
                self.fault = lambda seen, data: raw if seen == label else data
                with self.assertRaises((capture.CaptureError, ValueError, plistlib.InvalidFileException)):
                    self.baseline()
                self.assertFalse((self.out / 'baseline.json').exists())

    def test_reader_digest_mode_and_content_changes_refused(self):
        self.digest = '0' * 64
        with self.assertRaises(capture.CaptureError): self.baseline()
        self.assertEqual([], self.calls)
        self.out = self.work / 'second offline fixture'
        self.digest = hashlib.sha256(self.reader.read_bytes()).hexdigest()
        self.reader.chmod(0o777)
        with self.assertRaises(capture.CaptureError): self.baseline()
        self.reader.chmod(0o700)
        self.out = self.work / 'third offline fixture'
        def change(label, raw):
            if label == 'image-after':
                self.reader.write_text(self.reader.read_text() + '# modified\n')
            return raw
        self.fault = change
        with self.assertRaises(capture.CaptureError): self.baseline()
        self.assertFalse((self.out / 'baseline.json').exists())

    def test_links_writable_or_oversized_private_inputs_refused(self):
        self.baseline()
        baseline = self.out / 'baseline.json'
        raw = baseline.read_bytes()
        for fault in ('symlink', 'hardlink', 'mode', 'large'):
            with self.subTest(fault=fault):
                baseline.unlink()
                target = self.work / fault
                target.write_bytes(raw); target.chmod(0o600)
                if fault == 'symlink': baseline.symlink_to(target)
                elif fault == 'hardlink': os.link(target, baseline)
                else:
                    baseline.write_bytes(raw); baseline.chmod(0o666 if fault == 'mode' else 0o600)
                    if fault == 'large': baseline.write_bytes(b' ' * (capture.LIMIT + 1))
                with self.assertRaises(capture.CaptureError): capture.finish(self.out, run=self.run_fake)
                self.assertFalse((self.out / 'failure.started').exists())

    def test_linked_directory_and_existing_directory_are_not_modified(self):
        self.out.mkdir(mode=0o700)
        keep = self.out / 'keep'; keep.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError): self.baseline()
        alias = self.work / 'alias'; alias.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(capture.CaptureError): capture.finish(alias, run=self.run_fake)
        with self.assertRaises(capture.CaptureError): capture.finish(alias / 'nested', run=self.run_fake)
        self.assertEqual([keep], list(self.out.iterdir()))

    def test_host_refusal_precedes_directory_or_command(self):
        self.host.stop()
        with mock.patch.object(capture.platform, 'system', return_value='Linux'):
            with self.assertRaises(capture.CaptureError): self.baseline()
        self.assertFalse(self.out.exists())
        self.assertEqual([], self.calls)
        self.host.start()

    def test_actual_process_failure_timeout_size_and_environment_boundaries(self):
        for mode in ('fail', 'hang', 'large'):
            with self.subTest(mode=mode):
                folder = self.work / mode; folder.mkdir(mode=0o700)
                start = time.monotonic()
                with self.assertRaises(capture.CaptureError):
                    capture.run_command((sys.executable, str(self.fake), mode, str(self.source)),
                                        folder, 'fake', time.monotonic() + (0.1 if mode == 'hang' else 3))
                self.assertLess(time.monotonic() - start, 4)
                self.assertLessEqual((folder / 'fake.stdout').stat().st_size, capture.LIMIT)
                status = json.loads((folder / 'fake.status.json').read_bytes())
                self.assertEqual(mode == 'hang', status['timed_out'])
        env_program = self.work / 'env.py'
        env_program.write_text('import json,os; print(json.dumps(dict(os.environ)))')
        folder = self.work / 'env'; folder.mkdir(mode=0o700)
        with mock.patch.dict(os.environ, {'PRIVATE_SECRET': 'PRIVATE', 'DYLD_INSERT_LIBRARIES': 'PRIVATE'}):
            data = capture.run_command((sys.executable, str(env_program)), folder, 'env', time.monotonic() + 3)
        child_env = json.loads(data)
        self.assertFalse({'PRIVATE_SECRET', 'DYLD_INSERT_LIBRARIES'} & set(child_env))
        self.assertEqual('C', child_env['LC_ALL'])

    def test_expired_budget_never_starts_a_process(self):
        with mock.patch.object(capture.subprocess, 'Popen') as popen:
            with self.assertRaises(capture.CaptureError):
                capture.run_command((str(self.reader),), self.work, 'never', time.monotonic() - 1)
            popen.assert_not_called()

    def test_baseline_changed_during_failure_capture_cannot_be_published(self):
        self.baseline()
        def change(label, raw):
            if label == 'image-after':
                path = self.out / 'baseline.json'
                path.write_bytes(path.read_bytes() + b'\n')
            return raw
        self.fault = change
        with self.assertRaises(capture.CaptureError): capture.finish(self.out, run=self.run_fake)
        self.assertTrue((self.out / 'failure.started').exists())
        self.assertFalse((self.out / 'failure.json').exists())

    def test_publication_never_exposes_a_partial_result_or_overwrites(self):
        target = self.work / 'result.json'
        with mock.patch.object(capture.os, 'link', side_effect=OSError('fixture interruption')):
            with self.assertRaises(OSError): capture.publish_json(target, {'complete': True})
        self.assertFalse(target.exists())
        self.assertEqual({'complete': True}, json.loads(target.with_name('result.json.incomplete').read_bytes()))
        other = self.work / 'other.json'
        capture.write_file(other, b'keep')
        with self.assertRaises(FileExistsError): capture.publish_json(other, {'replacement': True})
        self.assertEqual(b'keep', other.read_bytes())

    def test_handled_termination_cleans_only_the_owned_child_group(self):
        folder = self.work / 'signal'; folder.mkdir(mode=0o700)
        pidfile = self.work / 'owned-child.pid'
        sleeper = self.work / 'sleeper.py'
        sleeper.write_text('import os,pathlib,sys,time\n'
                           'pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))\n'
                           'time.sleep(10)\n')
        wrapper = self.work / 'wrapper.py'
        wrapper.write_text('import signal,sys,time\n'
                           f'sys.path.insert(0, {str(ROOT / "tools")!r})\n'
                           'import allocation_capture as c\n'
                           'from pathlib import Path\n'
                           'signal.signal(signal.SIGTERM, c.interrupted)\n'
                           'try:\n'
                           f' c.run_command(({sys.executable!r}, {str(sleeper)!r}, {str(pidfile)!r}), '
                           f'Path({str(folder)!r}), "owned", time.monotonic()+5)\n'
                           'except c.CaptureError: sys.exit(74)\n')
        child = subprocess.Popen((sys.executable, str(wrapper)), stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
        owned = None
        try:
            deadline = time.monotonic() + 3
            while not pidfile.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(pidfile.exists())
            owned = int(pidfile.read_text())
            child.send_signal(signal.SIGTERM)
            self.assertEqual(74, child.wait(timeout=3))
            with self.assertRaises(ProcessLookupError): os.kill(owned, 0)
        finally:
            if child.poll() is None:
                child.kill(); child.wait(timeout=3)
            if owned is not None:
                try: os.kill(owned, signal.SIGKILL)
                except ProcessLookupError: pass

    def test_cli_errors_do_not_disclose_private_input_and_have_no_traceback(self):
        with mock.patch.object(sys, 'argv', ['allocation_capture.py', 'failure', '--capture', str(self.out)]):
            from io import StringIO
            with mock.patch.object(sys, 'stderr', new_callable=StringIO) as stderr, \
                    mock.patch.object(capture.signal, 'signal'):
                self.assertEqual(74, capture.main())
            self.assertNotIn(str(self.out), stderr.getvalue())
            self.assertNotIn('Traceback', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
