// SPDX-License-Identifier: MIT
// Actual native client bodies; finite CPU framework/GPU-backend doubles only.
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include "PhxNativeABI.h"
#include "build34_exact_callbacks.h"
#include "build34_exact_ownership.h"
using namespace phx34_exact;
using IOReturn=int;
using UInt32=uint32_t;
using IOOptionBits=uint32_t;
struct IOExternalMethodDispatch {};
struct OSObject {};
static std::atomic<uint64_t> checks{0};
static unsigned groups;
#ifndef PHX34_CLIENT_LEGACY_COUNTEREXAMPLE
static unsigned threaded;
#endif
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x); std::abort(); } } while(0)
enum { kIOReturnSuccess,kIOReturnNotReady,kIOReturnBadArgument,kIOReturnBusy,kIOReturnNoResources,
       kIOReturnNotFound,kIOReturnUnsupported,kIOReturnNoMemory };
static constexpr int kMaxMaps=4;
static constexpr uint32_t kFirstUserVmid=8;
static constexpr uint64_t kVaMask=(1ull<<48)-1,sentinel=0xabcdef;
static thread_local unsigned clientHeld;
static thread_local uint64_t ticks;
static thread_local std::function<void(const char *)> eventHook;
static std::atomic<unsigned> lockTouches{0},mdRetains{0},mdReleases{0},mdCompletes{0},heapFrees{0};
static std::atomic<unsigned> sleeps{0},baseFrees{0},terminations{0},leafCalls{0},flushLines{0};
static bool baseStart=true;
static void event(const char *name) { if(eventHook) eventHook(name); }
struct Lock { std::mutex mutex; bool client=true; };
static void IOLockLock(Lock *p) {
    CHECK(p); ++lockTouches; if(p->client) event("client-lock-pointer"); p->mutex.lock();
    if(p->client) ++clientHeld;
}
static void IOLockUnlock(Lock *p) {
    CHECK(p); if(p->client) { CHECK(clientHeld); --clientHeld; } p->mutex.unlock();
}
static void IOLockFree(Lock *) { ++heapFrees; }
static void IOFree(void *,size_t) { ++heapFrees; }
static void IOSleep(unsigned ms) { CHECK(ms==1); ++sleeps; ticks+=1000000; }
static void IODelay(unsigned us) { ticks+=uint64_t(us)*1000; }
static uint64_t mach_absolute_time() { return ticks; }
static void absolutetime_to_nanoseconds(uint64_t value,uint64_t *out) { *out=value; }
static void flushLine(void *) { ++flushLines; }
static void IOLog(const char *,...) {}
static bool vaCanonical(uint64_t va) { return va>>47==0 || va>>47==0x1ffff; }
struct Memory {
    alignas(16) uint8_t bytes[8192]{};
    void retain() { ++mdRetains; }
    void release() { ++mdReleases; }
    void complete() { ++mdCompletes; }
    void *getBytesNoCopy() { return bytes; }
};
using IOMemoryDescriptor=Memory;
using IOBufferMemoryDescriptor=Memory;
struct IOService {
    std::atomic<unsigned> retained{0};
    void retain() { ++retained; }
};
struct IOUserClient : IOService {
    bool start(IOService *) { return baseStart; }
    void free() { ++baseFrees; }
    void terminate() { ++terminations; }
};
#define OSDynamicCast(type,p) static_cast<type *>(p)
struct IOExternalMethodArguments {
    unsigned scalarInputCount=0,scalarOutputCount=0;
    size_t structureInputSize=0,structureOutputSize=0;
    const void *structureInput=nullptr;
    void *structureOutput=nullptr,*structureInputDescriptor=nullptr,*structureOutputDescriptor=nullptr;
    uint64_t scalarInput[6]{},scalarOutput[6]{sentinel,sentinel,sentinel,sentinel,sentinel,sentinel};
};
struct PhxBringup : IOService {
    Lock gpuMutex;
    Lock *gpuLock=&gpuMutex;
    static constexpr uint32_t kPtChunks=2,kPtChunkPages=1;
    struct VmCtx { Memory *chunk[kPtChunks]{}; uint32_t used=1,hw=8; bool busy=true; } vm[1];
    struct { uint32_t ctx=1; } hwv[8];
    Memory pageTable;
    std::atomic<uint64_t> retired{0},nextSeq{99};
    std::atomic<unsigned> vmidCalls{0},sessionReleases{0},unmaps{0},submits{0};
    bool gpuIsReady=true,rejectSubmit=false,vmidAvailable=true;
    PhxBringup() { gpuMutex.client=false; vm[0].chunk[0]=&pageTable; std::memset(pageTable.bytes,0x5a,4096); }
    bool claimSession() { return true; }
    void releaseSession() { ++sessionReleases; }
    bool gpuReady() const { return gpuIsReady; }
    bool debugEnabled() const { return false; }
    uint32_t vmidAlloc() { return vmidAvailable ? 1 : 0; }
    VmCtx *vmCtx(uint32_t handle) { ++vmidCalls; return handle==1 && vm[0].busy ? &vm[0] : nullptr; }
    uint64_t gpuRetired() { event("wait-backend"); return retired.load(); }
    void vmFlushTlb(uint32_t) {}
    IOReturn vmMap(uint32_t,uint64_t,Memory *,uint64_t,uint64_t) { return kIOReturnSuccess; }
    IOReturn vmUnmap(uint32_t,uint64_t,uint64_t) { ++unmaps; return kIOReturnSuccess; }
    void vmidFree(uint32_t,uint64_t);
    IOReturn gpuSubmit(uint32_t,bool,const uint64_t *,const uint32_t *,uint32_t,uint64_t *seq,
                      Registry *registry=nullptr,Ticket ticket={}) {
        CHECK(clientHeld); ++submits; event("GPU-admission");
        if(rejectSubmit) return kIOReturnBusy;
        const auto value=++nextSeq;
        if(registry && registry->publish(ticket,{value,11,0})!=Status::Ok) return kIOReturnNotReady;
        *seq=value; return kIOReturnSuccess;
    }
};
struct IOAccelPhxNativeClient : IOUserClient {
    struct Bo { Memory *md; uint64_t size; uint32_t domain,bits; uint8_t *kva; bool host; };
    struct Map { bool used; uint32_t handle; uint64_t va,size,off; uint32_t flags; };
    std::unique_ptr<Bo[]> boStorage{new Bo[PHXN_MAX_BOS]{}};
    Bo *bos=boStorage.get();
    Map mapStorage[kMaxMaps]{};
    Map *maps=mapStorage;
    Lock clientMutex;
    Lock *lock=&clientMutex;
    PhxBringup *owner=nullptr;
    Registry *exactOwnership=nullptr;
    CallbackGate<> exactClientCallbacks;
    bool exactClientPinned=false,exactResourcesExposed=false;
    bool hello=true,sessionClaimed=false;
    uint32_t vmid=1;
    uint64_t lastSeq=0,emitted=0,visUsed=4096,hiUsed=0,gttUsed=0,hostUsed=4096;
    uint32_t pendFenceHandle=0,pendFenceOffset=0;
    uint64_t pendFenceSeq=0;
    bool ctx[PHXN_MAX_CTX+1]{};
    Memory privateMD,hostMD;
    IOAccelPhxNativeClient() {
        bos[1]={&privateMD,4096,0,0,privateMD.bytes,false};
        bos[2]={&hostMD,4096,2,0,nullptr,true};
        maps[0]={true,1,0x10000,4096,0,PHX_AMDGPU_VM_PAGE_EXECUTABLE};
        maps[1]={true,2,0x20000,4096,0,0}; ctx[1]=true;
    }
    bool ensureVmid() { return vmid || (vmid=owner->vmidAlloc())!=0; }
    bool ibCovered(uint64_t,uint64_t) { CHECK(clientHeld); return true; }
    void flushBos() { CHECK(clientHeld); }
    bool start(IOService *);
    IOReturn clientClose();
    void free();
    void freeAll();
    void boRelease(Bo &);
    Bo *findBo(uint32_t);
    IOReturn doSubmit(IOExternalMethodArguments *);
    IOReturn doBoFree(IOExternalMethodArguments *);
    IOReturn doGemVa(IOExternalMethodArguments *);
    IOReturn doWaitSeq(IOExternalMethodArguments *);
    IOReturn externalMethod(uint32_t,IOExternalMethodArguments *,IOExternalMethodDispatch *,OSObject *,void *);
    IOReturn clientMemoryForType(UInt32,IOOptionBits *,Memory **);
    // PHX34_CLIENT_STUBS
};

