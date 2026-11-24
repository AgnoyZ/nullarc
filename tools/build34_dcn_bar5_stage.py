"""Bind staged flip register operations to the exact native provider's BAR5."""

import build34_dcn_flip_commit_stage as flip
from build34_exact_submit import once
from test_build34_exact_ownership import method


BIND = 'bool PhxBringup::bindDcnBar5('
LIVE = 'bool PhxBringup::dcnBar5Live('
CURRENT = 'bool PhxBringup::dcnBar5Current('
READ = 'bool PhxBringup::readDcnBar5('
WRITE = 'bool PhxBringup::writeDcnBar5('
CLOCK = 'bool PhxBringup::clockDcnBar5('
DELAY = 'void PhxBringup::delayDcnBar5('
SIGNATURES = (BIND, LIVE, CURRENT, READ, WRITE, CLOCK, DELAY)

FIELDS = '''    build34::dcn::DcnBar5Window dcnBar5Window;
    struct {
        IOPCIDevice *device;
        IOMemoryMap *map;
        const IOMemoryDescriptor *resource;
        volatile uint32_t *registers;
        uint64_t physical, bytes;
    } dcnBar5{};
    bool dcnBar5Revoked{false};
    bool bindDcnBar5(const build34::dcn::ScanoutFlipIntent &, build34::dcn::HubpFlipRoute &);
    bool dcnBar5Live() const;
    bool dcnBar5Current() const;
    static bool readDcnBar5(void *, uint32_t, uint32_t &);
    static bool writeDcnBar5(void *, uint32_t, uint32_t);
    static bool clockDcnBar5(void *, uint64_t &);
    static void delayDcnBar5(void *, uint32_t);
'''

