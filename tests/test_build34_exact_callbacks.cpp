// SPDX-License-Identifier: MIT
// Actual staged methods, two CPU threads, finite scheduler/platform doubles.
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <mutex>
#include <thread>
#include "build34_exact_callbacks.h"
#include "build34_exact_ownership.h"

using namespace phx34_exact;
using IOReturn = int;
using thread_call_param_t = void *;
static std::atomic<uint64_t> checks{0};
static unsigned groups, threaded;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x); std::abort(); } } while (0)
enum { kIOReturnSuccess, kIOReturnNotReady, kIOReturnBadArgument, kIOReturnBusy, kIOReturnNoResources };
static constexpr int IOPMAckImplied = 77, kMillisecondScale = 1000000;
static constexpr uint32_t kFirstUserVmid = 8, kRegSqCmd = 0x237b, kRegRlcSafeMode = 0xa980;
static constexpr uint64_t sentinel = 0xabcdef;
static int gHangMs = 1;
static std::atomic<int> gHangKills{0};
static thread_local unsigned held;
static thread_local std::function<void(const char *)> eventHook;
static std::atomic<unsigned> lockTouches{0}, memoryTouches{0}, releases{0}, rearms{0}, sleeps{0};
static void event(const char *name) { if (eventHook) eventHook(name); }
struct Lock { std::mutex mutex; };
static void IOLockLock(Lock *p) {
    CHECK(p); ++lockTouches; event("lock-pointer"); p->mutex.lock(); ++held;
}
static void IOLockUnlock(Lock *p) { CHECK(p && held); --held; p->mutex.unlock(); }
struct Memory {
    alignas(16) uint64_t words[2048]{};
    uintptr_t getVirtualAddress() const { ++memoryTouches; event("aperture-pointer"); return reinterpret_cast<uintptr_t>(words); }
    size_t getLength() const { ++memoryTouches; event("length-pointer"); return sizeof words; }
    void release() { ++releases; }
};
static uint64_t mach_absolute_time() { return 10000000; }
static void absolutetime_to_nanoseconds(uint64_t value, uint64_t *out) { *out = value; }
static void nanoseconds_to_absolutetime(uint64_t value, uint64_t *out) { *out = value; }
static void clock_interval_to_deadline(int, int, uint64_t *out) { *out = 1; }
static void thread_call_enter_delayed(void *call, uint64_t) { CHECK(call); event("rearm-pointer"); ++rearms; }
static void IOSleep(unsigned ms) { CHECK(ms == 1 && !held); ++sleeps; event("unlocked-sleep"); }
static void IODelay(unsigned us) { CHECK(us == 1 && held); }
static void OSIncrementAtomic(std::atomic<int> *p) { ++*p; }
static void IOLog(const char *, ...) {}

struct PhxBringup {
    struct GpuQueue {
        bool ready = true, gfx = false;
        uint32_t ringOff = 0, ringDw = 1024, wbOff = 8192, fenceOff = 9000;
        uint64_t dbByte = 0, wptr = 8, doneEnd = 8;
        uint64_t fseq[64]{}, fend[64]{};
        uint32_t fvmid[64]{};
        volatile uint32_t head = 0, tail = 0;
        uint64_t lastDone = 99, lastProgress = 0, killedSeq = 0;
        bool killedAll = false;
    } gq[2];
    Memory aperture, bells, registers;
    Memory *fbAper = &aperture, *doorbellMap = &bells, *mmio = &registers;
    uint64_t fbAperLen = sizeof aperture.words, fbMcBase = 0x123400000ull;
    Lock gpuMutex;
    Lock *gpuLock = &gpuMutex;
    uint64_t gSeq = 99, exactQueueGeneration[2]{11,22}, exactInvalidationEpoch = 0;
    bool exactQueueLive[2]{true,true}, exactStopped = false, isSleeping = false;
    mutable CallbackGate<> exactCallbacks;
    std::atomic<unsigned> retained{0};
    void *hangCall = this;
    bool hangStop = false;
    struct { uint64_t lastSeq = 0; } hwv[8];
    unsigned binds = 0, packetWrites = 0, registerWrites = 0;
    bool contextReady = true, bindReady = true;
    PhxBringup() {
        gq[1].gfx = true; gq[1].ringOff = 4096; gq[1].wbOff += 64;
        gq[1].fenceOff += 8; gq[1].dbByte = 8;
        setFence(0,99); setFence(1,99);
    }
    void retain() { ++retained; }
    void *vmCtx(uint32_t handle) { CHECK(held); return contextReady && handle == 7 ? this : nullptr; }
    uint32_t vmBind(uint32_t handle) { CHECK(held && handle == 7); ++binds; return bindReady ? 8 : 0; }
    void hdpFlush() { CHECK(held); }
    void ringPut(GpuQueue &, uint32_t, uint32_t) { CHECK(held); event("first-packet"); ++packetWrites; }
    void wreg(uint32_t, uint32_t) { CHECK(held); event("register-write"); ++registerWrites; }
    uint32_t rreg(uint32_t reg) { CHECK(held && reg == kRegRlcSafeMode); return 0; }
    void setFence(unsigned qi, uint64_t value) { std::memcpy(reinterpret_cast<uint8_t *>(aperture.words)+gq[qi].fenceOff,&value,8); }
    IOReturn gpuSubmit(uint32_t, bool, const uint64_t *, const uint32_t *, uint32_t, uint64_t *, Registry * = nullptr, Ticket = {});
    IOReturn adoptQueue(const uint64_t[6]);
    IOReturn setPowerState(unsigned long, void *);
    uint64_t queueFence(const GpuQueue &) const;
    uint64_t gpuRetired() const;
    void invalidateExactQueues();
    void killWaves(uint32_t, bool);
    void hangCheck();
    static void hangTick(thread_call_param_t, thread_call_param_t);
    void stop(void *);
};
using IOService = void;

