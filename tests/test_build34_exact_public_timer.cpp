// SPDX-License-Identifier: MIT
// Actual timer method bodies are inserted below by the frozen-source runner.
#include "build34_exact_public_timer_backend.h"
// PHX34_REFERENCE
struct PhxBringup:IOService {
    phx34_exact::CallbackGate<> exactCallbacks;
    bool exactStopped=false;volatile bool hangStop=false;
    struct {bool active=false,terminal=false;} watchdogRecovery;
    IOLock gpuStorage;IOLock *gpuLock=&gpuStorage;unsigned invalidations=0;
    PhxBringup(){gpuStorage.gpu=true;}
    void invalidateExactQueues(){CHECK(gpuHeld==1);++invalidations;}
    void reapLegacyClients(){++reaps;event("reap");}
    void hangCheck(){++watches;IOLockLock(gpuLock);event("watchdog-locked");IOLockUnlock(gpuLock);}
    void stop(IOService *);
    static void hangTick(OSObject *,IOTimerEventSource *);
    // PHX34_FIELDS
};
// PHX34_METHODS
static void start(PhxBringup &d) {
    CHECK(d.startHangTimer());CHECK(d.hangState==2 && d.hangTimerReady() && !d.hangTimerDrained());
    CHECK(d.hangServicePinned && d.refs==2 && d.hangLoop && d.hangEvent && d.hangDrainCall);
    CHECK(d.hangEvent->options==kIOTimerEventSourceOptionsPriorityKernel);
    CHECK(!(d.hangEvent->options&kIOTimerEventSourceOptionsAllowReenter));
    CHECK(d.hangDrainCall->priority==THREAD_CALL_PRIORITY_KERNEL && d.hangDrainCall->options==THREAD_CALL_OPTIONS_ONCE);
    CHECK(queued(d.hangEvent) && d.hangEvent->refs==3 && d.hangLoop->refs==2);
}
static void drain(PhxBringup &d) {
    auto *timer=d.hangEvent;auto *loop=d.hangLoop;auto *call=d.hangDrainCall;
    d.stop(nullptr);CHECK(d.hangState==3 && !d.hangTimerReady() && !d.hangTimerDrained());runDrain(call);
    CHECK(d.hangTimerDrained() && d.hangState==5 && !d.hangServicePinned && d.refs==2 && d.exactStopped);
    CHECK(!d.hangEvent && !d.hangLoop && !d.hangDrainCall && timer->dead && loop->dead && call->freed);
}
static void basicAndOneShot() {
    reset();PhxBringup d;start(d);CHECK(allocation==4 && arms==1);
    auto *timer=d.hangEvent;for(unsigned i=0;i<64;++i)runTimer(timer);
    CHECK(arms==65 && driverActions==64 && reaps==64 && watches==64 && d.refs==2);
    CHECK(!d.startHangTimer() && allocation==4);drain(d);CHECK(rawEnqueues==1 && rawFrees==1);
    d.stop(nullptr);CHECK(!d.armHangTimer() && d.refs==2 && rawEnqueues==1);
}
static void allocationAndAttachFailure() {
    for(unsigned point=1;point<=4;++point) {
        reset();PhxBringup d;failAllocation=point;CHECK(!d.startHangTimer());
        CHECK(d.hangState==6 && !d.hangTimerDrained() && !d.hangTimerReady() && d.refs==1 && !d.hangServicePinned);
        CHECK(!d.hangLoop && !d.hangEvent && !d.hangDrainCall && !arms && !rawEnqueues);
        for(auto &t:timers)CHECK(t->dead);for(auto &l:loops)CHECK(l->dead);
    }
    for(bool partial:{false,true}) {
        reset();PhxBringup d;failAttach=true;partialAttach=partial;CHECK(!d.startHangTimer());
        CHECK(d.refs==1 && d.hangState==6 && !d.hangServicePinned && !arms && !d.hangEvent && !d.hangLoop);
        CHECK(timers[0]->dead && loops[0]->dead && calls[0]->freed);
    }
    reset();PhxBringup d;failArm=true;CHECK(!d.startHangTimer());CHECK(d.refs==1 && !d.hangServicePinned && !arms && timers[0]->dead && loops[0]->dead);
}
static void stopDuringInitialization() {
    for(const char *point:{"allocate-lock","allocate-loop","allocate-event","allocate-drain","event-attached"}) {
        reset();PhxBringup d;bool once=true;hook=[&](const char *e){if(once && !std::strcmp(e,point)){once=false;d.stop(nullptr);}};
        CHECK(!d.startHangTimer());hook={};CHECK(!once && d.hangState==6 && !d.hangServicePinned && d.refs==2 && !arms && !rawEnqueues);
    }
}
static void ownCallbackAndGpuLockStop() {
    reset();PhxBringup d;start(d);auto *timer=d.hangEvent;auto *call=d.hangDrainCall;bool once=true;
    hook=[&](const char *e){if(once && !std::strcmp(e,"watchdog-locked")){once=false;CHECK(gpuHeld==1);d.stop(nullptr);}};
    runTimer(timer);hook={};CHECK(!once && !queued(timer) && d.hangState==3 && d.refs==3);
    runDrain(call);CHECK(d.hangTimerDrained() && timer->dead && d.refs==2 && d.exactStopped && d.invalidations==1);
}
static void faultRetainsResources() {
    for(unsigned point=0;point<5;++point) {
        reset();PhxBringup d;start(d);auto *timer=d.hangEvent;auto *loop=d.hangLoop;auto *call=d.hangDrainCall;
        if(point==0)failRemove=true;if(point==1)lieRemove=true;if(point==2)call->failFree=true;if(point==3)failAction=true;
        if(point==4)failRemoveAfterDetach=true;
        d.stop(nullptr);runDrain(call);
        CHECK(d.hangState==6 && !d.hangTimerDrained() && d.hangServicePinned && d.refs==3 && !timer->dead && !loop->dead);
        CHECK(d.hangEvent==timer && d.hangLoop==loop && d.hangDrainCall==(point==2 ? call : nullptr));
        CHECK(call->freed==(point!=2));auto refs=d.refs.load();d.stop(nullptr);CHECK(d.refs==refs && rawEnqueues==1 && rawFrees==1);
    }
    reset();PhxBringup d;bool once=true;hook=[&](const char *e){if(once && !std::strcmp(e,"event-attached")){once=false;calls[0]->failFree=true;}};
    failArm=true;CHECK(!d.startHangTimer());hook={};CHECK(d.refs==2 && d.hangState==6 && d.hangServicePinned && d.hangDrainCall && d.hangEvent && !d.hangEvent->dead);
    reset();PhxBringup e;failArm=failRemove=true;CHECK(!e.startHangTimer());
    CHECK(e.refs==2 && e.hangState==6 && e.hangServicePinned && !e.hangDrainCall && e.hangLoop && e.hangEvent && !e.hangEvent->dead);
}
static void rearmFailureClosesService() {
    reset();PhxBringup d;start(d);auto *timer=d.hangEvent;auto *call=d.hangDrainCall;
    failArm=true;runTimer(timer);CHECK(d.exactCallbacks.closed() && d.hangState==3 && !queued(timer));runDrain(call);
    CHECK(d.hangTimerDrained() && timer->dead && d.refs==2);
}
static void staleSenderAndUngatedActionRefuse() {
    reset();PhxBringup d;start(d);auto oldReaps=reaps.load();IOTimerEventSource stranger;
    PhxBringup::hangTick(&d,&stranger);CHECK(reaps==oldReaps && d.refs==2 && arms==1);
    CHECK(PhxBringup::armHangTimerAction(&d,d.hangEvent,d.hangLoop,nullptr,nullptr)==kIOReturnNotReady);
    CHECK(PhxBringup::closeHangTimerAction(&d,d.hangEvent,d.hangLoop,nullptr,nullptr)==kIOReturnNotReady);drain(d);
}
static void missingHandleRefusesReady() {
    reset();PhxBringup d;start(d);auto *timer=d.hangEvent;auto *loop=d.hangLoop;auto *call=d.hangDrainCall;
    d.hangEvent=nullptr;CHECK(!d.hangTimerReady());d.hangEvent=timer;
    d.hangLoop=nullptr;CHECK(!d.hangTimerReady());d.hangLoop=loop;
    d.hangDrainCall=nullptr;CHECK(!d.hangTimerReady());d.hangDrainCall=call;drain(d);
}
static void workerGateDelaysDrainClaim() {
    reset();PhxBringup d;start(d);auto *call=d.hangDrainCall;d.stop(nullptr);bool saw=false;
    hook=[&](const char *e){if(!saw && !std::strcmp(e,"object-release") && d.hangState==5){saw=true;CHECK(!d.hangTimerDrained());}};
    runDrain(call);hook={};CHECK(saw && d.hangTimerDrained());
}
static void wrapperBeforeGateLosesToDetach() {
    reset();++threaded;PhxBringup d;start(d);auto *timer=d.hangEvent;auto *loop=d.hangLoop;auto *call=d.hangDrainCall;
    Pause before;std::thread t([&]{hook=[&](const char *e){if(!std::strcmp(e,"wrapper-before-gate"))before.arrive();};runTimer(timer);hook={};});
    before.wait();d.stop(nullptr);runDrain(call);
    CHECK(d.hangTimerDrained() && !timer->dead && !loop->dead && d.refs==2 && !driverActions && !reaps);
    before.resume();t.join();CHECK(timer->dead && loop->dead && !driverActions);
}
static void drainWaitsForAdmittedAction() {
    reset();++threaded;PhxBringup d;start(d);auto *timer=d.hangEvent;auto *call=d.hangDrainCall;Pause inside,waiter;
    std::thread t([&]{hook=[&](const char *e){if(!std::strcmp(e,"reap"))inside.arrive();};runTimer(timer);hook={};});
    inside.wait();d.stop(nullptr);std::atomic<bool>done{false};
    std::thread w([&]{bool once=true;hook=[&](const char *e){if(once && !std::strcmp(e,"loop-before-gate")){once=false;waiter.arrive();}};runDrain(call);done=true;hook={};});
    waiter.wait();CHECK(!done && !d.hangTimerDrained() && d.refs>=3);waiter.resume();inside.resume();t.join();w.join();
    CHECK(done && d.hangTimerDrained() && timer->dead && d.refs==2 && watches==1);
}
static void capturedArmQueuedBehindStop() {
    reset();++threaded;PhxBringup d;start(d);auto *timer=d.hangEvent;auto *loop=d.hangLoop;auto *call=d.hangDrainCall;Pause queuedArm;
    bool result=true;std::thread t([&]{bool once=true;hook=[&](const char *e){if(once && !std::strcmp(e,"loop-before-gate")){once=false;queuedArm.arrive();}};result=d.armHangTimer();hook={};});
    queuedArm.wait();d.stop(nullptr);runDrain(call);CHECK(d.hangTimerDrained() && !timer->dead && !loop->dead && d.refs==2);
    queuedArm.resume();t.join();CHECK(!result && timer->dead && loop->dead && arms==1);
}
static void capturedArmSeesClosureBeforeDrainQueue() {
    reset();++threaded;PhxBringup d;start(d);Pause captured,closed;bool result=true;
    std::thread a([&]{bool once=true;hook=[&](const char *e){if(once && !std::strcmp(e,"loop-before-gate")){once=false;captured.arrive();}};result=d.armHangTimer();hook={};});
    captured.wait();std::thread s([&]{hook=[&](const char *e){if(!std::strcmp(e,"timer-before-lock"))closed.arrive();};d.stop(nullptr);hook={};});
    closed.wait();CHECK(d.hangState==2 && d.exactCallbacks.closed() && d.hangStopping());captured.resume();a.join();
    CHECK(!result && arms==1);closed.resume();s.join();auto *call=d.hangDrainCall;runDrain(call);CHECK(d.hangTimerDrained() && d.refs==2);
}
static void stopsHaveOneWinner() {
    reset();++threaded;PhxBringup d;start(d);auto *call=d.hangDrainCall;
    std::thread a([&]{d.stop(nullptr);}),b([&]{d.stop(nullptr);});a.join();b.join();
    CHECK(d.refs==3 && rawEnqueues==1);runDrain(call);CHECK(d.hangTimerDrained() && d.refs==2 && d.invalidations==1);
}
static void initializationRacesStop() {
    reset();++threaded;PhxBringup d;Pause at;bool result=true;
    std::thread t([&]{hook=[&](const char *e){if(!std::strcmp(e,"allocate-event"))at.arrive();};result=d.startHangTimer();hook={};});
    at.wait();d.stop(nullptr);at.resume();t.join();CHECK(!result && !arms && !rawEnqueues && d.refs==2 && !d.hangServicePinned && d.hangState==6);
}
static void stopDuringFirstArmCannotLoseDrain() {
    reset();++threaded;PhxBringup d;Pause armed,stopping;bool result=false;
    std::thread init([&]{hook=[&](const char *e){if(!std::strcmp(e,"event-armed"))armed.arrive();};result=d.startHangTimer();hook={};});
    armed.wait();std::thread stop([&]{hook=[&](const char *e){if(!std::strcmp(e,"timer-before-lock"))stopping.arrive();};d.stop(nullptr);hook={};});
    stopping.wait();CHECK(d.exactCallbacks.closed() && d.hangStopping());armed.resume();init.join();stopping.resume();stop.join();
    CHECK(result && d.hangState==3 && rawEnqueues==1 && !d.hangTimerReady());auto *call=d.hangDrainCall;runDrain(call);
    CHECK(d.hangTimerDrained() && d.refs==2 && d.exactStopped);
}
static void pinProtectsDrainBeforeEntry() {
    reset();++threaded;PhxBringup d;start(d);auto *call=d.hangDrainCall;d.stop(nullptr);Pause entry;
    std::thread w([&]{hook=[&](const char *e){if(!std::strcmp(e,"drain-before-entry"))entry.arrive();};runDrain(call);hook={};});
    entry.wait();CHECK(d.hangServicePinned && d.refs==3 && !d.hangTimerDrained());d.release();CHECK(!d.dead);
    entry.resume();w.join();CHECK(d.hangTimerDrained() && d.refs==1 && !d.dead);
}
static void wrapperMayFinishAfterDriverDrain() {
    reset();++threaded;PhxBringup d;start(d);auto *timer=d.hangEvent;auto *loop=d.hangLoop;auto *call=d.hangDrainCall;Pause after;
    std::thread t([&]{hook=[&](const char *e){if(!std::strcmp(e,"wrapper-before-finish"))after.arrive();};runTimer(timer);hook={};});
    after.wait();CHECK(queued(timer));d.stop(nullptr);runDrain(call);
    CHECK(d.hangTimerDrained() && !timer->dead && !loop->dead && d.refs==2 && driverActions==1);
    after.resume();t.join();CHECK(timer->dead && loop->dead);
}
int main() {
    basicAndOneShot();allocationAndAttachFailure();stopDuringInitialization();ownCallbackAndGpuLockStop();faultRetainsResources();
    rearmFailureClosesService();staleSenderAndUngatedActionRefuse();missingHandleRefusesReady();workerGateDelaysDrainClaim();wrapperBeforeGateLosesToDetach();
    drainWaitsForAdmittedAction();capturedArmQueuedBehindStop();capturedArmSeesClosureBeforeDrainQueue();stopsHaveOneWinner();initializationRacesStop();stopDuringFirstArmCannotLoseDrain();
    pinProtectsDrainBeforeEntry();wrapperMayFinishAfterDriverDrain();
    std::printf("PASS public service timer: %u checks; %u groups; %u threaded scenarios; GPU_executed=false\n",checks.load(),groups,threaded);
}
