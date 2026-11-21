// SPDX-License-Identifier: MIT
// Own-timer tests use actual allocation/arm/stop/drain source methods and a CPU scheduler.
static void svcFresh(PhxBringup &d) {
    // Remove ONLY the inherited, unpublished legacy CPU sentinel. This is not
    // native reset/rebind support: actual startHangTimer admits state zero once.
    CHECK(d.hangCall==&d.legacyTimer && !d.legacyTimer.real && d.refs==1);
    d.hangCall=nullptr; d.hangLock=nullptr; d.hangState=0;
}
static void svcStart(PhxBringup &d) {
    svcFresh(d); CHECK(d.startHangTimer());
    CHECK(d.refs==2 && d.hangServicePinned && d.hangTimerReady() && !d.hangTimerDrained());
    CHECK(d.hangCall && d.hangDrainCall && timerQueued(d.hangCall) && !timerQueued(d.hangDrainCall));
    CHECK(d.hangCall->priority==THREAD_CALL_PRIORITY_KERNEL && d.hangDrainCall->priority==THREAD_CALL_PRIORITY_KERNEL);
    CHECK(d.hangCall->options==THREAD_CALL_OPTIONS_ONCE && d.hangDrainCall->options==THREAD_CALL_OPTIONS_ONCE);
}
static void svcDrain(PhxBringup &d) {
    auto *periodic=d.hangCall,*drain=d.hangDrainCall; CHECK(periodic && drain);
    d.stop(nullptr); CHECK(d.hangState==3 && timerQueued(drain) && !d.hangTimerReady() && !d.hangTimerDrained());
    timerRun(drain);
    CHECK(d.hangTimerDrained() && d.hangState==5 && !d.hangServicePinned && !d.hangCall && !d.hangDrainCall);
    CHECK(timerFreed(periodic) && timerFreed(drain) && d.refs==2 && d.exactCallbacks.drained());
    CHECK(d.exactStopped && d.hangStopping() && d.hangLock && !d.hangLock->freed);
}
static void svcPinPriorityAndOneShotStart() {
    reset(); PhxBringup d; svcFresh(d); unsigned publications=0;
    eventHook=[&](const char *e) { if(!std::strcmp(e,"timer-delayed")) {
        ++publications; CHECK(d.refs==2 && d.hangServicePinned && timerHeld==1 && !gpuHeld && d.hangState==2);
    } };
    CHECK(d.startHangTimer()); eventHook={};
    CHECK(publications==1 && timerAllocations==2 && hangArms==1 && d.refs==2);
    CHECK(d.hangCall->priority==THREAD_CALL_PRIORITY_KERNEL && d.hangDrainCall->priority==THREAD_CALL_PRIORITY_KERNEL);
    CHECK(d.hangCall->options==THREAD_CALL_OPTIONS_ONCE && d.hangDrainCall->options==THREAD_CALL_OPTIONS_ONCE);
    auto *first=d.hangCall,*second=d.hangDrainCall;
    CHECK(!d.startHangTimer() && timerAllocations==2 && d.hangCall==first && d.hangDrainCall==second && d.refs==2);
    svcDrain(d); CHECK(timerImmediate==1 && timerCancelWaits==1 && timerFreeAttempts==2);
    auto refs=d.refs.load(); d.stop(nullptr); d.armHangTimer();
    CHECK(d.refs==refs && timerImmediate==1 && hangArms==1);
    PhxBringup::hangDrainTick(&d,nullptr); CHECK(d.refs==refs && timerFreeAttempts==2);
}
static void svcRepeatedTicksAndFalseEnqueueResult() {
    reset(); PhxBringup d; svcStart(d); auto *periodic=d.hangCall;
    for(unsigned i=0;i<64;++i) {
        timerRun(periodic); CHECK(timerQueued(periodic) && d.refs==2 && d.hangState==2 && d.hangTimerReady());
    }
    CHECK(hangArms==65 && !timerImmediate); svcDrain(d);
}
static void svcAllocationFailurePreservesOwnership() {
    for(unsigned bad=0;bad<4;++bad) {
        reset(); PhxBringup d; svcFresh(d);
        if(bad==0) failTimerLock=true;
        if(bad==1) failTimerAllocation=1;
        if(bad>=2) failTimerAllocation=2;
        if(bad==3) eventHook=[&](const char *e) {
            if(!std::strcmp(e,"timer-allocate") && timerAllocations==2) { CHECK(d.hangCall); d.hangCall->failFree=true; }
        };
        CHECK(!d.startHangTimer()); eventHook={};
        CHECK(d.hangState==6 && !d.hangTimerReady() && !d.hangTimerDrained() && !hangArms && !timerImmediate);
        if(bad==3) CHECK(d.hangServicePinned && d.refs==2 && d.hangCall && !timerFreed(d.hangCall) && !d.hangDrainCall);
        else CHECK(!d.hangServicePinned && d.refs==1 && !d.hangCall && !d.hangDrainCall);
        CHECK(timerAllocations==(bad==0 ? 0u : 2u) && timerFreeAttempts==(bad==0 ? 0u : 1u));
        CHECK(!d.startHangTimer() && !hangArms);
    }
}
static void svcStopDuringInitialization() {
    for(unsigned where=0;where<3;++where) {
        reset(); PhxBringup d; svcFresh(d); bool once=true;
        eventHook=[&](const char *e) {
            if(once && ((where==0 && !std::strcmp(e,"timer-lock-allocate")) ||
                (where==1 && !std::strcmp(e,"timer-allocate") && timerAllocations==1) ||
                (where==2 && !std::strcmp(e,"timer-allocate") && timerAllocations==2))) {
                once=false; d.stop(nullptr);
            }
        };
        CHECK(!d.startHangTimer()); eventHook={};
        CHECK(!once && !hangArms && !timerImmediate && !d.hangCall && !d.hangDrainCall && d.refs==2);
        CHECK(!d.hangServicePinned && d.hangState==6 && d.hangStopping() && d.exactCallbacks.drained());
    }
}
static void svcOwnCallbackStopUsesDistinctWorker() {
    reset(); PhxBringup d; svcStart(d); auto *periodic=d.hangCall,*drain=d.hangDrainCall; bool once=true;
    eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"gpu-lock-pointer")) { once=false; d.stop(nullptr); CHECK(!timerCancelWaits); }
    };
    timerRun(periodic); eventHook={};
    CHECK(!once && !timerQueued(periodic) && timerQueued(drain) && d.hangState==3 && d.refs==3 && !timerCancelWaits);
    timerRun(drain); // periodic is neither pending nor running: cancel returns FALSE, drain still succeeds
    CHECK(d.hangTimerDrained() && timerFreed(periodic) && timerFreed(drain) && d.refs==2 && timerCancelWaits==1 && d.exactStopped);
}
static void svcFreeFailureRetainsExactHandleAndPin() {
    for(bool failPeriodic : {false,true}) {
        reset(); PhxBringup d; svcStart(d); auto *periodic=d.hangCall,*drain=d.hangDrainCall;
        (failPeriodic ? periodic : drain)->failFree=true;
        d.stop(nullptr); timerRun(drain);
        CHECK(d.hangState==6 && !d.hangTimerDrained() && d.hangServicePinned && d.refs==3 && d.hangWorkers.drained());
        CHECK(d.hangCall==(failPeriodic ? periodic : nullptr) && d.hangDrainCall==(failPeriodic ? nullptr : drain));
        CHECK(timerFreed(periodic)==!failPeriodic && timerFreed(drain)==failPeriodic && timerFreeAttempts==2);
        d.stop(nullptr); CHECK(timerFreeAttempts==2 && timerImmediate==1 && d.refs==3);
    }
}
static void svcWorkerGatePreventsEarlyDrainClaim() {
    reset(); PhxBringup d; svcStart(d); auto *drain=d.hangDrainCall; d.stop(nullptr); bool saw=false;
    eventHook=[&](const char *e) {
        if(!saw && !std::strcmp(e,"object-release") && d.hangState==5) {
            saw=true; CHECK(d.hangWorkers.closed() && !d.hangWorkers.drained() && !d.hangTimerDrained());
        }
    };
    timerRun(drain); eventHook={}; CHECK(saw && d.hangTimerDrained() && d.refs==2);
}
static void svcBeforeEntryPinAndExternalWait() {
    reset(); ++threaded; PhxBringup d; svcStart(d); auto *periodic=d.hangCall,*drain=d.hangDrainCall;
    Pause entry; bool once=true;
    std::thread callback([&] { eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"timer-before-entry")) { once=false; entry.arrive(); }
    }; timerRun(periodic); eventHook={}; });
    entry.wait(); d.stop(nullptr); CHECK(d.refs==3 && d.hangServicePinned && d.exactCallbacks.drained());
    std::atomic<bool> finished{false}; std::thread cleanup([&] { timerRun(drain); finished=true; });
    waitForTimerWaiter(periodic); CHECK(!finished && !d.hangTimerDrained());
    d.release(); CHECK(!d.finalized); // registration pin already protects entry before its transient retain
    entry.release(); callback.join(); cleanup.join();
    CHECK(finished && d.hangTimerDrained() && d.refs==1 && !d.finalized && timerFreed(periodic) && timerFreed(drain));
}
static void svcRescheduledButNotFinishedWaitsForOnce() {
    reset(); ++threaded; PhxBringup d; svcStart(d); auto *periodic=d.hangCall,*drain=d.hangDrainCall;
    Pause finish; bool once=true;
    std::thread callback([&] { eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"timer-before-finish")) { once=false; finish.arrive(); }
    }; timerRun(periodic); eventHook={}; });
    finish.wait(); CHECK(timerQueued(periodic) && timerRunning(periodic) && d.exactCallbacks.active()==0);
    d.stop(nullptr); std::atomic<bool> finished{false};
    std::thread cleanup([&] { timerRun(drain); finished=true; });
    waitForTimerWaiter(periodic); CHECK(!finished && !d.hangTimerDrained() && !timerQueued(periodic));
    finish.release(); callback.join(); cleanup.join();
    CHECK(finished && d.hangTimerDrained() && d.refs==2 && hangArms==2 && timerFreed(periodic));
}
static void svcQueuedRearmLosesToStop() {
    reset(); ++threaded; PhxBringup d; svcStart(d); auto *periodic=d.hangCall,*drain=d.hangDrainCall;
    Pause arm; bool once=true;
    std::thread callback([&] { eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"timer-lock-pointer")) { once=false; arm.arrive(); }
    }; timerRun(periodic); eventHook={}; });
    arm.wait(); d.stop(nullptr); std::thread cleanup([&] { timerRun(drain); });
    waitForTimerWaiter(periodic); arm.release(); callback.join(); cleanup.join();
    CHECK(d.hangTimerDrained() && d.refs==2 && hangArms==1 && timerImmediate==1 && timerFreed(periodic));
}
static void svcConcurrentStopsHaveOneWinner() {
    reset(); ++threaded; PhxBringup d; svcStart(d); auto *drain=d.hangDrainCall;
    std::thread a([&] { d.stop(nullptr); }),b([&] { d.stop(nullptr); }); a.join(); b.join();
    CHECK(d.refs==3 && timerImmediate==1 && timerQueued(drain)); timerRun(drain);
    CHECK(d.refs==2 && d.hangTimerDrained() && timerCancelWaits==1 && timerFreeAttempts==2);
}
static void svcConcurrentInitializationStop() {
    reset(); ++threaded; PhxBringup d; svcFresh(d); Pause allocation; bool once=true,result=true;
    std::thread init([&] { eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"timer-allocate")) { once=false; allocation.arrive(); }
    }; result=d.startHangTimer(); eventHook={}; });
    allocation.wait(); d.stop(nullptr); allocation.release(); init.join();
    CHECK(!result && d.hangState==6 && d.refs==2 && !d.hangServicePinned && !d.hangCall && !d.hangDrainCall);
    CHECK(!hangArms && !timerImmediate && !d.hangTimerDrained() && timerFreeAttempts==2);
}
static void svcStopAtRlcKeepsGpuOwnership() {
    reset(); ++threaded; PhxBringup d; svcStart(d); IOAccelPhxNativeClient c; setup(d,c);
    IOMemoryDescriptor md; std::vector<uint8_t> bytes(4096); attach(c,1,md,bytes);
    const auto seq=acceptedFence(c,1,8); wdArm(d);
    auto *periodic=d.hangCall,*drain=d.hangDrainCall; Pause entered; bool once=true;
    std::thread callback([&] { testTicks=11000000; eventHook=[&](const char *e) {
        if(once && !std::strcmp(e,"rlc-enter")) { once=false; CHECK(gpuHeld==1); d.stop(nullptr); entered.arrive(); }
    }; timerRun(periodic); eventHook={}; });
    entered.wait(); std::thread cleanup([&] { timerRun(drain); }); waitForTimerWaiter(periodic);
    CHECK(!d.hangTimerDrained()); entered.release(); callback.join(); cleanup.join();
    CHECK(d.hangTimerDrained() && !wdCommands(d) && d.rlcEnters==1 && d.rlcExits==1 && !d.rlcEntered);
    d.setFence(1,seq); CHECK(!d.gpuRetired() && !read64(bytes,8) && md.alive && c.cpuFenceCount==1 && d.exactVMFault);
    CHECK(c.clientClose()==kIOReturnNotReady && c.legacyClientPinned && d.vm[c.vmid-1].busy && d.refs==3);
    c.release(); CHECK(!c.finalized && md.alive && !md.completes && !md.releases);
}
int main() {
    watchdog_regressions(); auto oldChecks=checks.load(); auto oldGroups=groups,oldThreads=threaded;
    svcPinPriorityAndOneShotStart(); svcRepeatedTicksAndFalseEnqueueResult(); svcAllocationFailurePreservesOwnership();
    svcStopDuringInitialization(); svcOwnCallbackStopUsesDistinctWorker(); svcFreeFailureRetainsExactHandleAndPin();
    svcWorkerGatePreventsEarlyDrainClaim(); svcBeforeEntryPinAndExternalWait(); svcRescheduledButNotFinishedWaitsForOnce();
    svcQueuedRearmLosesToStop(); svcConcurrentStopsHaveOneWinner(); svcConcurrentInitializationStop(); svcStopAtRlcKeepsGpuOwnership();
    std::printf("PASS staged owned service timer: %llu additional checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()-oldChecks),groups-oldGroups,threaded-oldThreads);
}
