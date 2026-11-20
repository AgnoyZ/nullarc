// SPDX-License-Identifier: MIT
// Actual staged doSubmit/gpuSubmit/adoptQueue/retirement, CPU doubles only.
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <vector>
#include "PhxNativeABI.h"
#include "build34_exact_ownership.h"

using namespace phx34_exact;
static uint64_t checks, cases;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"failed %d: %s\n",__LINE__,#x); std::abort(); } } while (0)
using IOReturn = int;
enum { kIOReturnSuccess, kIOReturnNotReady, kIOReturnBadArgument, kIOReturnBusy,
       kIOReturnNoResources, kIOReturnNotFound, kIOReturnUnsupported };
static constexpr uint32_t kFirstUserVmid = 8;
static constexpr int kMaxMaps = 2;
static constexpr uint64_t kVaMask = (1ull << 48) - 1, sentinel = 0xabcde;
static int gpuToken, clientToken, otherClientToken;
static bool gpuHeld, clientHeld, otherClientHeld;
static uint64_t ticks, sleepTicks = 1000000;
static unsigned sleeps;
static std::function<void()> wake;
static void IOLockLock(void *p) {
    if (p == &gpuToken) { CHECK(!gpuHeld); gpuHeld = true; }
    else if (p == &otherClientToken) { CHECK(clientHeld && !otherClientHeld); otherClientHeld = true; }
    else { CHECK(p == &clientToken && !clientHeld); clientHeld = true; }
}
static void IOLockUnlock(void *p) {
    if (p == &gpuToken) { CHECK(gpuHeld); gpuHeld = false; }
    else if (p == &otherClientToken) { CHECK(otherClientHeld && !gpuHeld); otherClientHeld = false; }
    else { CHECK(p == &clientToken && clientHeld && !otherClientHeld && !gpuHeld); clientHeld = false; }
}
static uint64_t mach_absolute_time() { return ticks; }
static void absolutetime_to_nanoseconds(uint64_t value, uint64_t *out) { *out = value; }
static void IOSleep(unsigned ms) {
    CHECK(!gpuHeld && clientHeld && ms == 1 && sleeps < 3);
    ++sleeps; ticks += sleepTicks;
    if (wake) wake();
}
static void IOLog(const char *, ...) {}
static bool vaCanonical(uint64_t va) { return va >> 47 == 0 || va >> 47 == 0x1ffff; }
struct Memory {
    alignas(16) uint64_t words[2048]{};
    uintptr_t getVirtualAddress() const { return reinterpret_cast<uintptr_t>(words); }
    size_t getLength() const { return sizeof words; }
};
struct IOExternalMethodArguments {
    unsigned scalarInputCount = 0, scalarOutputCount = 1;
    size_t structureOutputSize = 0, structureInputSize = 0;
    void *structureInputDescriptor = nullptr;
    const void *structureInput = nullptr;
    uint64_t scalarOutput[1]{sentinel};
};
struct PhxBringup {
    struct GpuQueue {
        bool ready, gfx;
        uint32_t ringOff, ringDw, wbOff, fenceOff;
        uint64_t dbByte, wptr, doneEnd;
        uint64_t fseq[64], fend[64];
        uint32_t fvmid[64];
        volatile uint32_t head, tail;
        uint64_t lastDone, lastProgress, killedSeq;
        bool killedAll;
    };
    GpuQueue gq[2]{};
    uint64_t gSeq = 99, exactQueueGeneration[2]{11,22}, fbMcBase = 0x123400000ull;
    Memory aperture, bells;
    Memory *fbAper = &aperture, *doorbellMap = &bells;
    uint64_t fbAperLen = sizeof aperture.words;
    void *mmio = this, *gpuLock = &gpuToken;
    struct { uint64_t lastSeq = 0; } hwv[8];
    bool contextReady = true, bindReady = true;
    unsigned binds = 0, flushes = 0;
    Registry *expected = nullptr;
    std::vector<uint32_t> packets[2];
    PhxBringup() {
        for (unsigned i = 0; i < 2; ++i) {
            auto &q = gq[i]; q.ready = true; q.gfx = i == 1; q.ringDw = 1024;
            q.ringOff = i * 4096; q.wbOff = 8192 + i * 64;
            q.fenceOff = 9000 + i * 8; q.dbByte = i * 8;
            q.wptr = q.doneEnd = 8; setFence(i,99);
        }
    }
    bool gpuReady() const { return gq[0].ready || gq[1].ready; }
    bool debugEnabled() const { return false; }
    void *vmCtx(uint32_t h) { CHECK(gpuHeld); return h == 7 && contextReady ? this : nullptr; }
    uint32_t vmBind(uint32_t h) { CHECK(gpuHeld && h == 7); ++binds; return bindReady ? 8 : 0; }
    void setFence(unsigned i, uint64_t value) {
        std::memcpy(reinterpret_cast<uint8_t *>(aperture.words)+gq[i].fenceOff,&value,8);
    }
    void hdpFlush() { CHECK(gpuHeld); ++flushes; }
    void ringPut(GpuQueue &q, uint32_t index, uint32_t value) {
        CHECK(gpuHeld && clientHeld);
        const unsigned qi = &q == &gq[1];
        if (!index && expected) {
            // Before the FIRST packet write: a forged/wrong-queue receipt fails.
            // Global gSeq still has its old value until the legacy update site.
            const auto candidate = gSeq+1;
            Ticket t;
            CHECK(expected->lookup(candidate,t) == Status::Ok);
            QueueObservation observations[2]{};
            observations[qi] = {exactQueueGeneration[qi],candidate,gSeq,true,false};
            CHECK(expected->observe(t,true,observations) == Status::Pending);
        }
        if (!index) packets[qi].clear();
        CHECK(index == packets[qi].size()); packets[qi].push_back(value);
    }
    uint64_t queueFence(const GpuQueue &) const;
    uint64_t gpuRetired() const;
    IOReturn adoptQueue(const uint64_t[6]);
    // PHX34_EXACT_SUBMIT_DECLARATION
};
struct IOAccelPhxNativeClient {
    struct Bo { uint8_t *kva; uint64_t size; };
    struct Map { bool used; uint64_t va,size,off; uint32_t handle; } maps[kMaxMaps]{};
    PhxBringup *owner;
    void *clientLock = &clientToken;
    Registry *exactOwnership = nullptr;
    uint64_t lastSeq = 0, emitted = 0, pendFenceSeq = 0;
    uint32_t vmid = 7, pendFenceHandle = 0, pendFenceOffset = 0;
    bool ctx[PHXN_MAX_CTX+1]{}, coverage = true, vmidReady = true;
    alignas(8) uint64_t fenceWords[2]{0x111,0x222};
    Bo fenceBo{reinterpret_cast<uint8_t *>(fenceWords),sizeof fenceWords};
    unsigned flushes = 0;
    explicit IOAccelPhxNativeClient(PhxBringup *d, Registry *r) : owner(d),exactOwnership(r) { ctx[1] = true; }
    bool ibCovered(uint64_t, uint64_t) { CHECK(clientHeld); return coverage; }
    Bo *findBo(uint32_t h) { CHECK(clientHeld); return h == 1 ? &fenceBo : nullptr; }
    void flushBos() { CHECK(clientHeld); ++flushes; }
    bool ensureVmid() { CHECK(clientHeld); return vmidReady; }
    IOReturn doSubmit(IOExternalMethodArguments *);
};

