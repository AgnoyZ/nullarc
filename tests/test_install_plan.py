"""Exercise the install planner: the steps it writes, and every layout it refuses.

Every fixture here is a synthetic OpenCore tree with a synthetic thin Mach-O; none of it comes from a real EFI,
and none of it is installed. The planner has no apply mode, so these tests also check that the tree is
byte-identical afterwards.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import plistlib
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/phx_install_plan.py"
BOOT_ARGS_GUID = "7C436110-AB2A-4BBB-A880-FE41995C9F82"


def macho():
    """A thin x86_64 MH_KEXT_BUNDLE: 32-byte header, one __TEXT segment, 16 bytes of body."""
    header = struct.pack("<IIIIIIII", 0xFEEDFACF, 0x01000007, 0, 11, 1, 72, 0x4 | 0x80, 0)
    segment = struct.pack("<II16sQQQQIIII", 0x19, 72, b"__TEXT", 0, 0x1000, 104, 16, 7, 5, 0, 0)
    return header + segment + b"\0" * 16


def write_kext(parent, name, identifier, executable=None, binary=None):
    bundle = Path(parent) / name
    (bundle / "Contents/MacOS").mkdir(parents=True)
    executable = executable or name[: -len(".kext")]
    info = {"CFBundleIdentifier": identifier, "CFBundleExecutable": executable, "CFBundlePackageType": "KEXT"}
    (bundle / "Contents/Info.plist").write_bytes(plistlib.dumps(info))
    (bundle / "Contents/MacOS" / executable).write_bytes(macho() if binary is None else binary)
    return bundle


def write_layout(directory, *, kernel_add=None, kernel_block=None, boot_args="", csr=None, secure_boot=None,
                 write_config=True):
    efi_root = Path(directory) / "EFIROOT"
    oc = efi_root / "EFI/OC"
    oc.mkdir(parents=True)
    if write_config:
        nvram_entry = {}
        if boot_args:
            nvram_entry["boot-args"] = boot_args
        if csr is not None:
            nvram_entry["csr-active-config"] = csr
        config = {
            "Kernel": {
                "Add": [{"BundlePath": "Lilu.kext", "Enabled": True, "MinKernel": "20.0.0"}]
                if kernel_add is None else kernel_add,
                "Block": kernel_block or [],
            },
            "NVRAM": {"Add": {BOOT_ARGS_GUID: nvram_entry}, "Delete": {}},
            "Misc": {"Security": {} if secure_boot is None else {"SecureBootModel": secure_boot}},
        }
        (oc / "config.plist").write_bytes(plistlib.dumps(config))
    return efi_root


def digest_of(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class InstallPlanTests(unittest.TestCase):
    def run_tool(self, *arguments):
        return subprocess.run([sys.executable, str(TOOL), *arguments], capture_output=True, text=True, timeout=300)

    def plan_json(self, *arguments):
        result = self.run_tool(*arguments, "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_a_clean_layout_produces_operator_steps_and_nothing_else(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary, boot_args="-v keepsyms=1")
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            plan = self.plan_json("--efi-root", str(efi_root), "--kext", str(bundle))
            self.assertEqual(plan["mode"], "plan-only")
            self.assertEqual([step["order"] for step in plan["steps"]], list(range(1, len(plan["steps"]) + 1)))
            titles = [step["title"] for step in plan["steps"]]
            self.assertEqual(titles[0], "Make the return path first")
            self.assertIn("Copy the kext bundle(s) into the EFI", titles)
            self.assertIn("Add the Kernel > Add entries", titles)
            self.assertIn("Add the boot argument", titles)
            self.assertTrue(any("phx_baseline.sh" in step["detail"] for step in plan["steps"]))
            # The digest of what would be copied is in the plan, so the copy can be checked afterwards.
            self.assertIn(plan["kexts"][0]["tree_sha256"], " ".join(step["detail"] for step in plan["steps"]))
            self.assertEqual(plan["claims"]["config_written"], False)
            self.assertEqual(plan["claims"]["efi_written"], False)
            self.assertEqual(plan["claims"]["hardware_execution_established"], False)
            self.assertTrue(plan["rollback"])

    def test_the_config_is_byte_identical_afterwards(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary, boot_args="")
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            config = efi_root / "EFI/OC/config.plist"
            before = digest_of(config)
            listing_before = sorted(str(path.relative_to(efi_root)) for path in efi_root.rglob("*"))
            result = self.run_tool("--efi-root", str(efi_root), "--kext", str(bundle))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(digest_of(config), before)
            listing_after = sorted(str(path.relative_to(efi_root)) for path in efi_root.rglob("*"))
            self.assertEqual(listing_before, listing_after, "the planner must not add or remove anything")

    def test_refuses_a_configuration_that_is_not_opencore(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = Path(temporary) / "EFIROOT"
            (efi_root / "EFI/OC").mkdir(parents=True)
            (efi_root / "EFI/OC/config.plist").write_bytes(plistlib.dumps({"SystemParameters": {}}))
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            result = self.run_tool("--efi-root", str(efi_root), "--kext", str(bundle))
            self.assertEqual(result.returncode, 3)
            self.assertIn("Kernel > Add", result.stderr)

    def test_refuses_a_missing_configuration(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary, write_config=False)
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            result = self.run_tool("--efi-root", str(efi_root), "--kext", str(bundle))
            self.assertEqual(result.returncode, 3)
            self.assertIn("no OpenCore config", result.stderr)

    def test_refuses_a_system_location(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            result = self.run_tool("--efi-root", "/Library/Extensions", "--kext", str(bundle))
            self.assertEqual(result.returncode, 3)
            self.assertIn("system location", result.stderr)

    def test_refuses_a_bundle_that_is_not_one_of_this_projects_kexts(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary)
            bundle = write_kext(temporary, "PhxBringup.kext", "com.example.Other")
            result = self.run_tool("--efi-root", str(efi_root), "--kext", str(bundle))
            self.assertEqual(result.returncode, 3)
            self.assertIn("com.example.Other", result.stderr)

    def test_refuses_a_bundle_whose_binary_is_not_a_kext(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary)
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup", binary=b"#!/bin/sh\nexit 0\n")
            result = self.run_tool("--efi-root", str(efi_root), "--kext", str(bundle))
            self.assertEqual(result.returncode, 3)
            self.assertIn("not a usable kext bundle", result.stderr)

    def test_refuses_a_digest_that_does_not_match(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary)
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            result = self.run_tool("--efi-root", str(efi_root), "--kext", str(bundle),
                                   "--expect-sha256", "PhxBringup.kext=" + "0" * 64)
            self.assertEqual(result.returncode, 3)
            self.assertIn("digest", result.stderr)

    def test_the_security_changes_are_named_as_decisions_never_as_steps(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary, boot_args="-v")
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            plan = self.plan_json("--efi-root", str(efi_root), "--kext", str(bundle))
            decisions = " ".join(plan["operator_decisions"])
            self.assertIn("amfi=0x80", decisions)
            self.assertIn("does not change", decisions)
            self.assertIn("will not attach", decisions)
            steps = " ".join(step["detail"] for step in plan["steps"])
            self.assertNotIn("amfi", steps, "weakening OS security must never be written up as a step")
            self.assertNotIn("csr-active-config", steps)

    def test_an_existing_entry_and_boot_argument_become_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(
                temporary, boot_args="phx780m=1 -v", csr=b"p\x08\x00\x00", secure_boot="Disabled",
                kernel_add=[{"BundlePath": "Lilu.kext", "Enabled": True},
                            {"BundlePath": "PhxBringup.kext", "Enabled": True, "MinKernel": "25.0.0"}])
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            plan = self.plan_json("--efi-root", str(efi_root), "--kext", str(bundle))
            titles = [step["title"] for step in plan["steps"]]
            self.assertIn("Verify the boot argument", titles)
            notes = " ".join(plan["notes"])
            self.assertIn("already lists PhxBringup.kext", notes)
            self.assertIn("already contain `phx780m=1`", notes)
            self.assertIn("already set", notes)

    def test_blocked_extensions_are_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary, kernel_block=[{"Identifier": "com.apple.iokit.IONDRVSupport",
                                                             "Enabled": True}])
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            plan = self.plan_json("--efi-root", str(efi_root), "--kext", str(bundle))
            self.assertTrue(any("IONDRVSupport" in warning for warning in plan["warnings"]))

    def test_phxaccel_is_reported_and_never_planned(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary)
            bringup = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            accel = write_kext(temporary, "PhxAccel.kext", "com.luuumi.PhxAccel")
            plan = self.plan_json("--efi-root", str(efi_root), "--kext", str(bringup), "--kext", str(accel))
            decisions = " ".join(plan["operator_decisions"])
            self.assertIn("/Library/Extensions", decisions)
            for step in plan["steps"]:
                self.assertNotIn("PhxAccel.kext", step["detail"])

    def test_a_layout_with_only_phxaccel_has_nothing_to_plan(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary)
            accel = write_kext(temporary, "PhxAccel.kext", "com.luuumi.PhxAccel")
            result = self.run_tool("--efi-root", str(efi_root), "--kext", str(accel))
            self.assertEqual(result.returncode, 3)
            self.assertIn("nothing to plan", result.stderr)

    def test_plan_files_are_written_once_and_refused_the_second_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary)
            bundle = write_kext(temporary, "PhxBringup.kext", "org.drip.PhxBringup")
            out = Path(temporary) / "plan"
            first = self.run_tool("--efi-root", str(efi_root), "--kext", str(bundle), "--out", str(out))
            self.assertEqual(first.returncode, 0, first.stderr)
            markdown = (out / "plan.md").read_text(encoding="utf-8")
            self.assertIn("nothing was written", markdown)
            self.assertIn("Rollback", markdown)
            written = json.loads((out / "plan.json").read_text(encoding="utf-8"))
            self.assertEqual(written["claims"]["kext_installed"], False)
            second = self.run_tool("--efi-root", str(efi_root), "--kext", str(bundle), "--out", str(out))
            self.assertEqual(second.returncode, 3)
            self.assertIn("exists", second.stderr)

    def test_a_kext_argument_is_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            efi_root = write_layout(temporary)
            result = self.run_tool("--efi-root", str(efi_root))
            self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
