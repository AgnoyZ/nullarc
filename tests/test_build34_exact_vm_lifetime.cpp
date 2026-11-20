// SPDX-License-Identifier: MIT
// Actual staged VM methods; handwritten CPU IOKit/register/page-walk doubles.
#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <strings.h>
#include <thread>
#include <vector>
#include "PhxNativeABI.h"
#include "build34_exact_callbacks.h"
#include "build34_exact_ownership.h"
#include "build34_exact_fence32.h"
using namespace phx34_exact;
using IOReturn=int;
using IOByteCount=uint64_t;
using addr64_t=uint64_t;
static std::atomic<uint64_t> checks{0};
static unsigned groups=0,threaded=0;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x); std::abort(); } } while(0)
enum { kIOReturnSuccess,kIOReturnNotReady,kIOReturnBadArgument,kIOReturnBusy,kIOReturnNoResources,
       kIOReturnNotFound,kIOReturnUnsupported,kIOReturnNoMemory,kIOReturnVMError };
static constexpr int kMaxMaps=2;
static constexpr unsigned kIOMemoryMapperNone=0;
static constexpr uint64_t sentinel=0xabcdef,kVaMask=(1ull<<48)-1;
// PHX34_VM_CONSTANTS
static thread_local unsigned clientHeld=0,gpuHeld=0;
static thread_local uint64_t testTicks=10000000,delayStep=1000;
static thread_local std::function<void(const char *)> eventHook;
static std::atomic<unsigned> packetWrites{0},frees{0},terminations{0},sleepCalls{0},delays{0},lineFlushes{0};
static void event(const char *n) { if(eventHook) eventHook(n); }
struct Lock { std::mutex mutex; bool client=false; };
static void IOLockLock(Lock *p) {
    CHECK(p); event(p->client ? "client-lock-pointer" : "gpu-lock-pointer");
    CHECK(!gpuHeld); p->mutex.lock(); if(p->client) ++clientHeld; else ++gpuHeld;
}
static void IOLockUnlock(Lock *p) {
    CHECK(p); if(p->client) { CHECK(clientHeld); --clientHeld; } else { CHECK(gpuHeld); --gpuHeld; }
    p->mutex.unlock();
}
static uint64_t mach_absolute_time() { event("clock"); return testTicks; }
static void absolutetime_to_nanoseconds(uint64_t v,uint64_t *p) { *p=v; }
static void IOSleep(unsigned n) { CHECK(n==1 && !gpuHeld && ++sleepCalls<=2000); event("sleep"); testTicks+=1000000; }
static void IODelay(unsigned n) { CHECK(n==1 && gpuHeld==1 && ++delays<=1000); event("delay"); testTicks+=delayStep; }
static void flushLine(const volatile void *) { CHECK(gpuHeld==1); ++lineFlushes; }
static bool vaCanonical(uint64_t v) { return v>>47==0 || v>>47==0x1ffff; }
static void IOLog(const char *,...) {}
struct OSObject { std::atomic<unsigned> retained{0}; virtual ~OSObject()=default; void retain() { ++retained; event("retain"); } };
struct IOService : OSObject {};
struct IOUserClient : IOService { bool start(IOService *) { return true; } void terminate() { ++terminations; } };
#define OSDynamicCast(t,p) dynamic_cast<t *>(p)
struct IOExternalMethodArguments {
    unsigned scalarInputCount=0,scalarOutputCount=1;
    size_t structureInputSize=0,structureOutputSize=0;
    const void *structureInput=nullptr,*structureInputDescriptor=nullptr;
    uint64_t scalarOutput[1]{sentinel};
};
struct IOMemoryDescriptor {
    uint64_t length=16384,segment=4096,physical=0x500000;
    unsigned segments=0,failAt=UINT32_MAX;
    uint64_t getLength() const { return length; }
    addr64_t getPhysicalSegment(uint64_t off,IOByteCount *len,unsigned mapper) {
        CHECK(gpuHeld==1 && mapper==kIOMemoryMapperNone); event("segment");
        *len=segment; return segments++==failAt ? 0 : physical+off;
    }
};
struct IOBufferMemoryDescriptor { std::vector<uint8_t> bytes=std::vector<uint8_t>(65536,0xa5);
    void *getBytesNoCopy() { CHECK(gpuHeld==1); return bytes.data(); } };
struct Memory { alignas(16) uint64_t words[2048]{};
    uintptr_t getVirtualAddress() const { return reinterpret_cast<uintptr_t>(words); }
    uint64_t getLength() const { return sizeof words; } };
