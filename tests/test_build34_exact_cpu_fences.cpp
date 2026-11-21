// SPDX-License-Identifier: MIT
// Multi-pending CPU fences in actual staged handlers; CPU-only backend.
static int submitFence(IOAccelPhxNativeClient &c,uint32_t handle,uint32_t offset,uint64_t &sequence,bool gfx=true) {
    Request r(gfx); r.h.flags=PHXN_CS_HAS_FENCE; r.h.fence_handle=handle; r.h.fence_offset=offset;
    IOLockLock(c.lock); const int result=c.doSubmit(&r.a); IOLockUnlock(c.lock);
    sequence=r.a.scalarOutput[0]; return result;
}
static uint64_t acceptedFence(IOAccelPhxNativeClient &c,uint32_t handle=1,uint32_t offset=0,bool gfx=true) {
    uint64_t sequence=0; CHECK(submitFence(c,handle,offset,sequence,gfx)==kIOReturnSuccess && sequence!=sentinel);
    return sequence;
}
static void multipleStoresAndSameAddressOrdering() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    const auto first=acceptedFence(c,1,0),second=acceptedFence(c,1,0),third=acceptedFence(c,1,8);
    CHECK(c.cpuFenceCount==3 && c.pendFenceSeq==third && !read64(bytes) && !read64(bytes,8));
    uint64_t out[3]{}; d.setFence(1,first);
    CHECK(wait(c,third,0,out)==kIOReturnSuccess && out[0]==1 && out[1]==first);
    CHECK(read64(bytes)==first && !read64(bytes,8) && c.cpuFenceCount==2 && c.pendFenceSeq==third);
    d.setFence(1,second); CHECK(wait(c,third,0)==kIOReturnSuccess);
    CHECK(read64(bytes)==second && !read64(bytes,8) && c.cpuFenceCount==1);
    d.setFence(1,third); CHECK(wait(c,third,0)==kIOReturnSuccess);
    CHECK(read64(bytes)==second && read64(bytes,8)==third && !c.cpuFenceCount && !c.pendFenceSeq);
    CHECK(!c.pendFenceHandle && !c.pendFenceOffset && c.clientClose()==kIOReturnSuccess);
    c.release(); CHECK(c.finalized && d.refs==1);
}
static void independentQueueCompletionCannotPublishPrefix() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor a,b; std::vector<uint8_t> av(4096),bv(4096); attach(c,1,a,av); attach(c,2,b,bv);
    const auto compute=acceptedFence(c,1,0,false),gfx=acceptedFence(c,2,0,true); CHECK(compute<gfx);
    d.setFence(1,gfx); uint64_t out[3]{};
    CHECK(wait(c,gfx,0,out)==kIOReturnSuccess && out[0]==1 && out[1]<compute);
    CHECK(!read64(av) && !read64(bv) && c.cpuFenceCount==2);
    d.setFence(0,compute); CHECK(wait(c,gfx,0)==kIOReturnSuccess);
    CHECK(read64(av)==compute && read64(bv)==gfx && !c.cpuFenceCount);
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
}
static void partialPublicationBeforeRequestedTimeout() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    const auto first=acceptedFence(c,1,0),second=acceptedFence(c,1,8),last=acceptedFence(c,1,16);
    d.setFence(1,first); unsigned flushes=0; bool progressed=false;
    eventHook=[&](const char *e) {
        if(!std::strcmp(e,"cpu-flush")) ++flushes;
        if(!progressed && !std::strcmp(e,"delay")) { progressed=true; d.setFence(1,second); }
    };
    uint64_t out[3]{}; CHECK(wait(c,last,2000000,out)==kIOReturnSuccess); eventHook={};
    CHECK(out[0]==1 && out[1]==second && progressed && flushes==2);
    CHECK(read64(bytes)==first && read64(bytes,8)==second && !read64(bytes,16) && c.cpuFenceCount==1);
    d.setFence(1,last); CHECK(c.clientClose()==kIOReturnSuccess && read64(bytes,16)==last);
    c.release(); CHECK(c.finalized);
}
static void publicationBeforeHandleReuse() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md,other,replacement; std::vector<uint8_t> bytes(4096),otherBytes(4096),newBytes(4096);
    attach(c,1,md,bytes); attach(c,2,other,otherBytes);
    const auto a=acceptedFence(c,1,0),b=acceptedFence(c,1,8),last=acceptedFence(c,2,0);
    CHECK(boFree(c)==kIOReturnBusy && md.alive && c.cpuFenceCount==3);
    IOLockLock(c.lock); c.releasePermit=&c.bos[1]; CHECK(!c.boRelease(c.bos[1]) && md.alive);
    c.releasePermit=nullptr; IOLockUnlock(c.lock);
    d.setFence(1,last); unsigned releases=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"md-release")) {
        ++releases; CHECK(read64(bytes)==a && read64(bytes,8)==b && read64(otherBytes)==last && !c.cpuFenceCount);
    } };
    CHECK(boFree(c)==kIOReturnSuccess); eventHook={}; CHECK(releases==1 && !md.alive);
    attach(c,1,replacement,newBytes); CHECK(wait(c,last,0)==kIOReturnSuccess);
    CHECK(!read64(newBytes) && !read64(newBytes,8) && !c.pendFenceSeq);
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
}
static void fullLedgerRefusesBeforeDispatchThenCollects() {
    reset(); PhxBringup d; IOAccelPhxNativeClient blocker,c; setup(d,blocker); CHECK(c.start(&d));
    const auto early=accepted(blocker,false);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    uint64_t expected[129]{};
    for(unsigned i=0;i<128;++i) { expected[i]=acceptedFence(c,1,8*i); d.setFence(1,expected[i]); }
    CHECK(c.cpuFenceCount==128 && !read64(bytes) && !read64(bytes,127*8));
    auto seq=d.gSeq; auto writes=packetWrites.load(); uint64_t out=0;
    d.exactDwordReader=nullptr;
    CHECK(submitFence(c,1,128*8,out)==kIOReturnNotReady && out==sentinel && c.cpuFenceCount==128 && d.gSeq==seq);
    d.exactDwordReader=raw32;
    CHECK(submitFence(c,1,128*8,out)==kIOReturnBusy && out==sentinel && !c.boCleanupFault);
    CHECK(d.gSeq==seq && packetWrites==writes && c.cpuFenceCount==128 && !read64(bytes,128*8));
    d.setFence(0,early); expected[128]=acceptedFence(c,1,128*8);
    CHECK(c.cpuFenceCount==1 && expected[128]>seq && !read64(bytes,128*8));
    for(unsigned i=0;i<128;++i) CHECK(read64(bytes,8*i)==expected[i]);
    d.setFence(1,expected[128]); CHECK(wait(c,expected[128],0)==kIOReturnSuccess);
    CHECK(!c.cpuFenceCount && read64(bytes,128*8)==expected[128]);
    CHECK(c.clientClose()==kIOReturnSuccess && blocker.clientClose()==kIOReturnSuccess);
    c.release(); blocker.release(); CHECK(c.finalized && blocker.finalized && d.refs==1);
}
static void boundedLedgerWrapAndReuse() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    for(unsigned batch=0;batch<16;++batch) {
        uint64_t expected[8]{}; uint64_t last=0;
        for(unsigned i=0;i<32;++i) { last=acceptedFence(c,1,8*(i%8)); expected[i%8]=last; }
        CHECK(c.cpuFenceCount==32); d.setFence(1,last); CHECK(wait(c,last,0)==kIOReturnSuccess && !c.cpuFenceCount);
        for(unsigned i=0;i<8;++i) CHECK(read64(bytes,8*i)==expected[i]);
        IOLockLock(c.lock); CHECK(c.checkCpuFences()); IOLockUnlock(c.lock);
    }
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
}
static void invalidFutureRecordPreventsEveryStore() {
    for(unsigned bad=0;bad<11;++bad) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        IOMemoryDescriptor a,b,replaced; std::vector<uint8_t> av(4096),bv(4096),other(4096);
        attach(c,1,a,av); attach(c,2,b,bv);
        const auto first=acceptedFence(c,1,0),second=acceptedFence(c,2,8); d.setFence(1,first);
        auto &later=c.cpuFences[(c.cpuFenceHead+1)%c.kMaxCpuFences];
        if(bad==0) later.md=&replaced;
        if(bad==1) later.kva=other.data();
        if(bad==2) later.size=8192;
        if(bad==3) later.offset=UINT32_MAX;
        if(bad==4) later.offset=3;
        if(bad==3 || bad==4) c.pendFenceOffset=later.offset;
        if(bad==5) later.sequence=first;
        if(bad==6) later.sequence=second+1;
        if(bad==5 || bad==6) c.pendFenceSeq=later.sequence;
        if(bad==7) c.cpuFenceCount=c.kMaxCpuFences+1;
        if(bad==8) c.cpuFenceHead=c.kMaxCpuFences;
        if(bad==9) ++c.pendFenceHandle;
        if(bad==10) c.cpuFences[50].sequence=1;
        const auto count=c.cpuFenceCount; unsigned flushes=0;
        eventHook=[&](const char *e) { if(!std::strcmp(e,"cpu-flush")) ++flushes; };
        CHECK(wait(c,second,0)==kIOReturnNotReady); eventHook={};
        IOLockLock(c.lock); CHECK(!c.publishCpuFence(first)); IOLockUnlock(c.lock);
        CHECK(c.boCleanupFault && c.cpuFenceCount==count && !read64(av) && !read64(bv,8) && !read64(other,8) && !flushes);
        CHECK(a.alive && b.alive && c.clientClose()==kIOReturnNotReady && c.legacyState==5 && c.refs==2);
        c.release(); d.reapLegacyClients(); CHECK(!c.finalized && c.refs==1 && a.alive && b.alive);
    }
}
static void recordCommitFailureRetainsOwnership() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    const auto sequence=acceptedFence(c,1,0);
    // Deliberate CPU bookkeeping fault; not an observed failed GPU dispatch.
    IOLockLock(c.lock); CHECK(!c.appendCpuFence(1,8,sequence)); IOLockUnlock(c.lock);
    CHECK(c.boCleanupFault && c.cpuFenceCount==1 && c.pendFenceSeq==sequence && md.alive && !read64(bytes));
    d.setFence(1,sequence); CHECK(boFree(c)==kIOReturnNotReady && c.clientClose()==kIOReturnNotReady);
    c.release(); d.reapLegacyClients(); CHECK(c.refs==1 && !c.finalized && md.alive);
}
static void userErrorsAndFailedAdmissionPreserveLedger() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    const auto first=acceptedFence(c,1,0); auto writes=packetWrites.load(); auto seq=d.gSeq;
    for(unsigned bad=0;bad<3;++bad) {
        uint64_t out=0; CHECK(submitFence(c,bad==0 ? 99 : 1,bad==1 ? UINT32_MAX : bad==2 ? 3 : 0,out)!=kIOReturnSuccess);
        CHECK(out==sentinel && c.cpuFenceCount==1 && !c.boCleanupFault && d.gSeq==seq && packetWrites==writes);
    }
    const auto old=d.gq[1].ringDw; d.gq[1].ringDw=16; uint64_t out=0;
    CHECK(submitFence(c,1,8,out)==kIOReturnBadArgument && out==sentinel && c.cpuFenceCount==1 && d.gSeq==seq);
    d.gq[1].ringDw=old; d.setFence(1,first); CHECK(wait(c,first,0)==kIOReturnSuccess);
    CHECK(read64(bytes)==first && !read64(bytes,8) && !c.cpuFenceCount && !c.boCleanupFault);
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
}
static void exactAndMockBoundaries() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,true);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes); uint64_t out=0;
    CHECK(submitFence(c,1,0,out)==kIOReturnUnsupported && out==sentinel && !c.vmid && !c.cpuFenceCount && !packetWrites);
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
    reset(); PhxBringup mock; IOAccelPhxNativeClient fake; for(auto &q:mock.gq) q.ready=false; CHECK(fake.start(&mock));
    IOMemoryDescriptor fakeMd; std::vector<uint8_t> fakeBytes(4096); attach(fake,1,fakeMd,fakeBytes);
    CHECK(submitFence(fake,1,0,out)==kIOReturnSuccess && out==1 && read64(fakeBytes)==1 && !fake.cpuFenceCount && !fake.vmid);
    fake.emitted=UINT64_MAX-1; CHECK(submitFence(fake,1,8,out)==kIOReturnNoResources && out==sentinel && !read64(fakeBytes,8));
    CHECK(fake.clientClose()==kIOReturnSuccess); fake.release(); CHECK(fake.finalized);
    reset(); PhxBringup stopped; IOAccelPhxNativeClient old; setup(stopped,old);
    IOMemoryDescriptor held; std::vector<uint8_t> heldBytes(4096); attach(old,1,held,heldBytes); acceptedFence(old,1,0);
    for(auto &q:stopped.gq) q.ready=false;
    CHECK(submitFence(old,1,8,out)==kIOReturnNotReady && out==sentinel && !read64(heldBytes,8) && old.cpuFenceCount==1);
    CHECK(old.clientClose()==kIOReturnNotReady && held.alive && old.legacyClientPinned);
}
static void deferredClosePublishesAllRecords() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor a,b; std::vector<uint8_t> av(4096),bv(4096); attach(c,1,a,av); attach(c,2,b,bv);
    const auto first=acceptedFence(c,1,0),second=acceptedFence(c,2,8);
    CHECK(c.clientClose()==kIOReturnBusy && c.cpuFenceCount==2); c.release();
    PhxBringup::hangTick(&d,nullptr); CHECK(a.alive && b.alive && !read64(av));
    d.setFence(1,second); unsigned released=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"md-release")) {
        ++released; CHECK(read64(av)==first && read64(bv,8)==second && !c.cpuFenceCount && !c.pendFenceSeq);
    } };
    PhxBringup::hangTick(&d,nullptr); eventHook={};
    CHECK(released==2 && c.finalized && !a.alive && !b.alive && d.refs==1);
}
static void queuedWaitCannotWriteReplacement() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md,newMd; std::vector<uint8_t> bytes(4096),newBytes(4096); attach(c,1,md,bytes);
    const auto first=acceptedFence(c,1,0),last=acceptedFence(c,1,8); d.setFence(1,last);
    Pause pause; int result=-1; bool once=true;
    std::thread worker([&] { eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"client-lock-pointer")) { once=false; pause.arrive(); }
    }; result=wait(c,last,0); eventHook={}; });
    pause.wait(); CHECK(boFree(c)==kIOReturnSuccess && read64(bytes)==first && read64(bytes,8)==last);
    attach(c,1,newMd,newBytes); pause.release(); worker.join();
    CHECK(result==kIOReturnSuccess && !read64(newBytes) && !read64(newBytes,8) && !c.cpuFenceCount);
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
}
static void admittedSubmitCommitsAfterClose() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    Pause pause; int result=-1; uint64_t sequence=0; bool once=true;
    std::thread worker([&] { eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"gpu-lock-pointer")) { once=false; pause.arrive(); }
    }; result=submitFence(c,1,8,sequence); eventHook={}; });
    pause.wait(); CHECK(c.clientClose()==kIOReturnBusy && c.cpuFenceCount==0); c.release();
    pause.release(); worker.join();
    CHECK(result==kIOReturnSuccess && c.cpuFenceCount==1 && c.pendFenceSeq==sequence && md.alive && c.refs==1);
    d.setFence(1,sequence); PhxBringup::hangTick(&d,nullptr);
    CHECK(c.finalized && read64(bytes,8)==sequence && !md.alive && d.refs==1);
}
int main() {
    exact_close_regressions(); auto oldChecks=checks.load(); auto oldGroups=groups,oldThreads=threaded;
    multipleStoresAndSameAddressOrdering(); independentQueueCompletionCannotPublishPrefix();
    partialPublicationBeforeRequestedTimeout(); publicationBeforeHandleReuse();
    fullLedgerRefusesBeforeDispatchThenCollects(); boundedLedgerWrapAndReuse();
    invalidFutureRecordPreventsEveryStore(); userErrorsAndFailedAdmissionPreserveLedger();
    recordCommitFailureRetainsOwnership();
    exactAndMockBoundaries(); deferredClosePublishesAllRecords(); queuedWaitCannotWriteReplacement(); admittedSubmitCommitsAfterClose();
    std::printf("PASS staged multiple CPU fences: %llu additional checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()-oldChecks),groups-oldGroups,threaded-oldThreads);
}
