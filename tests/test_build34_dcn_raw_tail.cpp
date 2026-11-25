#include <cassert>
#include <cstddef>
#include <cstdint>

#include "build34_exact_callbacks.h"

struct Aperture {
    uint32_t words[2048]{};
    size_t bytes = sizeof(words);
    uint64_t getLength() const { return bytes; }
    uintptr_t getVirtualAddress() const { return reinterpret_cast<uintptr_t>(words); }
};

struct PhxBringup {
    phx34_exact::CallbackGate<> exactCallbacks;
    phx34_exact::CallbackGate<1> exactRawWriters;
    Aperture storage;
    Aperture *fbAper = &storage;
    uint64_t fbAperLen = sizeof(storage.words), fbMcBase = 0x800000000ull, gSeq = 0;
    bool exactStopped = false, isSleeping = false, exactVMFault = false;
    bool (*exactDwordReader)(const volatile uint32_t *, uint32_t *) = nullptr;
#include "raw-tail-decl.inc"
};

#include "raw-tail-method.inc"

static PhxBringup *provider = nullptr;
static unsigned reads = 0, pairs = 0, failAfter = 0, failPairAfter = 0, driftPairAfter = 0, closeAfter = 0;
static constexpr uint64_t ring = 0x100, ringDw = 256, wptr = 16, wb = 0x800, fence = 0x1000;

static bool sample(const volatile uint32_t *address, uint32_t *word) {
    assert(address >= provider->storage.words && address < provider->storage.words + 2048);
    ++reads;
    if (reads == failAfter) return false;
    if (reads == closeAfter) provider->exactCallbacks.close();
    *word = *address;
    return true;
}

// The paired sampler: both cookie dwords from one snapshot. driftPairAfter tears the
// snapshot between the two loads, which two independent raw reads could never detect.
static bool samplePair(const PhxBringup &device, uint64_t offset, uint32_t (&pair)[2]) {
    assert(&device == provider && !(offset & 3));
    ++pairs;
    if (pairs == failPairAfter) return false;
    pair[0] = device.storage.words[offset / 4];
    if (pairs == driftPairAfter) provider->storage.words[offset / 4 + 1] ^= 1;
    pair[1] = device.storage.words[offset / 4 + 1];
    return true;
}

static PhxBringup::DcnCoherentFenceAccess const coherent = {samplePair};

int main() {
    PhxBringup device;
    provider = &device;
    const auto check = [&] { return device.dcnRawTailMatchesLocked(ring, ringDw, wb, wptr, fence); };
    assert(!check() && !reads && !pairs);
    {
        phx34_exact::CallbackGate<1>::Lease raw(device.exactRawWriters);
        assert(raw && device.exactRawWriters.close());
        device.exactDwordReader = sample;
        assert(!check() && !reads && !pairs);
        device.dcnCoherentFence = &coherent;
    }
    auto *tail = device.storage.words + ring / 4 + wptr - 8;
    const uint32_t release[8] = {0xc0064900u, 0x06603514u, 0x40000000u, static_cast<uint32_t>(fence), 8, 0x1235, 0x80002345, 0};
    for (unsigned index = 0; index < 8; ++index) tail[index] = release[index];
    auto *last = device.storage.words + fence / 4;
    last[0] = tail[5]; last[1] = tail[6];
    device.storage.words[wb / 4 + 4] = wptr;
    assert(check() && reads == 12 && pairs == 2);
    for (unsigned index = 0; index < 8; ++index) {
        tail[index] ^= 1;
        assert(!check());
        tail[index] ^= 1;
    }
    device.storage.words[wb / 4 + 5] = 1;
    assert(!check());
    device.storage.words[wb / 4 + 5] = 0;
    device.storage.bytes = fence + 4;
    assert(!check());
    device.storage.bytes = device.fbAperLen;
    assert(!device.dcnRawTailMatchesLocked(ring, ringDw, wb, ringDw, fence));
    assert(!device.dcnRawTailMatchesLocked(ring, ringDw, wb, wptr - 8, fence));
    assert(!device.dcnRawTailMatchesLocked(ring, ringDw, wb, wptr, fence + 2));
    device.gSeq = (uint64_t(last[1]) << 32) | last[0];
    assert(!check());
    device.gSeq = 0;
    failPairAfter = pairs + 1;
    assert(!check());
    failPairAfter = 0;
    last[0] ^= 1;
    assert(!check());
    last[0] = tail[5];
    driftPairAfter = pairs + 1;
    assert(!check());
    driftPairAfter = 0;
    last[1] = tail[6];
    failAfter = reads + 6;
    assert(!check());
    failAfter = 0;
    reads = 0;
    closeAfter = 2;
    assert(!check());
}
