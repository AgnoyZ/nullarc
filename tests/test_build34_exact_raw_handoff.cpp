// SPDX-License-Identifier: MIT
// Actual public method bodies; CPU mappings/registers/PSP transport only.
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>
#include "PhxNativeABI.h"
#include "build34_exact_callbacks.h"
#include "build34_exact_fence32.h"
static std::atomic<unsigned> checks{0};
static unsigned groups=0,threaded=0;
#define CHECK(x) do { ++checks; if(!(x)) { std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x); std::_Exit(86); } } while(0)
static thread_local std::function<void(const char *)> hook;
static void event(const char *s) { if(hook)hook(s); }
using IOReturn=int;
static constexpr IOReturn kIOReturnSuccess=0,kIOReturnNotReady=1,kIOReturnBusy=2,kIOReturnBadArgument=3,
    kIOReturnNoResources=4,kIOReturnExclusiveAccess=5,kIOReturnNoMemory=6,kIOReturnNotPermitted=7,kIOReturnTimeout=8;
static thread_local unsigned gpuHeld=0,smuHeld=0;
struct IOLock { std::mutex mutex; bool gpu=false; };
static void IOLockLock(IOLock *p) { CHECK(p);event(p->gpu?"gpu-before-lock":"smu-before-lock");p->mutex.lock();if(p->gpu)++gpuHeld;else ++smuHeld; }
static void IOLockUnlock(IOLock *p) { CHECK(p);if(p->gpu){CHECK(gpuHeld==1);--gpuHeld;}else{CHECK(smuHeld==1);--smuHeld;}p->mutex.unlock(); }
struct IOService {};
struct IOMemoryMap {
    std::vector<uint64_t> words; const char *name; mutable std::atomic<unsigned> calls{0};
    IOMemoryMap(size_t n,const char *s):words(n/8),name(s){}
    uint64_t getLength() const { return words.size()*8; }
    uintptr_t getVirtualAddress() { ++calls;event(name);return reinterpret_cast<uintptr_t>(words.data()); }
};
static constexpr int kernel_task=0,kIODirectionInOut=1,kIOMemoryPhysicallyContiguous=2;
struct IOBufferMemoryDescriptor {
    std::vector<uint64_t> data;
    explicit IOBufferMemoryDescriptor(size_t n):data((n+7)/8){}
    static IOBufferMemoryDescriptor *inTaskWithPhysicalMask(int,int,uint64_t n,uint64_t) { event("sys-allocate");return new IOBufferMemoryDescriptor(n); }
    void *getBytesNoCopy() { event("sys-bytes");return data.data(); }
    uint64_t getPhysicalAddress() { return 0x100000; }
    uint64_t getLength() { return data.size()*8; }
    void release() { event("sys-release");delete this; }
};
static void IOSleep(unsigned) { event("sleep"); }
static uint64_t mach_absolute_time() { return 100; }
static void IOLog(const char *,...) {}
struct Pause {
    std::mutex m;std::condition_variable cv;bool reached=false,released=false;
    void arrive(){std::unique_lock<std::mutex> l(m);reached=true;cv.notify_all();CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return released;}));}
    void wait(){std::unique_lock<std::mutex> l(m);CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return reached;}));}
    void resume(){std::lock_guard<std::mutex> l(m);released=true;cv.notify_all();}
};
struct PhxBringup {
    // PHX34_GATES
    // PHX34_QUEUE
    bool exactStopped=false,isSleeping=false,exactVMFault=false,hangStop=false;
    bool exactQueueLive[2]{};uint64_t exactQueueGeneration[2]{},exactQueueSubmitted[2]{},exactInvalidationEpoch=0,gSeq=100;
    phx34_exact::FenceWindow32 exactFenceWindow[2];
    using ExactDwordReader=bool (*)(const volatile uint32_t *,uint32_t *);
    ExactDwordReader exactDwordReader=nullptr;
    struct {bool active=false,terminal=false;}watchdogRecovery;
    IOMemoryMap aperture{0x40000,"aperture-address"},registers{0x60000,"register-address"},doorbells{0x1000,"doorbell-address"};
    IOMemoryMap *fbAper=&aperture,*mmio=&registers,*doorbellMap=&doorbells;
    uint64_t fbAperLen=0x40000,fbMcBase=0x100000000,fbPhys=0;
    IOLock gpuStorage,smuStorage;IOLock *gpuLock=&gpuStorage,*smuLock=&smuStorage;
    IOBufferMemoryDescriptor *sysBuf=nullptr;
    uint64_t ringMc=1,ringOff=0,cmdOff=0x4000,cmdMc=0,fenceOff=0x8000,fenceMc=0;
    uint64_t tmrOff=0,tmrMc=0,tmrSize=0,fwBufOff=0x10000,fwBufMc=0,fwBufSize=0x1000;
    uint32_t fenceCounter=0,hdpFlushDword=0;bool tmrSetUp=false,smuUsed=false;
    std::atomic<unsigned> refs{1},pspCalls{0};
    PhxBringup(){gpuStorage.gpu=true;}
    ~PhxBringup(){if(sysBuf)sysBuf->release();}
    void retain(){++refs;}
    void requestHangDrain(){hangStop=true;} // timer backend tested separately; no model of IOKit here
    uint32_t smuPoll()const{event("smu-poll");return 1;}
    bool pspWaitTos(uint32_t)const{return true;}
    IOReturn pspRunCmd(uint32_t,const uint32_t *,uint32_t,uint64_t out[4]){++pspCalls;event("psp-transport");out[0]=0;return kIOReturnSuccess;}
    uint32_t rreg(uint32_t)const;void wreg(uint32_t,uint32_t)const;void hdpFlush()const;void clearRing();
    void stop(IOService *);void sealStoppedQueues();void invalidateExactQueues();
    bool readExactFence32(uint32_t,uint64_t *);
    IOReturn adoptQueue(const uint64_t[6]);
    // PHX34_DECLARATIONS
};
// PHX34_METHODS
static bool raw32(const volatile uint32_t *p,uint32_t *out){CHECK(gpuHeld==1);*out=*p;return true;}
static void next(){CHECK(!gpuHeld&&!smuHeld);hook={};++groups;}
static IOReturn invoke(PhxBringup &d,unsigned i){
    uint32_t out=0xabc,other=0xabc,bytes=0x12345678;uint64_t wide[4]={0xabc,0xabc,0xabc,0xabc};const uint32_t words[6]={};
    switch(i){
    case 0:return d.writeReg(4,0x1234,&out);
    case 1:return d.vramWrite(9000,101);
    case 2:return d.doorbellWrite(0,8);
    case 3:return d.sysMem(1,64,0,wide,wide+1);
    case 4:return d.smuMessage(1,0,&out,&other);
    case 5:return d.pspRing(3,0,wide);
    case 6:return d.pspSubmit(PHX_PSP_GFX_CMD_FB_FW_RESERV_ADDR,wide);
    case 7:return d.fwStage(0,&bytes,4);
    case 8:return d.loadIpFw(0,0,4,wide);
    case 9:return d.pspCtl(2,0,wide);
    case 10:return d.pspRaw(0,words,wide);
    case 11:return d.readRegs(0,1,&out);
    case 12:return d.vramRead(9000,1,&out);
    default:CHECK(false);return -1;
    }
}
static void inputs(uint64_t a[6],unsigned qi=0){a[0]=qi?4096:0;a[1]=1024;a[2]=qi?8256:8192;a[3]=qi?8:0;a[4]=8;a[5]=(qi?9008:9000)|qi;}
static void adopt(PhxBringup &d,unsigned qi=0){uint64_t a[6];inputs(a,qi);CHECK(d.adoptQueue(a)==kIOReturnSuccess);}
static bool read(PhxBringup &d,uint64_t &out){phx34_exact::CallbackGate<>::Lease callback(d.exactCallbacks);CHECK(callback);IOLockLock(d.gpuLock);bool r=d.readExactFence32(0,&out);IOLockUnlock(d.gpuLock);return r;}
static void unguardedCounterexamples(){
    next();PhxBringup d;d.exactDwordReader=raw32;adopt(d);d.gSeq=101;
    CHECK(d.exactFenceWindow[0].submit(d.exactQueueGeneration[0],101));d.exactQueueSubmitted[0]=101;
    uint64_t out=0;CHECK(read(d,out)&&out==100);
    CHECK(d.vramWrite(9000,101)==kIOReturnSuccess);CHECK(read(d,out)&&out==101); // CPU write spoofed completion
    d.gq[0].tail=1;auto gen=d.exactQueueGeneration[0];adopt(d);
    CHECK(d.exactQueueGeneration[0]>gen&&!d.gq[0].tail&&d.aperture.words[9000/8]==101);
    d.stop(nullptr);CHECK(d.writeReg(4,77,reinterpret_cast<uint32_t *>(&out))==kIOReturnSuccess);
    PhxBringup alias;alias.exactDwordReader=raw32;adopt(alias);alias.gSeq=101;
    CHECK(alias.exactFenceWindow[0].submit(alias.exactQueueGeneration[0],101));alias.exactQueueSubmitted[0]=101;
    uint64_t a[6];inputs(a,1);a[5]=9001;CHECK(alias.adoptQueue(a)==kIOReturnSuccess);
    CHECK(read(alias,out)&&out==101); // second queue's CPU seed overwrote the first queue's fence
    std::puts("PASS prior raw-write/closed-service/readoption/alias CPU counterexamples; GPU_executed=false");
}
static void admissionAndRefusals(){
    for(unsigned i=0;i<13;++i){
        next();PhxBringup d;CHECK(invoke(d,i)==kIOReturnSuccess);CHECK(d.exactCallbacks.active()==0);
        d.stop(nullptr);const auto accesses=d.aperture.calls+d.registers.calls+d.doorbells.calls,psp=d.pspCalls.load();
        CHECK(invoke(d,i)==kIOReturnNotReady);CHECK(d.exactCallbacks.drained()&&d.refs==2);
        CHECK(d.aperture.calls+d.registers.calls+d.doorbells.calls==accesses&&d.pspCalls==psp);
    }
    for(unsigned i=0;i<11;++i){
        next();PhxBringup d;adopt(d);CHECK(d.exactRawWriters.closed()&&d.exactRawWriters.drained());
        const auto accesses=d.aperture.calls+d.registers.calls+d.doorbells.calls,psp=d.pspCalls.load();
        CHECK(invoke(d,i)==kIOReturnNotReady);CHECK(!d.exactCallbacks.active());
        CHECK(d.aperture.calls+d.registers.calls+d.doorbells.calls==accesses&&d.pspCalls==psp);
        CHECK(invoke(d,11)==kIOReturnSuccess&&invoke(d,12)==kIOReturnSuccess);
        adopt(d,1);CHECK(d.exactQueueAdopted[0]&&d.exactQueueAdopted[1]);
    }
}
static void lifetimeAcrossClosure(){
    const char *pausePoints[]={"register-address","aperture-address","doorbell-address","sys-allocate","smu-poll",
        "smu-before-lock","psp-transport","aperture-address","psp-transport","psp-transport","psp-transport",
        "register-address","aperture-address"};
    for(unsigned i=0;i<13;++i){
        next();++threaded;PhxBringup d;Pause p;IOReturn r=-1;
        std::thread t([&]{bool once=true;hook=[&](const char *s){if(once&&!std::strcmp(s,pausePoints[i])){once=false;p.arrive();}};r=invoke(d,i);hook={};});
        p.wait();CHECK(d.exactCallbacks.active()==1);d.stop(nullptr);
        CHECK(d.exactCallbacks.closed()&&!d.exactCallbacks.drained()&&!d.exactStopped&&d.refs==2);
        CHECK(invoke(d,i)==kIOReturnNotReady);p.resume();t.join();CHECK(r==kIOReturnSuccess&&d.exactCallbacks.drained());
        d.sealStoppedQueues();CHECK(d.exactStopped); // drain prerequisite only; no resource release
    }
}
static void rawTransactionAndHandoff(){
    for(unsigned i=0;i<11;++i){
        next();++threaded;PhxBringup d;Pause p;IOReturn r=-1;
        std::thread t([&]{bool once=true;hook=[&](const char *){if(once){once=false;p.arrive();}};r=invoke(d,i);hook={};});
        p.wait();CHECK(d.exactRawWriters.active()==1&&d.exactCallbacks.active()==1);
        for(unsigned j=0;j<11;++j)CHECK(invoke(d,j)==kIOReturnBusy);
        uint64_t a[6];inputs(a);CHECK(d.adoptQueue(a)==kIOReturnBusy);
        CHECK(d.exactRawWriters.closed()&&!d.exactRawWriters.drained()&&!d.gq[0].ready&&!d.exactQueueAdopted[0]);
        CHECK(!d.exactQueueGeneration[0]&&!d.exactQueueSubmitted[0]&&!d.aperture.words[9000/8]);
        CHECK(invoke(d,i)==kIOReturnNotReady);p.resume();t.join();CHECK(r==kIOReturnSuccess);
        CHECK(d.exactRawWriters.drained());adopt(d);CHECK(d.exactQueueAdopted[0]);
    }
}
static void noCompletionSpoofOrReadoption(){
    next();PhxBringup d;d.exactDwordReader=raw32;adopt(d);d.gSeq=101;
    CHECK(d.exactFenceWindow[0].submit(d.exactQueueGeneration[0],101));d.exactQueueSubmitted[0]=101;
    CHECK(d.vramWrite(9000,101)==kIOReturnNotReady);uint64_t out=0;CHECK(read(d,out)&&out==100);
    d.gq[0].tail=1;auto gen=d.exactQueueGeneration[0];uint64_t a[6];inputs(a);
    CHECK(d.adoptQueue(a)==kIOReturnExclusiveAccess&&d.exactQueueGeneration[0]==gen&&d.gq[0].tail==1);
    CHECK(d.aperture.words[9000/8]==100);
    // Even history invalidation and ready=false do not prove an old writer stopped.
    IOLockLock(d.gpuLock);d.invalidateExactQueues();d.gq[0].ready=false;IOLockUnlock(d.gpuLock);
    CHECK(d.adoptQueue(a)==kIOReturnExclusiveAccess&&d.exactRawWriters.drained());
}
static void badAdoptionDoesNotCloseWriters(){
    for(unsigned i=0;i<9;++i){
        next();PhxBringup d;uint64_t a[6];inputs(a);
        if(i==0)a[1]=255;if(i==1)a[0]=d.fbAperLen;if(i==2)a[2]=d.fbAperLen-24;
        if(i==3)a[5]=d.fbAperLen;if(i==4)a[3]=d.doorbells.getLength();
        if(i==5)a[0]=UINT64_MAX-255;if(i==6)a[2]=UINT64_MAX-7;
        if(i==7)a[5]=UINT64_MAX-7;if(i==8)a[3]=UINT64_MAX-7;
        CHECK(d.adoptQueue(a)==kIOReturnBadArgument&&!d.exactRawWriters.closed()&&!d.exactQueueAdopted[0]);
        CHECK(invoke(d,0)==kIOReturnSuccess);
    }
    next();PhxBringup d;d.gSeq=UINT64_MAX;uint64_t a[6];inputs(a);
    CHECK(d.adoptQueue(a)==kIOReturnNoResources&&!d.exactRawWriters.closed());
}
static void adoptionRaces(){
    for(unsigned mode=0;mode<3;++mode){
        next();++threaded;PhxBringup d;Pause p;IOReturn r=-1;uint64_t a[6];inputs(a);
        std::thread t([&]{bool once=true;hook=[&](const char *s){if(once&&!std::strcmp(s,mode==2?"aperture-address":"gpu-before-lock")){once=false;p.arrive();}};r=d.adoptQueue(a);hook={};});
        p.wait();CHECK(d.exactCallbacks.active()==1);
        if(mode==0){d.stop(nullptr);p.resume();t.join();CHECK(r==kIOReturnNotReady&&!d.exactQueueAdopted[0]);}
        if(mode==1){adopt(d);p.resume();t.join();CHECK(r==kIOReturnExclusiveAccess&&d.exactQueueGeneration[0]==1);}
        if(mode==2){CHECK(d.exactRawWriters.drained());CHECK(invoke(d,1)==kIOReturnNotReady);p.resume();t.join();CHECK(r==kIOReturnSuccess);}
    }
}
static void disjointOwnedRanges(){
    for(unsigned mode=0;mode<3;++mode){
        next();PhxBringup d;uint64_t a[6];inputs(a);
        if(mode==0)a[2]=16;if(mode==1)a[5]=24;if(mode==2)a[5]=a[2]+8;
        CHECK(d.adoptQueue(a)==kIOReturnBadArgument&&!d.exactRawWriters.closed()&&!d.exactQueueAdopted[0]);
    }
    for(unsigned i=0;i<3;++i)for(unsigned j=0;j<3;++j){
        next();PhxBringup d;adopt(d);uint64_t a[6]={0x10000,1024,0x20000,8,8,0x21001};
        const uint64_t peer[3]={0,8192,9000};
        if(i==0)a[0]=peer[j]&~255ull;if(i==1)a[2]=peer[j];if(i==2)a[5]=peer[j]|1;
        const auto value=d.aperture.words[9000/8];
        CHECK(d.adoptQueue(a)==kIOReturnBadArgument&&!d.exactQueueAdopted[1]);
        CHECK(d.aperture.words[9000/8]==value&&d.exactQueueGeneration[0]==1&&!d.exactQueueGeneration[1]);
        IOLockLock(d.gpuLock);d.invalidateExactQueues();d.gq[0].ready=false;IOLockUnlock(d.gpuLock);
        CHECK(d.adoptQueue(a)==kIOReturnBadArgument); // not conditional on old ready flag
    }
    next();PhxBringup d;adopt(d);uint64_t a[6];inputs(a,1);a[3]=0;
    CHECK(d.adoptQueue(a)==kIOReturnBadArgument&&!d.exactQueueAdopted[1]);
}
int main(int argc,char **){
    if(argc>1){unguardedCounterexamples();return 0;}
    admissionAndRefusals();lifetimeAcrossClosure();rawTransactionAndHandoff();noCompletionSpoofOrReadoption();badAdoptionDoesNotCloseWriters();adoptionRaces();disjointOwnedRanges();
    CHECK(!gpuHeld&&!smuHeld);
    std::printf("PASS raw handoff: %u checks; %u groups; %u threaded scenarios; GPU_executed=false\n",checks.load(),groups,threaded);
}
