// SPDX-License-Identifier: MIT
// Conditional reclamation of actual staged legacy clients, with CPU doubles.
// PHX34_CLOSE_BASE

static unsigned registered(PhxBringup &d) {
    unsigned count=0; for(const auto &slot:d.legacyClients) count+=slot.client!=nullptr; return count;
}
static int outer(IOAccelPhxNativeClient &c,unsigned selector=PHXN_SEL_QUERYINFO) {
    IOExternalMethodArguments a; return c.externalMethod(selector,&a,nullptr,nullptr,nullptr);
}
static void healthyClose() {
    for(unsigned pool=0;pool<4;++pool) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        CHECK(c.refs==2 && d.refs==2 && c.legacyClientPinned && registered(d)==1);
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096);
        attach(c,1,md,bytes,pool==0 ? 2 : 1,pool==3,pool==2 ? PHXN_PLACED_HI_POOL : 0);
        CHECK(map(c)==kIOReturnSuccess); auto handle=c.vmid; const auto seq=accepted(c); d.setFence(1,seq);
        unsigned callbacks=0;
        eventHook=[&](const char *e) { if(!std::strcmp(e,"md-complete") || !std::strcmp(e,"md-release")) {
            ++callbacks; CHECK(!d.vm[handle-1].busy && !c.vmid && !c.vmGeneration && !c.lastSeq);
            CHECK(!c.maps[0].used && !c.bos[1].md && !c.gttUsed && !c.hostUsed && !c.visUsed && !c.hiUsed);
            CHECK(c.clientClose()==kIOReturnBusy); // a callback may not recursively take the client lock
        } };
        CHECK(c.clientClose()==kIOReturnSuccess); eventHook={};
        CHECK(callbacks==(pool==3 ? 2u : 1u) && md.releases==1 && md.completes==(pool==3));
        CHECK(c.legacyState==3 && !c.legacyClientPinned && c.legacyProviderPinned && !registered(d) && c.refs==1 && d.refs==2);
        CHECK(c.clientClose()==kIOReturnSuccess && terminations==1 && sessionReleases==1);
        CHECK(outer(c)==kIOReturnNotReady); c.release();
        CHECK(c.finalized && !c.refs && d.refs==1 && baseFrees==1 && storageFrees==2 && lockFrees==1 && !c.lock);
    }
}
static void pendingGpuAutomaticallyReaped() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    CHECK(map(c)==kIOReturnSuccess); const auto seq=accepted(c); const auto handle=c.vmid;
    c.pendFenceHandle=1; c.pendFenceSeq=seq;
    CHECK(c.clientClose()==kIOReturnBusy && c.legacyClientPinned && c.vmid==handle && md.alive);
    CHECK(!sleepCalls && !terminations && !sessionReleases && c.sessionClaimed && c.refs==2);
    c.release(); CHECK(c.refs==1 && !c.finalized); // user port reference disappears, registration keeps it alive
    PhxBringup::hangTick(&d,nullptr); CHECK(md.alive && c.refs==1 && !c.finalized && hangArms==1);
    d.setFence(1,seq); PhxBringup::hangTick(&d,nullptr);
    CHECK(c.finalized && !c.refs && !registered(d) && md.releases==1 && read64(bytes)==seq);
    CHECK(!c.pendFenceSeq && d.refs==1 && hangArms==2 && hangChecks==2 && terminations==1);
}
static void completeFailureQuarantine() {
    for(bool close : {false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        IOMemoryDescriptor host,other; std::vector<uint8_t> hostBytes(4096),otherBytes(4096);
        attach(c,1,host,hostBytes,2,true); attach(c,2,other,otherBytes); host.failComplete=true;
        CHECK((close ? c.clientClose() : boFree(c))==kIOReturnNotReady);
        CHECK(c.boCleanupFault && c.releaseHeld.md==&host && host.completes==1 && !host.releases && host.alive);
        CHECK(!c.bos[1].md && c.bos[2].md==&other && other.alive && c.legacyClientPinned && c.refs==2);
        CHECK(outer(c,PHXN_SEL_BOCREATE)==kIOReturnNotReady); c.release();
        for(unsigned tick=0;tick<3;++tick) PhxBringup::hangTick(&d,nullptr);
        CHECK(!c.finalized && c.refs==1 && host.completes==1 && !host.releases && other.alive && !terminations);
    }
}
static void vmFailureKeepsTupleAndBos() {
    for(unsigned failure=0;failure<3;++failure) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
        CHECK(map(c)==kIOReturnSuccess); const auto seq=accepted(c); d.setFence(1,seq);
        auto handle=c.vmid; auto generation=c.vmGeneration; auto before=c.maps[0];
        if(failure==0) d.ackBits=0;
        if(failure==1) ++d.exactQueueGeneration[1];
        if(failure==2) d.exactDwordReader=nullptr;
        CHECK(c.clientClose()==kIOReturnNotReady);
        CHECK(c.vmid==handle && c.vmGeneration==generation && d.vm[handle-1].busy && md.alive && c.bos[1].md==&md);
        CHECK(mapsEqual(c.maps[0],before) && c.gttUsed==4096 && c.sessionClaimed && !sessionReleases && !terminations);
        CHECK(c.legacyState==5 && c.refs==2 && d.refs==2);
        c.free(); CHECK(!baseFrees && !storageFrees && !lockFrees); c.release();
        PhxBringup::hangTick(&d,nullptr); CHECK(c.refs==1 && !c.finalized && md.alive);
    }
}
static void exactReleasePermission() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor host,other; std::vector<uint8_t> a(4096),b(4096);
    attach(c,1,host,a,2,true); attach(c,2,other,b);
    IOLockLock(c.lock); CHECK(!c.freeAll() && !c.boRelease(c.bos[1])); IOLockUnlock(c.lock);
    unsigned denied=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"md-complete")) {
        CHECK(!c.releasePermit && c.releaseHeld.md==&host);
        CHECK(!c.boRelease(c.bos[2]) && other.alive && c.bos[2].md==&other); ++denied;
    } };
    CHECK(boFree(c)==kIOReturnSuccess); eventHook={};
    CHECK(denied==1 && host.releases==1 && !c.releaseHeld.md && !c.releasePermit && other.alive);
    CHECK(c.clientClose()==kIOReturnSuccess && other.releases==1); c.release(); CHECK(c.finalized);
}
static void fencePublicationBeforeLiveHandleReuse() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor oldMd,newMd; std::vector<uint8_t> oldBytes(4096),newBytes(4096);
    attach(c,1,oldMd,oldBytes); const auto seq=accepted(c);
    c.pendFenceHandle=1; c.pendFenceOffset=8; c.pendFenceSeq=seq;
    CHECK(boFree(c)==kIOReturnBusy && oldMd.alive && !read64(oldBytes,8));
    d.setFence(1,seq); CHECK(boFree(c)==kIOReturnSuccess && oldMd.releases==1 && read64(oldBytes,8)==seq);
    CHECK(!c.pendFenceSeq && !c.releasePermit && !c.releaseHeld.md);
    attach(c,1,newMd,newBytes); CHECK(wait(c,seq,0)==kIOReturnSuccess && !read64(newBytes,8) && newMd.alive);
    CHECK(c.clientClose()==kIOReturnSuccess && newMd.releases==1); c.release(); CHECK(c.finalized && d.refs==1);
}
static void invalidAccountingRetained() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes); c.gttUsed=4095;
    CHECK(c.clientClose()==kIOReturnNotReady && c.legacyState==5 && c.boCleanupFault && md.alive && c.gttUsed==4095);
    CHECK(!terminations && !sessionReleases && c.sessionClaimed && c.legacyClientPinned);
    c.release(); d.reapLegacyClients(); CHECK(!c.finalized && c.refs==1 && md.alive);
}
static void unstartedAndFailed() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c;
    CHECK(c.clientClose()==kIOReturnNotReady && outer(c)==kIOReturnNotReady);
    CHECK(c.refs==1 && !registered(d)); c.release(); CHECK(c.finalized && baseFrees==1);
    reset(); IOAccelPhxNativeClient failed; baseStartResult=false;
    CHECK(!failed.start(&d) && failed.legacyState==4 && failed.refs==1 && d.refs==1 && !registered(d));
    baseStartResult=true; CHECK(!failed.start(&d)); failed.release(); CHECK(failed.finalized && baseFrees==1);
    reset(); IOService wrong; IOAccelPhxNativeClient foreign;
    CHECK(!foreign.start(&wrong) && foreign.legacyState==4 && !foreign.owner); foreign.release(); CHECK(foreign.finalized);
    for(bool stopped : {false,true}) {
        reset(); PhxBringup unavailable; IOAccelPhxNativeClient refused;
        if(stopped) unavailable.hangStop=true; else unavailable.hangCall=nullptr;
        CHECK(!refused.start(&unavailable) && refused.legacyState==4 && refused.refs==1 && unavailable.refs==1);
        CHECK(!registered(unavailable) && !refused.legacyClientPinned && !refused.legacyProviderPinned);
        refused.release(); CHECK(refused.finalized);
    }
}
static void queuedStartRechecksReaperAvailability() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; Pause pause; bool started=true;
    std::thread worker([&] { eventHook=[&](const char *e) { if(!std::strcmp(e,"gpu-lock-pointer")) pause.arrive(); };
        started=c.start(&d); eventHook={}; });
    pause.wait(); IOLockLock(d.gpuLock); d.hangCall=nullptr; IOLockUnlock(d.gpuLock);
    pause.release(); worker.join(); CHECK(!started && c.legacyState==4 && c.refs==1 && d.refs==1 && !registered(d));
    c.release(); CHECK(c.finalized);
}
static void publicationAfterBothPins() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; unsigned retains=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"retain")) {
        ++retains; CHECK(!registered(d) && c.refs==2 && (retains==1 ? d.refs==1 : d.refs==2));
    } };
    setup(d,c); eventHook={}; CHECK(retains==2 && registered(d)==1);
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
}
static void boundedCapacityAndStartReuse() {
    reset(); PhxBringup d,other;
    std::vector<std::unique_ptr<IOAccelPhxNativeClient>> clients;
    for(unsigned n=0;n<d.kMaxCtx;++n) {
        clients.emplace_back(new IOAccelPhxNativeClient); CHECK(clients.back()->start(&d));
    }
    CHECK(registered(d)==d.kMaxCtx && d.refs==d.kMaxCtx+1);
    IOAccelPhxNativeClient extra; CHECK(!extra.start(&d) && extra.refs==1 && extra.legacyState==4); extra.release();
    auto &first=*clients[0]; CHECK(!first.start(&other) && first.owner==&d && other.refs==1 && !registered(other));
    auto &last=*clients.back();
    { CallbackGate<>::Lease lease(last.exactClientCallbacks); CHECK(last.clientClose()==kIOReturnBusy); }
    d.reapLegacyClients(); CHECK(last.legacyState==3 && registered(d)==d.kMaxCtx-1); // sparse slot at the end
    for(auto &p:clients) { CHECK(p->clientClose()==kIOReturnSuccess); p->release(); CHECK(p->finalized); }
    CHECK(!registered(d) && d.refs==1);
}
static void boundedBatchAndCursor() {
    reset(); PhxBringup d;
    std::vector<std::unique_ptr<IOAccelPhxNativeClient>> clients;
    std::vector<std::unique_ptr<CallbackGate<>::Lease>> leases;
    for(unsigned i=0;i<9;++i) {
        clients.emplace_back(new IOAccelPhxNativeClient); auto &c=*clients.back(); CHECK(c.start(&d));
        leases.emplace_back(new CallbackGate<>::Lease(c.exactClientCallbacks));
        CHECK(*leases.back() && c.clientClose()==kIOReturnBusy); c.release();
    }
    leases.clear(); CHECK(registered(d)==9);
    PhxBringup::hangTick(&d,nullptr); CHECK(registered(d)==5 && baseFrees==4);
    PhxBringup::hangTick(&d,nullptr); CHECK(registered(d)==1 && baseFrees==8);
    PhxBringup::hangTick(&d,nullptr); CHECK(!registered(d) && baseFrees==9 && d.refs==1 && hangArms==3);
}
static void stopRetainsPending() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes); accepted(c);
    CHECK(c.clientClose()==kIOReturnBusy); c.release(); d.stop(nullptr);
    const auto refs=d.refs.load(); PhxBringup::hangTick(&d,nullptr);
    CHECK(c.refs==1 && d.refs==refs && c.legacyClientPinned && md.alive && !c.finalized && !hangArms);
    CHECK(outer(c)==kIOReturnNotReady);
    reset(); PhxBringup idle; IOAccelPhxNativeClient open; CHECK(open.start(&idle)); idle.stop(nullptr);
    CHECK(outer(open)==kIOReturnNotReady && open.refs==2); // service closure alone, not a closed client gate
    IOMemoryDescriptor *out=nullptr; IOOptionBits options=0xdead;
    CHECK(open.clientMemoryForType(1,&options,&out)==kIOReturnNotReady && options==0xdead && !out);
}
static void exactStillQuarantined() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    CHECK(!registered(d) && c.exactClientPinned && c.refs==2 && d.refs==2);
    CHECK(c.clientClose()==kIOReturnSuccess && !terminations); c.release();
    PhxBringup::hangTick(&d,nullptr); CHECK(md.alive && c.refs==1 && c.exactClientPinned && !c.finalized);
}
static void callbackDrainWithoutLockWait() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    Pause pause; int result=-1;
    std::thread worker([&] { eventHook=[&](const char *e) { if(!std::strcmp(e,"dispatch")) pause.arrive(); };
        result=outer(c); eventHook={}; });
    pause.wait(); eventHook=[&](const char *e) { CHECK(std::strcmp(e,"client-lock-pointer")); };
    CHECK(c.exactClientCallbacks.active()==1 && c.clientClose()==kIOReturnBusy && !terminations); eventHook={};
    CHECK(c.legacyClientPinned && c.refs==2); pause.release(); worker.join(); CHECK(result==kIOReturnSuccess);
    CHECK(outer(c)==kIOReturnNotReady); PhxBringup::hangTick(&d,nullptr);
    CHECK(c.legacyState==3 && c.refs==1 && !registered(d)); c.release(); CHECK(c.finalized);
}
static void queuedOuterEntryRefusesAfterClose() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    Pause pause; int result=-1; unsigned dispatched=0;
    std::thread worker([&] { eventHook=[&](const char *e) {
        if(!std::strcmp(e,"client-lock-pointer")) pause.arrive();
        if(!std::strcmp(e,"dispatch")) ++dispatched;
    }; result=outer(c); eventHook={}; });
    pause.wait(); CHECK(c.clientClose()==kIOReturnBusy); pause.release(); worker.join();
    CHECK(result==kIOReturnNotReady && !dispatched); d.reapLegacyClients(); c.release(); CHECK(c.finalized);
}
static void queuedMemoryEntryRefusesAfterClose() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    Pause pause; int result=-1; IOMemoryDescriptor *out=nullptr; IOOptionBits options=0xdead;
    std::thread worker([&] { eventHook=[&](const char *e) { if(!std::strcmp(e,"client-lock-pointer")) pause.arrive(); };
        result=c.clientMemoryForType(1,&options,&out); eventHook={}; });
    pause.wait(); CHECK(c.clientClose()==kIOReturnBusy); pause.release(); worker.join();
    CHECK(result==kIOReturnNotReady && !out && options==0xdead && !md.retains);
    d.reapLegacyClients(); CHECK(md.releases==1 && c.legacyState==3); c.release(); CHECK(c.finalized);
}
static void concurrentStartSingleRegistration() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c;
    Pause pause; bool a=false,b=false;
    std::thread first([&] { eventHook=[&](const char *e) { if(!std::strcmp(e,"gpu-lock-pointer")) pause.arrive(); };
        a=c.start(&d); eventHook={}; });
    pause.wait(); std::thread second([&] { b=c.start(&d); }); second.join();
    CHECK(!b && c.legacyState==1 && outer(c)==kIOReturnNotReady); pause.release(); first.join();
    CHECK(a && c.refs==2 && d.refs==2 && registered(d)==1);
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
}
static void selectedClientPinSurvivesCompetingClose() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    { CallbackGate<>::Lease lease(c.exactClientCallbacks); CHECK(lease); CHECK(c.clientClose()==kIOReturnBusy); }
    c.release(); CHECK(c.refs==1);
    Pause pause; bool first=true;
    std::thread reaper([&] { eventHook=[&](const char *e) { if(first && !std::strcmp(e,"client-lock-pointer")) { first=false; pause.arrive(); } };
        d.reapLegacyClients(); eventHook={}; });
    pause.wait(); CHECK(c.refs==2); CHECK(c.clientClose()==kIOReturnBusy); // one-reaper claim prevents concurrent cleanup
    pause.release(); reaper.join();
    CHECK(c.finalized && !c.refs && !registered(d) && terminations==1 && !c.legacyReaping);
}
static void providerOutlivesConcurrentClose() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    Pause pause; int result=-1; bool first=true;
    std::thread early([&] { eventHook=[&](const char *e) {
        if(first && !std::strcmp(e,"retain")) { first=false; pause.arrive(); }
    }; result=c.clientClose(); eventHook={}; });
    pause.wait(); CHECK(c.refs==3 && c.clientClose()==kIOReturnSuccess);
    CHECK(c.legacyState==3 && c.refs==2 && d.refs==2 && c.legacyProviderPinned);
    c.release(); d.release(); // only the earlier close's client reference and its provider ownership remain
    CHECK(c.refs==1 && d.refs==1 && !c.finalized && !d.finalized);
    pause.release(); early.join();
    CHECK(result==kIOReturnSuccess && c.finalized && d.finalized && !c.refs && !d.refs);
}
int main() {
    healthyClose(); pendingGpuAutomaticallyReaped(); completeFailureQuarantine(); vmFailureKeepsTupleAndBos();
    exactReleasePermission(); fencePublicationBeforeLiveHandleReuse();
    invalidAccountingRetained(); unstartedAndFailed(); boundedCapacityAndStartReuse();
    publicationAfterBothPins();
    boundedBatchAndCursor(); stopRetainsPending(); exactStillQuarantined(); callbackDrainWithoutLockWait();
    queuedMemoryEntryRefusesAfterClose(); concurrentStartSingleRegistration(); selectedClientPinSurvivesCompetingClose();
    queuedOuterEntryRefusesAfterClose();
    providerOutlivesConcurrentClose();
    queuedStartRechecksReaperAvailability();
    std::printf("PASS staged legacy close and reaping: %llu checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()),groups,threaded);
}
