// SPDX-License-Identifier: MIT
// Extracted staged methods; CPU register/aperture/IOKit and reader doubles only.
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
using IOReturn=int;
using IOService=void;
static std::atomic<uint64_t> checks{0};
static unsigned groups,threaded;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x); std::abort(); } } while(0)
enum { kIOReturnSuccess,kIOReturnNotReady,kIOReturnBadArgument,kIOReturnBusy,kIOReturnNoResources };
static constexpr int IOPMAckImplied=77;
static constexpr uint32_t kFirstUserVmid=8,kRegSqCmd=0x237b,kRegRlcSafeMode=0xa980;
static constexpr uint64_t sentinel=0xabcdef;
static std::atomic<int> gHangKills{0};
static std::atomic<unsigned> lockTouches{0},memoryTouches{0},sampleCalls{0},sleeps{0};
static thread_local unsigned clientHeld,gpuHeld;
static thread_local std::function<void(const char *)> eventHook;
static bool readerAccept=true;
static void event(const char *name) { if(eventHook) eventHook(name); }
struct Lock { std::mutex mutex; bool client=false; };
static void IOLockLock(Lock *p) {
    CHECK(p); ++lockTouches; event(p->client ? "client-lock-pointer" : "gpu-lock-pointer");
    if(p->client) CHECK(!gpuHeld);
    p->mutex.lock(); if(p->client) ++clientHeld; else ++gpuHeld;
}
static void IOLockUnlock(Lock *p) {
    CHECK(p); if(p->client) { CHECK(clientHeld); --clientHeld; } else { CHECK(gpuHeld); --gpuHeld; }
    p->mutex.unlock();
}
struct Memory {
    alignas(16) uint64_t words[2048]{};
    uint64_t length=sizeof words;
    bool overrideBase=false; uintptr_t base=0;
    uintptr_t getVirtualAddress() const { ++memoryTouches; event("aperture-pointer");
        return overrideBase ? base : reinterpret_cast<uintptr_t>(words); }
    uint64_t getLength() const { ++memoryTouches; return length; }
};
static uint64_t mach_absolute_time() { return 10000000; }
static void absolutetime_to_nanoseconds(uint64_t v,uint64_t *out) { *out=v; }
static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); ++sleeps; }
static void IODelay(unsigned us) { CHECK(us==1 && gpuHeld); }
static void OSIncrementAtomic(std::atomic<int> *p) { ++*p; }
static void IOLog(const char *,...) {}
static bool sample(const volatile uint32_t *f,uint64_t *out) {
    CHECK(clientHeld==1 && gpuHeld==1); ++sampleCalls; event("sample");
    if(!readerAccept) return false;
    // Controlled CPU bytes, NOT an implementation/proof of device coherency.
    *out=uint64_t(f[0]) | (uint64_t(f[1])<<32); return true;
}
struct PhxBringup {
    struct GpuQueue {
        bool ready=true,gfx=false;
        uint32_t ringOff=0,ringDw=1024,wbOff=8192,fenceOff=9000;
        uint64_t dbByte=0,wptr=8,doneEnd=8,fseq[64]{},fend[64]{};
        uint32_t fvmid[64]{};
        volatile uint32_t head=0,tail=0;
        uint64_t lastDone=99,lastProgress=0,killedSeq=0;
        bool killedAll=false;
    } gq[2];
    Memory aperture,bells,registers;
    Memory *fbAper=&aperture,*doorbellMap=&bells,*mmio=&registers;
    uint64_t fbAperLen=sizeof aperture.words,fbMcBase=0x123400000ull;
    Lock mutex; Lock *gpuLock=&mutex;
    uint64_t gSeq=99,exactQueueGeneration[2]{11,22},exactQueueSubmitted[2]{99,99},exactInvalidationEpoch=0;
    bool exactQueueLive[2]{true,true},exactStopped=false,isSleeping=false;
    mutable CallbackGate<> exactCallbacks;
    using ExactFenceReader=bool (*)(const volatile uint32_t *,uint64_t *);
    ExactFenceReader exactFenceReader=nullptr;
    unsigned retained=0,binds=0,packetWrites=0,registerWrites=0;
    struct { uint64_t lastSeq=0; } hwv[8];
    PhxBringup() {
        gq[1].gfx=true; gq[1].ringOff=4096; gq[1].wbOff+=64; gq[1].fenceOff+=8; gq[1].dbByte=8;
        setFence(0,99); setFence(1,99);
    }
    void setFence(unsigned qi,uint64_t v) { CHECK(qi<2); std::memcpy(reinterpret_cast<uint8_t *>(aperture.words)+gq[qi].fenceOff,&v,8); }
    void retain() { ++retained; }
    void *vmCtx(uint32_t h) { CHECK(gpuHeld); return h==7 ? this : nullptr; }
    uint32_t vmBind(uint32_t h) { CHECK(gpuHeld && h==7); ++binds; return 8; }
    void hdpFlush() { CHECK(gpuHeld); }
    void ringPut(GpuQueue &,uint32_t,uint32_t) { CHECK(gpuHeld); ++packetWrites; }
    void wreg(uint32_t,uint32_t) { CHECK(gpuHeld); ++registerWrites; }
    uint32_t rreg(uint32_t reg) { CHECK(gpuHeld && reg==kRegRlcSafeMode); return 0; }
    IOReturn gpuSubmit(uint32_t,bool,const uint64_t *,const uint32_t *,uint32_t,uint64_t *,Registry * =nullptr,Ticket ={});
    IOReturn adoptQueue(const uint64_t[6]);
    IOReturn setPowerState(unsigned long,void *);
    void invalidateExactQueues();
    void killWaves(uint32_t,bool);
    void stop(void *);
    uint64_t gpuRetired() const;
    uint64_t queueFence(const GpuQueue &) const;
    Status observeExact(Registry &,Ticket,const CallbackGate<> &);
};
struct IOAccelPhxNativeClient {
    PhxBringup *owner;
    Registry *exactOwnership;
    bool exactClientPinned=true; // fixture binding; prior suite separately tests actual start/close
    CallbackGate<> exactClientCallbacks;
    Lock mutex; Lock *lock=&mutex;
    IOAccelPhxNativeClient(PhxBringup &d,Registry &r):owner(&d),exactOwnership(&r) { mutex.client=true; }
    Status queryExact(uint64_t);
};

