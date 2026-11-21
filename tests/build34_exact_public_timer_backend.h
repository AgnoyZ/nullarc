// SPDX-License-Identifier: MIT
// Original CPU contract model, not copied IOKit/XNU code or native KPI evidence.
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
#include <vector>
#include "build34_exact_callbacks.h"
static std::atomic<unsigned> checks{0};
static unsigned groups=0,threaded=0;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x); std::_Exit(86); } } while(0)
static thread_local std::function<void(const char *)> hook;
static void event(const char *name) { if(hook) hook(name); }
using IOReturn=int; using thread_call_param_t=void *;
static constexpr IOReturn kIOReturnSuccess=0,kIOReturnNotReady=1,kIOReturnNoResources=2,kIOReturnBadArgument=3;
static constexpr int THREAD_CALL_PRIORITY_KERNEL=1;
static constexpr unsigned THREAD_CALL_OPTIONS_ONCE=1,kMillisecondScale=1;
static constexpr unsigned kIOTimerEventSourceOptionsPriorityKernel=2,kIOTimerEventSourceOptionsPriorityKernelHigh=1,kIOTimerEventSourceOptionsAllowReenter=256;
static thread_local unsigned timerHeld=0,gpuHeld=0;
static std::atomic<unsigned> allocation{0},failAllocation{0},arms{0},driverActions{0},reaps{0},watches{0},rawEnqueues{0},rawFrees{0};
static std::atomic<bool> failAttach{false},partialAttach{false},failRemove{false},failRemoveAfterDetach{false},lieRemove{false},failArm{false},failAction{false};
static bool allocating(const char *name) { auto n=++allocation; event(name); return failAllocation!=n; }
struct OSObject {
    std::atomic<unsigned> refs{1}; std::atomic<bool> dead{false};
    virtual ~OSObject()=default;
    virtual void free() { CHECK(!refs && !dead.exchange(true)); }
    void retain() { CHECK(!dead && refs.fetch_add(1)>0); }
    void release() { event("object-release"); auto n=refs.fetch_sub(1); CHECK(n>0 && !dead); if(n==1) free(); }
};
struct IOService:OSObject {};
struct IOLock { std::mutex mutex; bool gpu=false; };
static std::vector<std::unique_ptr<IOLock>> locks;
static IOLock *IOLockAlloc() { if(!allocating("allocate-lock")) return nullptr; auto p=std::make_unique<IOLock>(); auto *r=p.get(); locks.push_back(std::move(p)); return r; }
static void IOLockLock(IOLock *p) { CHECK(p && (p->gpu ? !gpuHeld : !timerHeld)); event(p->gpu ? "gpu-before-lock" : "timer-before-lock"); p->mutex.lock(); if(p->gpu) ++gpuHeld; else ++timerHeld; }
static void IOLockUnlock(IOLock *p) { CHECK(p); if(p->gpu) { CHECK(gpuHeld); --gpuHeld; } else { CHECK(timerHeld); --timerHeld; } p->mutex.unlock(); }
static void clock_interval_to_deadline(unsigned n,unsigned,uint64_t *p) { CHECK(n==500); *p=500; }
struct CpuCall {
    std::mutex mutex; void (*func)(void *,void *)=nullptr; void *owner=nullptr;
    bool queued=false,running=false,freed=false,freeRequested=false,failFree=false;
    int priority=0; unsigned options=0;
};
using thread_call_t=CpuCall *;
static std::vector<std::unique_ptr<CpuCall>> calls;
static thread_call_t thread_call_allocate_with_options(void (*f)(void *,void *),void *owner,int pri,unsigned opt) {
    if(!allocating("allocate-drain")) return nullptr;
    auto p=std::make_unique<CpuCall>(); p->func=f;p->owner=owner;p->priority=pri;p->options=opt;
    auto *r=p.get();calls.push_back(std::move(p));return r;
}
static bool thread_call_enter(CpuCall *p) {
    CHECK(p && timerHeld==1); std::lock_guard<std::mutex> guard(p->mutex);
    CHECK(!p->freed && !p->freeRequested); const bool was=p->queued;p->queued=true;++rawEnqueues;return was;
}
static bool thread_call_free(CpuCall *p) {
    CHECK(p && !gpuHeld && !timerHeld);++rawFrees;std::lock_guard<std::mutex> guard(p->mutex);
    CHECK(!p->freed && !p->freeRequested);if(p->queued || p->failFree) return false;
    p->freeRequested=true;p->freed=!p->running;return true;
}
static void runDrain(CpuCall *p) {
    { std::lock_guard<std::mutex> guard(p->mutex);CHECK(p->queued && !p->running && !p->freed);p->queued=false;p->running=true; }
    event("drain-before-entry");p->func(p->owner,nullptr);event("drain-before-finish");
    { std::lock_guard<std::mutex> guard(p->mutex);p->running=false;if(p->freeRequested)p->freed=true; }
}
struct IOTimerEventSource;
struct IOWorkLoop:OSObject {
    using Action=IOReturn (*)(OSObject *,void *,void *,void *,void *);
    std::recursive_timed_mutex gate;
    static thread_local std::vector<IOWorkLoop *> entered;
    static IOWorkLoop *workLoop();
    bool inGate() const { for(auto *p:entered) if(p==this)return true;return false; }
    IOReturn runAction(Action action,OSObject *owner,void *a=nullptr,void *b=nullptr,void *c=nullptr,void *d=nullptr) {
        CHECK(!dead && !timerHeld && !gpuHeld);event("loop-before-gate");
        CHECK(gate.try_lock_for(std::chrono::seconds(5)));entered.push_back(this);event("loop-in-gate");
        IOReturn r=failAction ? kIOReturnNotReady : action(owner,a,b,c,d);
        entered.pop_back();gate.unlock();return r;
    }
    IOReturn addEventSource(IOTimerEventSource *);
    IOReturn removeEventSource(IOTimerEventSource *);
};
thread_local std::vector<IOWorkLoop *> IOWorkLoop::entered;
struct IOTimerEventSource:OSObject {
    using Action=void (*)(OSObject *,IOTimerEventSource *);
    OSObject *owner=nullptr;Action action=nullptr;unsigned options=0;
    std::atomic<IOWorkLoop *> loop{nullptr};std::atomic<bool> enabled{true};std::atomic<uint64_t> generation{0};
    std::mutex mutex;bool queued=false,running=false;uint64_t queuedGeneration=0;IOWorkLoop *queuedLoop=nullptr;
    static IOTimerEventSource *timerEventSource(unsigned,OSObject *,Action);
    IOWorkLoop *getWorkLoop() const { CHECK(!dead);return loop; }
    bool isEnabled() const { CHECK(!dead);return enabled; }
    IOReturn wakeAtTime(uint64_t deadline) {
        auto *wl=loop.load();CHECK(!dead && wl && wl->inGate() && timerHeld && enabled && deadline==500);
        if(failArm)return kIOReturnNoResources;
        std::lock_guard<std::mutex> guard(mutex);++generation;queuedGeneration=generation;queuedLoop=wl;
        if(!queued) { retain();wl->retain();queued=true; }++arms;event("event-armed");return kIOReturnSuccess;
    }
    void cancelTimeout() {
        auto *wl=loop.load();CHECK(!dead && (!wl || wl->inGate()) && timerHeld);++generation;
        bool canceled=false;IOWorkLoop *held=nullptr;
        { std::lock_guard<std::mutex> guard(mutex);canceled=queued;if(canceled){queued=false;held=queuedLoop;} }
        if(canceled){held->release();release();}event("event-canceled");
    }
    void disable() { cancelTimeout();enabled=false;event("event-disabled"); }
    void free() override { CHECK(!loop && !queued && !running);OSObject::free(); }
};
static std::vector<std::unique_ptr<IOWorkLoop>> loops;
static std::vector<std::unique_ptr<IOTimerEventSource>> timers;
IOWorkLoop *IOWorkLoop::workLoop() {
    if(!allocating("allocate-loop"))return nullptr;
    auto p=std::make_unique<IOWorkLoop>();auto *r=p.get();loops.push_back(std::move(p));return r;
}
IOTimerEventSource *IOTimerEventSource::timerEventSource(unsigned options,OSObject *owner,Action action) {
    if(!allocating("allocate-event"))return nullptr;
    auto p=std::make_unique<IOTimerEventSource>();p->owner=owner;p->action=action;p->options=options;
    auto *r=p.get();timers.push_back(std::move(p));return r;
}
IOReturn IOWorkLoop::addEventSource(IOTimerEventSource *timer) {
    return runAction([](OSObject *o,void *arg,void *,void *,void *) {
        auto *wl=static_cast<IOWorkLoop *>(o);auto *t=static_cast<IOTimerEventSource *>(arg);
        CHECK(!t->loop && wl->inGate());if(!failAttach || partialAttach){t->retain();t->loop=wl;}event("event-attached");
        return failAttach ? kIOReturnNoResources : kIOReturnSuccess;
    },this,timer);
}
IOReturn IOWorkLoop::removeEventSource(IOTimerEventSource *timer) {
    CHECK(inGate() && timerHeld && timer->loop==this);
    if(failRemove)return kIOReturnNotReady;if(lieRemove)return kIOReturnSuccess;
    timer->loop=nullptr;timer->release();event("event-detached");return failRemoveAfterDetach ? kIOReturnNotReady : kIOReturnSuccess;
}
static void runTimer(IOTimerEventSource *timer) {
    IOWorkLoop *wl=nullptr;uint64_t gen=0;
    { std::lock_guard<std::mutex> guard(timer->mutex);CHECK(timer->queued && !timer->running && !timer->dead);
      timer->queued=false;timer->running=true;wl=timer->queuedLoop;gen=timer->queuedGeneration; }
    // Model a wrapper that has already observed enabled before waiting on its
    // gate. Cancellation still has to defeat the generation check under gate.
    event("wrapper-before-gate");
    struct Invocation { IOTimerEventSource *timer;uint64_t generation; } invocation{timer,gen};
    wl->runAction([](OSObject *,void *arg,void *,void *,void *) {
        auto &i=*static_cast<Invocation *>(arg);auto *t=i.timer;
        if(t->generation==i.generation && t->enabled) { ++driverActions;event("action-before-owner");t->action(t->owner,t); }
        return kIOReturnSuccess;
    },timer,&invocation);
    event("wrapper-before-finish");
    { std::lock_guard<std::mutex> guard(timer->mutex);timer->running=false; }
    wl->release();timer->release();
}
static bool queued(IOTimerEventSource *timer) { std::lock_guard<std::mutex> guard(timer->mutex);return timer->queued; }
struct Pause {
    std::mutex mutex;std::condition_variable cv;bool reached=false,released=false;
    void arrive(){std::unique_lock<std::mutex> lock(mutex);reached=true;cv.notify_all();CHECK(cv.wait_for(lock,std::chrono::seconds(5),[&]{return released;}));}
    void wait(){std::unique_lock<std::mutex> lock(mutex);CHECK(cv.wait_for(lock,std::chrono::seconds(5),[&]{return reached;}));}
    void resume(){std::lock_guard<std::mutex> lock(mutex);released=true;cv.notify_all();}
};
static void reset() {
    CHECK(!timerHeld && !gpuHeld && IOWorkLoop::entered.empty());hook={};++groups;
    for(auto &p:calls)CHECK(!p->running);for(auto &p:timers)CHECK(!p->running);
    calls.clear();timers.clear();loops.clear();locks.clear();
    allocation=failAllocation=arms=driverActions=reaps=watches=rawEnqueues=rawFrees=0;
    failAttach=partialAttach=failRemove=failRemoveAfterDetach=lieRemove=failArm=failAction=false;
}
