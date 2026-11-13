"""Packaging fixtures are structural data, not signed or runnable GPU libraries."""
import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import package_radv as pr


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.PIPE).decode().strip()


def commit(root):
    git(root, "add", ".")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
    return git(root, "rev-parse", "HEAD")


def write(root, name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode())


def structural_library():
    # One valid-looking __TEXT segment, with no executable instructions or signature.
    return struct.pack("<8I", 0xFEEDFACF, 0x01000007, 3, 6, 1, 72, 0, 0) + struct.pack(
        "<II16sQQQQIIII", 0x19, 72, b"__TEXT", 0, 104, 0, 104, 7, 5, 0, 0)


class PackageFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root, self.mesa, self.cobalt, self.headers = [base / n for n in ("project", "mesa", "cobalt", "headers")]
        for directory in (self.root, self.mesa, self.cobalt, self.headers):
            directory.mkdir()
            git(directory, "init", "-q")
        for name in pr.SOURCE_PATHS:
            source = ROOT / name
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copyfile(source, destination)
        write(self.root, ".gitignore", "build/\n")
        for directory, prefix, count in ((self.cobalt, "mesa-patches", 9), (self.root, "mesa-patches-phoenix", 7)):
            for i in range(1, count + 1):
                write(directory, f"{prefix}/{i:04d}-fixture.patch", f"fixture patch {i}\n")
            write(directory, prefix + "/README.txt", "Fixture patch license and ordering\n")
        write(self.cobalt, "LICENSE", "Fixture MIT notice\n")
        write(self.cobalt, "third-party/THIRD-PARTY-LICENSES.txt", "Fixture third party notices\n")
        write(self.cobalt, "src/navi48-bringup/src/Navi48NativeABI.h", "/* Fixture ABI */\n")
        write(self.mesa, "licenses/MIT", "Fixture MIT\n")
        write(self.mesa, "licenses/exceptions/fixture", "Fixture exception\n")
        write(self.mesa, "docs/license.rst", "Fixture per-file terms\n")
        write(self.mesa, "source.c", "/* Fixture source, never compiled */\n")
        (self.mesa / "source-link.c").symlink_to("source.c")
        write(self.headers, "LICENSE.md", "Fixture terms\n")
        write(self.headers, "LICENSES/MIT.txt", "Fixture MIT\n")
        write(self.headers, "LICENSES/Apache-2.0.txt", "Fixture Apache\n")
        write(self.headers, "include/vulkan/vulkan.h", "/* Fixture headers */\n")
        lock = json.loads((ROOT / "upstream.lock.json").read_text())
        for name, source in (("Mesa", self.mesa), ("Cobalt64", self.cobalt), ("Vulkan-Headers", self.headers), ("nullarc", self.root)):
            lock[name]["commit"] = commit(source)
        self.lock = lock
        write(self.root, "upstream.lock.json", json.dumps(lock))
        self.head = commit(self.root)
        self.series = pr.patch_inputs(self.root, self.cobalt, lock, self.head)
        self.expected = pr.provenance(lock, self.series)
        self.notices = pr.notice_inputs(self.mesa, self.cobalt, lock, self.expected)
        self.artifacts = self.root / "build/artifacts"
        for name, data in self.notices.items():
            write(self.artifacts, name, data)
        write(self.artifacts, "nvmtl/" + pr.LIBRARY, structural_library())
        self.report = {**self.expected, **pr.inspect_macho(self.artifacts / "nvmtl" / pr.LIBRARY, 6),
            "project_commit": self.head, "native_transport_layout_verified": True,
            "metal_stack_complete": False, "host": "fixture-host", "runtime_dependency_policy": "system-only",
            "runtime_layout": "standalone-nvmtl", "dependencies": ["/usr/lib/libSystem.B.dylib"],
            "meson_version": "fixture", "ninja_version": "fixture", "glslang_version": "fixture", "compiler": "fixture",
            "runtime_tests": {n: {"runtime_loaded": True, "physical_devices": 0, "gpu_submitted": False}
                              for n in ("native", "reject_mock", "reject_host_only", "reject_other_gpu")}}
        self.save_report()
        self.icd = {"file_format_version": "1.0.0", "ICD": {"library_path": "./" + pr.LIBRARY, "api_version": "1.4.0"}}
        self.save_icd()

    def save_report(self):
        write(self.artifacts, "nvmtl/radv-build-report.json", json.dumps(self.report))

    def save_icd(self):
        write(self.artifacts, "nvmtl/radeon_icd.json", json.dumps(self.icd))

    def check(self):
        return pr.check_inputs(self.artifacts, self.notices, self.expected, self.head)

    def test_exact_standalone_report_and_notices(self):
        self.assertEqual(self.report, self.check())
        self.assertEqual(18, len(self.series))

    def test_builder_provenance_key_order_is_semantic_but_changes_are_rejected(self):
        # prepare_radv emits patches before the two booleans; JSON object order is not provenance.
        data = {key: self.expected[key] for key in ("mesa_commit", "cobalt_commit", "nullarc_commit",
                                                   "patches", "hardware_tested", "deployment_performed")}
        target = self.artifacts / "DEPENDENCY-LICENSES/Mesa-RADV/source-provenance.json"
        target.write_text(json.dumps(data, indent=2) + "\n")
        self.assertEqual(self.report, self.check())
        data["patches"] = list(reversed(data["patches"]))
        target.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, "differs from pinned"):
            self.check()

    def test_extra_binary_log_and_empty_directory_rejected(self):
        for name in ("nvmtl/other.dylib", "raw.log", "NVMTLDriver.bundle"):
            path = self.artifacts / name
            if name.endswith("bundle"):
                path.mkdir()
            else:
                write(self.artifacts, name, b"unapproved")
            with self.assertRaisesRegex(ValueError, "Unexpected artifact"):
                self.check()
            if path.is_dir():
                path.rmdir()
            else:
                path.unlink()

    def test_symlink_even_to_allowed_bytes_rejected(self):
        library = self.artifacts / "nvmtl" / pr.LIBRARY
        library.unlink()
        library.symlink_to(self.mesa / "source.c")
        with self.assertRaisesRegex(ValueError, "symlinks"):
            self.check()

    def test_missing_license_or_changed_notice_rejected(self):
        path = self.artifacts / "DEPENDENCY-LICENSES/Mesa-RADV/licenses/MIT"
        path.write_text("wrong attribution")
        with self.assertRaisesRegex(ValueError, "differs from pinned"):
            self.check()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Missing required"):
            self.check()

    def test_source_patch_binary_identity_and_evidence_rejections(self):
        original = copy.deepcopy(self.report)
        for key, value in (("project_commit", "0" * 40), ("sha256", "0" * 64),
                           ("native_transport_layout_verified", False), ("metal_stack_complete", True),
                           ("patches", list(reversed(original["patches"]))),
                           ("runtime_tests", {}), ("runtime_layout", "plugin-relative"),
                           ("dependencies", ["@rpath/other.dylib"]), ("compiler", "/home/fixture/toolchain")):
            self.report = {**copy.deepcopy(original), key: value}
            self.save_report()
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()

    def test_nonrelocatable_or_extra_icd_fields_rejected(self):
        self.icd["ICD"]["library_arch"] = "64"
        self.save_icd()
        self.check()
        for data in ({**self.icd, "private": "log"},
                     {**self.icd, "ICD": {**self.icd["ICD"], "library_path": "/tmp/old.dylib"}},
                     {**self.icd, "ICD": {**self.icd["ICD"], "library_arch": "32"}}):
            self.icd = data
            self.save_icd()
            with self.assertRaisesRegex(ValueError, "relocatable"):
                self.check()

    def test_end_to_end_manifest_sources_only_and_normalized_archive(self):
        # Mock native validation ONLY for this non-executable fixture. Real CI never bypasses it.
        with patch.object(pr, "check_native") as native, patch.object(pr.platform, "system", return_value="Darwin"), patch.object(pr.platform, "machine", return_value="x86_64"):
            with patch("builtins.print"):
                archive = pr.package(self.mesa, self.cobalt, self.headers, self.artifacts, self.root / "build/package", self.root)
        self.assertEqual(2, native.call_count)
        self.assertEqual({archive.name, "SHA256SUMS"}, {p.name for p in archive.parent.iterdir()})
        self.assertEqual(pr.sha256(archive), (archive.parent / "SHA256SUMS").read_text().split()[0])
        with tarfile.open(archive) as outer:
            members = outer.getmembers()
            self.assertTrue(all(m.uid == m.gid == m.mtime == 0 and m.uname == m.gname == "" for m in members))
            prefix = members[0].name + "/"
            files = {m.name[len(prefix):]: outer.extractfile(m).read() for m in members if m.isfile()}
        self.assertEqual([pr.LIBRARY], sorted(n for n in files if n.endswith(".dylib")))
        for line in files["SHA256SUMS"].decode().splitlines():
            checksum, name = line.split("  ", 1)
            self.assertEqual(checksum, hashlib.sha256(files[name]).hexdigest())
        self.assertEqual(set(files) - {"SHA256SUMS"}, {line.split("  ", 1)[1] for line in files["SHA256SUMS"].decode().splitlines()})
        with tarfile.open(fileobj=io.BytesIO(files["SOURCE/mesa-base.tar.gz"])) as source:
            self.assertTrue(source.getmember("mesa/source-link.c").issym())
            self.assertEqual(b"/* Fixture source, never compiled */\n", source.extractfile("mesa/source.c").read())
        series = json.loads(files["SOURCE/patch-series.json"])["patches"]
        self.assertEqual(18, len(series))
        for entry in series:
            self.assertEqual(entry["sha256"], hashlib.sha256(files["SOURCE/" + entry["path"]]).hexdigest())
        self.assertFalse(json.loads(files["package-report.json"])["hardware_tested"])


