#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build34_dcn_mapper_probe_stage import DRIVER_SHA256, stage

DRIVER = ROOT / 'src/phxbringup/PhxBringup.cpp'
FIXTURE = Path(__file__).with_suffix('.cpp')


class DcnMapperProbeTests(unittest.TestCase):
    def test_stage_is_exact_build34_and_opt_in(self):
        original = DRIVER.read_bytes()
        with self.assertRaisesRegex(ValueError, 'source drift'):
            stage(original + b'\n')
        staged = stage(original)
        rendered = staged.decode()
        self.assertIn('#include "PhxDcnMapperProbe.h"', rendered)
        self.assertIn('PE_parse_boot_argn("-phx-dcnmapperprobe"', rendered)
        self.assertIn('dcnMapperProbeRequested &&', rendered)
        self.assertIn('pci->configRead32(kIOPCIConfigVendorID) == 0x19001002u', rendered)
        self.assertIn('setProperty("phx-dcn-address-domain-proven", false);', rendered)
        self.assertEqual(rendered.count('probeDeviceMapperNoWait<IOMapper>'), 1)
        probe = (ROOT / 'src/phxbringup/PhxDcnMapperProbe.h').read_text()
        self.assertEqual(probe.count('IOService::getMatchingServices'), 1)
        self.assertNotIn('copyMapperForDevice', probe)
        self.assertNotIn('waitForMatchingService', probe)
        self.assertEqual(len(DRIVER_SHA256), 64)

    def test_cpu_lookup_lifetime_fixture(self):
        with tempfile.TemporaryDirectory(prefix='phx34-mapper-probe-CPU-') as directory:
            binary = Path(directory) / 'mapper-probe-CPU-only'
            built = subprocess.run([
                *shlex.split(os.environ.get('CXX', 'clang++')), '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                '-I' + str(ROOT / 'tests/build34_dcn_mapper'), '-I' + str(ROOT / 'src/phxbringup'),
                str(FIXTURE), '-o', str(binary),
            ], capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stderr)
            if sys.platform == 'darwin':
                linkage = subprocess.check_output(['otool', '-L', str(binary)], text=True, timeout=15)
                self.assertNotIn('IOKit.framework', linkage)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '[PASS] build34 non-waiting mapper probe CPU-only\n')


if __name__ == '__main__':
    unittest.main()
