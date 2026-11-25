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
import build34_dcn_bar5_stage as bar5
import build34_dcn_firmware_home_stage as firmware_home
import build34_dcn_phxfb_lease_stage as fb_lease
import build34_dcn_flip_commit_stage as flip_commit
import build34_dcn_present_handoff_stage as handoff
import build34_dcn_scanout_dma_stage as scanout_dma
import build34_dcn_scanout_pin_stage as scanout_pin
import build34_dcn_transaction_stage as transaction
import build34_dcn_raw_tail_stage as raw_tail
from build34_dcn_present_backing_stage import ACCEL, stage as present_backing
import build34_exact_submit_pressure as pressure
from build34_exact_open import stage as exact_open, stage_header
from build34_exact_submit import once
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
        self.check_native_methods(paired=True, pins=True, dma=True, flip=True, bar5_adapter=True)

    def test_raw_tail_adoption(self):
        native = bar5.stage_native(DRIVER, ABI)
        adopt = method(native, raw_tail.ADOPT)
        self.assertLess(adopt.index('if (!exactRawWriters.drained())'), adopt.index('if (!dcnRawTailMatchesLocked('))
        # The coherent-pair sampler stays an unbound hook: declared, null-initialized, never assigned.
        self.assertEqual(native.count('dcnCoherentFence'), 4)
        self.assertIn('const DcnCoherentFenceAccess *dcnCoherentFence{nullptr};', native)
        self.assertEqual(native.count('dcnCoherentFence ='), native.count('dcnCoherentFence{nullptr}') - 1)
        for mutation in ('exactQueueAdopted[qi] = true;', 'exactFenceWindow[qi].invalidate();', 'fence[0] ='):
            self.assertLess(adopt.index('if (!dcnRawTailMatchesLocked('), adopt.index(mutation))
        self.assertEqual(method(native, 'bool PhxBringup::exactNativeOpenAdmitted('),
                         method(self.source, 'bool PhxBringup::exactNativeOpenAdmitted('))
        (self.directory / 'raw-tail-decl.inc').write_text(raw_tail.DECLARATION)
        (self.directory / 'raw-tail-method.inc').write_text(method(native, raw_tail.VERIFY))
        binary = self.directory / 'raw-tail-CPU-only'
        compiler = shlex.split(os.environ.get('CXX', 'clang++'))
        self.run_checked([*compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-O1', '-g',
                          '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I' + str(self.directory),
                          '-I' + str(ROOT / 'tools'), str(ROOT / 'tests/test_build34_dcn_raw_tail.cpp'), '-o', str(binary)])
        self.run_checked([str(binary)])

    @unittest.skipUnless(sys.platform == 'darwin', 'bootstrap uses Darwin SDK headers')
    def test_raw_tail_bootstrap(self):
        bootstrap = raw_tail.stage_bootstrap((ROOT / 'tools/phxctl/mesboot.c').read_text())
        full = self.directory / 'staged-mesboot.c'
        full.write_text(bootstrap)
        compiler = ['xcrun', 'clang', '-std=gnu11', '-I' + str(ROOT / 'tools/phxctl')]
        self.run_checked([*compiler, '-fsyntax-only', str(full)])
        mock = once(bootstrap, method(bootstrap, 'static int open_kext('), 'static int open_kext(void) { return mockOpen(); }\n')
        (self.directory / 'cpu-mesboot.inc').write_text(mock)
        base = (ROOT / 'tests/test_build34_exact_bootstrap_progress.c').read_text()
        base = once(base, '/* Resolve the fake transport',
                    'static void completeMes(uint64_t);\nstatic void injectDuringPacket(uint64_t);\n'
                    'static void completeTail(uint64_t, uint64_t, uint64_t, unsigned);\n/* Resolve the fake transport')
        base = once(base, '        *word(in[0]) = (uint32_t)in[1];',
                    '        *word(in[0]) = (uint32_t)in[1];\n        injectDuringPacket(in[0]);')
        base = once(base, '            *word(SCH_WB + 64) = mesBells == badMesStatus ? 0 : 1;', '            completeMes(in[1]);')
        for bell, wptr, call in [('cmp', 'in[4] != 8', 'CMP_RING, in[1], PHX34_CMP_TAIL_FENCE, 1'),
                                 ('gfx', 'in[4] != sizeof(kCsbGfx11) / 4 + 8', 'GFX_RING, in[1], PHX34_GFX_TAIL_FENCE, 2')]:
            base = once(base, wptr, wptr + ' + 8')
            launch = f'            if ({bell}Published != {bell}Bells) abort();'
            base = once(base, launch, launch + f'\n            completeTail({call});')
        entry = 'int main(int argc, char **argv)'
        (self.directory / 'base-fixture.inc').write_text(once(base, entry, 'static int progress_main(int argc, char **argv)'))
        mes = (ROOT / 'tests/test_build34_exact_mes_status.c').read_text()
        (self.directory / 'mes-status-fixture.inc').write_text(once(mes, entry, 'int mes_status_main(int argc, char **argv)'))
        binary = self.directory / 'raw-tail-bootstrap-CPU-only'
        self.run_checked([*compiler, '-I' + str(self.directory), '-DCHECKED_STAGE', '-DISOLATED', '-O1', '-g',
                          '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
                          str(ROOT / 'tests/test_build34_dcn_raw_tail.c'), '-o', str(binary)])
        self.assertNotRegex(self.run_checked(['otool', '-L', str(binary)]), r'IOKit\.framework|Metal\.framework|vulkan')
        self.run_checked([str(binary)])

    def test_scanout_transaction_caller(self):
        source = transaction.stage_native(DRIVER, ABI)
        accelerator = transaction.stage_accelerator((ROOT / ACCEL).read_bytes())
        dispatch = method(source, handoff.DISPATCH)
        self.assertIn('return submitDcnPresent(', dispatch)
        for isolated in ('BUILD34_DCN_PRESENT_PROBE', 'BUILD34_DCN_PIN_MAP', 'BUILD34_DCN_FLIP_BEGIN', 'BUILD34_DCN_FLIP_POLL'):
            self.assertNotIn(isolated, dispatch)
        self.assertIn('route->framebuffer != intent.framebuffer', method(source, flip_commit.BEGIN))
        self.assertEqual(method(source, 'bool PhxBringup::exactNativeOpenAdmitted('),
                         method(self.source, 'bool PhxBringup::exactNativeOpenAdmitted('))
        perform = method(accelerator, transaction.PERFORM)
        self.assertNotIn('nvAccelObserveDcnCopyBacking', perform)
        self.assertIn('!fromRes && !l10r', perform)
        self.assertLess(perform.index('fDcnPresent.presented(txn)'), perform.index('nvAccelIopHome(fb, head)'))
        self.assertLess(perform.index('if (result != DcnPresentResult::Copy)'), perform.index('movnti'))
        self.assertLess(perform.index('if (result != DcnPresentResult::Copy)'), perform.rindex('nvAccelSurfCopyReady(s, head)'))
        self.assertLess(perform.index('if (!dcnAttempt)'), perform.index('nvAccelSurfCopyReady(s, head)'))
        self.assertIn('if (!dcnAttempt)\n#endif\n        {\n            src = (const volatile unsigned int *)iopMapSurface(', perform)
        self.assertEqual(perform.count('iopMapSurface('), 2)
        self.assertLess(perform.index('if (result != DcnPresentResult::Copy)'), perform.rindex('iopMapSurface('))
        self.assertLess(perform.rindex('a->askFramebufferForScanout('), perform.rindex('iopMapSurface('))
        self.assertIn('observed = describePresentBacking(', perform)
        self.assertIn('fDcnPresent.check(txn, complete)', method(accelerator, transaction.COMPLETE))
        self.assertNotIn('nvAccelDcnSleepable', accelerator)
        self.assertIn('kDcnPresentReady', dispatch)
        self.assertLess(perform.index('nvAccelDcnCallerCurrent('), perform.index('callPlatformFunction(kDcnPresentReady,'))
        self.assertLess(perform.rindex('nvAccelDcnCallerCurrent('), perform.index('nvAccelSubmitDcnPresent('))
        self.assertNotIn('dcnPlacePresent', source)
        submit = method(source, transaction.NATIVE)
        self.assertLess(submit.index('BUILD34_DCN_CHECK_FIRMWARE'), submit.index('mapDcnPin('))
        self.assertLess(submit.index('dcnPresentBacking.acquirePresent('), submit.index('mapDcnPin('))
        self.assertLess(submit.index('dcnPresentBacking.releaseUnused()'), submit.index('const auto result = submit(intent)'))
        self.assertIn('request.framebuffer, &route}', submit)
        self.check_native_methods(paired=True, pins=True, dma=True, flip=True, bar5_adapter=True, present=source, accel=accelerator)

    def test_paired_framebuffer_route(self):
        native = fb_lease.stage_native(DRIVER, ABI)
        framebuffer = fb_lease.stage_framebuffer((ROOT / firmware_home.FRAMEBUFFER).read_bytes())
        self.assertIn(fb_lease.FB_QUERY, framebuffer)
        self.assertEqual(framebuffer.count('fDcnRoute.closeLocked();'), 2)
        self.assertLess(method(framebuffer, 'void PhxAMDFB::stop(').index('closeDcnFirmwareSample();'),
                        method(framebuffer, 'void PhxAMDFB::stop(').index('OSSafeReleaseNULL(fMmio)'))
        submit = method(native, transaction.NATIVE)
        self.assertLess(submit.index('acquireDcnFbRoute(route, home)'), submit.index('dcnPresentBacking.acquirePresent('))
        self.assertLess(submit.index('submit(home) != ScanoutFlipResult::Presented'), submit.index('releaseDcnFbRoute()'))
        self.assertIn('dcnQualifiedFlipRoute)(IOPCIDevice *){nullptr}', native)
        self.assertEqual(method(native, 'bool PhxBringup::exactNativeOpenAdmitted('),
                         method(self.source, 'bool PhxBringup::exactNativeOpenAdmitted('))
        self.check_native_methods(paired=True, pins=True, dma=True, flip=True, bar5_adapter=True, lease=native)

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
        bound = bar5.stage_native(DRIVER, ABI)
        for signature in ('bool PhxBringup::exactNativeOpenAdmitted(',
                          'IOReturn IOAccelPhxNativeClient::externalMethod(', 'IOReturn PhxBringup::vmMap(',
                          handoff.CLOSE, handoff.SEAL, handoff.GLOBAL, pressure.SUBMIT):
            self.assertEqual(method(pinned, signature), method(source, signature))
            self.assertEqual(method(mapped, signature), method(pinned, signature))
            previous = method(mapped, signature)
            if signature == flip_commit.MAP:
                previous = previous.replace('    for (uint64_t p = 0; p < size; p += 4096) {\n',
                    flip_commit.MAP_PREFLIGHT + '    for (uint64_t p = 0; p < size; p += 4096) {\n').replace(
                    '        uint64_t *pte = validPage ?', flip_commit.MAP_PAGE_GATE + '        uint64_t *pte = validPage ?').replace(
                    '        *pte =', flip_commit.MAP_RECORD + '        *pte =')
            self.assertEqual(method(flipped, signature), previous)
            self.assertEqual(method(bound, signature), method(flipped, signature))
        mapped_submit = method(mapped, flip_commit.SUBMIT)
        self.assertEqual(mapped_submit, method(source, flip_commit.SUBMIT))
        staged_submit = method(flipped, flip_commit.SUBMIT)
        self.assertEqual(staged_submit, method(bound, flip_commit.SUBMIT))
        self.assertEqual(staged_submit.replace(flip_commit.SUBMIT_EPOCH + flip_commit.SUBMIT_GATE, ''),
                         mapped_submit.replace(flip_commit.SUBMIT_EPOCH, ''))
        self.assertLess(staged_submit.index('IOLockLock(gpuLock);'), staged_submit.index(flip_commit.SUBMIT_EPOCH))
        self.assertLess(staged_submit.index(flip_commit.SUBMIT_GATE), staged_submit.index('vmBind('))
        self.assertLess(staged_submit.index(flip_commit.SUBMIT_GATE), staged_submit.index('exact->publish('))
        for stage in (mapped, flipped, bound):
            self.assertEqual(stage.count('dcnQualifyMapper)(IOPCIDevice &, IOMapper &){nullptr}'), 1)
            self.assertNotIn('dcnQualifyMapper =', stage)
            self.assertEqual(stage.count('dcnQualifyDirect)(IOPCIDevice &){nullptr}'), 1)
            self.assertNotIn('dcnQualifyDirect =', stage)
        mapping = method(mapped, scanout_dma.MAP)
        self.assertEqual(mapping.count('IOMapper::copyMapperForDevice(device)'), 1)
        self.assertLess(mapping.index('return prepareDcnPin'), mapping.index('IOMapper::copyMapperForDevice(device)'))
        self.assertNotIn('gSystem', mapping)
        self.assertNotIn('mapToPhysicalAddress', mapping)
        self.assertEqual(flipped.count('dcnQualifiedFlipRoute)(IOPCIDevice *){nullptr}'), 1)
        self.assertNotIn('dcnQualifiedFlipRoute =', flipped)
        self.assertNotIn('dcnQualifiedFlipRoute =', bound)
        self.assertIn('dcnProveGpuVmOwnership)(const PhxBringup &, build34::dcn::PhysicalPageSet){nullptr}', bound)
        self.assertNotIn('dcnProveGpuVmOwnership =', bound)
        self.assertIn('DcnGpuPermissionPhase){nullptr}', bound)
        self.assertNotIn('dcnGpuPermissionEvidence =', bound)
        bind = method(bound, flip_commit.VM_BIND)
        self.assertIn(flip_commit.BOUND_SLOT_GATE, bind)
        self.assertIn(flip_commit.FREE_SLOT_GATE, bind)
        self.assertLess(bind.index('dcnGpuWrites.bound('), bind.index('wreg('))
        self.assertLess(bind.index('if (!vmFlushTlbChecked(vmid))'), bind.index('dcnGcvm[pick] ='))
        self.assertNotIn('dcnGcvm', method(bound, flip_commit.VM_FREE))
        current = method(bound, writer.CURRENT)
        self.assertLess(current.index('drain->matches(*expected)'), current.index('dcnGcvmCurrent()'))
        self.assertLess(current.index('dcnProveGpuVmOwnership(*this, pages) && dcnGcvmCurrent()'),
                        current.index('reserve->reserve(dcnSubmitGate)'))
        begin = method(bound, flip_commit.BEGIN)
        self.assertLess(begin.index('bindDcnBar5(intent, boundRoute)'), begin.index('dcnFlip.begin('))
        self.assertIn('return barLive && dcnBar5Live();', method(bound, flip_commit.POLL))
        power = method(bound, 'IOReturn PhxBringup::setPowerState(')
        self.assertLess(power.index('&dcnBar5Revoked'), power.index('invalidateExactQueues();'))

    def check_native_methods(self, paired=False, pins=False, dma=False, flip=False, bar5_adapter=False, present=None, lease=None, accel=None):
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
            signatures += (scanout_pin.CANCEL_SLOT, scanout_pin.REMEMBER_PIN_CANCELLATION,
                           scanout_pin.PREPARE, scanout_pin.CANCEL)
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
            signatures += (flip_commit.WRITER_CURRENT, flip_commit.LOOKUP, flip_commit.BIND, flip_commit.BEGIN,
                           flip_commit.POLL, flip_commit.PERMISSION_CURRENT, flip_commit.PERMISSION_TABLE,
                           flip_commit.PERMISSION_CHANGE, flip_commit.PERMISSION_RESTORE, flip_commit.VM_FREE)
            fields = fields.replace(scanout_dma.DMA_FIELDS, scanout_dma.DMA_FIELDS + flip_commit.SLOT)
            fields = fields.replace(scanout_dma.MAPPER_GATE, scanout_dma.MAPPER_GATE + flip_commit.FIELDS)
            probe += flip_commit.CLIENT
            submit_gate = method(source, flip_commit.SUBMIT)
            self.assertEqual(submit_gate.count(flip_commit.SUBMIT_GATE), 1)
            boundary = '            // DCN_SUBMIT_GATE\n'
            self.assertEqual(fixture.count(boundary), 1)
            fixture = fixture.replace(boundary, ''.join('    ' + line for line in flip_commit.SUBMIT_GATE.splitlines(True)))
        extracted = '\n'.join(method(source, signature) for signature in signatures)
        if flip:
            extracted += '\n' + method(source, flip_commit.MAP).replace('PhxBringup::vmMap(', 'PhxBringup::guardedVmMap(', 1)
        if bar5_adapter:
            bound = lease if lease is not None else bar5.stage_native(DRIVER, ABI)
            fields += bar5.FIELDS
            extracted += '\n' + '\n'.join(method(bound, signature) for signature in bar5.SIGNATURES)
            extracted += '\n' + method(bound, writer.CURRENT).replace('::exactWriterVmCurrent(', '::checkBar5WriterCurrent(', 1)
            fixture = fixture.replace('// GCVM_FIELDS', bar5.GCVM_FIELDS)
            declaration = flip_commit.DRAIN_DECL.split('\n', 1)[1]
            fixture = fixture.replace('// GCVM_WRITER', declaration.replace('exactWriterVmCurrent(', 'checkBar5WriterCurrent('))
        if flip:
            extracted += '\n' + method(bound if bar5_adapter else source, flip_commit.VM_BIND)
        if lease is not None:
            fields += fb_lease.NATIVE_FIELDS
            extracted += '\n' + '\n'.join(method(lease, signature) for signature in (fb_lease.ACQUIRE, fb_lease.RELEASE))
            self.assertEqual(fixture.count('// FRAMEBUFFER_ROUTE_FIELDS'), 1)
            self.assertEqual(fixture.count('// FRAMEBUFFER_ROUTE_QUERY'), 1)
            fixture = fixture.replace('// FRAMEBUFFER_ROUTE_FIELDS', fb_lease.FB_FIELDS)
            fixture = fixture.replace('// FRAMEBUFFER_ROUTE_QUERY', fb_lease.FB_QUERY)
        if present is not None:
            fixture = fixture.replace('// TRANSACTION_FIELDS', transaction.FIELDS)
            fixture = fixture.replace('// TRANSACTION_METHOD', '\n'.join(
                method(present, signature).replace('PhxBringup::', 'TransactionFixture::', 1)
                for signature in (transaction.READY, transaction.NATIVE)))
            fixture = fixture.replace('// ACCEL_CONTEXT', method(accel, transaction.ACCEL_CONTEXT))
        for marker, replacement in {
            '// WRITER_METHODS': ('static OwnerEpochs gDcnPinSerials;\n' if pins else '') +
            extracted,
            '// WRITER_SERVICE': (flip_commit.DRAIN_DECL if flip else handoff.DRAIN_DECL) + handoff.PROVIDER_PUBLIC + fields
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
                          *(['-DTEST_SCANOUT_BAR5'] if bar5_adapter else []),
                          *(['-DTEST_SCANOUT_TRANSACTION'] if present is not None else []),
                          *(['-DTEST_SCANOUT_FB_LEASE'] if lease is not None else []),
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
                       scanout_dma.stage_native(DRIVER, ABI), flip_commit.stage_native(DRIVER, ABI), bar5.stage_native(DRIVER, ABI),
                       transaction.stage_native(DRIVER, ABI), fb_lease.stage_native(DRIVER, ABI)):
            src.write_text(source)
            self.run_checked([*flags, str(src)])
        accel = ROOT / ACCEL
        staged = self.directory / 'nvrm-accel.cpp'
        staged.write_text(handoff.stage_accelerator(accel.read_bytes()))
        accel_flags = [*flags, '-DNMX_ACCEL', '-DNM_TAHOE', '-DPHX_FB', '-I' + str(accel.parent.parent), '-I' + str(accel.parent),
                       '-I' + str(accel.parent / 'iofam'), '-I' + str(accel.parent / 're'), str(staged)]
        self.run_checked(accel_flags)
        staged.write_text(transaction.stage_accelerator(accel.read_bytes()))
        stubs = ROOT / transaction.STUBS
        (self.directory / stubs.name).write_text(transaction.stage_stubs(stubs.read_text()))
        self.run_checked(accel_flags)
        framebuffer = ROOT / firmware_home.FRAMEBUFFER
        staged_framebuffer = self.directory / framebuffer.name
        for stage in (firmware_home.stage, fb_lease.stage_framebuffer):
            staged_framebuffer.write_text(stage(framebuffer.read_bytes()))
            self.run_checked([*flags, '-DNMX_ACCEL', '-DNM_TAHOE', '-DPHX_FB', '-I' + str(framebuffer.parent),
                              '-I' + str(framebuffer.parent.parent), str(staged_framebuffer)])


if __name__ == '__main__':
    unittest.main()
