// SPDX-License-Identifier: MIT
// Extracted staged callsites; CPU objects/registers/reader, never IOKit or GPU.
#include <algorithm>
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
#include <vector>
#include "PhxNativeABI.h"
#include "build34_exact_callbacks.h"
#include "build34_exact_ownership.h"
using namespace phx34_exact;
using IOReturn=int;
static std::atomic<uint64_t> checks{0};
static unsigned groups,threaded;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x); std::abort(); } } while(0)
enum { kIOReturnSuccess,kIOReturnNotReady,kIOReturnBadArgument,kIOReturnBusy,kIOReturnNoResources,
       kIOReturnNotFound,kIOReturnUnsupported };
static constexpr int kMaxMaps=2;
static constexpr uint32_t kFirstUserVmid=8;
static constexpr uint64_t kVaMask=(1ull<<48)-1,sentinel=0xabcdef;
static thread_local unsigned clientHeld,gpuHeld;
static thread_local std::function<void(const char *)> eventHook;
static std::atomic<unsigned> sampleCalls{0},packetWrites{0},frees{0},terminations{0};
static bool baseStart=true;
static void event(const char *name) { if(eventHook) eventHook(name); }
struct Lock { std::mutex mutex; bool client=false; };
static void IOLockLock(Lock *p) {
    CHECK(p); event(p->client ? "client-lock-pointer" : "gpu-lock-pointer");
    if(p->client) CHECK(!gpuHeld);
    p->mutex.lock(); if(p->client) ++clientHeld; else ++gpuHeld;
}
static void IOLockUnlock(Lock *p) {
    CHECK(p); if(p->client) { CHECK(clientHeld); --clientHeld; } else { CHECK(gpuHeld); --gpuHeld; }
    p->mutex.unlock();
}
static uint64_t mach_absolute_time() { return 10000000; }
static void absolutetime_to_nanoseconds(uint64_t v,uint64_t *out) { *out=v; }
static void IOSleep(unsigned ms) { CHECK(ms==1 && !gpuHeld); }
static void IOLog(const char *,...) {}
static bool vaCanonical(uint64_t va) { return va>>47==0 || va>>47==0x1ffff; }
struct OSObject {
    std::atomic<unsigned> retained{0};
    virtual ~OSObject()=default; // CPU polymorphism only, not OSObject finalization.
    void retain() { ++retained; event("retain"); }
};
struct IOService : OSObject {};
struct IOUserClient : IOService {
    bool start(IOService *) { event("base-start"); return baseStart; }
    void terminate() { ++terminations; }
};
#define OSDynamicCast(type,p) dynamic_cast<type *>(p)
struct IOExternalMethodArguments {
    unsigned scalarInputCount=0,scalarOutputCount=1;
    size_t structureInputSize=0,structureOutputSize=0;
    const void *structureInput=nullptr,*structureInputDescriptor=nullptr;
    uint64_t scalarOutput[1]{sentinel};
};
struct Memory {
    alignas(16) uint64_t words[2048]{};
    uintptr_t getVirtualAddress() const { return reinterpret_cast<uintptr_t>(words); }
    uint64_t getLength() const { return sizeof words; }
};
struct IOAccelPhxNativeClient;
struct PhxBringup : IOService {
    struct GpuQueue {
        bool ready=true,gfx=false;
        uint32_t ringOff=0,ringDw=1024,wbOff=8192,fenceOff=9000;
        uint64_t dbByte=0,wptr=8,doneEnd=8,fseq[64]{},fend[64]{};
        uint32_t fvmid[64]{};
        volatile uint32_t head=0,tail=0;
        uint64_t lastDone=99,lastProgress=0,killedSeq=0;
        bool killedAll=false;
    } gq[2];
    Memory aperture,bells;
    Memory *fbAper=&aperture,*doorbellMap=&bells,*mmio=&aperture;
    uint64_t fbAperLen=sizeof aperture.words,fbMcBase=0x123400000ull;
    Lock mutex; Lock *gpuLock=&mutex;
    uint64_t gSeq=99,exactQueueGeneration[2]{11,22},exactQueueSubmitted[2]{99,99},exactInvalidationEpoch=0;
    bool exactQueueLive[2]{true,true},exactStopped=false,isSleeping=false;
    mutable CallbackGate<> exactCallbacks;
    using ExactFenceReader=bool (*)(const volatile uint32_t *,uint64_t *);
    ExactFenceReader exactFenceReader=nullptr;
    struct { uint64_t lastSeq=0; } hwv[8];
    std::atomic<unsigned> sessionClaims{0},sessionReleases{0};
    PhxBringup() {
        gq[1].gfx=true; gq[1].ringOff=4096; gq[1].wbOff+=64; gq[1].fenceOff+=8; gq[1].dbByte=8;
        setFence(0,99); setFence(1,99);
    }
    void setFence(unsigned qi,uint64_t v) { CHECK(qi<2); std::memcpy(reinterpret_cast<uint8_t *>(aperture.words)+gq[qi].fenceOff,&v,8); }
    bool claimSession() { ++sessionClaims; return true; }
    void releaseSession() { ++sessionReleases; }
    bool gpuReady() const { return true; }
    bool debugEnabled() const { return false; }
    void vmidFree(uint32_t,uint64_t) { CHECK(false); }
    void *vmCtx(uint32_t h) { CHECK(gpuHeld); return h==7 ? this : nullptr; }
    uint32_t vmBind(uint32_t h) { CHECK(gpuHeld && h==7); return 8; }
    void hdpFlush() { CHECK(gpuHeld); }
    void ringPut(GpuQueue &,uint32_t,uint32_t) { CHECK(gpuHeld); ++packetWrites; }
    bool bindExactClient(Registry &,OSObject *);
    IOReturn gpuSubmit(uint32_t,bool,const uint64_t *,const uint32_t *,uint32_t,uint64_t *,
                       Registry * =nullptr,Ticket ={},const void * =nullptr);
    IOReturn adoptQueue(const uint64_t[6]);
    uint64_t queueFence(const GpuQueue &) const;
    uint64_t gpuRetired() const;
    Status observeExact(Registry &,Ticket,const CallbackGate<> &,const void *);
    void invalidateExactQueues();
    void stop(IOService *);
};
struct IOAccelPhxNativeClient : IOUserClient {
    struct Bo { uint8_t *kva=nullptr; uint64_t size=0; };
    struct Map { bool used=false; uint32_t handle=0; uint64_t va=0,size=0,off=0; } maps[kMaxMaps];
    PhxBringup *owner=nullptr;
    Registry exactRegistry{0};
    Registry *exactOwnership=nullptr;
    bool exactRequested=false,exactStartAttempted=false;
    CallbackGate<> exactClientCallbacks;
    bool exactClientPinned=false,exactResourcesExposed=false,sessionClaimed=false;
    Lock mutex; Lock *lock=&mutex;
    uint32_t vmid=0;
    uint64_t lastSeq=0,emitted=0;
    uint32_t pendFenceHandle=0,pendFenceOffset=0;
    uint64_t pendFenceSeq=0;
    bool ctx[PHXN_MAX_CTX+1]{};
    IOAccelPhxNativeClient() { mutex.client=true; ctx[1]=true; }
    bool ensureVmid() { vmid=7; return true; }
    bool ibCovered(uint64_t,uint64_t) { CHECK(clientHeld); event("validate-IB"); return true; }
    void flushBos() { CHECK(clientHeld); }
    Bo *findBo(uint32_t) { return nullptr; }
    void freeAll() { ++frees; }
    bool start(IOService *);
    IOReturn clientClose();
    IOReturn doSubmit(IOExternalMethodArguments *);
    Status queryExact(uint64_t);
};
static OwnerEpochs gExactOwners;

