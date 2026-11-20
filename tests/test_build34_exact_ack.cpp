// SPDX-License-Identifier: MIT
#include "ack-base-CPU-only.h"

// PHX34_EXACT_ACK_METHODS

#include "wait-regressions-CPU-only.h"

static void ackReset() { reset(); testTicks=10000000; sleepCalls=0; clockScale=1; }
static void metadataOnly() {
    ackReset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d);
    auto compute=submit(c,false),gfx=submit(c); d.exactFenceReader=sample;
    CHECK(c.ackExact(0)==Status::Invalid && c.ackExact(UINT64_MAX)==Status::Invalid);
    CHECK(c.ackExact(gfx+1)==Status::Unknown && c.exactRegistry.occupied()==2);
    eventHook=[&](const char *name) { if(std::strcmp(name,"sample")==0) CHECK(c.exactClientCallbacks.active()==1); };
    CHECK(c.ackExact(gfx)==Status::Pending && c.exactRegistry.occupied()==2);
    d.setFence(1,gfx);
    CHECK(c.ackExact(gfx)==Status::Ok && c.exactRegistry.occupied()==1);
    CHECK(c.ackExact(gfx)==Status::Unknown && c.queryExact(gfx)==Status::Unknown);
    CHECK(c.ackExact(compute)==Status::Pending && d.gpuRetired()==99);
    eventHook={};
    CHECK(!frees && !terminations && c.exactResourcesExposed && c.retained==1 && d.retained==1);
}
static void sustainedReuse() {
    ackReset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d); d.exactFenceReader=sample;
    for(unsigned i=0;i<2000;++i) {
        const bool gfx=i%2; auto seq=submit(c,gfx); d.setFence(gfx ? 1 : 0,seq);
        CHECK(c.ackExact(seq)==Status::Ok && c.exactRegistry.occupied()==0);
        CHECK(c.ackExact(seq)==Status::Unknown);
    }
    CHECK(!frees && !terminations && c.exactResourcesExposed);
}
static void capacityAndRecovery() {
    ackReset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d); d.exactFenceReader=sample;
    uint64_t seqs[64];
    for(unsigned i=0;i<64;++i) seqs[i]=submit(c,i%2);
    CHECK(c.exactRegistry.occupied()==64);
    auto before=packetWrites.load();
    Request refused; IOLockLock(c.lock);
    CHECK(c.doSubmit(&refused.a)==kIOReturnNoResources); IOLockUnlock(c.lock);
    CHECK(refused.a.scalarOutput[0]==sentinel);
    CHECK(packetWrites==before && c.exactRegistry.occupied()==64);
    d.setFence(0,seqs[62]); d.setFence(1,seqs[63]);
    for(auto seq:seqs) CHECK(c.ackExact(seq)==Status::Ok);
    CHECK(c.exactRegistry.occupied()==0 && !frees && !terminations);
    auto next=submit(c); CHECK(next>seqs[63]);
}
static void invalidAndLost() {
    for(unsigned mode=0;mode<6;++mode) {
        ackReset(); PhxBringup d; IOAccelPhxNativeClient c,other; start(c,d); start(other,d);
        auto seq=submit(c); d.exactFenceReader=sample; d.setFence(1,seq);
        Status expected=Status::Invalid;
        if(mode==0) c.exactOwnership=&other.exactRegistry;
        if(mode==1) c.exactClientPinned=false;
        if(mode==2) { c.clientClose(); expected=Status::Closed; }
        if(mode==3) { IOLockLock(d.gpuLock); d.invalidateExactQueues(); IOLockUnlock(d.gpuLock); expected=Status::Lost; }
        if(mode==4) { d.exactFenceReader=nullptr; expected=Status::InvalidObservation; }
        if(mode==5) { d.setFence(1,seq+1); expected=Status::InvalidObservation; }
        const auto packets=packetWrites.load(); CHECK(c.ackExact(seq)==expected);
        CHECK(c.exactRegistry.occupied()==1 && packetWrites==packets && !frees && !terminations);
    }
}
static void waitAndAck(unsigned mode) {
    ackReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; start(c,d);
    auto seq=submit(c); d.exactFenceReader=sample; Pause p; Status waited=Status::Invalid;
    std::thread t([&] { testTicks=10000000; eventHook=[&](const char *name) {
        if(std::strcmp(name,"sleep")==0 && sleepCalls==1) p.arrive(); };
        waited=c.waitExact(seq,2000000); eventHook={}; });
    p.wait(); CHECK(c.exactClientCallbacks.active()==1);
    if(mode==0) d.setFence(1,seq);
    if(mode==1) c.clientClose();
    if(mode==2) { IOLockLock(d.gpuLock); d.invalidateExactQueues(); IOLockUnlock(d.gpuLock); }
    if(mode==3) d.stop(nullptr);
    auto acknowledged=c.ackExact(seq);
    CHECK(acknowledged==(mode==0 ? Status::Busy : mode==1 ? Status::Closed : Status::Lost));
    CHECK(c.exactRegistry.occupied()==1 && !frees && !terminations);
    p.release(); t.join();
    CHECK(waited==(mode==0 ? Status::Complete : mode==1 ? Status::Closed : Status::Lost));
    if(mode==0) CHECK(c.ackExact(seq)==Status::Ok && c.exactRegistry.occupied()==0);
    CHECK(c.exactClientCallbacks.active()==0);
}
static void twoWaiters() {
    ackReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; start(c,d);
    auto seq=submit(c); d.exactFenceReader=sample; Pause a,b; Status first=Status::Invalid,second=Status::Invalid;
    auto wait=[&](Pause &p,Status &result) { testTicks=10000000; bool paused=false;
        eventHook=[&](const char *name) { if(std::strcmp(name,"sleep")==0 && !paused) { paused=true; p.arrive(); } };
        result=c.waitExact(seq,2000000); eventHook={}; };
    std::thread t1([&] { wait(a,first); }); a.wait();
    std::thread t2([&] { wait(b,second); }); b.wait();
    CHECK(c.exactClientCallbacks.active()==2); d.setFence(1,seq);
    CHECK(c.ackExact(seq)==Status::Busy);
    a.release(); t1.join(); CHECK(first==Status::Complete);
    CHECK(c.ackExact(seq)==Status::Busy); // second waiter still owns its ticket
    b.release(); t2.join(); CHECK(second==Status::Complete);
    CHECK(c.ackExact(seq)==Status::Ok && c.exactRegistry.occupied()==0);
    CHECK(!frees && !terminations && c.exactClientCallbacks.active()==0);
}
static void terminalWaitsUnpin() {
    for(unsigned mode=0;mode<4;++mode) {
        ackReset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d); auto seq=submit(c);
        auto owned=ticket(c.exactRegistry,seq); d.exactFenceReader=sample;
        Status expected=Status::TimedOut;
        if(mode==1) { d.setFence(1,seq); expected=Status::Complete; }
        if(mode==2) { d.exactFenceReader=nullptr; expected=Status::InvalidObservation; }
        if(mode==3) { d.setFence(1,seq+1); expected=Status::InvalidObservation; }
        unsigned locks=0;
        eventHook=[&](const char *name) { if(std::strcmp(name,"client-lock-pointer")==0) ++locks; };
        CHECK(c.waitExact(seq,0)==expected && sleepCalls==0); eventHook={};
        CHECK(locks==3); // ticket admission, observation, serialized unpin
        // A fresh good observation permits receipt forget: no hidden wait pin remains.
        d.exactFenceReader=sample; d.setFence(1,seq);
        CHECK(c.ackExact(seq)==Status::Ok);
        CHECK(c.exactRegistry.unpinWait(owned)==Status::Unknown);
    }
}
static void pinBoundaries() {
    ackReset(); Registry r(17); Ticket owned;
    CHECK(r.reserve(owned)==Status::Ok && r.pinWait(owned)==Status::Unsubmitted);
    CHECK(r.publish(owned,{100,1,0})==Status::Ok);
    Ticket foreign=owned; ++foreign.owner;
    CHECK(r.pinWait(foreign)==Status::Unknown && r.unpinWait(foreign)==Status::Unknown);
    CHECK(r.unpinWait(owned)==Status::Invalid);
    for(unsigned i=0;i<UINT16_MAX;++i) CHECK(r.pinWait(owned)==Status::Ok);
    CHECK(r.pinWait(owned)==Status::Exhausted);
    QueueObservation observations[2]{}; observations[0]={1,100,100,true,false};
    CHECK(r.observe(owned,true,observations)==Status::Complete && r.forget(owned)==Status::Busy);
    for(unsigned i=0;i<UINT16_MAX;++i) CHECK(r.unpinWait(owned)==Status::Ok);
    CHECK(r.unpinWait(owned)==Status::Invalid && r.forget(owned)==Status::Ok);
    CHECK(r.pinWait(owned)==Status::Unknown && r.unpinWait(owned)==Status::Unknown);
    Ticket next; CHECK(r.reserve(next)==Status::Ok && r.publish(next,{101,1,0})==Status::Ok);
    CHECK(next.slot==owned.slot && next.serial!=owned.serial && r.pinWait(next)==Status::Ok);
    CHECK(r.unpinWait(owned)==Status::Unknown); // old waiter cannot decrement new receipt
    r.close(); CHECK(r.pinWait(next)==Status::Closed && r.unpinWait(next)==Status::Ok);
    CHECK(r.unpinWait(next)==Status::Invalid && r.forget(next)==Status::Closed);
}
int main() {
    binding_regressions(); wait_regressions(); const auto inherited=checks.load();
    const auto baselineGroups=groups,baselineThreads=threaded;
    metadataOnly(); sustainedReuse(); capacityAndRecovery(); invalidAndLost();
    for(unsigned i=0;i<4;++i) waitAndAck(i);
    twoWaiters(); terminalWaitsUnpin(); pinBoundaries();
    CHECK(!clientHeld && !gpuHeld && !eventHook);
    std::printf("PASS staged exact receipt acknowledgement: %llu additional checks; %u additional groups; %u additional threaded scenarios; inherited binding passed; GPU_executed=false\n",
                static_cast<unsigned long long>(checks.load()-inherited),groups-baselineGroups,threaded-baselineThreads);
}
