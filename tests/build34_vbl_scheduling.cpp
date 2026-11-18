// CPU doubles exercise production VBL logic; they do not validate XNU or a GPU.
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
using SInt64 = int64_t;
using thread_call_param_t = void *;
using IOFBInterruptProc = void (*)(void *, void *);
using Callback = void (*)(void *, void *);
constexpr unsigned THREAD_CALL_PRIORITY_HIGH = 0, THREAD_CALL_PRIORITY_KERNEL = 1;
constexpr unsigned THREAD_CALL_OPTIONS_ONCE = 1, kMicrosecondScale = 1000;
struct Call {
    Callback function;
    void *owner;
    unsigned priority, options;
    uint64_t deadline = 0;
    bool pending = false, running = false, freed = false;
};
using thread_call_t = Call *;
static uint64_t clockNow, highBusyUntil, gPhxVblLastAbs, gPhxVblSeq;
static SInt64 gVblN, gVblLateUsSum, gVblLateUsMax;
static int gVblStaged;
static unsigned checks, handlers, depth, maxDepth, waitCalls;
static bool allocationFails, injectReentry, injectStopRearm, agdcRemoved;
static void check(bool value) { assert(value); ++checks; }
static uint64_t mach_absolute_time() { return clockNow; }
static void nanoseconds_to_absolutetime(uint64_t v, uint64_t *out) { *out = v; }
static void absolutetime_to_nanoseconds(uint64_t v, uint64_t *out) { *out = v; }
static SInt64 OSAddAtomic64(SInt64 v, SInt64 *out) { return *out += v; }
static void clock_interval_to_deadline(uint32_t v, unsigned scale, uint64_t *out) {
    *out = clockNow + uint64_t(v) * scale;
}
static Call *thread_call_allocate_with_options(Callback f, void *owner, unsigned priority, unsigned options) {
    return allocationFails ? nullptr : new Call{f, owner, priority, options};
}
static bool dispatch(Call *c);
static bool thread_call_enter_delayed(Call *c, uint64_t deadline) {
    assert(c && !c->freed);
    const bool pending = c->pending;
    c->pending = true; c->deadline = deadline;
    if (c->running && injectReentry) {
        injectReentry = false; clockNow = deadline;
        dispatch(c); // Simulate another worker observing the newly due rearm.
    }
    return pending;
}
static bool dispatch(Call *c) {
    if (!c->pending || c->deadline > clockNow ||
        (c->priority == THREAD_CALL_PRIORITY_HIGH && clockNow < highBusyUntil) ||
        (c->running && (c->options & THREAD_CALL_OPTIONS_ONCE))) return false;
    c->pending = false; c->running = true;
    ++depth; if (depth > maxDepth) maxDepth = depth;
    c->function(c->owner, nullptr);
    --depth; c->running = false;
    return true;
}
static bool thread_call_cancel_wait(Call *c) {
    ++waitCalls; bool pending = c->pending; c->pending = false;
    if (injectStopRearm) {
        // An invocation that passed the stop check before stop() rearmed late.
        injectStopRearm = false; c->running = false; c->pending = true;
    } else c->running = false;
    return pending;
}
static bool thread_call_free(Call *c) {
    assert(!c->running); // Must drain before releasing callback-owned state.
    if (c->pending) return false;
    c->freed = true; return true;
}
static void phxAgdcRemove() { agdcRemoved = true; }
struct PhxAMDFB {
    struct Irq { IOFBInterruptProc proc; void *target, *ref; };
    std::vector<Irq> fVbl;
    bool fStopping = false;
    uint64_t fVblNext = 0, fFrameNs = 8333333;
    Call *fVblTimer = nullptr;
    // ACTUAL_VBL_CALLBACK
    void startTimer() {
        // ACTUAL_VBL_ALLOCATION
    }
    void stopTimer() {
        // ACTUAL_VBL_DRAIN
    }
};
static void handler(void *, void *) { ++handlers; }
static void reset() {
    clockNow = 1000000000; highBusyUntil = 0; gPhxVblLastAbs = gPhxVblSeq = 0;
    gVblN = gVblLateUsSum = gVblLateUsMax = 0; gVblStaged = 1;
    handlers = depth = maxDepth = waitCalls = 0;
    allocationFails = injectReentry = injectStopRearm = agdcRemoved = false;
}
static void release(PhxAMDFB &f) {
    Call *c = f.fVblTimer; f.stopTimer();
    check(f.fStopping && !f.fVblTimer && agdcRemoved);
    if (c) { check(c->freed && !c->pending && !c->running); delete c; }
}
int main() {
    for (int staged : {0, 1}) {
        reset(); gVblStaged = staged; PhxAMDFB f;
        f.fVbl.push_back({handler, nullptr, nullptr});
        f.startTimer(); Call *c = f.fVblTimer;
        check(c && c->priority == THREAD_CALL_PRIORITY_KERNEL);
        check(c->options & THREAD_CALL_OPTIONS_ONCE);
        // Model the observed unrelated HIGH callback without sleeping or hardware.
        highBusyUntil = clockNow + 300000000;
        Call control{PhxAMDFB::vblFire, &f, THREAD_CALL_PRIORITY_HIGH, 0};
        control.pending = true; control.deadline = c->deadline;
        clockNow = c->deadline;
        check(!dispatch(&control)); check(dispatch(c));
        check(gVblN == 1 && gPhxVblSeq == 1 && handlers == 1);
        check(gPhxVblLastAbs == 1008333000 && !gVblLateUsSum);
        check(c->pending && c->deadline == f.fVblNext - (staged ? 1500000 : 0));
        if (staged) {
            clockNow = c->deadline; check(dispatch(c));
            check(gVblN == 1 && handlers == 1 && c->deadline == f.fVblNext);
        }
        // A late callback produces one notification, not a catch-up burst.
        clockNow = f.fVblNext + 300000000;
        check(dispatch(c)); check(gVblN == 2 && handlers == 2);
        check(gVblLateUsSum == 300000 && gVblLateUsMax == 300000);
        check(f.fVblNext == clockNow + f.fFrameNs);
        // ONCE prevents another worker entering while the current call returns.
        clockNow = f.fVblNext; injectReentry = true;
        check(dispatch(c)); check(maxDepth == 1 && c->pending);
        release(f); check(waitCalls >= 2);
    }
    reset(); PhxAMDFB stopped; stopped.startTimer();
    stopped.fStopping = true; clockNow = stopped.fVblTimer->deadline;
    check(dispatch(stopped.fVblTimer));
    check(!gVblN && !stopped.fVblTimer->pending); release(stopped);
    reset(); PhxAMDFB racing; racing.startTimer();
    racing.fVblTimer->running = true; injectStopRearm = true;
    release(racing); check(waitCalls == 2);
    reset(); allocationFails = true; PhxAMDFB missing; missing.startTimer();
    check(!missing.fVblTimer && !missing.fVblNext); release(missing); check(!waitCalls);
    std::printf("actual VBL callback/allocation/drain: %u CPU assertions passed\n", checks);
}
