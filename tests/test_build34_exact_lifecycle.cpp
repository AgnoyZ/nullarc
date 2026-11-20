// SPDX-License-Identifier: MIT
// This extends the frozen actual-submit fixture; it never opens a device.
// PHX34_LIFECYCLE_SUPPORT
struct Memory;
using IOBufferMemoryDescriptor = Memory;
static std::function<void()> releaseHook;
static std::function<void(uint32_t,uint32_t)> registerHook;
static unsigned releaseCalls, registerWrites, delayCalls, polls;
static int gSysctlUp, gHangKills;
static int sysctl__debug_phxbos_flush, sysctl__debug_phxbos_flush_bytes;
static int sysctl__debug_phx_hang_ms, sysctl__debug_phx_hang_kills;
static constexpr int IOPMAckImplied = 77;
static constexpr uint32_t kRegSqCmd = 0x1260 + 0x111b, kRegRlcSafeMode = 0xa000 + 0x0980;
static void releaseCheck() {
    CHECK(!gpuHeld); ++releaseCalls;
    if (releaseHook) releaseHook();
}
struct IOService { void stop(IOService *) { releaseCheck(); } };
static void thread_call_cancel_wait(void *) { releaseCheck(); }
static void thread_call_free(void *) { releaseCheck(); }
static void sysctl_unregister_oid(int *) { releaseCheck(); }
static void IOLockFree(void *) { releaseCheck(); }
static void OSIncrementAtomic(int *value) { CHECK(gpuHeld); ++*value; }
static void IODelay(unsigned amount) { CHECK(gpuHeld && amount == 1); ++delayCalls; }

// PHX34_LIFECYCLE_MEMBERS
    bool exactQueueLive[2]{true,true}, exactStopped = false, isSleeping = false;
    uint64_t exactInvalidationEpoch = 0;
    void *hangCall = nullptr, *smuLock = nullptr;
    bool hangStop = false;
    Memory *sysBuf = nullptr, *pci = nullptr;
    struct VmCtx { Memory *chunk[2]{}; } vm[2];
    void PMstop() { releaseCheck(); }
    void clearRing() { releaseCheck(); }
    void wreg(uint32_t reg, uint32_t value) {
        CHECK(gpuHeld); ++registerWrites;
        if (registerHook) registerHook(reg,value);
    }
    uint32_t rreg(uint32_t reg) const { CHECK(gpuHeld && reg==kRegRlcSafeMode); return polls++ < 2 ? 1 : 0; }
    IOReturn setPowerState(unsigned long, IOService *);
    void stop(IOService *);
    void killWaves(uint32_t, bool);
    void invalidateExactQueues();

