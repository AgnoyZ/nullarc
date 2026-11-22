"""Stage a native-submit mapping readiness check; no runtime opt-in."""

from build34_exact_submit import once
from build34_exact_vm_unmap import stage as previous_stage
from test_build34_exact_ownership import method


GEM = 'IOReturn IOAccelPhxNativeClient::doGemVa('
LEGACY = 'IOReturn IOAccelPhxNativeClient::doSubmit('
TYPED = 'IOReturn IOAccelPhxNativeClient::submitExactReceipt('
READY = 'bool IOAccelPhxNativeClient::nativeMappingsReady('
COVERED = 'bool IOAccelPhxNativeClient::ibCovered('
MAP = '        uint64_t va, size, off;\n        uint32_t flags;\n'
MAP_READY = MAP + '        bool materialized;\n'
DECL = '    bool ibCovered(uint64_t vaCanon, uint64_t bytes);\n'
DECL_READY = DECL + '    bool nativeMappingsReady();\n    bool mayHaveLogicalMappings{false};\n'
CHECK_READY = '''bool IOAccelPhxNativeClient::nativeMappingsReady() {
    if (!maps) return false;
    if (!mayHaveLogicalMappings) return true;
    for (int index = 0; index < kMaxMaps; ++index) {
        if (!maps[index].used) continue;
        if (!maps[index].materialized) return false;
        mayHaveLogicalMappings = false;
    }
    return true;
}

'''


def stage(source):
    source = once(previous_stage(source), MAP, MAP_READY)
    source = once(source, DECL, DECL_READY)
    covered = method(source, COVERED)
    source = once(source, covered, CHECK_READY + covered)
    gem = method(source, GEM)
    mapped = once(gem, '        if (vmid || owner->gpuReady()) {',
                  '        const bool materialize = vmid || owner->gpuReady();\n'
                  '        if (materialize) {')
    mapped = once(mapped, '        maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags};',
                  '        maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags, materialize};\n'
                  '        if (!materialize) mayHaveLogicalMappings = true;')
    source = once(source, gem, mapped)
    for signature in (LEGACY, TYPED):
        submit = method(source, signature)
        source = once(source, submit, once(submit, '    if (owner->gpuReady()) {\n',
                      '    if (owner->gpuReady()) {\n'
                      '        if (!nativeMappingsReady()) return kIOReturnNotReady;\n'))
    return source
