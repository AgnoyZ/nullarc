"""Synthetic private observation files only; no GPU, subprocess or network backend."""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import gc_state_compare as compare


def observation(stage):
    values = {name: 0 for name, _ in compare.REGISTERS}
    values.update(PSP_INITIALIZATION_STATUS=0x80000000, RCC_CONFIG_MEMSIZE=512)
    return {"schema": 1, "observation_only": True,
            "phase": "configured" if stage == "baseline" else "tmr-ready", "GPU_register_writes": 0,
            "registers": [{"name": name, "index": index, "value": values[name]}
                          for name, index in compare.REGISTERS]}


class GCStateComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="gc-files-only-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self, count=4, change=None):
        manifest = {"schema": 1, "observations": []}
        for stage in compare.STAGES[:count]:
            data = observation(stage)
            if change:
                change(stage, data)
            name = stage + ".partial"
            raw = json.dumps(data).encode()
            (self.root / name).write_bytes(raw)
            manifest["observations"].append({"stage": stage, "file": name,
                                             "sha256": hashlib.sha256(raw).hexdigest(), "exit_status": 0})
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest))
        return path, manifest

    def test_every_phase_prefix_and_zero_GC_are_observations_without_readiness(self):
        for count in range(1, 5):
            with self.subTest(count=count):
                path, _ = self.fixture(count)
                result = compare.compare(path)
                self.assertEqual(list(compare.STAGES[:count]), [p["stage"] for p in result["phases"]])
                self.assertEqual(count == 4, result["complete_four_phase_input"])
                for key in ("GPU_access_performed", "hardware_readiness_proven", "physical_cause_established",
                            "boot_and_capture_provenance_verified"):
                    self.assertIs(result[key], False)
                self.assertIs(result["phase_order_and_exit_status_are_caller_asserted"], True)
                self.assertTrue(all(not p["changes_from_previous"] for p in result["phases"]))

    def test_changes_and_completion_bits_do_not_establish_readiness(self):
        def change(stage, data):
            if stage == "power":
                for row in data["registers"]:
                    if row["name"] == "GRBM_CNTL":
                        row["value"] = 0x100FF
                    if row["name"] == "RLC_RLCS_BOOTLOAD_STATUS_GC_11_0_1":
                        row["value"] = 0x80000000
        path, _ = self.fixture(change=change)
        report = compare.compare(path)
        power = report["phases"][-1]
        self.assertIs(power["CP_RLC_completion_bits_observed"], True)
        self.assertEqual(["RLC_RLCS_BOOTLOAD_STATUS_GC_11_0_1", "GRBM_CNTL"],
                         [v["name"] for v in power["changes_from_previous"]])
        self.assertEqual({"name": "GRBM_CNTL", "before": 0, "after": 0x100FF, "xor": 0x100FF},
                         power["changes_from_previous"][-1])
        self.assertEqual({"fields": {"READ_TIMEOUT": 255}, "undecoded_bits": 0x10000},
                         power["decoded"]["GRBM_CNTL"])
        self.assertIs(report["hardware_readiness_proven"], False)

    def test_one_hot_field_decode_and_undecoded_bits_preserved(self):
        values = {name: 0 for name, _ in compare.REGISTERS}
        for register, fields in compare.FIELDS.items():
            known = 0
            for field, (shift, mask) in fields.items():
                with self.subTest(register=register, field=field):
                    values[register] = mask
                    decoded = compare.decode_fields(values)[register]
                    self.assertEqual(mask >> shift, decoded["fields"][field])
                    self.assertTrue(all(v == 0 for k, v in decoded["fields"].items() if k != field))
                    self.assertEqual(0, decoded["undecoded_bits"])
                    known |= mask
            values[register] = ~known & 0xFFFFFFFF
            decoded = compare.decode_fields(values)[register]
            self.assertEqual(values[register], decoded["undecoded_bits"])
            self.assertTrue(all(v == 0 for v in decoded["fields"].values()))
            values[register] = 0

    def test_each_register_rejects_wrong_identity_shape_order_and_values(self):
        for ordinal in range(19):
            for key, value in (("name", "other"), ("index", -1), ("index", True), ("value", -1),
                               ("value", True), ("value", 0xFFFFFFFF), ("value", 1 << 32), ("extra", 1)):
                with self.subTest(ordinal=ordinal, key=key, value=value):
                    data = observation("baseline")
                    data["registers"][ordinal][key] = value
                    with self.assertRaises(compare.ObservationError):
                        compare.validate_observation(data, "baseline")
        data = observation("baseline")
        data["registers"][2:4] = reversed(data["registers"][2:4])
        with self.assertRaises(compare.ObservationError):
            compare.validate_observation(data, "baseline")

    def test_observation_schema_modes_controls_and_cross_phase_size(self):
        for key, value in (("schema", True), ("schema", 2), ("observation_only", 1), ("phase", "tmr-ready"),
                           ("GPU_register_writes", False), ("GPU_register_writes", 1), ("registers", []),
                           ("extra", "ignored?")):
            with self.subTest(key=key, value=value):
                data = observation("baseline")
                data[key] = value
                with self.assertRaises(compare.ObservationError):
                    compare.validate_observation(data, "baseline")
        for ordinal, value in ((0, 0), (1, 0), (1, 127), (1, (1 << 20) + 1)):
            data = observation("baseline")
            data["registers"][ordinal]["value"] = value
            with self.assertRaises(compare.ObservationError):
                compare.validate_observation(data, "baseline")
        def changed_size(stage, data):
            if stage == "psp":
                data["registers"][1]["value"] = 1024
        path, _ = self.fixture(change=changed_size)
        with self.assertRaisesRegex(compare.ObservationError, "changed between phases"):
            compare.compare(path)

    def test_manifest_requires_order_unique_files_zero_exit_and_exact_bytes(self):
        path, original = self.fixture()
        changes = [("stage", "power"), ("exit_status", 75), ("exit_status", False),
                   ("file", "../baseline.partial"), ("file", "/baseline.partial"),
                   ("file", "nested/baseline.partial"), ("file", "baseline.json"),
                   ("sha256", "0" * 64), ("sha256", "bad"), ("extra", 1)]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                manifest = copy.deepcopy(original)
                manifest["observations"][0][key] = value
                path.write_text(json.dumps(manifest))
                with self.assertRaises(compare.ObservationError):
                    compare.compare(path)
        for phases in ([], original["observations"][1:], list(reversed(original["observations"])),
                       original["observations"] + original["observations"][:1]):
            path.write_text(json.dumps({"schema": 1, "observations": phases}))
            with self.assertRaises(compare.ObservationError):
                compare.compare(path)
        manifest = copy.deepcopy(original)
        manifest["observations"][1]["file"] = manifest["observations"][0]["file"]
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(compare.ObservationError, "repeated observation filename"):
            compare.compare(path)
        for schema in (True, 2):
            path.write_text(json.dumps({"schema": schema, "observations": original["observations"]}))
            with self.assertRaises(compare.ObservationError):
                compare.compare(path)

    def test_bounded_regular_JSON_inputs_and_duplicates(self):
        path = self.root / "input.json"
        for raw in (b"{", b'{"schema":1,"schema":1}', b'{"x":NaN}', b'{"x":Infinity}',
                    b" " * (compare.MAX_BYTES + 1)):
            path.write_bytes(raw)
            with self.assertRaises(ValueError):
                compare.read_json(path)
        path.unlink()
        path.symlink_to(self.root / "absent")
        with self.assertRaises(OSError):
            compare.read_json(path)
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(compare.ObservationError):
            compare.read_json(path)
        with self.assertRaises(compare.ObservationError):
            compare.read_json(self.root)

    def test_main_private_exclusive_output_and_no_hardware_or_child_process(self):
        path, _ = self.fixture()
        output = self.root / "report.partial"
        # Actual main path can use only these local files. No command execution hook exists.
        with mock.patch("subprocess.Popen", side_effect=AssertionError("must not start a process")), \
                mock.patch("socket.socket", side_effect=AssertionError("must not use network")), \
                mock.patch("builtins.print"):
            self.assertEqual(0, compare.main([str(path), str(output)]))
            before = output.read_bytes()
            self.assertEqual(0o600, stat.S_IMODE(output.stat().st_mode))
            self.assertEqual(1, compare.main([str(path), str(output)]))
            self.assertEqual(before, output.read_bytes())
            output.unlink()
            output.symlink_to(self.root / "protected")
            self.assertEqual(1, compare.main([str(path), str(output)]))
            self.assertFalse((self.root / "protected").exists())
            self.assertEqual(1, compare.main([str(path), "relative.partial"]))
            self.assertEqual(1, compare.main([str(path), str(self.root / "report.json")]))
            output.unlink()
            (self.root / "power.partial").write_text("truncated")
            self.assertEqual(1, compare.main([str(path), str(output)]))
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
