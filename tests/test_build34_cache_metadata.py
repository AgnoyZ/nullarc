#!/usr/bin/env python3
"""CPU fixtures for the boot-matching regression missed by UUID-only checks."""
import copy
import importlib.util
from pathlib import Path
import plistlib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "cache_metadata", ROOT / "tools/check_build34_cache_metadata.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
ACCEL = "com.example.accel"


def capture(value):
    return b"kmutil inspection header\n" + b"\n".join(plistlib.dumps(x) for x in value)


class CacheMetadataTests(unittest.TestCase):
    def setUp(self):
        def row(name, image=None):
            value = dict(CFBundleIdentifier=name, _PrelinkBundlePath="/Library/Extensions/" + name,
                         IOKitPersonalities={"panel": {"IOClass": "ExamplePanel"}},
                         OSBundleLibraries={"com.example.lib": "1.0"}, _InfoPlistDigest=b"plist",
                         _PrelinkExecutableLoadAddr=16, _PrelinkExecutableSourceAddr=32,
                         _PrelinkKmodInfo=64)
            if image:
                value.update(OSBundleUUID=image, _PrelinkExecutableSize=128)
            return value
        self.old = [
            {"_PrelinkKCID": b"boot", "_PrelinkInfoDictionary": [row("com.example.lib", b"lib")]},
            {"_PrelinkKCID": b"system", "_BootKCID": b"boot", "_PrelinkInfoDictionary": []},
            {"_PrelinkKCID": b"aux", "_BootKCID": b"boot", "_PageableKCID": b"system",
             "_PrelinkInfoDictionary": [row(ACCEL, b"old"), row("com.example.codeless")]},
        ]
        self.new = copy.deepcopy(self.old)
        self.new[2]["_PrelinkKCID"] = b"new-aux"
        self.accel = self.new[2]["_PrelinkInfoDictionary"][0]
        self.accel.update(OSBundleUUID=b"new", _PrelinkExecutableSize=160,
                          _PrelinkExecutableLoadAddr=128, _PrelinkExecutableSourceAddr=256,
                          _PrelinkKmodInfo=512)

    def check(self, changes=(ACCEL,)):
        return M.compare_captures(capture(self.old), capture(self.new), changes, 3, 1)

    def refuse(self):
        with self.assertRaises(M.ValidationError):
            self.check()

    def test_exact_image_and_relocation_allowance(self):
        self.assertEqual(self.check()["changed_images"], [ACCEL])

    def test_same_image_control(self):
        self.new = copy.deepcopy(self.old)
        self.assertEqual(self.check(())["changed_images"], [])

    def test_explicit_load_regression(self):
        self.accel["OSBundleRequireExplicitLoad"] = True
        self.refuse()

    def test_absent_policy_is_not_false(self):
        self.accel["OSBundleRequireExplicitLoad"] = False
        self.refuse()

    def test_unrelated_explicit_load_policy(self):
        self.new[2]["_PrelinkInfoDictionary"][1]["OSBundleRequireExplicitLoad"] = True
        self.refuse()

    def test_removed_existing_explicit_load_policy(self):
        self.old[2]["_PrelinkInfoDictionary"][0]["OSBundleRequireExplicitLoad"] = True
        self.refuse()

    def test_private_staging_path_regression(self):
        self.accel["_PrelinkBundlePath"] = "/private/staging/example.kext"
        self.refuse()

    def test_personality_changed(self):
        self.accel["IOKitPersonalities"]["panel"]["IOClass"] = "AnotherPanel"
        self.refuse()

    def test_dependency_changed(self):
        self.accel["OSBundleLibraries"]["com.example.lib"] = "2.0"
        self.refuse()

    def test_info_digest_changed(self):
        self.accel["_InfoPlistDigest"] = b"different"
        self.refuse()

    def test_missing_component(self):
        self.new[2]["_PrelinkInfoDictionary"].pop()
        self.refuse()

    def test_extra_component(self):
        self.new[2]["_PrelinkInfoDictionary"].append({"CFBundleIdentifier": "extra"})
        self.refuse()

    def test_replaced_component(self):
        self.new[2]["_PrelinkInfoDictionary"][1]["CFBundleIdentifier"] = "replacement"
        self.refuse()

    def test_codeless_becomes_executable(self):
        self.new[2]["_PrelinkInfoDictionary"][1]["OSBundleUUID"] = b"extra"
        self.refuse()

    def test_unexpected_changed_image(self):
        self.new[0]["_PrelinkInfoDictionary"][0]["OSBundleUUID"] = b"other"
        self.refuse()

    def test_expected_image_unchanged(self):
        self.accel["OSBundleUUID"] = b"old"
        self.refuse()

    def test_unrelated_size_change(self):
        self.new[0]["_PrelinkInfoDictionary"][0]["_PrelinkExecutableSize"] = 999
        self.refuse()

    def test_boot_link_changed(self):
        self.new[2]["_BootKCID"] = b"other"
        self.refuse()

    def test_system_link_changed(self):
        self.new[2]["_PageableKCID"] = b"other"
        self.refuse()

    def test_boot_collection_identity_changed(self):
        self.new[0]["_PrelinkKCID"] = b"other"
        self.refuse()

    def test_moved_component(self):
        self.new[1]["_PrelinkInfoDictionary"].append(self.new[2]["_PrelinkInfoDictionary"].pop())
        self.refuse()

    def test_duplicate_bundle(self):
        self.new[1]["_PrelinkInfoDictionary"].append(copy.deepcopy(self.accel))
        self.refuse()

    def test_missing_collection(self):
        self.new.pop(1)
        self.refuse()

    def test_invalid_plist(self):
        with self.assertRaises(M.ValidationError):
            M.parse_capture(b"<?xml broken </plist>" * 3)

    def test_missing_bundle_identifier(self):
        del self.accel["CFBundleIdentifier"]
        self.refuse()


if __name__ == "__main__":
    unittest.main(verbosity=2)
