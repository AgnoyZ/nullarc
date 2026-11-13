"""Fault-inject the patched pinned Darwin transport with CPU-only IOKit/logging doubles."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/radv_iokit_transport.c"
PATCH = ROOT / "patches/radv/0003-bounded-native-allocation-diagnostics.patch"
SOURCE_SHA256 = "96e4151e6258f302eb167a5be23f478435acbbf563616ea0a895dc91a3a1ada4"


def patched_transport(source=FIXTURE):
    data = Path(source).read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("Transport differs from the reviewed pinned Darwin source")
    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        path = stage / "src/amd/common/darwin/ac_darwin_iokit.c"
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        for options in (("--check",), ()):
            subprocess.run(["git", "apply", *options, str(PATCH)], cwd=stage,
                           check=True, capture_output=True, timeout=30)
        return path.read_text()


def exercise(out, source=FIXTURE):
    out = Path(out).resolve()
    if out.exists():
        raise RuntimeError("Diagnostic output exists; choose a fresh directory")
    compiler = shutil.which("clang")
    if not compiler:
        raise RuntimeError("Clang required; no skipped test counts as a pass")
    patched = patched_transport(source)
    # Only platform headers are replaced. Execute every actual patched function,
    # including selector remapping, native calls and CPU-map output handling.
    tested = re.sub(r'^#include (?:"ac_darwin_kext.h"|<IOKit/IOKitLib.h>|<mach/mach.h>|<os/log.h>)\n',
                    "", patched, flags=re.M)
    out.mkdir(parents=True)
    (out / "radv_iokit_patched.inc").write_text(tested)
    binary = out / "radv-allocation-diagnostic-test"
    subprocess.run([compiler, "-std=c11", "-D_DEFAULT_SOURCE", "-Wall", "-Wextra", "-Werror", "-g",
                    "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-pthread",
                    "-I" + str(out), "-I" + str(ROOT / "tests"), "-I" + str(ROOT / "src/phxbringup"),
                    str(ROOT / "tests/test_radv_allocation_diagnostic.c"), "-o", str(binary)],
                   check=True, timeout=120)
    process = subprocess.run([str(binary)], capture_output=True, text=True, check=True, timeout=30)
    result = json.loads(process.stdout)
    if result != {"cases": 54, "concurrent_calls": 1200, "hardware_executed": False, "real_iokit_linked": False}:
        raise RuntimeError("Unexpected transport diagnostic result")
    result.update({"fixture_sha256": SOURCE_SHA256,
                   "patched_transport_sha256": hashlib.sha256(patched.encode()).hexdigest(),
                   "patch_sha256": hashlib.sha256(PATCH.read_bytes()).hexdigest(),
                   "limitation": "Actual patched pinned transport; fake IOKit and OSLog. Does not validate real log persistence, GPU allocation or desktop execution."})
    (out / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(exercise(args.out), indent=2))