// PHX34_CALLBACK_METHODS

struct Pause {
    std::mutex mutex;
    std::condition_variable cv;
    bool reached = false, resume = false;
    void arrive() {
        std::unique_lock<std::mutex> guard(mutex);
        reached = true; cv.notify_all();
        CHECK(cv.wait_for(guard,std::chrono::seconds(5),[&]{return resume;}));
    }
    void wait() {
        std::unique_lock<std::mutex> guard(mutex);
        CHECK(cv.wait_for(guard,std::chrono::seconds(5),[&]{return reached;}));
    }
    void release() { std::lock_guard<std::mutex> guard(mutex); resume = true; cv.notify_all(); }
};
static void reset() {
    CHECK(!held && !eventHook); ++groups;
    lockTouches=memoryTouches=releases=rearms=sleeps=0;
}
static void adoptInput(PhxBringup &d, uint64_t in[6]) {
    const auto &q=d.gq[0];
    const uint64_t values[6]={q.ringOff,q.ringDw,q.wbOff,q.dbByte,q.wptr,q.fenceOff};
    std::memcpy(in,values,sizeof values);
}
static void deniedEntries(PhxBringup &d) {
    const auto locks=lockTouches.load(), memory=memoryTouches.load(), arms=rearms.load();
    uint64_t in[6]; adoptInput(d,in);
    uint64_t seq=sentinel, va=0x10000; uint32_t dw=16;
    CHECK(d.gpuSubmit(7,false,&va,&dw,1,&seq)==kIOReturnNotReady && seq==sentinel);
    CHECK(d.adoptQueue(in)==kIOReturnNotReady);
    CHECK(d.setPowerState(0,nullptr)==IOPMAckImplied);
    CHECK(d.gpuRetired()==0);
    d.killWaves(8,false); d.hangCheck(); PhxBringup::hangTick(&d,nullptr);
    CHECK(lockTouches==locks && memoryTouches==memory && rearms==arms);
    CHECK(!d.exactCallbacks.active() || !d.exactCallbacks.drained());
}
static void gateContract() {
    reset(); CallbackGate<2> gate;
    CHECK(!gate.closed() && !gate.drained() && gate.active()==0);
    {
        CallbackGate<2>::Lease beforeClose(gate); CHECK(beforeClose && gate.active()==1);
    }
    CHECK(!gate.closed() && !gate.active());
    {
        CallbackGate<2>::Lease first(gate); CHECK(first && gate.active()==1);
        {
            CallbackGate<2>::Lease second(gate), full(gate);
            CHECK(second && !full && gate.active()==2);
            CHECK(gate.close() && !gate.close() && !gate.drained());
            CallbackGate<2>::Lease denied(gate); CHECK(!denied && gate.active()==2);
        }
        CHECK(gate.active()==1 && !gate.drained());
    }
    CHECK(gate.closed() && gate.drained() && !gate.active());
    CallbackGate<2>::Lease foreverDenied(gate); CHECK(!foreverDenied);
}
static void idleAndQueuedStop() {
    reset(); PhxBringup d; Pause queued;
    std::thread callback([&]{queued.arrive(); deniedEntries(d);}); ++threaded;
    queued.wait(); d.stop(nullptr);
    CHECK(d.exactCallbacks.drained() && d.exactStopped && d.retained==1);
    CHECK(!d.exactQueueLive[0] && !d.exactQueueLive[1] && releases==0);
    queued.release(); callback.join();
    const auto epoch=d.exactInvalidationEpoch;
    d.stop(nullptr); CHECK(d.retained==1 && d.exactInvalidationEpoch==epoch && releases==0);
    CHECK(d.gpuLock && d.mmio && d.fbAper && d.doorbellMap && d.hangCall);
}
enum Operation { Submit, Adopt, Power, Retired, Kill, Watchdog, Tick, TickArm };
static void inflight(Operation op, bool pastWrite=false) {
    reset(); PhxBringup d; Pause pause; Registry registry(1); Ticket ticket;
    CHECK(registry.reserve(ticket)==Status::Ok);
    uint64_t in[6]; adoptInput(d,in);
    uint64_t seq=sentinel, va=0x10000; uint32_t dw=16;
    IOReturn result=-1; uint64_t retired=sentinel;
    const char *point=(op==Retired || op==Watchdog || op==Tick) ? "aperture-pointer" :
                      op==TickArm ? "rearm-pointer" : pastWrite ? "first-packet" : "lock-pointer";
    std::thread callback([&]{
        bool paused=false;
        eventHook=[&](const char *name){
            if (!paused && !std::strcmp(name,point)) { paused=true; pause.arrive(); }
        };
        switch(op) {
        case Submit: result=d.gpuSubmit(7,false,&va,&dw,1,&seq,&registry,ticket); break;
        case Adopt: result=d.adoptQueue(in); break;
        case Power: result=d.setPowerState(0,nullptr); break;
        case Retired: retired=d.gpuRetired(); break;
        case Kill: d.killWaves(8,false); break;
        case Watchdog: d.hangCheck(); break;
        case Tick: case TickArm: PhxBringup::hangTick(&d,nullptr); break;
        }
        CHECK(paused && !held); eventHook={};
    }); ++threaded;
    pause.wait();
    CHECK(d.exactCallbacks.active()>0);
    if (pastWrite) { Ticket found; CHECK(registry.lookup(100,found)==Status::Ok); }
    // This must return even when the callback holds gpuLock. No waiting on a
    // callback under that callback's lock, and no late release on last exit.
    d.stop(nullptr);
    CHECK(d.exactCallbacks.closed() && !d.exactCallbacks.drained() && d.retained==1 && releases==0);
    CHECK(!d.exactStopped); // busy stop does not race on GPU-locked metadata
    deniedEntries(d);
    pause.release(); callback.join();
    CHECK(d.exactCallbacks.drained() && !d.exactCallbacks.active() && releases==0);
    if (op==Submit) {
        CHECK(result==(pastWrite ? kIOReturnSuccess : kIOReturnNotReady));
        CHECK(seq==(pastWrite ? 100 : sentinel));
        CHECK(d.binds==unsigned(pastWrite) && bool(d.packetWrites)==pastWrite);
        if (pastWrite) {
            QueueObservation observations[2]={{11,100,100,true,false},{22,100,100,true,false}};
            CHECK(registry.observe(ticket,false,observations)==Status::Lost);
            CHECK(registry.forget(ticket)==Status::Invalid && registry.cancel(ticket)==Status::Invalid);
        } else CHECK(registry.cancel(ticket)==Status::Ok);
    }
    if (op==Adopt) CHECK(result==kIOReturnNotReady && d.exactQueueGeneration[0]==11);
    if (op==Power) CHECK(result==IOPMAckImplied && !d.isSleeping);
    if (op==Retired) CHECK(retired==99);
    if (op==Kill) CHECK(d.registerWrites==0 && d.exactInvalidationEpoch==0);
    if (op==Tick) CHECK(rearms==0);
    if (op==TickArm) {
        CHECK(rearms==1); // close after the final check may leave ONE queued tick
        PhxBringup::hangTick(&d,nullptr); CHECK(rearms==1); // it cannot recurse
    }
    d.stop(nullptr); CHECK(d.retained==1 && releases==0 && !d.exactStopped);
}
static void submitAcrossSleep() {
    reset(); PhxBringup d; Pause pause; Registry registry(2); Ticket ticket;
    CHECK(registry.reserve(ticket)==Status::Ok);
    auto &q=d.gq[0]; q.tail=63; q.ringDw=4096;
    for(unsigned i=0;i<63;++i) { q.fseq[i]=i+1; q.fend[i]=8; }
    d.setFence(0,0);
    uint64_t seq=sentinel, va=0x10000; uint32_t dw=16; IOReturn result=-1;
    std::thread callback([&]{
        eventHook=[&](const char *name){if(!std::strcmp(name,"unlocked-sleep")) pause.arrive();};
        result=d.gpuSubmit(7,false,&va,&dw,1,&seq,&registry,ticket);
        eventHook={}; CHECK(!held);
    }); ++threaded;
    pause.wait(); CHECK(d.exactCallbacks.active()==1 && sleeps==1);
    d.stop(nullptr); d.setFence(0,99); // space becomes available AFTER close
    CHECK(d.exactCallbacks.closed() && releases==0);
    pause.release(); callback.join();
    CHECK(result==kIOReturnNotReady && seq==sentinel && !d.binds && !d.packetWrites && d.gSeq==99);
    CHECK(registry.cancel(ticket)==Status::Ok && d.exactCallbacks.drained() && releases==0);
}
static void stopInsideCallback() {
    reset(); PhxBringup d;
    eventHook=[&](const char *name){
        if(!std::strcmp(name,"register-write")) {
            CHECK(held && d.exactCallbacks.active()==1);
            d.stop(nullptr); CHECK(d.exactCallbacks.closed() && releases==0 && d.retained==1);
        }
    };
    d.killWaves(8,false); eventHook={};
    CHECK(d.registerWrites==3 && d.exactCallbacks.drained() && releases==0);
}
static void earlyReturns() {
    for(unsigned fault=0;fault<8;++fault) {
        reset(); PhxBringup d; Registry registry(3); Ticket ticket;
        CHECK(registry.reserve(ticket)==Status::Ok);
        uint64_t seq=sentinel, va=0x10000; uint32_t dw=16;
        if(fault==0) d.contextReady=false;
        if(fault==1) d.gq[0].ready=d.gq[1].ready=false;
        if(fault==2) d.gq[0].ringDw=16;
        if(fault==3) d.bindReady=false;
        if(fault==4) d.gSeq=UINT64_MAX-1;
        if(fault==5) CHECK(registry.cancel(ticket)==Status::Ok);
        if(fault==6) d.isSleeping=true;
        if(fault==7) d.exactQueueLive[0]=false;
        CHECK(d.gpuSubmit(7,false,&va,&dw,1,&seq,&registry,ticket)!=kIOReturnSuccess);
        CHECK(seq==sentinel && !d.packetWrites && !d.exactCallbacks.active() && !held);
        d.stop(nullptr); CHECK(d.exactCallbacks.drained() && d.retained==1 && releases==0);
    }
    for(unsigned fault=0;fault<5;++fault) {
        reset(); PhxBringup d; uint64_t in[6]; adoptInput(d,in);
        if(fault==0) d.fbAper=nullptr;
        if(fault==1) in[1]=123;
        if(fault==2) d.exactQueueGeneration[0]=UINT64_MAX-1;
        if(fault==3) d.isSleeping=true;
        if(fault==4) d.exactStopped=true;
        CHECK(d.adoptQueue(in)!=kIOReturnSuccess && !d.exactCallbacks.active() && !held);
        d.stop(nullptr); CHECK(d.exactCallbacks.drained() && d.retained==1 && releases==0);
    }
    reset(); PhxBringup noLock; noLock.gpuLock=nullptr;
    noLock.killWaves(8,false);
    CHECK(!noLock.exactCallbacks.active() && !noLock.registerWrites);
    CHECK(noLock.setPowerState(0,nullptr)==IOPMAckImplied && !noLock.exactCallbacks.active());
    noLock.stop(nullptr); CHECK(noLock.exactCallbacks.drained() && noLock.retained==1 && releases==0);
}
static void simultaneousStops() {
    reset(); PhxBringup d; Pause start;
    std::thread otherStop([&]{start.arrive(); d.stop(nullptr);}); ++threaded;
    start.wait(); start.release(); d.stop(nullptr); otherStop.join();
    CHECK(d.retained==1 && d.exactCallbacks.drained() && d.exactInvalidationEpoch==1 && releases==0);
    deniedEntries(d);
}
static void closeAdmissionRace() {
    for(unsigned round=0;round<64;++round) {
        reset(); PhxBringup d; Pause start;
        std::thread callback([&]{start.arrive(); CHECK(d.setPowerState(0,nullptr)==IOPMAckImplied);});
        ++threaded; start.wait(); start.release(); d.stop(nullptr); callback.join();
        CHECK(d.exactCallbacks.drained() && d.retained==1 && releases==0);
        deniedEntries(d);
    }
}
int main() {
    gateContract(); idleAndQueuedStop();
    for(unsigned op=Submit;op<=TickArm;++op) inflight(Operation(op));
    inflight(Submit,true); submitAcrossSleep(); stopInsideCallback(); closeAdmissionRace();
    earlyReturns(); simultaneousStops();
    CHECK(!held && !eventHook);
    std::printf("PASS actual staged callback leases: %llu checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
                (unsigned long long)checks.load(),groups,threaded);
}
