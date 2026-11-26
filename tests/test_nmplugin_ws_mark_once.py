#!/usr/bin/env python3
"""Verify WindowServer's commit marks each IOSurface plane once per command buffer."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WsMarkOnceTests(unittest.TestCase):
    def test_marks_each_surface_plane_once_per_commit(self):
        source = (ROOT / "src/nmplugin/NVMTLEventSync.m").read_text()
        fn_start = source.index("static void nvmtl_ws_mark_pending(")
        start = source.index("    if (holds->early) {", fn_start)
        end = source.index("holds->dirtied = dirtied;", start) + len("holds->dirtied = dirtied;")
        loop = source[start:end] + "\n    }\n"

        harness = (
            "#import <Foundation/Foundation.h>\n"
            "#include <stdio.h>\n"
            "typedef struct { uint32_t id; } Surf;\n"
            "static uint32_t IOSurfaceGetID(Surf *s) { return s->id; }\n"
            "static unsigned calls, errors;\n"
            "static int refuse_id;\n"
            "static int nvmtl_vk_surface_dirty(uint32_t sid, uint32_t plane) {\n"
            "    (void)plane; calls++; return (int)sid == refuse_id ? -1 : 0;\n"
            "}\n"
            "@interface NVMTLTexture : NSObject { @public Surf *_surf; BOOL _vramOn; NSUInteger _plane; } @end\n"
            "@implementation NVMTLTexture @end\n"
            "@interface NVMTLSubmissionPart : NSObject { @public NSSet *surfaces; } @end\n"
            "@implementation NVMTLSubmissionPart @end\n"
            "@interface Holds : NSObject { @public BOOL early; NSSet *dirtied; } @end\n"
            "@implementation Holds @end\n"
            "@interface CB : NSObject { @public NSMutableArray *_parts; } @end\n"
            "@implementation CB @end\n"
            "static void check(int ok, const char *name) {\n"
            "    if (!ok) { fprintf(stderr, \"FAIL: %s\\n\", name); errors++; }\n"
            "}\n"
            "static void run(CB *cb, Holds *holds) {\n"
            + loop
            + "}\n"
            "static NVMTLTexture *tex(Surf *s, NSUInteger plane) {\n"
            "    NVMTLTexture *t = [NVMTLTexture new]; t->_surf = s; t->_vramOn = YES; t->_plane = plane; return t;\n"
            "}\n"
            "int main(void) { @autoreleasepool {\n"
            "    Surf video = { 7 }, desk = { 9 }, other = { 11 };\n"
            "    NVMTLTexture *v0 = tex(&video, 0), *v0view = tex(&video, 0), *v1 = tex(&video, 1), *d = tex(&desk, 0);\n"
            "    NVMTLTexture *off = tex(&other, 0); off->_vramOn = NO;\n"
            "    CB *cb = [CB new]; cb->_parts = [NSMutableArray new];\n"
            "    for (int partIdx = 0; partIdx < 4; partIdx++) {\n"
            "        NVMTLSubmissionPart *part = [NVMTLSubmissionPart new];\n"
            "        part->surfaces = [NSSet setWithObjects:v0, v0view, v1, d, off, nil];\n"
            "        [cb->_parts addObject:part];\n"
            "    }\n"
            "    [cb->_parts addObject:[NSNull null]];\n"
            "    Holds *h = [Holds new]; h->early = YES;\n"
            "    run(cb, h);\n"
            "    check(calls == 3, \"3 unique surface planes marked once across 4 parts\");\n"
            "    check([h->dirtied containsObject:v0] && [h->dirtied containsObject:v0view] && "
            "[h->dirtied containsObject:v1] && [h->dirtied containsObject:d], \"all marked textures recorded\");\n"
            "    check(![h->dirtied containsObject:off], \"non-vram texture skipped\");\n"
            "    calls = 0; refuse_id = 7; h = [Holds new]; h->early = YES;\n"
            "    run(cb, h);\n"
            "    check(calls == 3 && ![h->dirtied containsObject:v0] && ![h->dirtied containsObject:v0view] && "
            "![h->dirtied containsObject:v1], \"refused surface marked once per plane and omitted\");\n"
            "    check([h->dirtied containsObject:d], \"other surface still marked\");\n"
            "    return errors ? 1 : 0;\n"
            "} }\n"
        )
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "test.m"
            exe = Path(td) / "test"
            src.write_text(harness)
            subprocess.run([
                "xcrun", "clang", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                "-fobjc-arc", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                str(src), "-framework", "Foundation", "-o", str(exe),
            ], check=True, timeout=60)
            subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == "__main__":
    unittest.main()
