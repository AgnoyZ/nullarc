// SPDX-License-Identifier: MIT
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr, "failed line %d\n", __LINE__); std::exit(86); } } while (false)

struct IOPCIDevice {
    std::array<uint8_t, 256> data{};
    std::array<unsigned, 256> reads{};
    unsigned total{0};
    int changingOffset{-1};
    unsigned changeOnRead{2};
    uint16_t replacement{0};

    void word(unsigned offset, uint16_t value) {
        data.at(offset) = value & 0xff;
        data.at(offset + 1) = value >> 8;
    }

    uint16_t read(uint8_t offset, bool wide) {
        CHECK(++total <= 118);
        CHECK(wide ? (offset == 0 || offset == 2 || offset == 6 ||
              (offset >= 0x40 && offset <= 0xfe && offset % 2 == 0)) : (offset == 0x0e || offset == 0x34));
        unsigned n = ++reads[offset];
        if (offset == changingOffset && n >= changeOnRead) return replacement;
        return wide ? data[offset] | (data[offset + 1] << 8) : data[offset];
    }

    uint8_t configRead8(uint8_t offset) { return read(offset, false); }
    uint16_t configRead16(uint8_t offset) { return read(offset, true); }
};

// PHX34_PCI_OBSERVER

struct Service {
    IOPCIDevice *pci;
    const char *property = "stale";
    bool failPublish = false;
    void removeProperty(const char *key) {
        CHECK(std::strcmp(key, "phx-pci-irq-start-v1") == 0);
        property = nullptr;
    }
    bool setProperty(const char *key, const char *value) {
        CHECK(std::strcmp(key, "phx-pci-irq-start-v1") == 0 && !property);
        if (failPublish) return false;
        property = value;
        return true;
    }
    void observe() {
        // PHX34_PCI_START_OBSERVER
    }
};

static IOPCIDevice device(uint16_t msi = 0, uint16_t msix = 0) {
    IOPCIDevice pci;
    pci.word(0, 0x1002);
    pci.word(2, 0x1900);
    pci.word(6, 0x10);
    pci.data[0x34] = 0x40;
    pci.word(0x40, 0x5001);
    pci.word(0x50, 0x7005);
    pci.word(0x52, msi);
    pci.word(0x70, 0x0011);
    pci.word(0x72, msix);
    return pci;
}

static void expect(IOPCIDevice pci, const char *expected, bool failPublish = false) {
    Service service{&pci};
    service.failPublish = failPublish;
    service.observe();
    CHECK(expected ? service.property && std::strcmp(service.property, expected) == 0 : !service.property);
}

int main() {
    expect(device(), "both-message-enables-clear");
    expect(device(0x181, 0x4000), "msi-enable-set");
    expect(device(0, 0x8001), "msix-enable-set-function-mask-clear");
    expect(device(0, 0xc001), "msix-enable-set-function-mask-set");
    expect(device(1, 0x8000), nullptr);
    expect(device(1), nullptr, true);
    auto pci = device();
    pci.word(0x40, 0x0001);
    expect(pci, "both-message-enables-clear"); // absent capabilities do not imply INTx
    pci.data[0x0e] = 0x80;
    expect(pci, "both-message-enables-clear");
    pci = device(1);
    pci.data[0x34] = 0x70;
    pci.word(0x70, 0x4011);
    pci.word(0x50, 0x0005);
    expect(pci, "msi-enable-set"); // linked list is not required to be sorted
    pci = device();
    pci.word(0x40, 0xf401);
    pci.word(0xf4, 0x11);
    pci.word(0xf6, 0xc000);
    expect(pci, "msix-enable-set-function-mask-set");

    for (const auto value : {0x00, 0x3c, 0x41, 0xff}) {
        pci = device();
        pci.data[0x34] = value;
        expect(pci, nullptr);
    }
    for (const auto header : {0x4001, 0x5001, 0x4201, 0x3c01, 0xff01, 0x0000, 0x00ff}) {
        pci = device();
        pci.word(0x50, header);
        expect(pci, nullptr);
    }
    for (const auto word : {0x5005, 0x5011, 0x0003}) {
        pci = device();
        pci.word(0x40, word);
        expect(pci, nullptr);
    }
    for (const auto offset : {0, 2, 6, 0x44, 0x52, 0x72}) {
        pci = device();
        pci.word(offset, 0xffff);
        expect(pci, nullptr);
    }
    pci = device();
    pci.word(6, 0);
    expect(pci, nullptr);
    pci = device();
    pci.data[0x0e] = 1;
    expect(pci, nullptr);
    for (uint16_t state = 1; state <= 3; ++state) {
        pci = device(1);
        pci.word(0x44, state);
        Service blocked{&pci};
        blocked.observe();
        CHECK(!blocked.property && !pci.reads[0x52] && !pci.reads[0x72]);
    }

    pci = device(1);
    pci.word(0x40, 0xfc01);
    pci.word(0xfc, 5);
    expect(pci, nullptr); // control fits, capability does not
    pci = device();
    pci.word(0x40, 0xf801);
    pci.word(0xf8, 0x11);
    expect(pci, nullptr);
    pci = device();
    pci.data[0x34] = 0xfc;
    pci.word(0xfc, 1);
    expect(pci, nullptr); // no wrapped PMCSR access
    pci = device(1);
    pci.word(0x40, 0x4401);
    pci.word(0x44, 0x5003);
    expect(pci, nullptr); // another header aliases PMCSR
    pci = device(0x181);
    pci.word(0x40, 0x6001);
    pci.word(0x60, 0x5011);
    pci.word(0x50, 0x0005);
    expect(pci, nullptr); // dynamic MSI payload overlaps another capability

    for (const auto offset : {0, 0x0e, 0x34, 0x44, 0x52, 0x72}) {
        pci = device(1);
        pci.changingOffset = offset;
        pci.replacement = offset == 0x52 ? 0 : offset == 0x72 ? 0x4000 : 0xff;
        expect(pci, nullptr);
    }
    pci = device(1);
    pci.changingOffset = 0x44;
    pci.changeOnRead = 3;
    pci.replacement = 0x100;
    expect(pci, nullptr); // two stable D0 samples but changed PMCSR
    pci = device(1);
    pci.word(0x70, 0x9003);
    pci.word(0x90, 0x0004);
    pci.changingOffset = 0x90;
    pci.replacement = 0x0006;
    expect(pci, nullptr); // changed unused header, identical mode bits

    pci = device();
    for (unsigned offset = 0x40; offset <= 0xfc; offset += 4)
        pci.word(offset, (static_cast<uint8_t>(offset + 4) << 8) | 0x03);
    expect(pci, nullptr); // bounded valid-address walk without PM
    std::printf("PASS %u PCI IRQ configuration checks\n", checks);
}
