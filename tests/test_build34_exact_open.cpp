// SPDX-License-Identifier: MIT
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include "PhxNativeABI.h"
#include "build34_exact_callbacks.h"
#include "build34_exact_fence32.h"
#include "build34_exact_open_wire.h"
#include "build34_exact_ownership.h"

static std::atomic<unsigned> checks{0};
#define CHECK(value) do { ++checks; if (!(value)) { std::fprintf(stderr, "failed %d: %s\n", __LINE__, #value); std::_Exit(86); } } while (0)
static thread_local std::function<void(const char *)> hook;
static void event(const char *name) { if (hook) hook(name); }
using task_t = void *;
using UInt32 = uint32_t;
using IOReturn = int;
enum { kIOReturnSuccess, kIOReturnBadArgument, kIOReturnNotReady, kIOReturnNoMemory,
       kIOReturnExclusiveAccess, kIOReturnNotPrivileged, IOPMAckImplied };
static constexpr char kIOClientPrivilegeAdministrator[] = "administrator";
static int admin, guest;
static volatile UInt32 gSysctlUp = 0;
static int sysctl__debug_phxbos_flush, sysctl__debug_phxbos_flush_bytes, sysctl__debug_phx_hang_ms, sysctl__debug_phx_hang_kills;
static bool OSCompareAndSwap(UInt32 from, UInt32 to, volatile UInt32 *where) {
    return __atomic_compare_exchange_n(where, &from, to, false, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE);
}
static void sysctl_register_oid(int *) {}
static void IOLog(const char *, ...) {}
static void *IOMallocZero(size_t size) { return std::calloc(1, size); }

struct IOLock { std::mutex mutex; };
static thread_local bool gpuHeld = false;
static IOLock *IOLockAlloc() { return new IOLock; }
static void IOLockLock(IOLock *lock) { CHECK(lock && !gpuHeld); lock->mutex.lock(); gpuHeld = true; }
static void IOLockUnlock(IOLock *lock) { CHECK(gpuHeld); gpuHeld = false; lock->mutex.unlock(); }

struct OSObject {
    std::atomic<unsigned> refs{1};
    virtual ~OSObject() = default;
    void retain() { CHECK(refs.fetch_add(1) != 0); }
    void release() { CHECK(refs.fetch_sub(1) != 0); }
};
struct IOService : OSObject {};
struct IOUserClient : IOService {
    bool attached = false, failBase = false;
    bool initWithTask(task_t, void *, UInt32) { event("init"); return true; }
    bool attach(IOService *) { attached = true; return true; }
    void detach(IOService *) { CHECK(attached && !gpuHeld); attached = false; }
    bool start(IOService *) { event("start"); return !failBase; }
    static IOReturn clientHasPrivilege(void *token, const char *right) {
        CHECK(!std::strcmp(right, kIOClientPrivilegeAdministrator));
        return token == &admin ? kIOReturnSuccess : kIOReturnNotPrivileged;
    }
};
#define OSDynamicCast(type, value) dynamic_cast<type *>(value)

