#!/usr/bin/env python3
"""CPU-only fixtures for the isolated kernel delta and retained recovery."""
import copy
from contextlib import contextmanager
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    "R1b_resume_CPU", Path(__file__).resolve().parents[1] / "tools/build34_r1b_resume_host.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    original = {m.acpi.CONFIG: {"sha256": "old", "bytes": 10},
                m.KERNEL: {"sha256": m.R1A_BINARY, "bytes": 100}, "Microsoft/file": "pinned"}
    retained = copy.deepcopy(original)
    retained[m.acpi.CONFIG] = {"sha256": "configured", "bytes": 20}
    retained[m.acpi.AML] = {"sha256": m.acpi.AML_SHA256, "bytes": 172}
    after = copy.deepcopy(retained)
    after[m.KERNEL] = {"sha256": m.R1B_BINARY, "bytes": 120}
    before_bundle = {m.EXECUTABLE: retained[m.KERNEL], "Info.plist": "unchanged"}
    after_bundle = {m.EXECUTABLE: after[m.KERNEL], "Info.plist": "unchanged"}
    return {"EFI_accepted_private": original, "EFI_after_private": after,
        "R1b_baseline_EFI_private": retained, "kernel_after": before_bundle,
        "R1b_kernel_files_private": after_bundle,
        "kernel_after_uuid_private": "R1a-image", "R1b_image_uuid_private": "R1b-image",
        "sealed": {"ACPI-config-before.plist": "old", "ACPI-config-after.plist": "configured",
                   "SSDT-BFCOPY.aml": m.acpi.AML_SHA256,
                   "R1a-kernel.bin": m.R1A_BINARY, "R1b-kernel.bin": m.R1B_BINARY}}


