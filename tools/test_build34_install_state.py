#!/usr/bin/env python3
"""No GPU APIs: regression coverage for the installed/OFF monitor mismatch."""

import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location(
    "tested_build34_install_state", Path(__file__).with_name("build34_install_state.py"))
_state = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_state)
kill_switch_required = _state.kill_switch_required
verify_kill_switch = _state.verify_kill_switch


EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()


class InstallStateTests(unittest.TestCase):
    def state(self, **changes):
        values = dict(owner_requested_install=True, installation_started=False,
                      installation_accepted=False, recovery_started=False)
        values.update(changes)
        return kill_switch_required(**values)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.marker = self.root / "off"

    def verify(self, required):
        verify_kill_switch(self.marker, EMPTY_SHA256, required=required,
                           expected_uid=os.getuid())

    def create_marker(self):
        self.marker.touch(mode=0o600)

    def test_preparation_requires_off(self):
        self.assertTrue(self.state())

    def test_install_intent_alone_still_requires_off(self):
        self.assertTrue(self.state(installation_started=True))

    def test_accepted_install_requires_absence(self):
        self.assertFalse(self.state(installation_started=True, installation_accepted=True))

    def test_recovery_after_acceptance_requires_off_again(self):
        self.assertTrue(self.state(installation_started=True, installation_accepted=True,
                                   recovery_started=True))

    def test_recovery_before_acceptance_requires_off(self):
        self.assertTrue(self.state(recovery_started=True))

    def test_acceptance_without_intent_is_refused(self):
        with self.assertRaises(ValueError):
            self.state(installation_accepted=True)

    def test_unrequested_acceptance_is_refused(self):
        with self.assertRaises(ValueError):
            self.state(owner_requested_install=False, installation_started=True,
                       installation_accepted=True)

    def test_non_boolean_state_is_refused(self):
        for value in [None, 0, 1, "false"]:
            with self.assertRaises(ValueError):
                self.state(recovery_started=value)

    def test_baseline_exact_empty_marker_is_accepted(self):
        self.create_marker()
        self.verify(True)

    def test_missing_required_off_marker_is_still_an_error(self):
        with self.assertRaises(FileNotFoundError):
            self.verify(True)

    def test_enabled_missing_marker_is_expected_regression(self):
        required = self.state(installation_started=True, installation_accepted=True)
        self.verify(required)

    def test_recreated_kill_switch_stops_enabled_operation(self):
        self.create_marker()
        with self.assertRaises(ValueError):
            self.verify(False)

    def test_dangling_symlink_is_not_expected_absence(self):
        self.marker.symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            self.verify(False)

    def test_symlink_does_not_replace_baseline_marker(self):
        target = self.root / "target"
        target.touch(mode=0o600)
        self.marker.symlink_to(target)
        with self.assertRaises(ValueError):
            self.verify(True)

    def test_changed_content_is_refused(self):
        self.create_marker()
        self.marker.write_bytes(b"foreign")
        with self.assertRaises(ValueError):
            self.verify(True)

    def test_writable_marker_is_refused(self):
        self.create_marker()
        self.marker.chmod(0o622)
        with self.assertRaises(ValueError):
            self.verify(True)

    def test_hardlinked_marker_is_refused(self):
        self.create_marker()
        os.link(self.marker, self.root / "alias")
        with self.assertRaises(ValueError):
            self.verify(True)

    def test_wrong_owner_is_refused(self):
        self.create_marker()
        with self.assertRaises(ValueError):
            verify_kill_switch(self.marker, EMPTY_SHA256, required=True,
                               expected_uid=os.getuid() + 1)

    def test_invalid_policy_is_refused(self):
        with self.assertRaises(ValueError):
            self.verify(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
