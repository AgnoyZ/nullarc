// SPDX-License-Identifier: MIT
// Actual staged submit/dispatch/wait/ACK and prior binding methods; CPU only.
#include "submit-binding-CPU-only.h"
#include "build34_exact_submit_wire.h"
extern "C" void phx34_submit_encode(uint8_t *,uint64_t,unsigned,bool);
extern "C" bool phx34_submit_reply(const uint8_t *,uint64_t,uint64_t,uint64_t,unsigned);
extern "C" void phx34_receipt_encode(uint8_t *,uint64_t,uint64_t,uint64_t,uint64_t,uint32_t,uint32_t,uint64_t);
extern "C" bool phx34_receipt_reply(const uint8_t *,const uint8_t *,uint32_t);
// PHX34_SUBMIT_RECEIPT_METHODS

static void setup(IOAccelPhxNativeClient &c,PhxBringup &d) {
    start(c,d); c.hello=true; d.exactFenceReader=sample;
}
static uint64_t ownerID(IOAccelPhxNativeClient &c) {
    Ticket t; CHECK(c.exactRegistry.reserve(t)==Status::Ok);
    CHECK(c.exactRegistry.cancel(t)==Status::Ok); return t.owner;
}
struct SubmitWire {
    uint8_t input[2114],output[66]; IOExternalMethodArguments a;
    SubmitWire(IOAccelPhxNativeClient &c,unsigned count=1,bool gfx=true) {
        std::memset(input,0x5a,sizeof input); std::memset(output,0xa5,sizeof output);
        phx34_submit_encode(input+1,ownerID(c),count,gfx);
        a.selector=PHX34_R3_SEL_SUBMIT_RECEIPT; a.scalarOutputCount=0;
        a.structureInput=input+1; a.structureInputSize=2112;
        a.structureOutput=output+1; a.structureOutputSize=64;
    }
    phx34_r3_submit_request request() const { phx34_r3_submit_request r; std::memcpy(&r,input+1,sizeof r); return r; }
    void request(const phx34_r3_submit_request &r) { std::memcpy(input+1,&r,sizeof r); }
    int call(IOAccelPhxNativeClient &c) { return c.externalMethod(PHX34_R3_SEL_SUBMIT_RECEIPT,&a,nullptr,nullptr,nullptr); }
    void unchanged() const { for(auto b:output) CHECK(b==0xa5); }
    phx34_r3_reply result() const { phx34_r3_reply r; std::memcpy(&r,output+1,sizeof r); return r; }
    void verify(IOAccelPhxNativeClient &c,uint64_t seq,unsigned qi) const {
        const auto r=result();
        CHECK(output[0]==0xa5 && output[65]==0xa5 && input[0]==0x5a && input[2113]==0x5a);
        CHECK(phx34_submit_reply(output+1,request().owner,seq,c.owner->exactQueueGeneration[qi],qi));
        CHECK(c.exactRegistry.authenticate({r.owner,r.serial,r.slot},{r.sequence,r.generation,r.queue})==Status::Ok);
        CHECK(c.lastSeq==seq && c.emitted==seq);
    }
};
static int receiptCall(IOAccelPhxNativeClient &c,const phx34_r3_reply &r,bool ack,uint32_t expected) {
    uint8_t in[64],out[64]; std::memset(out,0xa5,64);
    phx34_receipt_encode(in,r.owner,r.serial,r.sequence,r.generation,r.slot,r.queue,0);
    IOExternalMethodArguments a; a.selector=ack ? PHX34_R3_SEL_ACK_RECEIPT : PHX34_R3_SEL_WAIT_RECEIPT;
    a.scalarOutputCount=0; a.structureInput=in; a.structureOutput=out; a.structureInputSize=a.structureOutputSize=64;
    const auto status=c.externalMethod(a.selector,&a,nullptr,nullptr,nullptr);
    if(status==kIOReturnSuccess) CHECK(phx34_receipt_reply(out,in,expected));
    else for(auto b:out) CHECK(b==0xa5);
    return status;
}
static void basic() {
    for(bool gfx:{false,true}) for(bool fallback:{false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d);
        unsigned qi=gfx ? 1 : 0; if(fallback) { d.gq[qi].ready=false; qi^=1; }
        SubmitWire w(c); auto request=w.request(); request.ibs[0].ip_type=gfx ? PHX_AMDGPU_HW_IP_GFX : PHX_AMDGPU_HW_IP_COMPUTE; w.request(request);
        d.gSeq=0x12345678fffffff0ull; d.exactQueueGeneration[qi]=0x2345678900000000ull;
        CHECK(w.call(c)==kIOReturnSuccess); const auto seq=d.gSeq; w.verify(c,seq,qi);
        const auto r=w.result(); CHECK(c.exactRegistry.occupied()==1 && packetWrites>0);
        CHECK(receiptCall(c,r,false,PHX34_R3_REPLY_PENDING)==kIOReturnSuccess);
        CHECK(receiptCall(c,r,true,0)==kIOReturnBusy);
        d.setFence(qi,seq);
        CHECK(receiptCall(c,r,false,PHX34_R3_REPLY_COMPLETE)==kIOReturnSuccess);
        CHECK(receiptCall(c,r,true,PHX34_R3_REPLY_ACKED)==kIOReturnSuccess);
        CHECK(receiptCall(c,r,false,0)==kIOReturnNotFound && !c.exactRegistry.occupied());
        CHECK(!frees && !terminations && c.retained==1 && d.retained==1);
    }
    // A newer GFX receipt completes independently of an earlier compute one.
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d);
    SubmitWire compute(c,1,false),gfx(c); CHECK(compute.call(c)==kIOReturnSuccess && gfx.call(c)==kIOReturnSuccess);
    d.setFence(1,gfx.result().sequence);
    CHECK(receiptCall(c,gfx.result(),false,PHX34_R3_REPLY_COMPLETE)==kIOReturnSuccess);
    CHECK(receiptCall(c,compute.result(),false,PHX34_R3_REPLY_PENDING)==kIOReturnSuccess && d.gpuRetired()==99);
}
static void batches() {
    for(unsigned n=1;n<=64;n++) for(bool gfx:{false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d); SubmitWire w(c,n,gfx);
        CHECK(w.call(c)==kIOReturnSuccess); w.verify(c,100,gfx ? 1 : 0);
        CHECK(d.gq[gfx ? 1 : 0].tail==1 && d.gq[gfx ? 0 : 1].tail==0 && c.exactRegistry.occupied()==1);
    }
    for(unsigned count:{2u,64u}) for(unsigned index:{0u,1u}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d); SubmitWire w(c,count);
        auto req=w.request(); req.ibs[index].ip_type=PHX_AMDGPU_HW_IP_COMPUTE; w.request(req);
        CHECK(w.call(c)==kIOReturnUnsupported); w.unchanged();
        CHECK(!packetWrites && !c.exactRegistry.occupied() && d.gSeq==99 && !c.vmid);
    }
}
static void malformed() {
    for(unsigned which=0;which<46;which++) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d); SubmitWire w(c); auto req=w.request();
        int expected=kIOReturnBadArgument;
        switch(which) {
        case 0: w.a.selector++; break;
        case 1: w.a.version++; break;
        case 2: w.a.scalarInputCount=1; break;
        case 3: w.a.scalarOutputCount=1; break;
        case 4: w.a.structureInput=nullptr; break;
        case 5: w.a.structureOutput=nullptr; break;
        case 6: w.a.structureInputDescriptor=&c; break;
        case 7: w.a.structureOutputDescriptor=&c; break;
        case 8: w.a.structureOutputDescriptorSize=1; break;
        case 9: w.a.structureVariableOutputData=&c; break;
        case 10: w.a.asyncWakePort=1; break;
        case 11: w.a.asyncReference=&c; break;
        case 12: w.a.asyncReferenceCount=1; break;
        case 13: req.version++; break;
        case 14: req.size--; break;
        case 15: req.owner=0; break;
        case 16: req.owner=UINT64_MAX; break;
        case 17: req.owner++; expected=kIOReturnNotFound; break;
        case 18: req.reserved[0]=1; break;
        case 19: req.reserved[1]=1; break;
        case 20: req.submit.abi++; break;
        case 21: req.submit.ctx_id=0; expected=kIOReturnNotFound; break;
        case 22: req.submit.num_ibs=0; break;
        case 23: req.submit.num_ibs=65; break;
        case 24: req.submit.reserved=1; break;
        case 25: req.submit.flags=PHXN_CS_HAS_FENCE; expected=kIOReturnUnsupported; break;
        case 26: req.submit.flags=2; break;
        case 27: req.submit.fence_handle=1; break;
        case 28: req.submit.fence_offset=8; break;
        case 29: req.ibs[0]._pad=1; break;
        case 30: req.ibs[0].ip_type=2; break;
        case 31: req.ibs[0].ip_instance=1; break;
        case 32: req.ibs[0].ring=1; break;
        case 33: req.ibs[0].ib_bytes=0; break;
        case 34: req.ibs[0].ib_bytes=1; break;
        case 35: req.ibs[0].va_start=1; break;
        case 36: req.ibs[0].flags=PHX_AMDGPU_IB_FLAGS_SECURE; expected=kIOReturnUnsupported; break;
        case 37: req.ibs[0].flags=0x80000000; break;
        case 38: req.ibs[1].va_start=1; break;
        case 39: req.ibs[63].ring=1; break;
        case 40: c.hello=false; expected=kIOReturnNotReady; break;
        case 41: c.exactClientCallbacks.close(); expected=kIOReturnNotReady; break;
        case 42: d.stop(nullptr); expected=kIOReturnNotReady; break;
        case 43: d.gq[0].ready=d.gq[1].ready=false; expected=kIOReturnNotReady; break;
        case 44: c.vmidAvailable=false; expected=kIOReturnNoResources; break;
        case 45: d.deviceReady=false; expected=kIOReturnNotReady; break;
        }
        w.request(req); CHECK(w.call(c)==expected); w.unchanged();
        CHECK(!packetWrites && !c.exactRegistry.occupied() && d.gSeq==99 && !c.emitted);
    }
    for(unsigned n=0;n<=2113;n++) if(n!=2112) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d); SubmitWire w(c); w.a.structureInputSize=n;
        CHECK(w.call(c)==kIOReturnBadArgument); w.unchanged(); CHECK(!packetWrites && !c.exactRegistry.occupied());
    }
    for(unsigned n=0;n<=65;n++) if(n!=64) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d); SubmitWire w(c); w.a.structureOutputSize=n;
        CHECK(w.call(c)==kIOReturnBadArgument); w.unchanged(); CHECK(!packetWrites && !c.exactRegistry.occupied());
    }
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d);
    CHECK(c.doExactSubmit(nullptr)==kIOReturnBadArgument);
    IOAccelPhxNativeClient foreign; setup(foreign,d); SubmitWire wrong(c);
    CHECK(wrong.call(foreign)==kIOReturnNotFound); wrong.unchanged(); CHECK(!packetWrites);
    // A legacy client cannot request exact submission by guessing a valid owner.
    IOAccelPhxNativeClient legacy; CHECK(legacy.start(&d)); legacy.hello=true;
    CHECK(wrong.call(legacy)==kIOReturnNotReady); wrong.unchanged();
    CHECK(!legacy.exactOwnership && !legacy.retained && !packetWrites);
}
static void capacityAndReuse() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d);
    std::vector<phx34_r3_reply> held;
    const auto owner=ownerID(c);
    for(unsigned i=0;i<64;i++) {
        SubmitWire w(c); CHECK(w.call(c)==kIOReturnSuccess); auto r=w.result(); held.push_back(r); d.setFence(r.queue,r.sequence);
    }
    // Construct directly: the helper must not reserve while the table is full.
    uint8_t in[2112],out[64]; phx34_submit_encode(in,owner,1,true); std::memset(out,0xa5,64);
    IOExternalMethodArguments a; a.selector=PHX34_R3_SEL_SUBMIT_RECEIPT; a.scalarOutputCount=0;
    a.structureInput=in; a.structureInputSize=2112; a.structureOutput=out; a.structureOutputSize=64;
    const auto before=packetWrites.load(); CHECK(c.externalMethod(a.selector,&a,nullptr,nullptr,nullptr)==kIOReturnNoResources);
    for(auto b:out) CHECK(b==0xa5);
    CHECK(packetWrites==before && c.exactRegistry.occupied()==64);
    for(auto r:held) CHECK(receiptCall(c,r,true,PHX34_R3_REPLY_ACKED)==kIOReturnSuccess);
    CHECK(!c.exactRegistry.occupied());
    const auto stale=held[0]; SubmitWire next(c); CHECK(next.call(c)==kIOReturnSuccess);
    CHECK(next.result().slot==stale.slot && next.result().serial!=stale.serial);
    CHECK(receiptCall(c,stale,false,0)==kIOReturnNotFound);
}
static void overlap() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(c,d); SubmitWire w(c,64); const auto owner=w.request().owner;
    w.a.structureOutput=w.input+1; CHECK(w.call(c)==kIOReturnSuccess);
    CHECK(phx34_submit_reply(w.input+1,owner,100,22,1)); CHECK(w.input[0]==0x5a && w.input[2113]==0x5a);
}
static void inputCopied() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(c,d); SubmitWire w(c); Pause p; int result=-1;
    std::thread worker([&] { bool paused=false;
        eventHook=[&](const char *name) { if(!paused && !std::strcmp(name,"client-lock-pointer")) { paused=true; p.arrive(); } };
        result=w.call(c); eventHook={}; });
    p.wait(); auto req=w.request(); req.ibs[0].ip_type=PHX_AMDGPU_HW_IP_COMPUTE; req.submit.ctx_id=0; w.request(req);
    p.release(); worker.join(); CHECK(result==kIOReturnSuccess && w.result().queue==1 && d.gq[1].tail==1 && !d.gq[0].tail);
}
static void closing(unsigned phase,bool service) {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(c,d); SubmitWire w(c); Pause p; int result=-1;
    std::thread worker([&] { bool paused=false; eventHook=[&](const char *name) {
            bool hit=phase==0 ? !std::strcmp(name,"client-lock-pointer") :
                     phase==1 ? !std::strcmp(name,"packet") : !std::strcmp(name,"client-unlocked");
            if(hit && !paused) { paused=true; p.arrive(); } };
        result=w.call(c); eventHook={}; });
    p.wait(); if(service) d.stop(nullptr); else CHECK(c.clientClose()==kIOReturnSuccess);
    p.release(); worker.join(); CHECK(result==kIOReturnNotReady); w.unchanged();
    CHECK(c.exactRegistry.occupied()==(phase==0 ? 0u : 1u));
    CHECK((packetWrites>0)==(phase>0) && !frees && !terminations && c.retained==1);
}
int main() {
    binding_regressions(); const auto previous=checks.load(); const auto oldgroups=groups,oldthreads=threaded;
    basic(); batches(); malformed(); capacityAndReuse(); overlap(); inputCopied();
    for(unsigned phase=0;phase<3;phase++) for(bool service:{false,true}) closing(phase,service);
    CHECK(!clientHeld && !gpuHeld);
    std::printf("PASS staged exact submit receipt: %llu additional checks; %u groups; %u threaded scenarios; inherited binding passed; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()-previous),groups-oldgroups,threaded-oldthreads);
}
