// Synthetic panel bytes and fake IOKit only. Never a physical EDID or GPU test.
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <string>
#include <vector>
#include "PhxEDID.hpp"

using IOIndex = uint32_t;
using UInt32 = uint32_t;
using UInt8 = uint8_t;
using IOSelect = uint32_t;
using IOOptionBits = uint32_t;
using IOByteCount = uint64_t;
using IOReturn = int;
enum { kIOReturnSuccess, kIOReturnBadArgument, kIOReturnUnsupported };
enum { kIODDCBlockTypeEDID = 1, kConnectionSupportsHLDDCSense = 20, kConnectionSupportsLLDDCSense,
       kConnectionSupportsAppleSense, kConnectionEnable, kConnectionCheckEnable, kConnectionFlags,
       kConnectionColorModesSupported, kConnectionColorMode, kConnectionColorDepthsSupported,
       kConnectionControllerColorDepth, kConnectionControllerDepthsSupported, kIOConnectionBuiltIn = 128 };
struct OSObject {
    unsigned references = 1;
    virtual ~OSObject() = default;
    void retain() { ++references; }
    void release() { assert(references > 1); --references; }
};
struct OSData : OSObject {
    std::vector<uint8_t> bytes;
    explicit OSData(std::vector<uint8_t> b) : bytes(std::move(b)) {}
    const void *getBytesNoCopy() { return bytes.data(); }
    unsigned getLength() { return (unsigned)bytes.size(); }
};
struct OSBoolean { bool value; };
static OSBoolean yes{true}, no{false};
static const OSBoolean *kOSBooleanTrue = &yes, *kOSBooleanFalse = &no;
#define OSDynamicCast(type, value) dynamic_cast<type *>(value)
#define PFBLOG(...) ((void)0)

struct FakePCI {
    std::map<std::string, OSObject *> properties;
    std::vector<std::string> queries;
    OSObject *copyProperty(const char *key) {
        queries.emplace_back(key);
        const auto it = properties.find(key);
        if (it == properties.end()) return nullptr;
        it->second->retain(); return it->second;
    }
};
struct IOFramebuffer {
    std::map<std::string, std::string> strings;
    std::map<std::string, uint64_t> numbers;
    std::vector<uint8_t> published;
    bool failPublication = false;
    bool setProperty(const char *key, const char *value) { strings[key] = value; return true; }
    bool setProperty(const char *key, unsigned long long value, unsigned) { numbers[key] = value; return true; }
    bool setProperty(const char *key, const OSBoolean *value) { numbers[key] = value->value; return true; }
    bool setProperty(const char *key, const void *data, unsigned size) {
        assert(std::string(key) == "IODisplayEDID");
        if (failPublication) return false;
        const auto *p = static_cast<const uint8_t *>(data);
        published.assign(p, p + size); return true;
    }
    IOReturn getAttributeForConnection(IOIndex, IOSelect, uintptr_t *) { return kIOReturnUnsupported; }
};
class PhxAMDFB : public IOFramebuffer {
public:
    FakePCI *fPCI;
    uint32_t fWidth = 2560, fHeight = 1600;
    bool fStopping = false;
    phx::EdidCache fEdid;
    explicit PhxAMDFB(FakePCI &pci) : fPCI(&pci) {}
    // ACTUAL_EDID_METHODS
};

static unsigned cases;
static void checksum(std::vector<uint8_t> &b, size_t block = 0) {
    const size_t off = block * 128;
    unsigned sum = 0;
    for (size_t i = 0; i < 127; ++i) sum += b[off + i];
    b[off + 127] = (uint8_t)(0u - sum);
}
static std::vector<uint8_t> panel(unsigned blocks = 1, unsigned w = 2560, unsigned h = 1600) {
    std::vector<uint8_t> p(blocks * 128, 0);
    const uint8_t hdr[] = {0, 255, 255, 255, 255, 255, 255, 0};
    std::copy(hdr, hdr + 8, p.begin());
    p[8] = 0x12; p[9] = 0x34; p[10] = 0x78; p[11] = 0x56; // synthetic identity
    p[18] = 1; p[19] = 4; p[54] = 1;
    p[56] = (uint8_t)w; p[58] = (uint8_t)((w >> 8) << 4);
    p[59] = (uint8_t)h; p[61] = (uint8_t)((h >> 8) << 4);
    p[126] = (uint8_t)(blocks - 1);
    checksum(p);
    for (unsigned b = 1; b < blocks; ++b) { p[b * 128] = 2; p[b * 128 + 1] = (uint8_t)b; checksum(p, b); }
    return p;
}
static void invalidCache(const std::vector<uint8_t> &bad) {
    phx::EdidCache cache;
    const auto good = panel();
    assert(cache.adopt(good.data(), good.size(), 2560, 1600));
    assert(!cache.adopt(bad.data(), bad.size(), 2560, 1600));
    std::array<uint8_t, 128> out; out.fill(0xa5); const auto before = out;
    assert(!cache.ready() && cache.size() == 0 && !cache.copyBlock(1, out.data(), out.size()) && out == before);
    ++cases;
}
static void refusedRead(PhxAMDFB &fb, IOIndex idx, uint32_t block, IOSelect type,
                        IOOptionBits options, IOByteCount size, IOReturn expected) {
    std::array<uint8_t, 258> out; out.fill(0xa5); const auto before = out;
    IOByteCount length = size;
    assert(fb.getDDCBlock(idx, block, type, options, out.data() + 1, &length) == expected);
    assert(out == before && length == size);
    ++cases;
}