struct IOAccelPhxNativeClient;
struct PhxBringup : IOService {
    struct GpuQueue {
        bool ready=true,gfx=false;
        uint32_t ringOff=0,ringDw=1024,wbOff=8192,fenceOff=9000;
        uint64_t dbByte=0,wptr=8,doneEnd=8,fseq[64]{},fend[64]{};
        uint32_t fvmid[64]{}; volatile uint32_t head=0,tail=0;
        uint64_t lastDone=99,lastProgress=0,killedSeq=0; bool killedAll=false;
    } gq[2];
    Memory aperture,bells; Memory *fbAper=&aperture,*doorbellMap=&bells,*mmio=&aperture;
    uint64_t fbAperLen=sizeof aperture.words,fbMcBase=0x123400000ull;
    Lock mutex; Lock *gpuLock=&mutex;
    uint64_t gSeq=99,exactQueueGeneration[2]{11,22},exactQueueSubmitted[2]{99,99},exactInvalidationEpoch=0;
    bool exactQueueLive[2]{true,true},exactStopped=false,isSleeping=false;
    mutable CallbackGate<> exactCallbacks;
    using ExactFenceReader=bool (*)(const volatile uint32_t *,uint64_t *);
    ExactFenceReader exactFenceReader=nullptr;
    using ExactDwordReader=bool (*)(const volatile uint32_t *,uint32_t *);
    ExactDwordReader exactDwordReader=nullptr;
    FenceWindow32 exactFenceWindow[2];
    // PHX34_VM_FIELDS
    std::vector<std::unique_ptr<IOBufferMemoryDescriptor>> buffers;
    std::map<std::pair<unsigned,uint64_t>,uint64_t> ptes;
    std::vector<std::pair<uint32_t,uint32_t>> registers;
    unsigned roots=0,pteCalls=0,ackReads=0,ackAfter=0;
    uint32_t ackBits=0xff00;
    bool failRoot=false,failPte=false;
    PhxBringup() {
        gq[1].gfx=true; gq[1].ringOff=4096; gq[1].wbOff+=64; gq[1].fenceOff+=8; gq[1].dbByte=8;
        setFence(0,99); setFence(1,99);
    }
    void setFence(unsigned qi,uint64_t v) { CHECK(qi<2); std::memcpy(reinterpret_cast<uint8_t *>(aperture.words)+gq[qi].fenceOff,&v,8); }
    bool claimSession() { return true; } void releaseSession() {}
    bool gpuReady() const { return gq[0].ready || gq[1].ready; }
    bool debugEnabled() const { return false; }
    uint64_t ptTablePhys(VmCtx &c,uint32_t i) {
        CHECK(gpuHeld==1 && i<kPtChunks); if(failRoot) return 0;
        if(!c.chunk[i]) {
            buffers.emplace_back(new IOBufferMemoryDescriptor); c.chunk[i]=buffers.back().get();
            c.chunkPhys[i]=0x100000000ull+(++roots)*65536ull;
        }
        return c.chunkPhys[i];
    }
    uint64_t *vmPte(VmCtx &c,uint64_t va,bool alloc) {
        CHECK(gpuHeld==1 && &c>=vm && &c<vm+kMaxCtx); ++pteCalls; event("pte");
        if(failPte) return nullptr;
        const auto key=std::make_pair(unsigned(&c-vm),va);
        if(!alloc && !ptes.count(key)) return nullptr;
        return &ptes[key]; // CPU identity/write double, NOT the actual native page walker
    }
    void wreg(uint32_t r,uint32_t v) { CHECK(gpuHeld==1); registers.emplace_back(r,v); event("register-write"); }
    uint32_t rreg(uint32_t r) { CHECK(gpuHeld==1 && r==kRegInvEng17Ack); ++ackReads; event("ack-read"); return ackReads>ackAfter ? ackBits : 0; }
    void hdpFlush() { CHECK(gpuHeld==1); }
    void ringPut(GpuQueue &,uint32_t,uint32_t) { CHECK(gpuHeld==1); ++packetWrites; }
    bool bindExactClient(Registry &,OSObject *);
    uint32_t vmidAlloc(const void *,uint64_t *);
    bool vmidFree(uint32_t,uint64_t,const void *,uint64_t);
    IOReturn vmMap(uint32_t,uint64_t,const void *,uint64_t,IOMemoryDescriptor *,uint64_t,uint64_t);
    IOReturn vmUnmap(uint32_t,uint64_t,const void *,uint64_t,uint64_t);
    IOReturn gpuSubmit(uint32_t,uint64_t,const void *,bool,const uint64_t *,const uint32_t *,uint32_t,uint64_t *,
        Registry * =nullptr,Ticket ={},const void * =nullptr);
    IOReturn adoptQueue(const uint64_t[6]);
    bool readExactFence32(uint32_t,uint64_t *);
    uint64_t queueFence(const GpuQueue &) const;
    uint64_t gpuRetired() const;
    Status observeExact(Registry &,Ticket,const CallbackGate<> &,const void *);
    void invalidateExactQueues(); void stop(IOService *);
};
struct IOAccelPhxNativeClient : IOUserClient {
    struct Bo { uint8_t *kva=nullptr; uint64_t size=0; };
    struct Map { bool used=false; uint32_t handle=0; uint64_t va=0,size=0,off=0; } maps[kMaxMaps];
    PhxBringup *owner=nullptr;
    Registry exactRegistry{0}; Registry *exactOwnership=nullptr;
    bool exactRequested=false,exactStartAttempted=false,exactClientPinned=false,exactResourcesExposed=false,sessionClaimed=false;
    CallbackGate<> exactClientCallbacks;
    Lock mutex; Lock *lock=&mutex;
    uint32_t vmid=0; uint64_t vmGeneration=0,lastSeq=0,emitted=0;
    uint32_t pendFenceHandle=0,pendFenceOffset=0; uint64_t pendFenceSeq=0;
    bool ctx[PHXN_MAX_CTX+1]{};
    IOAccelPhxNativeClient() { mutex.client=true; ctx[1]=true; }
    // PHX34_VM_ENSURE
    bool ibCovered(uint64_t,uint64_t) { CHECK(clientHeld); return true; }
    void flushBos() { CHECK(clientHeld); } Bo *findBo(uint32_t) { return nullptr; }
    void freeAll() { ++frees; }
    bool start(IOService *); IOReturn clientClose(); IOReturn doSubmit(IOExternalMethodArguments *);
    Status queryExact(uint64_t);
};
static OwnerEpochs gExactOwners;
// PHX34_VM_METHODS

