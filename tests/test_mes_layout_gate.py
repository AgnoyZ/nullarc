"""Exercise current mesboot layout/entrypoint contracts using fake IOKit only."""
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
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


@unittest.skipIf(os.name == "nt", "Full fake-I/O entrypoint tests require POSIX")
class MesEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang")
        if not compiler:
            raise unittest.SkipTest("Clang required for actual mesboot with fake IOKit")
        cls.temporary = tempfile.TemporaryDirectory(prefix="phx-mes-entrypoint-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.binary = Path(cls.temporary.name) / "mesboot-fake-only"
        result = subprocess.run([compiler, "-std=c11", "-D_DEFAULT_SOURCE", "-Wall", "-Wextra", "-g",
                                 "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                                 "-I" + str(ROOT / "tests/fake_iokit"), "-I" + str(ROOT / "tools/phxctl"),
                                 str(ROOT / "tests/test_mes_entrypoint.c"), "-o", str(cls.binary)],
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise RuntimeError("Fake-only actual entrypoint compile failed: " + result.stderr)

    @staticmethod
    def environment():
        return {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"}

    @staticmethod
    def accounting(result):
        prefix = "fake-entrypoint-summary "
        rows = [line[len(prefix):] for line in result.stderr.splitlines() if line.startswith(prefix)]
        if len(rows) != 1:
            raise AssertionError("Missing actual-entrypoint accounting: " + result.stderr)
        data = json.loads(rows[0])
        if set(data) != {"lookups", "opens", "releases", "hellos", "claims", "snapshots", "closes"}:
            raise AssertionError("Unexpected entrypoint accounting keys")
        if any(type(value) is not int for value in data.values()):
            raise AssertionError("Unexpected entrypoint accounting types")
        return data

    def invoke(self, fixture, fault, *arguments):
        return subprocess.run([str(self.binary), fixture, fault, *arguments], env=self.environment(),
                              capture_output=True, text=True, timeout=10)

    def test_legacy_claim_and_scheduler_refuse_relocated_layout_before_side_effects(self):
        for command in ("claim", "kiqsched"):
            with self.subTest(command=command):
                result = self.invoke("relocated", "ok", command)
                self.assertEqual(1, result.returncode, result.stderr)
                self.assertIn("not the reference layout", result.stderr)
                self.assertEqual(dict(lookups=1, opens=1, releases=1, hellos=1, claims=0,
                                      snapshots=0, closes=1), self.accounting(result))

    def test_legacy_claim_refuses_missing_layout(self):
        result = self.invoke("missing", "ok", "claim")
        self.assertEqual(1, result.returncode, result.stderr)
        self.assertIn("did not publish a usable carve-out", result.stderr)
        self.assertEqual(0, self.accounting(result)["claims"])
        self.assertEqual(1, self.accounting(result)["closes"])

    def test_explicit_bootstrap_reaches_snapshot_with_relocated_layout(self):
        for command in ("gart", "mes"):
            with self.subTest(command=command):
                result = self.invoke("relocated", "ok", command, "0x4000000000", "0x5000", "0x700000", "0x710000")
                self.assertEqual(74, result.returncode, result.stderr)
                self.assertIn("selector=116", result.stderr)
                self.assertNotIn("not the reference layout", result.stderr)
                self.assertEqual(dict(lookups=1, opens=1, releases=1, hellos=1, claims=0,
                                      snapshots=1, closes=0), self.accounting(result))
                self.assertNotIn("fake-entrypoint-returned", result.stdout)

    def test_bare_bootstrap_refuses_before_service_lookup(self):
        for command in ("gart", "mes"):
            with self.subTest(command=command):
                result = self.invoke("relocated", "ok", command)
                self.assertEqual(64, result.returncode, result.stderr)
                self.assertEqual(dict.fromkeys(("lookups", "opens", "releases", "hellos", "claims",
                                               "snapshots", "closes"), 0), self.accounting(result))

    def test_claim_transport_failure_is_terminal_in_current_entrypoint(self):
        for fault, expected in (("ok", 0), ("claim-status", 74)):
            with self.subTest(fault=fault):
                result = self.invoke("reference", fault, "claim")
                self.assertEqual(expected, result.returncode, result.stderr)
                self.assertEqual(1, self.accounting(result)["claims"])
                self.assertEqual(expected == 0, "claim -> kr 0x0" in result.stdout)
                if expected:
                    self.assertIn("mesboot transport: selector=113", result.stderr)
                    self.assertNotIn("fake-entrypoint-returned", result.stdout)

    def test_hello_failures_precede_actual_claim(self):
        for fault in ("hello-status", "hello-short", "hello-long", "hello-abi"):
            with self.subTest(fault=fault):
                result = self.invoke("reference", fault, "claim")
                self.assertEqual(1 if fault == "hello-abi" else 74, result.returncode, result.stderr)
                self.assertEqual(0, self.accounting(result)["claims"])
                self.assertEqual(0, self.accounting(result)["snapshots"])

    def gate_fixture(self, work, fixture, fault):
        stages = work / "stages"
        stages.mkdir()
        # These are test-only stage adapters; no initializer, monitor, target command or release-hold hook exists here.
        claim = stages / "20-claim"
        command = shlex.join([str(self.binary), fixture, fault, "claim"])
        claim.write_text("#!/bin/sh\nexec " + command + "\n")
        claim.chmod(0o700)
        later = stages / "30-later-sentinel"
        later.write_text("#!/bin/sh\nprintf 'later\\n' > " + shlex.quote(str(work / "later.calls")) + "\n")
        later.chmod(0o700)
        release = work / "release-fake"
        release.write_text("#!/bin/sh\nprintf 'release\\n' >> " + shlex.quote(str(work / "release.calls")) + "\n")
        release.chmod(0o700)
        uname = work / "uname-fake"
        uname.write_text("#!/bin/sh\ncase $1 in -s) echo Darwin;; -m) echo x86_64;; *) exit 99;; esac\n")
        uname.chmod(0o700)
        ioreg = work / "ioreg-fake"
        ioreg.write_text('''#!/bin/sh
cat <<'FIXTURE'
"phx-780m-policy" = "strict-execution-v1"
"phx-build" = 37
"phx-fb-phys" = 553648128
"phx-fb-aper-len" = 268435456
FIXTURE
''')
        ioreg.chmod(0o700)
        env = {**self.environment(), "PHX_BOOT_GATE_TEST": "1", "PHX_UNAME": str(uname), "PHX_IOREG": str(ioreg)}
        args = ["/bin/sh", str(ROOT / "tools/phx_boot_gate.sh"), "--state", str(work / "state"),
                "--stages", str(stages), "--expected-build", "37", "--release", str(release), "--timeout", "10"]
        return args, env

    def test_actual_gate_preserves_claim_failure_and_stops_later_stage(self):
        for fixture, fault, status in (("relocated", "ok", 1), ("reference", "claim-status", 74)):
            with self.subTest(fixture=fixture, fault=fault), tempfile.TemporaryDirectory(prefix="phx-claim-gate-") as tmp:
                work = Path(tmp)
                args, env = self.gate_fixture(work, fixture, fault)
                result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=15)
                self.assertEqual(77, result.returncode, result.stderr)
                self.assertEqual("20-claim " + str(status) + "\n", (work / "state/results.txt").read_text())
                self.assertFalse((work / "later.calls").exists())
                self.assertEqual("release\n", (work / "release.calls").read_text())
                self.assertFalse((work / "state/attempt.pending").exists())

    def test_actual_gate_success_control_is_only_fake_claim_status(self):
        with tempfile.TemporaryDirectory(prefix="phx-claim-gate-") as tmp:
            work = Path(tmp)
            args, env = self.gate_fixture(work, "reference", "ok")
            result = subprocess.run(args, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("20-claim 0\n30-later-sentinel 0\n", (work / "state/results.txt").read_text())
            self.assertEqual("later\n", (work / "later.calls").read_text())
            self.assertEqual("release\n", (work / "release.calls").read_text())

    def test_actual_gate_release_waits_for_blocked_claim(self):
        with tempfile.TemporaryDirectory(prefix="phx-claim-gate-block-") as tmp:
            work = Path(tmp)
            args, env = self.gate_fixture(work, "reference", "claim-block")
            fifo = work / "fake-claim.fifo"
            os.mkfifo(fifo, 0o600)
            env["PHX_FAKE_CLAIM_FIFO"] = str(fifo)
            # An explicit FIFO is required: a non-interactive shell background stage gets empty stdin by default.
            with os.fdopen(os.open(fifo, os.O_RDWR | os.O_NONBLOCK), "wb", buffering=0) as unblock:
                process = subprocess.Popen(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True, start_new_session=True)
                try:
                    evidence = work / "state/stage-20-claim.out"
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        self.assertIsNone(process.poll(), "gate exited before reaching fake claim block")
                        if evidence.exists() and "fake-claim-waiting-for-input" in evidence.read_text():
                            break
                        time.sleep(0.02)
                    else:
                        self.fail("actual entrypoint never reached the fake claim FIFO")
                    self.assertFalse((work / "release.calls").exists())
                    self.assertFalse((work / "later.calls").exists())
                    self.assertTrue((work / "state/attempt.pending").exists())
                    unblock.write(b"\n")
                    _, error = process.communicate(timeout=10)
                    self.assertEqual(0, process.returncode, error)
                    self.assertEqual("release\n", (work / "release.calls").read_text())
                    self.assertEqual("later\n", (work / "later.calls").read_text())
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.communicate(timeout=5)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