// PHX34_OBSERVER_METHODS

struct Pause {
    std::mutex mutex; std::condition_variable cv; bool reached=false,resume=false;
    void arrive() { std::unique_lock<std::mutex> l(mutex); reached=true; cv.notify_all();
        CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return resume;})); }
    void wait() { std::unique_lock<std::mutex> l(mutex);
        CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return reached;})); }
    void release() { std::lock_guard<std::mutex> l(mutex); resume=true; cv.notify_all(); }
};
static void reset() { CHECK(!clientHeld && !gpuHeld && !eventHook); ++groups;
    lockTouches=memoryTouches=sampleCalls=sleeps=0; readerAccept=true; }
static uint64_t submit(IOAccelPhxNativeClient &c,bool gfx,bool exact=true) {
    IOLockLock(c.lock); Ticket t; Registry *r=exact ? c.exactOwnership : nullptr;
    if(r) CHECK(r->reserve(t)==Status::Ok);
    uint64_t seq=sentinel,va=0x10000; uint32_t dw=16;
    CHECK(c.owner->gpuSubmit(7,gfx,&va,&dw,1,&seq,r,t)==kIOReturnSuccess);
    IOLockUnlock(c.lock); return seq;
}
static Ticket ticket(Registry &r,uint64_t seq) { Ticket t; CHECK(r.lookup(seq,t)==Status::Ok); return t; }
static void adopt(PhxBringup &d,unsigned qi) {
    const auto &q=d.gq[qi]; uint64_t in[]={q.ringOff,q.ringDw,q.wbOff,q.dbByte,q.wptr,q.fenceOff|qi};
    CHECK(d.adoptQueue(in)==kIOReturnSuccess);
    CHECK(d.exactQueueSubmitted[qi]==d.gSeq);
}
static void inspectContract() {
    reset(); Registry r(1); Ticket t; Receipt out{sentinel,sentinel,1};
    CHECK(r.reserve(t)==Status::Ok && r.inspect(t,out)==Status::Unsubmitted && out.sequence==sentinel);
    CHECK(r.publish(t,{100,11,0})==Status::Ok);
    Ticket foreign=t; ++foreign.owner;
    CHECK(r.inspect(foreign,out)==Status::Unknown && out.sequence==sentinel);
    CHECK(r.inspect(t,out)==Status::Ok && out.sequence==100 && out.generation==11 && out.queue==0);
    QueueObservation q[2]={{11,100,100,true,false},{}};
    CHECK(r.observe(t,true,q)==Status::Complete && r.inspect(t,out)==Status::Ok);
    CHECK(r.forget(t)==Status::Ok); Ticket replacement;
    CHECK(r.reserve(replacement)==Status::Ok && r.inspect(t,out)==Status::Unknown);
    CHECK(r.publish(replacement,{101,11,0})==Status::Ok);
    CHECK(r.observe(replacement,false,q)==Status::Lost && r.inspect(replacement,out)==Status::Lost);
    r.close(); CHECK(r.inspect(replacement,out)==Status::Closed);
}
static void splitQueuesAndHistory() {
    reset(); PhxBringup d; Registry r(2); IOAccelPhxNativeClient c(d,r); d.exactFenceReader=sample;
    const auto compute=submit(c,false),gfx=submit(c,true);
    CHECK(compute==100 && gfx==101 && d.exactQueueSubmitted[0]==100 && d.exactQueueSubmitted[1]==101);
    d.setFence(1,gfx); CHECK(d.gpuRetired()==99);
    CHECK(c.queryExact(gfx)==Status::Complete && c.queryExact(compute)==Status::Pending);
    CHECK(d.gpuRetired()==99); // exact success never advances the safe global prefix
    // Reuse/empty the 64-slot transport history; exact ownership is separate.
    d.gq[1].head=d.gq[1].tail=128;
    for(auto &value:d.gq[1].fseq) value=0;
    CHECK(c.queryExact(gfx)==Status::Complete && r.occupied()==2);
    CHECK(c.queryExact(gfx-2)==Status::Unknown);
    const auto t=ticket(r,gfx); CHECK(r.forget(t)==Status::Ok && c.queryExact(gfx)==Status::Unknown);
    CHECK(c.queryExact(compute)==Status::Pending && sleeps==0);
}
static void noReaderAndUnowned() {
    reset(); PhxBringup d; Registry r(3),other(4); IOAccelPhxNativeClient c(d,r),foreign(d,other);
    const auto seq=submit(c,true); d.setFence(1,seq);
    CHECK(!d.exactFenceReader && c.queryExact(seq)==Status::InvalidObservation && sampleCalls==0);
    CHECK(foreign.queryExact(seq)==Status::Unknown);
    auto before=memoryTouches.load(); CHECK(c.queryExact(0)==Status::Invalid && c.queryExact(UINT64_MAX)==Status::Invalid);
    CHECK(c.queryExact(seq+1)==Status::Unknown && memoryTouches==before);
    c.exactClientPinned=false; CHECK(c.queryExact(seq)==Status::Invalid);
    c.exactClientPinned=true; c.exactOwnership=nullptr; CHECK(c.queryExact(seq)==Status::Invalid);
}
enum BadSample { FutureFence,StaleAfterComplete,RejectReader,NoCachedRange,NoMapRange,MisalignedOffset,
                 NullBase,WrappedBase,MisalignedBase,MissingMap,MissingLock,Unready,InvalidQueue,WrongGeneration };
