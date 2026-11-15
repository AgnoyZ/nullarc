"""Legacy entrypoint migration; all subprocesses use a synthetic file-only helper."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReferenceLayoutSafetyTests(unittest.TestCase):
    def invoke(self, home, *args):
        return subprocess.run(['/bin/bash', '--noprofile', '--norc',
                               str(ROOT / 'tools/phxctl/bringup5.sh'), *args],
                              env={'PATH': '/usr/bin:/bin', 'HOME': str(home), 'LC_ALL': 'C'},
                              capture_output=True, text=True, timeout=5)

    def fixture(self, directory, status=0):
        home = Path(directory)
        helper = home / 'gpu/phxctl/phxctl'
        helper.parent.mkdir(parents=True)
        helper.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$HOME/calls"\nexit ' + str(status) + '\n')
        helper.chmod(0o700)
        return home

    def test_no_implicit_layout_or_reference_fallback(self):
        for count in (0, 1, 5, 7):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temporary:
                home = self.fixture(temporary)
                result = self.invoke(home, *(['1'] * count))
                self.assertEqual(64, result.returncode, result.stderr)
                self.assertFalse((home / 'calls').exists())
                self.assertIn('Explicit target-relative regions are required', result.stderr)

    def test_forwards_exact_regions_to_existing_checked_power_path(self):
        args = ['firmware folder', '0x1100000', '0x8000000', '0x4000000', '0x4000000', '0x1000000']
        for status in (0, 64, 74, 75):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as temporary:
                home = self.fixture(temporary, status)
                result = self.invoke(home, *args)
                self.assertEqual(status, result.returncode, result.stderr)
                self.assertEqual(['gfx-power-sequence', *args], (home / 'calls').read_text().splitlines())

    def test_missing_checked_helper_cannot_fall_back_to_raw_recipe(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = self.invoke(Path(temporary), *(['1'] * 6))
            self.assertEqual(127, result.returncode, result.stderr)
            self.assertFalse((Path(temporary) / 'calls').exists())


if __name__ == '__main__':
    unittest.main()
