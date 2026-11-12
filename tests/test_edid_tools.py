"""Only synthetic EDIDs. Never ingest a machine's private panel dump into tests."""
import argparse
import json
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import phx_edid
from test_edid import extract_methods, harness


def panel(blocks=1):
    p = bytearray(blocks * 128)
    p[:8] = phx_edid.HEADER
    p[8:12] = bytes.fromhex("12347856")  # deliberately synthetic identity
    p[18:20] = bytes([1, 4])
    p[54], p[56], p[58], p[59], p[61] = 1, 0, 0xA0, 0x40, 0x60
    p[126] = blocks - 1
    for block in range(blocks):
        p[block * 128 + 127] = (-sum(p[block * 128:block * 128 + 127])) & 255
    return bytes(p)


class EDIDToolsTests(unittest.TestCase):
    def test_header_count_size_version_and_every_corrupt_byte_refused(self):
        p = panel()
        self.assertEqual(phx_edid.validate(p, (2560, 1600)), p)
        for i in range(128):
            bad = bytearray(p); bad[i] ^= 1
            with self.subTest(byte=i), self.assertRaises(ValueError):
                phx_edid.validate(bad, (2560, 1600))
        for bad in (b"", p[:-1], p + b"x", bytes(4097), panel(33), panel(2)[:-128]):
            with self.subTest(size=len(bad)), self.assertRaises(ValueError):
                phx_edid.validate(bad)
        for off, value in ((18, 0), (18, 2), (19, 5), (71, 0x80)):
            bad = bytearray(p); bad[off] = value; bad[127] = (-sum(bad[:127])) & 255
            with self.subTest(offset=off, value=value), self.assertRaises(ValueError):
                phx_edid.validate(bad, (2560, 1600))

    def test_extensions_accepted_only_complete_and_individually_checked(self):
        for blocks in (1, 2, 4, 32):
            p = panel(blocks)
            self.assertEqual(phx_edid.validate(p), p)
            if blocks > 1:
                bad = bytearray(p); bad[-2] ^= 1
                with self.assertRaisesRegex(ValueError, "checksum"):
                    phx_edid.validate(bad)

    def test_raster_matching_is_conservative_and_not_required_for_check_only(self):
        p = panel()
        with self.assertRaisesRegex(ValueError, "raster"):
            phx_edid.validate(p, (1920, 1080))
        self.assertEqual(phx_edid.validate(p), p)
        for text in ("0x1600", "2560x0", "16385x1600", "-1x1600", "2560x1600x2"):
            with self.subTest(text=text), self.assertRaises(argparse.ArgumentTypeError):
                phx_edid.native_size(text)

    def test_padding_requires_explicit_opt_in_and_must_be_whole_zero_blocks(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "input.bin"
            p.write_bytes(panel() + bytes(128))
            with self.assertRaisesRegex(ValueError, "count"):
                phx_edid.read_edid(p)
            self.assertEqual(phx_edid.read_edid(p, trim_zero_padding=True), panel())
            for extra in (b"\0", bytes(127) + b"x"):
                p.write_bytes(panel() + extra)
                with self.assertRaises(ValueError):
                    phx_edid.read_edid(p, trim_zero_padding=True)
            p.write_bytes(panel(32) + b"x")
            with self.assertRaisesRegex(ValueError, "4096"):
                phx_edid.read_edid(p, trim_zero_padding=True)

    def test_only_verified_well_formed_gpu_pci_path_is_accepted(self):
        good = "PciRoot(0x0)/Pci(0x8,0x1)/Pci(0x0,0x0)"
        self.assertEqual(phx_edid.device_path(good), good)
        for path in ("", "PciRoot(0x0)", "PciRoot(0x0)/Pci(0x20,0x0)",
                     "PciRoot(0x0)/Pci(0x0,0x8)", good + "/../EFI", "<guess>"):
            with self.subTest(path=path), self.assertRaises(argparse.ArgumentTypeError):
                phx_edid.device_path(path)

    def test_prepare_writes_only_a_local_fragment_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as t, patch.object(phx_edid, "ROOT", Path(t)):
            root = Path(t); source = root / "synthetic.bin"; source.write_bytes(panel())
            out = root / "build/review"
            gpu = "PciRoot(0x0)/Pci(0x1,0x0)"
            result = phx_edid.prepare(source, out, (2560, 1600), gpu)
            self.assertEqual(plistlib.loads((out / "DeviceProperties.plist").read_bytes()),
                             {"DeviceProperties": {"Add": {gpu: {"phx-edid": panel()}}}})
            self.assertEqual((out / "edid.bin").read_bytes(), panel())
            for key in ("hardware_read", "hardware_tested", "installed", "mode_changed"):
                self.assertIs(result[key], False)
            self.assertEqual(json.loads((out / "plan.json").read_text()), result)
            with self.assertRaises(FileExistsError):
                phx_edid.prepare(source, out, (2560, 1600), gpu)
            self.assertEqual(source.read_bytes(), panel())

    def test_invalid_input_and_unsafe_outputs_create_nothing(self):
        with tempfile.TemporaryDirectory() as t, patch.object(phx_edid, "ROOT", Path(t)):
            root = Path(t); source = root / "synthetic.bin"; source.write_bytes(panel())
            for out in (root, root / "build", root / "EFI/OC", root / "build/../../escape"):
                with self.subTest(out=out), self.assertRaises(ValueError):
                    phx_edid.prepare(source, out, (2560, 1600), "PciRoot(0x0)/Pci(0x1,0x0)")
            source.write_bytes(bytes(128))
            with self.assertRaises(ValueError):
                phx_edid.prepare(source, root / "build/review", (2560, 1600), "PciRoot(0x0)/Pci(0x1,0x0)")
            self.assertFalse((root / "build").exists())

    def test_build_symlink_cannot_redirect_output_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as elsewhere:
            root = Path(t)
            try:
                (root / "build").symlink_to(elsewhere, target_is_directory=True)
            except OSError as error:
                self.skipTest(str(error))
            source = root / "synthetic.bin"; source.write_bytes(panel())
            with patch.object(phx_edid, "ROOT", root), self.assertRaises(ValueError):
                phx_edid.prepare(source, root / "build/review", (2560, 1600), "PciRoot(0x0)/Pci(0x1,0x0)")
            self.assertEqual(list(Path(elsewhere).iterdir()), [])

    def test_actual_driver_methods_are_used_and_incomplete_extraction_is_rejected(self):
        source = (ROOT / "src/phxaccel/accel/phxfb.cpp").read_text(encoding="utf-8")
        methods = extract_methods(source)
        self.assertIn("fEdid.copyBlock", methods)
        self.assertIn("property->release()", methods)
        self.assertIn("ACTUAL_EDID_METHODS_SHA256", (ROOT / "tools/test_edid.py").read_text())
        text, digest = harness()
        self.assertEqual(len(digest), 64)
        self.assertNotIn("// ACTUAL_EDID_METHODS", text)
        for bad in ("", source + source, source.replace("getDDCBlock(", "missing("),
                    "    void loadEdid() {", source.replace("hasDDCConnect(", "missing(")):
            with self.assertRaises(RuntimeError):
                extract_methods(bad)

    def test_snapshot_is_built_before_the_base_framebuffer_can_publish_callbacks(self):
        source = (ROOT / "src/phxaccel/accel/phxfb.cpp").read_text(encoding="utf-8")
        start = source.split("bool PhxAMDFB::start(IOService *provider)", 1)[1]
        self.assertEqual(start.count("loadEdid();"), 1)
        self.assertLess(start.index("fWidth ="), start.index("loadEdid();"))
        self.assertLess(start.index("loadEdid();"), start.index("IOFramebuffer::start(provider)"))
        stop = source.split("void PhxAMDFB::stop(IOService *provider)", 1)[1]
        self.assertNotIn("fEdid.clear", stop)

    def test_cli_has_no_install_or_apply_command(self):
        result = subprocess.run([sys.executable, str(ROOT / "tools/phx_edid.py"), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("{check,prepare}", result.stdout)
        self.assertNotIn("{check,prepare,install}", result.stdout)


if __name__ == "__main__":
    unittest.main()
