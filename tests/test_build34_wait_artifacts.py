#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Offline refusal tests; no native artifacts, IOKit or Metal required."""
import copy
import importlib.util
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("wait_artifacts", ROOT / "tools/check_build34_wait_artifacts.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ArtifactAdmission(unittest.TestCase):
    def report(self):
        return dict(status="built-and-statically-verified-not-installed", base_commit=m.source.BASE,
                    kernel_build=34, candidate_source_sha256=m.source.CANDIDATE_SHA,
                    sdk_commit=m.source.common.SDK_PIN, recipe_sha256=m.RECIPE_SHA,
                    installed=False, loaded=False, GPU_executed=False,
                    old_admission_modified=False, hardware_acceptance=False,
                    warning_multisets_equal=True,
                    checks=[dict(name=role+"-"+suffix, returncode=0)
                            for role in m.BINARY_SHA for suffix in ("compile", "sign", "signature", "architecture")],
                    roles={role: dict(binary_sha256=binary, packaged_plist_sha256=m.PLIST_SHA,
                                      warning_multiset=m.WARNINGS.copy(),
                                      bundle_files_sha256_private={n: v["sha256"] for n, v in m.expected_files(role).items()})
                           for role, binary in m.BINARY_SHA.items()})

    def efi(self):
        before = {"unrelated/"+str(i): dict(sha256=str(i), bytes=i) for i in range(351)}
        before.update({"Microsoft/Boot/"+n: dict(sha256="external-"+n, bytes=1)
                       for n in ("BCD", "BCD.LOG", "BOOTSTAT.DAT")})
        before.update({m.ACTIVE+n: v for n, v in m.expected_files("baseline").items()})
        return before

    def test_exact_pair_is_admitted(self):
        m.validate_report(self.report())

    def test_unknown_build_and_source_recipe_SDK_refused(self):
        for key, value in (("kernel_build", 41), ("kernel_build", 42), ("base_commit", "unknown"),
                           ("candidate_source_sha256", m.source.BASE_SHA), ("recipe_sha256", "unknown"),
                           ("sdk_commit", "unknown")):
            report = self.report(); report[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                m.validate_report(report)

    def test_missing_and_wrong_typed_status_refused(self):
        for key in ("installed", "loaded", "GPU_executed", "hardware_acceptance", "old_admission_modified"):
            for value in (True, 0, None):
                report = self.report(); report[key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    m.validate_report(report)
            report = self.report(); del report[key]
            with self.assertRaises(ValueError): m.validate_report(report)

    def test_candidate_substitution_or_extra_bundle_file_refused(self):
        for role in m.BINARY_SHA:
            report = self.report(); report["roles"][role]["binary_sha256"] = "unknown"
            with self.assertRaises(ValueError): m.validate_report(report)
            report = self.report(); report["roles"][role]["bundle_files_sha256_private"]["extra"] = "extra"
            with self.assertRaises(ValueError): m.validate_report(report)

    def test_failed_missing_or_duplicate_native_checks_refused(self):
        report = self.report(); report["checks"][0]["returncode"] = 1
        with self.assertRaises(ValueError): m.validate_report(report)
        report = self.report(); report["checks"].pop()
        with self.assertRaises(ValueError): m.validate_report(report)
        report = self.report(); report["checks"].append(report["checks"][0])
        with self.assertRaises(ValueError): m.validate_report(report)

    def test_manifest_preserves_all_external_records_and_does_not_mutate_input(self):
        before = self.efi(); original = copy.deepcopy(before)
        after = m.derive_efi_manifest(before)
        self.assertEqual(before, original)
        self.assertEqual(len(after), 357)
        self.assertEqual({n for n in after if after[n] != before[n]}, {m.ACTIVE+m.EXE})
        for n in before:
            if n.startswith("Microsoft/"): self.assertEqual(after[n], before[n])

    def test_incomplete_EFI_or_unknown_control_refused(self):
        before = self.efi(); before.pop("Microsoft/Boot/BCD")
        with self.assertRaises(ValueError): m.derive_efi_manifest(before)
        before = self.efi(); before[m.ACTIVE+m.EXE]["sha256"] = "unknown"
        with self.assertRaises(ValueError): m.derive_efi_manifest(before)

    def test_already_candidate_or_extra_active_file_refused(self):
        before = m.derive_efi_manifest(self.efi())
        with self.assertRaises(ValueError): m.derive_efi_manifest(before)
        before = self.efi(); before.pop("unrelated/0"); before[m.ACTIVE+"extra"] = dict(sha256="extra", bytes=1)
        with self.assertRaises(ValueError): m.derive_efi_manifest(before)

    def test_bundle_symlink_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/"file").write_text("content"); (root/"link").symlink_to(root/"file")
            with self.assertRaises(ValueError): m.manifest(root)


if __name__ == "__main__":
    unittest.main()
