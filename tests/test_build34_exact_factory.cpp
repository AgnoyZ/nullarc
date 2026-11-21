// SPDX-License-Identifier: MIT
// Actual factory/start/registration/adoption bodies. OSObjects, registration,
// mappings, timer readiness and close finalization are explicit CPU models.
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
#define CHECK(x) do { ++checks; if(!(x)){std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x);std::_Exit(86);} } while(0)
static thread_local std::function<void(const char *)> hook;
static void event(const char *s){if(hook)hook(s);}
using task_t=void *;using UInt32=uint32_t;using IOReturn=int;
static constexpr IOReturn kIOReturnSuccess=0,kIOReturnBadArgument=1,kIOReturnNotReady=2,kIOReturnNoMemory=3,
    kIOReturnExclusiveAccess=4,kIOReturnBusy=5,kIOReturnNoResources=6,IOPMAckImplied=7;
static std::atomic<bool> failAlloc{false},failInit{false},failAttach{false},failBaseStart{false};
static std::atomic<unsigned> allocs{0},inits{0},attaches{0},detaches{0},baseStarts{0},frees{0},closes{0},sysctls{0};
static volatile UInt32 gSysctlUp=0;
static int sysctl__debug_phxbos_flush,sysctl__debug_phxbos_flush_bytes,sysctl__debug_phx_hang_ms,sysctl__debug_phx_hang_kills;
static bool OSCompareAndSwap(UInt32 old,UInt32 value,volatile UInt32 *p){return __atomic_compare_exchange_n(p,&old,value,false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);}
static void sysctl_register_oid(int *){++sysctls;event("register-sysctl");}
struct OSObject {
    std::atomic<unsigned> refs{1};std::atomic<bool> dead{false};
    virtual ~OSObject()=default;
    void retain(){CHECK(!dead&&refs.fetch_add(1)>0);}
    virtual void free(){CHECK(!dead.exchange(true));++frees;}
    void release(){CHECK(!dead);auto n=refs.fetch_sub(1);CHECK(n>0);if(n==1)free();}
};
struct IOService:OSObject{};
struct IOUserClient:IOService {
    bool attached=false;
    bool initWithTask(task_t,void *,UInt32){++inits;event("client-init");return !failInit;}
    bool attach(IOService *){++attaches;event("client-attach");attached=!failAttach;return attached;}
    void detach(IOService *){CHECK(attached&&!dead);attached=false;++detaches;}
    virtual bool start(IOService *){++baseStarts;event("base-client-start");return !failBaseStart;}
    virtual IOReturn clientClose(){return kIOReturnNotReady;}
};
#define OSDynamicCast(type,p) dynamic_cast<type *>(p)
static thread_local unsigned gpuHeld=0;
struct IOLock{std::mutex mutex;};
static void IOLockLock(IOLock *p){CHECK(p&&!gpuHeld);event("gpu-before-lock");p->mutex.lock();++gpuHeld;}
static void IOLockUnlock(IOLock *p){CHECK(p&&gpuHeld==1);--gpuHeld;p->mutex.unlock();}
struct IOMemoryMap{std::vector<uint64_t> words;explicit IOMemoryMap(size_t n):words(n/8){}uint64_t getLength()const{return words.size()*8;}uintptr_t getVirtualAddress(){event("aperture-address");return reinterpret_cast<uintptr_t>(words.data());}};
static uint64_t mach_absolute_time(){return 100;}
static void IOLog(const char *,...){}
struct IOAccelPhxNativeClient;
struct FakeRegistry{};
struct PhxBringup:IOService {
    // PHX34_FIELDS
    // PHX34_QUEUE
    uint64_t gSeq=0,exactQueueGeneration[2]{},exactQueueSubmitted[2]{},exactInvalidationEpoch=0;
    bool exactQueueLive[2]{},exactStopped=false,isSleeping=false,exactVMFault=false;
    bool hangStop=false,timerReady=true;
    phx34_exact::FenceWindow32 exactFenceWindow[2];
    IOLock gpuStorage;IOLock *gpuLock=&gpuStorage;
    IOMemoryMap aperture{0x40000},doorbells{0x1000},registers{0x60000};
    IOMemoryMap *fbAper=&aperture,*doorbellMap=&doorbells,*mmio=&registers;
    uint64_t fbMcBase=0x100000000,fbAperLen=0x40000;
    struct {bool active=false,terminal=false;}watchdogRecovery;
    static constexpr uint32_t kMaxCtx=96;
    struct LegacyClientSlot{IOAccelPhxNativeClient *client=nullptr;bool pending=false;};
    LegacyClientSlot legacyClients[kMaxCtx]{};
    bool hangTimerReady()const{event("timer-ready");return timerReady&&!__atomic_load_n(&hangStop,__ATOMIC_ACQUIRE);}
    bool hangStopping()const{return __atomic_load_n(&hangStop,__ATOMIC_ACQUIRE);}
    void requestHangDrain(){__atomic_store_n(&hangStop,true,__ATOMIC_RELEASE);}
    void hdpFlush()const{event("hdp-flush");}
    bool claimSession(){event("claim-session");return false;}
    bool bindExactClient(FakeRegistry &,OSObject *){return false;}
    // PHX34_GETTER
    IOReturn newUserClient(task_t,void *,UInt32,IOUserClient **);
    IOReturn adoptQueue(const uint64_t[6]);
    bool registerLegacyClient(OSObject *);
    bool requestLegacyClose(IOAccelPhxNativeClient *);
    void stop(IOService *);void sealStoppedQueues();void invalidateExactQueues();
    IOReturn setPowerState(unsigned long,IOService *);
};
struct IOAccelPhxNativeClient:IOUserClient {
    PhxBringup *owner=nullptr;bool exactRequested=false,exactStartAttempted=false,exactClientPinned=false;
    bool legacyClientPinned=false,legacyProviderPinned=false,sessionClaimed=false;
    uint32_t legacyState=0;FakeRegistry exactRegistry,*exactOwnership=nullptr;
    phx34_exact::CallbackGate<> exactClientCallbacks;
    bool start(IOService *)override;
    IOReturn clientClose()override{
        ++closes;exactClientCallbacks.close();
        CHECK(owner&&owner->requestLegacyClose(this));
        // This fixture does not replace the frozen actual VM/BO close suites.
        // A closed provider retains registration/provider pins, never GPU frees.
        CHECK(owner->exactCallbacks.closed()&&legacyClientPinned&&legacyProviderPinned);
        return kIOReturnNotReady;
    }
};
static std::mutex poolMutex;
static std::vector<std::unique_ptr<IOAccelPhxNativeClient>> clients;
static IOAccelPhxNativeClient *allocateClient(){
    ++allocs;event("allocate-client");if(failAlloc)return nullptr;
    auto p=std::make_unique<IOAccelPhxNativeClient>();auto *r=p.get();
    std::lock_guard<std::mutex> guard(poolMutex);clients.push_back(std::move(p));return r;
}
#define OSTypeAlloc(type) allocateClient()
// PHX34_METHODS
struct Pause{
    std::mutex m;std::condition_variable cv;bool reached=false,released=false;
    void arrive(){std::unique_lock<std::mutex> l(m);reached=true;cv.notify_all();CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return released;}));}
    void wait(){std::unique_lock<std::mutex> l(m);CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return reached;}));}
    void resume(){std::lock_guard<std::mutex> l(m);released=true;cv.notify_all();}
};
static void reset(){
    CHECK(!gpuHeld);hook={};++groups;
    failAlloc=failInit=failAttach=failBaseStart=false;
    allocs=inits=attaches=detaches=baseStarts=frees=closes=sysctls=0;
    __atomic_store_n(&gSysctlUp,0u,__ATOMIC_RELEASE);
}
static IOUserClient *sentinel(){return reinterpret_cast<IOUserClient *>(uintptr_t{0x1234});}
static IOReturn open(PhxBringup &d,IOUserClient *&out){return d.newUserClient(nullptr,nullptr,PHXN_UC_TYPE,&out);}
static void adopt(PhxBringup &d,unsigned qi=0){uint64_t a[6]={qi?4096u:0u,1024,qi?8256u:8192u,qi?8u:0u,8,(qi?9008u:9000u)|qi};CHECK(d.adoptQueue(a)==kIOReturnSuccess);}
static void priorCounterexamples(){
    reset();PhxBringup d;d.stop(nullptr);IOUserClient *out=sentinel();
    CHECK(open(d,out)==kIOReturnExclusiveAccess&&out==sentinel()&&allocs==1&&attaches==1&&sysctls==4);
    reset();++threaded;PhxBringup p;Pause pause;IOReturn r=-1;out=sentinel();
    std::thread t([&]{hook=[&](const char *s){if(!std::strcmp(s,"claim-session"))pause.arrive();};r=open(p,out);hook={};});
    pause.wait();CHECK(p.exactCallbacks.active()==0);p.stop(nullptr);pause.resume();t.join();
    auto *client=dynamic_cast<IOAccelPhxNativeClient *>(out);
    CHECK(r==kIOReturnSuccess&&client&&client->legacyState==2&&!client->exactClientCallbacks.closed()&&p.exactCallbacks.closed());
    std::puts("PASS prior factory CPU counterexamples: post-close allocation/attach and late handler; GPU_executed=false");
}
static void readinessRace(){
    reset();PhxBringup d;std::atomic<bool>go{false},stop{false};std::atomic<unsigned>reads{0};
    std::thread r([&]{go=true;while(!stop.load(std::memory_order_relaxed))reads.fetch_add(d.gpuReady()?2u:1u,std::memory_order_relaxed);});
    while(!go.load()||reads<100)std::this_thread::yield();
    adopt(d);stop.store(true,std::memory_order_relaxed);r.join();CHECK(d.gpuReady());
}
static void factoryCases(){
    reset();PhxBringup d;IOUserClient *out=sentinel();CHECK(open(d,out)==kIOReturnSuccess&&out&&out!=sentinel());
    auto *c=dynamic_cast<IOAccelPhxNativeClient *>(out);CHECK(c&&c->legacyState==2&&c->legacyClientPinned&&c->legacyProviderPinned);
    CHECK(c->refs==2&&d.refs==2&&sysctls==4&&!d.exactCallbacks.active());
    for(unsigned i=0;i<6;++i){
        reset();PhxBringup p;out=sentinel();
        if(i==0)failAlloc=true;if(i==1)failInit=true;if(i==2)failAttach=true;if(i==3)failBaseStart=true;
        if(i==4)p.timerReady=false;if(i==5)p.stop(nullptr);
        auto r=open(p,out);CHECK(r==(i<3?kIOReturnNoMemory:i==3?kIOReturnExclusiveAccess:kIOReturnNotReady)&&out==nullptr);
        CHECK(!p.exactCallbacks.active());
        if(i>=4)CHECK(!allocs&&!inits&&!attaches&&!sysctls);
        if(i==1||i==2)CHECK(frees==1&&!detaches);
        if(i==3)CHECK(frees==1&&detaches==1&&!closes);
    }
    reset();PhxBringup p;CHECK(p.newUserClient(nullptr,nullptr,PHXN_UC_TYPE,nullptr)==kIOReturnBadArgument&&!allocs&&!sysctls);
    CHECK(p.newUserClient(nullptr,nullptr,0,&out)==kIOReturnBadArgument&&out==nullptr&&!allocs&&!sysctls);
    reset();PhxBringup full;for(auto &s:full.legacyClients)s.client=reinterpret_cast<IOAccelPhxNativeClient *>(uintptr_t{1});
    out=sentinel();CHECK(open(full,out)==kIOReturnExclusiveAccess&&out==nullptr&&frees==1&&detaches==1&&full.refs==1);
}
static void closeDuringFactory(){
    const char *points[]={"register-sysctl","allocate-client","client-init","client-attach","base-client-start","claim-session"};
    for(const char *point:points){
        reset();++threaded;PhxBringup d;Pause p;IOUserClient *out=sentinel();IOReturn result=-1;
        std::thread t([&]{bool once=true;hook=[&](const char *s){if(once&&!std::strcmp(point,s)){once=false;p.arrive();}};result=open(d,out);hook={};});
        p.wait();CHECK(d.exactCallbacks.active()==1);d.stop(nullptr);
        CHECK(d.exactCallbacks.closed()&&!d.exactCallbacks.drained()&&!d.exactStopped);
        p.resume();t.join();CHECK(result==kIOReturnNotReady&&out==nullptr&&d.exactCallbacks.drained());
        CHECK(baseStarts==((!std::strcmp(point,"base-client-start")||!std::strcmp(point,"claim-session"))?1u:0u));
        if(!std::strcmp(point,"claim-session")){
            auto *c=clients.back().get();CHECK(closes==1&&detaches==1&&!frees&&c->exactClientCallbacks.closed());
            CHECK(c->refs==1&&c->legacyClientPinned&&c->legacyProviderPinned&&!c->dead&&d.refs==3);
            CHECK(d.legacyClients[0].client==c&&d.legacyClients[0].pending);
        }
        d.sealStoppedQueues();CHECK(d.exactStopped);
    }
}
static void parallelFactories(){
    reset();++threaded;PhxBringup d;std::vector<std::thread>threads;
    std::mutex mutex;std::condition_variable cv;unsigned ready=0;bool go=false;
    for(unsigned i=0;i<8;++i)threads.emplace_back([&]{
        bool once=true;hook=[&](const char *s){if(once&&!std::strcmp(s,"timer-ready")){
            once=false;std::unique_lock<std::mutex> l(mutex);++ready;cv.notify_all();
            CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return go;}));
        }};
        IOUserClient *out=sentinel();CHECK(open(d,out)==kIOReturnSuccess&&out&&out!=sentinel());hook={};
    });
    // All factory leases enter before any participant reaches the sysctl flag.
    // No callback-gate acquire after the first writer can mask a plain read.
    {std::unique_lock<std::mutex> l(mutex);CHECK(cv.wait_for(l,std::chrono::seconds(5),[&]{return ready==8;}));go=true;cv.notify_all();}
    for(auto &t:threads)t.join();CHECK(sysctls==4&&allocs==8&&d.refs==9&&!d.exactCallbacks.active());
    unsigned slots=0;for(const auto &slot:d.legacyClients)if(slot.client)++slots;CHECK(slots==8);
}
static void configuredPublication(){
    reset();PhxBringup d;CHECK(!d.gpuReady()&&!d.exactConfiguredQueues);Pause p;IOReturn result=-1;
    ++threaded;std::thread t([&]{hook=[&](const char *s){if(!std::strcmp(s,"hdp-flush"))p.arrive();};adopt(d);result=0;hook={};});
    p.wait();CHECK(!d.gpuReady());p.resume();t.join();CHECK(result==0&&d.gpuReady()&&d.exactConfiguredQueues==1);
    adopt(d,1);CHECK(d.exactConfiguredQueues==3);
    IOLockLock(d.gpuLock);d.invalidateExactQueues();IOLockUnlock(d.gpuLock);
    CHECK(d.gpuReady()&&d.exactConfiguredQueues==3&&!d.exactQueueLive[0]&&!d.exactQueueLive[1]);
    CHECK(d.setPowerState(0,nullptr)==IOPMAckImplied&&d.gpuReady());
    CHECK(d.setPowerState(1,nullptr)==IOPMAckImplied&&d.gpuReady());
    d.stop(nullptr);CHECK(d.gpuReady()&&d.exactConfiguredQueues==3); // configured != live; never E1 fallback
    ++threaded;readinessRace();
}
int main(int argc,char **argv){
    if(argc>1&&!std::strcmp(argv[1],"prior")){priorCounterexamples();return 0;}
    if(argc>1&&!std::strcmp(argv[1],"readiness-race")){readinessRace();std::puts("PASS configured readiness CPU race scenario; GPU_executed=false");return 0;}
    if(argc>1&&!std::strcmp(argv[1],"sysctl-race")){parallelFactories();std::puts("PASS factory CPU sysctl scenario; GPU_executed=false");return 0;}
    factoryCases();closeDuringFactory();parallelFactories();configuredPublication();
    std::printf("PASS native factory: %u checks; %u groups; %u threaded scenarios; GPU_executed=false\n",checks.load(),groups,threaded);
}
