"""The fake CoreFoundation copies the SDK's include graph, so a missing include fails here and not only on macOS.

`macos-kexts` run 41789199775 failed on `tools/phxctl/mesboot.c`: its layout gate calls `CFNumberGetTypeID()` and
`CFNumberGetValue()`, but `<IOKit/IOKitLib.h>` on macOS brings in `CFBase.h` and `CFString.h` and *not*
`CFNumber.h` -- `error: call to undeclared function 'CFNumberGetTypeID'`. `source-tests` had been green on the same
commit, because the fake headers handed out the whole CoreFoundation API through their umbrella and through
`IOKitLib.h` alike, which the real SDK never does. The fake was more permissive than the platform, so the cheaper
job could not see the mistake.

These assertions keep the fake faithful instead of convenient: `CFNumber.h` is a separate header, the umbrella
includes it, `IOKitLib.h` does not, and every native tool that calls the CFNumber API asks for it itself.
`tools/` is the scope because that is what the macOS job compiles; `src/nmplugin` is built by no workflow here, so
its include requirements cannot be verified and are deliberately out of scope.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests/fake_iokit"
CFNUMBER_API = re.compile(r"\bCFNumber(?:Create|GetValue|GetTypeID)\b")
PROVIDES_CFNUMBER = re.compile(
    r"#\s*(?:include|import)\s*<(?:CoreFoundation/CFNumber\.h|CoreFoundation/CoreFoundation\.h"
    r"|Foundation/Foundation\.h|Cocoa/Cocoa\.h|AppKit/AppKit\.h)>")


def includes(path):
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("#include") or line.strip().startswith("#import")]
class FakeCoreFoundationTests(unittest.TestCase):
    def test_the_umbrella_still_offers_the_whole_api(self):
        headers = includes(FAKE / "CoreFoundation/CoreFoundation.h")
        for header in ("CFBase.h", "CFString.h", "CFNumber.h"):
            self.assertIn(f"#include <CoreFoundation/{header}>", headers,
                          f"the fake umbrella no longer includes {header}")

    def test_the_fake_iokitlib_does_not_export_cfnumber(self):
        # This is the whole point: macOS's IOKitLib.h stops at CFBase/CFString, so the fake must too.
        headers = includes(FAKE / "IOKit/IOKitLib.h")
        self.assertNotIn("#include <CoreFoundation/CFNumber.h>", headers,
                         "the fake IOKitLib.h exports CFNumber.h; a tool that uses CFNumber without including it "
                         "would pass here and fail in macos-kexts")
        self.assertNotIn("#include <CoreFoundation/CoreFoundation.h>", headers,
                         "the fake IOKitLib.h exports the CoreFoundation umbrella, which the real one does not")
        self.assertIn("#include <CoreFoundation/CFBase.h>", headers)
        self.assertIn("#include <CoreFoundation/CFString.h>", headers)

    def test_cfnumber_lives_in_its_own_header(self):
        self.assertTrue((FAKE / "CoreFoundation/CFNumber.h").is_file())
        for name in ("CoreFoundation.h", "CFString.h"):
            self.assertNotIn("CFNumberGetValue", (FAKE / "CoreFoundation" / name).read_text(encoding="utf-8"),
                             f"{name} declares the CFNumber API; it belongs in CoreFoundation/CFNumber.h")

    def test_every_native_tool_asks_for_the_cfnumber_api_itself(self):
        checked = 0
        for source in sorted((ROOT / "tools").rglob("*")):
            if source.suffix not in (".c", ".cpp", ".m", ".mm") or not source.is_file():
                continue
            text = source.read_text(encoding="utf-8", errors="replace")
            if not CFNUMBER_API.search(text):
                continue
            checked += 1
            self.assertTrue(PROVIDES_CFNUMBER.search(text),
                            f"{source.relative_to(ROOT)} calls the CFNumber API but does not include "
                            "<CoreFoundation/CFNumber.h>, <CoreFoundation/CoreFoundation.h> or a framework umbrella; "
                            "it compiles against the fakes on Linux and fails in macos-kexts")
        self.assertGreater(checked, 0, "no native tool uses the CFNumber API any more; this test can be revisited")

    def test_the_layout_gate_still_reads_the_published_numbers(self):
        # The include that broke the macOS build is the one this gate needs, so pin the two together.
        tool = (ROOT / "tools/phxctl/mesboot.c").read_text(encoding="utf-8")
        self.assertIn("CFNumberGetValue", tool)
        self.assertIn("<CoreFoundation/CFNumber.h>", tool)


if __name__ == "__main__":
    unittest.main()
