"""Stage checked session discovery and independent prefix for an already bound client."""

from build34_exact_dispatch_mode import DISPATCH, MODE_GATE, stage as previous_stage
from build34_exact_binding import CLIENT_VALID
from build34_exact_submit import once
from test_build34_exact_ownership import method


PREFIX = 'bool PhxBringup::readExactPrefix('
PROGRESS = 'IOReturn IOAccelPhxNativeClient::doExactProgress('
OWNER_GETTER = '    uint64_t ownerEpoch() const { return owner_; }\n'
PREFIX_DECL = '    bool readExactPrefix(uint64_t &);\n'
PROGRESS_DECL = '    IOReturn doExactProgress(uint32_t, IOExternalMethodArguments *);\n'

SERVICE = '''bool PhxBringup::readExactPrefix(uint64_t &retired) {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return false;
    ExactOverlapSnapshot scratch{};
    IOLockLock(gpuLock);
    const bool valid = exactGlobalRetiredLocked(retired, &scratch);
    IOLockUnlock(gpuLock);
    return valid;
}
'''

CLIENT = '''IOReturn IOAccelPhxNativeClient::doExactProgress(uint32_t selector, IOExternalMethodArguments *a) {
    const uint64_t start = mach_absolute_time();
    phx34_exact::CallbackGate<>::Lease callback(exactClientCallbacks);
    if (!callback) return kIOReturnNotReady;
    if (!a || (selector != PHX34_R3_SEL_SESSION && selector != PHX34_R3_SEL_PREFIX) ||
        a->selector != selector || a->version != kIOExternalMethodArgumentsCurrentVersion ||
        a->scalarInputCount || a->scalarOutputCount || !a->structureInput || !a->structureOutput ||
        a->structureInputSize != sizeof(phx34_r3_progress_request) ||
        a->structureOutputSize != sizeof(phx34_r3_progress_reply) ||
        a->structureInputDescriptor || a->structureOutputDescriptor || a->structureOutputDescriptorSize ||
        a->structureVariableOutputData || a->asyncWakePort || a->asyncReference || a->asyncReferenceCount)
        return kIOReturnBadArgument;
    phx34_r3_progress_request request;
    memcpy(&request, a->structureInput, sizeof(request));
    const bool session = selector == PHX34_R3_SEL_SESSION;
    if (request.version != PHX34_R3_WIRE_VERSION || request.size != sizeof(request) ||
        request.timeout_ns > PHXN_WAIT_CAP_NS || request.target == UINT64_MAX ||
        (!request.target && request.timeout_ns) ||
        (session ? (request.owner || request.target) : (!request.owner || request.owner == UINT64_MAX)))
        return kIOReturnBadArgument;

    for (;;) {
        phx34_r3_progress_reply reply{};
        IOLockLock(lock);
        IOReturn result = kIOReturnNotReady;
        if (hello && (''' + CLIENT_VALID + ''') && !boCleanupFault &&
            !exactClientCallbacks.closed() && !owner->exactAdmissionClosed()) {
            if (!session && !exactRegistry.hasOwner(request.owner)) result = kIOReturnNotFound;
            else if (request.target > emitted) result = kIOReturnBadArgument;
            else if (owner->readExactPrefix(reply.retired)) {
                reply.owner = exactRegistry.ownerEpoch();
                result = kIOReturnSuccess;
            }
        }
        IOLockUnlock(lock);
        if (result != kIOReturnSuccess) return result;

        uint64_t elapsed = 0;
        absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
        if (exactClientCallbacks.closed() || owner->exactAdmissionClosed()) return kIOReturnNotReady;
        if (reply.retired >= request.target || elapsed >= request.timeout_ns) {
            reply.version = PHX34_R3_WIRE_VERSION;
            reply.size = sizeof(reply);
            reply.build = PHX_KEXT_BUILD;
            reply.flags = PHX34_R3_PROGRESS_FLAGS;
            reply.target = request.target;
            memcpy(a->structureOutput, &reply, sizeof(reply));
            return kIOReturnSuccess;
        }
        IOSleep(1);
    }
}
'''


def stage_header(source):
    anchor = '    bool hasOwner('
    return once(source, anchor, OWNER_GETTER + anchor)


def stage(source):
    source = previous_stage(source)
    source = once(source, '#include "build34_exact_submit_wire.h"\n',
                  '#include "build34_exact_submit_wire.h"\n#include "build34_exact_progress_wire.h"\n')
    source = once(source, '    bool exactAdmissionClosed() const;\n',
                  '    bool exactAdmissionClosed() const;\n' + PREFIX_DECL)
    source = once(source, '    IOReturn doExactSubmit(IOExternalMethodArguments *);\n',
                  '    IOReturn doExactSubmit(IOExternalMethodArguments *);\n' + PROGRESS_DECL)
    anchor = 'uint64_t PhxBringup::queueFence(const GpuQueue &q) const {\n'
    source = once(source, anchor, SERVICE + '\n' + CLIENT + '\n' + anchor)
    dispatch = method(source, DISPATCH)
    dispatch_new = once(dispatch, MODE_GATE, MODE_GATE.replace('selector == PHX34_R3_SEL_ACK_RECEIPT;',
                        'selector == PHX34_R3_SEL_ACK_RECEIPT ||\n'
                        '        selector == PHX34_R3_SEL_SESSION || selector == PHX34_R3_SEL_PREFIX;'))
    route = '    if (selector == PHX34_R3_SEL_SUBMIT_RECEIPT)\n'
    dispatch_new = once(dispatch_new, route, '    if (selector == PHX34_R3_SEL_SESSION || selector == PHX34_R3_SEL_PREFIX)\n'
                        '        return doExactProgress(selector, a);\n' + route)
    return once(source, dispatch, dispatch_new)