// PHX34_CLIENT_METHODS

#ifndef PHX34_CLIENT_LEGACY_COUNTEREXAMPLE
struct Pause {
    std::mutex mutex; std::condition_variable cv; bool reached=false,resume=false;
    void arrive() { std::unique_lock<std::mutex> l(mutex); reached=true; cv.notify_all();
        CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return resume;})); }
    void wait() { std::unique_lock<std::mutex> l(mutex);
        CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return reached;})); }
    void release() { std::lock_guard<std::mutex> l(mutex); resume=true; cv.notify_all(); }
};
#endif
static void reset() {
    CHECK(!clientHeld && !eventHook); ++groups; ticks=0; baseStart=true;
    lockTouches=mdRetains=mdReleases=mdCompletes=heapFrees=sleeps=baseFrees=terminations=leafCalls=flushLines=0;
}
#ifndef PHX34_CLIENT_LEGACY_COUNTEREXAMPLE
static IOReturn call(IOAccelPhxNativeClient &c,uint32_t selector,IOExternalMethodArguments &a) {
    return c.externalMethod(selector,&a,nullptr,nullptr,nullptr);
}
struct Request {
    phxn_cs_in h{}; phxn_cs_ib ib{}; IOExternalMethodArguments a;
    Request() {
        h.abi=PHXN_ABI_VERSION; h.ctx_id=1; h.num_ibs=1;
        ib.ip_type=PHX_AMDGPU_HW_IP_COMPUTE; ib.va_start=0x10000; ib.ib_bytes=64;
        a.scalarOutputCount=1; a.structureInput=&h; a.structureInputSize=sizeof h+sizeof ib;
        CHECK(reinterpret_cast<uint8_t *>(&ib)-reinterpret_cast<uint8_t *>(&h)==sizeof h);
    }
    IOReturn run(IOAccelPhxNativeClient &c) { return call(c,PHXN_SEL_SUBMIT,a); }
};
static IOExternalMethodArguments boFreeArgs(unsigned handle=1) {
    IOExternalMethodArguments a; a.scalarInputCount=1; a.scalarInput[0]=handle; return a;
}
static IOExternalMethodArguments unmapArgs(phxn_gem_va &v) {
    v={}; v.handle=1; v.va_address=0x10000; v.map_size=4096; v.operation=PHX_AMDGPU_VA_OP_UNMAP;
    IOExternalMethodArguments a; a.structureInput=&v; a.structureInputSize=sizeof v; return a;
}
static void intact(IOAccelPhxNativeClient &c,PhxBringup &owner) {
    CHECK(c.bos[1].md==&c.privateMD && c.bos[2].md==&c.hostMD && c.vmid==1 && c.sessionClaimed);
    CHECK(c.maps[0].used && c.maps[1].used && owner.vm[0].busy && owner.hwv[0].ctx==1);
    CHECK(owner.pageTable.bytes[0]==0x5a && owner.vmidCalls==0 && owner.sessionReleases==0 && owner.unmaps==0);
    CHECK(mdReleases==0 && mdCompletes==0 && heapFrees==0 && baseFrees==0 && terminations==0);
}
static void startExact(IOAccelPhxNativeClient &c,PhxBringup &owner,Registry &registry) {
    c.exactOwnership=&registry;
    CHECK(c.start(&owner) && c.exactClientPinned && c.retained==1 && owner.retained>=1);
    CHECK(!c.start(&owner) && c.retained==1);
}
#endif

