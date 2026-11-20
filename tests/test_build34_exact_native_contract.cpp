// SPDX-License-Identifier: MIT
// Actual legacy kernel methods, CPU aperture/fence/lock doubles only.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include "PhxNativeABI.h"

static unsigned checks;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"check failed at %d: %s\n",__LINE__,#x); std::abort(); } } while (0)
using IOReturn = int;
enum { kIOReturnSuccess, kIOReturnNotReady, kIOReturnBadArgument };
static bool held;
static void IOLockLock(void *) { CHECK(!held); held = true; }
static void IOLockUnlock(void *) { CHECK(held); held = false; }
static uint64_t mach_absolute_time() { return 0; }
static void absolutetime_to_nanoseconds(uint64_t ticks, uint64_t *ns) { *ns = ticks; }
static void IODelay(unsigned) { CHECK(false); }
static void IOSleep(unsigned) { CHECK(false); }
static void IOLog(const char *, ...) {}
struct Memory {
    alignas(16) uint64_t data[2048]{};
    uintptr_t getVirtualAddress() const { return reinterpret_cast<uintptr_t>(data); }
    size_t getLength() const { return sizeof data; }
};
struct PhxBringup {
    struct GpuQueue {
        bool ready, gfx;
        uint32_t ringOff, ringDw, wbOff, fenceOff;
        uint64_t dbByte, wptr, doneEnd;
        uint64_t fseq[64], fend[64];
        uint32_t fvmid[64];
        volatile uint32_t head, tail;
        uint64_t lastDone, lastProgress, killedSeq;
        bool killedAll;
    };
    GpuQueue gq[2]{};
    uint64_t gSeq = 20, fbMcBase = 0x100000000ull, fbAperLen = 0;
    Memory memory, doorbells;
    Memory *fbAper = &memory, *doorbellMap = &doorbells;
    void *mmio = this, *gpuLock = this;
    PhxBringup() {
        fbAperLen = memory.getLength();
        for (unsigned i = 0; i < 2; ++i) {
            auto &q = gq[i];
            q.ready = true; q.gfx = i == 1; q.ringDw = 1024;
            q.fenceOff = 12000 + 8 * i; q.tail = 1;
            q.fseq[0] = i ? 20 : 10;
            setFence(i, i ? 20 : 9);
        }
    }
    bool gpuReady() const { return gq[0].ready || gq[1].ready; }
    void hdpFlush() { CHECK(held); }
    void setFence(unsigned index, uint64_t value) {
        std::memcpy(reinterpret_cast<uint8_t *>(memory.data)+gq[index].fenceOff,&value,8);
    }
    uint64_t queueFence(const GpuQueue &) const;
    uint64_t gpuRetired() const;
    IOReturn adoptQueue(const uint64_t[6]);
};
struct IOExternalMethodArguments {
    uint64_t scalarInput[3]{}, scalarOutput[3]{};
};
static bool shape(IOExternalMethodArguments *, unsigned i, unsigned o, unsigned si, unsigned so) {
    CHECK(i==3 && o==3 && !si && !so); return true;
}
struct IOAccelPhxNativeClient {
    struct Bo { uint8_t *kva; uint64_t size; };
    bool hello = true;
    void *lock = this;
    PhxBringup *owner;
    uint64_t emitted = 20, pendFenceSeq = 0;
    uint32_t pendFenceHandle = 0, pendFenceOffset = 0;
    explicit IOAccelPhxNativeClient(PhxBringup *device) : owner(device) {}
    void flushBos() { CHECK(held); }
    Bo *findBo(uint32_t) { CHECK(false); return nullptr; }
    IOReturn doWaitSeq(IOExternalMethodArguments *);
};

// PHX34_EXTRACTED_NATIVE_CONTRACT_METHODS

int main() {
    PhxBringup device;
    IOAccelPhxNativeClient client(&device);
    CHECK(device.gpuRetired()==9);
    // A future exact backend cannot inherit this legacy ownership test: target
    // 15 was never submitted by this fixture's client (which emitted 20).
    device.setFence(0,20);
    IOExternalMethodArguments a;
    a.scalarInput[0]=15;
    CHECK(client.doWaitSeq(&a)==kIOReturnSuccess);
    CHECK(a.scalarOutput[0]==0 && a.scalarOutput[1]==20);
    device.setFence(0,9);
    CHECK(device.gpuRetired()==9);
    // Actual boot/adoption behavior seeds a new fence with gSeq and clears old
    // history. No GPU work runs here, and this is not a live readoption test.
    const uint64_t in[6]={0,1024,8192,0,0,12000};
    CHECK(device.adoptQueue(in)==kIOReturnSuccess);
    CHECK(device.gq[0].head==device.gq[0].tail && device.queueFence(device.gq[0])==20);
    CHECK(device.gpuRetired()==20);
    CHECK(!held);
    std::puts("PASS actual legacy native contract: upper bound is not ownership; readoption seeds fence and clears history; GPU_executed=false");
}
