"""Exercise the staged NativeClient methods with CPU-only platform doubles."""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build34_dcn_render_map_stage import ABI, DRIVER, stage
from build34_dcn_present_backing_stage import ACCEL, stage as present_stage
from test_build34_exact_ownership import method


def render_fixture(source):
    client = source[source.index("class IOAccelPhxNativeClient :"):source.index(
        "OSDefineMetaClassAndStructors(IOAccelPhxNativeClient,")]
    constants = source[source.index("static constexpr uint64_t kHostCap"):
                       source.index("class PhxBringup :")]
    staged_methods = ("static bool shape(", "IOAccelPhxNativeClient::Bo *IOAccelPhxNativeClient::findBo(",
                      "IOReturn IOAccelPhxNativeClient::doBoImportHost(", "IOReturn IOAccelPhxNativeClient::doGemVa(",
                      "const IOAccelPhxNativeClient::Map *IOAccelPhxNativeClient::softwareMappedHostRangeLocked(",
                      "build34::dcn::LiveHostRenderMap IOAccelPhxNativeClient::liveHostRenderMapLocked(",
                      "build34::dcn::RenderTlbAck IOAccelPhxNativeClient::confirmRenderTlbLocked(",
                      "bool IOAccelPhxNativeClient::acquireRenderBackingClientLocked(",
                      "bool IOAccelPhxNativeClient::acquirePresentBackingClientLocked(",
                      "IOReturn IOAccelPhxNativeClient::doBoFree(", "void IOAccelPhxNativeClient::boRelease(",
                      "void IOAccelPhxNativeClient::freeAll(", "IOReturn IOAccelPhxNativeClient::clientClose(")
    copy = method(present_stage((ROOT / ACCEL).read_bytes()), "IOReturn NVDisplayPipe::performTransaction(")
    start = copy.index("    if (nvAccelObserveDcnCopyBacking &&")
    end = copy.index("    nvAccelIopHome(fb, head);", start)
    slots = {
        "// PHX34_RENDER_MAP_CONSTANTS": constants,
        "    // PHX34_RENDER_MAP_TYPES": client[client.index("    struct Bo {"):client.index("    IOReturn doHello(")],
        "    // PHX34_RENDER_MAP_FIELDS": client[client.index("    uint32_t vmid{"):client.index("    task_t task{")],
        "// PHX34_RENDER_MAP_METHODS": "\n".join(method(source, signature) for signature in staged_methods),
        "    // PHX34_PRESENT_BACKING_PROBE": copy[start:end],
    }
    fixture = Path(__file__).with_suffix(".cpp").read_text()
    for marker, code in slots.items():
        if fixture.count(marker) != 1:
            raise ValueError("CPU fixture marker drift: " + marker)
        fixture = fixture.replace(marker, code)
    return fixture


def render_vm_fixture(source):
    driver = source[source.index("class PhxBringup :"):source.index("OSDefineMetaClassAndStructors(PhxBringup,")]
    fields = driver[driver.index("    static constexpr uint32_t kPtChunkBytes"):
                    driver.index("    uint32_t vmBind(")]
    queues = driver[driver.index("    struct GpuQueue {"):driver.index("    uint64_t queueFence(")]
    registers = source[source.index("static constexpr uint32_t kFirstUserVmid"):
                       source.index("static inline void flushLine(")]
    signatures = ("uint64_t PhxBringup::nextRenderVmGenerationLocked(",
                  "build34::dcn::RenderVmTranslation PhxBringup::renderVmIdentityLocked(",
                  "bool PhxBringup::takeRenderEngine17Locked(",
                  "build34::dcn::RenderTlbAck PhxBringup::confirmRenderTlbLocked(",
                  "IOReturn PhxBringup::adoptQueue(", "IOReturn PhxBringup::writeReg(",
                  "void PhxBringup::vmFlushTlb(",
                  "uint32_t PhxBringup::vmidAlloc(", "uint32_t PhxBringup::vmBind(", "void PhxBringup::vmidFree(",
                  "IOReturn PhxBringup::vmMap(", "IOReturn PhxBringup::vmUnmap(", "IOReturn PhxBringup::setPowerState(")
    fixture = Path(__file__).with_name("test_build34_dcn_render_vm.cpp").read_text()
    for marker, code in {"// PHX34_VM_FIELDS": fields, "// PHX34_VM_QUEUES": queues, "// PHX34_VM_REGISTERS": registers,
                         "// PHX34_VM_METHODS": "\n".join(method(source, signature) for signature in signatures)
                         }.items():
        if fixture.count(marker) != 1:
            raise ValueError("CPU fixture marker drift: " + marker)
        fixture = fixture.replace(marker, code)
    return fixture