// PHX34_BINDING_METHODS

struct Pause {
    std::mutex mutex; std::condition_variable cv; bool reached=false,resume=false;
    void arrive() { std::unique_lock<std::mutex> l(mutex); reached=true; cv.notify_all();
        CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return resume;})); }
    void wait() { std::unique_lock<std::mutex> l(mutex);
        CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return reached;})); }
    void release() { std::lock_guard<std::mutex> l(mutex); resume=true; cv.notify_all(); }
};
static void reset() { CHECK(!clientHeld && !gpuHeld && !eventHook); ++groups;
    sampleCalls=packetWrites=frees=terminations=0; baseStart=true; }
static bool sample(const volatile uint32_t *words,uint64_t *out) {
    CHECK(clientHeld==1 && gpuHeld==1); ++sampleCalls; event("sample");
    *out=uint64_t(words[0]) | uint64_t(words[1])<<32; return true; // controlled CPU bytes only
}
static void start(IOAccelPhxNativeClient &c,PhxBringup &d) {
    c.exactRequested=true;
    eventHook=[&](const char *name) { if(std::strcmp(name,"retain")==0)
        CHECK(gpuHeld==1 && !c.exactOwnership && !c.exactClientPinned && c.exactRegistry.boundTo(&d,&c)); };
    CHECK(c.start(&d)); eventHook={};
    CHECK(c.exactClientPinned && c.exactOwnership==&c.exactRegistry);
    CHECK(c.retained==1 && c.exactRegistry.boundTo(&d,&c));
}
struct Request {
    phxn_cs_in h{}; phxn_cs_ib ib{}; IOExternalMethodArguments a;
    explicit Request(bool gfx=true) {
        h.abi=PHXN_ABI_VERSION; h.ctx_id=1; h.num_ibs=1;
        ib.ip_type=gfx ? PHX_AMDGPU_HW_IP_GFX : PHX_AMDGPU_HW_IP_COMPUTE;
        ib.va_start=0x10000; ib.ib_bytes=64;
        a.structureInput=&h; a.structureInputSize=sizeof h+sizeof ib;
        CHECK(reinterpret_cast<uint8_t *>(&ib)-reinterpret_cast<uint8_t *>(&h)==sizeof h);
    }
};
static uint64_t submit(IOAccelPhxNativeClient &c,bool gfx=true) {
    Request r(gfx); IOLockLock(c.lock); CHECK(c.doSubmit(&r.a)==kIOReturnSuccess); IOLockUnlock(c.lock);
    CHECK(c.exactResourcesExposed && r.a.scalarOutput[0]!=sentinel); return r.a.scalarOutput[0];
}
static Ticket ticket(Registry &r,uint64_t seq) { Ticket t; CHECK(r.lookup(seq,t)==Status::Ok); return t; }
static void identities() {
    reset(); PhxBringup d,other; IOAccelPhxNativeClient a,b,c; start(a,d); start(b,d); start(c,other);
    d.exactFenceReader=other.exactFenceReader=sample;
    auto sa=submit(a,false),sb=submit(b),sc=submit(c);
    auto ta=ticket(a.exactRegistry,sa),tb=ticket(b.exactRegistry,sb),tc=ticket(c.exactRegistry,sc);
    CHECK(ta.owner && ta.owner!=tb.owner && ta.owner!=tc.owner && tb.owner!=tc.owner);
    d.setFence(1,sb); CHECK(a.queryExact(sa)==Status::Pending && b.queryExact(sb)==Status::Complete);
    CHECK(d.gpuRetired()==99 && c.queryExact(sc)==Status::Pending);
    auto before=sampleCalls.load(); CallbackGate<> gate;
    CHECK(other.observeExact(a.exactRegistry,ta,gate,&a)==Status::Invalid);
    CHECK(d.observeExact(a.exactRegistry,ta,gate,&b)==Status::Invalid && sampleCalls==before);
    uint64_t va=0x10000,out=sentinel; uint32_t dw=16;
    Ticket reserved; CHECK(a.exactRegistry.reserve(reserved)==Status::Ok);
    before=packetWrites.load();
    CHECK(other.gpuSubmit(7,true,&va,&dw,1,&out,&a.exactRegistry,reserved,&a)==kIOReturnNotReady);
    CHECK(d.gpuSubmit(7,true,&va,&dw,1,&out,&a.exactRegistry,reserved,&b)==kIOReturnNotReady);
    CHECK(packetWrites==before && out==sentinel && a.exactRegistry.cancel(reserved)==Status::Ok);
    a.exactOwnership=&b.exactRegistry;
    eventHook=[](const char *name) { if(std::strcmp(name,"client-lock-pointer")==0) CHECK(false); };
    CHECK(a.queryExact(sb)==Status::Invalid); eventHook={};
    Request invalid; IOLockLock(a.lock);
    eventHook=[](const char *name) { if(std::strcmp(name,"validate-IB")==0) CHECK(false); };
    CHECK(a.doSubmit(&invalid.a)==kIOReturnNotReady); eventHook={}; IOLockUnlock(a.lock);
    CHECK(invalid.a.scalarOutput[0]==sentinel && packetWrites==before);
    a.exactOwnership=&a.exactRegistry; a.owner=&other;
    CHECK(a.queryExact(sa)==Status::Invalid); a.owner=&d;
    CHECK(a.queryExact(sa)==Status::Pending && d.retained==2 && other.retained==1);
}
static void bindRefusals() {
    for(unsigned mode=0;mode<9;++mode) {
        reset(); PhxBringup d,other; IOAccelPhxNativeClient c; Registry external(0); OSObject nonclient;
        c.exactRequested=true; c.exactStartAttempted=true; c.owner=&d;
        if(mode==0) c.exactRequested=false;
        if(mode==1) c.exactStartAttempted=false;
        if(mode==2) c.owner=&other;
        if(mode==3) c.exactClientPinned=true;
        if(mode==4) c.exactOwnership=&external;
        if(mode==5) c.exactClientCallbacks.close();
        Registry &storage=mode==6 ? external : c.exactRegistry;
        OSObject *object=mode==7 ? &nonclient : mode==8 ? nullptr : &c;
        CHECK(!d.bindExactClient(storage,object));
        CHECK(!storage.boundTo(&d,&c) && !d.retained && !c.retained);
    }
    for(unsigned mode=0;mode<4;++mode) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; c.exactRequested=true;
        if(mode==0) d.exactCallbacks.close();
        if(mode==1) d.exactStopped=true;
        if(mode==2) d.isSleeping=true;
        if(mode==3) d.gpuLock=nullptr;
        CHECK(!c.start(&d)); CHECK(!c.exactOwnership && !c.exactClientPinned && !c.retained && !d.retained);
        CHECK(!c.start(&d)); // a failed exact start cannot later downgrade/rebind
        CHECK(c.clientClose()==kIOReturnNotReady && !frees && !terminations);
    }
}
static void startsAndClose() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; c.exactRequested=true;
    baseStart=false; CHECK(!c.start(&d)); baseStart=true;
    CHECK(!c.start(&d) && !d.retained && !c.retained && !c.exactOwnership);
    IOAccelPhxNativeClient poisoned; Registry injected(123); poisoned.exactOwnership=&injected;
    CHECK(!poisoned.start(&d) && !poisoned.owner);
    IOAccelPhxNativeClient good; start(good,d); auto seq=submit(good);
    CHECK(!good.start(&d) && d.retained==1 && good.retained==1);
    CHECK(good.clientClose()==kIOReturnSuccess && good.clientClose()==kIOReturnSuccess);
    CHECK(!frees && !terminations && good.retained==1 && d.retained==1);
    CHECK(good.queryExact(seq)==Status::Closed && !good.start(&d));
    Receipt receipt; CHECK(good.exactRegistry.inspect(ticket(good.exactRegistry,seq),receipt)==Status::Ok);
    CHECK(good.exactRegistry.bind(&d,&good,gExactOwners)==Status::Invalid);
    IOAccelPhxNativeClient legacy; CHECK(legacy.start(&d));
    CHECK(!legacy.exactOwnership && !legacy.exactClientPinned && !legacy.retained && d.retained==1);
    CHECK(legacy.clientClose()==kIOReturnSuccess && frees==1 && terminations==1);
}
static void registryContract() {
    reset(); int provider=0,client=0,other=0; OwnerEpochs owners(UINT64_MAX-3); Registry a(0),b(0),c(0);
    CHECK(a.bind(nullptr,&client,owners)==Status::Invalid);
    CHECK(a.bind(&provider,nullptr,owners)==Status::Invalid);
    CHECK(a.bind(&provider,&client,owners)==Status::Ok);
    CHECK(a.boundTo(&provider,&client) && !a.boundTo(&provider,&other) && !a.boundTo(&other,&client));
    CHECK(!a.boundTo(nullptr,&client) && !a.boundTo(&provider,nullptr));
    Ticket ta,tb; CHECK(a.reserve(ta)==Status::Ok && ta.owner==UINT64_MAX-2);
    CHECK(a.cancel(ta)==Status::Ok && a.bind(&provider,&other,owners)==Status::Invalid);
    CHECK(b.bind(&provider,&client,owners)==Status::Ok && b.reserve(tb)==Status::Ok && tb.owner==UINT64_MAX-1);
    CHECK(c.bind(&provider,&client,owners)==Status::Exhausted && !c.boundTo(&provider,&client));
    uint64_t out=sentinel; CHECK(!owners.take(out) && out==sentinel);
    a.close(); CHECK(a.bind(&other,&other,owners)==Status::Invalid && a.boundTo(&provider,&client));
    OwnerEpochs empty; Registry legacy(1),invalid(UINT64_MAX);
    CHECK(legacy.bind(&provider,&client,empty)==Status::Invalid && invalid.bind(&provider,&client,empty)==Status::Invalid);
    // Reusing the exact same storage labels cannot reuse the old ticket identity.
    Ticket old; { Registry previous(0); CHECK(previous.bind(&provider,&client,empty)==Status::Ok);
        CHECK(previous.reserve(old)==Status::Ok); }
    Registry replacement(0); CHECK(replacement.bind(&provider,&client,empty)==Status::Ok);
    Ticket next; CHECK(replacement.reserve(next)==Status::Ok && next.owner!=old.owner);
    CHECK(replacement.publish(old,{100,11,1})==Status::Unknown);
}
static void metadataAndAdoption() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; start(c,d); auto seq=submit(c);
    CHECK(c.queryExact(seq)==Status::InvalidObservation); d.exactFenceReader=sample;
    d.setFence(1,seq); CHECK(c.queryExact(seq)==Status::Complete);
    const Ticket old=ticket(c.exactRegistry,seq); CHECK(c.exactRegistry.forget(old)==Status::Ok);
    CHECK(c.queryExact(seq)==Status::Unknown);
    auto nextSeq=submit(c); const Ticket next=ticket(c.exactRegistry,nextSeq);
    CHECK(next.owner==old.owner && next.slot==old.slot && next.serial!=old.serial);
    Receipt receipt; CHECK(c.exactRegistry.inspect(old,receipt)==Status::Unknown);
    auto &q=d.gq[1]; uint64_t in[]={q.ringOff,q.ringDw,q.wbOff,q.dbByte,q.wptr,q.fenceOff|1u};
    CHECK(d.adoptQueue(in)==kIOReturnSuccess && c.queryExact(nextSeq)==Status::Lost);
    auto fresh=submit(c); d.setFence(1,fresh); CHECK(c.queryExact(fresh)==Status::Complete);
    CHECK(c.exactRegistry.boundTo(&d,&c) && c.retained==1 && d.retained==1);
    d.stop(nullptr); CHECK(c.queryExact(fresh)==Status::Lost && d.retained==2 && c.retained==1);
}
static void parallelOwners() {
    reset(); ++threaded; OwnerEpochs owners; constexpr unsigned n=8,each=256;
    uint64_t values[n][each]{}; std::vector<std::thread> threads;
    for(unsigned i=0;i<n;++i) threads.emplace_back([&,i] {
        for(unsigned j=0;j<each;++j) {
            uint64_t id=sentinel; const bool ok=owners.take(id);
            if(ok) { CHECK(id && id!=UINT64_MAX); values[i][j]=id; }
            else CHECK(id==sentinel); // bounded contention refusal is allowed
        }
    });
    for(auto &t:threads) t.join();
    std::vector<uint64_t> sorted;
    for(auto &row:values) for(auto value:row) if(value) sorted.push_back(value);
    std::sort(sorted.begin(),sorted.end()); CHECK(!sorted.empty());
    for(size_t i=0;i<sorted.size();++i) CHECK(sorted[i]==i+1);
}
static void parallelClients() {
    reset(); ++threaded; constexpr unsigned n=8;
    std::unique_ptr<PhxBringup> providers[2]; for(auto &p:providers) p.reset(new PhxBringup);
    std::unique_ptr<IOAccelPhxNativeClient> clients[n]; for(auto &c:clients) c.reset(new IOAccelPhxNativeClient);
    uint64_t owners[n]{}; std::vector<std::thread> threads;
    for(unsigned i=0;i<n;++i) threads.emplace_back([&,i] {
        auto &c=*clients[i]; start(c,*providers[i%2]); auto seq=submit(c);
        owners[i]=ticket(c.exactRegistry,seq).owner;
    });
    for(auto &t:threads) t.join();
    std::sort(owners,owners+n);
    for(unsigned i=0;i<n;++i) CHECK(owners[i] && (i==0 || owners[i]>owners[i-1]));
    CHECK(providers[0]->retained==4 && providers[1]->retained==4);
}
static void closeDuringBind(bool stop) {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; c.exactRequested=true; Pause p;
    bool started=false;
    std::thread t([&] { eventHook=[&](const char *eventName) {
            if(std::strcmp(eventName,"gpu-lock-pointer")==0) p.arrive(); };
        started=c.start(&d); eventHook={}; });
    p.wait(); if(stop) d.stop(nullptr); else c.exactClientCallbacks.close();
    p.release(); t.join(); CHECK(!started && !c.retained && !c.exactOwnership);
    CHECK(!c.exactClientPinned && d.retained==(stop ? 1u : 0u));
}
static void closeDuringObservation() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; start(c,d);
    d.exactFenceReader=sample; auto seq=submit(c); d.setFence(1,seq); Pause p;
    Status result=Status::Invalid;
    std::thread t([&] { eventHook=[&](const char *name) { if(std::strcmp(name,"sample")==0) p.arrive(); };
        result=c.queryExact(seq); eventHook={}; });
    p.wait(); CHECK(c.clientClose()==kIOReturnSuccess && !frees && !terminations);
    p.release(); t.join(); CHECK(result==Status::Lost && c.queryExact(seq)==Status::Closed);
    CHECK(c.retained==1 && d.retained==1);
}
int main() {
    identities(); bindRefusals(); startsAndClose(); registryContract(); metadataAndAdoption(); parallelOwners(); parallelClients();
    closeDuringBind(false); closeDuringBind(true); closeDuringObservation();
    CHECK(!clientHeld && !gpuHeld);
    std::printf("PASS staged exact embedded binding: %llu checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
                static_cast<unsigned long long>(checks.load()),groups,threaded);
}
