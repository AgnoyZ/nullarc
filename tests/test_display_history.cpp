// CPU-only harness around the actual hold/history bridge and server override.
#include <cassert>
#include <cstdint>
#include <cstring>
#include "PhxDisplayHistory.h"
using thread_call_t = void *;
using thread_call_param_t = void *;
using IOLock = bool;
static uint64_t now = 10;
static IOLock lock;
static IOLock *IOLockAlloc() { return &lock; }
static void IOLockLock(IOLock *p) { assert(!*p); *p = true; }
static void IOLockUnlock(IOLock *p) { assert(*p); *p = false; }
static void clock_get_uptime(uint64_t *v) { *v = now; }
static void absolutetime_to_nanoseconds(uint64_t v, uint64_t *out) { *out = v; }
struct IOService {
    int busy = 0;
    uint64_t id = 17;
    uint64_t getRegistryEntryID() { return id; }
    void adjustBusy(int v) { assert(lock); busy += v; }
};
#define AGLOG(...) ((void)0)
#include "display-bridge.inc"
using task_t = void *;
using UInt32 = unsigned;
using IOReturn = int;
struct IOUserClient {};
static constexpr unsigned kIOFBServerConnectType = 0;
static constexpr int kIOReturnSuccess = 0;
static int baseStatus = 0, baseCalls = 0;
struct IOFramebuffer {
    virtual int newUserClient(task_t, void *, unsigned, IOUserClient **) { ++baseCalls; return baseStatus; }
};
struct ActualServer : IOFramebuffer {
#include "display-server.inc"
};
int main(int argc, char **argv)
{
    assert(argc == 2);
    IOService fb;
    phxDisplayHistoryPrepare(&fb);
    assert(gDisplayHistory.framebufferID == 17 && gDisplayHistory.preparedNs == 10);
    gHoldFB = &fb; now = 20;
    holdSet(true, "boot", 0, 120000000000ull);
    assert(fb.busy == 1 && gDisplayHistory.held == 1 && gDisplayHistory.holdOnCount == 1);
    assert(gDisplayHistory.holdDeadlineNs == 120000000020ull);
    if (!strcmp(argv[1], "release")) {
        now = 30; holdSet(false, "sysctl");
        assert(fb.busy == 0 && gDisplayHistory.releaseReason == PHX_RELEASE_SYSCTL);
        now = 40; holdExpired(nullptr, nullptr);
        assert(gDisplayHistory.firstReleaseNs == 30 && gDisplayHistory.releaseCount == 1);
    } else if (!strcmp(argv[1], "timeout")) {
        now = 120000000020ull; holdExpired(nullptr, nullptr);
        assert(fb.busy == 0 && gDisplayHistory.releaseReason == PHX_RELEASE_TIMEOUT);
        holdSet(false, "sysctl");
        assert(gDisplayHistory.releaseReason == PHX_RELEASE_TIMEOUT && gDisplayHistory.releaseCount == 1);
    } else if (!strcmp(argv[1], "rearm")) {
        now = 30; holdSet(false, "sysctl");
        now = 40; holdSet(true, "sysctl");
        assert(gDisplayHistory.invalid == 1 && gDisplayHistory.holdOnCount == 2);
        assert(gDisplayHistory.firstReleaseNs == 30 && gDisplayHistory.holdOnNs == 20);
    } else if (!strcmp(argv[1], "restart")) {
        now = 30; phxDisplayHistoryPrepare(&fb);
        assert(gDisplayHistory.invalid == 1 && gDisplayHistory.preparations == 2);
        assert(gDisplayHistory.preparedNs == 10);
    } else if (!strcmp(argv[1], "server")) {
        ActualServer server; IOUserClient *client = nullptr;
        now = 30; assert(server.newUserClient(nullptr, nullptr, 1, &client) == 0);
        assert(!gDisplayHistory.serverRequests && baseCalls == 1);
        baseStatus = 99; now = 40;
        assert(server.newUserClient(nullptr, nullptr, 0, &client) == 99);
        assert(gDisplayHistory.serverRequests == 1 && !gDisplayHistory.serverSuccesses);
        baseStatus = 0; now = 50;
        assert(server.newUserClient(nullptr, nullptr, 0, &client) == 0);
        assert(gDisplayHistory.serverRequests == 2 && gDisplayHistory.serverSuccesses == 1);
        assert(gDisplayHistory.firstServerRequestNs == 40 && gDisplayHistory.firstServerSuccessNs == 50);
    } else return 1;
    return 0;
}
