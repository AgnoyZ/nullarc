/* SPDX-License-Identifier: MIT */
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>
#include <vector>
#include "PhxNativeABI.h"
#include "build34_exact_callbacks.h"
#include "build34_exact_fence32.h"

static unsigned checks;
#define CHECK(expr) do { ++checks; if (!(expr)) { std::fprintf(stderr, "failed %d: %s\n", __LINE__, #expr); std::_Exit(86); } } while (0)
using IOReturn = int;
enum : IOReturn { kIOReturnSuccess, kIOReturnNotReady, kIOReturnBusy, kIOReturnBadArgument,
                  kIOReturnNoResources, kIOReturnExclusiveAccess, kIOReturnTimeout, kIOReturnInternalError,
                  kIOReturnNotPermitted };
using IOLock = std::mutex;
static void IOLockLock(IOLock *l) { l->lock(); }
static void IOLockUnlock(IOLock *l) { l->unlock(); }
static void IODelay(unsigned) {}
static void IOLog(const char *, ...) {}
static uint64_t mach_absolute_time() { return 100; }

struct Pause {
    std::mutex mutex;
    std::condition_variable cv;
    bool waiting = false, resume = false;
    void arrive() {
        std::unique_lock<std::mutex> lock(mutex);
        waiting = true;
        cv.notify_all();
        if (!cv.wait_for(lock, std::chrono::seconds(5), [&] { return resume; })) std::abort();
    }
    void wait() {
        std::unique_lock<std::mutex> lock(mutex);
        CHECK(cv.wait_for(lock, std::chrono::seconds(5), [&] { return waiting; }));
    }
    void release() {
        std::lock_guard<std::mutex> lock(mutex);
        resume = true;
        cv.notify_all();
    }
};
static thread_local Pause *firstPoll;
static void IOSleep(unsigned) {
    if (firstPoll) { auto *pause = firstPoll; firstPoll = nullptr; pause->arrive(); }
}

struct Map {
    std::vector<uint32_t> words;
    explicit Map(size_t bytes) : words(bytes / 4) {}
    uint32_t &at(uint64_t offset) { return words.at(offset / 4); }
    uintptr_t getVirtualAddress() { return reinterpret_cast<uintptr_t>(words.data()); }
    uint64_t getLength() const { return words.size() * 4; }
};

// PHX34_FRAME
struct PhxBringup {
    // PHX34_FIELDS
    // PHX34_QUEUE
    bool exactStopped = false, isSleeping = false, exactVMFault = false;
    bool exactQueueLive[2]{};
    uint64_t exactQueueGeneration[2]{}, exactQueueSubmitted[2]{}, gSeq = 100;
    phx34_exact::FenceWindow32 exactFenceWindow[2];
    Map aperture{0x40000}, doorbells{0x100}, registers{16};
    Map *fbAper = &aperture, *doorbellMap = &doorbells, *mmio = &registers;
    uint64_t fbAperLen = 0x10000000, fbMcBase = 0x100000000;
    IOLock gpu, smu;
    IOLock *gpuLock = &gpu, *smuLock = &smu;
    uint64_t ringMc = 0, ringOff = 0, cmdOff = 0, cmdMc = 0, fenceOff = 0, fenceMc = 0;
    uint64_t tmrOff = 0, tmrMc = 0, tmrSize = 0, fwBufOff = 0, fwBufMc = 0, fwBufSize = 0;
    uint32_t fenceCounter = 0;
    bool tmrSetUp = false;
    mutable uint32_t ctrl = PHX_MBOX_TOS_READY, pointer = 0;
    mutable unsigned controlWrites = 0, commandWrites = 0;
    bool ackControl = false, ackCommand = false;
    uint32_t commandStatus = 0;
    bool gpuReady() const { return __atomic_load_n(&exactConfiguredQueues, __ATOMIC_ACQUIRE); }
    uint32_t rreg(uint32_t reg) const {
        return reg == PHX_PSP_C2PMSG_64 ? ctrl : reg == PHX_PSP_C2PMSG_67 ? pointer : 0;
    }
    void wreg(uint32_t reg, uint32_t value) const {
        if (reg == PHX_PSP_C2PMSG_64) {
            ++controlWrites;
            ctrl = ackControl ? PHX_MBOX_TOS_READY : 0;
        } else if (reg == PHX_PSP_C2PMSG_67) {
            pointer = value;
            if (!value) return; // initial producer pointer, not a command in these tests
            ++commandWrites;
            if (ackCommand) {
                fbAper->at(cmdOff + PHX_PSP_GFX_RESP_OFFSET) = commandStatus;
                fbAper->at(cmdOff + PHX_PSP_GFX_RESP_OFFSET + 8) = 9;
                fbAper->at(fenceOff) = fenceCounter;
            }
        }
    }
    void hdpFlush() const {}
    // PHX34_DECLS
};
// PHX34_METHODS

static constexpr uint64_t queue[6] = {0x10000, 1024, 0x12000, 0, 8, 0x13000};
static void setup(PhxBringup &d) {
    uint64_t out[4]{};
    d.ackControl = true;
    CHECK(d.pspRing(1, 0, out) == kIOReturnSuccess && d.ringMc == d.fbMcBase);
    CHECK(d.fenceOff == PHX_PSP_FENCE_REL && d.cmdOff == PHX_PSP_CMD_REL && d.controlWrites == 1);
    d.ackControl = false;
}

