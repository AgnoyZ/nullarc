// SPDX-License-Identifier: MIT
// Actual staged watchdog/submit/lifetime methods. Registers and time are CPU doubles.
static unsigned wdCommands(const PhxBringup &d) {
    unsigned n=0; for(const auto &r:d.registers) n+=r.first==kRegSqCmd; return n;
}
static uint32_t wdLastCommand(const PhxBringup &d) {
    for(auto i=d.registers.rbegin();i!=d.registers.rend();++i) if(i->first==kRegSqCmd) return i->second;
    return UINT32_MAX;
}
static int wdAdopt(PhxBringup &d,unsigned qi=1) {
    const uint64_t in[6]={qi ? 4096u : 0u,1024,qi ? 8256u : 8192u,qi ? 8u : 0u,8,(qi ? 9008u : 9000u)|qi};
    return d.adoptQueue(in);
}
static bool wdRaw(const volatile uint32_t *p,uint32_t *v) {
    CHECK(gpuHeld==1); event("wd-read"); *v=*p; return true;
}
static void wdArm(PhxBringup &d) {
    gHangMs=1; d.hangCheck(); CHECK(!d.watchdogRecovery.active && !wdCommands(d));
}
static void wdFire(PhxBringup &d) {
    testTicks+=1000000; d.hangCheck();
}
static void wdTargeted(PhxBringup &d) {
    wdArm(d); wdFire(d);
    CHECK(d.watchdogRecovery.active && !d.watchdogRecovery.terminal && d.exactVMFault && gHangKills==1);
    CHECK(wdCommands(d)==1 && d.rlcEnters==1 && d.rlcExits==1 && !d.rlcEntered);
}
static void wdIdleAndDisabled() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    for(int setting : {-1,0,1,3000}) {
        gHangMs=setting;
        for(unsigned i=0;i<4;++i) { testTicks+=4000000000ull; d.hangCheck(); }
        CHECK(!d.watchdogRecovery.active && !wdCommands(d) && !d.rlcEnters && !gHangKills);
    }
    gHangMs=1; d.mmio=nullptr; d.hangCheck(); CHECK(!wdCommands(d));
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized);
}
static void wdTagsLockAndHighDword() {
    for(bool gfx : {false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto seq=accepted(c,gfx);
        const unsigned qi=gfx ? 1 : 0; auto &q=d.gq[qi]; const unsigned slot=(q.tail-1)&63;
        CHECK(q.fctx[slot]==c.vmid && q.fallocation[slot]==c.vmGeneration && q.fvmid[slot]==d.vm[c.vmid-1].hw);
        d.setFence(qi,0xfedcba9800000063ull); // malicious high dword must never become completion
        unsigned protectedReads=0,writes=0;
        eventHook=[&](const char *e) {
            if(!std::strcmp(e,"map-address")) { CHECK(gpuHeld==1); ++protectedReads; }
            if(!std::strcmp(e,"rlc-enter") || !std::strcmp(e,"sq-write")) {
                ++writes; CHECK(gpuHeld==1 && d.exactVMFault && !d.exactQueueLive[0] && !d.exactQueueLive[1]);
            }
        };
        wdTargeted(d); eventHook={};
        CHECK(protectedReads && writes==2 && d.watchdogRecovery.sequence==seq && d.watchdogRecovery.queue==qi);
        CHECK(wdLastCommand(d)==(0x13u|0x80u|(d.vm[c.vmid-1].hw<<28)) && q.killedSeq==seq);
        CHECK(d.exactQueueGeneration[qi]==d.watchdogRecovery.generation+1);
    }
}
static void wdProgressAndFullFirstThreshold() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    const auto first=accepted(c),last=accepted(c); wdArm(d);
    testTicks+=999999; d.hangCheck(); CHECK(!wdCommands(d));
    d.setFence(1,first); d.hangCheck(); CHECK(d.gq[1].lastDone==first && d.gq[1].lastProgress==testTicks);
    testTicks+=999999; d.hangCheck(); CHECK(!wdCommands(d));
    ++testTicks; d.hangCheck();
    CHECK(wdCommands(d)==1 && d.watchdogRecovery.sequence==last && d.watchdogRecovery.slot==1);
}
static void wdIdleTimeNeverCountsAgainstNewWork() {
    for(bool zeroSeed : {false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        if(zeroSeed) { d.gSeq=0; CHECK(wdAdopt(d,0)==kIOReturnSuccess && wdAdopt(d,1)==kIOReturnSuccess); }
        testTicks+=3600000000000ull; gHangMs=1; bool delayed=false;
        eventHook=[&](const char *e) {
            if(!delayed && !std::strcmp(e,"map-address") && d.gq[1].tail!=d.gq[1].head) {
                delayed=true; testTicks+=3600000000000ull; // CPU preemption after history, before doorbell
            }
        };
        const auto first=accepted(c); eventHook={}; CHECK(delayed);
        d.hangCheck(); CHECK(!wdCommands(d) && d.gq[1].lastProgress==testTicks);
        testTicks+=999999; d.hangCheck(); CHECK(!wdCommands(d));
        d.setFence(1,first); testTicks+=3600000000000ull; const auto second=accepted(c);
        CHECK(second>first); d.hangCheck(); CHECK(!wdCommands(d) && d.gq[1].lastDone==first);
        testTicks+=999999; d.hangCheck(); CHECK(!wdCommands(d));
        ++testTicks; d.hangCheck(); CHECK(wdCommands(d)==1 && d.watchdogRecovery.sequence==second);
    }
}
static void wdIndependentQueues() {
    reset(); PhxBringup d; IOAccelPhxNativeClient compute,gfx; setup(d,compute); CHECK(gfx.start(&d));
    const auto a=accepted(compute,false),b=accepted(gfx,true); CHECK(a<b); d.setFence(1,b);
    wdTargeted(d); CHECK(d.watchdogRecovery.sequence==a && d.watchdogRecovery.queue==0);
    CHECK(d.watchdogRecovery.client==&compute && wdLastCommand(d)==(0x93u|(d.vm[compute.vmid-1].hw<<28)));
}
static void wdInvalidSnapshotRefuses() {
    for(unsigned bad=0;bad<34;++bad) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto seq=accepted(c); wdArm(d);
        auto &q=d.gq[1]; auto &v=d.vm[c.vmid-1]; auto &hw=d.hwv[v.hw-8]; const auto slot=(q.tail-1)&63;
        if(bad==0) d.exactDwordReader=nullptr;
        if(bad==1) d.exactDwordReader=[](const volatile uint32_t *,uint32_t *) { return false; };
        if(bad==2) d.setFence(1,seq+1);
        if(bad==3) q.tail=q.head+64;
        if(bad==4) q.fseq[slot]=0;
        if(bad==5) q.fseq[slot]=seq+1;
        if(bad==6) q.fctx[slot]=0;
        if(bad==7) q.fctx[slot]=d.kMaxCtx+1;
        if(bad==8) ++q.fallocation[slot];
        if(bad==9) q.fvmid[slot]=7;
        if(bad==10) q.fvmid[slot]=16;
        if(bad==11) v.busy=false;
        if(bad==12) ++v.generation;
        if(bad==13) v.client=nullptr;
        if(bad==14) ++v.hw;
        if(bad==15) hw.ctx=0;
        if(bad==16) ++hw.generation;
        if(bad==17) ++hw.lastSeq;
        if(bad==18) v.queueSequence[1]=seq-1;
        if(bad==19) ++v.queueGeneration[1];
        if(bad==20) q.ringDw=16;
        if(bad==21) q.ringOff=UINT32_MAX;
        if(bad==22) q.wbOff=UINT32_MAX;
        if(bad==23) q.fenceOff=UINT32_MAX;
        if(bad==24) q.dbByte=UINT64_MAX-7;
        if(bad==25) q.fend[slot]=q.wptr+1;
        if(bad==26) q.fend[slot]=q.doneEnd;
        if(bad==27) q.gfx=false;
        if(bad==28) d.mmioStorage.length=4;
        if(bad==29) d.mmioStorage.addressOverride=UINTPTR_MAX-3;
        if(bad==30) d.exactStopped=true;
        if(bad==31) d.isSleeping=true;
        if(bad==32) d.hangStop=true;
        if(bad==33) d.exactCallbacks.close();
        wdFire(d); CHECK(!wdCommands(d) && !d.rlcEnters && !gHangKills && !d.watchdogRecovery.active);
    }
}
static void wdCompletedHistoryMayOutliveAllocation() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c,other; setup(d,c); const auto seq=accepted(c);
    const auto handle=c.vmid; const auto generation=c.vmGeneration; d.setFence(1,seq);
    CHECK(c.clientClose()==kIOReturnSuccess); c.release(); CHECK(c.finalized && !d.vm[handle-1].busy);
    gHangMs=1; d.hangCheck(); testTicks+=1000000; d.hangCheck(); CHECK(!wdCommands(d));
    CHECK(other.start(&d)); const auto next=accepted(other); CHECK(next>seq && other.vmid==handle && other.vmGeneration>generation);
    CHECK(d.gq[1].fctx[(d.gq[1].tail-1)&63]==handle && d.gq[1].fallocation[(d.gq[1].tail-1)&63]==other.vmGeneration);
    d.setFence(1,next); CHECK(other.clientClose()==kIOReturnSuccess); other.release(); CHECK(other.finalized);
}
static void wdRlcReadAndMonotonicBounds() {
    for(unsigned variant=0;variant<5;++variant) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); accepted(c); wdArm(d);
        d.rlcAfter=variant==0 ? 3 : UINT32_MAX;
        if(variant==2) delayStep=2000000;
        if(variant==3) delayStep=0; // a broken/stalled clock still has a finite read bound
        if(variant==4) eventHook=[&](const char *e) { if(!std::strcmp(e,"rlc-ack")) testTicks+=2000000; };
        wdFire(d); eventHook={};
        CHECK(d.rlcEnters==1 && d.rlcExits==1 && !d.rlcEntered && d.exactVMFault);
        if(variant==0) CHECK(gHangKills==1 && d.rlcReads==4 && !d.watchdogRecovery.terminal);
        else {
            CHECK(!gHangKills && !wdCommands(d) && d.watchdogRecovery.terminal);
            CHECK(d.rlcReads==(variant==2 || variant==4 ? 1u : 1000u));
            auto reads=d.rlcReads; for(unsigned i=0;i<4;++i) wdFire(d);
            CHECK(d.rlcReads==reads && d.rlcEnters==1);
        }
    }
}
static void wdObservedClosePairsExit() {
    for(unsigned when=0;when<7;++when) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); accepted(c); wdArm(d);
        d.exactDwordReader=wdRaw; bool closed=false;
        eventHook=[&](const char *e) {
            const bool atRead=when==0 && !std::strcmp(e,"wd-read") && d.watchdogRecovery.active;
            const bool atClock=when==1 && !std::strcmp(e,"clock") && d.watchdogRecovery.active && !d.rlcEntered;
            const bool atEnter=when==2 && !std::strcmp(e,"rlc-enter");
            const bool atAck=when==3 && !std::strcmp(e,"rlc-ack");
            const bool beforeSq=when==4 && !std::strcmp(e,"wd-read") && d.rlcEntered;
            const bool atDelay=when==5 && !std::strcmp(e,"delay") && d.rlcEntered;
            const bool afterSq=when==6 && !std::strcmp(e,"sq-write");
            if(!closed && (atRead || atClock || atEnter || atAck || beforeSq || atDelay || afterSq)) { closed=true; d.exactCallbacks.close(); }
        };
        if(when==5) d.rlcAfter=1;
        wdFire(d); eventHook={};
        CHECK(closed && gHangKills==(when==6 ? 1 : 0) && wdCommands(d)==(when==6 ? 1u : 0u) &&
              d.watchdogRecovery.active && d.watchdogRecovery.terminal);
        CHECK(d.rlcEnters==(when<2 ? 0u : 1u) && d.rlcExits==d.rlcEnters && !d.rlcEntered && d.exactCallbacks.drained());
    }
}
static void wdCompletionDuringRlcCancelsCommand() {
    for(bool global : {false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto seq=accepted(c);
        if(global) wdTargeted(d); else wdArm(d);
        eventHook=[&](const char *e) { if(!std::strcmp(e,"rlc-ack")) d.setFence(1,seq); };
        wdFire(d); eventHook={};
        CHECK(wdCommands(d)==(global ? 1u : 0u) && d.watchdogRecovery.terminal && d.exactVMFault);
        CHECK(d.rlcEnters==(global ? 2u : 1u) && d.rlcExits==d.rlcEnters && !d.rlcEntered);
    }
}
static void wdSecondFullThresholdAndSingleEscalation() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); accepted(c); wdTargeted(d);
    testTicks+=500000; d.hangCheck(); CHECK(wdCommands(d)==1 && !d.watchdogRecovery.globalAttempted);
    testTicks+=499999; d.hangCheck(); CHECK(wdCommands(d)==1);
    ++testTicks; d.hangCheck(); CHECK(wdCommands(d)==2 && wdLastCommand(d)==0x13 && gHangKills==2);
    CHECK(d.watchdogRecovery.globalAttempted && d.watchdogRecovery.terminal && d.rlcEnters==2 && d.rlcExits==2);
    auto reads=d.rlcReads; for(unsigned i=0;i<10;++i) wdFire(d);
    CHECK(wdCommands(d)==2 && d.rlcReads==reads && d.exactVMFault);
}
static void wdNoPostRecoveryCompletionOrRelease() {
    for(bool exact : {false,true}) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,exact);
        IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
        const auto seq=exact ? accepted(c) : acceptedFence(c,1,8); wdTargeted(d);
        const auto gen=d.exactQueueGeneration[1]; d.setFence(1,seq);
        d.hangCheck(); CHECK(d.watchdogRecovery.terminal && wdCommands(d)==1 && d.exactVMFault);
        CHECK(!d.gpuRetired() && !read64(bytes,8) && md.alive && !md.completes && !md.releases);
        if(exact) CHECK(c.queryExact(seq)==Status::Lost);
        else CHECK(wait(c,seq,0)==kIOReturnNotReady && c.cpuFenceCount==1);
        CHECK(boFree(c)==(exact ? kIOReturnBusy : kIOReturnNotReady));
        CHECK(c.clientClose()==kIOReturnNotReady);
        c.release(); d.reapLegacyClients(); CHECK(!c.finalized && c.refs==1 && md.alive && d.vm[c.vmid-1].busy);
        CHECK(d.exactQueueGeneration[1]==gen && !d.exactQueueLive[0] && !d.exactQueueLive[1]);
    }
}
static void wdRecoveryIdentityFailuresAreTerminal() {
    for(unsigned bad=0;bad<40;++bad) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto seq=accepted(c); wdTargeted(d);
        auto &w=d.watchdogRecovery; auto &q=d.gq[1]; auto &v=d.vm[c.vmid-1]; auto &hw=d.hwv[v.hw-8];
        Memory replacement;
        if(bad==0) d.exactDwordReader=nullptr;
        if(bad==1) d.exactDwordReader=[](const volatile uint32_t *,uint32_t *) { return false; };
        if(bad==2) d.setFence(1,seq+1);
        if(bad==3) { replacement.addressOverride=w.base; replacement.length=w.length; d.fbAper=&replacement; }
        if(bad==4) { replacement.addressOverride=w.registerBase; replacement.length=w.registerLength; d.mmio=&replacement; }
        if(bad==5) { replacement.addressOverride=w.doorbellBase; replacement.length=w.doorbellLength; d.doorbellMap=&replacement; }
        if(bad==6) --d.aperture.length;
        if(bad==7) --d.mmioStorage.length;
        if(bad==8) --d.bells.length;
        if(bad==9) --d.fbAperLen;
        if(bad==10) ++d.exactInvalidationEpoch;
        if(bad==11) ++d.exactQueueGeneration[0];
        if(bad==12) ++d.exactQueueSubmitted[0];
        if(bad==13) d.exactQueueLive[0]=true;
        if(bad==14) ++q.head;
        if(bad==15) ++q.tail;
        if(bad==16) q.ready=false;
        if(bad==17) q.gfx=false;
        if(bad==18) ++q.ringOff;
        if(bad==19) q.ringDw*=2;
        if(bad==20) q.wbOff+=8;
        if(bad==21) q.fenceOff+=8;
        if(bad==22) q.dbByte+=8;
        if(bad==23) ++q.wptr;
        if(bad==24) ++q.doneEnd;
        if(bad==25) ++q.fseq[w.slot];
        if(bad==26) ++q.fend[w.slot];
        if(bad==27) ++q.fctx[w.slot];
        if(bad==28) ++q.fallocation[w.slot];
        if(bad==29) ++q.fvmid[w.slot];
        if(bad==30) v.client=&replacement;
        if(bad==31) ++v.generation;
        if(bad==32) ++v.hw;
        if(bad==33) ++v.newest;
        if(bad==34) ++hw.ctx;
        if(bad==35) ++hw.generation;
        if(bad==36) ++hw.lastSeq;
        if(bad==37) ++v.queueSequence[0];
        if(bad==38) ++v.queueGeneration[0];
        if(bad==39) d.isSleeping=true;
        wdFire(d); CHECK(w.terminal && wdCommands(d)==1 && d.rlcEnters==1 && d.rlcExits==1 && d.exactVMFault);
        auto reads=d.rlcReads; wdFire(d); CHECK(d.rlcReads==reads && wdCommands(d)==1);
    }
}
static void wdDisabledEpisodeDoesNotResume() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); accepted(c); wdTargeted(d);
    gHangMs=0; d.hangCheck(); CHECK(d.watchdogRecovery.terminal);
    gHangMs=1; wdFire(d); CHECK(wdCommands(d)==1 && d.rlcEnters==1);
}
static void wdDiagnosticFailurePreservesOutput() {
    for(unsigned failure=0;failure<4;++failure) {
        reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto seq=accepted(c);
        d.exactDwordReader=wdRaw; wdTargeted(d); uint64_t completed=sentinel;
        if(failure==0) d.setFence(1,seq+1);
        if(failure==1) eventHook=[&](const char *e) { if(!std::strcmp(e,"wd-read")) d.exactCallbacks.close(); };
        if(failure==2) eventHook=[&](const char *e) { if(!std::strcmp(e,"wd-read")) ++d.exactInvalidationEpoch; };
        if(failure==3) d.exactDwordReader=nullptr;
        { CallbackGate<>::Lease pin(d.exactCallbacks); CHECK(pin); IOLockLock(d.gpuLock);
          CHECK(!d.readWatchdogRecoveryLocked(&completed) && completed==sentinel); IOLockUnlock(d.gpuLock); }
        eventHook={}; CHECK(d.exactVMFault && wdCommands(d)==1);
    }
}
static void wdFaultBlocksAdoptionDispatchAndReuse() {
    reset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); accepted(c); wdTargeted(d);
    const auto gen=d.exactQueueGeneration[1]; const auto written=packetWrites.load();
    CHECK(wdAdopt(d)==kIOReturnNotReady && d.exactQueueGeneration[1]==gen);
    uint64_t seq=0; CHECK(submit(c,seq)==kIOReturnNotReady && seq==sentinel && packetWrites==written);
    CHECK(!d.vmidFree(c.vmid,c.vmGeneration,&c,c.lastSeq));
    uint64_t generation=0; CHECK(!d.vmidAlloc(&c,&generation) && !generation);
    uint64_t completed=sentinel;
    { CallbackGate<>::Lease pin(d.exactCallbacks); CHECK(pin); IOLockLock(d.gpuLock);
      CHECK(!d.readExactFence32(1,&completed) && completed==sentinel); IOLockUnlock(d.gpuLock); }
    CHECK(!d.gpuRetired() && d.exactVMFault && wdCommands(d)==1);
}
static void wdQueuedStop() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); accepted(c); wdArm(d);
    Pause pause; bool once=true;
    std::thread worker([&] { testTicks=11000000; eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"gpu-lock-pointer")) { once=false; pause.arrive(); }
    }; d.hangCheck(); eventHook={}; });
    pause.wait(); d.stop(nullptr); pause.release(); worker.join();
    CHECK(!wdCommands(d) && !d.rlcEnters && !d.watchdogRecovery.active && d.exactCallbacks.closed() && d.exactCallbacks.drained());
}
static void wdReaderCloseWhilePinned() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); accepted(c); wdArm(d);
    d.exactDwordReader=wdRaw; Pause pause; bool once=true;
    std::thread worker([&] { testTicks=11000000; eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"wd-read") && d.watchdogRecovery.active) { once=false; pause.arrive(); }
    }; d.hangCheck(); eventHook={}; });
    pause.wait(); d.exactCallbacks.close(); CHECK(!d.exactCallbacks.drained()); pause.release(); worker.join();
    CHECK(d.exactCallbacks.drained() && !wdCommands(d) && !d.rlcEnters && d.watchdogRecovery.terminal && d.exactVMFault);
}
static void wdConcurrentTicksRecoverOnlyOnce() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); accepted(c); wdArm(d);
    Pause ack,queued; bool first=true,second=true;
    std::thread a([&] { testTicks=11000000; eventHook=[&](const char *e) {
        if(first && !std::strcmp(e,"rlc-ack")) { first=false; ack.arrive(); }
    }; d.hangCheck(); eventHook={}; });
    ack.wait();
    std::thread b([&] { testTicks=11000000; eventHook=[&](const char *e) {
        if(second && !std::strcmp(e,"gpu-lock-pointer")) { second=false; queued.arrive(); }
    }; d.hangCheck(); eventHook={}; });
    queued.wait(); queued.release(); ack.release(); a.join(); b.join();
    CHECK(wdCommands(d)==1 && gHangKills==1 && d.rlcEnters==1 && d.rlcExits==1 && !d.watchdogRecovery.terminal);
}
static void wdQueuedReadoptionRejectsLostOldWork() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); accepted(c); wdArm(d);
    Pause pause; bool once=true;
    std::thread worker([&] { testTicks=11000000; eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"gpu-lock-pointer")) { once=false; pause.arrive(); }
    }; d.hangCheck(); eventHook={}; });
    pause.wait(); const auto old=d.exactQueueGeneration[1]; CHECK(wdAdopt(d)==kIOReturnSuccess);
    pause.release(); worker.join();
    CHECK(d.exactQueueGeneration[1]==old+1 && !wdCommands(d) && !d.rlcEnters && !d.watchdogRecovery.active);
    CHECK(!d.gpuRetired() && !d.exactVMFault); // loss is not old-work completion or recovery authority
}
static void wdQueuedContextReuseRestartsProgress() {
    reset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c,other; setup(d,c); const auto seq=accepted(c); wdArm(d);
    const auto handle=c.vmid; const auto old=c.vmGeneration; Pause pause; bool once=true;
    std::thread worker([&] { testTicks=11000000; eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"gpu-lock-pointer")) { once=false; pause.arrive(); }
    }; d.hangCheck(); eventHook={}; });
    pause.wait(); testTicks=10999999; d.setFence(1,seq); CHECK(c.clientClose()==kIOReturnSuccess); c.release();
    CHECK(other.start(&d)); accepted(other); CHECK(other.vmid==handle && other.vmGeneration>old);
    pause.release(); worker.join(); CHECK(!wdCommands(d) && !d.watchdogRecovery.active && d.gq[1].lastDone==seq);
    testTicks=12000000; d.hangCheck();
    CHECK(wdCommands(d)==1 && d.watchdogRecovery.client==&other && d.watchdogRecovery.allocation==other.vmGeneration);
}
int main() {
    cpu_fence_regressions(); auto oldChecks=checks.load(); auto oldGroups=groups,oldThreads=threaded;
    wdIdleAndDisabled(); wdTagsLockAndHighDword(); wdProgressAndFullFirstThreshold(); wdIdleTimeNeverCountsAgainstNewWork(); wdIndependentQueues();
    wdInvalidSnapshotRefuses(); wdCompletedHistoryMayOutliveAllocation(); wdRlcReadAndMonotonicBounds();
    wdObservedClosePairsExit(); wdCompletionDuringRlcCancelsCommand(); wdSecondFullThresholdAndSingleEscalation();
    wdNoPostRecoveryCompletionOrRelease(); wdRecoveryIdentityFailuresAreTerminal(); wdDisabledEpisodeDoesNotResume();
    wdDiagnosticFailurePreservesOutput(); wdFaultBlocksAdoptionDispatchAndReuse(); wdQueuedStop(); wdReaderCloseWhilePinned();
    wdConcurrentTicksRecoverOnlyOnce(); wdQueuedReadoptionRejectsLostOldWork(); wdQueuedContextReuseRestartsProgress();
    std::printf("PASS staged checked watchdog: %llu additional checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()-oldChecks),groups-oldGroups,threaded-oldThreads);
}
