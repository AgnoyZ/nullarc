#!/usr/bin/env python3
"""Sealed adapter for a one-boot R1a startup recovery scope.

Install a private copy as owner-startup-private.py only after separate scope
preparation and validation. No candidate driver or GPU probe is part of this
adapter. Recovery is restricted to the sealed, already accepted R1a disk/jobs.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import signal
import stat
import subprocess
import sys
import time


PYTHON = "/Library/Developer/CommandLineTools/usr/bin/python3"
PYTHON_APP = str(Path(os.path.realpath(PYTHON)).parent.parent /
                 "Resources/Python.app/Contents/MacOS/Python")
R1A_SOURCE = "568e80b205c10b00cba4f21c6d324d239d725bfd"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def secure(path):
    info = Path(path).lstat()
    if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
        raise ValueError("unsafe startup scope path")


def worker_matches(fields, *, pid, script, role):
    """Accept CLT launcher/runtime names, with exact arguments and group."""
    return (len(fields) == 8 and fields[:2] == ["0", str(pid)]
            and fields[2] in (PYTHON, os.path.realpath(PYTHON), PYTHON_APP)
            and fields[3:] == ["-B", "-I", str(script), "worker", role])


def process_matches(text, *, pid, script, role):
    fields = text.strip().split()
    if len(fields) < 3:
        return False
    # ps stat is separate: zombies have no runnable work or descendants to stop.
    if fields[2].startswith("Z"):
        return "zombie"
    return worker_matches(fields[:2] + fields[3:],
                          pid=pid, script=script, role=role)


class Host:
    def __init__(self, directory):
        self.scope = Path(directory)
        self.config = self.contract()
        self.readonly = module("sealed_R1a_readonly", self.scope / "accepted-runtime-private.py")
        self.readonly.W = self.scope
        self.readonly.contract = self.contract
        self.readonly.recover = self.note_failure
        recovery = module("sealed_startup_recovery", self.scope / "build34_startup_recovery.py")
        self.policy = recovery.StartupRecovery(self.scope / "recovery-journal")

    def contract(self):
        assert os.geteuid() == 0 and sys.executable == PYTHON
        secure(self.scope)
        secure(self.scope / "contract-private.json")
        value = json.loads((self.scope / "contract-private.json").read_text())
        assert value["scope_kind"] == "accepted-R1a-startup-recovery"
        assert value["kernel_source_checkpoint"] == R1A_SOURCE
        assert value["startup_limits_seconds"] == [45, 150, 300]
        assert value["automatic_recovery_reboots"] == 1
        assert value["owner_authorized_startup_auto_recovery"] is True
        assert value["resident_monitor_enabled"] is False
        assert value["pressure_probe_enabled"] is False
        assert value["EFI_after_private"] == value["EFI_accepted_private"]
        for name, digest in value["sealed"].items():
            path = Path(name)
            assert not path.is_absolute() and ".." not in path.parts
            secure(self.scope / path)
            assert sha(self.scope / path) == digest
        return value

    def put(self, name, value):
        with (self.scope / name).open("x") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(value, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def boot(self):
        return self.readonly.boot()

    def note_failure(self, reason):
        # No frozen or older controller's recovery is invoked.
        try:
            self.put("failure-" + self.boot() + ".json", {"reason": reason})
        except FileExistsError:
            pass

    def root(self):
        return self.scope / ("installed-boot-" + self.boot())

    def read_admission(self):
        try:
            return self._read_admission()
        except BaseException as error:
            self.note_failure(type(error).__name__)
            return "admission-exception"

    def _read_admission(self):
        root = self.root()
        if ((self.scope / ("failure-" + self.boot() + ".json")).exists()
                or any((root / name).exists() for name in ("failure.json", "startup-failure.json"))):
            return "startup-worker-failure"
        if not all((root / name).is_file() for name in self.readonly.RECEIPTS):
            return None
        self.readonly.validate_receipts(
            [json.loads((root / name).read_text()) for name in self.readonly.RECEIPTS], self.boot())
        d, k, _, _ = self.readonly.full_static()
        d.live_identity(k, desktop=True)
        self.readonly.progress(self.readonly.snapshot(d), self.sample_later(d))
        return True

    def sample_later(self, desktop):
        time.sleep(1)
        return self.readonly.snapshot(desktop)

    def quiesce(self):
        """Stop only exact current-boot worker groups and verify retirement."""
        if (self.scope / "GPU-probe.intent").exists():
            return False
        for role in ("startup", "guardian"):
            receipt = self.scope / ("process-" + role + "-" + self.boot() + ".json")
            if not receipt.is_file():
                continue
            secure(receipt)
            pid = json.loads(receipt.read_text())["worker_pid"]
            assert type(pid) is int and pid > 1 and pid != os.getpgrp()
            query = subprocess.run(["/bin/ps", "-ww", "-p", str(pid), "-o", "uid=,pgid=,stat=,command="],
                                   capture_output=True, text=True, timeout=5)
            if query.returncode == 0:
                state = process_matches(query.stdout, pid=pid,
                                        script=self.scope / "owner-startup-private.py", role=role)
                if state is False:
                    return False
                if state is True:
                    os.killpg(pid, signal.SIGTERM)
            elif query.returncode != 1:
                return False
            # Also check descendants after a leader exits; a surviving group
            # is not permission to send a signal to an unverified process.
            end = time.monotonic() + 5
            while True:
                group = subprocess.run(["/usr/bin/pgrep", "-g", str(pid)],
                                       capture_output=True, timeout=3)
                if group.returncode == 1:
                    break
                if group.returncode != 0 or time.monotonic() >= end:
                    return False
                time.sleep(0.1)
        return True

    def restore(self):
        """R1a-only scope: refuse any unknown kernel or job before mutation."""
        c = self.contract()
        route = module("accepted_disk_route", self.readonly.OLD / "internal-route-private.py")
        with route.efi(route.static()) as root:
            assert route.files(root) == c["EFI_accepted_private"]
        for path, accepted in c["recovery_jobs"].items():
            secure(path)
            assert sha(path) in (c["jobs"][path], accepted["sha256"])
            assert sha(self.scope / accepted["backup"]) == accepted["sha256"]
        pending = Path("/var/db/phxboot.pending")
        if pending.exists():
            secure(pending)
            assert pending.read_bytes() == b""
        self.restore_jobs()
        watcher = Path(c["watcher_job"])
        secure(watcher)
        assert sha(watcher) == c["watcher_job_sha256"]
        watcher.unlink()
        if pending.exists():
            pending.unlink()
        subprocess.run(["/usr/sbin/sysctl", "-w", "debug.phxfb_hold=0"],
                       capture_output=True, timeout=5)
        subprocess.run(["/bin/sync"], check=True, timeout=15)

    def restore_jobs(self):
        c = self.contract()
        for path, accepted in c["recovery_jobs"].items():
            secure(path)
            assert sha(path) in (c["jobs"][path], accepted["sha256"])
            assert sha(self.scope / accepted["backup"]) == accepted["sha256"]
        for path, accepted in c["recovery_jobs"].items():
            self.readonly.atomic_file(path, (self.scope / accepted["backup"]).read_bytes(),
                                      [c["jobs"][path], accepted["sha256"]])

    def verify_restore(self):
        """Independent accepted scope: exact disk, cache, ACPI and jobs.

        New diagnostic reports are failure evidence, not disk restore failure.
        Do not use loaded-image or successful desktop checks here: recovery is
        specifically needed when the loaded accelerator did not start.
        """
        base = module("independent_accepted_R1a", Path(self.config["accepted_scope"]) / "owner-startup-private.py")
        d, k, accepted = base.build()
        d.r.verify_disk("candidate")
        with d.r.efi(d.r.static()) as root:
            assert d.r.files(root) == accepted["EFI_after_private"] == self.config["EFI_accepted_private"]
            subprocess.run(["/usr/bin/codesign", "--verify", "--strict", str(root / d.r.ACTIVE)],
                           capture_output=True, check=True, timeout=20)
        assert d.plugin.files(d.plugin.LIVE) == k["plugin_after"]
        base.cache_check()
        base.acpi_check()
        assert d.r.support.security() == k["security"]
        for path, digest in accepted["jobs"].items():
            secure(path)
            assert sha(path) == digest
        assert not Path(self.config["watcher_job"]).exists()
        return True

    def prepare_restart(self):
        assert self.boot() != self.config["prepared_boot"]
        for name in ("reboot", "shutdown"):
            assert subprocess.run(["/usr/bin/pgrep", "-x", name], capture_output=True, timeout=5).returncode == 1
        subprocess.run(["/usr/sbin/nvram", "phxfb-boot=1"], capture_output=True, check=True, timeout=10)
        subprocess.run(["/usr/sbin/nvram", "IONVRAM-FORCESYNCNOW-PROPERTY=phxfb"],
                       capture_output=True, check=True, timeout=10)
        flag = plistlib.loads(subprocess.check_output(["/usr/sbin/nvram", "-x", "phxfb-boot"], timeout=10))
        assert len(flag) == 1 and next(iter(flag.values())) in ("1", b"1")
        tree = plistlib.loads(subprocess.check_output(
            ["/usr/sbin/ioreg", "-p", "IODeviceTree", "-n", "options", "-r", "-d", "1", "-a"], timeout=10))
        flags = [entry["phxfb-boot"] for entry in tree if "phxfb-boot" in entry]
        assert len(flags) == 1 and flags[0] in ("1", b"1", b"1\0")
        subprocess.run(["/bin/sync"], check=True, timeout=15)
        return True

    def request_restart(self):
        # The policy has already durably consumed the sole power permission.
        subprocess.run(["/sbin/shutdown", "-r", "now", "Bounded R1a startup recovery"],
                       capture_output=True, check=True, timeout=15)

    def watch(self):
        assert self.boot() != self.config["prepared_boot"]
        try:
            status = self.policy.watch(self.boot(), read_admission=self.read_admission,
                                       recovery_actions={name: getattr(self, name) for name in
                                                         ("quiesce", "restore", "verify", "prepare_restart", "request_restart")})
            if status == "accepted":
                self.restore_jobs()
            self.put("watcher-result-" + self.boot() + ".json", {"status": status})
        finally:
            # Retire this finite launch job, preserving unknown replacements.
            path = Path(self.config["watcher_job"])
            if path.exists():
                secure(path)
                assert sha(path) == self.config["watcher_job_sha256"]
                path.unlink()

    verify = verify_restore

    def worker(self, role):
        assert self.boot() != self.config["prepared_boot"]
        assert role in ("startup", "guardian")
        assert self.policy.begin_trial(self.boot()), "startup recovery scope already closed"
        d, k, _ = self.readonly.build()
        d.live_identity(k)
        getattr(d.deployment, "future_" + role)(d, k)

    def supervise(self, role):
        assert role in ("startup", "guardian") and self.boot() != self.config["prepared_boot"]
        name = "process-" + role + "-" + self.boot() + ".json"
        assert not (self.scope / name).exists()
        with (self.scope / (role + "-" + self.boot() + ".stdout")).open("xb") as out, \
                (self.scope / (role + "-" + self.boot() + ".stderr")).open("xb") as err:
            proc = subprocess.Popen([PYTHON, "-B", "-I", str(self.scope / "owner-startup-private.py"), "worker", role],
                                    stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True)
            self.put(name, {"worker_pid": proc.pid})
            try:
                assert proc.wait(timeout=300) == 0, "startup worker exited unsuccessfully"
            except BaseException:
                self.note_failure("startup-worker-failure")
                raise


def main():
    os.umask(0o077)
    host = Host(Path(__file__).resolve().parent)
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