class RenderMapTests(unittest.TestCase):
    def test_pins_production_inputs(self):
        driver, abi = (ROOT / DRIVER).read_bytes(), (ROOT / ABI).read_bytes()
        with self.assertRaisesRegex(ValueError, "source or ABI drift"):
            stage(driver + b"\n", abi)
        with self.assertRaisesRegex(ValueError, "source or ABI drift"):
            stage(driver, abi + b"\n")

    def test_staged_methods(self):
        source = stage((ROOT / DRIVER).read_bytes(), (ROOT / ABI).read_bytes())
        self.check_fixture(render_fixture(source), "host-map generations")

    def test_present_backing_stage_keeps_copy_and_flip(self):
        original = (ROOT / ACCEL).read_bytes()
        with self.assertRaisesRegex(ValueError, "backing source drift"):
            present_stage(original + b"\n")
        before = method(original.decode(), "IOReturn NVDisplayPipe::performTransaction(")
        after = method(present_stage(original), "IOReturn NVDisplayPipe::performTransaction(")
        start = after.index("    if (nvAccelObserveDcnCopyBacking &&")
        self.assertLess(after.index("iopMapSurface(s->getSurfaceID(), md, H * P)"), start)
        self.assertLess(after.index("if (w != q.width || h != q.height)"), start)
        home = "    nvAccelIopHome(fb, head);"
        self.assertEqual(before[before.index(home):], after[after.index(home):])

    def test_staged_gpuvm_identities(self):
        source = stage((ROOT / DRIVER).read_bytes(), (ROOT / ABI).read_bytes())
        self.check_fixture(render_vm_fixture(source), "GPUVM identities", "-Wno-unused-parameter")

    def test_all_raw_debug_writers_are_guarded(self):
        source = stage((ROOT / DRIVER).read_bytes(), (ROOT / ABI).read_bytes())
        writers = ("writeReg", "vramWrite", "doorbellWrite", "sysMem", "smuMessage", "pspRing",
                   "pspSubmit", "fwStage", "loadIpFw", "pspCtl", "pspRaw")
        for writer in writers:
            with self.subTest(writer=writer):
                body = method(source, "IOReturn PhxBringup::" + writer + "(").split("{\n", 1)[1]
                self.assertTrue(body.startswith("    phx34_exact::CallbackGate<>::Lease rawWriter(renderRawWriters);\n"
                                                "    if (!rawWriter)\n        return kIOReturnNotReady;\n"))

    def check_fixture(self, cpu_source, label, *additional_flags):
        with tempfile.TemporaryDirectory(prefix="phx34-render-map-CPU-") as directory:
            fixture = Path(directory) / "render-map.cpp"
            binary = Path(directory) / "render-map-CPU-only"
            fixture.write_text(cpu_source)
            compile_result = subprocess.run([
                *shlex.split(os.environ.get("CXX", "clang++")), "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                *additional_flags,
                "-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-I" + str(ROOT / "src/phxbringup"),
                "-I" + str(ROOT / "tools"),
                "-I" + str(ROOT / "tests/build34_dcn"),
                str(fixture), "-o", str(binary),
            ], capture_output=True, text=True, timeout=90)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            if sys.platform == "darwin":
                linkage = subprocess.check_output(["otool", "-L", str(binary)], text=True, timeout=15)
                self.assertNotRegex(linkage, r"IOKit\.framework|Metal\.framework|vulkan")
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(result.stdout, f"[PASS] staged build34 {label} (CPU only)\n")


if __name__ == "__main__":
    unittest.main()
