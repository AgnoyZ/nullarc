#!/usr/bin/env python3
"""One kernel-only R1b trial retaining the accepted R1a/VBL/AML desktop.

Startup recovery ends before a separately dispatched finite pressure probe.
Old R1a, VBL and ACPI contracts retain their exact original source admission.
"""

import copy
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


acpi = load("R1b_ACPI_host", Path(__file__).with_name("build34_acpi_resume_host.py"))
base = acpi.base
R1B_SOURCE = "194ce9098b34c9f48483ff0729a50b21c5ca0401"
EXECUTABLE = "Contents/MacOS/PhxBringup"
KERNEL = "OC/Kexts/PhxBringup.kext/" + EXECUTABLE
R1A_BINARY = "fab1c35b3be1485bb60aa2e03731f971db922ac56508029057c02d4e40bc16fe"
R1B_BINARY = "0414c22119bad9526a33ec97bb56b9e7a8fd26320976cf24e0cb541d0d882d10"


def kernel_states(c):
    before, after = c["R1b_baseline_EFI_private"], c["EFI_after_private"]
    assert set(before) == set(after)
    assert {p for p in before if before[p] != after[p]} == {KERNEL}
    assert before[KERNEL] == c["kernel_after"][EXECUTABLE]
    assert before[KERNEL]["sha256"] == R1A_BINARY
    assert after[KERNEL] == c["R1b_kernel_files_private"][EXECUTABLE]
    assert after[KERNEL]["sha256"] == R1B_BINARY
    bundle = c["R1b_kernel_files_private"]
    assert set(bundle) == set(c["kernel_after"])
    assert {p for p in bundle if bundle[p] != c["kernel_after"][p]} == {EXECUTABLE}
    assert c["sealed"]["R1a-kernel.bin"] == R1A_BINARY
    assert c["sealed"]["R1b-kernel.bin"] == R1B_BINARY
    # Retain the old AML allowance, without allowing another EFI change.
    old = copy.deepcopy(c)
    old["EFI_after_private"] = before
    acpi.efi_states(old)
    return before, after


def derive_kernel(original, c, kind):
    result = copy.deepcopy(original)
    assert kind in ("contract", "stage")
    if kind == "contract":
        assert result["candidate_files"] == c["kernel_after"]
        assert result["candidate_binary_sha256"] == R1A_BINARY
        assert result["candidate_image_uuid"] == c["kernel_after_uuid_private"]
        assert c["R1b_image_uuid_private"] != c["kernel_after_uuid_private"]
        result["candidate_files"] = copy.deepcopy(c["R1b_kernel_files_private"])
        result["candidate_binary_sha256"] = R1B_BINARY
        result["candidate_image_uuid"] = c["R1b_image_uuid_private"]
    return result


def pre_restart_live_contract(candidate, c):
    """Check the still-loaded R1a image while R1b is only on disk."""
    assert candidate["candidate_image_uuid"] == c["R1b_image_uuid_private"]
    assert candidate["candidate_binary_sha256"] == R1B_BINARY
    assert c["R1b_image_uuid_private"] != c["kernel_after_uuid_private"]
    live = copy.deepcopy(candidate)
    live["candidate_image_uuid"] = c["kernel_after_uuid_private"]
    return live


class R1bHost(acpi.ACPIHost):
    SCOPE_KIND = "R1b-kernel-only-retained-VBL-AML-startup-recovery"

    def validate_kernel_contract(self, value):
        assert value["kernel_source_checkpoint"] == R1B_SOURCE
        assert value["R1b_baseline_kernel_source"] == base.R1A_SOURCE
        assert value["R1b_owner_authorized_sequential_trial"] is True

    def validate_efi_contract(self, value):
        kernel_states(value)

    def __init__(self, directory):
        super().__init__(directory)
        self.baseline = acpi.ACPIHost(Path(self.config["R1b_baseline_scope"]))
        assert base.sha(self.baseline.scope / "contract-private.json") == self.config["R1b_baseline_contract_sha256"]
        assert self.baseline.config["EFI_after_private"] == self.config["R1b_baseline_EFI_private"]
        assert self.baseline.policy.accepted_boot() is not None
        assert not self.baseline.daily_failed()
        original = self.readonly.derive
        self.readonly.derive = lambda record, config, kind: derive_kernel(
            original(record, config, kind), config, kind)

    def acpi_check(self, *, allow_recovery=False):
        # AML is already loaded in the preparation boot too. Never reinterpret
        # the new scope's preparation boot as permission for original ACPI.
        result = self.baseline.acpi_check()
        assert result["exact_candidate_SSDT"] is True
        assert result["exact_DSDT_method_body_and_callsite"] is True
        return result

    def check_restore_inputs(self):
        c = self.contract()
        before, after = kernel_states(c)
        route = load("R1b_restore_route", self.readonly.OLD / "internal-route-private.py")
        with route.efi(route.static()) as root:
            assert route.files(root) in (before, after)
        for path, change in c["VBL_changes"].items():
            base.secure(path)
            assert base.sha(path) == change["after"]
        for path, accepted in c["recovery_jobs"].items():
            base.secure(path)
            assert base.sha(path) in (c["jobs"][path], accepted["sha256"])
            assert base.sha(self.scope / accepted["backup"]) == accepted["sha256"]
            assert accepted["sha256"] == self.baseline.config["jobs"][path]
        watcher = Path(c["watcher_job"])
        if watcher.exists():
            base.secure(watcher)
            assert base.sha(watcher) == c["watcher_job_sha256"]
        pending = Path("/var/db/phxboot.pending")
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b""
        return c

    def restore(self):
        c = self.check_restore_inputs()
        route = load("R1b_kernel_restore", self.readonly.OLD / "internal-route-private.py")
        with route.efi(route.static(), writable=True) as root:
            before, after = kernel_states(c)
            assert route.files(root) in (before, after)
            self.readonly.atomic_file(root / KERNEL, (self.scope / "R1a-kernel.bin").read_bytes(),
                                      [R1A_BINARY, R1B_BINARY])
            assert route.files(root) == before
        self.restore_jobs()
        self.retire_watcher()
        pending = Path("/var/db/phxboot.pending")
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b""
            pending.unlink()
        subprocess.run(["/usr/sbin/sysctl", "-w", "debug.phxfb_hold=0"], capture_output=True, timeout=5)
        subprocess.run(["/bin/sync"], check=True, timeout=15)

    def verify_restore(self):
        d, k, c = self.baseline.readonly.build()
        d.r.verify_disk("candidate")
        with d.r.efi(d.r.static()) as root:
            assert d.r.files(root) == c["EFI_after_private"] == self.config["R1b_baseline_EFI_private"]
            subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(root / d.r.ACTIVE)],
                           capture_output=True, check=True, timeout=20)
        assert d.plugin.files(d.plugin.LIVE) == k["plugin_after"]
        self.baseline.cache_check()
        self.acpi_check()
        assert d.r.support.security() == k["security"]
        for path, digest in c["jobs"].items():
            base.secure(path)
            assert base.sha(path) == digest
        assert not Path(self.config["watcher_job"]).exists()
        return True

    verify = verify_restore


def main():
    os.umask(0o077)
    host = R1bHost(Path(__file__).resolve().parent)
    action = sys.argv[1]
    if action == "watch":
        host.watch()
    elif action == "recover":
        host.note_failure("protected-startup-failure")
    elif action == "worker":
        host.worker(sys.argv[2])
    else:
        host.supervise(action)


if __name__ == "__main__":
    main()
