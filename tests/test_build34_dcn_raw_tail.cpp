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
static unsigned reads = 0, failAfter = 0, driftAfter = 0, closeAfter = 0;
static constexpr uint64_t ring = 0x100, ringDw = 256, wptr = 16, wb = 0x800, fence = 0x1000;

static bool sample(const volatile uint32_t *address, uint32_t *word) {
    assert(address >= provider->storage.words && address < provider->storage.words + 2048);
    ++reads;
    if (reads == failAfter) return false;
    if (reads == driftAfter) provider->storage.words[fence / 4 + 1] ^= 1;
    if (reads == closeAfter) provider->exactCallbacks.close();
    *word = *address;
    return true;
}

int main() {
    PhxBringup device;
    provider = &device;
    const auto check = [&] { return device.dcnRawTailMatchesLocked(ring, ringDw, wb, wptr, fence); };
    assert(!check() && !reads);
    {
        phx34_exact::CallbackGate<1>::Lease raw(device.exactRawWriters);
        assert(raw && device.exactRawWriters.close());
        device.exactDwordReader = sample;
        assert(!check() && !reads);
    }
    auto *tail = device.storage.words + ring / 4 + wptr - 8;
    const uint32_t release[8] = {0xc0064900u, 0x06603514u, 0x40000000u, static_cast<uint32_t>(fence), 8, 0x1235, 0x80002345, 0};
    for (unsigned index = 0; index < 8; ++index) tail[index] = release[index];
    auto *last = device.storage.words + fence / 4;
    last[0] = tail[5]; last[1] = tail[6];
    device.storage.words[wb / 4 + 4] = wptr;
    assert(check() && reads == 16);
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
    device.gSeq = (uint64_t(last[1]) << 32) | last[0];
    assert(!check());
    device.gSeq = 0;
    failAfter = reads + 6;
    assert(!check());
    driftAfter = reads + 15;
    assert(!check());
    last[1] = tail[6];
    closeAfter = reads + 16;
    assert(!check());
}
