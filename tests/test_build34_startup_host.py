#!/usr/bin/env python3
"""CPU/filesystem tests; no live launch job, driver or power operation."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SPEC = importlib.util.spec_from_file_location(
    "build34_startup_host",
    Path(__file__).resolve().parents[1] / "tools/build34_startup_host.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class IdentityTests(unittest.TestCase):
    def text(self, *, executable=m.PYTHON, uid=0, group=123, role="guardian"):
        return f"{uid} {group} S {executable} -B -I /scope/owner-startup-private.py worker {role}\n"

    def match(self, text):
        return m.process_matches(text, pid=123, script=Path("/scope/owner-startup-private.py"), role="guardian")

    def test_declared_and_real_python_paths_have_identical_exact_arguments(self):
        self.assertIs(self.match(self.text()), True)
        self.assertIs(self.match(self.text(executable=m.os.path.realpath(m.PYTHON))), True)
        self.assertIs(self.match(self.text(executable=m.PYTHON_APP)), True)

    def test_nonroot_other_group_or_wrong_worker_is_never_signalled(self):
        for kw in ({"uid": 501}, {"group": 124}, {"role": "startup"}, {"executable": "/unknown/python"}):
            self.assertIs(self.match(self.text(**kw)), False)
        self.assertIs(self.match(self.text().replace("/scope/", "/unrelated/")), False)
        self.assertIs(self.match(self.text() + " extra"), False)

    def test_zombie_is_distinct_from_live_verified_process(self):
        self.assertEqual(self.match("0 123 Z (Python)"), "zombie")

    def test_actual_CLT_exec_transition_still_matches_only_its_exact_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            script = Path(directory) / "worker.py"
            script.write_text("import time; time.sleep(5)\n")
            child = subprocess.Popen([m.PYTHON, "-B", "-I", str(script), "worker", "guardian"],
                                     start_new_session=True)
            try:
                time.sleep(0.2)
                text = subprocess.check_output(["/bin/ps", "-ww", "-p", str(child.pid),
                                                "-o", "uid=,pgid=,stat=,command="], text=True)
                # Production requires root. This unit test runs as the caller,
                # so substitute only that field to test real argv/group output.
                text = "0 " + text.strip().split(None, 1)[1]
                self.assertIs(m.process_matches(text, pid=child.pid, script=script, role="guardian"), True)
                self.assertIs(m.process_matches(text, pid=child.pid, script=script, role="startup"), False)
            finally:
                child.terminate();child.wait(timeout=3)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.host = m.Host.__new__(m.Host)
        self.host.scope = self.root
        self.host.boot = lambda: "trial"

    def test_uncertain_admission_is_recovery_reason_not_false_success(self):
        self.host._read_admission = Mock(side_effect=AssertionError("framebuffer"))
        self.assertEqual(self.host.read_admission(), "admission-exception")
        self.assertEqual(json.loads((self.root / "failure-trial.json").read_text()),
                         {"reason": "AssertionError"})

    def test_no_probe_is_retired_by_startup_recovery(self):
        (self.root / "GPU-probe.intent").write_text("{}")
        with patch.object(m.os, "killpg") as kill:
            self.assertFalse(self.host.quiesce())
            kill.assert_not_called()

    def test_unknown_worker_identity_stops_recovery(self):
        (self.root / "process-startup-trial.json").write_text(json.dumps({"worker_pid": 123}))
        with patch.object(m, "secure"), patch.object(m.os, "getpgrp", return_value=456), \
                patch.object(m.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="0 123 S /unknown")), \
                patch.object(m.os, "killpg") as kill:
            self.assertFalse(self.host.quiesce())
            kill.assert_not_called()

    def test_restore_jobs_refuses_unknown_second_file_before_any_write(self):
        first, second = self.root / "first.plist", self.root / "second.plist"
        first.write_bytes(b"scoped"); second.write_bytes(b"unknown")
        backup = self.root / "accepted.plist"; backup.write_bytes(b"accepted")
        digest = lambda b: hashlib.sha256(b).hexdigest()
        c = {"jobs": {str(p): digest(b"scoped") for p in (first, second)},
             "recovery_jobs": {str(p): {"backup": backup.name, "sha256": digest(b"accepted")}
                               for p in (first, second)}}
        self.host.contract = lambda: c
        self.host.readonly = SimpleNamespace(atomic_file=Mock())
        with patch.object(m, "secure"), self.assertRaises(AssertionError):
            self.host.restore_jobs()
        self.host.readonly.atomic_file.assert_not_called()

    def test_watch_success_restores_normal_jobs_and_retires_only_own_watcher(self):
        watcher = self.root / "watcher.plist"; watcher.write_bytes(b"ours")
        self.host.config = {"prepared_boot": "preparation", "watcher_job": str(watcher),
                            "watcher_job_sha256": m.sha(watcher)}
        self.host.policy = SimpleNamespace(watch=Mock(return_value="accepted"))
        self.host.restore_jobs = Mock()
        with patch.object(m, "secure"), patch.object(m.subprocess, "run") as run:
            self.host.watch()
        self.host.restore_jobs.assert_called_once()
        self.assertFalse(watcher.exists())
        run.assert_not_called()

    def test_changed_watcher_job_is_retained(self):
        watcher = self.root / "watcher.plist"; watcher.write_bytes(b"ours")
        expected = m.sha(watcher);watcher.write_bytes(b"unrelated")
        self.host.config = {"prepared_boot": "preparation", "watcher_job": str(watcher),
                            "watcher_job_sha256": expected}
        self.host.policy = SimpleNamespace(watch=Mock(return_value="closed"))
        with patch.object(m, "secure"), self.assertRaises(AssertionError):
            self.host.watch()
        self.assertEqual(watcher.read_bytes(), b"unrelated")


if __name__ == "__main__":
    unittest.main()
