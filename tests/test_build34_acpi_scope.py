#!/usr/bin/env python3
"""CPU-only checks for exact S5 EFI expectation derivation. No deployment."""

import copy
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


SPEC = importlib.util.spec_from_file_location(
    "build34_acpi_scope", Path(__file__).resolve().parents[1] / "tools/build34_acpi_scope.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def record(data):
    return {"sha256": m.digest_bytes(data), "bytes": len(data)}


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.before = {m.CONFIG: record(b"old config"),
                       "Microsoft/Boot/bootmgfw.efi": record(b"Windows fixture"),
                       "OC/Kexts/PhxBringup.kext/Contents/MacOS/PhxBringup": record(b"build34 fixture")}
        self.contract = {"EFI_baseline": copy.deepcopy(self.before),
                         "protected": {"plugin": "untouched"}, "source_commit": "fixture"}
        self.stage = {"EFI_baseline": dict(self.before, **{"OC/Recovery/backup": record(b"backup")}),
                      "recovery_files": {"backup": record(b"backup")}}
        self.scope = {"kind": m.KIND,
                      "contract_before_sha256": "1" * 64,
                      "stage_before_sha256": "2" * 64,
                      "contract_manifest_before_sha256": m.manifest_digest(self.before),
                      "stage_manifest_before_sha256": m.manifest_digest(self.stage["EFI_baseline"]),
                      "config_before": self.before[m.CONFIG],
                      "config_after": record(b"new config"), "aml_after": record(b"own AML")}

    def derive(self):
        return m.derive_manifest(self.before, self.scope,
                                 self.scope["contract_manifest_before_sha256"])

    def test_only_configuration_and_one_table_differ(self):
        old = copy.deepcopy(self.before)
        after = self.derive()
        self.assertEqual(set(after) - set(old), {m.AML})
        self.assertEqual({k for k in old if old[k] != after[k]}, {m.CONFIG})
        self.assertEqual(self.before, old)

    def test_windows_and_build34_records_retained(self):
        after = self.derive()
        for key in self.before.keys() - {m.CONFIG}:
            self.assertEqual(after[key], self.before[key])

    def test_original_rollback_state_keeps_exact_original_manifest(self):
        after = m.derive_manifest(self.before, self.scope,
                                  self.scope["contract_manifest_before_sha256"], "original")
        self.assertEqual(after, self.before)
        self.assertEqual(m.select_state(after, self.scope), "original")

    def test_inactive_table_stage_preserves_configuration(self):
        after = m.derive_manifest(self.before, self.scope,
                                  self.scope["contract_manifest_before_sha256"], "staged")
        self.assertEqual(after[m.CONFIG], self.before[m.CONFIG])
        self.assertEqual(m.select_state(after, self.scope), "staged")

    def test_active_candidate_selected(self):
        self.assertEqual(m.select_state(self.derive(), self.scope), "candidate")

    def test_enabled_configuration_without_table_refused(self):
        after = self.derive()
        del after[m.AML]
        with self.assertRaisesRegex(ValueError, "unrecognized"):
            m.select_state(after, self.scope)

    def test_corrupt_table_and_configuration_refused(self):
        for key in [m.CONFIG, m.AML]:
            after = self.derive()
            after[key] = record(b"corrupted")
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.select_state(after, self.scope)

    def test_unknown_state_refused(self):
        with self.assertRaisesRegex(ValueError, "wrong S5 state"):
            m.derive_manifest(self.before, self.scope,
                              self.scope["contract_manifest_before_sha256"], "skip checks")

    def test_unrelated_baseline_drift_refused(self):
        self.before["unrelated"] = record(b"extra")
        with self.assertRaisesRegex(ValueError, "historical EFI"):
            self.derive()

    def test_configuration_baseline_mismatch_refused(self):
        self.scope["config_before"] = record(b"wrong old config")
        with self.assertRaisesRegex(ValueError, "configuration baseline"):
            self.derive()

    def test_preexisting_table_refused(self):
        self.before[m.AML] = record(b"preexisting")
        self.scope["contract_manifest_before_sha256"] = m.manifest_digest(self.before)
        with self.assertRaisesRegex(ValueError, "already present"):
            self.derive()

    def test_extra_scope_path_not_accepted(self):
        self.scope["additional_allowed_path"] = "OC/Kexts/Other.kext"
        with self.assertRaisesRegex(ValueError, "unexpected S5 scope"):
            self.derive()

    def test_invalid_or_extra_record_fields_refused(self):
        for value in [dict(self.scope["aml_after"], extra=True),
                      {"sha256": "bad", "bytes": 1},
                      {"sha256": "a" * 64, "bytes": True}]:
            with self.subTest(value=value):
                self.scope["aml_after"] = value
                with self.assertRaises(ValueError):
                    self.derive()

    def test_unchanged_configuration_refused(self):
        self.scope["config_after"] = copy.deepcopy(self.scope["config_before"])
        with self.assertRaisesRegex(ValueError, "actually change"):
            self.derive()

    def test_other_contract_fields_and_original_preserved(self):
        before = copy.deepcopy(self.contract)
        after = m.derive_record(self.contract, self.scope, "contract")
        self.assertEqual(after["protected"], before["protected"])
        self.assertEqual(after["source_commit"], before["source_commit"])
        after["protected"]["plugin"] = "mutated derived copy"
        self.assertEqual(self.contract, before)

    def test_recovery_backup_manifest_preserved(self):
        after = m.derive_record(self.stage, self.scope, "stage")
        self.assertEqual(after["recovery_files"], self.stage["recovery_files"])
        self.assertNotIn(m.AML, self.stage["EFI_baseline"])

    def route(self, directory):
        d = Path(directory)
        for name, obj, key in [("contract-private.json", self.contract, "contract_before_sha256"),
                               ("stage-private.json", self.stage, "stage_before_sha256")]:
            data = json.dumps(obj).encode()
            (d / name).write_bytes(data)
            self.scope[key] = m.digest_bytes(data)
        return SimpleNamespace(D=d, static=lambda: copy.deepcopy(self.contract),
                               read=lambda name: json.loads((d / name).read_text()))

    def test_route_uses_new_expectations_without_changing_old_files(self):
        with tempfile.TemporaryDirectory() as d:
            route = self.route(d)
            before = {p.name: p.read_bytes() for p in Path(d).iterdir()}
            m.bind_route(route, self.scope)
            self.assertIn(m.AML, route.static()["EFI_baseline"])
            self.assertIn(m.AML, route.read("stage-private.json")["EFI_baseline"])
            self.assertNotIn(m.AML, route.read("contract-private.json")["EFI_baseline"])
            self.assertEqual(before, {p.name: p.read_bytes() for p in Path(d).iterdir()})

    def test_changed_historical_input_refused_before_binding(self):
        with tempfile.TemporaryDirectory() as d:
            route = self.route(d)
            old_static, old_read = route.static, route.read
            (Path(d) / "stage-private.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "historical input changed"):
                m.bind_route(route, self.scope)
            self.assertIs(route.static, old_static)
            self.assertIs(route.read, old_read)

    def test_caller_scope_mutation_does_not_change_bound_policy(self):
        with tempfile.TemporaryDirectory() as d:
            route = self.route(d)
            m.bind_route(route, self.scope)
            expected = route.static()
            self.scope["aml_after"] = record(b"different AML")
            self.assertEqual(route.static(), expected)

    def test_duplicate_binding_refused(self):
        with tempfile.TemporaryDirectory() as d:
            route = self.route(d)
            m.bind_route(route, self.scope)
            with self.assertRaisesRegex(ValueError, "already bound"):
                m.bind_route(route, self.scope)


if __name__ == "__main__":
    unittest.main()
