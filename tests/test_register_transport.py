"""Extract the real register transport into a CPU-only BAR/IOKit harness.

Address oracles are independent literals, not SEG1. This checks software units
and value propagation; ordinary host memory cannot validate a physical GPU BAR.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def fragment(source, expression):
    matches = re.findall(expression, source, re.M | re.S)
    if len(matches) != 1:
        raise RuntimeError("Actual register source fragment missing or ambiguous: " + expression)
    return matches[0] + "\n"


class RegisterTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("clang++")
        if not compiler:
            raise RuntimeError("Actual register CPU contracts require Clang; absence is not a pass")
        cls.temporary = tempfile.TemporaryDirectory(prefix="phx-register-cpu-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.directory = Path(cls.temporary.name)
        provider = (ROOT / "src/phxbringup/PhxBringup.cpp").read_text()
        cli = (ROOT / "tools/phxctl/mesboot.c").read_text()
        definitions = []
        for name in ("rreg", "wreg", "writeReg", "readRegs"):
            definitions.append(fragment(provider,
                r"^(?:uint32_t|void|IOReturn) PhxBringup::" + name + r"\([^\n]*\)(?: const)? \{.*?^\}\n"))
        for name in ("externalMethod", "doReadRegs", "doDbgWriteReg"):
            definitions.append(fragment(provider,
                r"^IOReturn IOAccelPhxNativeClient::" + name + r"\(.*?^\}\n"))
        definitions.insert(0, fragment(provider, r"^static bool shape\(.*?^\}\n"))
        definitions.insert(0, fragment(provider, r"^static constexpr uint64_t kGoldenTscUpper = [^\n]+;"))
        (cls.directory / "register-provider.inc").write_text("\n".join(definitions))
        # Unrelated dispatcher branches must fail if accidentally entered.
        dispatcher = fragment(provider, r"^IOReturn IOAccelPhxNativeClient::externalMethod\(.*?^\}\n")
        unused = sorted(set(re.findall(r"\b(do\w+)\(a\)", dispatcher)) - {"doReadRegs", "doDbgWriteReg"})
        (cls.directory / "register-unused.inc").write_text("\n".join(
            f'IOReturn {name}(IOExternalMethodArguments *) {{ assert(!"unrelated dispatcher branch"); return kIOReturnUnsupported; }}'
            for name in unused))
        definitions = [fragment(cli, r"^#define " + name + r"(?:\([^\n]*?\))? [^\n]+")
                       for name in ("SEL_READREGS", "SEL_DBG_WRITE_REG", "SEG1")]
        for name in ("checked_scalar", "checked_method", "rd", "wr", "grbm_select"):
            definitions.append(fragment(cli,
                r"^static (?:kern_return_t|uint32_t) " + name + r"\(.*?^\}\n"))
        (cls.directory / "register-cli.inc").write_text("\n".join(definitions))
        cls.binary = cls.directory / "register-fake"
        result = subprocess.run([
            compiler, "-std=c++17", "-g", "-Wall", "-Wextra", "-Werror",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
            "-I" + str(ROOT / "src/phxbringup"), "-I" + str(cls.directory),
            str(ROOT / "tests/test_register_transport.cpp"), "-o", str(cls.binary),
        ], capture_output=True, text=True, timeout=90)
        if result.returncode:
            raise RuntimeError("Fake-only register compile failed: " + result.stderr)

    def case(self, name, status=0):
        result = subprocess.run([str(self.binary), name], capture_output=True, text=True,
                                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, timeout=15)
        self.assertEqual(status, result.returncode, result.stderr)
        if status == 0:
            self.assertEqual("actual-register-methods-passed " + name, result.stdout.strip())
        else:
            self.assertIn("mesboot transport:", result.stderr)

    def test_cli_to_actual_dispatch_and_mmio_preserves_literal_address_and_fields(self):
        self.case("roundtrip")

    def test_provider_dword_units_and_range_boundaries(self):
        self.case("bounds")

    def test_read_abi_rejects_invalid_shapes_ranges_and_privilege(self):
        self.case("read-abi")

    def test_write_abi_rejects_invalid_shapes_wide_scalars_and_privilege(self):
        self.case("write-abi")

    def test_actual_dispatch_retains_handshake_closed_and_mutation_gates(self):
        self.case("dispatch")

    def test_synthetic_lost_store_returns_real_zero_in_both_reply_paths(self):
        self.case("lost-store")

    def test_provider_status_cannot_be_turned_into_zero_success_by_cli(self):
        for name in ("read-not-ready", "write-not-ready", "write-denied"):
            with self.subTest(name=name):
                self.case(name, 74)


if __name__ == "__main__":
    unittest.main()
