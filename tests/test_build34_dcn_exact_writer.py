"""Exercise the staged exact writer protocol and page proof, without IOKit."""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import build34_dcn_exact_writer_stage as writer
import build34_dcn_firmware_home_stage as firmware_home
import build34_dcn_flip_commit_stage as flip_commit
import build34_dcn_present_handoff_stage as handoff
import build34_dcn_scanout_dma_stage as scanout_dma
import build34_dcn_scanout_pin_stage as scanout_pin
from build34_dcn_present_backing_stage import ACCEL, stage as present_backing
import build34_exact_submit_pressure as pressure
from build34_exact_open import stage as exact_open, stage_header
from test_build34_exact_ownership import method


DRIVER, ABI = [(ROOT / path).read_bytes() for path in (writer.DRIVER, writer.ABI)]
SIGNATURES = ('static bool shape(', writer.CURRENT, writer.SNAPSHOT, writer.COMPLETE, writer.PROBE, writer.MAP, writer.CONTEXT,
              writer.HANDLER, writer.WAIT, writer.ACK, pressure.SUBMIT,
              'bool PhxBringup::vmWorkCurrent(', 'PhxBringup::VmCtx *PhxBringup::vmOwned(',
              'IOAccelPhxNativeClient::Bo *IOAccelPhxNativeClient::findBo(')


