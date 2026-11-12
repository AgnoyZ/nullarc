"""Synthetic geometry only. No personal memory layout or installed EFI is read."""
import copy
import json
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import phx_legacy_boot as tool


def profile():
    return dict(zip(tool.FIELDS, (0x100000000, 0x200000000, 0x200000, 0x200000, 0x10000, 0x1000,
                                  0, 0x100000, 0x3000, 0xC000, 0x1000)))


class LegacyBootToolTests(unittest.TestCase):
    def test_wire_format_has_explicit_version_flags_and_zero_reserved_fields(self):
        data = tool.encode(profile())
        self.assertEqual(len(data), 128)
        self.assertEqual(struct.unpack("<16Q", data), (1, 1, 0x100000000, 0x200000000, 0x200000, 0x200000,
                         0x10000, 0x1000, 1, 0, 0x100000, 0x3000, 0xC000, 0x1000, 0, 0))
        self.assertEqual(data, tool.encode({k: hex(v) for k, v in profile().items()}))

    def test_no_implicit_or_unknown_fields(self):
        for name in tool.FIELDS:
            bad = profile(); del bad[name]
            with self.subTest(name=name), self.assertRaises(ValueError): tool.encode(bad)
        with self.assertRaises(ValueError): tool.encode({**profile(), "default": True})
        for bad in (None, [], "profile"):
            with self.assertRaises(ValueError): tool.encode(bad)

    def test_rejects_ambiguous_negative_noninteger_and_overflow_values(self):
        for value in (True, False, -1, 1 << 64, 1.0, "-1", "+1", " 0x1000", "1e3", "0x", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                tool.encode({**profile(), "ring_offset": value})

    def test_rejects_overlap_overflow_bounds_and_alignment(self):
        for name, value in (("mc_base", 0), ("physical_base", tool.U64_MAX - 4095),
                            ("vram_bytes", 0), ("aperture_bytes", 0x100000),
                            ("ring_offset", 1), ("tmr_offset", 0x101000),
                            ("tmr_capacity", 1 << 32), ("staging_capacity", 0x1001000),
                            ("staging_offset", 0), ("console_offset", 0),
                            ("console_offset", 0x100000), ("console_offset", 0xC000),
                            ("console_offset", tool.U64_MAX - 4095), ("console_bytes", 0),
                            ("console_bytes", 4097)):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                tool.encode({**profile(), name: value})

    def test_exact_region_boundaries_are_accepted(self):
        p = profile(); p["console_offset"] = 0x9000; p["console_bytes"] = 0x3000
        self.assertEqual(len(tool.encode(p)), 128)

    def test_input_is_bounded_and_duplicate_keys_are_refused(self):
        with tempfile.TemporaryDirectory() as t:
            source = Path(t) / "input.json"
            for data in ('{"ring_offset":0,"ring_offset":4096}', 'x' * 8193):
                source.write_text(data)
                with self.assertRaises(ValueError): tool.read_profile(source)

    def test_offline_fragment_is_exact_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as t, patch.object(tool, "ROOT", Path(t)):
            root = Path(t); source = root / "input.json"; source.write_text(json.dumps(profile()))
            gpu = "PciRoot(0x0)/Pci(0x1,0x0)"; out = root / "build/review"
            plan = tool.prepare(source, out, gpu)
            data = tool.encode(profile())
            self.assertEqual(plistlib.loads((out / "DeviceProperties.plist").read_bytes()),
                             {"DeviceProperties": {"Add": {gpu: {tool.PROPERTY: data}}}})
            self.assertEqual((out / "legacy-boot.bin").read_bytes(), data)
            self.assertEqual(json.loads((out / "plan.json").read_text()), plan)
            for key in ("hardware_tested", "installed", "memory_reserved"): self.assertIs(plan[key], False)
            with self.assertRaises(FileExistsError): tool.prepare(source, out, gpu)
            self.assertEqual(set(p.name for p in out.iterdir()), {"DeviceProperties.plist", "legacy-boot.bin", "plan.json"})

    def test_output_path_and_symlink_escape_fail_before_creating_files(self):
        with tempfile.TemporaryDirectory() as t, patch.object(tool, "ROOT", Path(t) / "repo"):
            root = tool.ROOT; root.mkdir(); source = root / "input.json"; source.write_text(json.dumps(profile()))
            for out in (root, root / "build", Path(t) / "outside"):
                with self.assertRaises(ValueError): tool.prepare(source, out, "PciRoot(0x0)/Pci(0x1,0x0)")
            (root / "build").symlink_to(Path(t), target_is_directory=True)
            with self.assertRaises(ValueError): tool.prepare(source, root / "build/escaped", "PciRoot(0x0)/Pci(0x1,0x0)")
            self.assertFalse((Path(t) / "escaped").exists())

    def test_invalid_profile_or_pci_path_creates_no_output(self):
        with tempfile.TemporaryDirectory() as t, patch.object(tool, "ROOT", Path(t)):
            source = Path(t) / "input.json"; source.write_text(json.dumps(profile()))
            out = Path(t) / "build/review"
            with self.assertRaises(ValueError): tool.prepare(source, out, "../EFI")
            self.assertFalse(out.exists())

    def test_generated_bytes_and_mutations_use_the_actual_kernel_validator(self):
        compiler = shutil.which("clang++")
        self.assertIsNotNone(compiler, "native Clang is required; cannot claim validation without it")
        with tempfile.TemporaryDirectory() as t:
            source = Path(t) / "check.cpp"; binary = Path(t) / "check"
            source.write_text('''#include "PhxLegacyBoot.h"
#include <cstdio>
int main() { PhxLegacyBoot p{}; static_assert(sizeof(p) == 128, "wire");
 if (fread(&p, 1, sizeof(p), stdin) != sizeof(p)) return 2;
 return phxLegacyBootValid(&p, 0x100000000ull, 0x200000000ull, 0x200000, 0x200000) ? 0 : 1;
}
''')
            subprocess.run([compiler, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Isrc", str(source), "-o", str(binary)],
                           cwd=ROOT, check=True, capture_output=True)
            data = tool.encode(profile()); self.assertEqual(subprocess.run([str(binary)], input=data).returncode, 0)
            # Every contract word is either bound to observed geometry, a checked span, or reserved.
            words = list(struct.unpack("<16Q", data))
            for i, value in ((0, 2), (1, 0), (1, 3), (2, 0), (3, 0), (4, 0), (5, 0),
                             (6, 0), (6, tool.U64_MAX - 4095), (7, 0), (8, 2), (9, 0xC000),
                             (10, 0x101000), (11, 0), (12, 0), (13, 0), (14, 1), (15, 1)):
                mutated = copy.copy(words); mutated[i] = value
                with self.subTest(word=i, value=value):
                    self.assertEqual(subprocess.run([str(binary)], input=struct.pack("<16Q", *mutated)).returncode, 1)


if __name__ == "__main__":
    unittest.main()
