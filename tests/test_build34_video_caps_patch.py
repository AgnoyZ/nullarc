#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools/upstream34_layout/radv_video_caps_sources.json"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mesa-source", required=True)
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    mesa = Path(args.mesa_source).resolve()
    relative = "src/amd/common/ac_video.c"
    source = mesa / relative
    source_bytes = source.read_bytes()
    assert sha256(source_bytes) == manifest["input_sha256"][relative], "unexpected Mesa source"

    patch = ROOT / manifest["patch"]
    patch_bytes = patch.read_bytes()
    if manifest["patch_sha256"] != "pending":
        assert sha256(patch_bytes) == manifest["patch_sha256"], "video capability patch hash drift"

    with tempfile.TemporaryDirectory(prefix="build34-video-caps-") as temporary:
        stage = Path(temporary)
        target = stage / relative
        target.parent.mkdir(parents=True)
        target.write_bytes(source_bytes)
        run(["git", "init", "-q", str(stage)])
        run(["git", "-C", str(stage), "apply", "--unidiff-zero", "--check", str(patch)])
        run(["git", "-C", str(stage), "apply", "--unidiff-zero", str(patch)])

        patched = target.read_text()
        declaration = re.search(
            r"struct amdgpu_codec_cap \{.*?\} dec_cap\[8\] = \{0\}, enc_cap\[8\] = \{0\};",
            patched,
            re.S,
        )
        assert declaration, "both codec capability result arrays must start zeroed"
        assert "info->video_caps.dec[codec].supported &= dec_cap[i].valid;" in patched
        assert "info->video_caps.enc[codec].supported &= enc_cap[i].valid;" in patched

        test_source = "#include <stdint.h>\nint main(void) {\n" + declaration.group(0) + "\n"
        test_source += (
            "for (unsigned i = 0; i < 8; ++i) "
            "if (dec_cap[i].valid || enc_cap[i].valid) return 1;\nreturn 0;\n}\n"
        )
        c_file = stage / "video_caps_zero_init.c"
        binary = stage / "video_caps_zero_init"
        c_file.write_text(test_source)
        run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(c_file), "-o", str(binary)])
        run([str(binary)])

    print("PASS: exact Mesa patch applies and codec query results default to unsupported")


if __name__ == "__main__":
    main()