// EXACT_OPEN_PROOF
static phx34_exact::OwnerEpochs gExactOwners;
struct IOAccelPhxNativeClient;
struct PhxBringup : IOService {
    mutable phx34_exact::CallbackGate<> exactCallbacks;
    phx34_exact::FenceWindow32 exactFenceWindow[2];
    struct { void (*wake)(IOLock *, void *); uint32_t queues; } *exactEventOps = nullptr;
    uint64_t exactEventSerial[2]{};
    struct { bool gfx, ready = true; } gq[2]{{false}, {true}};
    uint64_t exactInvalidationEpoch = 1, exactQueueGeneration[2]{4, 8};
    bool exactQueueLive[2]{true, true}, exactStopped = false, isSleeping = false, exactVMFault = false;
    struct { bool active = false, terminal = false; } watchdogRecovery;
    bool modeledAdmission = false, timerReady = true;
    std::atomic<bool> stopping{false};
    IOLock gpuStorage;
    IOLock *gpuLock = &gpuStorage;
    static bool modelReader(const volatile uint32_t *, uint32_t *) { std::_Exit(87); }
    decltype(&modelReader) exactDwordReader = nullptr;
    struct LegacyClientSlot { IOAccelPhxNativeClient *client = nullptr; bool pending = false; };
    static constexpr uint32_t kMaxCtx = 96;
    LegacyClientSlot legacyClients[kMaxCtx]{};
    bool hangTimerReady() const { return timerReady && !hangStopping(); }
    bool hangStopping() const { return stopping.load(); }
    void requestHangDrain() { stopping = true; }
    bool claimSession() { event("registered"); return true; }
    bool exactNativeOpenAdmitted() const;
    bool captureExactOpenLocked(Phx34ExactOpen &) const;
    IOReturn newUserClient(task_t, void *, UInt32, IOUserClient **);
    bool bindExactClient(phx34_exact::Registry &, OSObject *);
    bool registerLegacyClient(OSObject *);
    bool requestLegacyClose(IOAccelPhxNativeClient *);
    void stop(IOService *);
    void sealStoppedQueues();
    void invalidateExactQueues();
    IOReturn setPowerState(unsigned long, IOService *);
};
static constexpr int kMaxMaps = 2;
struct IOAccelPhxNativeClient : IOUserClient {
    struct Bo { uint64_t value; };
    struct Map { uint64_t value; };
    PhxBringup *owner = nullptr;
    IOLock *lock = nullptr;
    Bo *bos = nullptr;
    Map *maps = nullptr;
    task_t task = nullptr;
    uint32_t legacyState = 0;
    bool privileged = false, exactRequested = false, exactStartAttempted = false, exactClientPinned = false;
    bool legacyClientPinned = false, legacyProviderPinned = false, sessionClaimed = false;
    Phx34ExactOpen requestedExactOpen{};
    phx34_exact::Registry exactRegistry{0}, *exactOwnership = nullptr;
    phx34_exact::CallbackGate<> exactClientCallbacks;
    ~IOAccelPhxNativeClient() override { delete lock; std::free(bos); std::free(maps); }
    bool initWithTask(task_t, void *, UInt32);
    bool start(IOService *);
    IOReturn clientClose();
    IOReturn finishLegacyClose() { CHECK(!gpuHeld && exactClientCallbacks.drained()); return kIOReturnNotReady; }
};
static std::unique_ptr<IOAccelPhxNativeClient> allocated;
static unsigned allocations = 0;
static IOAccelPhxNativeClient *allocateClient() {
    ++allocations;
    allocated = std::make_unique<IOAccelPhxNativeClient>();
    return allocated.get();
}
#define OSTypeAlloc(type) allocateClient()

// EXACT_OPEN_METHODS

static IOReturn open(PhxBringup &driver, task_t task, UInt32 type, IOUserClient *&handler) {
    return driver.newUserClient(task, &admin, type, &handler);
}
static IOReturn exact(PhxBringup &driver, IOUserClient *&handler) {
    return open(driver, &admin, PHX34_R3_UC_TYPE, handler);
}
static void ready(PhxBringup &driver) {
    driver.modeledAdmission = true;
    driver.exactDwordReader = PhxBringup::modelReader;
}
static IOUserClient *sentinel() { return reinterpret_cast<IOUserClient *>(uintptr_t{1}); }

static void legacy() {
    PhxBringup driver;
    IOUserClient *handler = sentinel();
    CHECK(open(driver, &guest, PHXN_UC_TYPE, handler) == kIOReturnSuccess);
    CHECK(handler == allocated.get() && !allocated->exactRequested && !allocated->exactOwnership);
    CHECK(allocated->legacyState == 2 && allocated->refs == 2 && driver.refs == 2);
}

