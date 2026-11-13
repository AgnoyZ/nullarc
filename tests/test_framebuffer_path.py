import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_source import prepare


class FramebufferPathTests(unittest.TestCase):
    """Patch 0028: the display path's pool release and scan-out alias retry, as staged source."""

    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.stage = Path(cls.temporary.name) / "stage"
        cls.provenance = prepare(cls.stage)
        cls.fb = (cls.stage / "src/phxaccel/accel/phxfb.cpp").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls): cls.temporary.cleanup()

    def test_patch_is_pinned_after_0027(self):
        names = list(self.provenance["historical_patches_sha256"])
        self.assertEqual(29, len(names))
        self.assertEqual("patches/0027-bounded-ib-debug-reads.patch", names[26])
        self.assertEqual("patches/0028-checked-framebuffer-pool-and-alias-retry.patch", names[27])
        patch = (ROOT / names[27]).read_bytes()
        self.assertEqual(hashlib.sha256(patch).hexdigest(), self.provenance["historical_patches_sha256"][names[27]])

    def test_pool_release_is_checked_as_integers_before_the_allocator(self):
        free = self.fb.split("IOReturn vramFree(NVRMVramRequest *r) {")[1].split("IOReturn rmCall(")[0]
        self.assertIn("phx780m::poolReleaseValid(kva - base, len, fPoolBytes)", free)
        self.assertIn("const uint64_t kva = (uint64_t)(uintptr_t)r->kva, base = (uint64_t)(uintptr_t)fPoolKva;", free)
        self.assertNotIn("(uint8_t *)r->kva - fPoolKva", free)
        self.assertNotIn("off + len > fPoolBytes", free)
        self.assertIn("!fPoolKva", free)
        self.assertLess(free.index("kva < base"), free.index("kva - base"))
        self.assertLess(free.index("poolReleaseValid"), free.index("fPoolRange->deallocate("))
        self.assertIn("return kIOReturnBadArgument;", free.split("poolReleaseValid")[1].split("deallocate(")[0])

    def test_pool_init_falls_back_to_a_smaller_pool(self):
        init = self.fb.split("void poolInit() {")[1].split("void poolFree()")[0]
        self.assertIn("if (!fPoolRange) { b->complete(); b->release(); continue; }", init)
        self.assertNotIn("b->release(); return;", init)

    def test_unpublished_carve_out_is_retried_instead_of_spending_the_budget(self):
        alias = self.fb.split("IOMemoryMap *aliasMap() {")[1].split("IOReturn callPlatformFunction(")[0]
        # The budget rules themselves are asserted in tests/test_hardware_policy.cpp; what this test still owns is
        # that the driver uses them and that a wait costs nothing: waits are counted before any verification try.
        self.assertIn("phx780m::aliasExhausted(fAliasTries, fAliasWaits)", alias)
        self.assertIn("phx780m::aliasCarveOutReady(fbPhys, barOff)", alias)
        wait = alias.split("phx780m::aliasCarveOutReady(fbPhys, barOff)) {")[1]
        self.assertIn("if (!fAliasWaits++)", wait)
        self.assertLess(alias.index("fAliasWaits++"), alias.index("fAliasTries++"))
        self.assertLess(alias.index("fAliasTries++"), alias.index("IODeviceMemory::withRange(phys, bytes)"))
        self.assertIn("static constexpr unsigned kAliasVerifyLimit = phx780m::kAliasVerifyLimit;", self.fb)
        self.assertIn("static constexpr unsigned kAliasWaitLimit = phx780m::kAliasWaitLimit;", self.fb)
        self.assertIn("unsigned fAliasWaits = 0;", self.fb)
        self.assertIn("phx780m::aliasSamplesMatch(same, n, nz)", alias)
        self.assertIn("phx780m::aliasSampleStep(words)", alias)

    def test_staged_policy_header_has_the_release_policy(self):
        policy = (ROOT / "src/PhxHardwarePolicy.hpp").read_bytes()
        self.assertEqual(policy, (self.stage / "src/phxaccel/PhxHardwarePolicy.hpp").read_bytes())
        self.assertIn(b"poolReleaseValid", policy)
        self.assertIn(b"pageAligned", policy)
        self.assertIn(b"aliasExhausted", policy)
        self.assertIn(b"aliasSamplesMatch", policy)


if __name__ == "__main__": unittest.main()