struct Pause {
    std::mutex mutex; std::condition_variable cv; bool reached=false,resume=false;
    void arrive() { std::unique_lock<std::mutex> l(mutex); reached=true; cv.notify_all();
        CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return resume;})); }
    void wait() { std::unique_lock<std::mutex> l(mutex); CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return reached;})); }
    void release() { std::lock_guard<std::mutex> l(mutex); resume=true; cv.notify_all(); }
};
static void reset() {
    CHECK(!clientHeld && !gpuHeld && !eventHook); ++groups;
    packetWrites=frees=terminations=sleepCalls=delays=lineFlushes=0; testTicks=10000000; delayStep=1000;
}
static bool raw32(const volatile uint32_t *p,uint32_t *v) { CHECK(gpuHeld==1); *v=*p; return true; }
static void start(IOAccelPhxNativeClient &c,PhxBringup &d) {
    c.exactRequested=true; CHECK(c.start(&d)); CHECK(c.exactClientPinned && c.exactOwnership==&c.exactRegistry);
}
static void setup(PhxBringup &d,IOAccelPhxNativeClient &c) {
    for(unsigned qi=0;qi<2;++qi) {
        const uint64_t in[6]={qi ? 4096u : 0u,1024,qi ? 8256u : 8192u,qi ? 8u : 0u,8,(qi ? 9008u : 9000u)|qi};
        CHECK(d.adoptQueue(in)==kIOReturnSuccess);
    }
    d.exactDwordReader=raw32; start(c,d);
}
struct Request {
    phxn_cs_in h{}; phxn_cs_ib ib{}; IOExternalMethodArguments a;
    explicit Request(bool gfx=true) {
        h.abi=PHXN_ABI_VERSION; h.ctx_id=1; h.num_ibs=1;
        ib.ip_type=gfx ? PHX_AMDGPU_HW_IP_GFX : PHX_AMDGPU_HW_IP_COMPUTE;
        ib.va_start=0x10000; ib.ib_bytes=64; a.structureInput=&h; a.structureInputSize=sizeof h+sizeof ib;
        CHECK(reinterpret_cast<uint8_t *>(&ib)-reinterpret_cast<uint8_t *>(&h)==sizeof h);
    }
};
static int submit(IOAccelPhxNativeClient &c,uint64_t &seq,bool gfx=true) {
    Request r(gfx); IOLockLock(c.lock); int result=c.doSubmit(&r.a); IOLockUnlock(c.lock); seq=r.a.scalarOutput[0]; return result;
}
static uint64_t accepted(IOAccelPhxNativeClient &c,bool gfx=true) { uint64_t seq; CHECK(submit(c,seq,gfx)==kIOReturnSuccess && seq!=sentinel); return seq; }
static unsigned allocate(PhxBringup &d,IOAccelPhxNativeClient &c) {
    IOLockLock(c.lock); CHECK(c.ensureVmid()); IOLockUnlock(c.lock);
    CHECK(c.vmid && c.vmGeneration && d.vm[c.vmid-1].client==&c); return c.vmid;
}
static bool release(PhxBringup &d,IOAccelPhxNativeClient &c,uint64_t last=0) { return d.vmidFree(c.vmid,c.vmGeneration,&c,last); }
static unsigned bind(PhxBringup &d,unsigned h,uint64_t gen,const void *client,uint64_t retired) {
    CallbackGate<>::Lease lease(d.exactCallbacks); CHECK(lease); IOLockLock(d.gpuLock);
    auto result=d.vmBind(h,gen,client,retired); IOLockUnlock(d.gpuLock); return result;
}
static bool flush(PhxBringup &d,unsigned hw) {
    CallbackGate<>::Lease lease(d.exactCallbacks); CHECK(lease); IOLockLock(d.gpuLock);
    bool result=d.vmFlushTlbChecked(hw); IOLockUnlock(d.gpuLock); return result;
}
static bool unchanged(const std::vector<uint8_t> &v) { return std::all_of(v.begin(),v.end(),[](uint8_t x){return x==0xa5;}); }
static void allocationAndABA() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c,other; setup(d,c); start(other,d);
    uint64_t out=0,old=0;
    CHECK(!d.vmidAlloc(nullptr,&out) && !d.vmidAlloc(&c,nullptr));
    out=7; CHECK(!d.vmidAlloc(&c,&out) && out==7); d.failRoot=true; out=0;
    CHECK(!d.vmidAlloc(&c,&out) && !out && !d.vm[0].busy); d.failRoot=false;
    const auto handle=allocate(d,c); old=c.vmGeneration; CHECK(handle==1 && old==1);
    CHECK(release(d,c) && !d.vm[0].busy && d.vm[0].generation==old && !d.vm[0].client);
    c.vmid=0; c.vmGeneration=0; CHECK(allocate(d,c)==handle && c.vmGeneration==old+1); // same client address too
    IOMemoryDescriptor md; const auto before=d.pteCalls;
    CHECK(d.vmMap(handle,old,&c,0x10000,&md,0,4096)==kIOReturnNotReady);
    CHECK(d.vmUnmap(handle,old,&c,0x10000,4096)==kIOReturnNotReady);
    CHECK(!d.vmidFree(handle,old,&c,0) && !bind(d,handle,old,&c,99));
    uint64_t va=0x10000,seq=sentinel; uint32_t dw=16;
    CHECK(d.gpuSubmit(handle,old,&c,true,&va,&dw,1,&seq)==kIOReturnNotReady && seq==sentinel);
    CHECK(d.vm[0].busy && !d.vm[0].closing && d.pteCalls==before && d.registers.empty());
    for(unsigned mode=0;mode<5;++mode) {
        const unsigned h=mode==0 ? 0 : mode==1 ? 97 : handle;
        const uint64_t gen=mode==2 ? 0 : mode==3 ? UINT64_MAX : c.vmGeneration;
        const void *owner=mode==4 ? static_cast<void *>(&other) : static_cast<void *>(&c);
        CHECK(d.vmMap(h,gen,owner,0x10000,&md,0,4096)==kIOReturnNotReady);
        CHECK(!d.vmidFree(h,gen,owner,0));
    }
}
static void generationAndCapacity() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); d.vm[0].generation=UINT64_MAX-1;
    uint64_t gen=0; CHECK(d.vmidAlloc(&c,&gen)==2 && gen==1 && !d.vm[0].busy);
    for(unsigned i=0;i<PhxBringup::kMaxCtx;++i) d.vm[i].busy=true;
    gen=0; CHECK(!d.vmidAlloc(&c,&gen) && !gen);
    d.vm[20].busy=false; d.vm[20].closing=true; CHECK(!d.vmidAlloc(&c,&gen));
    d.vm[20].closing=false; d.vm[20].generation=UINT64_MAX; CHECK(!d.vmidAlloc(&c,&gen));
}
static void queuedAllocationRechecksOutput() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    uint64_t generation=0; unsigned result=99; Pause pause; bool first=true;
    std::thread t([&] {
        eventHook=[&](const char *n){ if(!std::strcmp(n,"gpu-lock-pointer") && first) { first=false; pause.arrive(); } };
        result=d.vmidAlloc(&c,&generation); eventHook={};
    });
    pause.wait(); CHECK(d.vmidAlloc(&c,&generation)==1 && generation==1);
    pause.release(); t.join(); CHECK(!result && generation==1 && d.roots==1 && d.vm[0].busy && !d.vm[1].busy);
}
static void wideIdentityAndRootAdmission() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    // Model an old root-allocation failure which cached a descriptor but no address.
    IOLockLock(d.gpuLock); (void)d.ptTablePhys(d.vm[0],0); IOLockUnlock(d.gpuLock);
    const auto h=allocate(d,c); CHECK(h==2 && !d.vm[0].busy && !d.vm[0].generation);
    CHECK(release(d,c)); c.vmid=0; c.vmGeneration=0;
    d.vm[0].phys=d.vm[0].chunkPhys[0]; d.vm[0].pages=PhxBringup::kPtChunks*PhxBringup::kPtChunkPages;
    d.vm[0].generation=0x123400000000ull;
    d.gSeq=0x12345678fffffffeull;
    for(unsigned qi=0;qi<2;++qi) {
        const uint64_t in[6]={qi ? 4096u : 0u,1024,qi ? 8256u : 8192u,qi ? 8u : 0u,8,(qi ? 9008u : 9000u)|qi};
        CHECK(d.adoptQueue(in)==kIOReturnSuccess);
    }
    const auto compute=accepted(c,false),gfx=accepted(c);
    CHECK(c.vmid==1 && c.vmGeneration==0x123400000001ull && compute==0x12345678ffffffffull && gfx==compute+1);
    CHECK(d.vm[0].queueSequence[0]==compute && d.vm[0].queueSequence[1]==gfx && d.vm[0].newest==gfx);
    d.setFence(1,gfx); CHECK(c.queryExact(gfx)==Status::Complete && d.gpuRetired()==compute-1);
    d.setFence(0,compute); CHECK(release(d,c) && !d.vm[0].busy && d.vm[0].generation==c.vmGeneration);
}
static void mappings() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto h=allocate(d,c); const auto gen=c.vmGeneration;
    IOMemoryDescriptor md;
    CHECK(d.vmMap(h,gen,&c,0x10000,&md,0,8192)==kIOReturnSuccess && d.pteCalls==2 && md.segments==2);
    CHECK(d.ptes[std::make_pair(h-1,0x10000ull)]==(0x500000|kPteSysFlags));
    CHECK(d.vmUnmap(h,gen,&c,0x10000,8192)==kIOReturnSuccess);
    CHECK(!d.ptes[std::make_pair(h-1,0x10000ull)] && !d.exactVMFault && d.registers.empty());
    const auto before=d.pteCalls;
    for(unsigned mode=0;mode<8;++mode) {
        uint64_t va=0x10000,size=4096,off=0; IOMemoryDescriptor *p=&md;
        if(mode==0) size=0; if(mode==1) va++; if(mode==2) size++; if(mode==3) va=0;
        if(mode==4) va=(1ull<<48)-4096,size=8192; if(mode==5) off=UINT64_MAX-4095;
        if(mode==6) p=nullptr; if(mode==7) off=4096,md.length=4096;
        CHECK(d.vmMap(h,gen,&c,va,p,off,size)==kIOReturnBadArgument);
    }
    CHECK(d.pteCalls==before && !d.exactVMFault);
    const auto seq=accepted(c,false); const auto writes=packetWrites.load();
    CHECK(d.vm[h-1].newest==seq);
    CHECK(d.vmMap(h,gen,&c,0x20000,&md,0,4096)==kIOReturnBusy);
    CHECK(d.vmUnmap(h,gen,&c,0x10000,4096)==kIOReturnBusy && d.pteCalls==before);
    CHECK(packetWrites==writes && !d.exactVMFault);
}
static void timeoutRetainsTables() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto seq=accepted(c,false);
    const auto h=c.vmid,hw=d.vm[h-1].hw; const auto gen=c.vmGeneration;
    const auto before=d.registers.size();
    CHECK(!release(d,c,0)); // deliberately underreports the client's last sequence
    CHECK(sleepCalls==2000 && d.vm[h-1].busy && d.vm[h-1].closing && d.vm[h-1].newest==seq);
    CHECK(d.vm[h-1].generation==gen && d.hwv[hw-8].ctx==h && d.hwv[hw-8].generation==gen);
    CHECK(unchanged(d.vm[h-1].chunk[0]->bytes) && !lineFlushes && d.registers.size()==before);
    IOMemoryDescriptor md; uint64_t out=0;
    CHECK(d.vmMap(h,gen,&c,0x10000,&md,0,4096)==kIOReturnNotReady);
    CHECK(submit(c,out)==kIOReturnNotReady && out==sentinel && c.exactRegistry.occupied()==1);
    CHECK(!frees && !terminations && c.retained==1 && !d.exactVMFault);
}
static void progressWhileFreeWaits(bool stop) {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c,gfx; setup(d,c); start(gfx,d);
    const auto seq=accepted(c,false); const auto h=c.vmid; const auto gen=c.vmGeneration;
    Pause pause; bool first=true,result=true;
    std::thread t([&] { eventHook=[&](const char *n){ if(!std::strcmp(n,"sleep") && first) { first=false; pause.arrive(); } };
        result=release(d,c,0); eventHook={}; });
    pause.wait(); CHECK(d.vm[h-1].busy && d.vm[h-1].closing && unchanged(d.vm[h-1].chunk[0]->bytes));
    if(stop) d.stop(nullptr);
    else {
        const auto g=accepted(gfx); IOLockLock(d.gpuLock); d.setFence(1,g); IOLockUnlock(d.gpuLock);
        CHECK(gfx.queryExact(g)==Status::Complete && c.queryExact(seq)==Status::Pending && d.gpuRetired()==seq-1);
        IOLockLock(d.gpuLock); d.setFence(0,seq); IOLockUnlock(d.gpuLock);
    }
    pause.release(); t.join(); CHECK(result==!stop && sleepCalls==1 && !frees && !terminations);
    if(stop) CHECK(d.vm[h-1].busy && unchanged(d.vm[h-1].chunk[0]->bytes));
    else {
        CHECK(!d.vm[h-1].busy && d.vm[h-1].generation==gen && !d.vm[h-1].client);
        CHECK(std::all_of(d.vm[h-1].chunk[0]->bytes.begin(),d.vm[h-1].chunk[0]->bytes.begin()+4096,[](uint8_t x){return !x;}));
        CHECK(d.vm[h-1].chunk[0]->bytes[4096]==0xa5 && lineFlushes==64);
        uint64_t next=0; CHECK(d.vmidAlloc(&c,&next)==h && next==gen+1);
    }
}
static void retryCannotAcquireReusedContext() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient waiter,replacement; setup(d,waiter); start(replacement,d);
    std::vector<std::unique_ptr<IOAccelPhxNativeClient>> active;
    for(unsigned i=0;i<8;++i) { active.emplace_back(new IOAccelPhxNativeClient); start(*active.back(),d); (void)accepted(*active.back()); }
    const auto handle=allocate(d,waiter); const auto old=waiter.vmGeneration; Pause pause; bool first=true; int result=-1; uint64_t seq=0;
    std::thread t([&] { eventHook=[&](const char *n){ if(!std::strcmp(n,"sleep") && first) { first=false; pause.arrive(); } };
        result=submit(waiter,seq); eventHook={}; });
    pause.wait(); CHECK(release(d,waiter)); CHECK(allocate(d,replacement)==handle && replacement.vmGeneration==old+1);
    const auto writes=packetWrites.load(); pause.release(); t.join();
    CHECK(result==kIOReturnNotReady && seq==sentinel && packetWrites==writes && !waiter.exactRegistry.occupied());
    CHECK(d.vm[handle-1].busy && !d.vm[handle-1].closing && d.vm[handle-1].client==&replacement && !d.exactVMFault);
}
static void queuedMutationCannotAcquireReplacement(bool unmap) {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c,replacement; setup(d,c); start(replacement,d);
    const auto h=allocate(d,c); const auto gen=c.vmGeneration; IOMemoryDescriptor md;
    Pause pause; bool first=true; int result=-1;
    std::thread t([&] {
        eventHook=[&](const char *n){ if(!std::strcmp(n,"gpu-lock-pointer") && first) { first=false; pause.arrive(); } };
        result=unmap ? d.vmUnmap(h,gen,&c,0x10000,4096) : d.vmMap(h,gen,&c,0x10000,&md,0,4096);
        eventHook={};
    });
    pause.wait(); CHECK(release(d,c)); CHECK(allocate(d,replacement)==h && replacement.vmGeneration==gen+1);
    CHECK(d.vmMap(h,replacement.vmGeneration,&replacement,0x10000,&md,0,4096)==kIOReturnSuccess);
    const auto calls=d.pteCalls; const auto ptes=d.ptes;
    pause.release(); t.join(); CHECK(result==kIOReturnNotReady && d.pteCalls==calls && d.ptes==ptes);
    CHECK(d.vm[h-1].client==&replacement && !d.vm[h-1].closing && !d.exactVMFault);
}
static void reciprocalAndLRU() {
    for(unsigned mode=0;mode<3;++mode) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        std::vector<std::unique_ptr<IOAccelPhxNativeClient>> active;
        for(unsigned i=0;i<8;++i) { active.emplace_back(new IOAccelPhxNativeClient); start(*active.back(),d); (void)accepted(*active.back()); }
        d.setFence(1,d.gSeq); const auto retired=d.gpuRetired(); CHECK(retired==d.gSeq);
        const auto handle=allocate(d,c); const auto before=d.registers.size();
        if(mode) ++d.hwv[0].generation;
        const auto result=mode==2 ? bind(d,active[0]->vmid,active[0]->vmGeneration,active[0].get(),retired)
                                 : bind(d,handle,c.vmGeneration,&c,retired);
        if(mode) CHECK(!result && d.registers.size()==before && d.vm[active[0]->vmid-1].hw==8);
        else {
            CHECK(result==8 && !d.vm[active[0]->vmid-1].hw && d.vm[handle-1].hw==8);
            CHECK(d.hwv[0].ctx==handle && d.hwv[0].generation==c.vmGeneration);
            CHECK(d.registers.size()==before+8); // seven context writes and one TLB request
            CHECK(release(d,*active[0])); // evicted allocation has no hardware backlink
        }
    }
}
static void multichunkCleanupAndReuse() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    for(uint64_t expected=1;expected<=64;++expected) {
        const auto h=allocate(d,c); CHECK(h==1 && c.vmGeneration==expected);
        IOLockLock(d.gpuLock); (void)d.ptTablePhys(d.vm[0],1); d.vm[0].used=17; IOLockUnlock(d.gpuLock);
        CHECK(release(d,c) && !d.vm[0].busy && d.vm[0].generation==expected);
        CHECK(std::all_of(d.vm[0].chunk[0]->bytes.begin(),d.vm[0].chunk[0]->bytes.end(),[](uint8_t x){return !x;}));
        CHECK(std::all_of(d.vm[0].chunk[1]->bytes.begin(),d.vm[0].chunk[1]->bytes.begin()+4096,[](uint8_t x){return !x;}));
        CHECK(d.vm[0].chunk[1]->bytes[4096]==0xa5);
        c.vmid=0; c.vmGeneration=0; // emulate caller clearing identity only after successful VM return
    }
    CHECK(lineFlushes==64*17*64 && d.roots==2 && !d.exactVMFault);
}
static void readoptionDoesNotDrainOldContext() {
    for(bool dual:{false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        const auto compute=accepted(c,false); const auto h=c.vmid,hw=d.vm[h-1].hw;
        if(dual) { const auto gfx=accepted(c); d.setFence(1,gfx); CHECK(c.queryExact(gfx)==Status::Complete); }
        CHECK(c.queryExact(compute)==Status::Pending);
        const uint64_t in[6]={0,1024,8192,0,8,9000};
        CHECK(d.adoptQueue(in)==kIOReturnSuccess); // CPU seed now equals gSeq; old compute is NOT proved drained
        CHECK(c.queryExact(compute)==Status::Lost && d.gpuRetired()==0);
        const auto writes=d.registers.size(); CHECK(!release(d,c));
        CHECK(d.vm[h-1].busy && d.vm[h-1].hw==hw && d.registers.size()==writes);
        CHECK(unchanged(d.vm[h-1].chunk[0]->bytes) && !lineFlushes && !d.exactVMFault);
        uint64_t out=0; CHECK(submit(c,out)==kIOReturnNotReady && out==sentinel);
    }
}
static void checkedTlb() {
    for(unsigned mode=0;mode<6;++mode) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        if(mode==0) { CHECK(!flush(d,7) && !flush(d,16) && d.registers.empty()); continue; }
        if(mode==1) d.ackAfter=3;
        if(mode==2) d.ackBits=1;
        if(mode==3) d.ackBits=0,delayStep=0; // iteration cap even with a stopped CPU clock
        if(mode==4) { d.ackBits=0; eventHook=[&](const char *n){if(!std::strcmp(n,"ack-read")) testTicks+=2000000;}; }
        if(mode==5) { eventHook=[&](const char *n){if(!std::strcmp(n,"ack-read")) d.exactCallbacks.close();}; }
        CHECK(flush(d,8)==(mode==1)); eventHook={};
        CHECK(d.registers.size()==1 && d.registers[0].first==kRegInvEng17Req && d.registers[0].second==(0x00f80000u|257u));
        if(mode==1) CHECK(delays==3 && d.ackReads==4);
        if(mode==2 || mode==3) CHECK(delays==1000 && d.ackReads==1001);
        if(mode==4 || mode==5) CHECK(!delays && d.ackReads==1);
    }
}
static void uncertainTlbNeverReclaims() {
    for(unsigned mode=0;mode<5;++mode) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto seq=accepted(c);
        d.setFence(1,seq); const auto h=c.vmid,hw=d.vm[h-1].hw; const auto gen=c.vmGeneration;
        const auto packets=packetWrites.load(); d.ackBits=0;
        if(mode==1) d.hwv[hw-8].generation++;
        if(mode==2) d.vm[h-1].used=17; // missing second chunk: validate before clearing first
        if(mode==3) d.vm[h-1].used=0;
        if(mode==4) d.vm[h-1].hw=0; // a dangling hardware backlink must not permit unbound cleanup
        CHECK(!release(d,c) && d.vm[h-1].busy && d.vm[h-1].closing);
        CHECK(unchanged(d.vm[h-1].chunk[0]->bytes) && !lineFlushes && d.vm[h-1].generation==gen);
        CHECK(d.hwv[hw-8].ctx==h && packetWrites==packets && !frees && !terminations);
        if(mode==0) {
            CHECK(d.exactVMFault); uint64_t generation=0,out=0;
            CHECK(!d.vmidAlloc(&c,&generation) && !generation && d.gpuRetired()==0);
            CHECK(submit(c,out)==kIOReturnNotReady && out==sentinel);
        } else CHECK(!d.exactVMFault && !delays);
    }
}
static void partialMapAndBindFailures() {
    for(unsigned mode=0;mode<6;++mode) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); auto h=allocate(d,c); IOMemoryDescriptor md;
        if(mode==0) md.failAt=1;
        if(mode==1) d.failPte=true;
        if(mode==2) { const auto seq=accepted(c); d.setFence(1,seq); d.ackBits=0; }
        if(mode==3) md.segment=4095;
        if(mode==4) md.physical++;
        if(mode==5) md.physical=1ull<<48;
        CHECK(d.vmMap(h,c.vmGeneration,&c,0x10000,&md,0,8192)!=kIOReturnSuccess && d.exactVMFault);
        CHECK(d.vm[h-1].busy && unchanged(d.vm[h-1].chunk[0]->bytes));
        const auto before=packetWrites.load(); uint64_t out=0;
        CHECK(submit(c,out)==kIOReturnNotReady && out==sentinel && packetWrites==before);
    }
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto h=allocate(d,c); const auto gen=c.vmGeneration;
    d.ackBits=0; uint64_t out=0;
    CHECK(submit(c,out)==kIOReturnNotReady && out==sentinel && d.exactVMFault);
    CHECK(d.vm[h-1].hw==0 && !d.hwv[0].ctx && !d.hwv[0].generation && d.vm[h-1].generation==gen);
    CHECK(!packetWrites && d.gSeq==99 && !c.exactRegistry.occupied());
}
int main() {
    allocationAndABA(); generationAndCapacity(); queuedAllocationRechecksOutput(); wideIdentityAndRootAdmission();
    mappings(); timeoutRetainsTables();
    progressWhileFreeWaits(false); progressWhileFreeWaits(true); retryCannotAcquireReusedContext();
    queuedMutationCannotAcquireReplacement(false); queuedMutationCannotAcquireReplacement(true);
    reciprocalAndLRU(); multichunkCleanupAndReuse(); readoptionDoesNotDrainOldContext();
    checkedTlb(); uncertainTlbNeverReclaims(); partialMapAndBindFailures();
    CHECK(!clientHeld && !gpuHeld);
    std::printf("PASS staged VM identities and checked cleanup: %llu checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()),groups,threaded);
}
