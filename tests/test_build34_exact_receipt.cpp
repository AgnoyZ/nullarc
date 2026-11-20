// SPDX-License-Identifier: MIT
// Actual staged externalMethod, complete-token helpers, submit/wait/ACK methods;
// C byte peer and CPU objects only. No real user client or device is opened.
#include "receipt-ack-regressions-CPU-only.h"
#include "build34_exact_receipt_wire.h"
extern "C" void phx34_receipt_encode(uint8_t *,uint64_t,uint64_t,uint64_t,uint64_t,uint32_t,uint32_t,uint64_t);
extern "C" bool phx34_receipt_reply(const uint8_t *,const uint8_t *,uint32_t);

// PHX34_RECEIPT_METHODS

struct Wire {
    uint8_t input[66],output[66];
    IOExternalMethodArguments a;
    Wire(IOAccelPhxNativeClient &c,uint64_t seq,bool ack=false,uint64_t timeout=0) {
        std::memset(input,0x5a,sizeof input); std::memset(output,0xa5,sizeof output);
        const Ticket t=ticket(c.exactRegistry,seq); Receipt r;
        CHECK(c.exactRegistry.inspect(t,r)==Status::Ok);
        phx34_receipt_encode(input+1,t.owner,t.serial,r.sequence,r.generation,t.slot,r.queue,timeout);
        a.version=kIOExternalMethodArgumentsCurrentVersion;
        a.selector=ack ? PHX34_R3_SEL_ACK_RECEIPT : PHX34_R3_SEL_WAIT_RECEIPT;
        a.scalarOutputCount=0; a.structureInput=input+1; a.structureOutput=output+1;
        a.structureInputSize=a.structureOutputSize=64;
    }
    phx34_r3_request request() const { phx34_r3_request r; std::memcpy(&r,input+1,64); return r; }
    void request(const phx34_r3_request &r) { std::memcpy(input+1,&r,64); }
    int call(IOAccelPhxNativeClient &c) { return c.externalMethod(a.selector,&a,nullptr,nullptr,nullptr); }
    void unchanged() const { for(auto b:output) CHECK(b==0xa5); }
    void reply(uint32_t status) const {
        CHECK(output[0]==0xa5 && output[65]==0xa5 && input[0]==0x5a && input[65]==0x5a);
        CHECK(phx34_receipt_reply(output+1,input+1,status));
    }
};
static void wireStart(IOAccelPhxNativeClient &c,PhxBringup &d) {
    start(c,d); c.hello=true; d.exactFenceReader=sample;
}
static void basicWire() {
    ackReset(); PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d);
    const auto compute=submit(c,false),gfx=submit(c); Wire pending(c,compute),ready(c,gfx),ack(c,gfx,true);
    CHECK(pending.call(c)==kIOReturnSuccess); pending.reply(PHX34_R3_REPLY_PENDING);
    CHECK(ack.call(c)==kIOReturnBusy); ack.unchanged();
    d.setFence(1,gfx); CHECK(ready.call(c)==kIOReturnSuccess); ready.reply(PHX34_R3_REPLY_COMPLETE);
    CHECK(d.gpuRetired()==99 && c.exactRegistry.occupied()==2);
    CHECK(ack.call(c)==kIOReturnSuccess); ack.reply(PHX34_R3_REPLY_ACKED);
    Wire old=ready; old.a.structureInput=old.input+1; old.a.structureOutput=old.output+1;
    std::memset(old.output,0xa5,sizeof old.output);
    CHECK(old.call(c)==kIOReturnNotFound); old.unchanged();
    CHECK(c.exactRegistry.occupied()==1 && c.queryExact(compute)==Status::Pending);
    CHECK(!frees && !terminations && c.retained==1 && d.retained==1);
    // In-place unaligned wire data is safe: the input was copied before output.
    Wire overlap(c,compute); d.setFence(0,compute);
    uint8_t original[64]; std::memcpy(original,overlap.input+1,64);
    overlap.a.structureOutput=overlap.input+1;
    CHECK(overlap.call(c)==kIOReturnSuccess);
    CHECK(phx34_receipt_reply(overlap.input+1,original,PHX34_R3_REPLY_COMPLETE));
    CHECK(overlap.input[0]==0x5a && overlap.input[65]==0x5a);
}
static void wrongTokens() {
    for(unsigned which=0;which<6;which++) for(bool ack:{false,true}) {
        ackReset(); PhxBringup d; IOAccelPhxNativeClient c,other; wireStart(c,d); wireStart(other,d);
        const auto seq=submit(c); (void)submit(other); d.setFence(1,seq);
        Wire wire(c,seq,ack); auto request=wire.request();
        if(which==0) request.owner++;
        if(which==1) request.serial++;
        if(which==2) request.sequence++;
        if(which==3) request.generation++;
        if(which==4) request.slot=(request.slot+1)%64;
        if(which==5) request.queue^=1;
        wire.request(request); const auto samples=sampleCalls.load();
        CHECK(wire.call(c)==kIOReturnNotFound); wire.unchanged();
        CHECK(c.exactRegistry.occupied()==1 && sampleCalls==samples && !sleepCalls);
    }
    ackReset(); PhxBringup d; IOAccelPhxNativeClient c,other; wireStart(c,d); wireStart(other,d);
    auto seq=submit(c); Wire foreign(c,seq); const auto before=sampleCalls.load();
    CHECK(foreign.call(other)==kIOReturnNotFound); foreign.unchanged(); CHECK(sampleCalls==before);
}
static void wideValues() {
    ackReset(); PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d);
    d.gSeq=0x12345678fffffff0ull; d.exactQueueGeneration[1]=0x1122334455667788ull;
    const auto seq=submit(c); CHECK(seq==0x12345678fffffff1ull);
    Wire wire(c,seq),ack(c,seq,true); d.setFence(1,seq);
    CHECK(wire.request().generation==0x1122334455667788ull);
    CHECK(wire.call(c)==kIOReturnSuccess); wire.reply(PHX34_R3_REPLY_COMPLETE);
    CHECK(ack.call(c)==kIOReturnSuccess); ack.reply(PHX34_R3_REPLY_ACKED);
}
static void staleReuse() {
    ackReset(); PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d);
    for(unsigned i=0;i<1024;i++) {
        const auto seq=submit(c,i%2); Wire old(c,seq),ack(c,seq,true);
        d.setFence(i%2 ? 1 : 0,seq); CHECK(ack.call(c)==kIOReturnSuccess); ack.reply(PHX34_R3_REPLY_ACKED);
        CHECK(old.call(c)==kIOReturnNotFound); old.unchanged();
        const auto next=submit(c,i%2); Wire current(c,next),release(c,next,true);
        auto request=old.request(),newRequest=current.request();
        CHECK(request.slot==newRequest.slot && request.serial!=newRequest.serial);
        request.sequence=newRequest.sequence; request.generation=newRequest.generation; request.queue=newRequest.queue;
        old.request(request); CHECK(old.call(c)==kIOReturnNotFound); old.unchanged();
        request=newRequest; request.sequence=seq; old.request(request);
        CHECK(old.call(c)==kIOReturnNotFound); old.unchanged();
        d.setFence(i%2 ? 1 : 0,next); CHECK(release.call(c)==kIOReturnSuccess);
        CHECK(c.exactRegistry.occupied()==0);
    }
}
static void malformed() {
    for(unsigned which=0;which<20;which++) {
        ackReset(); PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d); auto seq=submit(c);
        Wire wire(c,seq); auto r=wire.request();
        if(which==0) r.version++;
        if(which==1) r.size--;
        if(which==2) r.reserved=1;
        if(which==3) r.owner=0;
        if(which==4) r.owner=UINT64_MAX;
        if(which==5) r.serial=0;
        if(which==6) r.serial=UINT64_MAX;
        if(which==7) r.sequence=0;
        if(which==8) r.sequence=UINT64_MAX;
        if(which==9) r.generation=0;
        if(which==10) r.generation=UINT64_MAX;
        if(which==11) r.slot=64;
        if(which==12) r.queue=2;
        if(which==13) r.timeout_ns=PHXN_WAIT_CAP_NS+1;
        if(which==14) { wire.a.selector=PHX34_R3_SEL_ACK_RECEIPT; r.timeout_ns=1; }
        if(which==15) wire.a.version++;
        if(which==16) wire.a.scalarInputCount=1;
        if(which==17) wire.a.scalarOutputCount=1;
        if(which==18) wire.a.structureInput=nullptr;
        if(which==19) wire.a.structureOutput=nullptr;
        wire.request(r); const auto samples=sampleCalls.load();
        CHECK(wire.call(c)==kIOReturnBadArgument); wire.unchanged();
        CHECK(sampleCalls==samples && !sleepCalls && c.exactRegistry.occupied()==1);
    }
    for(unsigned which=0;which<8;which++) {
        ackReset(); PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d); auto seq=submit(c);
        Wire wire(c,seq);
        if(which==0) wire.a.structureInputDescriptor=&c;
        if(which==1) wire.a.structureOutputDescriptor=&c;
        if(which==2) wire.a.structureOutputDescriptorSize=64;
        if(which==3) wire.a.structureVariableOutputData=&c;
        if(which==4) wire.a.asyncWakePort=1;
        if(which==5) wire.a.asyncReference=&c;
        if(which==6) wire.a.asyncReferenceCount=1;
        if(which==7) CHECK(c.doExactReceipt(PHX34_R3_SEL_ACK_RECEIPT,&wire.a)==kIOReturnBadArgument);
        if(which!=7) CHECK(wire.call(c)==kIOReturnBadArgument);
        wire.unchanged(); CHECK(!sampleCalls && !sleepCalls);
    }
    for(unsigned size=0;size<=130;size++) if(size!=64) for(bool output:{false,true}) {
        ackReset(); PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d); auto seq=submit(c);
        Wire wire(c,seq); if(output) wire.a.structureOutputSize=size; else wire.a.structureInputSize=size;
        CHECK(wire.call(c)==kIOReturnBadArgument); wire.unchanged(); CHECK(!sampleCalls);
    }
}
static void lostAndUnadmitted() {
    for(unsigned mode=0;mode<8;mode++) {
        ackReset(); PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d); auto seq=submit(c); Wire wire(c,seq);
        if(mode==0) c.hello=false;
        if(mode==1) c.exactClientPinned=false;
        if(mode==2) { IOLockLock(d.gpuLock); d.invalidateExactQueues(); IOLockUnlock(d.gpuLock); }
        if(mode==3) d.exactFenceReader=nullptr;
        if(mode==4) c.clientClose();
        if(mode==5) d.stop(nullptr);
        if(mode==6) c.owner=nullptr;
        if(mode==7) c.exactOwnership=nullptr;
        CHECK(wire.call(c)==kIOReturnNotReady); wire.unchanged();
        CHECK(c.exactRegistry.occupied()==1 && !frees && !terminations);
    }
    ackReset(); PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d); auto seq=submit(c); Wire wire(c,seq);
    IOAccelPhxNativeClient legacy; legacy.owner=&d; legacy.hello=true;
    CHECK(wire.call(legacy)==kIOReturnNotReady); wire.unchanged(); CHECK(!sampleCalls);
    CHECK(c.doExactReceipt(PHX34_R3_SEL_WAIT_RECEIPT,nullptr)==kIOReturnBadArgument);
    CHECK(c.doExactReceipt(66,&wire.a)==kIOReturnBadArgument);
}
static void sleepingWire(unsigned mode) {
    ackReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d);
    const auto compute=submit(c,false),gfx=submit(c); Wire wire(c,gfx,false,2000000),ack(c,gfx,true);
    uint8_t original[64]; std::memcpy(original,wire.input+1,64);
    Pause pause; int result=-1;
    std::thread t([&] { testTicks=10000000; bool paused=false;
        eventHook=[&](const char *name) { if(!paused && std::strcmp(name,"sleep")==0) { paused=true; pause.arrive(); } };
        result=wire.call(c); eventHook={}; });
    pause.wait();
    if(mode==0) {
        auto request=wire.request(); request.sequence=compute; wire.request(request);
        d.setFence(1,gfx); CHECK(ack.call(c)==kIOReturnBusy); ack.unchanged();
    }
    if(mode==1) c.clientClose();
    if(mode==2) d.stop(nullptr);
    pause.release(); t.join();
    if(mode==0) {
        CHECK(result==kIOReturnSuccess && phx34_receipt_reply(wire.output+1,original,PHX34_R3_REPLY_COMPLETE));
        CHECK(ack.call(c)==kIOReturnSuccess && c.exactRegistry.occupied()==1 && d.gpuRetired()==99);
    } else { CHECK(result==kIOReturnNotReady); wire.unchanged(); }
    CHECK(c.exactClientCallbacks.active()==0 && !frees && !terminations);
}
static void closureAfterWait(bool provider) {
    ackReset(); PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d); auto seq=submit(c); d.setFence(1,seq);
    Wire wire(c,seq); unsigned unlocks=0;
    eventHook=[&](const char *name) { if(std::strcmp(name,"client-unlocked")==0 && ++unlocks==4) {
        if(provider) d.stop(nullptr); else c.clientClose();
    } };
    CHECK(wire.call(c)==kIOReturnNotReady); eventHook={}; wire.unchanged();
    CHECK(unlocks==4 && c.exactRegistry.occupied()==1 && !frees && !terminations);
}
static void queuedWireLock(bool complete) {
    ackReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; wireStart(c,d);
    auto seq=submit(c); Wire wire(c,seq,false,1000000); Pause pause; int result=-1;
    IOLockLock(c.lock);
    std::thread t([&] { testTicks=10000000; bool paused=false;
        eventHook=[&](const char *name) {
            if(!paused && std::strcmp(name,"client-lock-pointer")==0) {
                paused=true; pause.arrive(); testTicks+=9000000; // outer queue consumed the whole budget
            }
        };
        result=wire.call(c); eventHook={};
    });
    pause.wait(); if(complete) d.setFence(1,seq); IOLockUnlock(c.lock); pause.release(); t.join();
    CHECK(result==kIOReturnSuccess && sleepCalls==0);
    wire.reply(complete ? PHX34_R3_REPLY_COMPLETE : PHX34_R3_REPLY_PENDING);
    CHECK(c.exactRegistry.occupied()==1 && !frees && !terminations);
}
int main() {
    ack_regressions(); const auto inherited=checks.load(); const auto baselineGroups=groups,baselineThreads=threaded;
    basicWire(); wrongTokens(); wideValues(); staleReuse(); malformed(); lostAndUnadmitted();
    for(unsigned mode=0;mode<3;mode++) sleepingWire(mode);
    closureAfterWait(false); closureAfterWait(true);
    queuedWireLock(false); queuedWireLock(true);
    CHECK(!clientHeld && !gpuHeld && !eventHook);
    std::printf("PASS staged complete-token receipt wire: %llu additional checks; %u groups; %u threaded scenarios; C peer and inherited ACK regressions; GPU_executed=false\n",
                static_cast<unsigned long long>(checks.load()-inherited),groups-baselineGroups,threaded-baselineThreads);
}
