import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from test_ib_fetch_sync import PACKET_CASES, check_regression, exercise, replace_submit
from upstream34_layout import ib_fetch_sync


class IbFetchSyncTests(unittest.TestCase):
    def original(self):
        result = subprocess.run(["git", "cat-file", "-e", ib_fetch_sync.BASE + "^{commit}"],
                                cwd=ROOT, capture_output=True, timeout=10)
        if result.returncode:
            self.skipTest("Pinned build34 commit unavailable; full actual-method target requires it")
        return subprocess.check_output(["git", "show", ib_fetch_sync.BASE + ":" + ib_fetch_sync.SOURCE], cwd=ROOT)

    def test_exact_backport_and_source_drift_refusal(self):
        original = self.original()
        result = ib_fetch_sync.transform(original).decode()
        for before, after in reversed(ib_fetch_sync.REPLACEMENTS):
            self.assertIn(after, result)
            result = result.replace(after, before)
        self.assertEqual(original, result.encode())
        with self.assertRaises(ValueError):
            ib_fetch_sync.transform(original + b"\n")

    def test_build34_pair_is_distinguished_and_never_overwrites(self):
        self.original()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "new"
            source, record = ib_fetch_sync.materialize(out)
            self.assertEqual(42, record["candidate_build"])
            self.assertFalse(record["original_build34_image"])
            self.assertFalse(record["installed"])
            self.assertFalse(record["GPU_executed"])
            self.assertIn(b"#define PHX_KEXT_BUILD 42u", (source / ib_fetch_sync.SOURCE).read_bytes())
            self.assertTrue((source / "src/amd/phx_topology.h").is_file())
            for name, digest in record["source_files_sha256"].items():
                self.assertEqual(digest, ib_fetch_sync.sha((source / name).read_bytes()))
            with self.assertRaises(ValueError):
                ib_fetch_sync.materialize(out)

    def test_actual_method_replacement_refuses_missing_or_duplicate(self):
        method = "IOReturn PhxBringup::gpuSubmit() {\n}\n"
        self.assertEqual(method, replace_submit(method, method))
        for old, new in (("missing", method), (method, "missing"), (method + method, method), (method, method + method)):
            with self.assertRaises(ValueError):
                replace_submit(old, new)

    def test_regression_requires_specific_actual_assertion(self):
        failure = "Assertion failed: p.memory.words == expected && selected.wptr == start + needed"
        check_regression(subprocess.CompletedProcess([], -6, "", failure))
        for code, out, err in ((0, "", failure), (-11, "", "crash"), (-6, "unexpected", failure), (-6, "", "Assertion unrelated")):
            with self.assertRaises(RuntimeError):
                check_regression(subprocess.CompletedProcess([], code, out, err))

    def test_packet_matrix_covers_engines_multi_IBs_wrap_and_space(self):
        self.assertEqual(len(PACKET_CASES), len(set(PACKET_CASES)))
        self.assertEqual(18, len(PACKET_CASES))
        for engine in ("compute", "graphics"):
            for suffix in ("", "-upper", "-wrap", "-short-ring", "-multi", "-max", "-max-wrap", "-space-exact", "-space-short"):
                self.assertIn("packet-" + engine + suffix, PACKET_CASES)

    def test_unsupported_host_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch("test_ib_fetch_sync.platform.system", return_value="Windows"):
            out = Path(directory) / "new"
            with self.assertRaises(RuntimeError):
                exercise(out)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
