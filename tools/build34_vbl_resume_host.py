#!/usr/bin/env python3
"""Restore only the previously tested VBL accelerator on the current R1a.

Run only from a newly sealed private scope. The kernel, plugin and ACPI are
unchanged. One finite startup watcher may recover the exact R1a disk/jobs and
request at most one restart. Accepted VBL jobs remain usable on later boots;
their bounded failure handler can restore R1a on disk but cannot request power.
"""

import copy
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


base = load("VBL_R1a_host", Path(__file__).with_name("build34_startup_host.py"))
VBL_SOURCE = "439f8a5bc3e086770df7b576897fbb11d7ccc9f1"
ACCELERATOR = "/Library/Extensions/PhxAccel.kext/Contents/MacOS/PhxAccel"
CACHE = "/Library/KernelCollections/AuxiliaryKernelExtensions.kc"
EXPECTED_CANDIDATES = {
    ACCELERATOR: "a206d983fca62dd7959cc701fb9f95d5490da78986aac02dbb67ed00410325e7",
    CACHE: "f0dbaacf423819c29af7ac0503d6f6c80d897a327dabb6a235385e1cd52728da",
}


def derive_vbl(original, config, kind):
    """Overlay only two exact protected hashes and the accelerator identity."""
    result = copy.deepcopy(original)
    if kind == "contract":
        for path, change in config["VBL_changes"].items():
            assert result["protected"][path] == change["before"]
            result["protected"][path] = change["after"]
        runtime = result["desktop_runtime"]
        assert runtime["accel_bundle_id"] == "com.luuumi.PhxAccel"
        assert runtime["accel_image_uuid"] == config["VBL_before_uuid_private"]
        assert config["VBL_after_uuid_private"] != config["VBL_before_uuid_private"]
        runtime["accel_image_uuid"] = config["VBL_after_uuid_private"]
    else:
        assert kind == "stage"
    return result


def atomic_image(target, source, allowed):
    """Replace a known image, preserving its owner, mode and BSD flags."""
    target, source = Path(target), Path(source)
    base.secure(target)
    base.secure(source)
    info = target.lstat()
    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1
    old, new = base.sha(target), base.sha(source)
    assert old in allowed and new in allowed
    if old == new:
        return
    temporary = target.with_name(target.name + ".nullarc-vbl-resume-next")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as out, source.open("rb") as src:
            for block in iter(lambda: src.read(1024 * 1024), b""):
                out.write(block)
            out.flush()
            os.fchmod(out.fileno(), stat.S_IMODE(info.st_mode))
            os.fchown(out.fileno(), info.st_uid, info.st_gid)
            os.fsync(out.fileno())
        assert base.sha(temporary) == new and base.sha(target) == old
        os.replace(temporary, target)
        if getattr(info, "st_flags", 0):
            os.chflags(target, info.st_flags)
        assert base.sha(target) == new
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


