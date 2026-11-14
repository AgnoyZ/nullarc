"""Native desktop handoff CPU contracts. No native target/helper is ever run."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DesktopHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler, cxx = shutil.which("clang"), shutil.which("clang++")
        if not compiler or not cxx:
            raise RuntimeError("Actual desktop CPU contracts require Clang, never count absence as a pass")
        cls.temporary = tempfile.TemporaryDirectory(prefix="phx-desktop-cpu-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        source = (ROOT / "src/phxbringup/PhxBringup.cpp").read_text()
        for filename, expression in {
            "queue-structure.inc": r"^    struct GpuQueue \{.*?^    \};",
            "queue-adoption.inc": r"^IOReturn PhxBringup::adoptQueue\([^\n]*\) \{.*?^\}\n",
            "queue-readiness-declaration.inc": r"^    bool gpuReady\(\) const[^\n]+$",
            "desktop-client-close.inc": r"^void IOAccelPhxNativeClient::closeResources\([^\n]*\) \{.*?^\}\n",
        }.items():
            matches = re.findall(expression, source, re.M | re.S)
            if len(matches) != 1:
                raise RuntimeError("Actual source fragment missing or ambiguous: " + filename)
            (cls.directory / filename).write_text(matches[0] + "\n")
        for filename, names in (
            ("queue-readiness-methods.inc", ("claimAccel", "bootMemory")),
            ("desktop-methods.inc", ("lockDebugMutation", "unlockDebugMutation", "abandonDesktop", "desktopHandoff")),
        ):
            fragments = []
            for name in names:
                matches = re.findall(r"^(?:IOReturn|void) PhxBringup::" + name + r"\([^\n]*\) \{.*?^\}\n", source, re.M | re.S)
                if len(matches) != 1:
                    raise RuntimeError("Actual provider method missing or ambiguous: " + name)
                fragments.extend(matches)
            (cls.directory / filename).write_text("\n".join(fragments))
        cls.provider, cls.entrypoint = cls.directory / "provider-fake", cls.directory / "entrypoint-fake"
        common = ["-g", "-Wall", "-Wextra", "-fsanitize=address,undefined", "-fno-sanitize-recover=all"]
        commands = [
            [cxx, "-std=c++17", "-Werror", *common, "-I" + str(ROOT / "src/phxbringup"),
             "-I" + str(cls.directory), str(ROOT / "tests/test_desktop_handoff.cpp"), "-o", str(cls.provider)],
            [compiler, "-std=c11", "-D_DEFAULT_SOURCE", *common, "-I" + str(ROOT / "tests/fake_iokit"),
             "-I" + str(ROOT / "tools/phxctl"), str(ROOT / "tests/test_desktop_entrypoint.c"), "-o", str(cls.entrypoint)],
        ]
        for command in commands:
            result = subprocess.run(command, capture_output=True, text=True, timeout=90)
            if result.returncode:
                raise RuntimeError("Fake-only desktop compile failed: " + result.stderr)

    def provider_case(self, name):
        result = subprocess.run([str(self.provider), name], capture_output=True, text=True, timeout=15)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("actual-desktop-methods-passed " + name, result.stdout.strip())

    def cli_case(self, fault, status, command="desktop-init", variant="relocated"):
        result = subprocess.run([str(self.entrypoint), variant, fault, command], capture_output=True, text=True,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, timeout=15)
        self.assertEqual(status, result.returncode, result.stderr)
        rows = re.findall(r"^fake-desktop-summary (.*)$", result.stderr, re.M)
        self.assertEqual(1, len(rows), result.stderr)
        data = json.loads(rows[0])
        self.assertTrue(all(type(value) is int and value >= 0 for value in data.values()))
        self.assertEqual(status == 0, "desktop claim:" in result.stdout if command == "desktop-claim" else "desktop handoff:" in result.stdout)
        return data

    def test_provider_reservation_covers_every_arena_and_doorbell(self):
        self.provider_case("arithmetic")

    def test_provider_all_debug_mutations_are_serialized_and_foreign_writes_refused(self):
        self.provider_case("lease")

    def test_passive_close_does_not_wait_for_initializer_and_initializer_close_abandons(self):
        self.provider_case("passive-close")
        self.provider_case("initializer-close")

    def test_provider_refuses_live_contexts_slots_stopping_or_unusable_bootstrap(self):
        for name in ("live-vm", "live-slot", "faulted-slot", "stopping", "invalid-layout", "doorbell-overrun", "psp-fault", "pre-adopted"):
            with self.subTest(case=name):
                self.provider_case(name)

    def test_provider_seal_is_bound_to_owner_layout_and_queue_positions(self):
        for name in ("foreign-seal", "layout-drift", "wrong-wptr"):
            with self.subTest(case=name):
                self.provider_case(name)

    def test_provider_checks_full_width_tokens_and_writeback_before_adoption(self):
        for index in range(4):
            with self.subTest(index=index):
                self.provider_case("bad-evidence-" + str(index))

    def test_provider_adoption_failure_never_claims_or_releases_reservation(self):
        for name in ("adoption-failure", "second-adoption-failure"):
            with self.subTest(case=name):
                self.provider_case(name)

    def test_provider_handoff_survives_initializer_exit_and_claim_is_single_use(self):
        self.provider_case("ok")
        self.provider_case("claim-no-pci")

    def test_complete_cli_relocated_and_reference_layouts_share_one_connection(self):
        for variant in ("reference", "relocated"):
            with self.subTest(variant=variant):
                data = self.cli_case("ok", 0, variant=variant)
                self.assertEqual([1, 3, 1, 1, 0, 4, 1, 1, 1],
                                 [data[key] for key in ("opens", "snapshots", "reservations", "seals", "claims",
                                                       "scheduler_bells", "compute_bells", "graphics_bells", "closes")])

    def test_cli_argument_and_environment_refusals_precede_service_open(self):
        for fault in ("bad-count", "bad-argument", "env-override"):
            with self.subTest(fault=fault):
                data = self.cli_case(fault, 64)
                self.assertFalse(any(data.values()))

    def test_cli_layout_and_preexisting_activity_refusals_precede_writes(self):
        for fault in ("overlap", "pre-adopted", "psp-fault"):
            with self.subTest(fault=fault):
                data = self.cli_case(fault, 75)
                self.assertEqual([0, 0, 0, 0], [data[key] for key in ("reservations", "seals", "writes", "vwrites")])

    def test_cli_reservation_refusal_precedes_register_or_memory_activity(self):
        data = self.cli_case("reserve-status", 74)
        self.assertEqual([0, 0, 0], [data[key] for key in ("reads", "writes", "vwrites")])

    def test_cli_preserves_transport_errors_without_seal_or_claim(self):
        for fault in ("hello-status", "snapshot-status", "snapshot-short", "read-status", "write-status",
                      "vwrite-status", "vread-status", "doorbell-status", "delay-error"):
            with self.subTest(fault=fault):
                data = self.cli_case(fault, 74)
                self.assertEqual([0, 0], [data["seals"], data["claims"]])

    def test_cli_preconditions_and_scheduler_failures_skip_both_workloads_and_seal(self):
        for fault in ("already-mes", "already-queue", "setup-readback", "gart-timeout", "scheduler-timeout",
                      "scheduler-fence-high", "scheduler-token-high"):
            with self.subTest(fault=fault):
                data = self.cli_case(fault, 75)
                self.assertEqual([0, 0, 0, 0], [data[key] for key in ("compute_bells", "graphics_bells", "seals", "claims")])

    def test_cli_compute_failures_never_start_graphics_or_seal(self):
        for fault in ("compute-timeout", "compute-scratch", "compute-memory", "compute-fence-high"):
            with self.subTest(fault=fault):
                data = self.cli_case(fault, 75)
                self.assertEqual([1, 0, 0, 0], [data[key] for key in ("compute_bells", "graphics_bells", "seals", "claims")])

    def test_cli_graphics_failures_never_seal_or_claim(self):
        for fault in ("graphics-timeout", "graphics-scratch", "graphics-memory", "graphics-fence-high"):
            with self.subTest(fault=fault):
                data = self.cli_case(fault, 75)
                self.assertEqual([1, 1, 0, 0], [data[key] for key in ("compute_bells", "graphics_bells", "seals", "claims")])

    def test_cli_seal_and_close_status_cannot_be_masked_by_prior_success(self):
        for fault in ("seal-status", "close-status"):
            with self.subTest(fault=fault):
                self.assertEqual(1, self.cli_case(fault, 74)["seals"])

    def test_explicit_claim_uses_exact_handoff_without_reinitialization_or_legacy_selector(self):
        for fault, status in (("ok", 0), ("claim-status", 74), ("close-status", 74)):
            with self.subTest(fault=fault):
                data = self.cli_case(fault, status, command="desktop-claim")
                self.assertEqual(1, data["claims"])
                self.assertFalse(any(data[key] for key in ("snapshots", "reservations", "seals", "writes", "vwrites", "reads")))

    def test_kernel_dispatcher_preserves_passive_lane_and_privilege_shape_checks(self):
        source = (ROOT / "src/phxbringup/PhxBringup.cpp").read_text()
        handler = source.split("IOReturn IOAccelPhxNativeClient::doDesktopHandoff(")[1].split("// Write back")[0]
        for required in ("!owner->debugEnabled()", "!privileged", "!shape(a, 0, 0, sizeof(PhxDesktopRequest), 0)", "!a->structureInput"):
            self.assertIn(required, handler)
        dispatcher = source.split("IOReturn IOAccelPhxNativeClient::externalMethod(")[1].split("IOReturn IOAccelPhxNativeClient::doAllocationSnapshot(")[0]
        self.assertLess(dispatcher.index("return doAllocationSnapshot(a)"), dispatcher.index("lockDebugMutation"))
        self.assertIn("case PHX_DESKTOP_SELECTOR: r = doDesktopHandoff(a);", dispatcher)
        close = source.split("void IOAccelPhxNativeClient::closeResources(")[1].split("IOReturn IOAccelPhxNativeClient::clientClose(")[0]
        self.assertIn("if (desktopReservationOwned && owner)", close)
        self.assertIn("desktopReservationOwned = false;", close)
        stop = source.split("void PhxBringup::stop(")[1].split("IOReturn PhxBringup::setPowerState(")[0]
        self.assertIn("desktopState != DesktopUnused", stop)
        self.assertLess(stop.index("stopQuarantined"), stop.index("fbAper->release()"))


if __name__ == "__main__":
    unittest.main()