#ifdef PHX34_CLIENT_LEGACY_COUNTEREXAMPLE
int main() {
    reset(); PhxBringup owner; IOAccelPhxNativeClient c;
    CHECK(c.start(&owner)); c.lastSeq=c.emitted=100;
    bool releasedBeforeWait=false;
    eventHook=[&](const char *name){if(!std::strcmp(name,"wait-backend")) releasedBeforeWait=mdReleases==2;};
    CHECK(c.clientClose()==kIOReturnSuccess); eventHook={};
    CHECK(releasedBeforeWait && sleeps==2000 && owner.retired==0);
    CHECK(mdReleases==2 && mdCompletes==1 && !owner.vm[0].busy && owner.pageTable.bytes[0]==0);
    reset(); PhxBringup other; IOAccelPhxNativeClient second;
    CHECK(second.start(&other)); second.lastSeq=100; second.free();
    CHECK(sleeps==2000 && other.retired==0 && mdReleases==2 && !other.vm[0].busy && baseFrees==1);
    std::printf("PASS actual legacy cleanup counterexamples: BOs released before close wait; timeout clears VM; free releases after timeout; GPU_executed=false\n");
}
#else
static void activationAndIdleClose() {
    reset(); PhxBringup owner; Registry registry(1); IOAccelPhxNativeClient c;
    c.exactOwnership=&registry;
    Request request; CHECK(request.run(c)==kIOReturnNotReady && owner.submits==0 && c.retained==0);
    baseStart=false; CHECK(!c.start(&owner) && !c.exactClientPinned && c.retained==0 && owner.retained==0);
    baseStart=true; CHECK(c.start(&owner) && c.exactClientPinned && c.retained==1 && owner.retained==1);
    c.freeAll(); intact(c,owner);
    CHECK(c.clientClose()==kIOReturnSuccess && c.exactClientCallbacks.drained());
    CHECK(c.clientClose()==kIOReturnSuccess && c.retained==1 && owner.retained==1);
    c.free(); intact(c,owner);
}
static void denied(IOAccelPhxNativeClient &c,PhxBringup &owner) {
    const auto touches=lockTouches.load(),leaves=leafCalls.load(),submissions=owner.submits.load(),retains=mdRetains.load();
    for(uint32_t selector:{PHXN_SEL_QUERYINFO,PHXN_SEL_WAITSEQ,PHXN_SEL_TOPOLOGY,PHXN_SEL_SURF_GPU_MARK}) {
        IOExternalMethodArguments a; a.scalarInputCount=3; a.scalarOutputCount=3;
        CHECK(call(c,selector,a)==kIOReturnNotReady && a.scalarOutput[0]==sentinel);
    }
    Request request; CHECK(request.run(c)==kIOReturnNotReady && request.a.scalarOutput[0]==sentinel);
    IOOptionBits options=123; Memory *memory=nullptr;
    CHECK(c.clientMemoryForType(1,&options,&memory)==kIOReturnNotReady && !memory && options==123);
    // Private doSubmit is also guarded; no nested/public dispatcher is needed
    // for this defensive callsite sensitivity check.
    IOLockLock(c.lock); CHECK(c.doSubmit(&request.a)==kIOReturnNotReady); IOLockUnlock(c.lock);
    CHECK(lockTouches==touches+1 && leafCalls==leaves && owner.submits==submissions && mdRetains==retains);
}
static void exposedResources() {
    for(unsigned mode=0;mode<5;++mode) {
        reset(); PhxBringup owner; Registry registry(10+mode); IOAccelPhxNativeClient c;
        startExact(c,owner,registry);
        owner.rejectSubmit=mode==1;
        if(mode==2) for(unsigned i=0;i<64;++i) { Ticket t; CHECK(registry.reserve(t)==Status::Ok); }
        Request request; const auto result=request.run(c);
        CHECK(result==(mode==1 ? kIOReturnBusy : mode==2 ? kIOReturnNoResources : kIOReturnSuccess));
        CHECK(c.exactResourcesExposed);
        if(mode==3) { Ticket t; CHECK(registry.lookup(100,t)==Status::Ok);
            QueueObservation q[2]={{11,100,100,true,false},{}};
            CHECK(registry.observe(t,true,q)==Status::Complete && registry.forget(t)==Status::Ok && registry.occupied()==0); }
        if(mode==4) owner.retired=100; // global readiness is not a release capability
        auto a=boFreeArgs(); CHECK(call(c,PHXN_SEL_BOFREE,a)==kIOReturnBusy);
        phxn_gem_va v; auto unmap=unmapArgs(v); CHECK(call(c,PHXN_SEL_GEMVA,unmap)==kIOReturnBusy);
        c.boRelease(c.bos[1]); c.boRelease(c.bos[2]); c.freeAll();
        CHECK(c.visUsed==4096 && c.hostUsed==4096); intact(c,owner);
        CHECK(c.clientClose()==kIOReturnSuccess); c.free(); denied(c,owner); intact(c,owner);
    }
}
enum Operation { SubmitOp,WaitOp,TopologyOp,SurfaceOp,LockedOp,MemoryOp };
static void duringClose(Operation operation) {
    reset(); PhxBringup owner; Registry registry(20+operation); IOAccelPhxNativeClient c;
    startExact(c,owner,registry); Pause pause; Request request; IOReturn result=-1;
    c.emitted=c.lastSeq=operation==WaitOp ? 100 : 0;
    IOExternalMethodArguments a; a.scalarInputCount=3; a.scalarOutputCount=3; a.scalarInput[0]=100;
    IOOptionBits options=55; Memory *memory=nullptr;
    const char *point=operation==SubmitOp ? "GPU-admission" : operation==WaitOp ? "wait-backend" :
                      operation==TopologyOp ? "doTopology" : operation==SurfaceOp ? "doSurfGpuMark" : "client-lock-pointer";
    std::thread worker([&]{
        bool paused=false; eventHook=[&](const char *name){if(!paused && !std::strcmp(name,point)) {paused=true; pause.arrive();}};
        switch(operation) {
        case SubmitOp: result=request.run(c); break;
        case WaitOp: result=call(c,PHXN_SEL_WAITSEQ,a); break;
        case TopologyOp: result=call(c,PHXN_SEL_TOPOLOGY,a); break;
        case SurfaceOp: result=call(c,PHXN_SEL_SURF_GPU_MARK,a); break;
        case LockedOp: result=call(c,PHXN_SEL_QUERYINFO,a); break;
        case MemoryOp: result=c.clientMemoryForType(1,&options,&memory); break;
        }
        CHECK(paused && !clientHeld); eventHook={};
    }); ++threaded;
    pause.wait(); CHECK(c.exactClientCallbacks.active()>0);
    CHECK(c.clientClose()==kIOReturnSuccess && !c.exactClientCallbacks.drained());
    intact(c,owner); pause.release(); worker.join();
    CHECK(c.exactClientCallbacks.drained());
    const bool blocked=operation==LockedOp || operation==MemoryOp;
    CHECK(result==(blocked ? kIOReturnNotReady : kIOReturnSuccess));
    CHECK(!memory && options==55);
    if(operation==SubmitOp) { Ticket t; CHECK(registry.lookup(100,t)==Status::Ok && request.a.scalarOutput[0]==100);
        QueueObservation q[2]={{11,100,100,true,false},{}};
        CHECK(registry.observe(t,false,q)==Status::Lost && registry.forget(t)==Status::Invalid); }
    if(blocked) CHECK(leafCalls==0 && mdRetains==0);
    denied(c,owner); c.free(); intact(c,owner);
}
static void queuedAndConcurrentClose() {
    reset(); PhxBringup owner; Registry registry(40); IOAccelPhxNativeClient c; startExact(c,owner,registry); Pause queued;
    std::thread worker([&]{queued.arrive(); denied(c,owner);}); ++threaded;
    queued.wait(); CHECK(c.clientClose()==kIOReturnSuccess); queued.release(); worker.join(); intact(c,owner);
    reset(); PhxBringup second; Registry r(41); IOAccelPhxNativeClient d; startExact(d,second,r); Pause start;
    std::thread closer([&]{start.arrive(); CHECK(d.clientClose()==kIOReturnSuccess);}); ++threaded;
    start.wait(); start.release(); CHECK(d.clientClose()==kIOReturnSuccess); closer.join();
    CHECK(d.retained==1 && second.retained==1 && d.exactClientCallbacks.drained()); intact(d,second);
}
static void otherClientAndLegacy() {
    reset(); PhxBringup owner; Registry one(50),two(51); IOAccelPhxNativeClient c,d;
    startExact(c,owner,one); startExact(d,owner,two); CHECK(owner.retained==2);
    CHECK(c.clientClose()==kIOReturnSuccess); Request request;
    CHECK(request.run(d)==kIOReturnSuccess && !d.exactClientCallbacks.closed() && two.occupied()==1);
    CHECK(one.occupied()==0 && owner.vmidCalls==0 && mdReleases==0);
    reset(); PhxBringup legacyOwner; IOAccelPhxNativeClient legacy;
    CHECK(legacy.start(&legacyOwner) && !legacy.exactClientPinned);
    auto a=boFreeArgs(); CHECK(call(legacy,PHXN_SEL_BOFREE,a)==kIOReturnSuccess && !legacy.bos[1].md);
    CHECK(mdReleases==1 && !legacy.maps[0].used && legacy.visUsed==0);
    legacy.lastSeq=100; CHECK(legacy.clientClose()==kIOReturnSuccess);
    CHECK(sleeps==2000 && !legacyOwner.vm[0].busy && mdReleases==2 && terminations==1);
}
static void beforeExposure() {
    reset(); PhxBringup owner; Registry registry(60); IOAccelPhxNativeClient c; startExact(c,owner,registry);
    phxn_gem_va v; auto a=unmapArgs(v);
    CHECK(call(c,PHXN_SEL_GEMVA,a)==kIOReturnSuccess && owner.unmaps==1 && !c.maps[0].used);
    auto b=boFreeArgs(); CHECK(call(c,PHXN_SEL_BOFREE,b)==kIOReturnSuccess && mdReleases==1 && !c.bos[1].md);
    CHECK(!c.exactResourcesExposed && c.visUsed==0 && !c.exactClientCallbacks.active());
}
int main() {
    activationAndIdleClose(); exposedResources();
    for(unsigned op=SubmitOp;op<=MemoryOp;++op) duringClose(Operation(op));
    queuedAndConcurrentClose(); otherClientAndLegacy(); beforeExposure();
    CHECK(!clientHeld && !eventHook);
    std::printf("PASS actual staged exact client retention: %llu checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
                (unsigned long long)checks.load(),groups,threaded);
}
#endif