int main() {
    const auto good = panel();
    // Full cache policy: null, short/overlong, all checksum/header bytes and count/version/geometry refusal.
    phx::EdidCache cache;
    assert(!cache.adopt(nullptr, 128, 2560, 1600)); ++cases;
    for (size_t n : {size_t(0), size_t(1), size_t(7), size_t(127), size_t(129), size_t(4097)})
        invalidCache(std::vector<uint8_t>(n, 0));
    for (size_t byte = 0; byte < 128; ++byte) { auto bad = good; bad[byte] ^= 1; invalidCache(bad); }
    for (unsigned blocks : {2u, 4u, 32u}) {
        const auto p = panel(blocks);
        assert(cache.adopt(p.data(), p.size(), 2560, 1600));
        for (unsigned b = 1; b <= blocks; ++b) {
            std::array<uint8_t, 130> out; out.fill(0xa5);
            assert(cache.copyBlock(b, out.data() + 1, 128));
            assert(out.front() == 0xa5 && out.back() == 0xa5);
            assert(std::equal(out.begin() + 1, out.begin() + 129, p.begin() + (b - 1) * 128)); ++cases;
        }
        auto bad = p; bad[129] ^= 1; invalidCache(bad);
    }
    for (unsigned version : {0u, 2u}) { auto p = good; p[18] = (uint8_t)version; checksum(p); invalidCache(p); }
    { auto p = good; p[19] = 5; checksum(p); invalidCache(p); }
    { auto p = good; p[126] = 1; checksum(p); invalidCache(p); }
    { auto p = good; p[71] |= 0x80; checksum(p); invalidCache(p); }
    invalidCache(panel(1, 1920, 1080));
    invalidCache(panel(33));
    assert(!cache.adopt(good.data(), good.size(), 0, 1600)); ++cases;
    assert(!cache.adopt(good.data(), good.size(), 2560, 0)); ++cases;
    // A match in a later base DTD is accepted; descriptor-only blocks are not timings.
    { auto p = good; std::copy(p.begin() + 54, p.begin() + 72, p.begin() + 108);
      std::fill(p.begin() + 54, p.begin() + 72, 0); checksum(p);
      assert(cache.adopt(p.data(), p.size(), 2560, 1600)); ++cases; }

    FakePCI pci;
    PhxAMDFB fb(pci);
    fb.loadEdid();
    assert(!fb.hasDDCConnect(0) && !fb.hasDDCConnect(1));
    assert(fb.strings["PhxFBEDIDStatus"] == "missing" && fb.strings["PhxFBEDIDSource"] == "none"); ++cases;
    refusedRead(fb, 0, 1, kIODDCBlockTypeEDID, 0, 128, kIOReturnUnsupported);
    uintptr_t value = 0xdead;
    assert(fb.getAttributeForConnection(0, kConnectionSupportsHLDDCSense, &value) == kIOReturnUnsupported && value == 0); ++cases;

    OSData data(panel(2)), other(good);
    pci.properties["phx-edid"] = &data;
    pci.properties["AAPL00,override-no-connect"] = &other;
    pci.properties["IODisplayEDID"] = &other;
    pci.queries.clear(); fb.loadEdid();
    assert(pci.queries == std::vector<std::string>{"phx-edid"});
    assert(data.references == 1 && other.references == 1);
    assert(fb.fEdid.ready() && fb.published == data.bytes && fb.hasDDCConnect(0) && !fb.hasDDCConnect(1));
    assert(fb.numbers["PhxFBEDIDValid"] == 1 && fb.numbers["PhxFBEDIDBytes"] == 256);
    assert(fb.strings["PhxFBEDIDSource"] == "phx-edid" && fb.strings["PhxFBEDIDStatus"] == "valid"); ++cases;
    assert(fb.getAttributeForConnection(0, kConnectionSupportsHLDDCSense, &value) == kIOReturnSuccess && value == 1); ++cases;
    for (IOSelect attr : {kConnectionSupportsLLDDCSense, kConnectionSupportsAppleSense}) {
        value = 0xdead;
        assert(fb.getAttributeForConnection(0, attr, &value) == kIOReturnUnsupported && value == 0); ++cases;
    }
    for (IOSelect attr : {kConnectionEnable, kConnectionCheckEnable, kConnectionFlags, kConnectionColorModesSupported,
                         kConnectionColorMode, kConnectionColorDepthsSupported, kConnectionControllerColorDepth,
                         kConnectionControllerDepthsSupported}) {
        assert(fb.getAttributeForConnection(0, attr, &value) == kIOReturnSuccess); ++cases;
    }
    assert(fb.getAttributeForConnection(1, kConnectionSupportsHLDDCSense, &value) == kIOReturnBadArgument); ++cases;
    assert(fb.getAttributeForConnection(0, kConnectionSupportsHLDDCSense, nullptr) == kIOReturnBadArgument); ++cases;
    assert(fb.getAttributeForConnection(0, 0xffffffffu, &value) == kIOReturnUnsupported); ++cases;
    const auto snapshot = data.bytes;
    std::fill(data.bytes.begin(), data.bytes.end(), 0); // source released/changed; cached snapshot must remain exact
    for (uint32_t block : {1u, 2u}) {
        std::array<uint8_t, 258> out; out.fill(0xa5); IOByteCount length = 256;
        assert(fb.getDDCBlock(0, block, kIODDCBlockTypeEDID, 0, out.data() + 1, &length) == kIOReturnSuccess);
        assert(length == 128 && std::equal(out.begin() + 1, out.begin() + 129, snapshot.begin() + (block - 1) * 128));
        assert(out[0] == 0xa5 && out[129] == 0xa5 && out.back() == 0xa5); ++cases;
    }
    for (uint32_t block : {0u, 3u, 0xffffffffu}) refusedRead(fb, 0, block, kIODDCBlockTypeEDID, 0, 128, kIOReturnBadArgument);
    for (IOByteCount length : {0u, 1u, 127u}) refusedRead(fb, 0, 1, kIODDCBlockTypeEDID, 0, length, kIOReturnBadArgument);
    refusedRead(fb, 1, 1, kIODDCBlockTypeEDID, 0, 128, kIOReturnBadArgument);
    refusedRead(fb, 0, 1, 2, 0, 128, kIOReturnUnsupported);
    refusedRead(fb, 0, 1, kIODDCBlockTypeEDID, 1, 128, kIOReturnUnsupported);
    IOByteCount length = 128; uint8_t output[128] = {};
    assert(fb.getDDCBlock(0, 1, kIODDCBlockTypeEDID, 0, nullptr, &length) == kIOReturnBadArgument && length == 128); ++cases;
    assert(fb.getDDCBlock(0, 1, kIODDCBlockTypeEDID, 0, output, nullptr) == kIOReturnBadArgument); ++cases;
    fb.fStopping = true;
    assert(!fb.hasDDCConnect(0)); ++cases;
    refusedRead(fb, 0, 1, kIODDCBlockTypeEDID, 0, 128, kIOReturnUnsupported);
    assert(fb.getAttributeForConnection(0, kConnectionSupportsHLDDCSense, &value) == kIOReturnUnsupported && value == 0); ++cases;

    for (const char *key : {"AAPL00,override-no-connect", "IODisplayEDID"}) {
        FakePCI provider; provider.properties[key] = &other; PhxAMDFB f(provider); f.loadEdid();
        assert(f.hasDDCConnect(0) && f.strings["PhxFBEDIDSource"] == key && other.references == 1); ++cases;
    }
    // A malformed or wrong-type explicit property is authoritative failure, not silent fallback to another monitor.
    OSObject wrongType;
    OSData badData(std::vector<uint8_t>(128, 0));
    for (OSObject *bad : {&wrongType, static_cast<OSObject *>(&badData)}) {
        FakePCI provider; provider.properties["phx-edid"] = bad; provider.properties["IODisplayEDID"] = &other;
        PhxAMDFB f(provider); f.loadEdid();
        assert(!f.hasDDCConnect(0) && f.published.empty() && f.strings["PhxFBEDIDStatus"] == "invalid");
        assert(provider.queries == std::vector<std::string>{"phx-edid"} && bad->references == 1); ++cases;
    }
    { FakePCI provider; provider.properties["phx-edid"] = &other; PhxAMDFB f(provider);
      f.failPublication = true; f.loadEdid();
      assert(!f.hasDDCConnect(0) && f.strings["PhxFBEDIDStatus"] == "publish-failed" && other.references == 1); ++cases; }
    std::printf("{\"edid_cases\":%u,\"hardware_executed\":false,\"kernel_loaded\":false}\n", cases);
}
