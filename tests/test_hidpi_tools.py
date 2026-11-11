import argparse
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import phx_hidpi
from test_hidpi import color_methods


class HiDPITests(unittest.TestCase):
    def test_color_callback_extraction_rejects_missing_or_duplicate_methods(self):
        source = (ROOT / 'src/phxaccel/accel/phxfb.cpp').read_text(encoding='utf-8')
        methods = color_methods(source)
        self.assertEqual(methods.count('setGammaTable('), 2)
        self.assertEqual(methods.count('setCLUTWithEntries('), 1)
        for changed in ('', source + source, source.replace('setCLUTWithEntries(', 'missing(')):
            with self.assertRaises(RuntimeError):
                color_methods(changed)

    def test_record_is_native_backing_not_logical_points(self):
        value = phx_hidpi.display_override(0x1234, 0x5678, 2560, 1600)
        self.assertEqual(value["scale-resolutions"], [bytes.fromhex("00000a000000064000000001")])
        self.assertEqual(plistlib.loads(plistlib.dumps(value)), value)
        self.assertNotIn("IODisplayEDID", value)
        self.assertNotIn("DisplayProductName", value)

    def test_no_partial_or_oversized_native_2x_geometry(self):
        for size in ("0x0", "2561x1600", "2560x1601", "639x400", "640x399",
                     "16386x1600", "2560x16386", "4294967295x1600", "1440x900x2"):
            with self.subTest(size=size), self.assertRaises(argparse.ArgumentTypeError):
                phx_hidpi.native_size(size)
        self.assertEqual(phx_hidpi.native_size("2880x1800"), (2880, 1800))

    def test_display_ids_are_unsigned_32_bit_including_no_edid_vendor(self):
        for value in ("-1", "4294967296", "0x100000000", "unknown"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                phx_hidpi.identifier(value)
        self.assertEqual(phx_hidpi.identifier("0xabcd"), 0xABCD)
        self.assertEqual(phx_hidpi.identifier("0"), 0)
        self.assertEqual(phx_hidpi.identifier("0xffffffff"), 0xFFFFFFFF)
        vendor = phx_hidpi.identifier("0x756e6b6e")  # IOGraphics kDisplayVendorIDUnknown
        value = phx_hidpi.display_override(vendor, 0x717, 2560, 1600)
        self.assertEqual(plistlib.loads(plistlib.dumps(value))["DisplayVendorID"], vendor)

    def test_fresh_output_and_explicit_unverified_plan(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(phx_hidpi, "ROOT", Path(temporary)):
            out = Path(temporary) / "build/hidpi"
            result = phx_hidpi.generate(out, 0x1234, 0x5678, (2560, 1600))
            self.assertEqual(result["logical_points"], [1280, 800])
            for flag in ("hardware_tested", "installed", "mode_changed", "resampling_supported"):
                self.assertIs(result[flag], False)
            data = (out / result["override"]).read_bytes()
            self.assertEqual(plistlib.loads(data)["DisplayVendorID"], 0x1234)
            with self.assertRaises(FileExistsError):
                phx_hidpi.generate(out, 0x1234, 0x5678, (2560, 1600))
            self.assertEqual((out / result["override"]).read_bytes(), data)

    def test_refuses_system_or_unrelated_output_before_writing(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(phx_hidpi, "ROOT", Path(temporary)):
            for out in (Path(temporary), Path(temporary) / "build", Path(temporary) / "EFI/OC"):
                with self.subTest(out=out), self.assertRaisesRegex(ValueError, "fresh subdirectory"):
                    phx_hidpi.generate(out, 0x1234, 0x5678, (2560, 1600))
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_no_size_options_for_unimplemented_downsampling(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/phx_hidpi.py"), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertNotIn("--logical", result.stdout)
        self.assertIn("never install", result.stdout)

    def test_refuses_build_directory_redirected_outside_repository(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as elsewhere:
            root = Path(temporary)
            try:
                (root / "build").symlink_to(elsewhere, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"directory symlinks unavailable: {error}")
            with patch.object(phx_hidpi, "ROOT", root), self.assertRaisesRegex(ValueError, "fresh subdirectory"):
                phx_hidpi.generate(root / "build/hidpi", 0x1234, 0x5678, (2560, 1600))
            self.assertEqual(list(Path(elsewhere).iterdir()), [])

    def test_driver_gate_and_physical_copy_contract(self):
        source = (ROOT / "src/phxaccel/accel/phxfb.cpp").read_text(encoding="utf-8")
        self.assertIn('PE_parse_boot_argn("phxfbhires", &hiRes, sizeof hiRes) && hiRes == 1', source)
        self.assertIn("phx780m::nativeHiDPIEligible(fWidth, fHeight, fRowBytes)", source)
        self.assertIn("pi->activeWidth = fWidth; pi->activeHeight = fHeight;", source)
        self.assertIn("getDisplayModeCount() override { return 1; }", source)
        self.assertNotIn("kIOScaleCanDownSamplePixels", source)
        copy = (ROOT / "src/phxaccel/accel/nvrm-accel.cpp").read_text(encoding="utf-8")
        self.assertIn("if (w != q.width || h != q.height) NVIOP_FAIL", copy)


if __name__ == "__main__":
    unittest.main()
