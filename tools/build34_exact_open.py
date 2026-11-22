"""Stage exact IOKit open admission without enabling a native backend."""

from build34_exact_progress_wire import stage as previous_stage, stage_header as progress_header
from build34_exact_close import stage_header as close_header
from build34_exact_submit import once
from test_build34_exact_ownership import method


FACTORY = 'IOReturn PhxBringup::newUserClient('
INIT = 'bool IOAccelPhxNativeClient::initWithTask('
BIND = 'bool PhxBringup::bindExactClient('
ADMITTED = 'bool PhxBringup::exactNativeOpenAdmitted('
SNAPSHOT = 'bool PhxBringup::captureExactOpenLocked('
OPEN_PROOF = '''struct Phx34ExactOpen {
    uint64_t epoch = 0;
    uint64_t generation[2]{};
    bool matches(const Phx34ExactOpen &other) const {
        return epoch == other.epoch && generation[0] == other.generation[0] &&
               generation[1] == other.generation[1];
    }
};

'''
DECLARATIONS = '''    bool exactNativeOpenAdmitted() const;
    bool captureExactOpenLocked(Phx34ExactOpen &) const;
'''
SERVICE = '''bool PhxBringup::exactNativeOpenAdmitted() const {
    return false;
}

bool PhxBringup::captureExactOpenLocked(Phx34ExactOpen &out) const {
    if (!exactNativeOpenAdmitted() || !exactDwordReader || exactCallbacks.closed() ||
        !hangTimerReady() || exactStopped || isSleeping || exactVMFault ||
        watchdogRecovery.active || watchdogRecovery.terminal ||
        exactInvalidationEpoch >= UINT64_MAX - 1 || gq[0].gfx || !gq[1].gfx)
        return false;
    for (uint32_t qi = 0; qi < 2; ++qi) {
        if (!gq[qi].ready || !exactQueueLive[qi] || !exactQueueGeneration[qi] ||
            exactQueueGeneration[qi] >= UINT64_MAX - 1) return false;
    }
    out = Phx34ExactOpen{exactInvalidationEpoch, {exactQueueGeneration[0], exactQueueGeneration[1]}};
    return true;
}

'''
PREFLIGHT = '''    const bool exact = type == PHX34_R3_UC_TYPE;
    if (!exact && type != PHXN_UC_TYPE) return kIOReturnBadArgument;
    Phx34ExactOpen requested{};
    if (exact) {
        if (!owningTask || IOUserClient::clientHasPrivilege(owningTask, kIOClientPrivilegeAdministrator) != kIOReturnSuccess)
            return kIOReturnNotPrivileged;
        if (!gpuLock) return kIOReturnNotReady;
        IOLockLock(gpuLock);
        const bool ready = captureExactOpenLocked(requested);
        IOLockUnlock(gpuLock);
        if (!ready) return kIOReturnNotReady;
    }
'''
PUBLISH = '''    if (exact) {
        Phx34ExactOpen current{};
        IOLockLock(gpuLock);
        const bool ready = captureExactOpenLocked(current) && requested.matches(current) &&
                           client->exactOwnership == &client->exactRegistry &&
                           client->exactRegistry.boundTo(this, client) &&
                           !client->exactClientCallbacks.closed() && !exactCallbacks.closed();
        if (ready) *handler = client;
        IOLockUnlock(gpuLock);
        if (ready) return kIOReturnSuccess;
    }
'''


def stage_header(source):
    return progress_header(close_header(source))


def stage(source):
    source = previous_stage(source)
    include = '#include "build34_exact_progress_wire.h"\n'
    source = once(source, include, include + '#include "build34_exact_open_wire.h"\n')
    service = 'class PhxBringup : public IOService {\n'
    source = once(source, service, OPEN_PROOF + service)
    fields = '    uint64_t exactInvalidationEpoch{0};\n'
    source = once(source, fields, fields + DECLARATIONS)
    client = '    bool exactRequested{false}, exactStartAttempted{false}; // no native assignment/selector\n'
    source = once(source, client, '    bool exactRequested{false}, exactStartAttempted{false};\n'
                  '    Phx34ExactOpen requestedExactOpen{};\n')
    init = method(source, INIT)
    source = once(source, init, once(init, '    task = owningTask;\n',
                  '    exactRequested = type == PHX34_R3_UC_TYPE;\n'
                  '    if (exactRequested && !privileged) return false;\n'
                  '    task = owningTask;\n'))
    bind = method(source, BIND)
    source = once(source, bind, once(bind, '    IOLockLock(gpuLock);\n    if (',
                  '    Phx34ExactOpen current{};\n    IOLockLock(gpuLock);\n'
                  '    if (!client->privileged || !captureExactOpenLocked(current) ||\n'
                  '        !client->requestedExactOpen.matches(current) || '))
    factory = method(source, FACTORY)
    updated = once(factory, '    if (type != PHXN_UC_TYPE) return kIOReturnBadArgument;\n', PREFLIGHT)
    updated = once(updated, '    if (!client->initWithTask(owningTask, securityID, type) || !client->attach(this)) {\n',
                   '    if (!client->initWithTask(owningTask, securityID, type)) {\n'
                   '        client->release();\n        return kIOReturnNoMemory;\n    }\n'
                   '    if (exact) client->requestedExactOpen = requested;\n'
                   '    if (!client->attach(this)) {\n')
    updated = once(updated, 'return exactCallbacks.closed() ? kIOReturnNotReady : kIOReturnExclusiveAccess;',
                   'return (exact || exactCallbacks.closed()) ? kIOReturnNotReady : kIOReturnExclusiveAccess;')
    updated = once(updated, '    if (exactCallbacks.closed()) {\n        // No handler escaped.',
                   PUBLISH + '    if (exact || exactCallbacks.closed()) {\n        // No handler escaped.')
    return once(source, factory, SERVICE + updated)