#if MODELED_OPEN
static void preflight() {
    for (unsigned fault = 0; fault != 14; ++fault) {
        PhxBringup driver;
        ready(driver);
        switch (fault) {
            case 0: driver.modeledAdmission = false; break;
            case 1: driver.exactDwordReader = nullptr; break;
            case 2: driver.gq[0].ready = false; break;
            case 3: driver.gq[1].ready = false; break;
            case 4: driver.exactQueueLive[0] = false; break;
            case 5: driver.exactQueueLive[1] = false; break;
            case 6: driver.exactQueueGeneration[0] = 0; break;
            case 7: driver.exactQueueGeneration[1] = UINT64_MAX - 1; break;
            case 8: driver.exactVMFault = true; break;
            case 9: driver.watchdogRecovery.active = true; break;
            case 10: driver.watchdogRecovery.terminal = true; break;
            case 11: driver.gq[1].gfx = false; break;
            case 12: driver.timerReady = false; break;
            case 13: driver.gpuLock = nullptr; break;
        }
        IOUserClient *handler = sentinel();
        const auto before = allocations;
        CHECK(exact(driver, handler) == kIOReturnNotReady && !handler);
        CHECK(allocations == before && driver.refs == 1 && !driver.exactCallbacks.active());
    }
    PhxBringup driver;
    ready(driver);
    const auto before = allocations;
    for (task_t task : {static_cast<task_t>(&guest), static_cast<task_t>(nullptr)}) {
        IOUserClient *handler = sentinel();
        CHECK(open(driver, task, PHX34_R3_UC_TYPE, handler) == kIOReturnNotPrivileged && !handler);
    }
    CHECK(allocations == before);
    IOUserClient *handler = sentinel();
    CHECK(open(driver, &admin, PHX34_R3_UC_TYPE + 1, handler) == kIOReturnBadArgument && !handler);
    CHECK(exact(driver, handler) == kIOReturnSuccess && handler == allocated.get());
    CHECK(allocated->exactRequested && allocated->exactStartAttempted && allocated->privileged);
    CHECK(allocated->exactOwnership == &allocated->exactRegistry && allocated->exactRegistry.boundTo(&driver, allocated.get()));
    CHECK(allocated->legacyState == 2 && allocated->refs == 2 && driver.refs == 2);
}

static void races() {
    for (const char *point : {"start", "registered"}) {
        for (unsigned fault = 0; fault != 4; ++fault) {
            PhxBringup driver;
            ready(driver);
            IOUserClient *handler = sentinel();
            IOReturn result = -1;
            std::mutex mutex;
            std::condition_variable changed;
            bool paused = false, resume = false;
            std::thread worker([&] {
                hook = [&](const char *name) {
                    if (std::strcmp(name, point)) return;
                    std::unique_lock<std::mutex> guard(mutex);
                    paused = true;
                    changed.notify_one();
                    CHECK(changed.wait_for(guard, std::chrono::seconds(5), [&] { return resume; }));
                };
                result = exact(driver, handler);
            });
            {
                std::unique_lock<std::mutex> guard(mutex);
                CHECK(changed.wait_for(guard, std::chrono::seconds(5), [&] { return paused; }));
            }
            if (fault == 0) driver.stop(nullptr);
            if (fault == 1) CHECK(driver.setPowerState(0, nullptr) == IOPMAckImplied);
            if (fault >= 2) {
                IOLockLock(driver.gpuLock);
                if (fault == 2) ++driver.exactQueueGeneration[1];
                else ++driver.exactInvalidationEpoch;
                IOLockUnlock(driver.gpuLock);
            }
            {
                std::lock_guard<std::mutex> guard(mutex);
                resume = true;
            }
            changed.notify_one();
            worker.join();
            CHECK(result == kIOReturnNotReady && !handler && !allocated->attached && !driver.exactCallbacks.active());
            if (!std::strcmp(point, "start")) {
                CHECK(allocated->legacyState == 4 && !allocated->refs && !allocated->exactOwnership);
                CHECK(!driver.legacyClients[0].client);
            } else {
                CHECK(allocated->exactClientCallbacks.drained() && allocated->refs == 1);
                CHECK(driver.legacyClients[0].client == allocated.get() && driver.legacyClients[0].pending);
            }
        }
    }
}
#endif

int main() {
    legacy();
#if MODELED_OPEN
    preflight();
    races();
#else
    PhxBringup driver;
    ready(driver);
    const auto before = allocations;
    IOUserClient *handler = sentinel();
    CHECK(exact(driver, handler) == kIOReturnNotReady && !handler);
    CHECK(allocations == before && !driver.legacyClients[0].client);
#endif
    std::printf("PASS exact open: %u checks; modeled=%d; GPU_executed=false\n", checks.load(), MODELED_OPEN);
}