class ArchiveSafetyTests(unittest.TestCase):
    def test_paths_links_and_special_files(self):
        for name, kind, link in (("../escape", tarfile.REGTYPE, ""), ("/mesa/file", tarfile.REGTYPE, ""),
                                 ("mesa/../file", tarfile.REGTYPE, ""), ("other/file", tarfile.REGTYPE, ""),
                                 ("mesa/link", tarfile.SYMTYPE, "../escape"), ("mesa/link", tarfile.SYMTYPE, "/etc/passwd"),
                                 ("mesa/link", tarfile.LNKTYPE, "mesa/file"), ("mesa/pipe", tarfile.FIFOTYPE, "")):
            item = tarfile.TarInfo(name)
            item.type, item.linkname = kind, link
            with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                pr.safe_member(item, "mesa")
        valid = tarfile.TarInfo("mesa/src/link")
        valid.type, valid.linkname = tarfile.SYMTYPE, "../source.c"
        self.assertEqual(0, pr.safe_member(valid, "mesa").mtime)

    def test_manual_narrow_workflow_and_source_scope(self):
        workflow = (ROOT / ".github/workflows/radv-artifacts.yml").read_text()
        for required in ("workflow_dispatch:", "runs-on: macos-15-intel", "fetch-depth: 0", "retention-days: 7",
                         "path: build/radv-upload/upload/", "persist-credentials: false", "contents: read",
                         "github.ref == 'refs/heads/downstream/780m-tahoe'"):
            self.assertIn(required, workflow)
        for excluded in ("  push:", "  pull_request:", "sudo ", "build_macos.py", "package_kexts.py", "phxctl", "shutdown"):
            self.assertNotIn(excluded, workflow)
        self.assertNotIn("src/phxaccel", pr.SOURCE_PATHS)
        self.assertNotIn("src/nmplugin", pr.SOURCE_PATHS)
        self.assertIn("github.event.repository.private", (ROOT / ".github/workflows/build.yml").read_text())


if __name__ == "__main__":
    unittest.main()
