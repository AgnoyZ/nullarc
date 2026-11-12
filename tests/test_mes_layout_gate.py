"""Exercise the actual registry gate with a non-reference synthetic target."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MesLayoutGateTests(unittest.TestCase):
    def test_actual_gate_distinguishes_explicit_and_legacy_layouts(self):
        compiler = shutil.which("clang")
        if not compiler:
            self.skipTest("POSIX Clang required for the actual C layout gate")
        source = (ROOT / "tools/phxctl/mesboot.c").read_text()
        functions = source[source.index("static int env_on("):source.index("static int open_kext(")]
        declarations = "\n".join(line for line in source.splitlines()
                                 if line.startswith("static uint64_t vram_mc =") or line.startswith("static uint64_t fb_pa ="))
        harness = r'''
#define _DEFAULT_SOURCE
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define IORegistryEntryCreateCFProperty ignored_default_property
#include <IOKit/IOKitLib.h>
#undef IORegistryEntryCreateCFProperty
#include <CoreFoundation/CFNumber.h>
static int missing, wrong_kind;
static uint64_t observed_mc, observed_phys, observed_size;
static CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t svc, CFStringRef key, CFAllocatorRef alloc, uint32_t options) {
    (void)svc; (void)alloc; (void)options;
    if (missing) return NULL;
    static struct FakeCF value;
    value.kind = wrong_kind ? 99 : PHX_FAKE_CF_NUMBER_KIND;
    value.number = !strcmp(key, "phx-fb-mc-base") ? (long long)observed_mc :
                   !strcmp(key, "phx-fb-phys") ? (long long)observed_phys :
                   !strcmp(key, "phx-fb-size") ? (long long)observed_size : 34;
    return &value;
}
''' + declarations + "\n" + functions + r'''
int main(void) {
    const uint64_t ref_mc = vram_mc, ref_phys = fb_pa;
    observed_mc = 0x6000000000ull; observed_phys = 0x300000000ull; observed_size = 0x10000000;
    unsetenv("PHX_LAYOUT_REFERENCE");
    assert(layout_from_driver(1, 0) == -1 && vram_mc == ref_mc && fb_pa == ref_phys);
    setenv("PHX_LAYOUT_REFERENCE", "1", 1);
    assert(layout_from_driver(1, 1) == -1 && vram_mc == ref_mc && fb_pa == ref_phys);
    assert(layout_from_driver(1, 0) == 0 && vram_mc == ref_mc && fb_pa == ref_phys);
    unsetenv("PHX_LAYOUT_REFERENCE");
    missing = 1; assert(layout_from_driver(1, 1) == -1); missing = 0;
    wrong_kind = 1; assert(layout_from_driver(1, 1) == -1); wrong_kind = 0;
    observed_phys++; assert(layout_from_driver(1, 1) == -1); observed_phys--;
    observed_size = 0; assert(layout_from_driver(1, 1) == -1); observed_size = 0x10000000;
    uint64_t saved = observed_mc; observed_mc = UINT64_MAX; assert(layout_from_driver(1, 1) == -1); observed_mc = saved;
    saved = observed_phys; observed_phys = UINT64_MAX & ~0xfffull; assert(layout_from_driver(1, 1) == -1); observed_phys = saved;
    assert(vram_mc == ref_mc && fb_pa == ref_phys);
    assert(layout_from_driver(1, 1) == 0 && vram_mc == observed_mc && fb_pa == observed_phys);
    vram_mc = ref_mc; fb_pa = ref_phys; observed_mc = ref_mc; observed_phys = ref_phys;
    assert(layout_from_driver(1, 0) == 0 && vram_mc == ref_mc && fb_pa == ref_phys);
    assert(layout_from_driver(1, 1) == 0 && vram_mc == ref_mc && fb_pa == ref_phys);
    puts("12 actual layout-gate cases passed; no IOKit connection or hardware");
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix="phx-mes-layout-") as tmp:
            path = Path(tmp)
            (path / "gate.c").write_text(harness)
            result = subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", "-g",
                                     "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                                     "-I" + str(ROOT / "tests/fake_iokit"), str(path / "gate.c"),
                                     "-o", str(path / "gate")], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(path / "gate")], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("12 actual layout-gate cases passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
