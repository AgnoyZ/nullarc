# SPDX-License-Identifier: MIT
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build34_r3_writeback_layout import LIMITS, PAGE_BYTES, check


def fixture():
    return dict(
        gart_window=dict(base=0x8000, bytes=4 * PAGE_BYTES),
        compute=dict(gpu_va=0x9000, dma=0x10000, host_pa=0x20000, fence_offset=4),
        gfx=dict(gpu_va=0xA000, dma=0x11000, host_pa=0x21000, fence_offset=4088),
        reserved=dict(gpu_va=[dict(base=0x8000, bytes=PAGE_BYTES)],
                      dma=[dict(base=0xF000, bytes=PAGE_BYTES)],
                      host_pa=[dict(base=0x1F000, bytes=PAGE_BYTES)]),
    )


class WritebackLayout(unittest.TestCase):
    def test_adjacent_pages_and_guard_bounds(self):
        self.assertEqual(check(**fixture()),
                         {"status": "consistent-writeback-layout-geometry", "hardware_attested": False})

    def test_full_bootstrap_aperture_has_no_fresh_slot(self):
        args = fixture()
        base = 0x7FFF00000000
        args["gart_window"] = dict(base=base, bytes=32768 * PAGE_BYTES)
        args["compute"]["gpu_va"] = base + PAGE_BYTES
        args["gfx"]["gpu_va"] = base + 2 * PAGE_BYTES
        args["reserved"]["gpu_va"] = [args["gart_window"]]
        with self.assertRaisesRegex(ValueError, "overlaps in gpu_va"):
            check(**args)

    def test_alias_on_any_one_address_space_refuses(self):
        for space in LIMITS:
            with self.subTest(space=space), self.assertRaisesRegex(ValueError, f"overlaps in {space}"):
                args = fixture()
                args["gfx"][space] = args["compute"][space]
                check(**args)

    def test_overlap_with_prior_page_tail_refuses(self):
        for space in LIMITS:
            with self.subTest(space=space), self.assertRaisesRegex(ValueError, f"overlaps in {space}"):
                args = fixture()
                args["reserved"][space].append(dict(base=args["gfx"][space] + PAGE_BYTES - 1, bytes=1))
                check(**args)

    def test_equal_numbers_in_different_spaces_are_not_aliases(self):
        args = fixture()
        args["compute"]["dma"] = args["gfx"]["host_pa"]
        self.assertIs(check(**args)["hardware_attested"], False)

    def test_rejects_outside_window_and_malformed_page(self):
        for field, value in (("gpu_va", 0xC000), ("gpu_va", 0xA004), ("dma", LIMITS["dma"]),
                             ("dma", True), ("host_pa", LIMITS["host_pa"] - 1), ("host_pa", 0),
                             ("fence_offset", 0), ("fence_offset", 5), ("fence_offset", 4092)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                args = fixture()
                args["gfx"][field] = value
                check(**args)

    def test_fails_closed_on_incomplete_or_wrapped_reservations(self):
        args = fixture()
        del args["reserved"]["dma"]
        with self.assertRaises(ValueError):
            check(**args)
        args = fixture()
        args["reserved"]["host_pa"].append(dict(base=LIMITS["host_pa"] - 1, bytes=2))
        with self.assertRaises(ValueError):
            check(**args)


if __name__ == "__main__":
    unittest.main()