class ExactWriterTests(unittest.TestCase):
    def setUp(self):
        self.source = writer.stage(DRIVER, ABI)
        directory = tempfile.TemporaryDirectory(prefix='phx34-exact-writer-')
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        headers = self.directory / 'headers'
        headers.mkdir()
        self.headers = headers
        for name, transform in {
            'build34_exact_ownership.h': lambda data: pressure.stage_ownership(stage_header(data)),
            'build34_exact_submit_wire.h': pressure.stage_submit_wire,
            'build34_exact_progress_wire.h': pressure.stage_progress_wire,
            'build34_dcn_writer_wire.h': str,
            'build34_dcn_writer_receipt.h': str,
        }.items():
            (headers / name).write_text(transform((ROOT / 'tools' / name).read_text()))

    def run_checked(self, args, timeout=90):
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_closed_native_and_no_submit_or_gpu_vm_changes(self):
        prior = pressure.stage(exact_open(DRIVER.decode()))
        for signature in ('bool PhxBringup::exactNativeOpenAdmitted(', 'bool PhxBringup::captureExactOpenLocked(',
                          'IOReturn IOAccelPhxNativeClient::externalMethod(', 'IOReturn PhxBringup::gpuSubmit(',
                          'IOReturn PhxBringup::vmMap(', 'void PhxBringup::invalidateExactQueues(', pressure.SUBMIT):
            self.assertEqual(method(self.source, signature), method(prior, signature))
        self.assertIn('    IOLockLock(lock);\n    exactWriter = {};\n', method(self.source, writer.CLOSE))
        self.assertIn('    return false;', method(self.source, 'bool PhxBringup::exactNativeOpenAdmitted('))
        self.assertEqual(method(self.source, writer.PROGRESS), method(prior, writer.PROGRESS).replace(
            'reply.flags = PHX34_R3_PRESSURE_FLAGS;', 'reply.flags = PHX34_R3_DCN_FLAGS;'))
        for driver, abi in ((DRIVER + b'\n', ABI), (DRIVER, ABI + b'\n')):
            with self.assertRaisesRegex(ValueError, 'source or ABI drift'):
                writer.stage(driver, abi)

    def test_extracted_native_exact_methods(self):
        self.check_native_methods()

    def test_extracted_present_handoff(self):
        self.check_native_methods(paired=True)

    def test_extracted_scanout_pin_lifetime(self):
        self.check_native_methods(paired=True, pins=True)

    def test_extracted_scanout_dma_lifetime(self):
        self.check_native_methods(paired=True, pins=True, dma=True)

    def test_extracted_scanout_flip_lifetime(self):
        self.check_native_methods(paired=True, pins=True, dma=True, flip=True)

    def test_firmware_sample_keeps_existing_scanout_and_vbl(self):
        original = (ROOT / firmware_home.FRAMEBUFFER).read_bytes()
        with self.assertRaisesRegex(ValueError, 'firmware sample source drift'):
            firmware_home.stage(original + b'\n')
        staged = firmware_home.stage(original)
        before = original.decode()
        def inline_method(source, signature):
            self.assertEqual(source.count(signature), 1)
            start = source.index(signature)
            return source[start:source.index('\n    }\n', start) + len('\n    }\n')]
        for signature in ('    static void vblFire(', '    void measureRefresh(', '    IOMemoryMap *aliasMap('):
            self.assertEqual(inline_method(before, signature), inline_method(staged, signature))
        signature = '    IOReturn callPlatformFunction('
        self.assertEqual(inline_method(staged, signature).replace(firmware_home.QUERY, ''), inline_method(before, signature))
        stop = method(staged, 'void PhxAMDFB::stop(')
        self.assertLess(stop.index('closeDcnFirmwareSample();'), stop.index('OSSafeReleaseNULL(fMmio)'))

    def test_present_handoff_preserves_collecting_only_boundaries(self):
        source = handoff.stage_native(DRIVER, ABI)
        for signature in ('bool PhxBringup::exactNativeOpenAdmitted(', 'bool PhxBringup::captureExactOpenLocked(',
                          'IOReturn PhxBringup::gpuSubmit(', pressure.SUBMIT, handoff.GLOBAL):
            self.assertEqual(method(source, signature), method(self.source, signature))
        accelerator = (ROOT / ACCEL).read_bytes()
        signature = 'IOReturn NVDisplayPipe::performTransaction('
        self.assertEqual(method(handoff.stage_accelerator(accelerator), signature),
                         method(present_backing(accelerator), signature))
        pinned = scanout_pin.stage_native(DRIVER, ABI)
        mapped = scanout_dma.stage_native(DRIVER, ABI)
        flipped = flip_commit.stage_native(DRIVER, ABI)
        for signature in ('bool PhxBringup::exactNativeOpenAdmitted(', 'IOReturn PhxBringup::gpuSubmit(',
                          'IOReturn IOAccelPhxNativeClient::externalMethod(', 'IOReturn PhxBringup::vmMap(',
                          handoff.CLOSE, handoff.SEAL, handoff.GLOBAL, pressure.SUBMIT):
            self.assertEqual(method(pinned, signature), method(source, signature))
            self.assertEqual(method(mapped, signature), method(pinned, signature))
            self.assertEqual(method(flipped, signature), method(mapped, signature))
        self.assertEqual(mapped.count('dcnCopyQualifiedMapper)(IOPCIDevice *){nullptr}'), 1)
        self.assertNotIn('dcnCopyQualifiedMapper =', mapped)
        self.assertEqual(flipped.count('dcnQualifiedFlipRoute)(IOPCIDevice *){nullptr}'), 1)
        self.assertNotIn('dcnQualifiedFlipRoute =', flipped)

    def check_native_methods(self, paired=False, pins=False, dma=False, flip=False):
        fixture = Path(__file__).with_suffix('.cpp').read_text()
        source = scanout_pin.stage_native(DRIVER, ABI) if pins else handoff.stage_native(DRIVER, ABI) if paired else self.source
        if dma:
            source = scanout_dma.stage_native(DRIVER, ABI)
        if flip:
            source = flip_commit.stage_native(DRIVER, ABI)
        client = source[source.index('class IOAccelPhxNativeClient :'):]
        types = client[client.index('    struct Bo {'):client.index('    IOReturn doHello(')]
        signatures = SIGNATURES
        if paired:
            signatures += (handoff.GLOBAL, handoff.ATTACH, handoff.CONSUME, handoff.DISPATCH, handoff.CLIENT_MATCH, handoff.OFFER,
                           handoff.CLOSE, handoff.SEAL)
        fields = handoff.PROVIDER_FIELDS
        probe = writer.PROBE_DECL
        if pins:
            signatures += (scanout_pin.PREPARE, scanout_pin.CANCEL)
            fields = fields[:fields.index('    bool checkDcnPresent(')] + scanout_pin.FIELDS + scanout_pin.OPERATIONS_DECL
            probe = scanout_pin.PROBE_DECL
        if dma:
            signatures += (scanout_dma.MAP,)
            fields = fields.replace(scanout_dma.CONSUME_DECL, scanout_dma.DMA_CONSUME + scanout_dma.MAPPER_GATE)
            fields = fields.replace(scanout_pin.OPERATIONS_DECL, scanout_dma.DMA_OPERATIONS_DECL)
            field = '        build34::dcn::ScanoutDescriptorPin descriptor;\n'
            fields = fields.replace(field, field + scanout_dma.DMA_FIELDS)
            probe = scanout_dma.DMA_PROBE_DECL
        if flip:
            signatures += (flip_commit.LOOKUP, flip_commit.BIND, flip_commit.BEGIN, flip_commit.POLL)
            fields = fields.replace(scanout_dma.DMA_FIELDS, scanout_dma.DMA_FIELDS + flip_commit.SLOT)
            fields = fields.replace(scanout_dma.MAPPER_GATE, scanout_dma.MAPPER_GATE + flip_commit.FIELDS)
        for marker, replacement in {
            '// WRITER_METHODS': ('static OwnerEpochs gDcnPinSerials;\n' if pins else '') +
            '\n'.join(method(source, signature) for signature in signatures),
            '// WRITER_SERVICE': handoff.DRAIN_DECL + handoff.PROVIDER_PUBLIC + fields
            if paired else writer.SERVICE_DECL,
            '// WRITER_CLIENT': writer.CLIENT_STATE + probe + (handoff.CLIENT_FIELDS if paired else ''),
            '// WRITER_TYPES': types,
        }.items():
            self.assertEqual(fixture.count(marker), 1)
            fixture = fixture.replace(marker, replacement)
        source = self.directory / 'fixture.cpp'
        binary = self.directory / 'writer-CPU-only'
        source.write_text(fixture)
        compiler = shlex.split(os.environ.get('CXX', 'clang++'))
        self.run_checked([*compiler, *(['-DTEST_PRESENT_HANDOFF'] if paired else []),
                          *(['-DTEST_SCANOUT_PINS'] if pins else []),
                          *(['-DTEST_SCANOUT_DMA'] if dma else []),
                          *(['-DTEST_SCANOUT_FLIP'] if flip else []),
                          '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-variable', '-O1', '-g',
                          '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I' + str(self.headers),
                          '-I' + str(ROOT / 'tests/build34_dcn'), '-I' + str(ROOT / 'tools'),
                          '-I' + str(ROOT / 'src/phxbringup'), str(source), '-o', str(binary)])
        if sys.platform == 'darwin':
            self.assertNotRegex(self.run_checked(['otool', '-L', str(binary)]), r'IOKit\.framework|Metal\.framework|vulkan')
        self.assertEqual(self.run_checked([str(binary)], timeout=15), '[PASS] exact writer backing (CPU only)\n')

    @unittest.skipUnless(os.environ.get('BUILD34_KERNEL_HEADERS'), 'set BUILD34_KERNEL_HEADERS to pinned SDK Headers')
    def test_kernel_sdk_syntax(self):
        src = self.directory / writer.DRIVER
        src.parent.mkdir(parents=True)
        (self.directory / writer.ABI).write_bytes(ABI)
        topology = self.directory / 'src/amd/phx_topology.h'
        topology.parent.mkdir()
        topology.write_bytes((ROOT / 'src/amd/phx_topology.h').read_bytes())
        compiler = shlex.split(os.environ.get('CXX', 'clang++'))
        flags = [*compiler, '-arch', 'x86_64', '-mmacosx-version-min=11.0', '-mkernel', '-fno-builtin',
                 '-fno-common', '-nostdinc', '-DKERNEL', '-DKERNEL_PRIVATE', '-DDRIVER_PRIVATE', '-DAPPLE', '-DNeXT',
                 '-std=c++17', '-fapple-kext', '-fno-rtti', '-fno-exceptions', '-fsyntax-only',
                 '-I' + os.environ['BUILD34_KERNEL_HEADERS'], '-I' + str(self.headers),
                 '-I' + str(ROOT / 'tools'), '-I' + str(src.parent)]
        for source in (self.source, handoff.stage_native(DRIVER, ABI), scanout_pin.stage_native(DRIVER, ABI),
                       scanout_dma.stage_native(DRIVER, ABI), flip_commit.stage_native(DRIVER, ABI)):
            src.write_text(source)
            self.run_checked([*flags, str(src)])
        accel = ROOT / ACCEL
        staged = self.directory / 'nvrm-accel.cpp'
        staged.write_text(handoff.stage_accelerator(accel.read_bytes()))
        self.run_checked([*flags, '-DNMX_ACCEL', '-DNM_TAHOE', '-DPHX_FB', '-I' + str(accel.parent.parent), '-I' + str(accel.parent),
                          '-I' + str(accel.parent / 'iofam'), '-I' + str(accel.parent / 're'), str(staged)])
        framebuffer = ROOT / firmware_home.FRAMEBUFFER
        staged_framebuffer = self.directory / framebuffer.name
        staged_framebuffer.write_text(firmware_home.stage(framebuffer.read_bytes()))
        self.run_checked([*flags, '-DNMX_ACCEL', '-DNM_TAHOE', '-DPHX_FB', '-I' + str(framebuffer.parent),
                          '-I' + str(framebuffer.parent.parent), str(staged_framebuffer)])


if __name__ == '__main__':
    unittest.main()
