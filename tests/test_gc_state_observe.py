"""Actual fixed GC collector with fake IOKit; never run a target-linked binary."""
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NAMES = [
    "PSP_INITIALIZATION_STATUS", "RCC_CONFIG_MEMSIZE", "GRBM_STATUS", "GRBM_STATUS2",
    "GB_ADDR_CONFIG", "CP_STAT", "GRBM_GFX_CNTL", "CP_MES_CNTL", "RLC_CNTL", "RLC_STAT",
    "RLC_PG_CNTL", "RLC_CGCG_CGLS_CTRL", "RLC_GPM_STAT", "RLC_RLCS_BOOTLOAD_STATUS_GC_11_0_1",
    "GFX_IMU_SCRATCH_0", "GRBM_SOFT_RESET", "CP_ME_CNTL", "CP_SOFT_RESET_CNTL", "GRBM_CNTL",
]


class GCStateObservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang")
        if not compiler:
            raise RuntimeError("GC observation contracts require Clang; absence is not a pass")
        cls.temporary = tempfile.TemporaryDirectory(prefix="phx-gc-observe-cpu-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        cls.binary = cls.directory / "fake-observer"
        result = subprocess.run([
            compiler, "-std=c11", "-D_DEFAULT_SOURCE", "-Wall", "-Wextra", "-Werror", "-g",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
            "-I" + str(ROOT / "tests/fake_iokit"), str(ROOT / "tests/test_gc_state_observe.c"),
            "-o", str(cls.binary),
        ], capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError("Fake-only collector compilation failed: " + result.stderr)

    def run_case(self, fault, status, snapshots=0, reads=0, closes=0, lookups=1, opens=1,
                 hellos=1, phase="configured", variant="reference"):
        with tempfile.TemporaryDirectory(dir=self.directory) as destination_dir:
            destination = Path(destination_dir) / "observation.partial"
            protected = Path(destination_dir) / "must-not-create"
            if fault == "output-exists":
                destination.write_bytes(b"original")
            if fault == "output-symlink":
                destination.symlink_to(protected)
            env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
            if fault == "reference-override":
                env["PHX_LAYOUT_REFERENCE"] = "1"
            name = ("tmr:" if phase == "tmr-ready" else "") + fault
            result = subprocess.run([str(self.binary), variant, name, str(destination)],
                                    capture_output=True, text=True, timeout=10, env=env)
            self.assertEqual(status, result.returncode, result.stderr)
            summaries = re.findall(r"^fake-gc-observation-summary (.*)$", result.stderr, re.M)
            self.assertEqual(1, len(summaries), result.stderr)
            self.assertEqual(dict(lookups=lookups, opens=opens, hellos=hellos, snapshots=snapshots,
                                  reads=reads, writes=0, closes=closes), json.loads(summaries[0]))
            self.assertEqual(status == 0, "GC observation complete:" in result.stdout)
            self.assertFalse(protected.exists())
            if status == 0:
                self.assertEqual(0o600, stat.S_IMODE(destination.stat().st_mode))
                data = json.loads(destination.read_text())
                self.assertEqual({"schema", "observation_only", "phase", "GPU_register_writes", "registers"}, set(data))
                self.assertEqual((1, True, phase, 0), (data["schema"], data["observation_only"],
                                                     data["phase"], data["GPU_register_writes"]))
                self.assertEqual(NAMES, [item["name"] for item in data["registers"]])
                self.assertEqual(19, len({item["index"] for item in data["registers"]}))
                self.assertNotIn("ready", result.stdout)
                if fault == "all-zero-gc":
                    self.assertTrue(all(item["value"] == 0 for item in data["registers"][2:]))
            elif destination.is_file() and not destination.is_symlink():
                self.assertEqual(b"original" if fault == "output-exists" else b"", destination.read_bytes())

    def test_fixed_observations_both_phases_and_layouts(self):
        for phase in ("configured", "tmr-ready"):
            for variant in ("reference", "relocated"):
                for fault in ("ok", "all-zero-gc"):
                    with self.subTest(phase=phase, variant=variant, fault=fault):
                        self.run_case(fault, 0, snapshots=2, reads=19, closes=1,
                                      phase=phase, variant=variant)

    def test_arguments_privilege_and_exclusive_output_before_service(self):
        for fault, status in [(name, 64) for name in ("arg-count", "relative-path", "bad-suffix", "bad-mode")] + [
            ("not-root", 77), ("output-exists", 73), ("output-symlink", 73),
        ]:
            with self.subTest(fault=fault):
                self.run_case(fault, status, lookups=0, opens=0, hellos=0)

    def test_service_ABI_and_geometry_failures_before_metadata_or_registers(self):
        self.run_case("no-service", 74, opens=0, hellos=0)
        self.run_case("open-fail", 74, hellos=0)
        for fault in ("hello-fail", "hello-short", "hello-long"):
            with self.subTest(fault=fault):
                self.run_case(fault, 74)
        for fault in ("hello-abi", "reference-override", "property-missing"):
            with self.subTest(fault=fault):
                self.run_case(fault, 74, closes=1)

    def test_bootstrap_metadata_refusals_before_registers(self):
        shared = ("gpu-active", "faulted", "unknown-flag", "snapshot-version", "snapshot-reserved",
                  "snapshot-geometry", "snapshot-unaligned", "snapshot-too-large", "snapshot-layout",
                  "layout-reserved", "layout-overlap", "layout-outside", "aperture-zero", "aperture-too-large")
        modes = {"configured": ("ring-active", "tmr-active", "snapshot-tmr"),
                 "tmr-ready": ("tmr-zero", "tmr-too-large", "missing-ring", "missing-tmr", "configured-only")}
        for phase, extra in modes.items():
            for fault in shared + extra:
                with self.subTest(phase=phase, fault=fault):
                    self.run_case(fault, 75, snapshots=1, phase=phase)

    def test_metadata_transport_failure_stops_at_each_snapshot(self):
        for phase in ("configured", "tmr-ready"):
            for ordinal in (1, 2):
                for fault in ("snapshot-fail", "snapshot-short", "snapshot-long"):
                    with self.subTest(phase=phase, ordinal=ordinal, fault=fault):
                        self.run_case(fault + "-" + str(ordinal), 74, snapshots=ordinal,
                                      reads=19 if ordinal == 2 else 0, phase=phase)

    def test_each_register_status_shape_and_all_ones_failure_is_terminal(self):
        for phase in ("configured", "tmr-ready"):
            for ordinal in range(1, 20):
                for fault, status in (("read-fail", 74), ("read-short", 74), ("read-long", 74), ("all-ones", 75)):
                    with self.subTest(phase=phase, ordinal=ordinal, fault=fault):
                        self.run_case(fault + "-" + str(ordinal), status, snapshots=1,
                                      reads=ordinal, phase=phase)

    def test_positive_controls_and_metadata_drift_never_publish_success(self):
        for phase in ("configured", "tmr-ready"):
            self.run_case("control-not-ready", 75, snapshots=1, reads=1, phase=phase)
            for fault in ("control-zero-size", "control-size-mismatch"):
                self.run_case(fault, 75, snapshots=1, reads=2, phase=phase)
            for fault in ("changed-after", "flag-after"):
                self.run_case(fault, 75, snapshots=2, reads=19, phase=phase)
            self.run_case("close-fail", 74, snapshots=2, reads=19, closes=1, phase=phase)


if __name__ == "__main__":
    unittest.main()