class VBLHost(base.Host):
    SCOPE_KIND = "R1a-retained-VBL-startup-recovery"

    def contract(self):
        value = super().contract()
        assert value["owner_authorized_VBL_restoration"] is True
        assert value["VBL_source_checkpoint"] == VBL_SOURCE
        assert value["Weather_candidate_enabled"] is False
        self.validate_acpi_contract(value)
        assert set(value["VBL_changes"]) == set(EXPECTED_CANDIDATES)
        assert value["daily_recovery_restart_limit"] == 0
        for path, digest in EXPECTED_CANDIDATES.items():
            change = value["VBL_changes"][path]
            assert change["after"] == digest and change["before"] != digest
            for key, expected in (("candidate", digest), ("backup", change["before"])):
                assert value["sealed"][change[key]] == expected
        return value

    def validate_acpi_contract(self, value):
        assert value["ACPI_candidate_enabled"] is False

    def __init__(self, directory):
        super().__init__(directory)
        old_derive = self.readonly.derive
        self.readonly.derive = lambda original, config, kind: derive_vbl(
            old_derive(original, config, kind), config, kind)
        self.readonly.cache_check = self.cache_check
        recovery = load("VBL_daily_journal", self.scope / "build34_startup_recovery.py")
        self.daily_policy = recovery.StartupRecovery(self.scope / "daily-recovery-journal")

    def cache_check(self):
        checker = load("VBL_complete_cache", self.scope / "check_build34_cache_metadata.py")
        raw = subprocess.check_output([
            "/usr/bin/kmutil", "inspect", "-a", "x86_64", "-B",
            "/System/Library/KernelCollections/BootKernelExtensions.kc", "-S",
            "/System/Library/KernelCollections/SystemKernelExtensions.kc", "-A", CACHE,
            "--show-prelink-info"], timeout=60)
        return checker.compare_captures(
            (self.scope / "candidate-prelink-info-private.txt").read_bytes(), raw, [])

    def check_restore_inputs(self):
        """Check every restore target before writing the first image."""
        c = self.contract()
        route = load("VBL_original_EFI", self.readonly.OLD / "internal-route-private.py")
        with route.efi(route.static()) as root:
            assert route.files(root) == c["EFI_accepted_private"]
        for path, change in c["VBL_changes"].items():
            base.secure(path)
            assert base.sha(path) in (change["before"], change["after"])
            assert base.sha(self.scope / change["backup"]) == change["before"]
        for path, accepted in c["recovery_jobs"].items():
            base.secure(path)
            assert base.sha(path) in (c["jobs"][path], accepted["sha256"])
            assert base.sha(self.scope / accepted["backup"]) == accepted["sha256"]
        watcher = Path(c["watcher_job"])
        if watcher.exists():
            base.secure(watcher)
            assert base.sha(watcher) == c["watcher_job_sha256"]
        pending = Path("/var/db/phxboot.pending")
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b""
        return c

    def quiesce(self):
        if super().quiesce() is not True:
            return False
        # Also refuse an orphan whose launch succeeded before its PID receipt
        # could be written. Supervisors/watchers never submit GPU work.
        script = str(self.scope / "owner-startup-private.py")
        for line in subprocess.check_output(
                ["/bin/ps", "-ww", "-axo", "command="], text=True, timeout=5).splitlines():
            fields = line.split()
            if script in fields:
                tail = fields[fields.index(script) + 1:]
                if tail not in (["startup"], ["guardian"], ["watch"]):
                    return False
        return True

    def restore(self):
        c = self.check_restore_inputs()
        for path, change in c["VBL_changes"].items():
            atomic_image(path, self.scope / change["backup"],
                         (change["before"], change["after"]))
        self.restore_jobs()
        self.retire_watcher()
        pending = Path("/var/db/phxboot.pending")
        if pending.exists():
            base.secure(pending)
            assert pending.read_bytes() == b""
            pending.unlink()
        subprocess.run(["/usr/sbin/sysctl", "-w", "debug.phxfb_hold=0"],
                       capture_output=True, timeout=5)
        subprocess.run(["/bin/sync"], check=True, timeout=15)

    def retire_watcher(self):
        path = Path(self.config["watcher_job"])
        if path.exists():
            base.secure(path)
            assert base.sha(path) == self.config["watcher_job_sha256"]
            path.unlink()

    def recovery_actions(self):
        return {name: getattr(self, name) for name in
                ("quiesce", "restore", "verify", "prepare_restart", "request_restart")}

    def watch(self):
        assert self.boot() != self.config["prepared_boot"]
        try:
            status = self.policy.watch(self.boot(), read_admission=self.read_admission,
                                       recovery_actions=self.recovery_actions())
            # Keep the exact candidate jobs after success. They understand the
            # accepted journal on later boots and do not reuse restart permission.
            self.put("watcher-result-" + self.boot() + ".json", {"status": status})
        finally:
            self.retire_watcher()

    def daily_failed(self):
        with self.daily_policy._locked() as directory:
            return self.daily_policy._read(directory, "outcome.json") is not None

    def worker(self, role):
        actual = self.boot()
        assert actual != self.config["prepared_boot"] and role in ("startup", "guardian")
        assert not self.daily_failed(), "retained VBL runtime already recovered"
        if self.policy.accepted_boot() is None:
            assert self.policy.begin_trial(actual), "VBL trial closed without acceptance"
        d, k, _ = self.readonly.build()
        d.live_identity(k)
        getattr(d.deployment, "future_" + role)(d, k)

    def supervise(self, role):
        try:
            super().supervise(role)
        except BaseException:
            accepted = self.policy.accepted_boot()
            if accepted is not None and accepted != self.boot():
                # Only startup worker failure on a later accepted boot; no
                # resident monitor or post-startup automatic action is added.
                assert self.daily_policy.begin_trial(self.boot())
                actions = dict(self.recovery_actions())
                actions.update(prepare_restart=self.refuse_daily_power,
                               request_restart=self.refuse_daily_power)
                self.daily_policy.recover(self.boot(), reason="daily-startup-failure",
                                          **actions)
            raise

    @staticmethod
    def refuse_daily_power():
        raise RuntimeError("retained daily VBL startup cannot request power")


def main():
    os.umask(0o077)
    host = VBLHost(Path(__file__).resolve().parent)
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
