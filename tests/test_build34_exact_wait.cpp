// SPDX-License-Identifier: MIT
// Includes frozen earlier CPU doubles and actual newly staged methods.
#include "binding-fixture-CPU-only.h"

// PHX34_EXACT_WAIT_METHOD

static void waitReset() { reset(); testTicks=10000000; sleepCalls=0; clockScale=1; }
static void zeroAndCompleted() {
    waitReset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d);
    auto seq=submit(c); d.exactFenceReader=sample;
    CHECK(c.waitExact(seq,0)==Status::TimedOut && sleepCalls==0);
    CHECK(c.waitExact(seq+1,100000)==Status::Unknown && sleepCalls==0);
    CHECK(c.waitExact(0,100000)==Status::Invalid && c.waitExact(UINT64_MAX,100000)==Status::Invalid);
    d.setFence(1,seq); CHECK(c.waitExact(seq,0)==Status::Complete && sleepCalls==0);
    CHECK(c.exactRegistry.occupied()==1 && c.retained==1 && d.retained==1);
}
static void timeBudgets() {
    for(unsigned mode=0;mode<8;++mode) {
        waitReset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d); auto seq=submit(c);
        d.exactFenceReader=sample; unsigned observations=0;
        const uint64_t budget=mode==0 ? 1 : mode==1 ? 2000001 : mode==2 ? 5000000 :
                              mode==3 ? 3000000 : mode==4 ? 2000000 : mode==5 ? UINT64_MAX :
                              mode==6 ? 750000 : 2000000;
        if(mode==6) clockScale=2;
        if(mode==7) testTicks=UINT64_MAX-500000; // modular monotonic tick rollover
        eventHook=[&](const char *name) {
            if(std::strcmp(name,"sample")==0) {
                ++observations;
                if(mode==3 && observations==1) testTicks+=3000000; // slow reader consumes budget
                if(mode==4 && observations==2) d.setFence(1,seq); // final observation can complete
            }
            if(std::strcmp(name,"sleep")==0 && mode==2) testTicks+=50000000; // scheduler delay
        };
        auto result=c.waitExact(seq,budget); eventHook={};
        CHECK(result==(mode==4 ? Status::Complete : Status::TimedOut));
        CHECK(sleepCalls==(mode==0 || mode==2 || mode==4 || mode==6 ? 1u : mode==1 ? 3u : mode==3 ? 0u : mode==5 ? 2000u : 2u));
        CHECK(observations==sleepCalls+1 && d.gpuRetired()==(mode==4 ? seq : 99));
        CHECK(c.exactRegistry.occupied()==1 && !frees && !terminations);
    }
}
static void exactGap() {
    waitReset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d);
    auto compute=submit(c,false),gfx=submit(c); d.exactFenceReader=sample; d.setFence(1,gfx);
    CHECK(d.gpuRetired()==99 && compute==100 && gfx==101);
    CHECK(c.waitExact(gfx,0)==Status::Complete && c.waitExact(compute,0)==Status::TimedOut);
    CHECK(d.gpuRetired()==99 && sleepCalls==0);
}
static void queuedLockTime(bool complete) {
    waitReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; start(c,d); auto seq=submit(c);
    d.exactFenceReader=sample; Pause p; Status result=Status::Invalid; unsigned count=0;
    IOLockLock(c.lock);
    std::thread t([&] { testTicks=10000000; eventHook=[&](const char *name) {
            if(std::strcmp(name,"client-lock-pointer")==0 && ++count==1) { p.arrive(); testTicks+=9000000; }
        };
        result=c.waitExact(seq,1000000); eventHook={}; });
    p.wait(); if(complete) d.setFence(1,seq); IOLockUnlock(c.lock); p.release(); t.join();
    CHECK(result==(complete ? Status::Complete : Status::TimedOut) && sleepCalls==0);
}
enum Mutation { CompleteOnSleep,ClientClose,ServiceStop,QueueLost,Readopt,ForgetAndReuse,
                ForgetUnknown,OtherQueueComplete,NoReader,ReaderFuture,AlreadyClosed };
