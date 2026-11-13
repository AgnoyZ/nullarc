"""Fault-inject the pinned real RADV constructor using explicit CPU-only API fakes."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/radv_cmd_buffer_constructor.c"
PATCH = ROOT / "patches/radv/0002-initialize-command-buffer-cleanup-before-stream.patch"
CONSTRUCTOR_SHA256 = "bdfbc84e5888e499d2f8e8d9a324875f8730b9ce62a504c8317f74df8167f737"


def constructor(source):
    marker = "static VkResult\nradv_create_cmd_buffer("
    if source.count(marker) != 1:
        raise RuntimeError("Expected one pinned RADV constructor")
    start = source.index(marker)
    end = source.index("\n}\n", start) + 3
    return source[start:end]


def exercise(out, source=FIXTURE):
    out, source = Path(out).resolve(), Path(source).resolve()
    if out.exists():
        raise RuntimeError("Output exists; choose a fresh directory")
    compiler = shutil.which("clang")
    if not compiler:
        raise RuntimeError("Clang is required; no skipped test counts as a pass")
    original = source.read_text(encoding="utf-8")
    body = constructor(original)
    if hashlib.sha256(body.encode()).hexdigest() != CONSTRUCTOR_SHA256:
        raise RuntimeError("Constructor differs from the reviewed pinned Mesa source")
    with tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        path = stage / "src/amd/vulkan/radv_cmd_buffer.c"
        path.parent.mkdir(parents=True)
        path.write_text(original, encoding="utf-8")
        for args in (("--check",), ()):
            subprocess.run(["git", "apply", *args, str(PATCH)], cwd=stage,
                           check=True, capture_output=True, timeout=30)
        patched = constructor(path.read_text(encoding="utf-8"))
    out.mkdir(parents=True)
    reports = {}
    for name, text in (("negative", body), ("patched", patched)):
        variant = out / name
        variant.mkdir()
        (variant / "radv_constructor.inc").write_text(text, encoding="utf-8")
        binary = variant / "radv-cmd-init-test"
        command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                   "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                   "-I" + str(variant), str(ROOT / "tests/test_radv_cmd_init.c"), "-o", str(binary)]
        if name == "negative":
            command.insert(1, "-DNEGATIVE_CONTROL=1")
        subprocess.run(command, check=True, timeout=120)
        result = json.loads(subprocess.check_output([str(binary)], text=True, timeout=30))
        if result != {"cases": 6, "hardware_executed": False}:
            raise RuntimeError("Unexpected constructor test result")
        reports[name] = {**result, "constructor_sha256": hashlib.sha256(text.encode()).hexdigest(),
                         "stream_failure_cleanup_preconditions_satisfied": name == "patched"}
    result = {"variants": reports, "patch_sha256": hashlib.sha256(PATCH.read_bytes()).hexdigest(),
              "fixture_matches_pinned_constructor": True,
              "limitation": "Real constructor, fake allocation/stream/cleanup APIs. The negative control observes missing cleanup initialization; it does not execute Mesa's complete destructor. No installed runtime, GPU execution, allocation-cause or device-loss fix is validated."}
    (out / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=FIXTURE)
    args = parser.parse_args()
    print(json.dumps(exercise(args.out, args.source), indent=2))