METHODS = '''bool PhxBringup::dcnBar5Live() const {
    return !exactCallbacks.closed() && exactCallbacks.active() && dcnPinOperation.active() == 1 && exactRawWriters.drained() &&
        !__atomic_load_n(&dcnBar5Revoked, __ATOMIC_ACQUIRE) && pci && mmio;
}

bool PhxBringup::dcnBar5Current() const {
    if (!dcnBar5Live() || dcnBar5.device != pci || dcnBar5.map != mmio || !dcnBar5.registers ||
        isInactive() || pci->isInactive() || getProvider() != pci) return false;
    const auto command = pci->configRead16(kIOPCIConfigCommand);
    auto *resource = pci->getDeviceMemoryWithRegister(kIOPCIConfigBaseAddress5);
    return command != UINT16_MAX && (command & 2) && pci->configRead32(kIOPCIConfigVendorID) == 0x19001002 &&
        resource && resource == dcnBar5.resource && mmio->getMemoryDescriptor() == resource && mmio->getAddressTask() == kernel_task &&
        resource->getPhysicalAddress() == dcnBar5.physical && resource->getLength() == dcnBar5.bytes &&
        mmio->getPhysicalAddress() == dcnBar5.physical && mmio->getLength() == dcnBar5.bytes &&
        reinterpret_cast<volatile uint32_t *>(mmio->getVirtualAddress()) == dcnBar5.registers && dcnBar5Live();
}

bool PhxBringup::bindDcnBar5(const build34::dcn::ScanoutFlipIntent &intent, build34::dcn::HubpFlipRoute &route) {
    using namespace build34::dcn;
    DcnBar5Window window;
    if (!dcnBar5Live() || !route.reader.current || !window.arm(intent.previous, intent.next)) return false;
    if (!dcnBar5.map) {
        auto *resource = pci->getDeviceMemoryWithRegister(kIOPCIConfigBaseAddress5);
        if (!resource) return false;
        const uint64_t address = mmio->getVirtualAddress(), bytes = mmio->getLength(), physical = resource->getPhysicalAddress();
        if (!address || address % sizeof(uint32_t) || !physical || physical % sizeof(uint32_t) ||
            bytes < dcnPeers::kMmioBytes || bytes > UINT64_MAX - address || bytes > UINT64_MAX - physical) return false;
        dcnBar5 = {pci, mmio, resource, reinterpret_cast<volatile uint32_t *>(address), physical, bytes};
        if (!dcnBar5Current()) {
            dcnBar5 = {};
            return false;
        }
    } else if (!dcnBar5Current()) {
        __atomic_store_n(&dcnBar5Revoked, true, __ATOMIC_RELEASE);
        return false;
    }
    dcnBar5Window = window;
    route.reader.apertureBytes = dcnBar5.bytes;
    route.reader.ioContext = this;
    route.reader.readDword = readDcnBar5;
    route.reader.readClockNs = clockDcnBar5;
    route.writer = {writeDcnBar5, delayDcnBar5};
    return true;
}

bool PhxBringup::readDcnBar5(void *context, uint32_t reg, uint32_t &value) {
    auto *self = static_cast<PhxBringup *>(context);
    if (!self->dcnBar5Live() || self->dcnBar5.device != self->pci || self->dcnBar5.map != self->mmio ||
        !self->dcnBar5Window.canRead(reg, self->dcnBar5.bytes) ||
        self->mmio->getLength() != self->dcnBar5.bytes ||
        self->mmio->getVirtualAddress() != reinterpret_cast<uintptr_t>(self->dcnBar5.registers)) return false;
    const auto sampled = self->dcnBar5.registers[reg];
    if (sampled == UINT32_MAX || !self->dcnBar5Live()) return false;
    value = sampled;
    return true;
}

bool PhxBringup::writeDcnBar5(void *context, uint32_t reg, uint32_t value) {
    auto *self = static_cast<PhxBringup *>(context);
    if (!self->dcnBar5Window.canWrite(reg, self->dcnBar5.bytes) || !self->dcnBar5Current()) return false;
    self->dcnBar5.registers[reg] = value;
    __asm__ __volatile__("mfence" ::: "memory");
    uint32_t posted = 0;
    return readDcnBar5(context, reg, posted) && self->dcnBar5Current();
}

bool PhxBringup::clockDcnBar5(void *context, uint64_t &value) {
    auto *self = static_cast<PhxBringup *>(context);
    if (!self->dcnBar5Live()) return false;
    absolutetime_to_nanoseconds(mach_absolute_time(), &value);
    return self->dcnBar5Live();
}

void PhxBringup::delayDcnBar5(void *context, uint32_t us) {
    if (us == 1 && static_cast<PhxBringup *>(context)->dcnBar5Live()) IODelay(1);
}

'''


def stage_native(driver, abi):
    source = flip.stage_native(driver, abi)
    include = '#include "build34_dcn_flip_commit.h"\n'
    source = once(source, include, include + '#include "build34_dcn_bar5.h"\n')
    source = once(source, flip.FIELDS, flip.FIELDS + FIELDS)
    source = once(source, flip.METHODS, METHODS + flip.METHODS)

    def replace(signature, old, new):
        nonlocal source
        before = method(source, signature)
        source = once(source, before, once(before, old, new))

    replace(flip.BEGIN, '    const auto result = dcnFlip.begin(intent, token, *route,',
            '    auto boundRoute = *route;\n'
            '    if (!bindDcnBar5(intent, boundRoute)) return kIOReturnNotReady;\n'
            '    const auto result = dcnFlip.begin(intent, token, boundRoute,')
    replace(flip.POLL, '    const auto result = dcnFlip.poll(poll.operation, [&] { return !exactCallbacks.closed(); }, route, framebuffer);',
            '    const bool barLive = dcnBar5Current();\n'
            '    if (!barLive) __atomic_store_n(&dcnBar5Revoked, true, __ATOMIC_RELEASE);\n'
            '    const auto result = dcnFlip.poll(poll.operation, [&] { return barLive && dcnBar5Live(); }, route, framebuffer);')
    replace('IOReturn PhxBringup::setPowerState(', '    if (ordinal == 0) {\n',
            '    if (ordinal == 0) {\n'
            '        __atomic_store_n(&dcnBar5Revoked, true, __ATOMIC_RELEASE);\n')
    return source
