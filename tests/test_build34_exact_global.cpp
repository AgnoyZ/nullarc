// SPDX-License-Identifier: MIT
// Actual staged global/VMID/submit methods, with CPU memory/register/TLB doubles.
// This is no native SDK, mapping, GPU-drain or physical execution acceptance.
#include "global-binding-CPU-only.h"
static thread_local bool failDword=false;
static std::atomic<unsigned> dwordReads{0};
static bool raw32(const volatile uint32_t *p,uint32_t *out) {
    CHECK(gpuHeld==1); ++dwordReads; event("dword-read"); *out=*p; return !failDword;
}
static bool forbidden64(const volatile uint32_t *,uint64_t *) { CHECK(false); return false; }
static void globalReset() {
    reset(); dwordReads=sleepCalls=0; testTicks=10000000; failDword=false;
}
static void adopt(PhxBringup &d,unsigned qi) {
    CHECK(qi<2); const uint64_t in[6]={qi ? 4096u : 0u,1024,qi ? 8256u : 8192u,qi ? 8u : 0u,8,(qi ? 9008u : 9000u)|qi};
    CHECK(d.adoptQueue(in)==kIOReturnSuccess);
}
static void context(PhxBringup &d,unsigned handle) {
    CHECK(handle && handle<=PhxBringup::kMaxCtx); auto &c=d.vm[handle-1];
    c.busy=true; c.phys=uint64_t(handle)<<16; c.used=1;
}
static void setup(PhxBringup &d,IOAccelPhxNativeClient &c,uint64_t seq=99,unsigned handle=7) {
    d.gSeq=seq; adopt(d,0); adopt(d,1); context(d,handle); c.contextID=handle; start(c,d);
    d.exactFenceReader=forbidden64; d.exactDwordReader=raw32;
}
static int call(IOAccelPhxNativeClient &c,bool gfx,uint64_t &seq) {
    Request request(gfx); IOLockLock(c.lock); int r=c.doSubmit(&request.a); IOLockUnlock(c.lock);
    seq=request.a.scalarOutput[0]; return r;
}
static uint64_t accepted(IOAccelPhxNativeClient &c,bool gfx=true) {
    uint64_t out; CHECK(call(c,gfx,out)==kIOReturnSuccess && out!=sentinel); return out;
}
static bool snapshot(PhxBringup &d,uint64_t &out) {
    CallbackGate<>::Lease lease(d.exactCallbacks); if(!lease) return false;
    IOLockLock(d.gpuLock); bool ok=d.exactGlobalRetiredLocked(out); IOLockUnlock(d.gpuLock); return ok;
}
static unsigned bind(PhxBringup &d,unsigned handle,uint64_t retired) {
    CallbackGate<>::Lease lease(d.exactCallbacks); CHECK(lease);
    IOLockLock(d.gpuLock); auto v=d.vmBind(handle,retired); IOLockUnlock(d.gpuLock); return v;
}
static void prefixAndExact() {
    for(uint64_t base:{99ull,0xfffffffdull,0x12345678fffffffdull}) {
        globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,base);
        const auto compute=accepted(c,false),gfx=accepted(c),gfx2=accepted(c);
        d.setFence(1,gfx2); CHECK(c.queryExact(gfx)==Status::Complete && c.queryExact(compute)==Status::Pending);
        uint64_t out=sentinel; CHECK(snapshot(d,out) && out==base && d.gpuRetired()==base);
        CHECK(d.hwv[0].lastSeq==gfx2 && d.vm[6].hw==8);
        d.setFence(0,compute); CHECK(snapshot(d,out) && out==gfx2 && d.gpuRetired()==gfx2);
        CHECK(d.registers.size()==7 && d.tlbCalls==1); // cached context never reprogrammed
        CHECK(c.queryExact(compute)==Status::Complete);
    }
}
static void history(PhxBringup &d,unsigned qi,uint64_t done,const std::vector<uint64_t> &seqs,uint32_t head=0) {
    auto &q=d.gq[qi]; q.head=head; q.tail=head+uint32_t(seqs.size());
    for(unsigned i=0;i<seqs.size();++i) q.fseq[(head+i)&63]=seqs[i];
    d.exactFenceWindow[qi].invalidate(); ++d.exactQueueGeneration[qi];
    CHECK(d.exactFenceWindow[qi].seed(d.exactQueueGeneration[qi],done));
    d.exactQueueSubmitted[qi]=seqs.empty() ? done : seqs.back();
    if(!seqs.empty() && seqs.back()>done) CHECK(d.exactFenceWindow[qi].submit(d.exactQueueGeneration[qi],seqs.back()));
    d.setFence(qi,done);
}
static void snapshotHistories() {
    for(uint32_t head:{0u,62u,UINT32_MAX-1}) {
        globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,0x1234500000000ull);
        const auto base=d.gSeq; d.gSeq+=500;
        history(d,0,base,{base+3,base+17,base+300},head);
        history(d,1,base+2,{base+2,base+400,base+500},head);
        uint64_t out=sentinel; CHECK(snapshot(d,out) && out==base+2);
        d.setFence(0,base+300); CHECK(snapshot(d,out) && out==base+399);
        d.setFence(1,base+500); CHECK(snapshot(d,out) && out==d.gSeq);
    }
    // Asymmetric adoption may start one queue at a later global sequence.
    globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    const auto compute=accepted(c,false); adopt(d,1); const auto gfx=accepted(c); d.setFence(1,gfx);
    uint64_t out=sentinel; CHECK(snapshot(d,out) && out==compute-1);
    d.setFence(0,compute); CHECK(snapshot(d,out) && out==gfx);
    // Never-adopted metadata is skippable only in the completely empty shape.
    globalReset(); PhxBringup single; IOAccelPhxNativeClient a; setup(single,a);
    single.exactQueueGeneration[0]=0; single.exactQueueLive[0]=false;
    single.exactQueueSubmitted[0]=0; single.gq[0].ready=false;
    CHECK(snapshot(single,out) && out==single.gSeq);
    CHECK(accepted(a)==100); single.setFence(1,100); CHECK(snapshot(single,out) && out==100);
}
static void malformedSnapshots() {
    for(unsigned mode=0;mode<24;++mode) {
        globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        const auto compute=accepted(c,false),gfx=accepted(c); d.setFence(1,gfx);
        auto &q=d.gq[0];
        switch(mode) {
        case 0: d.exactQueueLive[0]=false; break;
        case 1: q.ready=false; break;
        case 2: d.exactQueueGeneration[0]++; break;
        case 3: d.exactDwordReader=nullptr; break;
        case 4: failDword=true; break;
        case 5: d.exactQueueSubmitted[0]=d.gSeq+1; break;
        case 6: d.exactQueueSubmitted[1]=gfx-1; break; // decoded completion exceeds submitted
        case 7: { // Every entry is otherwise valid: isolate the capacity guard.
            std::vector<uint64_t> many(64);
            for(unsigned i=0;i<64;++i) many[i]=100+i;
            d.gSeq=163; history(d,0,99,many); break;
        }
        case 8: q.head=q.tail; break; // missing pending history
        case 9: q.fseq[0]=0; break;
        case 10: q.fseq[0]=UINT64_MAX; break;
        case 11: q.tail=2; q.fseq[0]=q.fseq[1]=compute; break;
        case 12: q.tail=2; q.fseq[0]=compute+1; q.fseq[1]=compute; break;
        case 13: q.fseq[0]=compute+1; break;
        case 14: q.fseq[0]=compute-1; break;
        case 15: d.exactStopped=true; break;
        case 16: d.isSleeping=true; break;
        case 17: d.gSeq=UINT64_MAX; break;
        case 18: d.exactQueueGeneration[0]=0; break;
        case 19: d.exactQueueGeneration[0]=0; d.exactQueueLive[0]=false; q.ready=false; break;
        case 20: q.fenceOff++; break;
        case 21: d.setFence(0,compute+1); break;
        case 22: d.exactCallbacks.close(); break;
        case 23: d.exactFenceWindow[0].invalidate(); break;
        }
        uint64_t out=sentinel; CHECK(!snapshot(d,out) && out==sentinel); CHECK(d.gpuRetired()==0);
        CHECK(c.exactRegistry.occupied()==2 && c.retained==1 && d.retained==1 && !frees && !terminations);
    }
    for(unsigned mode=0;mode<4;++mode) {
        globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
        d.exactQueueGeneration[0]=0; d.exactQueueLive[0]=d.gq[0].ready=false;
        d.exactQueueSubmitted[0]=0;
        if(mode==0) d.gq[0].ready=true;
        if(mode==1) d.exactQueueLive[0]=true;
        if(mode==2) d.gq[0].head=1;
        if(mode==3) d.exactQueueSubmitted[0]=1;
        uint64_t out=sentinel; CHECK(!snapshot(d,out) && out==sentinel);
    }
}
static void referencePrefixes() {
    // Independent job-list oracle, including gaps and both uint32 counter wraps.
    // Synthetic histories use controlled CPU completion bytes, never a GPU.
    for(unsigned round=0;round<16;++round) {
        const uint64_t base=round&1 ? 0x3456fffffffaull : 99ull;
        std::vector<std::pair<uint64_t,unsigned>> jobs;
        std::vector<uint64_t> queues[2]; uint64_t last=base;
        for(unsigned i=0;i<10;++i) {
            last+=1+(i+round)%7; const unsigned qi=(i+(i>>1)+round)&1;
            jobs.emplace_back(last,qi); queues[qi].push_back(last);
        }
        for(unsigned a=0;a<=queues[0].size();++a) for(unsigned b=0;b<=queues[1].size();++b) {
            globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,base); d.gSeq=last;
            const uint64_t done[2]={a ? queues[0][a-1] : base,b ? queues[1][b-1] : base};
            for(unsigned qi=0;qi<2;++qi) history(d,qi,done[qi],queues[qi],UINT32_MAX-2);
            uint64_t expected=last;
            for(const auto &job:jobs) if(job.first>done[job.second]) { expected=job.first-1; break; }
            uint64_t out=sentinel; CHECK(snapshot(d,out) && out==expected);
            CHECK(d.gpuRetired()==expected && d.registers.empty() && !packetWrites);
        }
    }
}
static void fillPool(PhxBringup &d,uint64_t lastSeq) {
    d.hwTick=100;
    for(unsigned i=0;i<8;++i) {
        context(d,i+1); d.vm[i].hw=8+i;
        d.hwv[i].ctx=i+1; d.hwv[i].lastSeq=lastSeq; d.hwv[i].lastUse=i+1;
    }
}
static void actualBinding() {
    { globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
      CHECK(!bind(d,0,99) && !bind(d,97,99) && !bind(d,6,99));
      CHECK(!bind(d,7,100) && !bind(d,7,UINT64_MAX) && d.registers.empty());
      CHECK(bind(d,7,99)==8 && d.vm[6].hw==8 && d.hwv[0].ctx==7);
      const std::vector<std::pair<uint32_t,uint32_t>> expected={
        {kRegCtx0BaseLo+16,0x70003},{kRegCtx0BaseLo+17,0},{kRegCtx0Cntl+8,0x01fffe07},
        {kRegCtx0StartLo+16,0},{kRegCtx0StartLo+17,0},{kRegCtx0EndLo+16,0xffffffff},{kRegCtx0EndLo+17,0xf}};
      CHECK(d.registers==expected && d.tlbCalls==1);
      const auto use=d.hwv[0].lastUse; CHECK(bind(d,7,99)==8 && d.hwv[0].lastUse>use);
      CHECK(d.registers==expected && d.tlbCalls==1);
    }
    for(unsigned mode=0;mode<9;++mode) {
        globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,99,30); fillPool(d,100);
        unsigned expected=0;
        if(mode==0) { d.hwv[5].ctx=0; expected=13; }
        if(mode==1) { d.hwv[3].lastSeq=d.hwv[6].lastSeq=99; expected=11; }
        if(mode==2) { d.hwv[0].lastSeq=99; d.vm[0].hw=9; }
        if(mode==3) { d.hwv[0].lastSeq=99; d.vm[0].busy=false; }
        if(mode==4) { d.vm[29].hw=8; }
        if(mode==5) { d.vm[29].hw=7; }
        if(mode==6) { d.vm[29].hw=16; }
        if(mode==7) { d.hwv[0].lastSeq=99; d.hwv[0].ctx=97; }
        CHECK(bind(d,30,99)==expected);
        CHECK(d.registers.size()==(expected ? 7u : 0u) && d.tlbCalls==(expected ? 1u : 0u));
        if(expected) CHECK(d.vm[29].hw==expected && d.hwv[expected-8].ctx==30);
        if(mode==1) CHECK(!d.vm[3].hw && d.vm[6].hw==14); // only eligible LRU is evicted
    }
}
static void noUnsafePromotionOrLockedSpin() {
    for(bool exact:{false,true}) {
        globalReset(); PhxBringup d; IOAccelPhxNativeClient c,legacy; setup(d,c,99,30);
        context(d,31); legacy.contextID=31; CHECK(legacy.start(&d));
        d.gSeq=101; history(d,0,99,{100}); history(d,1,101,{101}); fillPool(d,100);
        auto &client=exact ? c : legacy; uint64_t out=0;
        CHECK(call(client,true,out)==kIOReturnBusy && out==sentinel);
        CHECK(sleepCalls==2000 && d.registers.empty() && !packetWrites && d.gSeq==101);
        for(unsigned i=0;i<8;++i) CHECK(d.hwv[i].ctx==i+1 && d.vm[i].hw==i+8);
        CHECK(!c.exactRegistry.occupied() && !frees && !terminations);
    }
    // The first admission itself consumed the full monotonic budget: no extra yield.
    globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,99,30);
    fillPool(d,100); unsigned reads=0;
    eventHook=[&](const char *name) { if(!std::strcmp(name,"dword-read") && ++reads==3) testTicks+=2000000000ull; };
    uint64_t out=0; CHECK(call(c,true,out)==kIOReturnBusy && out==sentinel); eventHook={};
    CHECK(!sleepCalls && d.registers.empty() && !packetWrites && !c.exactRegistry.occupied());
}
static void waiterAllowsGfxProgress() {
    globalReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient waiter,gfx; setup(d,waiter,99,30);
    context(d,1); gfx.contextID=1; start(gfx,d);
    d.gSeq=100; history(d,0,99,{100}); history(d,1,99,{}); fillPool(d,100);
    Pause pause; int result=-1; uint64_t out=0; bool first=true;
    std::thread t([&] {
        eventHook=[&](const char *name) { if(!std::strcmp(name,"sleep") && first) { first=false; pause.arrive(); } };
        result=call(waiter,true,out); eventHook={};
    });
    pause.wait(); CHECK(sleepCalls==1 && !packetWrites && d.registers.empty());
    const auto progressed=accepted(gfx); CHECK(progressed==101); // different client obtained gpuLock
    IOLockLock(d.gpuLock); d.setFence(1,progressed); IOLockUnlock(d.gpuLock);
    CHECK(gfx.queryExact(progressed)==Status::Complete);
    uint64_t prefix=sentinel; CHECK(snapshot(d,prefix) && prefix==99);
    IOLockLock(d.gpuLock); d.setFence(0,100); IOLockUnlock(d.gpuLock);
    pause.release(); t.join(); CHECK(result==kIOReturnSuccess && out==102 && sleepCalls==1);
    CHECK(d.vm[29].hw==9 && !d.vm[1].hw && d.hwv[0].ctx==1); // keep most recently used GFX slot
    CHECK(d.registers.size()==7 && d.tlbCalls==1 && waiter.exactRegistry.occupied()==1);
}
static void terminalDuringRetry(unsigned mode) {
    globalReset(); ++threaded; PhxBringup d; IOAccelPhxNativeClient c; setup(d,c,99,30);
    // An existing receipt/resource set must survive abort of a later reservation.
    const auto old=accepted(c); d.setFence(1,old); d.registers.clear(); d.tlbCalls=0;
    d.vm[29].hw=0; fillPool(d,old+1); const auto writes=packetWrites.load();
    Pause pause; int result=-1; uint64_t out=0;
    std::thread t([&] {
        eventHook=[&](const char *name) { if(!std::strcmp(name,"sleep")) pause.arrive(); };
        result=call(c,true,out); eventHook={};
    });
    pause.wait();
    if(mode==0) CHECK(c.clientClose()==kIOReturnSuccess);
    if(mode==1) d.stop(nullptr);
    if(mode==2) { IOLockLock(d.gpuLock); d.invalidateExactQueues(); IOLockUnlock(d.gpuLock); }
    // Existing contract: an admitted client submit retains its lease after close.
    // It may finish or reach its bounded timeout; service stop/epoch loss abort.
    pause.release(); t.join();
    CHECK(result==(mode==0 ? kIOReturnBusy : kIOReturnNotReady) && out==sentinel);
    CHECK(sleepCalls==(mode==0 ? 2000u : 1u));
    CHECK(c.exactRegistry.occupied()>=1 && !frees && !terminations && c.retained==1);
    CHECK(d.registers.empty() && !d.tlbCalls && packetWrites==writes && d.gSeq==old);
}
static void stopAfterLastSnapshotRead() {
    globalReset(); PhxBringup d; IOAccelPhxNativeClient c; setup(d,c);
    // Empty never-adopted queue 1 means final gate, not its reader, detects closure.
    d.exactQueueGeneration[1]=0; d.exactQueueLive[1]=d.gq[1].ready=false;
    d.exactQueueSubmitted[1]=0;
    uint64_t out=sentinel;
    eventHook=[&](const char *name) { if(!std::strcmp(name,"dword-read")) {
        // Complete the reader; closure below occurs before helper final gate.
        d.exactStopped=true;
    } };
    CHECK(!snapshot(d,out) && out==sentinel); eventHook={};
}
int main() {
    prefixAndExact(); snapshotHistories(); malformedSnapshots(); referencePrefixes(); actualBinding();
    noUnsafePromotionOrLockedSpin(); waiterAllowsGfxProgress();
    for(unsigned mode=0;mode<3;++mode) terminalDuringRetry(mode);
    stopAfterLastSnapshotRead(); CHECK(!clientHeld && !gpuHeld);
    std::printf("PASS staged checked global and actual VMID: %llu checks; %u groups; %u threaded scenarios; GPU_executed=false\n",
        static_cast<unsigned long long>(checks.load()),groups,threaded);
}
