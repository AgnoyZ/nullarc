"""Verify CPU binding checks and optionally compile the actual pinned Mesa overlay."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build34_dcn_radv_binding_stage as binding
import build34_dcn_radv_clear_stage as clear
import build34_dcn_radv_submit_stage as submit


class RenderBinding(unittest.TestCase):
    def run_checked(self, command, cwd=ROOT):
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_sanitized(self, source, flags=()):
        with tempfile.TemporaryDirectory() as tmp:
            binary = str(Path(tmp) / source.stem)
            self.run_checked([
                os.environ.get("CC", "clang"), "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-fno-omit-frame-pointer",
                "-I" + str(ROOT / "tools"), *flags, str(source), "-o", binary,
            ])
            self.run_checked([binary])

    def test_binding_ranges_and_handle_reuse(self):
        self.run_sanitized(Path(__file__).with_suffix(".c"))

    def test_clear_recording_lifetime(self):
        self.run_sanitized(ROOT / "tests/test_build34_dcn_radv_clear.c")

    def test_clear_submission_lifetime(self):
        self.run_sanitized(ROOT / "tests/test_build34_dcn_radv_submit.c")

    def test_pinned_mesa_native_syntax(self):
        recipe = os.environ.get("BUILD34_RADV_COMPILE_COMMANDS")
        if not recipe:
            self.skipTest("set BUILD34_RADV_COMPILE_COMMANDS to the reviewed Darwin Meson recipe")
        rows = json.loads(Path(recipe).read_text())
        commands = {}
        for name in (name for name in submit.INPUTS if name.endswith(".c")):
            matches = [row for row in rows if row["file"].endswith("/" + name)]
            self.assertEqual(len(matches), 1, name)
            row = matches[0]
            cwd = Path(row["directory"])
            source = (cwd / row["file"]).resolve(strict=True)
            commands[name] = (cwd, source, shlex.split(row["command"]))
        mesa = commands[binding.IMAGE][1].parents[3]
        for name, (_, source, _) in commands.items():
            self.assertEqual(mesa / name, source)

        inputs = {name: (mesa / name).read_bytes() for name in submit.INPUTS}
        for name in inputs:
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, name):
                submit.stage({**inputs, name: inputs[name] + b"\n"})
        sources = submit.stage(inputs)
        BO, IMAGE = binding.BO, binding.IMAGE
        self.assertLess(sources[BO].index("goto error_va_map;", sources[BO].index("radv_amdgpu_winsys_bo_from_ptr(")),
                        sources[BO].index("bo->dcn_host_map = host_map;"))
        self.assertLess(sources[IMAGE].index("      radv_bind_image_memory(device, image, bind_idx,"),
                        sources[IMAGE].index("image->dcn_render_binding = radv_dcn_bound_image("))
        self.assertNotIn("VKAPI_ATTR", sources[IMAGE][sources[IMAGE].index("static struct radv_dcn_render_binding"):
                                                    sources[IMAGE].index("radv_dcn_check_binding(map,")])

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            transport = sources[submit.DRM]
            (out / "staged_darwin_submit.inc").write_text(
                transport[transport.index("static bool\nacd_dcn_matches_plan("):transport.index("static int\nacd_cmd_ctx(")]
            )
            self.run_sanitized(ROOT / "tests/test_build34_dcn_radv_submit.c", ("-DTEST_DARWIN_SUBMIT", "-I" + tmp))
            for name in (binding.HEADER, clear.HEADER, submit.HEADER, submit.NATIVE_HEADER):
                sources[name] = (ROOT / "tools" / Path(name).name).read_text()
            overlay = []
            for name, source in sources.items():
                destination = out / Path(name).name
                destination.write_text(source)
                overlay.append({"type": "file", "name": str(mesa / name), "external-contents": str(destination)})
            manifest = out / "overlay.json"
            manifest.write_text(json.dumps({"version": 0, "use-external-names": False, "roots": overlay}))
            for name, (cwd, source, words) in commands.items():
                with self.subTest(name=name):
                    self.assertIn("-MD", words)
                    self.assertTrue(any(word.startswith("-DHAVE_AMDGPU_DARWIN") for word in words))
                    args = words[:words.index("-MD")]
                    self.run_checked([*args, "-fsyntax-only", "-ivfsoverlay", str(manifest), str(source)], cwd)


if __name__ == "__main__":
    unittest.main()