// PHX34_LIFECYCLE_TESTS
static QueueObservation view(PhxBringup &d, unsigned qi, uint64_t submitted, uint64_t completed) {
    return {d.exactQueueGeneration[qi],submitted,completed,
            d.exactQueueLive[qi] && d.gq[qi].ready && !d.exactStopped && !d.isSleeping,false};
}
static Status observe(Registry &r, Ticket t, PhxBringup &d, uint64_t completed) {
    QueueObservation queues[2] = {view(d,0,d.gSeq,completed),view(d,1,d.gSeq,completed)};
    return r.observe(t,!d.exactStopped,queues);
}
static void adopt(PhxBringup &d, unsigned qi) {
    const auto &q = d.gq[qi];
    const uint64_t in[6]={q.ringOff,q.ringDw,q.wbOff,q.dbByte,q.wptr,uint64_t(q.fenceOff)|qi};
    CHECK(d.adoptQueue(in)==kIOReturnSuccess);
}
static void refused(PhxBringup &d, IOAccelPhxNativeClient &c, bool gfx) {
    const auto seq=d.gSeq;
    const auto count0=d.packets[0].size(),count1=d.packets[1].size();
    const auto tail0=d.gq[0].tail,tail1=d.gq[1].tail;
    const auto bell0=d.bells.words[0],bell1=d.bells.words[1];
    const auto entries=c.exactOwnership->occupied(), binds=d.binds;
    Request next(gfx);
    CHECK(next.run(c)==kIOReturnNotReady && next.a.scalarOutput[0]==sentinel);
    CHECK(d.gSeq==seq && d.packets[0].size()==count0 && d.packets[1].size()==count1);
    CHECK(d.gq[0].tail==tail0 && d.gq[1].tail==tail1 && d.binds==binds);
    CHECK(d.bells.words[0]==bell0 && d.bells.words[1]==bell1 && c.exactOwnership->occupied()==entries);
}
static void powerAndFault() {
    for (unsigned action=0;action<3;++action) for (unsigned qi=0;qi<2;++qi) {
        reset(); Registry registry(100+action*2+qi); PhxBringup d;
        IOAccelPhxNativeClient client(&d,&registry); d.expected=&registry;
        Request first(qi); CHECK(first.run(client)==kIOReturnSuccess);
        const auto t=lookup(registry,100);
        const auto before0=d.exactQueueGeneration[0],before1=d.exactQueueGeneration[1];
        CHECK(observe(registry,t,d,99)==Status::Pending);
        if (!action) {
            CHECK(d.setPowerState(0,nullptr)==IOPMAckImplied && d.isSleeping);
            const auto generation=d.exactQueueGeneration[0];
            CHECK(d.setPowerState(0,nullptr)==IOPMAckImplied && d.exactQueueGeneration[0]==generation);
            // Adopting during sleep is refused before geometry/fence reset.
            const auto &q=d.gq[qi];
            const uint64_t in[6]={q.ringOff,q.ringDw,q.wbOff,q.dbByte,q.wptr,uint64_t(q.fenceOff)|qi};
            CHECK(d.adoptQueue(in)==kIOReturnNotReady);
        } else {
            registerWrites=delayCalls=polls=0;
            registerHook=[&](uint32_t, uint32_t) {
                CHECK(!d.exactQueueLive[0] && !d.exactQueueLive[1]);
                CHECK(d.exactQueueGeneration[0]>before0 && d.exactQueueGeneration[1]>before1);
            };
            const auto kills=gHangKills;
            d.killWaves(8,action==2);
            CHECK(registerWrites==3 && delayCalls==2 && gHangKills==kills+1);
            registerHook={};
        }
        CHECK(d.exactQueueGeneration[0]==before0+1 && d.exactQueueGeneration[1]==before1+1);
        CHECK(!d.exactQueueLive[0] && !d.exactQueueLive[1]);
        d.setFence(qi,100); // A post-kill/old-generation fence is NOT completion.
        CHECK(observe(registry,t,d,100)==Status::Lost);
        CHECK(registry.forget(t)==Status::Invalid && registry.cancel(t)==Status::Invalid);
        refused(d,client,false); refused(d,client,true);
        CHECK(d.setPowerState(1,nullptr)==IOPMAckImplied && !d.isSleeping);
        refused(d,client,false); refused(d,client,true); // wake alone cannot reopen
        adopt(d,qi); CHECK(d.exactQueueLive[qi] && !d.exactQueueLive[1-qi]);
        CHECK(observe(registry,t,d,100)==Status::Lost); // sticky loss after fresh adoption
        const auto old=d.gSeq;
        Request fresh(qi); CHECK(fresh.run(client)==kIOReturnSuccess && d.gSeq==old+1);
        CHECK(registry.occupied()==2); refused(d,client,!qi);
    }
}
static void invalidationWhileWaiting() {
    for (unsigned action=0;action<6;++action) {
        reset(); Registry registry(120+action); PhxBringup d;
        IOAccelPhxNativeClient client(&d,&registry); d.expected=&registry;
        fill(d.gq[0]); d.setFence(0,0);
        wake=[&] {
            CHECK(registry.occupied()==1 && !gpuHeld && clientHeld);
            const auto kind=action%3;
            if (!kind) CHECK(d.setPowerState(0,nullptr)==IOPMAckImplied);
            else { registerHook={}; polls=0; d.killWaves(8,kind==2); }
            if (action>=3) {
                CHECK(d.setPowerState(1,nullptr)==IOPMAckImplied);
                adopt(d,0); // New callers may submit, but the OLD waiting request must fail.
                CHECK(d.exactQueueLive[0] && d.exactInvalidationEpoch==1);
            }
            d.setFence(0,99); // Even newly available space must not bypass the gate.
        };
        Request blocked;
        CHECK(blocked.run(client)==kIOReturnNotReady && sleeps==1);
        CHECK(d.gSeq==99 && registry.occupied()==0 && !d.binds && d.packets[0].empty());
        CHECK(blocked.a.scalarOutput[0]==sentinel && client.lastSeq==0 && !d.bells.words[0]);
    }
}
static void terminalStop() {
    reset(); Registry registry(130); PhxBringup d;
    IOAccelPhxNativeClient client(&d,&registry); d.expected=&registry;
    Request first; CHECK(first.run(client)==kIOReturnSuccess); const auto t=lookup(registry,100);
    d.hangCall=&d; gSysctlUp=1; releaseCalls=0;
    const auto before=d.exactQueueGeneration[0];
    bool reentryChecked=false;
    releaseHook=[&] {
        CHECK(d.exactStopped && !d.exactQueueLive[0] && !d.exactQueueLive[1]);
        CHECK(d.exactQueueGeneration[0]==before+1);
        if (!reentryChecked) {
            reentryChecked=true;
            // This is still before release of the aperture/lock: terminal state
            // itself must refuse reopen, not merely later null pointers.
            CHECK(d.fbAper && d.gpuLock);
            CHECK(d.setPowerState(1,nullptr)==IOPMAckImplied);
            const auto &q=d.gq[0];
            const uint64_t in[6]={q.ringOff,q.ringDw,q.wbOff,q.dbByte,q.wptr,q.fenceOff};
            CHECK(d.adoptQueue(in)==kIOReturnNotReady);
            refused(d,client,false);
        }
    };
    d.stop(nullptr); releaseHook={};
    CHECK(reentryChecked && releaseCalls>=10 && d.hangStop && !d.gpuLock && !d.fbAper && !d.mmio);
    CHECK(!d.gq[0].ready && !d.gq[1].ready && registry.occupied()==1);
    // No hardware reads are needed to classify a stopped service.
    CHECK(observe(registry,t,d,100)==Status::Lost && registry.forget(t)==Status::Invalid);
    CHECK(client.lastSeq==100); // unchanged old teardown is not certified safe
}
static void saturationAndLegacy() {
    for (unsigned action=0;action<3;++action) {
        reset(); Registry registry(140+action); PhxBringup d;
        IOAccelPhxNativeClient client(&d,&registry); d.expected=&registry;
        d.exactQueueGeneration[0]=UINT64_MAX-1;
        Request first; CHECK(first.run(client)==kIOReturnSuccess); const auto t=lookup(registry,100);
        if (!action) CHECK(d.setPowerState(0,nullptr)==IOPMAckImplied);
        else { polls=0; d.killWaves(8,action==2); }
        CHECK(d.exactQueueGeneration[0]==UINT64_MAX-1 && !d.exactQueueLive[0]);
        CHECK(observe(registry,t,d,100)==Status::Lost);
        CHECK(d.setPowerState(1,nullptr)==IOPMAckImplied);
        const auto &q=d.gq[0];
        const uint64_t in[6]={q.ringOff,q.ringDw,q.wbOff,q.dbByte,q.wptr,q.fenceOff};
        CHECK(d.adoptQueue(in)==kIOReturnNoResources);
        refused(d,client,false);
    }
    reset(); Registry registry(150); PhxBringup exhausted;
    IOAccelPhxNativeClient c(&exhausted,&registry); exhausted.expected=&registry;
    exhausted.exactInvalidationEpoch=UINT64_MAX-2;
    Request before; CHECK(before.run(c)==kIOReturnSuccess);
    const auto t=lookup(registry,100);
    CHECK(exhausted.setPowerState(0,nullptr)==IOPMAckImplied);
    CHECK(exhausted.exactInvalidationEpoch==UINT64_MAX-1 && exhausted.exactStopped);
    CHECK(exhausted.setPowerState(1,nullptr)==IOPMAckImplied);
    CHECK(exhausted.setPowerState(0,nullptr)==IOPMAckImplied);
    CHECK(exhausted.exactInvalidationEpoch==UINT64_MAX-1 && exhausted.exactStopped);
    CHECK(observe(registry,t,exhausted,100)==Status::Lost);
    refused(exhausted,c,false);
    // Native legacy submissions retain their old behavior; lifecycle gates
    // apply only to the proposed exact branch. This is NOT a safe-drain claim.
    reset(); PhxBringup d; IOAccelPhxNativeClient legacy(&d,nullptr);
    CHECK(d.setPowerState(0,nullptr)==IOPMAckImplied);
    Request r; CHECK(r.run(legacy)==kIOReturnSuccess && d.gSeq==100);
    CHECK(!d.exactQueueLive[0] && !d.exactQueueLive[1]);
}
int main() {
    CHECK(runSubmitRegression()==0);
    const auto baselineChecks=checks,baselineCases=cases;
    powerAndFault(); invalidationWhileWaiting(); terminalStop(); saturationAndLegacy();
    CHECK(!gpuHeld && !clientHeld && !otherClientHeld && !releaseHook && !registerHook);
    std::printf("PASS actual staged lifecycle: %llu additional checks; %llu additional groups; baseline_checks=%llu; baseline_groups=%llu; GPU_executed=false\n",
        (unsigned long long)(checks-baselineChecks),(unsigned long long)(cases-baselineCases),
        (unsigned long long)baselineChecks,(unsigned long long)baselineCases);
}
