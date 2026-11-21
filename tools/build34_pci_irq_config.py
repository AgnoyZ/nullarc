# SPDX-License-Identifier: MIT
"""Derive a start-time PCI IRQ observer on top of the mapping-only stage."""

from build34_map_observation import sha, stage_baseline

MAP_SHA = '9826065e11adc6ec7363459210704b685d1fc5df29758271ca674163254cd0c3'
SERVICE = 'bool PhxBringup::start(IOService *provider) {\n'
START_ANCHOR = '    PMinit();\n    provider->joinPMtree(this);\n'
START_OBSERVER = '''    removeProperty("phx-pci-irq-start-v1");
    if (const char *mode = phx_pci_irq_start_mode(*pci))
        setProperty("phx-pci-irq-start-v1", mode);
'''

OBSERVER = '''namespace {

struct PhxPciIrqSample {
    uint64_t visited;
    uint16_t headers[48];
    uint16_t pmcsr, controlMsi, controlMsix;
    uint8_t first, headerType;
};

static bool phx_pci_irq_is_780m(IOPCIDevice &pci) {
    return pci.configRead16(uint8_t{0}) == 0x1002 && pci.configRead16(uint8_t{2}) == 0x1900;
}

// Distinct, aligned header slots plus the lengths of the three parsed capabilities.
static bool phx_pci_irq_claim(uint64_t visited, uint64_t &claimed, unsigned offset, unsigned size) {
    if (offset + size > 0x100) return false;
    const unsigned slot = (offset - 0x40) / 4;
    const uint64_t region = ((uint64_t{1} << (size / 4)) - 1) << slot;
    if ((region & claimed) || (region & visited) != (uint64_t{1} << slot)) return false;
    claimed |= region;
    return true;
}

static bool phx_pci_irq_sample(IOPCIDevice &pci, PhxPciIrqSample &sample) {
    if (!phx_pci_irq_is_780m(pci)) return false;
    sample.headerType = pci.configRead8(uint8_t{0x0e});
    const uint16_t status = pci.configRead16(uint8_t{0x06});
    if ((sample.headerType & 0x7f) || status == 0xffff || !(status & 0x10)) return false;
    sample.first = pci.configRead8(uint8_t{0x34});
    unsigned pm = 0, msi = 0, msix = 0;
    unsigned offset = sample.first;
    for (unsigned i = 0; offset && i < 48; ++i) {
        if (offset < 0x40 || offset > 0xfc || offset % 4) return false;
        const unsigned slot = (offset - 0x40) / 4;
        const uint64_t bit = uint64_t{1} << slot;
        if (sample.visited & bit) return false;
        sample.visited |= bit;
        const uint16_t header = pci.configRead16(static_cast<uint8_t>(offset));
        const unsigned id = header & 0xff;
        if (!id || id == 0xff) return false;
        sample.headers[slot] = header;
        unsigned *location = id == 0x01 ? &pm : id == 0x05 ? &msi : id == 0x11 ? &msix : nullptr;
        if (location) {
            if (*location) return false;
            *location = offset;
        }
        offset = header >> 8;
    }
    if (offset || !pm) return false;
    uint64_t claimed = 0;
    if (!phx_pci_irq_claim(sample.visited, claimed, pm, 8) ||
        (msix && !phx_pci_irq_claim(sample.visited, claimed, msix, 12)) ||
        (msi && msi + 12 > 0x100)) return false;
    const auto pmcsr = static_cast<uint8_t>(pm + 4);
    sample.pmcsr = pci.configRead16(pmcsr);
    if (sample.pmcsr == 0xffff || (sample.pmcsr & 3)) return false;
    if (msi) {
        sample.controlMsi = pci.configRead16(static_cast<uint8_t>(msi + 2));
        if (sample.controlMsi == 0xffff) return false;
        const unsigned size = 12 + ((sample.controlMsi & 0x80) ? 4 : 0) +
            ((sample.controlMsi & 0x100) ? 8 : 0);
        if (!phx_pci_irq_claim(sample.visited, claimed, msi, size)) return false;
    }
    if (msix) {
        sample.controlMsix = pci.configRead16(static_cast<uint8_t>(msix + 2));
        if (sample.controlMsix == 0xffff) return false;
    }
    return pci.configRead16(pmcsr) == sample.pmcsr && phx_pci_irq_is_780m(pci);
}

static const char *phx_pci_irq_start_mode(IOPCIDevice &pci) {
    PhxPciIrqSample a{}, b{};
    if (!phx_pci_irq_sample(pci, a) || !phx_pci_irq_sample(pci, b) ||
        a.first != b.first || a.headerType != b.headerType || a.visited != b.visited ||
        a.pmcsr != b.pmcsr || a.controlMsi != b.controlMsi || a.controlMsix != b.controlMsix) return nullptr;
    for (unsigned i = 0; i < 48; ++i)
        if (a.headers[i] != b.headers[i]) return nullptr;
    const bool msi = a.controlMsi & 1, msix = a.controlMsix & 0x8000;
    if (msi && msix) return nullptr;
    if (msi) return "msi-enable-set";
    if (!msix) return "both-message-enables-clear";
    return (a.controlMsix & 0x4000) ? "msix-enable-set-function-mask-set" :
        "msix-enable-set-function-mask-clear";
}

} // namespace

'''


def stage(source):
    control = stage_baseline(source)
    if sha(control.encode()) != MAP_SHA or control.count(SERVICE) != 1 or control.count(START_ANCHOR) != 1:
        raise ValueError('Require exact accepted mapping-only build34 source')
    return control.replace(SERVICE, OBSERVER + SERVICE, 1).replace(START_ANCHOR, START_OBSERVER + START_ANCHOR, 1)