static IOReturn submit(PhxBringup &d, uint64_t out[4]) {
    return d.pspSubmit(PHX_PSP_GFX_CMD_FB_FW_RESERV_ADDR, out);
}

static void blocked(PhxBringup &d) {
    uint64_t out[4]{};
    const auto ctrl = d.controlWrites, cmd = d.commandWrites;
    CHECK(d.exactRawWriters.drained() && !d.gpuReady());
    CHECK(d.adoptQueue(queue) == kIOReturnNotReady);
    CHECK(!d.exactQueueAdopted[0] && !d.exactQueueGeneration[0] && d.aperture.at(queue[5]) == 0);
    CHECK(d.pspRing(2, 0, out) == kIOReturnNotReady && submit(d, out) == kIOReturnNotReady);
    CHECK(d.vramWrite(queue[5], 11) == kIOReturnNotReady && d.aperture.at(queue[5]) == 0);
    CHECK(d.controlWrites == ctrl && d.commandWrites == cmd);
}

static void prior() {
    PhxBringup d;
    setup(d);
    uint64_t out[4]{};
    CHECK(submit(d, out) == kIOReturnSuccess && out[0] == 0xffffffffu);
    CHECK(!d.exactRawWriters.closed() && d.adoptQueue(queue) == kIOReturnSuccess && d.gpuReady());
    PhxBringup destroy;
    setup(destroy);
    CHECK(destroy.pspRing(2, 0, out) == kIOReturnTimeout && !destroy.ringMc);
    CHECK(destroy.adoptQueue(queue) == kIOReturnSuccess);
    PhxBringup create;
    CHECK(create.pspRing(1, 0, out) == kIOReturnTimeout && !create.ringMc);
    CHECK(create.adoptQueue(queue) == kIOReturnSuccess);
}

static void checked() {
    uint64_t out[4]{};
    PhxBringup create;
    CHECK(create.pspRing(1, 0, out) == kIOReturnTimeout && create.ringMc == create.fbMcBase);
    CHECK(create.controlWrites == 1 && !create.commandWrites);
    blocked(create);

    PhxBringup destroy;
    setup(destroy);
    CHECK(destroy.pspRing(2, 0, out) == kIOReturnTimeout && destroy.ringMc == destroy.fbMcBase);
    CHECK(destroy.controlWrites == 2 && destroy.cmdOff == PHX_PSP_CMD_REL && destroy.fenceOff == PHX_PSP_FENCE_REL);
    blocked(destroy);

    PhxBringup command;
    setup(command);
    out[2] = 12; out[3] = 13;
    CHECK(submit(command, out) == kIOReturnSuccess && out[0] == 0xffffffffu && out[2] == 0 && out[3] == 0);
    CHECK(command.commandWrites == 1 && command.fenceCounter == 1 && command.ringMc == command.fbMcBase);
    blocked(command);
    command.aperture.at(command.fenceOff) = command.fenceCounter; // modeled late device indication
    blocked(command);

    PhxBringup preflight;
    preflight.ctrl = 0;
    CHECK(preflight.pspRing(1, 0, out) == kIOReturnNotReady && !preflight.controlWrites);
    CHECK(!preflight.exactRawWriters.closed()); // no published request by this call

    PhxBringup finished;
    setup(finished);
    finished.ackCommand = true;
    CHECK(submit(finished, out) == kIOReturnSuccess && out[0] == 0 && out[2] == 9);
    finished.commandStatus = PHX_PSP_ERR_UNKNOWN_COMMAND;
    CHECK(submit(finished, out) == kIOReturnSuccess && out[0] == PHX_PSP_ERR_UNKNOWN_COMMAND);
    finished.ackControl = true;
    CHECK(finished.pspRing(2, 0, out) == kIOReturnSuccess && !finished.ringMc);
    CHECK(finished.adoptQueue(queue) == kIOReturnSuccess && finished.gpuReady());

    for (bool success : {false, true}) {
        PhxBringup race;
        setup(race);
        Pause pause;
        // Pause after publication, before the next fence sample.
        uint64_t result[4]{};
        IOReturn code = -1;
        std::thread worker([&] { firstPoll = &pause; code = submit(race, result); });
        pause.wait();
        CHECK(race.adoptQueue(queue) == kIOReturnBusy && race.exactRawWriters.closed());
        CHECK(!race.gpuReady() && race.vramWrite(queue[5], 1) == kIOReturnNotReady);
        if (success) race.aperture.at(race.fenceOff) = race.fenceCounter;
        pause.release();
        worker.join();
        CHECK(code == kIOReturnSuccess && result[0] == (success ? 0 : 0xffffffffu));
        if (success) CHECK(race.adoptQueue(queue) == kIOReturnSuccess);
        else blocked(race);
    }
}

int main(int argc, char **) {
    if (argc == 2) prior();
    else checked();
    std::printf("PASS %u PSP handoff checks\n", checks);
}