static void betweenPolls() {
    for(unsigned mode=CompleteOnSleep;mode<=AlreadyClosed;++mode) {
        waitReset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d);
        auto seq=submit(c); d.exactFenceReader=sample; const auto old=ticket(c.exactRegistry,seq);
        Status expected=Status::Complete;
        if(mode==AlreadyClosed) { CHECK(c.clientClose()==kIOReturnSuccess); expected=Status::Closed; }
        if(mode==NoReader) { d.exactFenceReader=nullptr; expected=Status::InvalidObservation; }
        if(mode==ReaderFuture) { d.setFence(1,seq+1); expected=Status::InvalidObservation; }
        if(mode==ClientClose) expected=Status::Closed;
        if(mode==ServiceStop || mode==QueueLost || mode==Readopt) expected=Status::Lost;
        if(mode==ForgetAndReuse || mode==ForgetUnknown) expected=Status::Unknown;
        if(mode==OtherQueueComplete) expected=Status::TimedOut;
        eventHook=[&](const char *name) {
            if(std::strcmp(name,"sleep")!=0 || sleepCalls!=1) return;
            CHECK(!clientHeld && !gpuHeld); CHECK(c.exactClientCallbacks.active()==1);
            if(mode==CompleteOnSleep) d.setFence(1,seq);
            if(mode==ClientClose) CHECK(c.clientClose()==kIOReturnSuccess);
            if(mode==ServiceStop) d.stop(nullptr);
            if(mode==QueueLost) { IOLockLock(d.gpuLock); d.invalidateExactQueues(); IOLockUnlock(d.gpuLock); }
            if(mode==Readopt) { const auto &q=d.gq[1]; uint64_t in[]={q.ringOff,q.ringDw,q.wbOff,q.dbByte,q.wptr,q.fenceOff|1u};
                CHECK(d.adoptQueue(in)==kIOReturnSuccess); }
            if(mode==ForgetAndReuse || mode==ForgetUnknown) {
                IOLockLock(c.lock); d.setFence(1,seq);
                CHECK(d.observeExact(c.exactRegistry,old,c.exactClientCallbacks,&c)==Status::Complete);
                CHECK(c.exactRegistry.forget(old)==Status::Ok); IOLockUnlock(c.lock);
                if(mode==ForgetAndReuse) { auto next=submit(c); CHECK(next>seq); d.setFence(1,next); }
            }
            if(mode==OtherQueueComplete) { auto other=submit(c,false); d.setFence(0,other); }
        };
        CHECK(c.waitExact(seq,2000000)==expected); eventHook={};
        CHECK(sleepCalls==(mode>=NoReader ? 0u : mode==OtherQueueComplete ? 2u : 1u));
        CHECK(!frees && !terminations && c.retained==1 && c.exactClientCallbacks.active()==0);
        if(mode==ClientClose || mode==AlreadyClosed) CHECK(c.exactClientCallbacks.drained());
    }
}
static void threadDuringSleep(unsigned mode) {
    waitReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; start(c,d);
    auto seq=submit(c); d.exactFenceReader=sample; Pause p; Status result=Status::Invalid;
    std::thread t([&] { testTicks=10000000; eventHook=[&](const char *name) {
            if(std::strcmp(name,"sleep")==0 && sleepCalls==1) p.arrive(); };
        result=c.waitExact(seq,2000000); eventHook={}; });
    p.wait();
    CHECK(c.exactClientCallbacks.active()==1);
    // Both locks must be acquirable by a different real thread during sleep.
    IOLockLock(c.lock); IOLockLock(d.gpuLock);
    if(mode==0) d.setFence(1,seq);
    if(mode==1) { /* close is lock-independent, after releasing locks */ }
    if(mode==2) d.invalidateExactQueues();
    IOLockUnlock(d.gpuLock); IOLockUnlock(c.lock);
    if(mode==1) CHECK(c.clientClose()==kIOReturnSuccess);
    if(mode==3) d.stop(nullptr);
    p.release(); t.join();
    CHECK(result==(mode==0 ? Status::Complete : mode==1 ? Status::Closed : Status::Lost));
    CHECK(sleepCalls==1 && c.exactClientCallbacks.active()==0 && !frees && !terminations);
    if(mode==1) CHECK(c.exactClientCallbacks.drained());
}
static void invalidClientIdentity() {
    waitReset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d); auto seq=submit(c);
    d.exactFenceReader=sample;
    CHECK(c.waitExact(seq,3000000)==Status::TimedOut && sleepCalls==3);
    IOAccelPhxNativeClient other; start(other,d);
    c.exactOwnership=&other.exactRegistry;
    CHECK(c.waitExact(seq,1)==Status::Invalid);
    c.exactOwnership=&c.exactRegistry; c.exactClientPinned=false;
    CHECK(c.waitExact(seq,1)==Status::Invalid);
}
int main() {
    binding_regressions();
    const auto baselineChecks=checks.load(); const auto baselineGroups=groups,baselineThreads=threaded;
    zeroAndCompleted(); timeBudgets(); exactGap(); queuedLockTime(false); queuedLockTime(true); betweenPolls();
    for(unsigned mode=0;mode<4;++mode) threadDuringSleep(mode);
    invalidClientIdentity(); CHECK(!clientHeld && !gpuHeld && !eventHook);
    std::printf("PASS staged exact ticket wait: %llu additional checks; %u additional groups; %u additional threaded scenarios; inherited binding passed; GPU_executed=false\n",
                static_cast<unsigned long long>(checks.load()-baselineChecks),groups-baselineGroups,threaded-baselineThreads);
}