class DeltaTests(unittest.TestCase):
    def test_exact_kernel_only_and_historical_AML_allowance(self):
        c = fixture()
        before = copy.deepcopy(c)
        self.assertEqual(m.kernel_states(c), (c["R1b_baseline_EFI_private"], c["EFI_after_private"]))
        self.assertEqual(c, before)

    def test_ACPI_config_table_or_Microsoft_delta_refused(self):
        for name in (m.acpi.CONFIG, m.acpi.AML, "Microsoft/file"):
            c = fixture()
            c["EFI_after_private"][name] = "drift"
            with self.subTest(name=name), self.assertRaises(AssertionError):
                m.kernel_states(c)

    def test_extra_file_and_unsigned_metadata_change_refused(self):
        c = fixture()
        c["EFI_after_private"]["other"] = "unknown"
        with self.assertRaises(AssertionError):
            m.kernel_states(c)
        c = fixture()
        c["R1b_kernel_files_private"]["Info.plist"] = "changed"
        with self.assertRaises(AssertionError):
            m.kernel_states(c)

    def test_unknown_kernel_or_backup_pin_refused(self):
        for key in ("R1a-kernel.bin", "R1b-kernel.bin"):
            c = fixture()
            c["sealed"][key] = "unknown"
            with self.subTest(key=key), self.assertRaises(AssertionError):
                m.kernel_states(c)

    def test_only_contract_image_identity_is_derived(self):
        c = fixture()
        record = {"candidate_files": c["kernel_after"], "candidate_binary_sha256": m.R1A_BINARY,
                  "candidate_image_uuid": "R1a-image", "protected": {"accelerator": "VBL"},
                  "EFI_baseline": c["R1b_baseline_EFI_private"], "ABI": "build34"}
        original = copy.deepcopy(record)
        out = m.derive_kernel(record, c, "contract")
        self.assertEqual(record, original)
        self.assertEqual(out["candidate_files"], c["R1b_kernel_files_private"])
        self.assertEqual(out["candidate_binary_sha256"], m.R1B_BINARY)
        self.assertEqual(out["candidate_image_uuid"], "R1b-image")
        for key in ("protected", "EFI_baseline", "ABI"):
            self.assertEqual(out[key], original[key])
        self.assertEqual(m.derive_kernel(record, c, "stage"), original)

    def test_derivation_refuses_unknown_input_image(self):
        c = fixture()
        with self.assertRaises(AssertionError):
            m.derive_kernel({"candidate_files": {}}, c, "contract")

    def test_original_hosts_still_reject_R1b_source(self):
        for cls in (m.base.Host, m.acpi.vbl.VBLHost, m.acpi.ACPIHost):
            h = cls.__new__(cls)
            with self.subTest(host=cls.__name__), self.assertRaises(AssertionError):
                h.validate_kernel_contract({"kernel_source_checkpoint": m.R1B_SOURCE})

    def test_pre_restart_checks_use_loaded_identity_and_preserve_disk_contract(self):
        c = fixture()
        disk = {"candidate_image_uuid": "R1b-image", "candidate_binary_sha256": m.R1B_BINARY,
                "candidate_files": c["R1b_kernel_files_private"], "VBL": "retained"}
        frozen = copy.deepcopy(disk)
        live = m.pre_restart_live_contract(disk, c)
        self.assertEqual(live["candidate_image_uuid"], "R1a-image")
        self.assertEqual(disk, frozen)
        live["candidate_image_uuid"] = "R1b-image"
        self.assertEqual(live, frozen)

    def test_pre_restart_checks_refuse_unexpected_candidate(self):
        c = fixture()
        for identity, digest in [("unknown", m.R1B_BINARY), ("R1b-image", "unknown")]:
            with self.subTest(identity=identity, digest=digest), self.assertRaises(AssertionError):
                m.pre_restart_live_contract({"candidate_image_uuid": identity,
                                            "candidate_binary_sha256": digest}, c)

    def test_new_contract_requires_R1b_source_and_R1a_baseline(self):
        h = m.R1bHost.__new__(m.R1bHost)
        good = {"kernel_source_checkpoint": m.R1B_SOURCE,
                "R1b_baseline_kernel_source": m.base.R1A_SOURCE,
                "R1b_owner_authorized_sequential_trial": True}
        h.validate_kernel_contract(good)
        for key in good:
            bad = dict(good, **{key: "unknown"})
            with self.subTest(key=key), self.assertRaises(AssertionError):
                h.validate_kernel_contract(bad)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.h = m.R1bHost.__new__(m.R1bHost)
        self.h.baseline = SimpleNamespace(acpi_check=Mock(return_value={
            "exact_candidate_SSDT": True, "exact_DSDT_method_body_and_callsite": True}))

    def test_preparation_and_recovery_require_retained_optimized_ACPI(self):
        self.assertTrue(self.h.acpi_check()["exact_candidate_SSDT"])
        self.assertTrue(self.h.acpi_check(allow_recovery=True)["exact_candidate_SSDT"])
        self.assertEqual(self.h.baseline.acpi_check.call_count, 2)
        self.h.baseline.acpi_check.side_effect = AssertionError("original AML")
        with self.assertRaises(AssertionError):
            self.h.acpi_check(allow_recovery=True)

    def test_unknown_restore_input_prevents_any_write(self):
        self.h.check_restore_inputs = Mock(side_effect=AssertionError("unknown EFI"))
        with patch.object(m, "load") as loader, self.assertRaises(AssertionError):
            self.h.restore()
        loader.assert_not_called()

    def test_pressure_job_retirement_preserves_unknown_replacement(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe.plist"
            path.write_bytes(b"unknown replacement")
            self.h.config = {"R1b_pressure_observer_job": str(path),
                             "R1b_pressure_observer_sha256": "expected"}
            with patch.object(m.base, "secure"), self.assertRaises(AssertionError):
                self.h.retire_pressure_observer()
            self.assertEqual(path.read_bytes(), b"unknown replacement")

    def test_pressure_job_retirement_removes_only_exact_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "probe.plist"
            path.write_bytes(b"exact job")
            self.h.config = {"R1b_pressure_observer_job": str(path),
                             "R1b_pressure_observer_sha256": m.base.sha(path)}
            with patch.object(m.base, "secure"):
                self.h.retire_pressure_observer()
                self.h.retire_pressure_observer()
            self.assertFalse(path.exists())

    def test_restore_writes_only_kernel_and_restores_jobs(self):
        c = fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "R1a-kernel.bin").write_bytes(b"accepted-kernel")
            self.h.scope = root
            self.h.check_restore_inputs = Mock(return_value=c)
            current = copy.deepcopy(c["EFI_after_private"])
            @contextmanager
            def mounted(*args, **kwargs):
                yield root
            def atomic(path, data, allowed):
                self.assertEqual(path, root / m.KERNEL)
                self.assertEqual(data, b"accepted-kernel")
                self.assertEqual(allowed, [m.R1A_BINARY, m.R1B_BINARY])
                current[m.KERNEL] = copy.deepcopy(c["R1b_baseline_EFI_private"][m.KERNEL])
            route = SimpleNamespace(efi=mounted, static=lambda: {}, files=lambda unused: current)
            self.h.readonly = SimpleNamespace(OLD=root, atomic_file=Mock(side_effect=atomic))
            self.h.restore_jobs = Mock()
            self.h.retire_watcher = Mock()
            self.h.retire_pressure_observer = Mock()
            with patch.object(m, "load", return_value=route), \
                    patch.object(m.subprocess, "run"), \
                    patch.object(m.Path, "exists", return_value=False):
                self.h.restore()
            self.h.readonly.atomic_file.assert_called_once()
            self.h.restore_jobs.assert_called_once()
            self.h.retire_watcher.assert_called_once()
            self.h.retire_pressure_observer.assert_called_once()
            self.assertEqual(current, c["R1b_baseline_EFI_private"])


if __name__ == "__main__":
    unittest.main()
