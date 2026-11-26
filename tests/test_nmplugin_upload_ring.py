#!/usr/bin/env python3
"""Unit-test the circular staging ring allocator and verify nvmtl_vk.c wiring."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/nmplugin/nvmtl_upload_ring.h"
VK_SRC = ROOT / "src/nmplugin/nvmtl_vk.c"


class UploadRingTests(unittest.TestCase):
    def test_ring_state_machine_under_sanitizers(self):
        harness = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include "nvmtl_upload_ring.h"

int main(void) {
    nvmtl_upring r;
    nvmtl_upring_init(&r, 4096);
    assert(r.capacity == 4096);
    assert(r.slot_count == 0 && r.used == 0);

    // Oversized or zero requests must be rejected cleanly
    uint32_t s = 0; size_t off = 0; uint64_t seq = 0;
    assert(nvmtl_upring_try_alloc(&r, 0, 1, &s, &off, &seq) == -1);
    assert(nvmtl_upring_try_alloc(&r, 4097, 1, &s, &off, &seq) == -1);

    // Sequential aligned allocation: 100 -> 256, 1000 -> 1024, 2000 -> 2048
    uint32_t s0, s1, s2, s3;
    size_t o0, o1, o2, o3;
    uint64_t q0, q1, q2, q3;
    assert(nvmtl_upring_try_alloc(&r, 100, 10, &s0, &o0, &q0) == 0);
    assert(o0 == 0 && r.head == 256 && r.used == 256);
    assert(nvmtl_upring_try_alloc(&r, 1000, 20, &s1, &o1, &q1) == 0);
    assert(o1 == 256 && r.head == 1280 && r.used == 1280);
    assert(nvmtl_upring_try_alloc(&r, 2000, 30, &s2, &o2, &q2) == 0);
    assert(o2 == 1280 && r.head == 3328 && r.used == 3328);

    // 1024 bytes does not fit at tail (4096 - 3328 = 768) and tail == 0, so must fail
    assert(nvmtl_upring_try_alloc(&r, 1024, 40, &s3, &o3, &q3) == -1);

    // Out-of-order completion of s1 must NOT advance tail yet
    assert(nvmtl_upring_mark_done(&r, s1, q1) == 1);
    assert(r.slot_count == 3 && r.tail == 0);
    // Duplicate mark_done is ignored
    assert(nvmtl_upring_mark_done(&r, s1, q1) == 0);

    // Completing oldest s0 must retire BOTH s0 and already-done s1 (tail -> 1280)
    uint32_t os = 0; uint64_t oq = 0, otag = 0;
    assert(nvmtl_upring_oldest_active(&r, &os, &oq, &otag) == 1);
    assert(os == s0 && oq == q0 && otag == 10);
    assert(nvmtl_upring_mark_done(&r, s0, q0) == 1);
    assert(r.slot_count == 1 && r.tail == 1280 && r.used == 2048);

    // Now 1024 bytes wraps to offset 0 (charges 768 pad + 1024 = 1792)
    assert(nvmtl_upring_try_alloc(&r, 1024, 40, &s3, &o3, &q3) == 0);
    assert(o3 == 0 && r.head == 1024 && r.used == 2048 + 1792);

    // Middle free is tail - head = 1280 - 1024 = 256 -> 256 fits, 512 does not
    uint32_t s4; size_t o4; uint64_t q4;
    assert(nvmtl_upring_try_alloc(&r, 512, 50, &s4, &o4, &q4) == -1);
    assert(nvmtl_upring_try_alloc(&r, 200, 50, &s4, &o4, &q4) == 0);
    assert(o4 == 1024 && r.head == 1280 && r.used == 4096);

    // Retire remaining slots in reverse order and confirm clean reset to 0
    assert(nvmtl_upring_mark_done(&r, s4, q4) == 1);
    assert(nvmtl_upring_mark_done(&r, s3, q3) == 1);
    assert(r.slot_count == 3);
    assert(nvmtl_upring_mark_done(&r, s2, q2) == 1);
    assert(r.slot_count == 0 && r.head == 0 && r.tail == 0 && r.used == 0);

    // Slot-count saturation (NVMTL_UPRING_MAX_SLOTS) and full drain
    nvmtl_upring_init(&r, 64 * 1024);
    uint32_t slots[NVMTL_UPRING_MAX_SLOTS];
    uint64_t seqs[NVMTL_UPRING_MAX_SLOTS];
    for (uint32_t i = 0; i < NVMTL_UPRING_MAX_SLOTS; i++) {
        assert(nvmtl_upring_try_alloc(&r, 256, 100 + i, &slots[i], &off, &seqs[i]) == 0);
    }
    assert(nvmtl_upring_try_alloc(&r, 256, 999, &s, &off, &seq) == -1);
    for (uint32_t i = 0; i < NVMTL_UPRING_MAX_SLOTS; i++) {
        assert(nvmtl_upring_mark_done(&r, slots[i], seqs[i]) == 1);
    }
    assert(r.slot_count == 0 && r.used == 0 && r.head == 0 && r.tail == 0);

    printf("PASS upload ring invariants\n");
    return 0;
}
"""
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "ring_test.c"
            exe = Path(td) / "ring_test"
            src.write_text(harness)
            subprocess.run([
                "xcrun", "clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                f"-I{HEADER.parent}", str(src), "-o", str(exe),
            ], check=True, timeout=60)
            subprocess.run([str(exe)], check=True, timeout=30)

    def test_vk_c_wires_upload_ring_with_offset_copy(self):
        text = VK_SRC.read_text()
        self.assertIn('#include "nvmtl_upload_ring.h"', text)
        self.assertIn("nvmtl_upring_alloc_slot(bytes, au)", text)
        self.assertIn("uint8_t *dst = (uint8_t *)stageb->map + stage_off;", text)
        self.assertIn("VkBufferImageCopy bic = { stage_off, 0, 0,", text)
        self.assertIn("nvmtl_upring_mark_done(&g_upring, au->ring_slot, au->ring_seq);", text)


if __name__ == "__main__":
    unittest.main()