// PHX34_EXACT_SUBMIT_METHODS

struct Request {
    phxn_cs_in h{};
    phxn_cs_ib ib[PHXN_MAX_IBS]{};
    IOExternalMethodArguments a;
    explicit Request(bool gfx = false, unsigned n = 1, bool fence = false) {
        h.abi = PHXN_ABI_VERSION; h.ctx_id = 1; h.num_ibs = n;
        if (fence) { h.flags = PHXN_CS_HAS_FENCE; h.fence_handle = 1; h.fence_offset = 8; }
        for (unsigned i=0; i<n; ++i) {
            ib[i].ip_type = gfx ? PHX_AMDGPU_HW_IP_GFX : PHX_AMDGPU_HW_IP_COMPUTE;
            ib[i].va_start = 0xffff800012340000ull + i*4096; ib[i].ib_bytes = 64 + i*4;
        }
        a.structureInput = &h; a.structureInputSize = sizeof(h)+n*sizeof(ib[0]);
        CHECK(reinterpret_cast<uint8_t *>(ib)-reinterpret_cast<uint8_t *>(&h) == sizeof h);
    }
    IOReturn run(IOAccelPhxNativeClient &c) {
        const bool nested = c.clientLock == &otherClientToken;
        CHECK(!gpuHeld && !otherClientHeld && (nested ? clientHeld : !clientHeld));
        IOLockLock(c.clientLock); const auto result = c.doSubmit(&a); IOLockUnlock(c.clientLock);
        CHECK(!gpuHeld && !otherClientHeld && (nested ? clientHeld : !clientHeld)); return result;
    }
};
static void reset() { CHECK(!gpuHeld && !clientHeld && !otherClientHeld); ticks = sleeps = 0; sleepTicks = 1000000; wake = {}; ++cases; }
static void noDispatch(const PhxBringup &d, const IOAccelPhxNativeClient &c, const Request &r) {
    CHECK(d.packets[0].empty() && d.packets[1].empty());
    CHECK(d.bells.words[0] == 0 && d.bells.words[1] == 0 && d.flushes == 0);
    CHECK(d.aperture.words[(8192+16)/8] == 0 && d.aperture.words[(8256+16)/8] == 0);
    CHECK(c.lastSeq == 0 && c.emitted == 0 && c.pendFenceSeq == 0);
    CHECK(c.fenceWords[0] == 0x111 && c.fenceWords[1] == 0x222 && r.a.scalarOutput[0] == sentinel);
}
static void packets(PhxBringup &d, const Request &r, unsigned qi, uint64_t seq) {
    const auto &q = d.gq[qi]; std::vector<uint32_t> expected;
    if (!qi) expected = {0xc0065800,0,0xffffffff,0xffffff,0,0,10,0xc3b1};
    for (unsigned i=0; i<r.h.num_ibs; ++i) {
        const auto &ib = r.ib[i];
        expected.insert(expected.end(),{0xc0023f00,uint32_t(ib.va_start),uint32_t(ib.va_start>>32),
            ib.ib_bytes/4 | (qi ? 0u : 1u<<23) | 8u<<24});
    }
    const auto address = d.fbMcBase+q.fenceOff;
    expected.insert(expected.end(),{0xc0064900,0x06603514,0x40000000,uint32_t(address),uint32_t(address>>32),uint32_t(seq),uint32_t(seq>>32),0});
    CHECK(d.packets[qi] == expected);
    CHECK(q.fseq[(q.tail-1)&63] == seq && q.fvmid[(q.tail-1)&63] == 8 && q.fend[(q.tail-1)&63] == q.wptr);
    CHECK(d.bells.words[qi] == q.wptr && d.aperture.words[(q.wbOff+16)/8] == q.wptr);
}
static Ticket lookup(Registry &r, uint64_t seq) { Ticket t; CHECK(r.lookup(seq,t)==Status::Ok); return t; }
static void fill(PhxBringup::GpuQueue &q) {
    q.tail = 63; q.ringDw = 4096;
    for (unsigned i=0; i<63; ++i) { q.fseq[i&63] = i+1; q.fend[i&63] = 8; }
}
static void matrix() {
    for (unsigned n : {1u,2u,PHXN_MAX_IBS}) for (unsigned requested=0; requested<2; ++requested)
        for (bool fallback : {false,true}) for (bool exact : {false,true}) for (bool fence : {false,true}) {
            reset(); Registry registry(1); PhxBringup d; Request r(requested,n,fence);
            const auto qi = fallback ? 1-requested : requested;
            if (fallback) d.gq[requested].ready = false;
            if (exact) d.expected = &registry;
            IOAccelPhxNativeClient c(&d,exact ? &registry : nullptr);
            CHECK(r.run(c)==kIOReturnSuccess && r.a.scalarOutput[0]==100);
            CHECK(c.lastSeq==100 && c.emitted==100 && d.gSeq==100 && !sleeps);
            CHECK(registry.occupied()==unsigned(exact)); packets(d,r,qi,100);
            if (fence) CHECK(c.pendFenceHandle==1 && c.pendFenceOffset==8 && c.pendFenceSeq==100 && c.fenceWords[1]==0x222);
        }
}
static void admission() {
    // No receipt means no dispatch, no synthetic E1 success, and no output publication.
    for (unsigned fault=0; fault<15; ++fault) {
        reset(); Registry registry(2); PhxBringup d; Request r(false,1,true); d.expected=&registry;
        IOAccelPhxNativeClient c(&d,&registry); IOReturn expected=kIOReturnNotReady;
        if (fault==0) { for (unsigned i=0;i<64;++i) { Ticket t; CHECK(registry.reserve(t)==Status::Ok); } expected=kIOReturnNoResources; }
        if (fault==1) { registry.close(); expected=kIOReturnNoResources; }
        if (fault==2) { d.gSeq=UINT64_MAX-1; expected=kIOReturnNoResources; }
        if (fault==3) { d.gSeq=UINT64_MAX; expected=kIOReturnNoResources; }
        if (fault==4) d.exactQueueGeneration[0]=0;
        if (fault==5) d.exactQueueGeneration[0]=UINT64_MAX;
        if (fault==6) d.contextReady=false;
        if (fault==7) { d.bindReady=false; expected=kIOReturnBusy; }
        if (fault==8) { d.gq[0].ready=d.gq[1].ready=false; }
        if (fault==9) { c.coverage=false; expected=kIOReturnBadArgument; }
        if (fault==10) { c.vmidReady=false; expected=kIOReturnNoResources; }
        if (fault==11) { r.ib[0].ib_bytes=3; expected=kIOReturnBadArgument; }
        if (fault==12) { r.h.fence_handle=2; expected=kIOReturnNotFound; }
        if (fault==13) { r.h.fence_offset=1; expected=kIOReturnBadArgument; }
        if (fault==14) { r.h.flags|=0x80000000u; expected=kIOReturnBadArgument; }
        const auto oldSeq=d.gSeq;
        CHECK(r.run(c)==expected); CHECK(d.gSeq==oldSeq); noDispatch(d,c,r);
        CHECK(registry.occupied()==(fault==0 ? 64u : 0u));
    }
    // Caller cannot mint a receipt for a foreign/cancelled/already-published lease.
    for (unsigned fault=0; fault<3; ++fault) {
        reset(); Registry registry(3), other(4); PhxBringup d;
        Ticket t; CHECK((fault==0 ? other : registry).reserve(t)==Status::Ok);
        if (fault==1) CHECK(registry.cancel(t)==Status::Ok);
        if (fault==2) CHECK(registry.publish(t,{98,11,0})==Status::Ok);
        uint64_t seq=sentinel, va=0x10000; uint32_t dw=16;
        IOLockLock(&clientToken);
        CHECK(d.gpuSubmit(7,false,&va,&dw,1,&seq,&registry,t)==kIOReturnNotReady);
        IOLockUnlock(&clientToken);
        CHECK(seq==sentinel && d.gSeq==99 && d.packets[0].empty() && !d.bells.words[0]);
        if (fault==2) CHECK(registry.occupied()==1 && registry.cancel(t)==Status::Invalid);
    }
}
static void retry() {
    for (unsigned change=0;change<7;++change) {
        reset(); Registry registry(5); PhxBringup d; Request r(true,change==3 ? PHXN_MAX_IBS : 1,true);
        d.expected=&registry; IOAccelPhxNativeClient c(&d,&registry);
        d.gq[1].ready=false; fill(d.gq[0]); d.setFence(0,0);
        wake=[&] {
            // A reservation exists, but no sequence is owned while gpuLock is released.
            CHECK(registry.occupied()==1 && d.gSeq==99 && d.packets[0].empty());
            Ticket t; CHECK(registry.lookup(100,t)==Status::Unknown);
            if (change==0) { d.gq[1].ready=true; }
            if (change==1 || change==3) {
                const uint64_t in[6]={0,change==3 ? 256u : 1024u,8192,0,8,9000};
                CHECK(d.adoptQueue(in)==kIOReturnSuccess);
            }
            if (change==2) d.contextReady=false;
            if (change==4) d.gq[0].ready=false;
            if (change==5) d.setFence(0,99);
        };
        if (change>=5) sleepTicks=2000000000ull;
        const auto expected=change<2 ? kIOReturnSuccess : change==3 ? kIOReturnBadArgument : change==2 || change==4 ? kIOReturnNotReady : kIOReturnBusy;
        CHECK(r.run(c)==expected && sleeps==1);
        if (change<2) {
            const unsigned qi=change==0 ? 1 : 0;
            CHECK(r.a.scalarOutput[0]==100 && registry.occupied()==1);
            if (change==1) CHECK(d.exactQueueGeneration[0]==12);
            packets(d,r,qi,100);
        } else {
            CHECK(registry.occupied()==0 && d.gSeq==99 && d.packets[0].empty() && d.packets[1].empty());
            CHECK(r.a.scalarOutput[0]==sentinel && c.lastSeq==0 && c.pendFenceSeq==0);
        }
    }
}
static void lifecycleAndCapacity() {
    reset(); Registry registry(6); PhxBringup d; d.expected=&registry; IOAccelPhxNativeClient c(&d,&registry);
    Ticket first;
    for (unsigned i=0;i<64;++i) {
        Request r(i&1); CHECK(r.run(c)==kIOReturnSuccess);
        if (!i) first=lookup(registry,r.a.scalarOutput[0]);
        d.setFence(i&1,d.gSeq); // Injected completion only; NOT real hardware evidence.
    }
    CHECK(registry.occupied()==64);
    const auto before=d.gSeq; Request full;
    CHECK(full.run(c)==kIOReturnNoResources && d.gSeq==before && full.a.scalarOutput[0]==sentinel);
    CHECK(registry.forget(first)==Status::Invalid); // No implicit completion or eviction.
    QueueObservation obs[2]={{11,d.gSeq,d.gSeq,true,false},{22,d.gSeq,d.gSeq,true,false}};
    CHECK(registry.observe(first,true,obs)==Status::Complete && registry.forget(first)==Status::Ok);
    Request next; CHECK(next.run(c)==kIOReturnSuccess && registry.occupied()==64);
    Ticket missing; CHECK(registry.lookup(100,missing)==Status::Unknown); // Never prefix fallback.
    const auto keep=lookup(registry,next.a.scalarOutput[0]);
    CHECK(registry.cancel(keep)==Status::Invalid && registry.forget(keep)==Status::Invalid);
    // Completion on GFX does not promote the safe global retirement past compute.
    reset(); Registry gap(7); PhxBringup two; two.expected=&gap; IOAccelPhxNativeClient cc(&two,&gap);
    Request compute(false), gfx(true); CHECK(compute.run(cc)==kIOReturnSuccess && gfx.run(cc)==kIOReturnSuccess);
    two.setFence(1,101); CHECK(two.gpuRetired()==99);
    QueueObservation done[2]={{11,100,99,true,false},{22,101,101,true,false}};
    CHECK(gap.observe(lookup(gap,101),true,done)==Status::Complete && two.gpuRetired()==99);
    const auto pending=lookup(gap,100);
    const uint64_t adopt[6]={0,1024,8192,0,8,9000};
    CHECK(two.adoptQueue(adopt)==kIOReturnSuccess && two.exactQueueGeneration[0]==12);
    done[0]={12,101,101,true,false};
    CHECK(gap.observe(pending,true,done)==Status::Lost && gap.forget(pending)==Status::Invalid);
    // Adoption epoch cannot wrap or silently reset a queue on exhaustion.
    two.exactQueueGeneration[0]=UINT64_MAX-1;
    const auto oldWptr=two.gq[0].wptr, oldDone=two.queueFence(two.gq[0]);
    CHECK(two.adoptQueue(adopt)==kIOReturnNoResources && two.gq[0].wptr==oldWptr && two.queueFence(two.gq[0])==oldDone);
}
static void interleavedClients() {
    reset(); Registry primary(10),other(11); PhxBringup d;
    IOAccelPhxNativeClient first(&d,&primary),second(&d,&other);
    second.clientLock=&otherClientToken;
    fill(d.gq[0]); d.setFence(0,0); d.expected=&primary;
    Request blocked(false),gfx(true);
    wake=[&] {
        CHECK(primary.occupied()==1 && other.occupied()==0 && !gpuHeld && clientHeld);
        Ticket unknown; CHECK(primary.lookup(100,unknown)==Status::Unknown);
        d.expected=&other;
        CHECK(gfx.run(second)==kIOReturnSuccess && gfx.a.scalarOutput[0]==100);
        packets(d,gfx,1,100);
        d.expected=&primary;
        d.setFence(0,1);
    };
    CHECK(blocked.run(first)==kIOReturnSuccess && blocked.a.scalarOutput[0]==101 && sleeps==1);
    packets(d,blocked,0,101);
    Ticket unknown;
    CHECK(primary.lookup(100,unknown)==Status::Unknown && other.lookup(101,unknown)==Status::Unknown);
    CHECK(primary.occupied()==1 && other.occupied()==1 && d.binds==2);
}
static void historyAndBoundary() {
    for (unsigned qi=0;qi<2;++qi) {
        reset(); Registry registry(8); PhxBringup d; d.expected=&registry; IOAccelPhxNativeClient c(&d,&registry);
        Ticket first;
        for (unsigned i=0;i<130;++i) {
            Request r(qi); CHECK(r.run(c)==kIOReturnSuccess);
            const auto t=lookup(registry,r.a.scalarOutput[0]);
            if (!i) first=t;
            d.setFence(qi,d.gSeq);
            QueueObservation obs[2]{}; obs[qi]={d.exactQueueGeneration[qi],d.gSeq,d.gSeq,true,false};
            if (i) CHECK(registry.observe(t,true,obs)==Status::Complete && registry.forget(t)==Status::Ok);
            CHECK(registry.observe(first,true,obs)==Status::Complete);
            CHECK(registry.occupied()==1); packets(d,r,qi,d.gSeq);
        }
        CHECK(d.gq[qi].tail==130 && d.gq[qi].fseq[0]!=100 && registry.lookup(100,first)==Status::Ok);
    }
    reset(); Registry registry(9); PhxBringup d; d.expected=&registry; IOAccelPhxNativeClient c(&d,&registry);
    d.gSeq=UINT64_MAX-2; Request last;
    CHECK(last.run(c)==kIOReturnSuccess && last.a.scalarOutput[0]==UINT64_MAX-1);
    Request overflow; CHECK(overflow.run(c)==kIOReturnNoResources && d.gSeq==UINT64_MAX-1 && registry.occupied()==1);
    // The null seam preserves the accepted no-GPU legacy mock behavior.
    reset(); PhxBringup legacy; legacy.gq[0].ready=legacy.gq[1].ready=false;
    IOAccelPhxNativeClient old(&legacy,nullptr); Request mock(false,1,true);
    CHECK(mock.run(old)==kIOReturnSuccess && mock.a.scalarOutput[0]==1 && old.fenceWords[1]==1 && old.lastSeq==0);
}
int main() {
    matrix(); admission(); retry(); lifecycleAndCapacity(); interleavedClients(); historyAndBoundary();
    CHECK(!gpuHeld && !clientHeld);
    std::printf("PASS actual staged native submit: %llu checks; %llu cases; CPU_only=true; GPU_executed=false\n",
        (unsigned long long)checks,(unsigned long long)cases);
}
