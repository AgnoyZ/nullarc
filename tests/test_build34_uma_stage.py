#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Unit and staging verification for build34 opt-in UMA high-VRAM support."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build34_uma_stage import DRIVER_SHA256, sha256, stage_driver

DRIVER = ROOT / 'src/phxbringup/PhxBringup.cpp'
UMA_HEADER = ROOT / 'src/phxbringup/PhxUmaPool.h'


class Build34UmaStageTests(unittest.TestCase):
    def test_exact_baseline_required(self):
        original = DRIVER.read_bytes()
        self.assertEqual(sha256(original), DRIVER_SHA256)
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            stage_driver(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            stage_driver(b'not build34')

    def test_staged_invariants_and_safety_gates(self):
        staged = stage_driver(DRIVER.read_bytes()).decode('utf-8')
        # Default off: debug.phx_uma_vram = 0
        self.assertIn('#include "PhxUmaPool.h"', staged)
        self.assertIn('static int gUmaVramMode = 0;', staged)
        self.assertIn('SYSCTL_INT(_debug, OID_AUTO, phx_uma_vram,', staged)
        self.assertIn('sysctl_register_oid(&sysctl__debug_phx_uma_vram);', staged)
        self.assertIn('sysctl_unregister_oid(&sysctl__debug_phx_uma_vram);', staged)

        # Phase 1 read-only probe runs on start and publishes phx-uma-* metadata
        self.assertEqual(staged.count('    probeUmaReadOnly();\n'), 1)
        self.assertEqual(staged.count('void PhxBringup::probeUmaReadOnly()'), 1)
        self.assertIn('setProperty("phx-uma-alias-matched", umaAliasMatched);', staged)
        self.assertIn('setProperty("phx-uma-pilot-host-status"', staged)
        self.assertIn('setProperty("phx-uma-full-host-status"', staged)
        self.assertIn('phx::uma::classifyBootMap(', staged)

        # Phase 2 safety: no CPU mmap on UMA BOs; EXECUTABLE is accepted (RADV maps
        # every VRAM BO EXECUTABLE) and the local VRAM PTE keeps EXEC set.
        self.assertIn('if (b->uma || !b->md)', staged)
        self.assertNotIn('return kIOReturnUnsupported;\n        maps[freei] = Map{true, v->handle', staged)
        header_text = UMA_HEADER.read_text(encoding='utf-8')
        self.assertIn('kPteLocalRwFlags = 0x71ull | (4ull << 48)', header_text)
        self.assertIn('kPteLocalReadFlags = 0x31ull | (4ull << 48)', header_text)
        # Correct AMDGPU_VM_PAGE_WRITEABLE bit (1 << 2)
        self.assertIn('(v->flags & (1u << 2)) != 0', staged)
        # CP instruction fetch from the high UMA carve-out faults on Phoenix: an IB
        # whose VA lands on a UMA BO mapping must be refused before submission.
        self.assertIn('const Bo *mapped = findBo(mp.handle);', staged)
        self.assertIn('if (mapped && mapped->uma)\n                    return false;', staged)

        # Client close tears down VMID before releasing UMA BOs
        vmid_free_idx = staged.index('owner->vmidFree(closingVmid, closingSeq);')
        close_free_all_idx = staged.index('freeAll();', vmid_free_idx)
        self.assertLess(vmid_free_idx, close_free_all_idx)

        # Sleep trips fault latch on active UMA pool
        self.assertIn('umaPool.tripFault();', staged)

        # Full-mode Vulkan/Metal 4 GiB reporting + large-BO page-table capacity + boot-arg opt-in
        self.assertIn('kPtChunks = 192;', staged)
        self.assertIn('kUmaFullGttCap = 2048ull << 20;', staged)
        self.assertIn('inf.vram_vis_total = kVisTotal + umaHiTotal;', staged)
        self.assertIn('PE_parse_boot_argn("phx_uma_vram"', staged)
        self.assertIn('kMaxAllocs = 2048u;', header_text)

        # License hygiene: MIT/GPL-2.0 header, no PolyForm header or NullMoth code copy
        self.assertIn('SPDX-License-Identifier: MIT OR GPL-2.0-only', header_text)
        self.assertNotIn('PolyForm', header_text)
        self.assertNotIn('PolyForm', staged)


if __name__ == '__main__':
    unittest.main()
