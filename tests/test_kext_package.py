import io
from pathlib import Path
import plistlib
import struct
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import package_kexts as pkg


class KextPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bundle = Path(self.temp.name) / "PhxAccel.kext"
        binary = self.bundle / "Contents/MacOS/PhxAccel"
        binary.parent.mkdir(parents=True)
        # Structural fixture only; not a signed, loadable kext.
        binary.write_bytes(struct.pack("<8I", 0xFEEDFACF, 0x01000007, 3, 11, 1, 72, 0, 0)
                           + struct.pack("<II16sQQQQIIII", 0x19, 72, b"__TEXT", 0, 104, 0, 104, 7, 5, 0, 0))
        (self.bundle / "Contents/Info.plist").write_bytes(plistlib.dumps({
            "CFBundlePackageType": "KEXT", "CFBundleExecutable": "PhxAccel",
            "CFBundleIdentifier": "com.luuumi.PhxAccel"}))

    def test_expected_bundle_is_inspected_and_every_file_is_hashed(self):
        result = pkg.check_bundle(self.bundle, "PhxAccel")
        self.assertEqual(result["architecture"], "x86_64")
        self.assertEqual(len(result["files_sha256"]), 2)

    def test_private_or_extra_bundle_file_is_refused(self):
        (self.bundle / "Contents/panel-edid.bin").write_bytes(b"private")
        with self.assertRaisesRegex(ValueError, "Unexpected kext file"):
            pkg.check_bundle(self.bundle, "PhxAccel")

    def test_wrong_component_identity_is_refused(self):
        with self.assertRaises(ValueError):
            pkg.check_bundle(self.bundle, "PhxBringup")

    def test_corrupted_executable_is_refused(self):
        (self.bundle / "Contents/MacOS/PhxAccel").write_bytes(b"not a kext")
        with self.assertRaises(ValueError):
            pkg.check_bundle(self.bundle, "PhxAccel")

    def test_source_export_excludes_worktree_and_unsafe_entries(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w") as archive:
            entry = tarfile.TarInfo("source/private-link")
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/private/secret"
            archive.addfile(entry)
        with patch.object(pkg, "git", return_value=data.getvalue()):
            with self.assertRaisesRegex(ValueError, "non-regular"):
                pkg.source_archive(ROOT, ("src",), Path(self.temp.name) / "source.tar.gz", "source/")

    def test_workflow_is_manual_scoped_and_uploads_only_the_package(self):
        workflow = (ROOT / ".github/workflows/kext-artifacts.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("  push:", workflow)
        self.assertNotIn("pull_request", workflow)
        self.assertIn("github.repository == 'AgnoyZ/nullarc'", workflow)
        self.assertIn("runs-on: macos-15-intel", workflow)
        self.assertIn("path: build/kext-upload/upload/", workflow)
        self.assertIn("if-no-files-found: error", workflow)
        self.assertNotIn("continue-on-error", workflow)
        self.assertNotIn("sudo ", workflow)


if __name__ == "__main__":
    unittest.main()
