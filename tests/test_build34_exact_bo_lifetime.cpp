// SPDX-License-Identifier: MIT
// Actual staged methods; no SDK, device I/O or GPU execution.
// PHX34_BO_BASE

struct Pause {
    std::mutex mutex; std::condition_variable cv; bool reached=false,resume=false;
    void arrive() { std::unique_lock<std::mutex> l(mutex); reached=true; cv.notify_all();
        CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return resume;})); }
    void wait() { std::unique_lock<std::mutex> l(mutex);
        CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return reached;})); }
    void release() { std::lock_guard<std::mutex> l(mutex); resume=true; cv.notify_all(); }
};
static void reset() {
    CHECK(!clientHeld && !gpuHeld && !eventHook); ++groups;
    packetWrites=frees=terminations=sleepCalls=delays=lineFlushes=0;
    testTicks=10000000; delayStep=1000;
}
static bool raw32(const volatile uint32_t *p,uint32_t *out) { CHECK(gpuHeld==1); *out=*p; return true; }
static void setup(PhxBringup &d,IOAccelPhxNativeClient &c,bool exact=false) {
    for(unsigned qi=0;qi<2;++qi) {
        const uint64_t in[6]={qi ? 4096u : 0u,1024,qi ? 8256u : 8192u,qi ? 8u : 0u,8,(qi ? 9008u : 9000u)|qi};
        CHECK(d.adoptQueue(in)==kIOReturnSuccess);
    }
    d.exactDwordReader=raw32; c.exactRequested=exact; CHECK(c.start(&d));
}
static void attach(IOAccelPhxNativeClient &c,unsigned h,IOMemoryDescriptor &md,std::vector<uint8_t> &bytes,
                   unsigned domain=2,bool host=false,unsigned bits=0) {
    CHECK(h && h<PHXN_MAX_BOS && !c.bos[h].md);
    c.bos[h]={&md,bytes.size(),domain,bits,host ? nullptr : bytes.data(),host};
    uint64_t &used=host ? c.hostUsed : domain==2 ? c.gttUsed : (bits&PHXN_PLACED_HI_POOL) ? c.hiUsed : c.visUsed;
    used+=bytes.size(); md.length=bytes.size();
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
    Request r(gfx); IOLockLock(c.lock); int out=c.doSubmit(&r.a); IOLockUnlock(c.lock);
    seq=r.a.scalarOutput[0]; return out;
}
static uint64_t accepted(IOAccelPhxNativeClient &c,bool gfx=true) {
    uint64_t out; CHECK(submit(c,out,gfx)==kIOReturnSuccess && out!=sentinel); return out;
}
static int gem(IOAccelPhxNativeClient &c,phxn_gem_va &v) {
    IOExternalMethodArguments a; a.scalarOutputCount=0; a.structureInput=&v; a.structureInputSize=sizeof v;
    IOLockLock(c.lock); const int r=c.doGemVa(&a); IOLockUnlock(c.lock); return r;
}
static phxn_gem_va mapping(unsigned h=1,uint64_t va=0x10000,uint64_t off=0,uint64_t size=4096) {
    phxn_gem_va v{}; v.handle=h; v.operation=PHX_AMDGPU_VA_OP_MAP;
    v.va_address=va; v.offset_in_bo=off; v.map_size=size; return v;
}
static int map(IOAccelPhxNativeClient &c,unsigned h=1,uint64_t va=0x10000,uint64_t off=0,uint64_t size=4096) {
    auto v=mapping(h,va,off,size); return gem(c,v);
}
static int unmap(IOAccelPhxNativeClient &c,unsigned h=1,uint64_t va=0x10000) {
    auto v=mapping(h,va); v.operation=PHX_AMDGPU_VA_OP_UNMAP; return gem(c,v);
}
static int boFree(IOAccelPhxNativeClient &c,uint64_t h=1) {
    IOExternalMethodArguments a; a.scalarInputCount=1; a.scalarOutputCount=0; a.scalarInput=&h;
    IOLockLock(c.lock); int r=c.doBoFree(&a); IOLockUnlock(c.lock); return r;
}
static int wait(IOAccelPhxNativeClient &c,uint64_t target,uint64_t timeout,uint64_t *out=nullptr) {
    uint64_t input[3]={target,timeout,0}; IOExternalMethodArguments a;
    a.scalarInputCount=3; a.scalarOutputCount=3; a.scalarInput=input;
    const int r=c.doWaitSeq(&a); if(out) std::copy(a.storage,a.storage+3,out); return r;
}
static uint64_t read64(const std::vector<uint8_t> &bytes,unsigned off=0) {
    uint64_t out; std::memcpy(&out,bytes.data()+off,8); return out;
}
static bool mapsEqual(const IOAccelPhxNativeClient::Map &a,const IOAccelPhxNativeClient::Map &b) {
    return a.used==b.used && a.handle==b.handle && a.va==b.va && a.size==b.size && a.off==b.off && a.flags==b.flags;
}
static void happyBoFree() {
    for(unsigned pool=0;pool<4;++pool) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(8192);
        attach(c,1,md,bytes,pool==0 ? 2 : 1,pool==3,pool==2 ? PHXN_PLACED_HI_POOL : 0);
        CHECK(map(c)==kIOReturnSuccess && map(c,1,0x20000,4096)==kIOReturnSuccess);
        unsigned called=0;
        eventHook=[&](const char *event) {
            if(!std::strcmp(event,"md-complete") || !std::strcmp(event,"md-release")) {
                ++called; CHECK(!c.findBo(1) && !c.maps[0].used && !c.maps[1].used);
                CHECK(!c.hostUsed && !c.gttUsed && !c.hiUsed && !c.visUsed);
                CHECK(!d.ptes[std::make_pair(c.vmid-1,0x10000ull)] && !d.ptes[std::make_pair(c.vmid-1,0x20000ull)]);
                c.boRelease(c.bos[1]); // callback cannot consume this descriptor twice
            }
        };
        CHECK(boFree(c)==kIOReturnSuccess); eventHook={};
        CHECK(!md.alive && md.releases==1 && md.completes==(pool==3) && called==(pool==3 ? 2u : 1u));
        CHECK(boFree(c)==kIOReturnNotFound && !c.boCleanupFault);
    }
}
static void pendingUnmappedBo() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    uint64_t seq=accepted(c); c.lastSeq=0; // authoritative service bound must still protect an UNMAPPED BO
    CHECK(boFree(c)==kIOReturnBusy && md.alive && c.gttUsed==4096 && !c.boCleanupFault);
    uint64_t out=sentinel;
    CHECK(d.vmBoSnapshot(c.vmid,c.vmGeneration,&c,true,&out)==kIOReturnBusy && out==sentinel);
    d.setFence(1,seq); CHECK(boFree(c)==kIOReturnSuccess && !md.alive);
}
static void independentExactIsNotGlobal() {
    reset(); PhxBringup d; IOAccelPhxNativeClient a,c; setup(d,a); CHECK(c.start(&d));
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    const auto compute=accepted(a,false),gfx=accepted(c,true); CHECK(compute<gfx);
    d.setFence(1,gfx); CHECK(boFree(c)==kIOReturnBusy && md.alive);
    d.setFence(0,compute); CHECK(boFree(c)==kIOReturnSuccess);
}
static void busyMappingPreservesMetadata() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(8192); attach(c,1,md,bytes);
    CHECK(map(c)==kIOReturnSuccess); const auto saved=c.maps[0]; const auto seq=accepted(c);
    CHECK(unmap(c)==kIOReturnBusy && mapsEqual(saved,c.maps[0]) && !c.boCleanupFault);
    CHECK(map(c,1,0x20000,4096)==kIOReturnBusy && !c.maps[1].used && !c.boCleanupFault);
    CHECK(boFree(c)==kIOReturnBusy && mapsEqual(saved,c.maps[0]) && md.alive);
    d.setFence(1,seq); CHECK(unmap(c)==kIOReturnSuccess && !c.maps[0].used);
    CHECK(boFree(c)==kIOReturnSuccess);
}
static void failedUnmapKeepsRecords() {
    for(bool freeing : {false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
        CHECK(map(c)==kIOReturnSuccess); const auto saved=c.maps[0]; const auto seq=accepted(c);
        d.setFence(1,seq); d.ackBits=0;
        CHECK((freeing ? boFree(c) : unmap(c))==kIOReturnNotReady);
        CHECK(mapsEqual(saved,c.maps[0]) && c.bos[1].md==&md && md.alive && c.gttUsed==4096);
        CHECK(c.boCleanupFault && d.exactVMFault);
        uint64_t unused; CHECK(submit(c,unused)==kIOReturnNotReady && map(c,1,0x20000)==kIOReturnNotReady);
        Ticket ticket; Receipt receipt; IOLockLock(c.lock);
        CHECK(c.submitExactReceipt(nullptr,0,ticket,receipt)==kIOReturnNotReady);
        c.boRelease(c.bos[1]); IOLockUnlock(c.lock); CHECK(md.alive);
    }
}
static void partialCleanupPoison() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(8192); attach(c,1,md,bytes);
    CHECK(map(c)==kIOReturnSuccess && map(c,1,0x20000,4096)==kIOReturnSuccess);
    const auto first=c.maps[0],second=c.maps[1]; unsigned locks=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"gpu-lock-pointer") && ++locks==3) d.exactStopped=true; };
    CHECK(boFree(c)==kIOReturnNotReady); eventHook={};
    CHECK(locks==3 && c.boCleanupFault && mapsEqual(c.maps[0],first) && mapsEqual(c.maps[1],second));
    CHECK(!d.ptes[std::make_pair(c.vmid-1,0x10000ull)] && d.ptes[std::make_pair(c.vmid-1,0x20000ull)]);
    CHECK(md.alive && c.gttUsed==8192 && boFree(c)==kIOReturnNotReady);
}
static void snapshotProofs() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c,other; setup(d,c);
    IOLockLock(c.lock); CHECK(c.ensureVmid()); IOLockUnlock(c.lock);
    uint64_t out=sentinel;
    CHECK(d.vmBoSnapshot(c.vmid,c.vmGeneration+1,&c,true,&out)==kIOReturnNotReady && out==sentinel);
    CHECK(d.vmBoSnapshot(c.vmid,c.vmGeneration,&other,true,&out)==kIOReturnNotReady && out==sentinel);
    CHECK(d.vmBoSnapshot(0,c.vmGeneration,&c,true,&out)==kIOReturnNotReady && out==sentinel);
    d.exactDwordReader=nullptr;
    CHECK(d.vmBoSnapshot(c.vmid,c.vmGeneration,&c,true,&out)==kIOReturnNotReady && out==sentinel);
    d.exactDwordReader=raw32; d.exactStopped=true;
    CHECK(d.vmBoSnapshot(c.vmid,c.vmGeneration,&c,true,&out)==kIOReturnNotReady && out==sentinel);
}
static void fenceFreeAndReuse() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md,replacement; std::vector<uint8_t> bytes(4096),next(4096);
    attach(c,1,md,bytes); const auto seq=accepted(c);
    c.pendFenceHandle=1; c.pendFenceOffset=8; c.pendFenceSeq=seq;
    CHECK(boFree(c)==kIOReturnBusy && !read64(bytes,8)); d.setFence(1,seq);
    unsigned flushes=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"cpu-flush")) { ++flushes; CHECK(!read64(bytes,8)); } };
    CHECK(boFree(c)==kIOReturnSuccess); eventHook={};
    CHECK(flushes==1 && read64(bytes,8)==seq && !c.pendFenceSeq && !c.pendFenceHandle);
    attach(c,1,replacement,next); CHECK(wait(c,seq,0)==kIOReturnSuccess && !read64(next,8));
    CHECK(boFree(c)==kIOReturnSuccess && replacement.releases==1);
}
static void invalidFenceRetained() {
    for(unsigned invalid=0;invalid<3;++invalid) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
        const auto seq=accepted(c); d.setFence(1,seq); c.pendFenceSeq=seq;
        c.pendFenceHandle=invalid==0 ? 2 : 1; c.pendFenceOffset=invalid==1 ? UINT32_MAX : 0;
        if(invalid==2) c.bos[1].kva=nullptr;
        CHECK(boFree(c)==kIOReturnNotReady && c.boCleanupFault && md.alive && c.pendFenceSeq==seq);
        CHECK(!d.exactVMFault); // client publication failure alone must close dispatch
        uint64_t unused; CHECK(submit(c,unused)==kIOReturnNotReady);
    }
}
static void exactFaultClosesTypedSubmit() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    const auto seq=accepted(c); d.setFence(1,seq); c.pendFenceSeq=seq; c.pendFenceHandle=1;
    CHECK(wait(c,seq,0)==kIOReturnNotReady && c.boCleanupFault && !d.exactVMFault);
    Request request; Ticket ticket; Receipt receipt;
    IOLockLock(c.lock);
    const auto result=c.submitExactReceipt(&request.h,sizeof(request.h)+sizeof(request.ib),ticket,receipt);
    IOLockUnlock(c.lock);
    CHECK(result==kIOReturnNotReady && c.emitted==seq && d.gSeq==seq);
}
static void inputAndAccounting() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    CHECK(boFree(c,(1ull<<32)|1)==kIOReturnBadArgument && md.alive);
    c.gttUsed=4095; CHECK(boFree(c)==kIOReturnBadArgument && md.alive && c.gttUsed==4095); c.gttUsed=4096;
    auto v=mapping(); v.offset_in_bo=UINT64_MAX-4095;
    CHECK(gem(c,v)==kIOReturnBadArgument && !c.vmid && !c.boCleanupFault);
    v=mapping(1,0x10000,0,UINT64_MAX-4095); CHECK(gem(c,v)==kIOReturnBadArgument && !c.vmid);
    CHECK(map(c)==kIOReturnSuccess); c.maps[0].size=UINT64_MAX;
    const auto before=d.pteCalls; CHECK(boFree(c)==kIOReturnBadArgument && d.pteCalls==before && md.alive);
}
static void immutableMapInput() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(8192); attach(c,1,md,bytes);
    auto v=mapping(); unsigned changes=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"segment")) { ++changes; v.handle=7; v.map_size=8192; v.offset_in_bo=4096; } };
    CHECK(gem(c,v)==kIOReturnSuccess); eventHook={};
    CHECK(changes==1 && c.maps[0].handle==1 && c.maps[0].size==4096 && c.maps[0].off==0);
    CHECK(boFree(c)==kIOReturnSuccess);
}
static void failedMapNotPublished() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(8192); attach(c,1,md,bytes);
    md.failAt=1; CHECK(map(c,1,0x10000,0,8192)==kIOReturnVMError);
    CHECK(c.boCleanupFault && d.exactVMFault && !c.maps[0].used && md.alive);
    CHECK(d.ptes[std::make_pair(c.vmid-1,0x10000ull)] && !c.maps[1].used);
}
static void mockAndExactRetention() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    d.gq[0].ready=d.gq[1].ready=false;
    CHECK(map(c)==kIOReturnSuccess && !c.vmid && c.maps[0].used);
    uint64_t seq=accepted(c); CHECK(seq==1 && !c.vmid);
    CHECK(wait(c,PHXN_SEQ_LAST,0)==kIOReturnSuccess && boFree(c)==kIOReturnSuccess);
    reset(); PhxBringup exactDevice; IOAccelPhxNativeClient exact; setup(exactDevice,exact,true);
    IOMemoryDescriptor exactMd; std::vector<uint8_t> exactBytes(4096); attach(exact,1,exactMd,exactBytes);
    CHECK(map(exact)==kIOReturnSuccess); const auto done=accepted(exact); exactDevice.setFence(1,done);
    CHECK(boFree(exact)==kIOReturnBusy && unmap(exact)==kIOReturnBusy && exactMd.alive);
    CHECK(exact.clientClose()==kIOReturnSuccess && !terminations && exact.exactClientPinned);
}
static void waitsAndFailureOutputs() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    const auto seq=accepted(c); uint64_t out[3]{};
    CHECK(wait(c,seq,0,out)==kIOReturnSuccess && out[0]==1 && out[1]<seq && !sleepCalls && !delays);
    CHECK(wait(c,seq,100000,out)==kIOReturnSuccess && out[0]==1 && delays==2);
    unsigned locks=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"client-lock-pointer") && ++locks==1) testTicks+=1000000; };
    CHECK(wait(c,seq,100000,out)==kIOReturnSuccess && out[0]==1 && delays==2 && !sleepCalls);
    eventHook={};
    d.exactDwordReader=nullptr;
    CHECK(wait(c,seq,0,out)==kIOReturnNotReady && out[0]==sentinel && out[1]==sentinel && out[2]==sentinel);
    d.exactDwordReader=raw32; d.setFence(1,seq);
    CHECK(wait(c,seq,0,out)==kIOReturnSuccess && !out[0] && out[1]>=seq && out[2]==seq);
}
static void repeatedReclamation() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    for(unsigned round=0;round<64;++round) {
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
        CHECK(map(c)==kIOReturnSuccess); const auto seq=accepted(c); d.setFence(1,seq);
        CHECK(boFree(c)==kIOReturnSuccess && md.releases==1 && !c.gttUsed && !c.boCleanupFault);
    }
}
static void queuedFreeAfterClose() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    Pause pause; int result=-1;
    std::thread worker([&] { eventHook=[&](const char *e) { if(!std::strcmp(e,"client-lock-pointer")) pause.arrive(); };
        result=boFree(c); eventHook={}; });
    pause.wait(); CHECK(c.clientClose()==kIOReturnSuccess); pause.release(); worker.join();
    CHECK(result==kIOReturnNotReady && md.alive && c.gttUsed==4096 && !terminations);
}
static void queuedSnapshotAfterStop() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes); CHECK(map(c)==kIOReturnSuccess);
    Pause pause; int result=-1;
    std::thread worker([&] { eventHook=[&](const char *e) { if(!std::strcmp(e,"gpu-lock-pointer")) pause.arrive(); };
        result=boFree(c); eventHook={}; });
    pause.wait(); d.exactCallbacks.close(); pause.release(); worker.join();
    CHECK(result==kIOReturnNotReady && c.maps[0].used && md.alive);
}
static void queuedMapAfterPartialFault() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(8192); attach(c,1,md,bytes);
    Pause pause; int result=-1;
    std::thread worker([&] { eventHook=[&](const char *e) { if(!std::strcmp(e,"client-lock-pointer")) pause.arrive(); };
        result=map(c); eventHook={}; });
    pause.wait(); IOLockLock(c.lock); c.boCleanupFault=true; IOLockUnlock(c.lock);
    pause.release(); worker.join(); CHECK(result==kIOReturnNotReady && !c.vmid && md.alive);
}
static void lateWaitAfterRecycledHandle() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor oldMd,newMd; std::vector<uint8_t> oldBytes(4096),newBytes(4096); attach(c,1,oldMd,oldBytes);
    const auto seq=accepted(c); d.setFence(1,seq); c.pendFenceHandle=1; c.pendFenceSeq=seq;
    Pause pause; int result=-1; bool first=true;
    std::thread worker([&] { eventHook=[&](const char *e) { if(first && !std::strcmp(e,"client-lock-pointer")) { first=false; pause.arrive(); } };
        result=wait(c,seq,0); eventHook={}; });
    pause.wait(); CHECK(boFree(c)==kIOReturnSuccess && read64(oldBytes)==seq);
    attach(c,1,newMd,newBytes); pause.release(); worker.join();
    CHECK(result==kIOReturnSuccess && !read64(newBytes) && newMd.alive && !c.pendFenceSeq);
}
int main() {
    happyBoFree(); pendingUnmappedBo(); independentExactIsNotGlobal(); busyMappingPreservesMetadata();
    failedUnmapKeepsRecords(); partialCleanupPoison(); snapshotProofs(); fenceFreeAndReuse(); invalidFenceRetained();
    exactFaultClosesTypedSubmit();
    inputAndAccounting(); immutableMapInput(); failedMapNotPublished(); mockAndExactRetention();
    waitsAndFailureOutputs(); repeatedReclamation(); queuedFreeAfterClose(); queuedSnapshotAfterStop();
    queuedMapAfterPartialFault(); lateWaitAfterRecycledHandle();
    std::printf("PASS staged transactional BO cleanup: %llu checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()),groups,threaded);
}