static void invalidSamples() {
    for(unsigned mode=FutureFence;mode<=WrongGeneration;++mode) {
        reset(); PhxBringup d; Registry r(10+mode); IOAccelPhxNativeClient c(d,r); d.exactFenceReader=sample;
        const auto seq=submit(c,true); submit(c,false,false); // other queue advances global but not target upper bound
        d.setFence(1,seq);
        if(mode==StaleAfterComplete) CHECK(c.queryExact(seq)==Status::Complete);
        const auto before=sampleCalls.load();
        switch(mode) {
        case FutureFence: d.setFence(1,seq+1); break;
        case StaleAfterComplete: d.setFence(1,seq-1); break;
        case RejectReader: readerAccept=false; break;
        case NoCachedRange: d.fbAperLen=d.gq[1].fenceOff+7; break;
        case NoMapRange: d.aperture.length=d.gq[1].fenceOff+7; break;
        case MisalignedOffset: ++d.gq[1].fenceOff; break;
        case NullBase: d.aperture.overrideBase=true; break;
        case WrappedBase: d.aperture.overrideBase=true; d.aperture.base=UINTPTR_MAX-7; break;
        case MisalignedBase: d.aperture.overrideBase=true; d.aperture.base=reinterpret_cast<uintptr_t>(d.aperture.words)+1; break;
        case MissingMap: d.fbAper=nullptr; break;
        case MissingLock: d.gpuLock=nullptr; break;
        case Unready: d.gq[1].ready=false; break;
        case InvalidQueue: d.exactQueueLive[1]=false; break;
        case WrongGeneration: ++d.exactQueueGeneration[1]; break;
        }
        const bool lost=mode>=MissingMap;
        CHECK(c.queryExact(seq)==(lost ? Status::Lost : Status::InvalidObservation));
        if(mode>=NoCachedRange) CHECK(sampleCalls==before);
        if(lost) { CHECK(r.forget(ticket(r,seq))==Status::Invalid); }
    }
}
static void lifecycleAndLegacy() {
    for(unsigned mode=0;mode<3;++mode) {
        reset(); PhxBringup d; Registry r(30+mode); IOAccelPhxNativeClient c(d,r); d.exactFenceReader=sample;
        const auto seq=submit(c,true); d.setFence(1,seq);
        if(mode==0) adopt(d,1);
        if(mode==1) { CHECK(d.setPowerState(0,nullptr)==IOPMAckImplied); CHECK(d.setPowerState(1,nullptr)==IOPMAckImplied); }
        if(mode==2) d.killWaves(8,false);
        const auto before=sampleCalls.load(); CHECK(c.queryExact(seq)==Status::Lost && sampleCalls==before);
        if(mode!=0) { adopt(d,0); adopt(d,1); }
        CHECK(c.queryExact(seq)==Status::Lost && r.forget(ticket(r,seq))==Status::Invalid);
        const auto next=submit(c,true); d.setFence(1,next); CHECK(c.queryExact(next)==Status::Complete);
    }
    reset(); PhxBringup d; Registry r(34); IOAccelPhxNativeClient c(d,r); d.exactFenceReader=sample;
    submit(c,true,false); const auto seq=submit(c,true); d.setFence(1,seq);
    CHECK(d.exactQueueSubmitted[1]==seq && c.queryExact(seq)==Status::Complete);
    CHECK(c.queryExact(seq-1)==Status::Unknown); // legacy dispatch does not invent an owned receipt
    // Selected/fallback queue identity comes from actual submit, not the request bit.
    d.gq[1].ready=false; const auto fallback=submit(c,true); d.setFence(0,fallback);
    CHECK(d.exactQueueSubmitted[0]==fallback && c.queryExact(fallback)==Status::Complete);
}
static void independentModel() {
    uint32_t random=0x7185;
    for(unsigned round=0;round<128;++round) {
        reset(); PhxBringup d; Registry r(100+round); IOAccelPhxNativeClient c(d,r); d.exactFenceReader=sample;
        uint64_t seq[8],done[2]={99,99}; unsigned queue[8];
        for(unsigned i=0;i<8;++i) {
            random=random*1664525u+1013904223u; queue[i]=(random>>16)&1;
            seq[i]=submit(c,queue[i]);
            if(random&0x1000000) done[queue[i]]=seq[i];
        }
        d.setFence(0,done[0]); d.setFence(1,done[1]);
        for(unsigned i=0;i<8;++i) CHECK(c.queryExact(seq[i])==(seq[i]<=done[queue[i]] ? Status::Complete : Status::Pending));
        CHECK(r.occupied()==8 && sleeps==0 && !clientHeld && !gpuHeld);
    }
}
static void wideSequences() {
    for(uint64_t previous:{(1ull<<32)-1,UINT64_MAX-3}) {
        reset(); PhxBringup d; Registry r(290); IOAccelPhxNativeClient c(d,r); d.exactFenceReader=sample;
        d.gSeq=previous;
        for(unsigned qi=0;qi<2;++qi) { d.exactQueueSubmitted[qi]=previous; d.setFence(qi,previous); }
        const auto first=submit(c,false),second=submit(c,true);
        CHECK(first==previous+1 && second==previous+2);
        d.setFence(1,second);
        CHECK(c.queryExact(first)==Status::Pending && c.queryExact(second)==Status::Complete);
        CHECK(d.gpuRetired()==previous);
        if(previous==UINT64_MAX-3) {
            IOLockLock(c.lock); Ticket t; CHECK(r.reserve(t)==Status::Ok);
            const auto writes=d.packetWrites; uint64_t seq=sentinel,va=0x10000; uint32_t dw=16;
            CHECK(d.gpuSubmit(7,true,&va,&dw,1,&seq,&r,t)==kIOReturnNoResources && seq==sentinel);
            CHECK(r.cancel(t)==Status::Ok && d.packetWrites==writes && d.gSeq==second);
            IOLockUnlock(c.lock);
        }
        d.exactQueueSubmitted[1]=UINT64_MAX;
        CHECK(c.queryExact(second)==Status::InvalidObservation); // reserved upper bound is never admitted
    }
}
static void closing(bool service,const char *point) {
    reset(); PhxBringup d; Registry r(300); IOAccelPhxNativeClient c(d,r); d.exactFenceReader=sample;
    const auto seq=submit(c,true); d.setFence(1,seq); Pause pause; Status result=Status::Invalid;
    std::thread worker([&]{ bool paused=false; eventHook=[&](const char *name){
        if(!paused && !std::strcmp(name,point)) {paused=true; pause.arrive();} };
        result=c.queryExact(seq); CHECK(paused && !clientHeld && !gpuHeld); eventHook={}; }); ++threaded;
    pause.wait(); CHECK(c.exactClientCallbacks.active()>0);
    if(service) { CHECK(d.exactCallbacks.active()>0); d.stop(nullptr); CHECK(d.retained==1 && !d.exactStopped); }
    else c.exactClientCallbacks.close(); // actual close body separately covered by the prior client suite
    pause.release(); worker.join();
    CHECK(result==(!service && !std::strcmp(point,"client-lock-pointer") ? Status::Closed : Status::Lost));
    if(service) { CHECK(d.exactCallbacks.drained()); }
    else { CHECK(c.exactClientCallbacks.drained()); }
    auto before=lockTouches.load(),reads=sampleCalls.load();
    CHECK(c.queryExact(seq)==(service ? Status::Lost : Status::Closed));
    CHECK(sampleCalls==reads && lockTouches==before+unsigned(service));
}
static void serializedInvalidation(unsigned kind) {
    reset(); PhxBringup d; Registry r(310+kind); IOAccelPhxNativeClient c(d,r); d.exactFenceReader=sample;
    const auto seq=submit(c,true); d.setFence(1,seq); Pause reading,mutating; Status result=Status::Invalid;
    std::thread query([&]{ eventHook=[&](const char *name){if(!std::strcmp(name,"sample")) reading.arrive();};
        result=c.queryExact(seq); eventHook={}; });
    reading.wait();
    std::thread mutate([&]{ bool paused=false; eventHook=[&](const char *name){if(!paused && !std::strcmp(name,"gpu-lock-pointer")) {
        paused=true; mutating.arrive(); }};
        if(kind==0) adopt(d,1); else if(kind==1) d.setPowerState(0,nullptr); else d.killWaves(8,false);
        eventHook={}; }); ++threaded;
    mutating.wait(); mutating.release(); reading.release(); query.join(); mutate.join();
    CHECK(result==Status::Complete && c.queryExact(seq)==Status::Lost);
    CHECK(r.forget(ticket(r,seq))==Status::Invalid);
}
static void closedBeforeEntry() {
    reset(); PhxBringup d; Registry r(320); IOAccelPhxNativeClient c(d,r); d.exactFenceReader=sample;
    const auto seq=submit(c,true); d.setFence(1,seq); d.stop(nullptr);
    const auto before=lockTouches.load(),reads=memoryTouches.load();
    CHECK(c.queryExact(seq)==Status::Lost && lockTouches==before+1 && memoryTouches==reads);
    CHECK(d.exactCallbacks.drained() && d.retained==1);
}
int main() {
    inspectContract(); splitQueuesAndHistory(); noReaderAndUnowned(); invalidSamples(); lifecycleAndLegacy(); independentModel(); wideSequences();
    for(const char *point:{"gpu-lock-pointer","aperture-pointer","sample"}) closing(true,point);
    for(const char *point:{"client-lock-pointer","gpu-lock-pointer","aperture-pointer","sample"}) closing(false,point);
    for(unsigned kind=0;kind<3;++kind) serializedInvalidation(kind);
    closedBeforeEntry(); CHECK(!clientHeld && !gpuHeld && !eventHook);
    std::printf("PASS staged exact target observer: %llu checks; %u groups; %u threaded scenarios; 128 model rounds; hardware_reader=false; GPU_executed=false\n",
                (unsigned long long)checks.load(),groups,threaded);
}
