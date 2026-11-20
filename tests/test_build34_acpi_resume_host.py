#!/usr/bin/env python3
"""CPU fixtures only; no local firmware, EFI, driver, launchd or power access."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    "ACPI_resume_CPU", Path(__file__).resolve().parents[1] / "tools/build34_acpi_resume_host.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.before = {m.CONFIG: {"sha256": "before", "bytes": 10}, "kernel": "R1a", "Microsoft/file": "keep"}
        self.after = copy.deepcopy(self.before)
        self.after[m.CONFIG] = {"sha256": "after", "bytes": 20}
        self.after[m.AML] = {"sha256": m.AML_SHA256, "bytes": 172}
        self.config = {"EFI_accepted_private": self.before, "EFI_after_private": self.after,
                       "sealed": {"ACPI-config-before.plist": "before",
                                  "ACPI-config-after.plist": "after", "SSDT-BFCOPY.aml": m.AML_SHA256}}

    def test_only_original_staged_and_candidate_manifests_are_derived(self):
        original = copy.deepcopy(self.config)
        states = m.efi_states(self.config)
        self.assertEqual(states["original"], self.before)
        self.assertEqual(states["candidate"], self.after)
        self.assertEqual(states["staged"][m.CONFIG], self.before[m.CONFIG])
        self.assertEqual(states["staged"][m.AML], self.after[m.AML])
        self.assertEqual(self.config, original)

    def test_kernel_or_Windows_delta_is_refused(self):
        for name in ("kernel", "Microsoft/file"):
            with self.subTest(name=name):
                c = copy.deepcopy(self.config)
                c["EFI_after_private"][name] = "changed"
                with self.assertRaises(AssertionError):
                    m.efi_states(c)

    def test_unknown_table_or_additional_file_is_refused(self):
        self.after["other.aml"] = "unexpected"
        with self.assertRaises(AssertionError):
            m.efi_states(self.config)

    def test_wrong_AML_hash_or_length_is_refused(self):
        for key, value in (("sha256", "unknown"), ("bytes", 171)):
            with self.subTest(key=key):
                c = copy.deepcopy(self.config)
                c["EFI_after_private"][m.AML][key] = value
                with self.assertRaises(AssertionError):
                    m.efi_states(c)

    def test_backup_or_candidate_not_sealed_to_manifest_is_refused(self):
        self.config["sealed"]["ACPI-config-before.plist"] = "other"
        with self.assertRaises(AssertionError):
            m.efi_states(self.config)

    def test_original_R1a_host_still_refuses_ACPI_delta(self):
        h = m.base.Host.__new__(m.base.Host)
        with self.assertRaises(AssertionError):
            h.validate_efi_contract(self.config)

    def test_original_VBL_host_still_refuses_ACPI_enabled(self):
        h = m.vbl.VBLHost.__new__(m.vbl.VBLHost)
        with self.assertRaises(AssertionError):
            h.validate_acpi_contract({"ACPI_candidate_enabled": True})

    def test_derive_changes_only_config_and_table_in_both_record_kinds(self):
        self.config["ACPI_input_manifests_private"] = {kind: self.before for kind in ("contract", "stage")}
        for kind in ("contract", "stage"):
            record = {"EFI_baseline": self.before, "kernel": "R1a", "plugin": "accepted", "limits": [45, 150, 300]}
            original = copy.deepcopy(record)
            result = m.derive_acpi(record, self.config, kind)
            self.assertEqual(record, original)
            self.assertEqual(result["EFI_baseline"], self.after)
            result["EFI_baseline"] = self.before
            self.assertEqual(result, record)

    def test_derive_refuses_drifted_input_manifest(self):
        self.config["ACPI_input_manifests_private"] = {"contract": self.before}
        with self.assertRaises(AssertionError):
            m.derive_acpi({"EFI_baseline": {m.CONFIG: "unknown"}}, self.config, "contract")


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.before = {"ACPI": {"Add": [], "Patch": [], "Delete": [], "Quirks": {}},
                       "NVRAM": {"unchanged": b"flags"}, "Kernel": {"unchanged": True}}
        self.after = copy.deepcopy(self.before)
        self.after["ACPI"]["Add"].append({"Enabled": True, "Path": "SSDT-BFCOPY.aml"})
        self.after["ACPI"]["Patch"].append({"Enabled": True, "TableSignature": b"DSDT",
            "Count": 1, "Skip": 0, "Find": b"original", "Replace": b"renamed"})

    def validate(self):
        return m.validate_config(plistlib.dumps(self.before), plistlib.dumps(self.after))

    def test_exact_append_preserves_other_settings(self):
        self.assertEqual(self.validate(), self.after["ACPI"]["Patch"][-1])

    def test_NVRAM_or_kernel_change_is_refused(self):
        for key in ("NVRAM", "Kernel"):
            c = copy.deepcopy(self.after)
            c[key]["extra"] = True
            with self.assertRaises(AssertionError):
                m.validate_config(plistlib.dumps(self.before), plistlib.dumps(c))

    def test_disabled_wrong_table_or_unbounded_match_is_refused(self):
        for key, value in (("Enabled", False), ("Count", 0), ("Skip", 1), ("TableSignature", b"SSDT")):
            c = copy.deepcopy(self.after)
            c["ACPI"]["Patch"][-1][key] = value
            with self.assertRaises(AssertionError):
                m.validate_config(plistlib.dumps(self.before), plistlib.dumps(c))

    def test_editing_existing_entry_is_refused(self):
        self.before["ACPI"]["Add"].append({"Enabled": True, "Path": "existing.aml"})
        self.after["ACPI"]["Add"].insert(0, {"Enabled": False, "Path": "existing.aml"})
        with self.assertRaises(AssertionError):
            self.validate()


class LoadedStateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.h = m.ACPIHost.__new__(m.ACPIHost)
        self.h.scope = self.root
        self.h.config = {"prepared_boot": "preparation"}
        self.h.boot = lambda: "new-boot"
        self.original = {"DSDT": b"original", "FACP": b"fadt", "RSDT": b"rsdt", "SSDT": b"other"}
        (self.root / "tables-before-private.plist").write_bytes(plistlib.dumps(self.original))
        (self.root / "SSDT-BFCOPY.aml").write_bytes(b"candidate")
        (self.root / "DSDT-preview-private.aml").write_bytes(b"renamed")
        (self.root / "acpi-contract-private.json").write_text(json.dumps({"withdrawn_SSDT_sha256": "withdrawn"}))
        self.reader = SimpleNamespace(acpi_tables=Mock(return_value=self.original))
        def candidate_check(tables, before, preview, candidate, withdrawn):
            assert tables["DSDT"] == preview and candidate in tables.values()
            return {"candidate": True}
        self.check = SimpleNamespace(facp_semantics=lambda b: b, header=lambda b: b,
            digest=lambda b: hashlib.sha256(b).hexdigest(), validate=Mock(side_effect=candidate_check))
        self.loader = patch.object(m, "load", side_effect=[self.reader, self.check])

    def test_new_boot_original_ACPI_is_not_candidate_acceptance(self):
        with self.loader, self.assertRaises(AssertionError):
            self.h.acpi_check()
        self.check.validate.assert_called_once()

    def test_installation_boot_accepts_only_original_ACPI(self):
        self.h.boot = lambda: "preparation"
        with self.loader:
            self.assertEqual(self.h.acpi_check(), {"loaded_candidate_ACPI": False})
        self.check.validate.assert_not_called()

    def test_recovery_may_validate_original_without_claiming_candidate_loading(self):
        with self.loader:
            self.assertEqual(self.h.acpi_check(allow_recovery=True), {"loaded_candidate_ACPI": False})

    def test_recovery_rejects_unrelated_loaded_table_drift(self):
        self.reader.acpi_tables.return_value = dict(self.original, SSDT=b"unknown")
        with self.loader, self.assertRaises(AssertionError):
            self.h.acpi_check(allow_recovery=True)

    def test_exact_candidate_is_checked_on_new_boot_and_during_recovery(self):
        self.reader.acpi_tables.return_value = dict(self.original, DSDT=b"renamed", added=b"candidate")
        with self.loader:
            self.assertEqual(self.h.acpi_check(), {"candidate": True})
        self.check.validate.assert_called_once()

    def test_unknown_restore_input_prevents_any_mutation(self):
        self.h.check_restore_inputs = Mock(side_effect=AssertionError("unknown file"))
        with patch.object(m.vbl, "atomic_image") as image, \
                patch.object(m, "load") as route, self.assertRaises(AssertionError):
            self.h.restore()
        image.assert_not_called()
        route.assert_not_called()


if __name__ == "__main__":
    unittest.main()
