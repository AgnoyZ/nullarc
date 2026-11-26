#!/usr/bin/env python3
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import build34_dcn_firmware_observation_stage as observation
import build34_dcn_firmware_observer_candidate as candidate


class DcnFirmwareObserverCandidateTests(unittest.TestCase):
    def mode_report(self, created_ns=None):
        return dict(status='passed-native-2x-scanout-mode-preflight',
            gate_source_sha256=candidate.common.file_sha(candidate.SCANOUT_GATE),
            gate_output_sha256=candidate.common.sha(candidate.SCANOUT_OUTPUT.encode()),
            os_version='26.7.2', os_build='25G332',
            created_unix_ns=time.time_ns() if created_ns is None else created_ns,
            logical_width=1280, logical_height=800, backing_width=2560,
            backing_height=1600, refresh_hz=120.0, appkit_backing_scale=2.0)

    def write_mode_report(self, path, data):
        path.write_text(json.dumps(data, sort_keys=True))
        path.chmod(0o600)

    def test_native_2x_report_requires_exact_fresh_gate_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / 'mode-private.json'
            data = self.mode_report()
            self.write_mode_report(report, data)
            result = candidate.validate_scanout_mode_report(
                report, '26.7.2', '25G332', now_ns=data['created_unix_ns'] + 1_000_000_000)
            self.assertEqual(result['created_unix_ns'], data['created_unix_ns'])

    def test_native_2x_report_rejects_stale_mode_or_wrong_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / 'mode-private.json'
            stale = self.mode_report()
            self.write_mode_report(report, stale)
            with self.assertRaisesRegex(ValueError, 'stale'):
                candidate.validate_scanout_mode_report(
                    report, '26.7.2', '25G332',
                    now_ns=stale['created_unix_ns'] + candidate.SCANOUT_MAX_AGE_NS + 1)

            changed_gate = self.mode_report()
            changed_gate['gate_source_sha256'] = '0' * 64
            self.write_mode_report(report, changed_gate)
            with self.assertRaisesRegex(ValueError, 'current gate and OS'):
                candidate.validate_scanout_mode_report(
                    report, '26.7.2', '25G332', now_ns=changed_gate['created_unix_ns'])

            link = Path(temporary) / 'linked-private.json'
            link.symlink_to(report)
            with self.assertRaises(OSError):
                candidate.validate_scanout_mode_report(
                    link, '26.7.2', '25G332', now_ns=changed_gate['created_unix_ns'])

    def make_bundle(self, root, executable_bytes):
        bundle = root / candidate.BUNDLE
        executable = bundle / candidate.EXECUTABLE
        executable.parent.mkdir(parents=True)
        (bundle / 'Contents/Info.plist').write_bytes(b'plist')
        executable.write_bytes(executable_bytes)
        return bundle

    def test_temporary_bundle_restores_if_candidate_rename_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = self.make_bundle(root / 'installed', b'control')
            candidate_bundle = self.make_bundle(root / 'candidate', b'observer')
            backup = installed.with_name('PhxAccel.kext.restore')
            staged = installed.with_name('PhxAccel.kext.next')
            baseline_manifest = candidate.common.tree_files(installed)
            candidate_manifest = candidate.common.tree_files(candidate_bundle)
            real_rename = os.rename
            rename_count = 0

            def fail_candidate_rename(source, destination):
                nonlocal rename_count
                rename_count += 1
                if rename_count == 2:
                    raise OSError('injected second-rename failure')
                return real_rename(source, destination)

            with patch.object(candidate, 'apply_bundle_metadata'), \
                    patch.object(candidate.os, 'rename', side_effect=fail_candidate_rename), \
                    patch.object(candidate.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                with self.assertRaisesRegex(OSError, 'second-rename failure'):
                    candidate.link_with_temporary_standard_bundle(
                        installed, candidate_bundle, backup, staged,
                        baseline_manifest, candidate_manifest,
                        lambda: self.fail('AuxKC linker must not run after failed rename'))

            self.assertEqual(candidate.common.tree_files(installed), baseline_manifest)
            self.assertFalse(backup.exists())
            self.assertFalse(staged.exists())

    def test_temporary_bundle_restores_when_linker_raises(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = self.make_bundle(root / 'installed', b'control')
            candidate_bundle = self.make_bundle(root / 'candidate', b'observer')
            backup = installed.with_name('PhxAccel.kext.restore')
            staged = installed.with_name('PhxAccel.kext.next')
            baseline_manifest = candidate.common.tree_files(installed)
            candidate_manifest = candidate.common.tree_files(candidate_bundle)

            def fail_link():
                raise RuntimeError('injected linker failure')

            with patch.object(candidate, 'apply_bundle_metadata'), \
                    patch.object(candidate.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)):
                with self.assertRaisesRegex(RuntimeError, 'injected linker failure'):
                    candidate.link_with_temporary_standard_bundle(
                        installed, candidate_bundle, backup, staged,
                        baseline_manifest, candidate_manifest,
                        fail_link)

            self.assertEqual(candidate.common.tree_files(installed), baseline_manifest)
            self.assertFalse(backup.exists())
            self.assertFalse(staged.exists())

    def test_source_pair_changes_only_pinned_framebuffer_overlay(self):
        baseline, observer = candidate.read_sources()
        self.assertEqual(set(baseline), set(observer))
        self.assertEqual({name for name in baseline if baseline[name] != observer[name]},
                         {candidate.FRAMEBUFFER})
        self.assertEqual(observer[candidate.FRAMEBUFFER], observation.stage(baseline[candidate.FRAMEBUFFER]).encode())

    def test_bundle_pair_accepts_only_executable_delta(self):
        control = {'Contents/Info.plist': 'a', candidate.EXECUTABLE: 'b'}
        observer = {'Contents/Info.plist': 'a', candidate.EXECUTABLE: 'c'}
        candidate.validate_bundle_pair(control, observer)
        changed = dict(observer, **{'Contents/Info.plist': 'changed'})
        with self.assertRaisesRegex(ValueError, 'only at its executable'):
            candidate.validate_bundle_pair(control, changed)

    def test_bundle_pair_rejects_added_or_missing_files(self):
        control = {'Contents/Info.plist': 'a', candidate.EXECUTABLE: 'b'}
        observer = {'Contents/Info.plist': 'a', candidate.EXECUTABLE: 'c', 'extra': 'd'}
        with self.assertRaisesRegex(ValueError, 'only at its executable'):
            candidate.validate_bundle_pair(control, observer)


if __name__ == '__main__':
    unittest.main()
