"""CPU recording regressions for full-view clears and render recording failure.

Adapted from upstream nullarc 10c9e65, e44deb7 and 9543d43. Production
branches and public data structures are compiled; Vulkan callbacks are doubles.
The pixel history is a model, not GPU, Weather or sRGB pixel validation.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/nmplugin/nvmtl_vk.c"

PRELUDE = r'''
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <mach/port.h>
#include "nvmtl_vk.h"
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "check failed at line %d: %s\n", __LINE__, #x); return 1; } } while (0)
#define nvlog(...) ((void)0)
'''


def function(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class RecordingTest(unittest.TestCase):
    @classmethod
    def compile(cls, code):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        path = Path(cls.temp.name) / "test.cpp"
        path.write_text(PRELUDE + code)
        cls.binary = Path(cls.temp.name) / "test"
        result = subprocess.run([
            "clang++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-parameter", "-Wno-missing-field-initializers",
            "-fsanitize=address,undefined",
            "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
            "-I" + str(ROOT / "src/nmplugin"), str(path), "-o", str(cls.binary),
        ], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError(result.stderr)

    def run_case(self, mode):
        result = subprocess.run([str(self.binary), str(mode)], capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


class FormatViewClear(RecordingTest):
    @classmethod
    def setUpClass(cls):
        source = SOURCE.read_text()
        start = source.index("        for (uint32_t i = 0; i < ncol; i++) {",
                             source.index("    nvk_pass full;"))
        end = source.index("        if (p->has_depth && ps->ds && !c->in_rp)", start)
        # Include the existing LOAD/size checks and the unchanged transfer path,
        # so the unpatched branch produces a semantic failure, not a missing-text error.
        loop = source[start:end]
        cls.compile(r'''
enum { VK_IMAGE_ASPECT_COLOR_BIT=1, VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER=2,
       VK_ACCESS_MEMORY_WRITE_BIT=4, VK_ACCESS_TRANSFER_WRITE_BIT=8,
       VK_IMAGE_LAYOUT_UNDEFINED=0, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL=2,
       VK_QUEUE_FAMILY_IGNORED=~0u, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT=16,
       VK_PIPELINE_STAGE_TRANSFER_BIT=32, VK_ACCESS_COLOR_ATTACHMENT_READ_BIT=64,
       VK_ACCESS_COLOR_ATTACHMENT_WRITE_BIT=128, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL=3,
       VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT=256 };
using VkImage = void *;
struct VkImageSubresourceRange { uint32_t aspectMask,baseMipLevel,levelCount,baseArrayLayer,layerCount; };
struct VkImageMemoryBarrier {
    uint32_t sType; const void *pNext; uint32_t srcAccessMask,dstAccessMask,oldLayout,newLayout;
    uint32_t srcQueueFamilyIndex,dstQueueFamilyIndex; VkImage image; VkImageSubresourceRange range;
};
struct VkClearColorValue { float float32[4]; };
static nvk_pass recorded;
static int calls, failure, transfers;
static void pvkCmdPipelineBarrier(void *, uint32_t, uint32_t, uint32_t, uint32_t,
                                 const void *, uint32_t, const void *, uint32_t,
                                 const VkImageMemoryBarrier *) {}
static void pvkCmdClearColorImage(void *, VkImage, uint32_t, const VkClearColorValue *,
                                 uint32_t, const VkImageSubresourceRange *) { transfers++; }
static void nvmtl_clear_colour(VkClearColorValue *v, uint32_t, const float *c) { std::memcpy(v->float32,c,16); }
int nvmtl_vk_cmd_empty_pass(nvk_cmdbuf *, const nvk_pass *p) { recorded=*p; calls++; return failure; }
static int prepare(nvk_cmdbuf *c, const nvk_pass *ps, uint32_t &add) {
    const uint32_t ncol=NVMTL_NCOL, nl=ps->layers>1?ps->layers:1;
    uint32_t cf[NVMTL_NCOL]{};
    for (uint32_t i=0;i<ncol;i++) if (ps->col[i]) cf[i]=ps->colfmt[i]?ps->colfmt[i]:ps->col[i]->fmt;
''' + loop + r'''
    return 0;
}
int main(int argc, char **argv) {
    if (argc!=2) return 64;
    const int mode=std::atoi(argv[1]);
    nvk_image image{}; image.mtl_type=2; image.fmt=44;
    nvk_cmdbuf c{}; nvk_pass p{};
    p.col[3]=&image; p.colview[3]=&image; p.colfmt[3]=50;
    p.colw[3]=8; p.colh[3]=4; p.w=4; p.h=2;
    p.col_level[3]=2; p.col_layer[3]=5; p.layers=2;
    p.clear[3][0]=0.5f; p.clear[3][3]=1.0f;
    uint32_t add=0;
    if (mode==1 || mode==6) {
        image.samples=mode==6?4:1;
        CHECK(prepare(&c,&p,add)==0);
        CHECK(calls==1 && transfers==0 && add==NVMTL_LOAD_COLOUR(3));
        CHECK(recorded.col[0]==&image && recorded.colview[0]==p.colview[3]);
        CHECK(recorded.colfmt[0]==50 && recorded.w==8 && recorded.h==4 && recorded.layers==2);
        CHECK(recorded.col_level[0]==2 && recorded.col_layer[0]==5);
        CHECK(std::memcmp(recorded.clear[0],p.clear[3],sizeof p.clear[3])==0);
        CHECK(recorded.load==0 && recorded.res[0]==nullptr && recorded.ds==nullptr);
        CHECK(p.w==4 && p.h==2 && p.load==0);
    } else if (mode==2) {
        failure=-1;
        CHECK(prepare(&c,&p,add)==-1 && calls==1 && transfers==0 && add==0);
    } else if (mode==3) {
        // No preclear for LOAD, equal-sized render area, 3D, or an open pass.
        for (int k=0;k<4;k++) {
            p.load=k==0?NVMTL_LOAD_COLOUR(3):0; p.w=k==1?8:4; p.h=k==1?4:2;
            image.mtl_type=k==2?7:2; c.in_rp=k==3;
            CHECK(prepare(&c,&p,add)==0 && calls==0 && transfers==0 && add==0);
        }
    } else if (mode==4) {
        p.colfmt[3]=image.fmt;
        CHECK(prepare(&c,&p,add)==0 && transfers==1 && calls==0 && add==NVMTL_LOAD_COLOUR(3));
        CHECK(image.layout==VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL);
    } else if (mode==5) {
        // Two frames reuse one view. The smaller draw area must not retain the
        // previous frame outside it after Metal requests attachment Clear.
        float pixels[32]{}; pixels[31]=0.75f;
        CHECK(prepare(&c,&p,add)==0);
        if (calls && recorded.w==8 && recorded.h==4) for (float &pixel:pixels) pixel=0;
        for (unsigned y=0;y<p.h;y++) for (unsigned x=0;x<p.w;x++) pixels[y*8+x]=0;
        pixels[0]=0.5f+pixels[0]*0.5f; // modeled premultiplied-alpha foreground
        CHECK(pixels[0]==0.5f && pixels[31]==0);
    } else return 64;
    return 0;
}
''')

    def test_full_view_subresource_layers_and_colour(self):
        self.run_case(1)

    def test_failed_preclear_does_not_mark_attachment_loaded(self):
        self.run_case(2)

    def test_load_equal_area_volume_and_open_pass_unchanged(self):
        self.run_case(3)

    def test_same_format_transfer_clear_unchanged(self):
        self.run_case(4)

    def test_previous_frame_is_not_retained_outside_draw_area(self):
        self.run_case(5)

    def test_multisample_view_uses_empty_render_pass(self):
        self.run_case(6)


class LoadSelection(RecordingTest):
    @classmethod
    def setUpClass(cls):
        source = SOURCE.read_text()
        start = source.index("    void *rpUse = rpShape ?")
        # Both old and corrected code stop before constructing the begin info;
        # the old fallback therefore compiles and fails the requested semantics.
        end = source.index("    VkRenderPassBeginInfo rbi", start)
        selection = source[start:end]
        # In corrected code framebuffer allocation lies between selection and
        # begin info. Keep just selection and its immediately following guard.
        if "\n    for (uint32_t i = 0; i < ncol;" in selection:
            selection = selection[:selection.index("\n    for (uint32_t i = 0; i < ncol;")]
        cls.compile(r'''
static void *variant;
static int requests;
static void *nvmtl_rp_variant(nvk_pipeline *, uint32_t, uint32_t) { requests++; return variant; }
static int select_pass(nvk_pipeline *p, const nvk_pass *ps, void *rpShape, void **selected) {
    uint32_t was=0;
''' + selection + r'''
    *selected=rpUse; return 0;
}
int main(int argc, char **argv) {
    if (argc!=2) return 64;
    nvk_pipeline p{}; nvk_pass ps{}; p.rp=&p; ps.load=NVMTL_LOAD_COLOUR(0);
    void *selected=nullptr; int value=0;
    switch (std::atoi(argv[1])) {
    case 1: CHECK(select_pass(&p,&ps,nullptr,&selected)==-1 && selected==nullptr); break;
    case 2: variant=&value; CHECK(select_pass(&p,&ps,nullptr,&selected)==0 && selected==variant); break;
    case 3: CHECK(select_pass(&p,&ps,&value,&selected)==0 && selected==&value && requests==0); break;
    default: return 64;
    }
    return 0;
}
''')

    def test_missing_load_variant_never_falls_back_to_clear(self):
        self.run_case(1)

    def test_available_load_variant(self):
        self.run_case(2)

    def test_explicit_resolve_shape(self):
        self.run_case(3)

    def test_selection_precedes_layout_mutation_and_framebuffer_creation(self):
        source = SOURCE.read_text()
        start = source.index("    void *rpUse = rpShape ?")
        layout = source.index("        ps->col[i]->layout =", source.index("    VkImageView views["))
        framebuffer = source.index("    VkFramebufferCreateInfo fci", layout)
        self.assertLess(start, layout)
        self.assertLess(start, framebuffer)


class EncodingFailure(RecordingTest):
    @classmethod
    def setUpClass(cls):
        source = SOURCE.read_text()
        cls.has_error_latch = "static int nvmtl_vk_cmd_begin_pass_impl(" in source
        if not cls.has_error_latch:
            return
        wrapper = function(source, "int nvmtl_vk_cmd_begin_pass(")
        start = source.index("    if (c->encoding_error || nvmtl_counter_flush(c))")
        end = source.index("\n", start)
        cls.compile(r'''
static int failure, retired, submitted, flush_failure;
static int nvmtl_vk_cmd_begin_pass_impl(nvk_cmdbuf *, const nvk_pass *, nvk_pipeline *) { return failure; }
static int nvmtl_counter_flush(nvk_cmdbuf *) { return flush_failure; }
static void nvmtl_cmd_retire(nvk_cmdbuf *) { retired++; }
''' + wrapper + "\nstatic int submit(nvk_cmdbuf *c) {\n" + source[start:end] + r'''
    submitted++; return 0;
}
int main(int argc, char **argv) {
    if (argc!=2) return 64;
    nvk_cmdbuf c{}; nvk_pass ps{}; nvk_pipeline p{};
    switch (std::atoi(argv[1])) {
    case 1:
        failure=-1;
        CHECK(nvmtl_vk_cmd_begin_pass(&c,&ps,&p)==-1 && c.encoding_error);
        failure=0;
        CHECK(nvmtl_vk_cmd_begin_pass(&c,&ps,&p)==0 && c.encoding_error);
        CHECK(submit(&c)==-1 && retired==1 && submitted==0);
        break;
    case 2:
        CHECK(nvmtl_vk_cmd_begin_pass(&c,&ps,&p)==0 && !c.encoding_error);
        CHECK(submit(&c)==0 && retired==0 && submitted==1);
        break;
    case 3:
        flush_failure=-1;
        CHECK(submit(&c)==-1 && retired==1 && submitted==0);
        break;
    default: return 64;
    }
    return 0;
}
''')

    def require_latch(self):
        self.assertTrue(self.has_error_latch, "render-pass failure has no sticky command-buffer encoding-error latch")

    def test_render_failure_sticks_and_prevents_submit(self):
        self.require_latch()
        self.run_case(1)

    def test_successful_recording_can_submit(self):
        self.require_latch()
        self.run_case(2)

    def test_counter_flush_failure_still_prevents_submit(self):
        self.require_latch()
        self.run_case(3)


if __name__ == "__main__":
    unittest.main()
