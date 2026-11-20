// SPDX-License-Identifier: MIT
// Appended to frozen derived legacy CPU regressions; no SDK/device execution.
static QueueObservation completeQueue(uint64_t generation,uint64_t sequence) {
    return QueueObservation{generation,sequence,sequence,true,false};
}
static Status prove(Registry &r,uint64_t prefix,const QueueObservation q[2]) {
    Receipt owned[2]{};
    for(unsigned qi=0;qi<2;++qi) if(q[qi].submitted) owned[qi]={q[qi].submitted,q[qi].generation,qi};
    return r.proveClosedDrain(prefix,q,owned);
}
static void registryClosedProof() {
    reset(); Registry r(7); Ticket t; Receipt receipt{100,11,1};
    QueueObservation q[2]{completeQueue(22,99),completeQueue(11,100)};
    CHECK(r.reserve(t)==Status::Ok && r.publish(t,receipt)==Status::Ok);
    CHECK(prove(r,100,q)==Status::Invalid && r.retireClosed()==Status::Invalid);
    CHECK(r.pinWait(t)==Status::Ok); r.close();
    CHECK(prove(r,100,q)==Status::Busy && !r.closedDrainProved() && r.occupied()==1);
    CHECK(r.unpinWait(t)==Status::Ok && r.unpinWait(t)==Status::Invalid);
    CHECK(prove(r,99,q)==Status::Pending && !r.closedDrainProved() && r.occupied()==1);
    CHECK(prove(r,100,q)==Status::Ok && r.closedDrainProved() && !r.closedDrained());
    CHECK(r.occupied()==1 && r.retireClosed()==Status::Ok && r.closedDrained() && !r.occupied());
    CHECK(r.retireClosed()==Status::Invalid && prove(r,100,q)==Status::Invalid);
    CHECK(r.reserve(t)==Status::Closed && r.inspect(t,receipt)==Status::Closed);
}
static void registryHistoryAfterAck() {
    for(unsigned bad=0;bad<7;++bad) {
        reset(); Registry r(8); Ticket t; QueueObservation q[2]{};
        q[1]=completeQueue(11,100);
        CHECK(r.reserve(t)==Status::Ok && r.publish(t,{100,11,1})==Status::Ok);
        CHECK(r.observe(t,true,q)==Status::Complete && r.forget(t)==Status::Ok && !r.occupied());
        r.close();
        uint64_t prefix=100;
        if(bad==0) prefix=99;
        if(bad==1) q[1].generation=12;
        if(bad==2) q[1].ready=false;
        if(bad==3) q[1].faulted=true;
        if(bad==4) q[1].completed=99;
        if(bad==5) q[1].submitted=99;
        if(bad==6) prefix=UINT64_MAX;
        const auto expected=(bad==1 || bad==2 || bad==3) ? Status::Lost :
                            (bad==0 || bad==4) ? Status::Pending : Status::InvalidObservation;
        CHECK(prove(r,prefix,q)==expected && !r.closedDrainProved());
        CHECK(r.retireClosed()==Status::Invalid && !r.closedDrained());
    }
    reset(); Registry changed(9); Ticket t; QueueObservation q[2]{}; q[1]=completeQueue(11,100);
    CHECK(changed.reserve(t)==Status::Ok && changed.publish(t,{100,11,1})==Status::Ok);
    CHECK(changed.observe(t,true,q)==Status::Complete && changed.forget(t)==Status::Ok);
    CHECK(changed.reserve(t)==Status::Ok && changed.publish(t,{101,12,1})==Status::Ok);
    q[1]=completeQueue(12,101);
    CHECK(changed.observe(t,true,q)==Status::Complete && changed.forget(t)==Status::Ok);
    changed.close(); CHECK(prove(changed,101,q)==Status::Lost && !changed.closedDrainProved());
    reset(); Registry inconsistent(13); CHECK(inconsistent.reserve(t)==Status::Ok);
    CHECK(inconsistent.publish(t,{100,11,1})==Status::Ok); inconsistent.close();
    Receipt owned[2]{}; owned[1]={100,11,1}; q[1]=completeQueue(11,99);
    CHECK(inconsistent.proveClosedDrain(100,q,owned)==Status::InvalidObservation);
    CHECK(!inconsistent.closedDrainProved() && inconsistent.occupied()==1);
    q[1]=completeQueue(11,100); owned[1]={};
    CHECK(inconsistent.proveClosedDrain(100,q,owned)==Status::InvalidObservation);
    CHECK(!inconsistent.closedDrainProved() && inconsistent.occupied()==1);
}
static void registryReservedLostAndFull() {
    reset(); Registry reserved(10); Ticket t; QueueObservation q[2]{};
    CHECK(reserved.reserve(t)==Status::Ok); reserved.close();
    CHECK(prove(reserved,0,q)==Status::Unsubmitted && reserved.occupied()==1);
    CHECK(reserved.retireClosed()==Status::Invalid && reserved.cancel(t)==Status::Closed);
    reset(); Registry lost(11); q[1]=completeQueue(11,100);
    CHECK(lost.reserve(t)==Status::Ok && lost.publish(t,{100,11,1})==Status::Ok);
    CHECK(lost.observe(t,false,q)==Status::Lost); lost.close();
    CHECK(prove(lost,100,q)==Status::Lost && lost.occupied()==1);
    reset(); Registry full(12); Ticket tickets[64];
    for(unsigned i=0;i<64;++i) {
        CHECK(full.reserve(tickets[i])==Status::Ok);
        CHECK(full.publish(tickets[i],{100+i,i%2 ? 22u : 11u,i%2})==Status::Ok);
    }
    CHECK(full.occupied()==64 && full.reserve(t)==Status::Full);
    q[0]=completeQueue(11,162); q[1]=completeQueue(22,163); full.close();
    CHECK(prove(full,163,q)==Status::Ok && full.occupied()==64);
    CHECK(full.retireClosed()==Status::Ok && !full.occupied());
}
static void exactHealthyPoolsAndProofOrder() {
    for(unsigned pool=0;pool<4;++pool) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096);
        attach(c,1,md,bytes,pool==0 ? 2 : 1,pool==3,pool==2 ? PHXN_PLACED_HI_POOL : 0);
        CHECK(registered(d)==1 && c.refs==2 && d.refs==2 && c.legacyProviderPinned);
        CHECK(map(c)==kIOReturnSuccess); const auto handle=c.vmid; const auto seq=accepted(c); d.setFence(1,seq);
        CHECK(c.exactRegistry.occupied()==1 && boFree(c)==kIOReturnBusy);
        unsigned callbacks=0;
        eventHook=[&](const char *e) { if(!std::strcmp(e,"md-complete") || !std::strcmp(e,"md-release")) {
            ++callbacks;
            CHECK(c.exactRegistry.closedDrainProved() && !c.exactRegistry.closedDrained());
            CHECK(c.exactRegistry.occupied()==1 && !d.vm[handle-1].busy && !c.vmid && !c.vmGeneration && !c.lastSeq);
            CHECK(c.exactClientPinned && c.legacyClientPinned && c.legacyProviderPinned && c.exactReleaseAuthorized);
            CHECK(c.clientClose()==kIOReturnBusy);
        } };
        CHECK(c.clientClose()==kIOReturnSuccess); eventHook={};
        CHECK(callbacks==(pool==3 ? 2u : 1u) && !md.alive && c.exactRegistry.closedDrained());
        CHECK(!c.exactRegistry.occupied() && !c.exactClientPinned && !c.exactReleaseAuthorized && !registered(d));
        CHECK(c.refs==1 && d.refs==2 && c.legacyProviderPinned && c.legacyState==3);
        CHECK(c.queryExact(seq)==Status::Closed && c.ackExact(seq)==Status::Closed);
        CHECK(c.clientClose()==kIOReturnSuccess && terminations==1); c.release();
        CHECK(c.finalized && d.refs==1 && baseFrees==1 && sessionReleases==1);
    }
}
static void exactPendingGpuReaped() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    const auto seq=accepted(c);
    CHECK(c.clientClose()==kIOReturnBusy && c.exactRegistry.occupied()==1 && !c.exactRegistry.closedDrainProved());
    c.release(); PhxBringup::hangTick(&d,nullptr);
    CHECK(!c.finalized && md.alive && c.refs==1 && c.exactClientPinned);
    d.setFence(1,seq); PhxBringup::hangTick(&d,nullptr);
    CHECK(c.finalized && !md.alive && !registered(d) && d.refs==1 && !c.exactRegistry.occupied());
}
static void exactFullReceiptTableAndAckReuse() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    uint64_t last[2]{};
    for(unsigned i=0;i<64;++i) { auto qi=i%2; last[qi]=accepted(c,qi==1); d.setFence(qi,last[qi]); }
    CHECK(c.exactRegistry.occupied()==64); uint64_t refused=0;
    CHECK(submit(c,refused)==kIOReturnNoResources && refused==sentinel && c.exactRegistry.occupied()==64);
    CHECK(c.clientClose()==kIOReturnSuccess && !c.exactRegistry.occupied()); c.release(); CHECK(c.finalized);
    reset(); PhxBringup reuse; IOAccelPhxNativeClient owner; setup(reuse,owner,true);
    for(unsigned i=0;i<128;++i) {
        const auto seq=accepted(owner,i%2); reuse.setFence(i%2 ? 1 : 0,seq);
        CHECK(owner.ackExact(seq)==Status::Ok && !owner.exactRegistry.occupied());
    }
    CHECK(owner.clientClose()==kIOReturnSuccess && owner.exactRegistry.closedDrained());
    owner.release(); CHECK(owner.finalized && reuse.refs==1);
}
static void exactTargetCannotDrainGlobal() {
    reset(); PhxBringup d; IOAccelPhxNativeClient compute,gfx; setup(d,compute); gfx.exactRequested=true; CHECK(gfx.start(&d));
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(gfx,1,md,bytes);
    const auto early=accepted(compute,false),late=accepted(gfx,true); d.setFence(1,late);
    CHECK(gfx.queryExact(late)==Status::Complete && gfx.ackExact(late)==Status::Ok && !gfx.exactRegistry.occupied());
    CHECK(gfx.clientClose()==kIOReturnBusy && md.alive && !gfx.exactRegistry.closedDrainProved());
    d.setFence(0,early); CHECK(gfx.clientClose()==kIOReturnSuccess && !md.alive);
    CHECK(compute.clientClose()==kIOReturnSuccess); gfx.release(); compute.release(); CHECK(d.refs==1);
}
static void exactFaultsRemainPinned() {
    for(unsigned failure=0;failure<5;++failure) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
        CHECK(map(c)==kIOReturnSuccess); const auto seq=accepted(c); d.setFence(1,seq); auto handle=c.vmid;
        if(failure==0) d.ackBits=0;
        if(failure==1) ++d.exactQueueGeneration[1];
        if(failure==2) d.exactDwordReader=nullptr;
        if(failure==3) { d.stop(nullptr); }
        if(failure==4) c.gttUsed=4095;
        CHECK(c.clientClose()==kIOReturnNotReady && c.legacyState==5 && md.alive);
        CHECK(c.exactClientPinned && c.legacyClientPinned && c.legacyProviderPinned && c.refs==2 && d.refs>=2);
        if(failure!=4) CHECK(c.vmid==handle && d.vm[handle-1].busy && c.exactRegistry.occupied()==1);
        c.release(); PhxBringup::hangTick(&d,nullptr);
        CHECK(!c.finalized && md.alive && c.refs==1 && !terminations && !sessionReleases);
    }
}
static void exactPartialPublicationAndReservations() {
    for(bool published : {false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
        IOLockLock(c.lock); CHECK(c.ensureVmid()); Ticket t; CHECK(c.exactRegistry.reserve(t)==Status::Ok);
        // Model the retained boundary after publication but before gSeq/VM newest;
        // do not describe this deliberate CPU injection as an actual GPU failure.
        if(published) CHECK(c.exactRegistry.publish(t,{d.gSeq+1,d.exactQueueGeneration[1],1})==Status::Ok);
        c.exactResourcesExposed=true; IOLockUnlock(c.lock);
        const auto handle=c.vmid; CHECK(!d.vm[handle-1].newest && !c.lastSeq);
        CHECK(c.clientClose()==kIOReturnNotReady && c.legacyState==5);
        CHECK(c.vmid==handle && d.vm[handle-1].busy && md.alive && c.exactRegistry.occupied()==1);
        CHECK(!c.exactRegistry.closedDrainProved() && !c.exactRegistry.closedDrained());
        c.release(); d.reapLegacyClients(); CHECK(c.refs==1 && !c.finalized && md.alive);
    }
}
static void exactSnapshotChecksCallerAndAuthoritativeWork() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    {
        CallbackGate<>::Lease lease(c.exactClientCallbacks); CHECK(lease);
        c.exactClientCallbacks.close(); c.exactRegistry.close();
        uint64_t out=sentinel;
        CHECK(d.exactCloseSnapshot(c.exactRegistry,&c,0,0,0,&out)==kIOReturnNotReady && out==sentinel);
    }
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
    reset(); PhxBringup pending; IOAccelPhxNativeClient owner; setup(pending,owner,true);
    IOLockLock(owner.lock); CHECK(owner.ensureVmid());
    uint64_t va=0x10000,seq=0; uint32_t dw=16;
    // Actual service submission with no receipt: authoritative context work must
    // protect cleanup even when client bookkeeping/receipt metadata is absent.
    CHECK(pending.gpuSubmit(owner.vmid,owner.vmGeneration,&owner,true,&va,&dw,1,&seq,nullptr,{},nullptr)==kIOReturnSuccess);
    IOLockUnlock(owner.lock); owner.exactClientCallbacks.close(); owner.exactRegistry.close();
    uint64_t out=sentinel;
    CHECK(pending.exactCloseSnapshot(owner.exactRegistry,&owner,owner.vmid,owner.vmGeneration,0,&out)==kIOReturnBusy && out==sentinel);
    CHECK(pending.exactCloseSnapshot(owner.exactRegistry,&owner,0,0,0,&out)==kIOReturnNotReady && out==sentinel);
    pending.setFence(1,seq); CHECK(owner.clientClose()==kIOReturnSuccess); owner.release(); CHECK(owner.finalized);
    reset(); PhxBringup reserved; IOAccelPhxNativeClient holder; setup(reserved,holder,true); Ticket ticket;
    CHECK(holder.exactRegistry.reserve(ticket)==Status::Ok); holder.exactClientCallbacks.close(); holder.exactRegistry.close();
    out=sentinel;
    CHECK(reserved.exactCloseSnapshot(holder.exactRegistry,&holder,0,0,0,&out)==kIOReturnNotReady && out==sentinel);
    CHECK(holder.exactRegistry.occupied()==1 && !holder.exactRegistry.closedDrainProved());
}
static void exactHostFailureAndNoPermissionBypass() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    IOMemoryDescriptor md,other; std::vector<uint8_t> bytes(4096),otherBytes(4096);
    attach(c,1,md,bytes,2,true); attach(c,2,other,otherBytes); const auto seq=accepted(c); d.setFence(1,seq);
    c.exactReleaseAuthorized=true; c.legacyReleaseAuthorized=true; c.releasePermit=&c.bos[1];
    CHECK(!c.freeAll() && !c.boRelease(c.bos[1]) && md.alive && !md.completes);
    c.exactReleaseAuthorized=false; c.legacyReleaseAuthorized=false; c.releasePermit=nullptr;
    md.failComplete=true;
    CHECK(c.clientClose()==kIOReturnNotReady && c.legacyState==5 && c.boCleanupFault);
    CHECK(c.releaseHeld.md==&md && md.completes==1 && !md.releases && other.alive);
    CHECK(c.exactRegistry.occupied()==1 && !c.exactRegistry.closedDrained() && !c.exactReleaseAuthorized);
    c.release(); for(unsigned i=0;i<3;++i) d.reapLegacyClients();
    CHECK(!c.finalized && md.completes==1 && !md.releases && other.alive && c.refs==1);
}
static void exactCloseWaitsForAdmittedSubmit() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    Pause pause; Request request; Ticket ticket; Receipt receipt; int result=-1;
    std::thread worker([&] { eventHook=[&](const char *e) { if(!std::strcmp(e,"cpu-flush")) pause.arrive(); };
        IOLockLock(c.lock); result=c.submitExactReceipt(&request.h,sizeof request.h+sizeof request.ib,ticket,receipt);
        IOLockUnlock(c.lock); eventHook={}; });
    pause.wait(); CHECK(c.exactClientCallbacks.active()==1 && c.clientClose()==kIOReturnBusy);
    // Registry is NOT sealed before the admitted submit can publish.
    CHECK(!c.exactRegistry.closedDrainProved()); pause.release(); worker.join();
    CHECK(result==kIOReturnNotReady && !ticket.owner && !receipt.sequence && c.lastSeq==d.gSeq && c.lastSeq>99);
    CHECK(c.exactRegistry.occupied()==1 && c.legacyState==2 && !c.exactRegistry.closedDrained());
    d.setFence(1,c.lastSeq); d.reapLegacyClients(); CHECK(c.legacyState==3 && c.exactRegistry.closedDrained());
    c.release(); CHECK(c.finalized && d.refs==1);
}
static void exactCloseDrainsWaitPinsAndQueuedAck() {
    for(bool ack : {false,true}) {
        reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
        const auto seq=accepted(c); Ticket t; Receipt r;
        IOLockLock(c.lock); CHECK(c.exactRegistry.lookup(seq,t)==Status::Ok && c.exactRegistry.inspect(t,r)==Status::Ok); IOLockUnlock(c.lock);
        Pause pause; Status result=Status::Invalid;
        std::thread worker([&] { eventHook=[&](const char *e) {
            if(!std::strcmp(e,ack ? "client-lock-pointer" : "sleep")) pause.arrive();
        }; result=ack ? c.ackExactReceipt(t,r) : c.waitExactReceipt(t,r,100000000,mach_absolute_time()); eventHook={}; });
        pause.wait(); CHECK(c.exactClientCallbacks.active()==1 && c.clientClose()==kIOReturnBusy);
        eventHook=[&](const char *e) { CHECK(std::strcmp(e,"client-lock-pointer")); };
        CHECK(c.clientClose()==kIOReturnBusy); eventHook={};
        pause.release(); worker.join(); CHECK(result==Status::Closed && !c.exactClientCallbacks.active());
        CHECK(c.exactRegistry.occupied()==1 && c.clientClose()==kIOReturnBusy);
        d.setFence(1,seq); d.reapLegacyClients(); CHECK(c.legacyState==3 && !c.exactRegistry.occupied());
        CHECK(c.waitExactReceipt(t,r,0,0)==Status::Closed && c.ackExactReceipt(t,r)==Status::Closed);
        c.release(); CHECK(c.finalized && d.refs==1);
    }
}
static void exactConcurrentStartAndProviderClose() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; c.exactRequested=true;
    Pause startPause; bool started=false;
    std::thread first([&] { eventHook=[&](const char *e) { if(!std::strcmp(e,"gpu-lock-pointer")) startPause.arrive(); };
        started=c.start(&d); eventHook={}; });
    startPause.wait(); CHECK(!c.start(&d) && c.legacyState==1 && outer(c)==kIOReturnNotReady);
    CHECK(c.queryExact(100)==Status::Closed); startPause.release(); first.join();
    CHECK(started && c.refs==2 && d.refs==2 && registered(d)==1);
    // Empty service with no adopted queue needs a valid global empty proof too.
    for(auto &q:d.gq) q.ready=false;
    d.gSeq=0; for(unsigned qi=0;qi<2;++qi) { d.exactQueueGeneration[qi]=0; d.exactQueueSubmitted[qi]=0; d.exactQueueLive[qi]=false; }
    Pause closePause; int result=-1; bool once=true;
    std::thread early([&] { eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"retain")) { once=false; closePause.arrive(); }
    }; result=c.clientClose(); eventHook={}; });
    closePause.wait(); CHECK(c.clientClose()==kIOReturnSuccess && c.legacyState==3);
    CHECK(d.refs==2 && c.legacyProviderPinned); c.release(); d.release();
    CHECK(c.refs==1 && d.refs==1 && !c.finalized && !d.finalized);
    closePause.release(); early.join(); CHECK(result==kIOReturnSuccess && c.finalized && d.finalized);
}
static void exactRegistrationAdmission() {
    reset(); PhxBringup publishing; IOAccelPhxNativeClient published; unsigned retains=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"retain")) {
        ++retains; CHECK(!registered(publishing) && published.refs==2 &&
                         (retains==1 ? publishing.refs==1 : publishing.refs==2));
    } };
    setup(publishing,published,true); eventHook={}; CHECK(retains==2 && registered(publishing)==1);
    CHECK(published.clientClose()==kIOReturnSuccess); published.release(); CHECK(published.finalized);
    for(unsigned bad=0;bad<4;++bad) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; c.exactRequested=true;
        if(bad==0) d.hangCall=nullptr;
        if(bad==1) d.hangStop=true;
        if(bad==2) d.exactVMFault=true;
        if(bad==3) d.exactCallbacks.close();
        CHECK(!c.start(&d) && c.legacyState==4 && c.refs==1 && d.refs==1 && !registered(d));
        CHECK(!c.exactRegistry.boundTo(&d,&c) && !c.exactClientPinned && !c.legacyProviderPinned);
        c.release(); CHECK(c.finalized);
    }
    reset(); PhxBringup d; std::vector<std::unique_ptr<IOAccelPhxNativeClient>> clients;
    for(unsigned i=0;i<d.kMaxCtx;++i) { clients.emplace_back(new IOAccelPhxNativeClient); CHECK(clients.back()->start(&d)); }
    IOAccelPhxNativeClient full; full.exactRequested=true;
    CHECK(!full.start(&d) && !full.exactRegistry.boundTo(&d,&full) && full.refs==1 && !full.exactClientPinned);
    full.release(); CHECK(full.finalized && registered(d)==d.kMaxCtx);
    for(auto &c:clients) { CHECK(c->clientClose()==kIOReturnSuccess); c->release(); CHECK(c->finalized); }
    CHECK(d.refs==1);
}
int main() {
    legacy_regressions();
    auto before=checks.load(); auto oldGroups=groups,oldThreaded=threaded;
    registryClosedProof(); registryHistoryAfterAck(); registryReservedLostAndFull();
    exactHealthyPoolsAndProofOrder(); exactPendingGpuReaped(); exactTargetCannotDrainGlobal();
    exactFullReceiptTableAndAckReuse();
    exactFaultsRemainPinned(); exactPartialPublicationAndReservations(); exactHostFailureAndNoPermissionBypass();
    exactSnapshotChecksCallerAndAuthoritativeWork();
    exactCloseWaitsForAdmittedSubmit(); exactCloseDrainsWaitPinsAndQueuedAck();
    exactConcurrentStartAndProviderClose(); exactRegistrationAdmission();
    std::printf("PASS staged exact close and reaping: %llu additional checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()-before),groups-oldGroups,threaded-oldThreaded);
}
