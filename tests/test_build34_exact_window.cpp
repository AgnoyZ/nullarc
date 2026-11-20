// SPDX-License-Identifier: MIT
// Actual staged adoption/submit/observer/invalidator plus controlled CPU dwords.
// Device coherency, mapping admission, drain and native lifetime are NOT proved.
#include "window-binding-CPU-only.h"
static thread_local bool failDword=false,overrideDword=false;
static thread_local uint32_t dword=0;
static std::atomic<unsigned> dwordReads{0};
// PHX34_WINDOW_METHODS
static bool raw32(const volatile uint32_t *p,uint32_t *out) {
    CHECK(gpuHeld==1); ++dwordReads; event("dword-read");
    *out=overrideDword ? dword : *p; return !failDword; // CPU bytes, never BAR access
}
static bool legacyReader(const volatile uint32_t *,uint64_t *) { CHECK(false); return false; }
static void windowReset() {
    reset(); dwordReads=vmBinds=sleepCalls=0; testTicks=10000000; failDword=overrideDword=false;
}
static void adopt(PhxBringup &d,unsigned qi) {
    CHECK(qi<2); const uint64_t in[6]={qi ? 4096u : 0u,1024,qi ? 8256u : 8192u,qi ? 8u : 0u,8,(qi ? 9008u : 9000u)|qi};
    CHECK(d.adoptQueue(in)==kIOReturnSuccess);
}
static void setup(PhxBringup &d,IOAccelPhxNativeClient &c,uint64_t seq=99) {
    d.gSeq=seq; adopt(d,0); adopt(d,1); start(c,d);
    d.exactFenceReader=legacyReader; d.exactDwordReader=raw32;
}
static int call(IOAccelPhxNativeClient &c,bool gfx,uint64_t &seq) {
    Request request(gfx); IOLockLock(c.lock); const int r=c.doSubmit(&request.a); IOLockUnlock(c.lock);
    seq=request.a.scalarOutput[0]; return r;
}
static uint64_t accepted(IOAccelPhxNativeClient &c,bool gfx=true) {
    uint64_t seq; CHECK(call(c,gfx,seq)==kIOReturnSuccess && seq!=sentinel); return seq;
}
static bool read(PhxBringup &d,unsigned qi,uint64_t &out) {
    CallbackGate<>::Lease lease(d.exactCallbacks); CHECK(lease);
    IOLockLock(d.gpuLock); bool r=d.readExactFence32(qi,&out); IOLockUnlock(d.gpuLock); return r;
}
static void basicsAndWrap() {
    for(uint64_t base:{99ull,0xfffffffdull,0x12345678fffffffdull}) {
        windowReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,base);
        const auto compute=accepted(c,false),gfx=accepted(c),gfx2=accepted(c);
        CHECK(compute==base+1 && gfx2==base+3);
        d.setFence(1,gfx2); CHECK(c.queryExact(gfx)==Status::Complete && c.queryExact(compute)==Status::Pending);
        CHECK(d.gpuRetired()==base && dwordReads==5);
        d.setFence(0,compute); CHECK(c.queryExact(compute)==Status::Complete);
        CHECK(d.gpuRetired()==gfx2);
        // The old high dword is deliberately incoherent in this CPU representation test.
        const auto bogus=(uint64_t{0xfedcba98}<<32)|uint32_t(gfx2); d.setFence(1,bogus);
        CHECK(d.queueFence(d.gq[1])==bogus); // unchanged legacy helper, NOT accepted hardware evidence
        CHECK(c.queryExact(gfx2)==Status::Complete); // only the genuine low dword enters this path
    }
}
static void sharedLegacyAndFallback() {
    for(bool fallback:{false,true}) {
        windowReset(); PhxBringup d; IOAccelPhxNativeClient c,legacy; setup(d,c);
        CHECK(legacy.start(&d) && !legacy.exactOwnership);
        if(fallback) d.gq[1].ready=false;
        const auto qi=fallback ? 0u : 1u; const auto target=accepted(c);
        for(unsigned i=0;i<192;i++) { d.setFence(qi,d.gSeq); (void)accepted(legacy); }
        CHECK(d.exactQueueSubmitted[qi]==d.gSeq && d.gq[qi].tail==193);
        d.setFence(qi,d.gSeq); CHECK(c.queryExact(target)==Status::Complete);
        uint64_t completed=sentinel; CHECK(read(d,qi,completed) && completed==d.gSeq);
    }
}
static void spanAdmission() {
    for(bool exact:{false,true}) for(uint64_t span:{(1ull<<32)-1,1ull<<32,(1ull<<32)+1}) {
        windowReset(); PhxBringup d; IOAccelPhxNativeClient c,legacy; setup(d,c);
        CHECK(legacy.start(&d)); auto &client=exact ? c : legacy;
        d.gSeq=99+span-1; const auto before=d.gSeq; uint64_t out=0;
        const auto result=call(client,true,out);
        if(span<(1ull<<32)) {
            CHECK(result==kIOReturnSuccess && out==before+1 && packetWrites>0);
            d.setFence(1,out); // refresh in submit admits the next sequence only after completion
            uint64_t next=0; CHECK(call(client,true,next)==kIOReturnSuccess && next==out+1 && dwordReads==2);
        } else {
            CHECK(result==kIOReturnBusy && out==sentinel && !packetWrites && !vmBinds);
            CHECK(!c.exactRegistry.occupied() && d.gSeq==before && dwordReads==1);
            CHECK(d.exactFenceWindow[1].canSubmit(d.exactQueueGeneration[1],100));
        }
    }
    // A missed publication cannot consume a window sequence or cause its retry to fail.
    windowReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    Ticket t; CHECK(c.exactRegistry.reserve(t)==Status::Ok && c.exactRegistry.cancel(t)==Status::Ok);
    uint64_t va=0x10000,out=sentinel; uint32_t dw=16;
    IOLockLock(c.lock);
    CHECK(d.gpuSubmit(7,true,&va,&dw,1,&out,&c.exactRegistry,t,&c)==kIOReturnNotReady);
    IOLockUnlock(c.lock);
    CHECK(!packetWrites && out==sentinel && d.gSeq==99 && accepted(c)==100);
    // Sequence exhaustion also covers legacy clients, before any publication.
    for(bool exact:{false,true}) {
        windowReset(); PhxBringup driver; IOAccelPhxNativeClient a,b; setup(driver,a,UINT64_MAX-1);
        CHECK(b.start(&driver)); out=0;
        CHECK(call(exact ? a : b,true,out)==kIOReturnNoResources && out==sentinel && !packetWrites && !vmBinds);
    }
}
static void invalidSamplesAndMappings() {
    for(unsigned mode=0;mode<11;mode++) {
        windowReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto seq=accepted(c);
        d.setFence(1,seq); uint64_t out=sentinel; const auto before=dwordReads.load();
        if(mode==0) d.exactDwordReader=nullptr;
        if(mode==1) failDword=true;
        if(mode==2) { overrideDword=true; dword=uint32_t(seq+1); }
        if(mode==3) d.gq[1].fenceOff++;
        if(mode==4) d.fbAperLen=d.gq[1].fenceOff+3;
        if(mode==5) { d.aperture.overrideLength=true; d.aperture.customLength=d.gq[1].fenceOff+3; }
        if(mode==6) { d.aperture.overrideBase=true; d.aperture.customBase=0; }
        if(mode==7) { d.aperture.overrideBase=true; d.aperture.customBase=UINTPTR_MAX-3; }
        if(mode==8) { d.aperture.overrideBase=true; d.aperture.customBase=reinterpret_cast<uintptr_t>(d.aperture.words)+1; }
        if(mode==9) d.exactQueueLive[1]=false;
        if(mode==10) d.exactQueueGeneration[1]++;
        CHECK(!read(d,1,out) && out==sentinel);
        if(mode!=1 && mode!=2 && mode!=10) CHECK(dwordReads==before);
        CHECK(!read(d,2,out) && out==sentinel);
        if(mode==1 || mode==2) { failDword=overrideDword=false; CHECK(read(d,1,out) && out==seq); }
    }
    windowReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); const auto seq=accepted(c);
    d.setFence(1,seq); uint64_t out=sentinel; CHECK(read(d,1,out) && out==seq);
    d.setFence(1,seq-1); out=sentinel; CHECK(!read(d,1,out) && out==sentinel);
    d.exactDwordReader=nullptr; CHECK(c.queryExact(seq)==Status::InvalidObservation); // no 64-bit fallback
}
static void invalidationAndReseed() {
    { // Metadata re-adoption only: this does not prove an old hardware writer drained.
        windowReset(); PhxBringup driver; IOAccelPhxNativeClient client; setup(driver,client);
        const auto old=accepted(client),generation=driver.exactQueueGeneration[1];
        adopt(driver,1); CHECK(driver.exactQueueGeneration[1]>generation);
        CHECK(client.queryExact(old)==Status::Lost && accepted(client)==old+1);
    }
    windowReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    const auto seq=accepted(c); const auto oldgen=d.exactQueueGeneration[1];
    IOLockLock(d.gpuLock); d.invalidateExactQueues(); IOLockUnlock(d.gpuLock);
    CHECK(!d.exactFenceWindow[1].canSubmit(oldgen,seq+1) && c.queryExact(seq)==Status::Lost);
    uint64_t out=0; CHECK(call(c,true,out)==kIOReturnNotReady && out==sentinel);
    adopt(d,1); CHECK(d.exactQueueGeneration[1]>oldgen && accepted(c)==seq+1);
    CHECK(c.queryExact(seq)==Status::Lost); // generation labels never revive an old receipt
    const auto generation=d.exactQueueGeneration[1]; const auto before=d.aperture.words[9008/8];
    d.gSeq=UINT64_MAX; const uint64_t in[6]={4096,1024,8256,8,8,9009};
    CHECK(d.adoptQueue(in)==kIOReturnNoResources && d.exactQueueGeneration[1]==generation);
    CHECK(d.aperture.words[9008/8]==before);
}
static void ringSpaceUsesBoundedDword() {
    for(bool exact:{false,true}) {
        windowReset(); PhxBringup d; IOAccelPhxNativeClient c,legacy; setup(d,c);
        CHECK(legacy.start(&d)); const auto seq=accepted(c); auto &q=d.gq[1];
        q.ringDw=256; q.wptr=q.fend[0]=248; q.doneEnd=8;
        d.setFence(1,(uint64_t{0x12345678}<<32)|uint32_t(seq-1));
        const auto packets=packetWrites.load(),binds=vmBinds.load(); uint64_t out=0;
        CHECK(call(exact ? c : legacy,true,out)==kIOReturnBusy && out==sentinel);
        CHECK(packetWrites==packets && vmBinds==binds && d.gSeq==seq && q.head==0 && q.tail==1);
        CHECK(sleepCalls==2000 && c.exactRegistry.occupied()==1);
    }
    // Missing or failed readers refuse before ring-history/VM/publication writes.
    for(bool missing:{false,true}) {
        windowReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c); uint64_t out=0;
        if(missing) d.exactDwordReader=nullptr; else failDword=true;
        CHECK(call(c,true,out)==kIOReturnNotReady && out==sentinel && !packetWrites && !vmBinds);
        CHECK(!c.exactRegistry.occupied() && d.gSeq==99 && !d.gq[1].head && !d.gq[1].tail);
    }
}
static void closeDuringRead(bool service) {
    windowReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    auto seq=accepted(c); d.setFence(1,seq); Pause pause; Status status=Status::Invalid;
    std::thread t([&] { eventHook=[&](const char *name) { if(!std::strcmp(name,"dword-read")) pause.arrive(); };
        status=c.queryExact(seq); eventHook={}; });
    pause.wait(); if(service) d.stop(nullptr); else CHECK(c.clientClose()==kIOReturnSuccess);
    pause.release(); t.join(); CHECK(status==Status::Lost && !frees && !terminations);
    CHECK(c.retained==1 && d.retained==(service ? 2u : 1u));
}
static void pairedClients() {
    windowReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c,other; setup(d,c); start(other,d);
    uint64_t a=0,b=0;
    std::thread x([&] { a=accepted(c); }),y([&] { b=accepted(other,false); }); x.join(); y.join();
    CHECK(a!=b && std::min(a,b)==100 && std::max(a,b)==101);
    d.setFence(1,a); d.setFence(0,b);
    CHECK(c.queryExact(a)==Status::Complete && other.queryExact(b)==Status::Complete);
    CHECK(d.exactQueueSubmitted[1]==a && d.exactQueueSubmitted[0]==b);
}
static void terminalDirectRead() {
    windowReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    const auto seq=accepted(c); d.setFence(1,seq); Pause pause; bool result=true; uint64_t out=sentinel;
    std::thread t([&] { eventHook=[&](const char *name) { if(!std::strcmp(name,"dword-read")) pause.arrive(); };
        result=read(d,1,out); eventHook={}; });
    pause.wait(); d.stop(nullptr); pause.release(); t.join();
    CHECK(!result && out==sentinel);
}
int main() {
    basicsAndWrap(); sharedLegacyAndFallback(); spanAdmission(); invalidSamplesAndMappings(); invalidationAndReseed(); ringSpaceUsesBoundedDword();
    closeDuringRead(false); closeDuringRead(true); pairedClients(); terminalDirectRead();
    CHECK(!clientHeld && !gpuHeld);
    std::printf("PASS staged exact dword window: %llu checks; %u groups; %u threaded scenarios; actual shared-queue callsites; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()),groups,threaded);
}
