// SPDX-License-Identifier: MIT
// Original, deliberately small CPU scheduler model; no Apple implementation copied.
// API booleans follow the pinned reference contract, not a native KPI acceptance.
static constexpr int THREAD_CALL_PRIORITY_HIGH=0,THREAD_CALL_PRIORITY_KERNEL=1;
static constexpr unsigned THREAD_CALL_OPTIONS_ONCE=1;
using thread_call_func_t=void (*)(void *,void *);
struct CpuCall {
    std::mutex mutex; std::condition_variable cv;
    thread_call_func_t func=nullptr; void *owner=nullptr;
    bool real=false,queued=false,running=false,freeRequested=false,freed=false,failFree=false;
    unsigned options=0; int priority=THREAD_CALL_PRIORITY_HIGH;
    unsigned waiters=0;
};
using thread_call_t=CpuCall *;
static thread_local CpuCall *executingCall=nullptr;
static std::mutex backendPoolMutex;
static std::vector<std::unique_ptr<CpuCall>> backendCalls;
static std::vector<std::unique_ptr<Lock>> backendLocks;
static std::atomic<unsigned> timerAllocations{0},timerImmediate{0},timerCancelWaits{0},timerFreeAttempts{0},timerLockAllocations{0};
static std::atomic<unsigned> failTimerAllocation{0};
static std::atomic<bool> failTimerLock{false};
static Lock *IOLockAlloc() {
    CHECK(!gpuHeld && !timerHeld); ++timerLockAllocations; event("timer-lock-allocate");
    if(failTimerLock) return nullptr;
    auto p=std::make_unique<Lock>(); p->timer=true; auto *value=p.get();
    std::lock_guard<std::mutex> guard(backendPoolMutex); backendLocks.push_back(std::move(p)); return value;
}
static thread_call_t thread_call_allocate_with_options(thread_call_func_t func,void *owner,int priority,unsigned options) {
    CHECK(func && owner && !gpuHeld && !timerHeld); unsigned number=++timerAllocations;
    event("timer-allocate"); if(failTimerAllocation==number) return nullptr;
    auto p=std::make_unique<CpuCall>(); p->func=func; p->owner=owner; p->real=true; p->priority=priority; p->options=options;
    auto *value=p.get(); std::lock_guard<std::mutex> guard(backendPoolMutex); backendCalls.push_back(std::move(p)); return value;
}
static bool timerEnqueue(CpuCall *p,bool delayed) {
    CHECK(p && timerHeld<=1); bool was=false;
    { std::lock_guard<std::mutex> guard(p->mutex); CHECK(!p->freed && !p->freeRequested);
      if(p->real) { was=p->queued; p->queued=true; } }
    if(delayed) ++hangArms; else ++timerImmediate;
    event(delayed ? "timer-delayed" : "timer-immediate"); return was;
}
static bool thread_call_enter_delayed(CpuCall *p,uint64_t deadline) { CHECK(deadline==500); return timerEnqueue(p,true); }
static bool thread_call_enter(CpuCall *p) { return timerEnqueue(p,false); }
static thread_call_t thread_call_allocate(thread_call_func_t func,void *owner) {
    return thread_call_allocate_with_options(func,owner,THREAD_CALL_PRIORITY_HIGH,0);
}
static bool thread_call_cancel_wait(CpuCall *p) {
    CHECK(p && p->real && !gpuHeld && !clientHeld && !timerHeld && executingCall!=p);
    ++timerCancelWaits; event("timer-cancel-wait");
    std::unique_lock<std::mutex> guard(p->mutex); CHECK(!p->freed && !p->freeRequested);
    const bool canceled=p->queued; p->queued=false;
    // ONCE cancels pending AND waits for in-flight; ordinary calls that cancel
    // a newer pending instance do not provide that same wait guarantee.
    if((p->options&THREAD_CALL_OPTIONS_ONCE) || !canceled) {
        ++p->waiters; p->cv.notify_all();
        CHECK(p->cv.wait_for(guard,std::chrono::seconds(5),[&] { return !p->running; }));
        --p->waiters;
    }
    return canceled;
}
static bool thread_call_free(CpuCall *p) {
    CHECK(p && p->real && !gpuHeld && !clientHeld && !timerHeld); ++timerFreeAttempts; event("timer-free");
    std::lock_guard<std::mutex> guard(p->mutex); CHECK(!p->freed && !p->freeRequested);
    if(p->failFree || p->queued) return false;
    p->freeRequested=true; p->freed=!p->running; return true;
}
static void timerRun(CpuCall *p) {
    CHECK(p && p->real && !executingCall && !gpuHeld && !timerHeld);
    { std::lock_guard<std::mutex> guard(p->mutex); CHECK(p->queued && !p->freed && !p->freeRequested);
      CHECK(!p->running); p->queued=false; p->running=true; }
    executingCall=p; event("timer-before-entry"); p->func(p->owner,nullptr); event("timer-before-finish"); executingCall=nullptr;
    { std::lock_guard<std::mutex> guard(p->mutex); p->running=false; if(p->freeRequested) p->freed=true; p->cv.notify_all(); }
}
static bool timerQueued(CpuCall *p) { CHECK(p); std::lock_guard<std::mutex> guard(p->mutex); return p->queued; }
static bool timerRunning(CpuCall *p) { CHECK(p); std::lock_guard<std::mutex> guard(p->mutex); return p->running; }
static bool timerFreed(CpuCall *p) { CHECK(p); std::lock_guard<std::mutex> guard(p->mutex); return p->freed; }
static void waitForTimerWaiter(CpuCall *p) {
    CHECK(p); std::unique_lock<std::mutex> guard(p->mutex);
    CHECK(p->cv.wait_for(guard,std::chrono::seconds(5),[&] { return p->waiters==1; }));
}
static void resetTimerBackend() {
    CHECK(!timerHeld && !executingCall);
    for(auto &p:backendCalls) { std::lock_guard<std::mutex> guard(p->mutex); CHECK(!p->running); }
    backendCalls.clear(); backendLocks.clear();
    timerAllocations=timerImmediate=timerCancelWaits=timerFreeAttempts=timerLockAllocations=0;
    failTimerAllocation=0; failTimerLock=false;
}
