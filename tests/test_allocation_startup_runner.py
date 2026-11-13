"""Only pinned source fragments and fixture commands; never execute the reference monitor."""
from contextlib import redirect_stdout
import hashlib
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import test_allocation_startup as audit


@unittest.skipUnless(os.name == 'posix' and Path('/bin/bash').is_file() and Path('/usr/bin/grep').is_file(),
                     'POSIX CPU shell fragment harness')
class StartupSourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.reference = ROOT / 'tools/phxctl/phxboot.sh'

    def test_actual_fragments_characterize_failure_propagation_and_serial_blocks(self):
        before = self.reference.read_bytes()
        with redirect_stdout(StringIO()):
            result = audit.exercise(self.root / 'audit')
        self.assertEqual(result['cases'], 7)
        self.assertTrue(result['passed'])
        self.assertTrue(all(result['observations'].values()))
        self.assertEqual(self.reference.read_bytes(), before)
        self.assertEqual(result['reference_sha256'], hashlib.sha256(before).hexdigest())
        self.assertFalse(result['hardware_executed'])
        self.assertFalse(result['target_services_opened'])
        self.assertFalse(result['reference_script_executed_as_a_whole'])
        self.assertFalse(result['real_sysctl_nvram_marker_or_shutdown_commands'])
        self.assertEqual(result, json.loads((self.root / 'audit/report.json').read_text()))

    def test_changed_source_is_refused_before_any_child_or_output(self):
        changed = self.root / 'changed.sh'
        changed.write_bytes(self.reference.read_bytes() + b'\n')
        with patch.object(audit.subprocess, 'Popen') as child:
            with self.assertRaisesRegex(RuntimeError, 'Reference source changed'):
                audit.exercise(self.root / 'new', source=changed)
            child.assert_not_called()
        self.assertFalse((self.root / 'new').exists())

    def test_existing_output_is_not_overwritten_or_replayed(self):
        output = self.root / 'existing'
        output.mkdir()
        (output / 'sentinel').write_bytes(b'keep')
        with patch.object(audit.subprocess, 'Popen') as child:
            with self.assertRaisesRegex(RuntimeError, 'Output exists'):
                audit.exercise(output)
            child.assert_not_called()
        self.assertEqual((output / 'sentinel').read_bytes(), b'keep')

    def test_extraction_preserves_actual_source_and_excludes_launch_paths(self):
        raw = self.reference.read_bytes()
        fragments = audit.extract(raw)
        for value in fragments.values():
            self.assertIn(value.encode(), raw)
        self.assertTrue(fragments['startup.inc'].startswith(audit.START))
        self.assertNotIn('watch_hangs', fragments['startup.inc'])
        self.assertNotIn('wait_fb', fragments['startup.inc'])
        self.assertIn('m2_fail() {', fragments['recovery.inc'])

    def test_fixture_commands_require_explicit_guard(self):
        script = self.root / 'guard.sh'
        script.write_text(audit.PRELUDE + '\nprintf unsafe\n')
        result = subprocess.run(['/bin/bash', '--noprofile', '--norc', str(script)],
                                capture_output=True, env={'PATH': str(self.root)}, timeout=3)
        self.assertEqual(result.returncode, 96)
        self.assertEqual(result.stdout, b'')

    def test_reference_is_only_syntax_checked_as_a_whole(self):
        before = self.reference.read_bytes()
        result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-n', str(self.reference)],
                                capture_output=True, env={'PATH': str(self.root), 'HOME': str(self.root)}, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.reference.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
