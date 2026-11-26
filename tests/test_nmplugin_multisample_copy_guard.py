#!/usr/bin/env python3
"""Verify multisample buffer<->image copy refusal and async upload barrier completeness."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/nmplugin/nvmtl_vk.c"


def extract_function(text: str, signature: str) -> str:
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 0
    for idx in range(brace, len(text)):
        ch = text[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    raise AssertionError(f"Unclosed function: {signature}")


class MultisampleCopyGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text()

    def test_all_buffer_image_copy_entry_points_reject_multisample(self):
        expected = [
            ("int nvmtl_vk_image_write(", 'if (nvmtl_vk_reject_multisample_copy(img, "image_write")) return -1;'),
            ("int nvmtl_vk_image_read(", 'if (nvmtl_vk_reject_multisample_copy(img, "image_read")) return -1;'),
            ("int nvmtl_vk_image_host_xfer(", 'if (nvmtl_vk_reject_multisample_copy(img, "image_host_xfer")) return -1;'),
            ("int nvmtl_vk_image_write_region_level_layer(", 'if (nvmtl_vk_reject_multisample_copy(img, "image_write_region")) return -1;'),
            ("int nvmtl_vk_image_read_region_level_layer(", 'if (nvmtl_vk_reject_multisample_copy(img, "image_read_region")) return -1;'),
            ("int nvmtl_vk_cmd_copy_buffer_to_image_level_layer(", 'if (nvmtl_vk_reject_multisample_copy(img, "copy_buffer_to_image")) return -1;'),
            ("int nvmtl_vk_cmd_copy_image_to_buffer_level_layer(", 'if (nvmtl_vk_reject_multisample_copy(img, "copy_image_to_buffer")) return -1;'),
        ]
        for sig, guard in expected:
            body = extract_function(self.text, sig)
            first_stmt = body[body.index("{") + 1 :].lstrip().splitlines()[0].strip()
            self.assertEqual(first_stmt, guard, f"{sig} must reject multisample images first")

    def test_upload_barrier_covers_full_image_write_and_bidirectional_host_xfer(self):
        write_body = extract_function(self.text, "int nvmtl_vk_image_write(")
        self.assertIn("nvmtl_vk_image_upload_barrier(img);", write_body)
        self.assertLess(
            write_body.index("nvmtl_vk_image_upload_barrier(img);"),
            write_body.index("nvmtl_upstage_get("),
        )

        xfer_body = extract_function(self.text, "int nvmtl_vk_image_host_xfer(")
        self.assertNotIn("if (!to_image) nvmtl_vk_image_upload_barrier(img);", xfer_body)
        self.assertIn("nvmtl_vk_image_upload_barrier(img);", xfer_body)
        self.assertLess(
            xfer_body.index("nvmtl_vk_image_upload_barrier(img);"),
            xfer_body.index("nvmtl_vk_cmd_begin("),
        )

        region_body = extract_function(self.text, "int nvmtl_vk_image_write_region_level_layer(")
        self.assertLess(
            region_body.index("if (finish_first) nvmtl_asyncup_finish(nvmtl_asyncup_take(img));"),
            region_body.index("if (mode == NVMTL_UP_SUBMIT_ASYNC)"),
        )

    def test_guard_helper_behavior_under_sanitizers(self):
        helper = extract_function(self.text, "static inline int nvmtl_vk_reject_multisample_copy(")
        harness = (
            "#include <stdint.h>\n"
            "#include <stdio.h>\n"
            "typedef struct { uint32_t samples; } nvk_image;\n"
            "static unsigned log_calls = 0;\n"
            "static void nvlog(const char *fmt, const char *who, unsigned samples) {\n"
            "    (void)fmt; (void)who; (void)samples; log_calls++;\n"
            "}\n"
            + helper
            + "\nint main(void) {\n"
            "    nvk_image s0 = { 0 }, s1 = { 1 }, s2 = { 2 }, s4 = { 4 }, s8 = { 8 };\n"
            "    if (nvmtl_vk_reject_multisample_copy(NULL, \"null\") != -1) return 1;\n"
            "    if (log_calls != 0) return 2;\n"
            "    if (nvmtl_vk_reject_multisample_copy(&s0, \"s0\") != 0) return 3;\n"
            "    if (nvmtl_vk_reject_multisample_copy(&s1, \"s1\") != 0) return 4;\n"
            "    if (log_calls != 0) return 5;\n"
            "    if (nvmtl_vk_reject_multisample_copy(&s2, \"s2\") != -1) return 6;\n"
            "    if (nvmtl_vk_reject_multisample_copy(&s4, \"s4\") != -1) return 7;\n"
            "    if (nvmtl_vk_reject_multisample_copy(&s8, \"s8\") != -1) return 8;\n"
            "    if (log_calls != 3) return 9;\n"
            "    return 0;\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "guard_test.c"
            exe = Path(td) / "guard_test"
            src.write_text(harness)
            subprocess.run([
                "xcrun", "clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                str(src), "-o", str(exe),
            ], check=True, timeout=60)
            subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == "__main__":
    unittest.main()
