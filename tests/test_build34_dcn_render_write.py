"""Test the staged plugin attachment observation without a Vulkan device."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "src/nmplugin"
sys.path.insert(0, str(ROOT / "tools"))
from build34_dcn_render_write_stage import INPUTS, stage
from test_nmplugin_render_pass_integrity import function


def extract(text, start, stop):
    low = text.index(start)
    return text[low:text.index(stop, low)]


class RenderWrite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = {name: (PLUGIN / name).read_bytes() for name in INPUTS}
        cls.sources = stage(cls.inputs)
        cls.vk = cls.sources["nvmtl_vk.c"]

    def test_every_source_is_pinned(self):
        for name, data in self.inputs.items():
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                stage({**self.inputs, name: data + b"\n"})

    def test_observation_does_not_escape_or_change_legacy_calls(self):
        for name in INPUTS:
            original, staged = self.inputs[name].decode(), self.sources[name]
            for call in ("IOConnectCall", "IOSurfaceSetValue(", "nvmtl_vk_surface_gpu_mark(", "nvmtl_ws_part_landed("):
                self.assertEqual(original.count(call), staged.count(call), (name, call))
        device = self.sources["NVMTLDevice.m"]
        self.assertLess(device.index("nvmtl_dcn_set_surface"), device.index("copyBuf = hb"))
        self.assertEqual(device.count("nvmtl_dcn_set_surface"), 1)
        event = function(self.sources["NVMTLEventSync.m"], "- (BOOL)nvmtlAdvancePart {")
        self.assertLess(event.index("if (!nvmtl_ws_publish_settled"), event.index("nvmtl_dcn_part_landed"))
        finish = function(self.vk, "int nvmtl_vk_submit_finish(nvmtl_inflight *f)\n{")
        self.assertEqual(finish.count("c->dcn_completed ="), 1)
        self.assertLess(finish.index("nvmtl_keep_verdict(c->wseq)"), finish.index("c->dcn_completed ="))
        self.assertLess(finish.index("nvmtl_cmd_retire(c)"), finish.index("c->dcn_completed ="))
        self.assertNotIn("return -", finish[finish.index("c->dcn_completed ="):])

    def test_external_alias_isolated_from_legacy_imports(self):
        self.assertEqual(self.vk.count("out->dcn_host_allocation ="), 1)
        imported = function(self.vk, "int nvmtl_vk_buffer_import_host(")
        self.assertLess(imported.index("pvkBindBufferMemory"), imported.index("out->dcn_host_allocation ="))
        self.assertIn('#include "build34_dcn_external_alias.h"', self.vk)
        self.assertFalse(any("nvmtl_dcn_create_render_alias(" in text for text in self.sources.values()))

    def test_external_alias_query_bind_and_cleanup(self):
        headers = os.environ.get("VULKAN_HEADERS")
        if not headers:
            self.skipTest("set VULKAN_HEADERS to the Vulkan-Headers include directory")
        self.assertTrue((Path(headers) / "vulkan/vulkan.h").is_file(), headers)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "nvmtl_vk.h").write_text(self.sources["nvmtl_vk.h"])
            binary = out / "external-alias"
            built = subprocess.run([
                os.environ.get("CC", "clang"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-g",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
                "-I" + str(out), "-I" + str(PLUGIN), "-I" + str(ROOT / "tools"), "-I" + headers,
                str(Path(__file__).with_name("test_build34_dcn_external_alias.c")), "-o", str(binary),
            ], capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_compiled_recording_and_submission_callsites(self):
        alias = function(self.vk, "const nvk_buffer *b, size_t offset, size_t row_pitch, nvk_image *out)\n{")
        begin = function(self.vk, "static int nvmtl_vk_cmd_begin_pass_impl(")
        records = {
            "alias": extract(self.vk, "    if (b->imported && b->map", '    nvlog("buffer texture: %ux%u VkFormat'),
            "begin": extract(begin, "    pvkCmdBeginRenderPass(c->cb, &rbi, VK_SUBPASS_CONTENTS_INLINE);",
                             "    for (uint32_t i = 0; i < NVMTL_NCOL; i++) c->fetchview[i]"),
            "end": extract(self.vk, "    pvkCmdEndRenderPass(c->cb); c->in_rp = 0;", "    if (c->pt_open"),
            "submit": extract(self.vk, "    result = g_state == 1 ? pvkQueueSubmit(g_queue, 1, &si, fence)",
                              "    pthread_mutex_unlock(&nvmtl_submit_mutex);"),
            "finish": extract(self.vk, "    c->dcn_completed = f->dcn_submitted;", "    return 0;"),
        }
        self.assertIn("else { nvmtl_commit_image(&pending); *out = pending; }", alias)
        self.assertLess(self.vk.index('"vkBindImageMemory(buffer texture)"'), self.vk.index(records["alias"]))
        self.assertLess(begin.index('"vkCreateFramebuffer"'), begin.index(records["begin"]))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for name, text in records.items():
                (out / f"{name}.inc").write_text(text)
            (out / "nvmtl_vk.h").write_text(self.sources["nvmtl_vk.h"])
            binary = out / "render-write"
            built = subprocess.run([
                os.environ.get("CC", "clang"), "-std=c11", "-Wall", "-Wextra", "-Werror", "-g",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
                "-I" + str(out), "-I" + str(PLUGIN), "-I" + str(ROOT / "tools"),
                str(Path(__file__).with_suffix(".c")), "-o", str(binary),
            ], capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stderr)
            for group in ("import", "pass", "submit"):
                with self.subTest(group=group):
                    result = subprocess.run([str(binary), group], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
