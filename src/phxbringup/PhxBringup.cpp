//
//  PhxBringup.cpp — Phoenix (Radeon 780M, 1002:1900) bring-up kext, step E1.
//
//  Publishes the service the RADV Darwin backend opens (class PhxBringup, user client type 'N48N')
//  and answers ABI v1 selectors 0..8 with the same rules as Mesa's in-process mock kext
//  (src/amd/common/darwin/ac_darwin_mock.c): buffers are kernel/user shared system memory,
//  GPU VA mappings are bookkeeping only, and Submit retires at once without touching the GPU.
//  Historical E1 description above: this downstream patch removes mock Submit/Wait success.
//
//  Boot-arg -phxbringupoff disables it. ReadRegs (MMIO read) is root-only; nothing else touches hardware.
//

#include <IOKit/IOService.h>
#include <IOKit/IOUserClient.h>
#include <IOKit/IOLib.h>
#include <IOKit/IOLocks.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <libkern/OSAtomic.h>
#include <pexpert/pexpert.h>
#include <sys/sysctl.h>

#include "PhxNativeABI.h"
#include "PhxPspLayout.h"
#include "PhxBootMemory.h"
static_assert(sizeof(PhxPspLayout) == 64, "PSP layout wire size");
static_assert(PHX_PSP_LAYOUT_RING_BYTES == PHX_PSP_FENCE_REL + 0x1000, "PSP layout ring span");
static_assert(PHX_PSP_GFX_RESP_OFFSET + PHX_PSP_TOC_SIZE_RESPONSE_REL + 4 <= PHX_PSP_CMD_BUF_SIZE,
              "TOC size response stays within command storage");
#include <libkern/version.h>
#include "PhxHardwarePolicy.hpp"
#include "PhxBoPolicy.hpp"

#define PHX_KEXT_BUILD 33u

// debug.phxbos_flush: how a client's BOs are made coherent around each submission and each completed wait.
// 2 = clflush every line (the bring-up way), 1 = clflushopt (the same lines, pipelined), 0 = none (the GPU maps system
// memory snooped, kPteSysFlags). With clflush, WindowServer spent ~73% of its CPU here and composited ~13 fps; with
// none, 41 fps and no artifacts (2026-10-20), hence the default.
static int gBosFlush = 0;
static volatile SInt64 gBosFlushBytes;
SYSCTL_INT(_debug, OID_AUTO, phxbos_flush, CTLFLAG_RW | CTLFLAG_LOCKED, &gBosFlush, 0,
           "BO cache maintenance per submit/wait: 0 none, 1 clflushopt, 2 clflush");
SYSCTL_QUAD(_debug, OID_AUTO, phxbos_flush_bytes, CTLFLAG_RD | CTLFLAG_LOCKED, (SInt64 *)&gBosFlushBytes,
            "bytes of BOs flushed from the CPU caches");
// The BO handle table is PHXN_MAX_BOS entries per client, and running out of it is the failure that made every
// texture allocation fail and the desktop flicker on a sibling port of this base (docs/RADEARC-REFERENCE.md §2).
// These two counters turn that cliff into evidence: how close a session got, and whether it hit it.
static volatile SInt64 gBosHandlesHigh;   // highest handle index handed out, any client
static volatile SInt64 gBosHandlesFull;   // BO creates refused because no handle was free
static volatile UInt32 gBosHandlesFullLogged;   // the log latch: the first refusal is the interesting one
SYSCTL_QUAD(_debug, OID_AUTO, phxbos_handles_high, CTLFLAG_RD | CTLFLAG_LOCKED, (SInt64 *)&gBosHandlesHigh,
            "highest BO handle index handed out by any client (the limit is PHXN_MAX_BOS)");
SYSCTL_QUAD(_debug, OID_AUTO, phxbos_handles_full, CTLFLAG_RD | CTLFLAG_LOCKED, (SInt64 *)&gBosHandlesFull,
            "BO creates refused because the per-client handle table was full");
static volatile UInt32 gSysctlUp;

// psp_gfx_rb_frame (64 B) — the ring entry the PSP reads. Only 5 fields are set; the rest stay zero
// (Linux amdgpu_psp.c:3485: a non-zero cmd_buf_size makes the PSP silently drop the frame).
struct PhxGfxRbFrame {
    uint32_t cmd_buf_addr_lo, cmd_buf_addr_hi, cmd_buf_size;
    uint32_t fence_addr_lo, fence_addr_hi, fence_value;
    uint32_t sid_lo, sid_hi;
    uint8_t vmid, frame_type, reserved1[2];
    uint32_t reserved2[7];
} __attribute__((packed));
static_assert(sizeof(PhxGfxRbFrame) == 64, "PhxGfxRbFrame must be 64 B");

// Compatibility profile from Mesa's canned phoenix table, NOT target-derived IP discovery.
// QueryInfo and registry properties label this assumption; PCI identity alone does not verify it.
static constexpr uint32_t kGbAddrConfig = 0x00000242;
static constexpr uint32_t kGcVersion = (11u << 16) | (0u << 8) | 1u;

// Per-client software budgets reported to RADV. Every allocated BO uses system memory.
// These values do not measure BAR0, the target's UMA carve-out or exclusive VRAM ownership.
static constexpr uint64_t kVisTotal = 256ull << 20;
static constexpr uint64_t kHiTotal = 1536ull << 20;
static constexpr uint64_t kGttCap = 512ull << 20;
static constexpr uint64_t kGttMaxBo = 256ull << 20;
static constexpr uint64_t kHostCap = 4096ull << 20, kHostMaxBo = 1024ull << 20;   // host imports, per client
static constexpr uint64_t kVaMask = (1ull << 48) - 1;
static constexpr int kMaxMaps = 4096;

static bool vaCanonical(uint64_t va) {
    uint64_t top = va >> 47;
    return top == 0 || top == 0x1FFFF;
}

// The allocated container owns the original descriptor references and host prepare calls.
// Closing transfers this whole container without allocating or unpinning anything.
struct PhxClientBo {
    IOMemoryDescriptor *md;
    uint64_t size;
    uint32_t domain, bits;
    uint8_t *kva;
    bool host, pendingFree;
};
struct PhxRetiredBuffers {
    PhxClientBo entries[PHXN_MAX_BOS];
    PhxRetiredBuffers *next;
};
static void phxReleaseBuffers(PhxRetiredBuffers *buffers) {
    if (!buffers) return;
    for (uint32_t h = 1; h < PHXN_MAX_BOS; ++h) {
        PhxClientBo &b = buffers->entries[h];
        if (!b.md) continue;
        if (b.host) b.md->complete();
        b.md->release();
        b = PhxClientBo{};
    }
    IOFree(buffers, sizeof(PhxRetiredBuffers));
}

class PhxBringup : public IOService {
    OSDeclareDefaultStructors(PhxBringup)
public:
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    IOReturn newUserClient(task_t owningTask, void *securityID, UInt32 type, IOUserClient **handler) override;

    bool claimSession();
    void releaseSession();
    IOReturn readRegs(uint32_t first, uint32_t count, uint32_t *out);
    IOReturn vramRead(uint32_t byteOff, uint32_t count, uint32_t *out);
    IOReturn writeReg(uint32_t reg, uint32_t value, uint32_t *readback);
    IOReturn vramWrite(uint32_t byteOff, uint32_t value);
    IOReturn doorbellWrite(uint64_t byteOff, uint64_t value);
    IOReturn sysMem(uint64_t op, uint64_t a, uint64_t b, uint64_t *out0, uint64_t *out1);
    IOReturn smuMessage(uint32_t msg, uint32_t arg, uint32_t *resp, uint32_t *argAfter);
    IOReturn pspRing(uint32_t op, uint64_t carveOffset, uint64_t out[4]);
    IOReturn configurePspLayout(const PhxPspLayout &layout, uint64_t out[4]);
    IOReturn bootMemory(PhxBootMemory *out);
    IOReturn pspSubmit(uint32_t cmdId, uint64_t out[4]);
    IOReturn fwStage(uint32_t dstOffset, const void *bytes, uint32_t len);
    IOReturn loadIpFw(uint32_t fwType, uint32_t fwBufOffset, uint32_t size, uint64_t out[4]);
    IOReturn loadToc(uint32_t fwBufOffset, uint32_t size, uint64_t out[4]);
    IOReturn pspCtl(uint32_t op, uint32_t arg, uint64_t out[4]);
    IOReturn pspRaw(uint32_t cmdId, const uint32_t words[6], uint64_t out[4]);
    bool debugEnabled() const { return debug; }
    // E8: GPU execution. The userspace bring-up maps MES queues (compute = 0, gfx = 1) and hands them over (adoptQueue);
    // user BOs are then mapped into the VMID 8 page table and SUBMIT writes INDIRECT_BUFFERs into the queue's ring.
    IOReturn adoptQueue(const uint64_t in[6]);
    IOReturn claimAccel();
    bool gpuReady() const { return !stopping && (gq[0].ready || gq[1].ready); }
    // one GPUVM context (VMID 8..15) per client process: RADV instances allocate VAs independently
    uint32_t vmidAlloc();
    void deferClient(uint32_t handle, uint64_t lastSeq, PhxRetiredBuffers *buffers);
    void reapContexts();
    IOReturn vmMap(uint32_t vmid, uint64_t va, IOMemoryDescriptor *md, uint64_t off, uint64_t size, bool *cleanupRequired);
    IOReturn vmCanReclaim(uint32_t handle);
    IOReturn vmUnmap(uint32_t vmid, uint64_t va, uint64_t size);
    IOReturn gpuSubmit(uint32_t vmid, bool gfx, const uint64_t *ibVa, const uint32_t *ibDw, uint32_t n, uint64_t *seq);
    uint64_t gpuRetired() const;

private:
    uint32_t rreg(uint32_t reg) const;
    void wreg(uint32_t reg, uint32_t value) const;
    uint32_t smuPoll() const;
    bool pspWaitTos(uint32_t timeoutMs) const;
    IOReturn pspRunCmd(uint32_t cmdId, const uint32_t *unionWords, uint32_t nWords, uint64_t out[4]);
    void hdpFlush() const;
    void readFbLayout();
    void clearRing();

    IOPCIDevice *pci{nullptr};
    IOMemoryMap *mmio{nullptr};
    IOLock *smuLock{nullptr};
    // UMA carve-out ("VRAM"): GPU MC address range and the system physical address behind it.
    uint64_t fbMcBase{0}, fbSize{0}, fbPhys{0};
    // BAR0 framebuffer aperture: the CPU window into the first fbAperLen bytes of VRAM. It is an MMIO
    // region above system RAM (phys 0x8_2040_0000 here, 256 MiB), so CPU writes through it reach the
    // GPU's local memory and never the macOS heap. This is how the PSP ring is initialised.
    IOMemoryMap *fbAper{nullptr};
    IOMemoryMap *doorbellMap{nullptr}; // BAR2: doorbell aperture (2 MiB)
    IOBufferMemoryDescriptor *sysBuf{nullptr}; // debug: physically contiguous system memory for GPU VM experiments
    uint64_t fbAperPhys{0}, fbAperLen{0};
    // MMIO dword to write 0 to for an HDP flush (0 if the NBIO remap register was implausible).
    uint32_t hdpFlushDword{0};
    // PSP KM ring (debug selector 101): MC address once created, else 0. The GPCOM command + fence buffers
    // (selector 103) live just above the ring in VRAM; offsets are VRAM byte offsets, Mc the matching MC address.
    uint64_t ringMc{0}, ringOff{0};
    uint64_t cmdOff{0}, cmdMc{0}, fenceOff{0}, fenceMc{0};
    uint32_t fenceCounter{0};
    bool pspSubmissionFaulted{false}; // sticky for this driver instance; no automatic recovery
    PhxPspLayout pspLayout{};
    bool pspLayoutConfigured{false};
    // Firmware bring-up regions (set when the ring is created): TMR the PSP copies firmware into, and fw_buf
    // where the CPU stages ucode for LOAD_IP_FW. Offsets are VRAM byte offsets, Mc the matching MC addresses.
    uint64_t tmrOff{0}, tmrMc{0}, tmrSize{0};
    uint64_t fwBufOff{0}, fwBufMc{0}, fwBufSize{0};
    bool tmrSetUp{false};
    uint32_t tocTmrSize{0};
    // E8 state: the adopted queues (ring/wb/fence are VRAM byte offsets reached through BAR0) and the VMID 8
    // page-table pool (physically contiguous system memory; page 0 is the root). Sequence numbers are global across
    // the queues; each queue's fence holds the last sequence it finished, and fseq/fend keep its outstanding
    // submissions in order (sequence, ring position after it).
    struct GpuQueue {
        bool ready, gfx;
        uint32_t ringOff, ringDw, wbOff, fenceOff;
        uint64_t dbByte, wptr, doneEnd, retiredSeq;
        uint64_t fseq[64], fend[64];
        volatile uint32_t head, tail;
    };
    GpuQueue gq[2]{};
    uint64_t gSeq{0};
    uint64_t queueFence(const GpuQueue &q) const;
    bool queueProgress(const GpuQueue &q, uint64_t *done) const;
    uint64_t gpuRetiredLocked() const;
    IOLock *gpuLock{nullptr};
    // One GPUVM context (page tables) per client, and the eight hardware VMIDs lent to contexts at submission time,
    // as amdgpu does: a fixed VMID per client capped Metal at eight processes, and with every app allowed Metal the
    // ninth got no device (2026-10-20). A context's handle is its index + 1.
    // A context's page tables, in physically contiguous 64 KiB chunks allocated as it maps (most contexts need one or
    // two): a single 4 MiB contiguous pool per context failed once memory was fragmented. Table i is page i % 16 of
    // chunk i / 16; table 0 is the root.
    static constexpr uint32_t kPtChunkBytes = 64u << 10, kPtChunkPages = kPtChunkBytes / 4096, kPtChunks = 64;
    struct VmCtx {
        IOBufferMemoryDescriptor *chunk[kPtChunks];
        uint64_t chunkPhys[kPtChunks];
        uint64_t phys;                    // the root table
        uint32_t pages, used;
        bool busy, closing;
        uint64_t lastSeq, retireSeq;
        PhxRetiredBuffers *retiredBuffers;
        uint32_t hw;                      // the hardware VMID pointed at these tables, 0 = none
    };
    static constexpr uint32_t kMaxCtx = 96;
    VmCtx vm[kMaxCtx]{};
    struct HwVmid {
        uint32_t ctx;                     // handle of the context it points at, 0 = free
        uint64_t lastSeq, lastUse;        // its newest submission; when it was last bound or used
        bool faulted;                    // hardware binding uncertain; do not reuse or reclaim through it
    };
    HwVmid hwv[8]{};
    uint64_t hwTick{0};
    bool stopping{false}, stopQuarantined{false};
    PhxRetiredBuffers *volatile quarantinedBuffers{nullptr};
    void reapContextsLocked();
    uint32_t vmBind(uint32_t handle);
    VmCtx *vmCtx(uint32_t handle) { return !stopping && handle && handle <= kMaxCtx && vm[handle - 1].busy && !vm[handle - 1].closing ? &vm[handle - 1] : nullptr; }
    bool ptClear(VmCtx &c) const;
    uint64_t *ptTable(const VmCtx &c, uint64_t phys) const;
    uint64_t ptTablePhys(VmCtx &c, uint32_t i);
    uint64_t *vmPte(VmCtx &c, uint64_t va, bool alloc, IOReturn *status = nullptr);
    bool vmFlushTlb(uint32_t vmid) const;
    bool vmBindingValid(uint32_t vmid, uint64_t physical) const;
    bool vmOwnershipKnown(uint32_t repairing) const;
    IOReturn vmIdleLocked(uint32_t handle, bool repair);
    void ringPut(GpuQueue &q, uint32_t idx, uint32_t value);
    bool debug{false};
    bool smuUsed{false};
    volatile SInt32 sessionOpen{0};
};

OSDefineMetaClassAndStructors(PhxBringup, IOService)

class IOAccelPhxNativeClient : public IOUserClient {
    OSDeclareDefaultStructors(IOAccelPhxNativeClient)
public:
    bool initWithTask(task_t owningTask, void *securityID, UInt32 type) override;
    bool start(IOService *provider) override;
    IOReturn clientClose() override;
    void free() override;
    IOReturn externalMethod(uint32_t selector, IOExternalMethodArguments *args, IOExternalMethodDispatch *dispatch,
                            OSObject *target, void *reference) override;
    IOReturn clientMemoryForType(UInt32 type, IOOptionBits *options, IOMemoryDescriptor **memory) override;

private:
    using Bo = PhxClientBo;
    struct Map {
        bool used;
        uint32_t handle;
        uint64_t va, size, off;
        uint32_t flags;
        bool pending;
    };

    IOReturn doHello(IOExternalMethodArguments *a);
    IOReturn doQueryInfo(IOExternalMethodArguments *a);
    IOReturn doReadRegs(IOExternalMethodArguments *a);
    IOReturn doBoCreate(IOExternalMethodArguments *a);
    IOReturn doBoFree(IOExternalMethodArguments *a);
    IOReturn doBoImportHost(IOExternalMethodArguments *a);
    void boRelease(Bo &b);
    IOReturn doGemVa(IOExternalMethodArguments *a);
    IOReturn doCtx(IOExternalMethodArguments *a);
    IOReturn doSubmit(IOExternalMethodArguments *a);
    IOReturn doWaitSeq(IOExternalMethodArguments *a);
    IOReturn doDbgSmu(IOExternalMethodArguments *a);
    IOReturn doDbgPspRing(IOExternalMethodArguments *a);
    IOReturn doDbgPspLayout(IOExternalMethodArguments *a);
    IOReturn doDbgBootMemory(IOExternalMethodArguments *a);
    IOReturn doDbgLoadToc(IOExternalMethodArguments *a);
    IOReturn doDbgVramRead(IOExternalMethodArguments *a);
    IOReturn doDbgPspSubmit(IOExternalMethodArguments *a);
    IOReturn doDbgFwStage(IOExternalMethodArguments *a);
    IOReturn doDbgLoadIpFw(IOExternalMethodArguments *a);
    IOReturn doDbgPspCtl(IOExternalMethodArguments *a);
    IOReturn doDbgPspRaw(IOExternalMethodArguments *a);
    IOReturn doDbgWriteReg(IOExternalMethodArguments *a);
    IOReturn doDbgVramWrite(IOExternalMethodArguments *a);
    IOReturn doDbgDoorbell(IOExternalMethodArguments *a);
    IOReturn doDbgSysMem(IOExternalMethodArguments *a);
    IOReturn doDbgAdoptQueue(IOExternalMethodArguments *a);
    IOReturn doDbgClaim(IOExternalMethodArguments *a);
    void flushBos();
    Bo *findBo(uint32_t h);
    bool ibCovered(uint64_t vaCanon, uint64_t bytes);
    void freeAll();
    void closeResources();
    void reapPending();
    bool hasPending() const;

    PhxBringup *owner{nullptr};
    IOLock *lock{nullptr};
    bool privileged{false};
    bool hello{false}, closed{false};
    bool sessionClaimed{false};
    uint32_t vmid{0};        // this client's GPUVM context, taken on its first GPU mapping or submission
    uint64_t lastSeq{0};     // its newest submission: the context is released only once the GPU is past it
    bool ensureVmid() { return vmid || (vmid = owner->vmidAlloc()) != 0; }
    PhxRetiredBuffers *bufferStorage{nullptr};
    Bo *bos{nullptr};      // aliases bufferStorage->entries until ownership transfer
    Map *maps{nullptr};    // kMaxMaps entries
    bool ctx[PHXN_MAX_CTX + 1]{};
    uint64_t visUsed{0}, hiUsed{0}, gttUsed{0}, hostUsed{0};
    task_t task{nullptr};
    uint64_t emitted{0};
    uint32_t pendFenceHandle{0}, pendFenceOffset{0};
    uint64_t pendFenceSeq{0};
};

OSDefineMetaClassAndStructors(IOAccelPhxNativeClient, IOUserClient)

// ---- service ---------------------------------------------------------------------------------------------

bool PhxBringup::start(IOService *provider) {
    int dummy = 0;
    if (PE_parse_boot_argn("-phxbringupoff", &dummy, sizeof(dummy)))
        return false;
    int optIn = 0;
    const bool optedIn = PE_parse_boot_argn("phx780m", &optIn, sizeof(optIn)) && optIn == 1;
    IOPCIDevice *candidate = OSDynamicCast(IOPCIDevice, provider);
    if (!candidate || !phx780m::allowDevice(version_major,
            candidate->configRead16(kIOPCIConfigVendorID),
            candidate->configRead16(kIOPCIConfigDeviceID), optedIn)) {
        IOLog("PhxBringup: 780M research gate declined (requires Darwin 25, 1002:1900, phx780m=1)\n");
        return false;
    }
    if (!IOService::start(provider))
        return false;
    pci = OSDynamicCast(IOPCIDevice, provider);
    if (!pci)
        return false;
    pci->retain();
    {   // the GPU must be a bus master before it can DMA to/from system memory (page tables, user BOs)
        uint16_t cmd = pci->configRead16(kIOPCIConfigCommand);
        setProperty("phx-pci-cmd-before", cmd, 16);
        pci->setBusMasterEnable(true);
        pci->setMemoryEnable(true);
        setProperty("phx-pci-cmd-after", pci->configRead16(kIOPCIConfigCommand), 16);
    }
    mmio = pci->mapDeviceMemoryWithRegister(kIOPCIConfigBaseAddress5);
    fbAper = pci->mapDeviceMemoryWithRegister(kIOPCIConfigBaseAddress0);
    if (fbAper) {
        fbAperLen = fbAper->getLength();
        fbAperPhys = fbAper->getPhysicalAddress();
    }
    doorbellMap = pci->mapDeviceMemoryWithRegister(kIOPCIConfigBaseAddress2);
    smuLock = IOLockAlloc();
    gpuLock = IOLockAlloc();
    uint32_t dbg = 0;
    debug = PE_parse_boot_argn("phxdebug", &dbg, sizeof(dbg)) && dbg == 1;
    if (mmio) {
        readFbLayout();
        // HDP flush window: the NBIO remap register holds the BAR5 byte offset where writing 0 flushes the
        // host data path. Accept it only if it is a plausible dword offset inside our MMIO aperture.
        uint32_t remap = rreg(PHX_NBIO_REMAP_HDP_MEM_FLUSH_CNTL);
        if (remap && remap != 0xFFFFFFFFu && (remap & 3) == 0 && remap + 4 <= mmio->getLength())
            hdpFlushDword = remap >> 2;
        setProperty("phx-hdp-flush-dword", hdpFlushDword, 32);
    }
    setProperty("phx-780m-policy", "strict-execution-v1");
    setProperty("phx-build", PHX_KEXT_BUILD, 32);
    setProperty("phx-stage", "E3");
    setProperty("phx-hw-profile", "phoenix-canned-unverified");
    setProperty("phx-memory-model", "system-backed-software-budgets");
    setProperty("phx-debug", debug);
    setProperty("phx-fb-aper-phys", fbAperPhys, 64);
    setProperty("phx-fb-aper-len", fbAperLen, 64);
    IOLog("PhxBringup: service up (mmio %s, bar0 %s %llu MiB, debug %d)\n", mmio ? "mapped" : "unmapped",
          fbAper ? "mapped" : "unmapped", (unsigned long long)(fbAperLen >> 20), debug);
    registerService();
    return true;
}

void PhxBringup::stop(IOService *provider) {
    if (gpuLock) IOLockLock(gpuLock);
    stopping = true;
    if (gpuLock) reapContextsLocked();
    bool retained = quarantinedBuffers || gq[0].ready || gq[1].ready || ringMc || tmrSetUp;
    for (const VmCtx &c : vm) retained = retained || c.busy;
    for (const HwVmid &h : hwv) retained = retained || h.ctx || h.faulted;
    if (retained) {
        // Lost synchronization or orphaned slot state cannot prove device-wide quiescence.
        if (!stopQuarantined) { retain(); stopQuarantined = true; }
        if (gpuLock) IOLockUnlock(gpuLock);
        IOLog("PhxBringup: stop quarantined active hardware/resources; reclaim requires verified quiescence\n");
        IOService::stop(provider);
        return;
    }
    if (gpuLock) IOLockUnlock(gpuLock);
    if (gSysctlUp) {
        sysctl_unregister_oid(&sysctl__debug_phxbos_flush);
        sysctl_unregister_oid(&sysctl__debug_phxbos_flush_bytes);
        sysctl_unregister_oid(&sysctl__debug_phxbos_handles_high);
        sysctl_unregister_oid(&sysctl__debug_phxbos_handles_full);
        gSysctlUp = 0;
    }
    clearRing();
    if (fbAper) {
        fbAper->release();
        fbAper = nullptr;
    }
    if (sysBuf) {
        sysBuf->release();
        sysBuf = nullptr;
    }
    gq[0].ready = gq[1].ready = false;
    for (VmCtx &c : vm) {
        for (IOBufferMemoryDescriptor *b : c.chunk)
            if (b)
                b->release();
        c = VmCtx{};
    }
    for (HwVmid &h : hwv)
        h = HwVmid{};
    if (gpuLock) {
        IOLockFree(gpuLock);
        gpuLock = nullptr;
    }
    if (doorbellMap) {
        doorbellMap->release();
        doorbellMap = nullptr;
    }
    if (mmio) {
        mmio->release();
        mmio = nullptr;
    }
    if (pci) {
        pci->release();
        pci = nullptr;
    }
    if (smuLock) {
        IOLockFree(smuLock);
        smuLock = nullptr;
    }
    IOService::stop(provider);
}

uint32_t PhxBringup::rreg(uint32_t reg) const {
    return reinterpret_cast<volatile uint32_t *>(mmio->getVirtualAddress())[reg];
}

void PhxBringup::wreg(uint32_t reg, uint32_t value) const {
    reinterpret_cast<volatile uint32_t *>(mmio->getVirtualAddress())[reg] = value;
}

// FB location (MC, 16 MiB units, FB_BASE bits 23:0) and the system physical address of the carve-out (FB_OFFSET << 24).
void PhxBringup::readFbLayout() {
    uint32_t base = rreg(PHX_MMMC_VM_FB_LOCATION_BASE) & 0x00FFFFFF;
    uint32_t top = rreg(PHX_MMMC_VM_FB_LOCATION_TOP) & 0x00FFFFFF;
    fbMcBase = static_cast<uint64_t>(base) << 24;
    fbSize = top >= base ? (static_cast<uint64_t>(top - base) + 1) << 24 : 0;
    fbPhys = static_cast<uint64_t>(rreg(PHX_MMMC_VM_FB_OFFSET)) << 24;
    setProperty("phx-fb-mc-base", fbMcBase, 64);
    setProperty("phx-fb-size", fbSize, 64);
    setProperty("phx-fb-phys", fbPhys, 64);
    // About This Mac / System Information name the GPU from the PCI device's "model" and size its memory from
    // "VRAM,totalMB"; without them the 780M read "Display, 15 MB" (the boot framebuffer)
    static const char kModel[] = "AMD Radeon 780M";
    if (OSData *m = OSData::withBytes(kModel, sizeof(kModel))) {
        pci->setProperty("model", m);
        m->release();
    }
    if (fbSize)
        pci->setProperty("VRAM,totalMB", fbSize >> 20, 32);
}

void PhxBringup::clearRing() {
    tocTmrSize = 0;
    ringMc = ringOff = 0;
    cmdOff = cmdMc = fenceOff = fenceMc = 0;
    fenceCounter = 0;
    tmrOff = tmrMc = tmrSize = 0;
    fwBufOff = fwBufMc = fwBufSize = 0;
    tmrSetUp = false;
}

// Drain the host data path so the PSP sees our VRAM writes before we ring the doorbell (C2PMSG_67).
void PhxBringup::hdpFlush() const {
    if (hdpFlushDword)
        wreg(hdpFlushDword, 0);
    (void)rreg(0x0DE3);   // read-back barrier (GRBM_STATUS), as in the reference
}

// Read-only: count dwords from VRAM at byteOff, through the BAR0 aperture. Used by debug selector 102 to
// find the live console framebuffer and a free (all-zero) VRAM region for the PSP structures.
IOReturn PhxBringup::vramRead(uint32_t byteOff, uint32_t count, uint32_t *out) {
    if (!fbAper)
        return kIOReturnNotReady;
    if ((byteOff & 3) || (static_cast<uint64_t>(byteOff) + static_cast<uint64_t>(count) * 4) > fbAperLen)
        return kIOReturnBadArgument;
    volatile uint32_t *v = reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + byteOff);
    for (uint32_t i = 0; i < count; i++)
        out[i] = v[i];
    return kIOReturnSuccess;
}

// Write one MMIO dword (bring-up experimentation; root + phxdebug only). Returns the readback.
IOReturn PhxBringup::writeReg(uint32_t reg, uint32_t value, uint32_t *readback) {
    if (!mmio)
        return kIOReturnNotReady;
    if ((static_cast<uint64_t>(reg) + 1) * 4 > mmio->getLength())
        return kIOReturnBadArgument;
    wreg(reg, value);
    __asm__ __volatile__("mfence" ::: "memory");
    *readback = rreg(reg);
    return kIOReturnSuccess;
}

// Write one dword into VRAM at byteOff through the BAR0 aperture.
// op 1: allocate a physically contiguous buffer of a bytes (replaces any previous), out0 = physical address
// op 2: read dword at byte offset a -> out1;  op 3: write dword b at byte offset a;  op 4: free
IOReturn PhxBringup::sysMem(uint64_t op, uint64_t a, uint64_t b, uint64_t *out0, uint64_t *out1) {
    *out0 = *out1 = 0;
    if (op == 1) {
        if (sysBuf) {
            sysBuf->release();
            sysBuf = nullptr;
        }
        if (a == 0 || a > (64ull << 20))
            return kIOReturnBadArgument;
        sysBuf = IOBufferMemoryDescriptor::inTaskWithPhysicalMask(
            kernel_task, kIODirectionInOut | kIOMemoryPhysicallyContiguous, a, 0x00007FFFFFFFF000ull);
        if (!sysBuf)
            return kIOReturnNoMemory;
        bzero(sysBuf->getBytesNoCopy(), a);
        *out0 = sysBuf->getPhysicalAddress();
        *out1 = sysBuf->getLength();
        return kIOReturnSuccess;
    }
    if (!sysBuf)
        return kIOReturnNotReady;
    if (op == 4) {
        sysBuf->release();
        sysBuf = nullptr;
        return kIOReturnSuccess;
    }
    if ((a & 3) || a + 4 > sysBuf->getLength())
        return kIOReturnBadArgument;
    volatile uint32_t *p = reinterpret_cast<volatile uint32_t *>(static_cast<uint8_t *>(sysBuf->getBytesNoCopy()) + a);
    if (op == 2) {
        __asm__ __volatile__("clflush (%0)\n\tmfence" ::"r"(p) : "memory");
        *out1 = *p;
        *out0 = sysBuf->getPhysicalAddress();
        return kIOReturnSuccess;
    }
    if (op == 3) {
        *p = static_cast<uint32_t>(b);
        __asm__ __volatile__("clflush (%0)\n\tmfence" ::"r"(p) : "memory"); // GPU walker may not snoop CPU caches
        return kIOReturnSuccess;
    }
    return kIOReturnBadArgument;
}

// ---- E8: GPU execution ------------------------------------------------------------------------------------
// Everything here reproduces what tools/phxctl/mesboot.c proved on the 780M: VMID 8 with a 4-level table in
// system memory (PDE = next|VALID|SYSTEM|SNOOPED, no BFS/TF since gmc_v11 has translate_further off), system-page
// PTEs with MTYPE 4, invalidation on engine 17, and an ACQUIRE/RELEASE_MEM GL2 writeback after each IB.
static constexpr uint32_t kFirstUserVmid = 8, kNumUserVmids = 8;   // VMIDs 8..15, lent to client contexts (vmBind)
static constexpr uint64_t kPteSysFlags = 0x77ull | (4ull << 48);  // VALID SYSTEM SNOOPED EXEC READ WRITE, MTYPE 4
static constexpr uint64_t kPtAddrMask = 0x0000FFFFFFFFF000ull;
// GC registers (absolute dword index, GC base 0x1260): context n = context 0 + n (CNTL) / + 2n (address pairs),
// invalidation engine 17
static constexpr uint32_t kRegCtx0Cntl = 0x28E8, kRegCtx0BaseLo = 0x2953, kRegCtx0StartLo = 0x2973, kRegCtx0EndLo = 0x2993;
static constexpr uint32_t kRegInvEng17Req = 0x291C, kRegInvEng17Ack = 0x292E;

static inline void flushLine(const volatile void *p) {
    __asm__ __volatile__("clflush (%0)" ::"r"(p) : "memory");
}

// Validate the entire descriptor before returning CPU or physical page-table storage.
static bool phxPtBacking(IOBufferMemoryDescriptor *b, uint32_t size, uint64_t *physical, uint8_t **cpu) {
    if (!physical || !cpu) return false;
    *physical = 0;
    *cpu = nullptr;
    if (!b || !size || (size & 4095) || b->getLength() != size) return false;
    uint8_t *p = static_cast<uint8_t *>(b->getBytesNoCopy());
    const uintptr_t address = reinterpret_cast<uintptr_t>(p);
    if (!p || (address & 4095) || address > UINTPTR_MAX - (size - 1)) return false;
    IOByteCount length = 0;
    const addr64_t pa = b->getPhysicalSegment(0, &length, kIOMemoryMapperNone);
    if (!pa || (pa & ~kPtAddrMask) || length < size ||
        static_cast<uint64_t>(size - 4096) > kPtAddrMask - pa) return false;
    *physical = pa;
    *cpu = p;
    return true;
}

// Preflight every cached chunk before clearing any used page; do not re-fetch CPU pointers during mutation.
bool PhxBringup::ptClear(VmCtx &c) const {
    if (!c.phys || c.phys != c.chunkPhys[0] || !c.used || c.used > c.pages ||
        c.pages > kPtChunks * kPtChunkPages) return false;
    uint8_t *cpu[kPtChunks]{};
    uint64_t physical[kPtChunks]{};
    bool hole = false;
    for (uint32_t k = 0; k < kPtChunks; ++k) {
        if (!c.chunk[k]) {
            if (c.chunkPhys[k] || k * kPtChunkPages < c.used) return false;
            hole = true;
            continue;
        }
        if (hole || !phxPtBacking(c.chunk[k], kPtChunkBytes, &physical[k], &cpu[k]) ||
            physical[k] != c.chunkPhys[k]) return false;
        for (uint32_t j = 0; j < k; ++j) {
            const uintptr_t a = reinterpret_cast<uintptr_t>(cpu[k]), b = reinterpret_cast<uintptr_t>(cpu[j]);
            if ((physical[k] >= physical[j] ? physical[k] - physical[j] : physical[j] - physical[k]) < kPtChunkBytes ||
                (a >= b ? a - b : b - a) < kPtChunkBytes) return false;
        }
    }
    const uint32_t chunks = (c.used + kPtChunkPages - 1) / kPtChunkPages;
    for (uint32_t k = 0; k < chunks; ++k) {
        const uint32_t left = c.used - k * kPtChunkPages;
        const uint32_t n = left < kPtChunkPages ? left : kPtChunkPages;
        bzero(cpu[k], static_cast<size_t>(n) * 4096);
        for (uint32_t o = 0; o < n * 4096u; o += 64) flushLine(cpu[k] + o);
    }
    return true;
}

uint64_t *PhxBringup::ptTable(const VmCtx &c, uint64_t phys) const {
    if (!phys || (phys & ~kPtAddrMask) || !c.used || c.used > c.pages ||
        c.pages > kPtChunks * kPtChunkPages) return nullptr;
    uint64_t *result = nullptr;
    for (uint32_t k = 0; k * kPtChunkPages < c.used; ++k) {
        uint64_t base = 0;
        uint8_t *p = nullptr;
        if (!phxPtBacking(c.chunk[k], kPtChunkBytes, &base, &p) || base != c.chunkPhys[k]) return nullptr;
        if (phys < base || phys - base > kPtChunkBytes - 4096) continue;
        if (result || k * kPtChunkPages + (phys - base) / 4096 >= c.used) return nullptr;
        result = reinterpret_cast<uint64_t *>(p + (phys - base));
    }
    return result;
}

// Allocate only the next table (or retrieve an existing one); publish only validated, zeroed storage.
uint64_t PhxBringup::ptTablePhys(VmCtx &c, uint32_t i) {
    if (c.pages > kPtChunks * kPtChunkPages || c.used > c.pages || i > c.used ||
        i >= kPtChunks * kPtChunkPages || (c.pages && i >= c.pages) ||
        (!c.pages && (c.used || c.phys || i)) ||
        (c.pages && (!c.chunk[0] || !c.phys || c.phys != c.chunkPhys[0]))) return 0;
    const uint32_t k = i / kPtChunkPages;
    for (uint32_t j = 0; j < k; ++j) if (!c.chunk[j]) return 0;
    if (!c.chunk[k] && c.chunkPhys[k]) return 0;
    IOBufferMemoryDescriptor *b = c.chunk[k];
    const bool fresh = !b;
    if (fresh) b = IOBufferMemoryDescriptor::inTaskWithPhysicalMask(
        kernel_task, kIODirectionInOut | kIOMemoryPhysicallyContiguous, kPtChunkBytes, kPtAddrMask);
    if (!b) return 0;
    uint64_t base = 0;
    uint8_t *p = nullptr;
    bool valid = phxPtBacking(b, kPtChunkBytes, &base, &p) && (fresh || base == c.chunkPhys[k]);
    bool hole = false;
    for (uint32_t j = 0; valid && j < kPtChunks; ++j) {
        IOBufferMemoryDescriptor *other = j == k ? b : c.chunk[j];
        if (!other) {
            if (c.chunkPhys[j]) valid = false;
            hole = true;
            continue;
        }
        if (hole) { valid = false; break; }
        if (j == k) continue;
        uint64_t otherBase = 0;
        uint8_t *otherCpu = nullptr;
        valid = phxPtBacking(other, kPtChunkBytes, &otherBase, &otherCpu) && otherBase == c.chunkPhys[j];
        if (!valid) break;
        const uintptr_t a = reinterpret_cast<uintptr_t>(p), o = reinterpret_cast<uintptr_t>(otherCpu);
        if ((base >= otherBase ? base - otherBase : otherBase - base) < kPtChunkBytes ||
            (a >= o ? a - o : o - a) < kPtChunkBytes) valid = false;
    }
    if (!valid) {
        if (fresh) b->release();
        return 0;
    }
    if (fresh) {
        bzero(p, kPtChunkBytes);
        for (uint32_t o = 0; o < kPtChunkBytes; o += 64) flushLine(p + o);
        c.chunkPhys[k] = base;
        c.chunk[k] = b;
    }
    return base + static_cast<uint64_t>(i % kPtChunkPages) * 4096;
}

// Null + Success is an absent branch; malformed storage/entries are VMError, allocation failure is NoMemory.
uint64_t *PhxBringup::vmPte(VmCtx &c, uint64_t va, bool alloc, IOReturn *status) {
    if (status) *status = kIOReturnVMError;
    if ((va >> 48) || !c.phys || c.phys != c.chunkPhys[0]) return nullptr;
    uint64_t ancestors[4] = {c.phys, 0, 0, 0};
    uint64_t tbl = c.phys;
    unsigned level = 0;
    for (int shift = 39; shift >= 21; shift -= 9, ++level) {
        uint64_t *t = ptTable(c, tbl);
        if (!t) return nullptr;
        uint64_t *e = t + ((va >> shift) & 511);
        uint64_t entry = *e;
        if (!entry) {
            if (!alloc) { if (status) *status = kIOReturnSuccess; return nullptr; }
            if (c.used >= c.pages) { if (status) *status = kIOReturnNoMemory; return nullptr; }
            const uint64_t child = ptTablePhys(c, c.used);
            if (!child) { if (status) *status = kIOReturnNoMemory; return nullptr; }
            ++c.used;
            entry = child | 7;
            *e = entry;
            flushLine(e);
        }
        // These owned non-leaf tables use exactly VALID|SYSTEM|SNOOPED, never leaf/large-page flags.
        if ((entry & ~kPtAddrMask) != 7) return nullptr;
        tbl = entry & kPtAddrMask;
        for (unsigned a = 0; a <= level; ++a) if (tbl == ancestors[a]) return nullptr;
        ancestors[level + 1] = tbl;
    }
    uint64_t *t = ptTable(c, tbl);
    if (t && status) *status = kIOReturnSuccess;
    return t ? t + ((va >> 12) & 511) : nullptr;
}

bool PhxBringup::vmFlushTlb(uint32_t vmid) const {
    if (!mmio || vmid < kFirstUserVmid || vmid >= kFirstUserVmid + kNumUserVmids)
        return false;
    const uint32_t mask = 1u << vmid;
    __asm__ __volatile__("mfence" ::: "memory");
    // GFXHUB legacy invalidation: flush only this user VMID, not VMID 0 as well.
    wreg(kRegInvEng17Req, 0x00F80000u | mask);
    for (unsigned sample = 0; sample < 1000; ++sample) {
        const uint32_t ack = rreg(kRegInvEng17Ack);
        if (ack == UINT32_MAX) return false;
        if (ack & mask) return true;
        if (sample + 1 < 1000) IODelay(1);
    }
    return false;
}

bool PhxBringup::vmBindingValid(uint32_t vmid, uint64_t physical) const {
    if (!mmio || vmid < kFirstUserVmid || vmid >= kFirstUserVmid + kNumUserVmids ||
        !physical || (physical & ~kPtAddrMask))
        return false;
    const uint32_t regs[] = {kRegCtx0BaseLo + 2 * vmid, kRegCtx0BaseLo + 2 * vmid + 1,
        kRegCtx0Cntl + vmid, kRegCtx0StartLo + 2 * vmid, kRegCtx0StartLo + 2 * vmid + 1,
        kRegCtx0EndLo + 2 * vmid, kRegCtx0EndLo + 2 * vmid + 1};
    const uint32_t values[] = {static_cast<uint32_t>(physical | 3), static_cast<uint32_t>(physical >> 32),
        0x01fffe07, 0, 0, 0xffffffff, 0xf};
    for (unsigned i = 0; i < 7; ++i)
        if (rreg(regs[i]) != values[i]) return false;
    return true;
}

// Takes a free context: empty tables (root only), no hardware VMID until its first submission. Returns its handle,
// 0 when all kMaxCtx are in use.
uint32_t PhxBringup::vmidAlloc() {
    if (!gpuReady())
        return 0;
    IOLockLock(gpuLock);
    if (!gpuReady()) { IOLockUnlock(gpuLock); return 0; }
    reapContextsLocked();
    for (uint32_t i = 0; i < kMaxCtx; i++) {
        VmCtx &c = vm[i];
        if (c.busy)
            continue;
        const uint64_t root = ptTablePhys(c, 0);
        if (!root) continue;
        c.phys = root;
        c.pages = kPtChunks * kPtChunkPages;
        c.used = 1;
        c.busy = true;
        c.closing = false;
        c.lastSeq = c.retireSeq = 0;
        c.retiredBuffers = nullptr;
        c.hw = 0;
        IOLockUnlock(gpuLock);
        return i + 1;
    }
    IOLockUnlock(gpuLock);
    return 0;
}

// Points a hardware VMID at the context's tables for a submission (gpuLock held): the one it already has, a free one,
// or the least recently used one whose submissions the GPU has all finished (waits for one, bounded ~2 s). 0 on timeout.
uint32_t PhxBringup::vmBind(uint32_t handle) {
    VmCtx *context = vmCtx(handle);
    if (!context || !mmio || !context->phys || (context->phys & ~kPtAddrMask) || hwTick == UINT64_MAX)
        return 0;
    VmCtx &c = *context;
    const uint64_t now = ++hwTick;
    if (c.hw) {
        if (c.hw < kFirstUserVmid || c.hw >= kFirstUserVmid + kNumUserVmids ||
            hwv[c.hw - kFirstUserVmid].ctx != handle)
            return 0;
        // Recheck cached assignments too: a prior invalidation may have failed.
        HwVmid &h = hwv[c.hw - kFirstUserVmid];
        h.faulted = !vmBindingValid(c.hw, c.phys) || !vmFlushTlb(c.hw);
        if (h.faulted) return 0;
        h.lastUse = now;
        return c.hw;
    }
    int pick = -1;
    for (int spin = 0; pick < 0; spin++) {
        const uint64_t done = gpuRetiredLocked();
        uint64_t oldest = ~0ull;
        for (uint32_t i = 0; i < kNumUserVmids; i++) {
            if (hwv[i].faulted) continue;
            if (hwv[i].ctx && (hwv[i].ctx > kMaxCtx || !vm[hwv[i].ctx - 1].busy ||
                              vm[hwv[i].ctx - 1].hw != kFirstUserVmid + i))
                return 0;
            if (!hwv[i].ctx) {
                pick = static_cast<int>(i);
                break;
            }
            if (hwv[i].lastSeq <= done && hwv[i].lastUse < oldest) {
                oldest = hwv[i].lastUse;
                pick = static_cast<int>(i);
            }
        }
        if (pick >= 0)
            break;
        if (spin > 40000)
            return 0;
        IODelay(50);
    }
    HwVmid &h = hwv[pick];
    if (h.ctx)
        vm[h.ctx - 1].hw = 0;
    h.ctx = handle;
    h.lastSeq = 0;
    h.lastUse = now;
    const uint32_t vmid = kFirstUserVmid + static_cast<uint32_t>(pick);
    c.hw = vmid;
    wreg(kRegCtx0BaseLo + 2 * vmid, static_cast<uint32_t>(c.phys | 3));
    wreg(kRegCtx0BaseLo + 2 * vmid + 1, static_cast<uint32_t>(c.phys >> 32));
    wreg(kRegCtx0Cntl + vmid, 0x01fffe07);
    wreg(kRegCtx0StartLo + 2 * vmid, 0);
    wreg(kRegCtx0StartLo + 2 * vmid + 1, 0);
    wreg(kRegCtx0EndLo + 2 * vmid, 0xffffffff);
    wreg(kRegCtx0EndLo + 2 * vmid + 1, 0xf);
    // Keep the software reservation on failure, but never return a submission-ready VMID.
    // A later call must revalidate these registers and obtain its own invalidation ACK.
    h.faulted = !vmBindingValid(vmid, c.phys) || !vmFlushTlb(vmid);
    if (h.faulted) return 0;
    return vmid;
}

// Transfer the client's original descriptor ownership; never allocate on the close path.
void PhxBringup::deferClient(uint32_t handle, uint64_t lastSeq, PhxRetiredBuffers *buffers) {
    if (gpuLock) IOLockLock(gpuLock);
    VmCtx *c = handle && handle <= kMaxCtx ? &vm[handle - 1] : nullptr;
    if (!gpuLock || !c || !c->busy || c->closing || lastSeq > gSeq) {
        // Inconsistent ownership cannot justify release. Keep an explicit, unreclaimed ledger.
        if (buffers) {
            PhxRetiredBuffers *head;
            do { head = quarantinedBuffers; buffers->next = head; }
            while (!OSCompareAndSwapPtr(head, buffers, reinterpret_cast<void *volatile *>(&quarantinedBuffers)));
        }
    } else {
        c->closing = true;
        c->retireSeq = lastSeq > c->lastSeq ? lastSeq : c->lastSeq;
        c->retiredBuffers = buffers;
        reapContextsLocked();
    }
    if (gpuLock) IOLockUnlock(gpuLock);
}

void PhxBringup::reapContexts() {
    if (!gpuLock) return;
    IOLockLock(gpuLock);
    reapContextsLocked();
    IOLockUnlock(gpuLock);
}

// gpuLock held. Closing contexts cannot accept new work. Never infer completion from lost hardware.
void PhxBringup::reapContextsLocked() {
    if (quarantinedBuffers) return;
    const bool observable = fbAper && mmio && (gq[0].ready || gq[1].ready);
    const uint64_t done = observable ? gpuRetiredLocked() : 0;
    for (uint32_t i = 0; i < kMaxCtx; ++i) {
        VmCtx &c = vm[i];
        if (!c.busy || !c.closing || c.retireSeq > done || (c.retireSeq && !observable) || !c.hw)
            continue;
        if (!mmio || c.hw < kFirstUserVmid || c.hw >= kFirstUserVmid + kNumUserVmids) continue;
        HwVmid &h = hwv[c.hw - kFirstUserVmid];
        if (h.ctx != i + 1) continue;
        wreg(kRegCtx0Cntl + c.hw, 0);
        h.faulted = rreg(kRegCtx0Cntl + c.hw) != 0 || !vmFlushTlb(c.hw);
        if (h.faulted) continue;
        h = HwVmid{};
        c.hw = 0;
    }
    // Failed replacement may have left hardware pointing at either old or new tables.
    if (!vmOwnershipKnown(0)) return;
    for (VmCtx &c : vm) {
        if (!c.busy || !c.closing || c.hw || c.retireSeq > done || (c.retireSeq && !observable) ||
            !c.used || c.used > c.pages || c.pages > kPtChunks * kPtChunkPages) continue;
        if (!ptClear(c)) continue;
        PhxRetiredBuffers *buffers = c.retiredBuffers;
        c.retiredBuffers = nullptr;
        c.used = 1;
        c.lastSeq = c.retireSeq = 0;
        c.closing = false;
        c.busy = false;
        phxReleaseBuffers(buffers);
    }
}

IOReturn PhxBringup::adoptQueue(const uint64_t in[6]) {
    if (!in) return kIOReturnBadArgument;
    if (!fbAper || !doorbellMap || !mmio || !fbMcBase || !gpuLock || !smuLock)
        return kIOReturnNotReady;
    // The queue index occupies fence bit 0; bits 1 and 2 must still be zero.
    const uint64_t ringOff = in[0], ringDw = in[1], wbOff = in[2], dbByte = in[3], wptr = in[4], fenceOff = in[5] & ~1ull;
    const uint32_t qi = static_cast<uint32_t>(in[5] & 1);
    if (ringDw < 256 || ringDw > 65536 || (ringDw & (ringDw - 1)) || (ringOff & 0xFF) ||
        (wbOff & 7) || (fenceOff & 7) || (dbByte & 7) ||
        !phxPspSpanFits(dbByte, 8, doorbellMap->getLength()))
        return kIOReturnBadArgument;
    const uint64_t offsets[] = {ringOff, wbOff, fenceOff};
    const uint64_t sizes[] = {ringDw * 4, 32, 8};
    for (unsigned i = 0; i < 3; ++i) {
        // Stored offsets and later raw writes are 32-bit. Validate the entire extent before narrowing.
        if (!phxPspSpanFits(offsets[i], sizes[i], 0x100000000ull) ||
            !phxPspSpanFits(offsets[i], sizes[i], fbAperLen) ||
            !phxPspSpanFits(offsets[i], sizes[i], fbSize))
            return kIOReturnBadArgument;
        for (unsigned j = 0; j < i; ++j)
            if (!phxPspDisjoint(offsets[i], sizes[i], offsets[j], sizes[j]))
                return kIOReturnBadArgument;
    }
    // Same lock order as configurePspLayout/bootMemory; layout cannot change during adoption.
    IOLockLock(gpuLock);
    IOLockLock(smuLock);
    const IOReturn result = [&]() -> IOReturn {
        GpuQueue &q = gq[qi];
        if (q.ready) return kIOReturnExclusiveAccess;
        if (stopping || !pspLayoutConfigured || pspSubmissionFaulted) return kIOReturnNotReady;
        if (!phxPspLayoutValid(&pspLayout, fbMcBase, fbPhys, fbSize, fbAperLen))
            return kIOReturnBadArgument;
        const uint64_t reserved[] = {pspLayout.ringOffset, pspLayout.tmrOffset, pspLayout.stagingOffset};
        const uint64_t capacities[] = {PHX_PSP_LAYOUT_RING_BYTES, pspLayout.tmrCapacity, pspLayout.stagingCapacity};
        for (unsigned i = 0; i < 3; ++i)
            for (unsigned j = 0; j < 3; ++j)
                if (!phxPspDisjoint(offsets[i], sizes[i], reserved[j], capacities[j]))
                    return kIOReturnExclusiveAccess;
        const GpuQueue &other = gq[qi ^ 1];
        if (other.ready) {
            if (dbByte == other.dbByte) return kIOReturnExclusiveAccess;
            const uint64_t occupied[] = {other.ringOff, other.wbOff, other.fenceOff};
            const uint64_t lengths[] = {static_cast<uint64_t>(other.ringDw) * 4, 32, 8};
            for (unsigned i = 0; i < 3; ++i)
                for (unsigned j = 0; j < 3; ++j)
                    if (!phxPspDisjoint(offsets[i], sizes[i], occupied[j], lengths[j]))
                        return kIOReturnExclusiveAccess;
        }
        GpuQueue next{};
        next.gfx = qi == 1;
        next.ringOff = static_cast<uint32_t>(ringOff);
        next.ringDw = static_cast<uint32_t>(ringDw);
        next.wbOff = static_cast<uint32_t>(wbOff);
        next.fenceOff = static_cast<uint32_t>(fenceOff);
        next.dbByte = dbByte;
        next.wptr = next.doneEnd = wptr;
        next.retiredSeq = gSeq;
        volatile uint32_t *fence = reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + fenceOff);
        fence[0] = static_cast<uint32_t>(gSeq);
        fence[1] = static_cast<uint32_t>(gSeq >> 32);
        hdpFlush();
        q = next;
        q.ready = true;
        return kIOReturnSuccess;
    }();
    IOLockUnlock(smuLock);
    IOLockUnlock(gpuLock);
    if (result == kIOReturnSuccess)
        IOLog("PhxBringup: adopted %s queue ring=+0x%llx (%llu dw) wptr=%llu doorbell=+0x%llx\n",
              qi ? "gfx" : "compute", ringOff, ringDw, wptr, dbByte);
    return result;
}

// PhxAccel (the NullMoth accelerator in its AMD configuration) starts only on a GPU marked as driven; matching is
// re-run so the accelerator personality, refused at boot, is offered the device again.
IOReturn PhxBringup::claimAccel() {
    if (!pci || !gpuReady())
        return kIOReturnNotReady;
    pci->setProperty("nmxgpu-claimed", kOSBooleanTrue);
    pci->registerService();
    IOLog("PhxBringup: GPU claimed for PhxAccel, matching re-run\n");
    return kIOReturnSuccess;
}

bool PhxBringup::vmOwnershipKnown(uint32_t repairing) const {
    if (repairing && (repairing < kFirstUserVmid || repairing >= kFirstUserVmid + kNumUserVmids)) return false;
    for (uint32_t i = 0; i < kNumUserVmids; ++i) {
        const HwVmid &h = hwv[i];
        if ((h.faulted && repairing != kFirstUserVmid + i) ||
            (h.ctx && (h.ctx > kMaxCtx || !vm[h.ctx - 1].busy || vm[h.ctx - 1].hw != kFirstUserVmid + i))) return false;
    }
    for (uint32_t i = 0; i < kMaxCtx; ++i) {
        const VmCtx &c = vm[i];
        if (c.busy && c.hw && (c.hw < kFirstUserVmid || c.hw >= kFirstUserVmid + kNumUserVmids ||
                              hwv[c.hw - kFirstUserVmid].ctx != i + 1)) return false;
    }
    return true;
}

// gpuLock held. A retry may repair this slot's failed invalidation, but not an unrelated uncertain slot.
IOReturn PhxBringup::vmIdleLocked(uint32_t handle, bool repair) {
    VmCtx *c = vmCtx(handle);
    if (!c || !gpuReady() || !mmio || !fbAper || !vmOwnershipKnown(repair ? c->hw : 0))
        return kIOReturnNotReady;
    if (c->lastSeq && gpuRetiredLocked() < c->lastSeq) return kIOReturnBusy;
    if (c->hw && !vmBindingValid(c->hw, c->phys)) {
        hwv[c->hw - kFirstUserVmid].faulted = true;
        return kIOReturnNotReady;
    }
    return kIOReturnSuccess;
}

IOReturn PhxBringup::vmCanReclaim(uint32_t handle) {
    if (!gpuLock) return kIOReturnNotReady;
    IOLockLock(gpuLock);
    const IOReturn result = vmIdleLocked(handle, false);
    IOLockUnlock(gpuLock);
    return result;
}

IOReturn PhxBringup::vmMap(uint32_t handle, uint64_t va, IOMemoryDescriptor *md, uint64_t off, uint64_t size, bool *cleanupRequired) {
    if (!cleanupRequired) return kIOReturnBadArgument;
    *cleanupRequired = false;
    if (!md || !size || ((va | off | size) & 4095) || va < 0x10000 ||
        !phx780m::rangeWithin(va, size, 1ull << 48) || !phx780m::rangeWithin(off, size, md->getLength()))
        return kIOReturnBadArgument;
    if (!gpuLock) return kIOReturnNotReady;
    IOLockLock(gpuLock);
    const IOReturn idle = vmIdleLocked(handle, true);
    if (idle != kIOReturnSuccess) { IOLockUnlock(gpuLock); return idle; }
    VmCtx &c = vm[handle - 1];
    // Validate the whole range before writing; an unreadable tree is not an empty mapping.
    for (uint64_t p = 0; p < size; p += 4096) {
        IOByteCount segLen = 0;
        const addr64_t pa = md->getPhysicalSegment(off + p, &segLen, kIOMemoryMapperNone);
        IOReturn lookup = kIOReturnVMError;
        uint64_t *pte = vmPte(c, va + p, false, &lookup);
        if (lookup != kIOReturnSuccess || (pte && *pte && !(*pte & 1))) {
            *cleanupRequired = true;
            IOLockUnlock(gpuLock);
            return kIOReturnVMError;
        }
        if (!pa || (pa & ~kPtAddrMask) || segLen < 4096 || (pte && *pte)) {
            IOLockUnlock(gpuLock);
            return pte && *pte ? kIOReturnExclusiveAccess : kIOReturnVMError;
        }
    }
    IOReturn result = kIOReturnSuccess;
    bool uncertain = false;
    uint64_t written = 0;
    for (; written < size; written += 4096) {
        IOByteCount segLen = 0;
        const addr64_t pa = md->getPhysicalSegment(off + written, &segLen, kIOMemoryMapperNone);
        if (!pa || (pa & ~kPtAddrMask) || segLen < 4096) { result = kIOReturnVMError; break; }
        IOReturn lookup = kIOReturnVMError;
        uint64_t *pte = vmPte(c, va + written, true, &lookup);
        if (!pte || lookup != kIOReturnSuccess) {
            result = lookup == kIOReturnNoMemory ? kIOReturnNoMemory : kIOReturnVMError;
            uncertain = result == kIOReturnVMError;
            if (uncertain) *cleanupRequired = true;
            break;
        }
        // Recheck after allocation too; never overwrite a leaf that became occupied.
        if (*pte) { result = kIOReturnVMError; uncertain = *cleanupRequired = true; break; }
        *cleanupRequired = true;
        *pte = pa | kPteSysFlags;
        flushLine(pte);
    }
    if (result != kIOReturnSuccess) {
        for (uint64_t p = 0; p < written; p += 4096) {
            IOReturn lookup = kIOReturnVMError;
            uint64_t *pte = vmPte(c, va + p, false, &lookup);
            IOByteCount segLen = 0;
            const addr64_t pa = md->getPhysicalSegment(off + p, &segLen, kIOMemoryMapperNone);
            if (lookup != kIOReturnSuccess || !pte || !pa || (pa & ~kPtAddrMask) || segLen < 4096 ||
                *pte != (pa | kPteSysFlags)) { uncertain = true; continue; }
            *pte = 0;
            flushLine(pte);
        }
    }
    if (c.hw && *cleanupRequired) {
        HwVmid &h = hwv[c.hw - kFirstUserVmid];
        h.faulted = !vmFlushTlb(c.hw);
        if (h.faulted) { IOLockUnlock(gpuLock); return kIOReturnTimeout; }
    }
    if (uncertain) { *cleanupRequired = true; IOLockUnlock(gpuLock); return kIOReturnVMError; }
    *cleanupRequired = false;
    IOLockUnlock(gpuLock);
    return result;
}

IOReturn PhxBringup::vmUnmap(uint32_t handle, uint64_t va, uint64_t size) {
    if (!size || ((va | size) & 4095) || va < 0x10000 || !phx780m::rangeWithin(va, size, 1ull << 48))
        return kIOReturnBadArgument;
    if (!gpuLock) return kIOReturnNotReady;
    IOLockLock(gpuLock);
    const IOReturn idle = vmIdleLocked(handle, true);
    if (idle != kIOReturnSuccess) { IOLockUnlock(gpuLock); return idle; }
    VmCtx &c = vm[handle - 1];
    // Preflight every page so a malformed later branch cannot silently authorize release.
    for (uint64_t p = 0; p < size; p += 4096) {
        IOReturn lookup = kIOReturnVMError;
        uint64_t *pte = vmPte(c, va + p, false, &lookup);
        if (lookup != kIOReturnSuccess || (pte && *pte &&
            ((!(*pte & kPtAddrMask)) || (*pte & ~kPtAddrMask) != kPteSysFlags))) {
            IOLockUnlock(gpuLock);
            return kIOReturnVMError;
        }
    }
    IOReturn result = kIOReturnSuccess;
    for (uint64_t p = 0; p < size; p += 4096) {
        IOReturn lookup = kIOReturnVMError;
        uint64_t *pte = vmPte(c, va + p, false, &lookup);
        if (lookup != kIOReturnSuccess || (pte && *pte &&
            ((!(*pte & kPtAddrMask)) || (*pte & ~kPtAddrMask) != kPteSysFlags))) {
            result = kIOReturnVMError;
            break;
        }
        if (pte && *pte) { *pte = 0; flushLine(pte); }
    }
    if (c.hw) {
        HwVmid &h = hwv[c.hw - kFirstUserVmid];
        h.faulted = !vmFlushTlb(c.hw);
        if (h.faulted) { IOLockUnlock(gpuLock); return kIOReturnTimeout; }
    }
    IOLockUnlock(gpuLock);
    return result;
}

void PhxBringup::ringPut(GpuQueue &q, uint32_t idx, uint32_t value) {
    const uint64_t slot = (q.wptr + idx) & (q.ringDw - 1);
    *reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + q.ringOff + slot * 4) = value;
}

uint64_t PhxBringup::queueFence(const GpuQueue &q) const {
    // Adoption requires an aligned eight-byte location; issue one native 64-bit observation.
    return *reinterpret_cast<const volatile uint64_t *>(fbAper->getVirtualAddress() + q.fenceOff);
}

// gpuLock held. Reject impossible observations before retiring history or publishing more work.
bool PhxBringup::queueProgress(const GpuQueue &q, uint64_t *doneOut) const {
    if (!doneOut || !fbAper || !q.ready || (q.fenceOff & 7) ||
        q.tail - q.head > 63 || q.retiredSeq > gSeq) return false;
    const uint64_t done = queueFence(q);
    if (done == UINT64_MAX || done < q.retiredSeq || done > gSeq) return false;
    uint64_t previous = q.retiredSeq;
    bool observed = done == q.retiredSeq;
    const uint32_t count = q.tail - q.head;
    for (uint32_t i = 0; i < count; ++i) {
        const uint64_t seq = q.fseq[(q.head + i) & 63];
        if (!seq || seq <= previous || seq > gSeq) return false;
        if (seq == done) observed = true;
        previous = seq;
    }
    if (!observed) return false;
    *doneOut = done;
    return true;
}

// gpuLock held: queue entries, sequence and history indices belong to one serialized snapshot.
uint64_t PhxBringup::gpuRetiredLocked() const {
    if (!fbAper || !mmio || (!gq[0].ready && !gq[1].ready)) return 0;
    uint64_t retired = gSeq;
    for (const GpuQueue &q : gq) {
        if (!q.ready) continue;
        uint64_t done = 0;
        if (!queueProgress(q, &done)) return 0;
        const uint32_t count = q.tail - q.head;
        for (uint32_t i = 0; i < count; ++i) {
            const uint64_t seq = q.fseq[(q.head + i) & 63];
            if (seq > done) {
                if (seq - 1 < retired) retired = seq - 1;
                break;
            }
        }
    }
    return retired;
}

uint64_t PhxBringup::gpuRetired() const {
    if (!gpuLock) return 0;
    IOLockLock(gpuLock);
    const uint64_t retired = gpuRetiredLocked();
    IOLockUnlock(gpuLock);
    return retired;
}

IOReturn PhxBringup::gpuSubmit(uint32_t handle, bool gfx, const uint64_t *ibVa, const uint32_t *ibDw, uint32_t n, uint64_t *seqOut) {
    if (!seqOut || !ibVa || !ibDw || !n || n > PHXN_MAX_IBS) return kIOReturnBadArgument;
    if (!gpuLock) return kIOReturnNotReady;
    IOLockLock(gpuLock);
    // Queue selection and context lookup share the lock with adoption, stop and retirement.
    const int queue = phx780m::queueIndex(gfx, gq[0].ready, gq[1].ready);
    if (stopping || queue < 0 || !vmCtx(handle) || !fbAper || !mmio || !doorbellMap) {
        IOLockUnlock(gpuLock); return kIOReturnNotReady;
    }
    GpuQueue &q = gq[queue];
    const uint32_t need = n * 4 + 8;
    if (q.ringDw < need + 16 || (q.ringDw & (q.ringDw - 1))) {
        IOLockUnlock(gpuLock); return kIOReturnBadArgument;
    }
    reapContextsLocked();
    if (gSeq == UINT64_MAX || q.wptr > UINT64_MAX - need) {
        IOLockUnlock(gpuLock);
        return kIOReturnNoResources;
    }
    // Ring space and the 64-entry history: retire finished entries, wait for the oldest one if needed (bounded, ~2 s).
    for (int spin = 0;; spin++) {
        uint64_t done = 0;
        if (!queueProgress(q, &done) || q.doneEnd > q.wptr) {
            IOLockUnlock(gpuLock); return kIOReturnBusy;
        }
        uint64_t end = q.doneEnd;
        const uint32_t count = q.tail - q.head;
        for (uint32_t i = 0; i < count; ++i) {
            const uint64_t next = q.fend[(q.head + i) & 63];
            if (next <= end || next > q.wptr) { IOLockUnlock(gpuLock); return kIOReturnBusy; }
            end = next;
        }
        if (end != q.wptr) { IOLockUnlock(gpuLock); return kIOReturnBusy; }
        while (q.head != q.tail && q.fseq[q.head & 63] <= done) {
            q.doneEnd = q.fend[q.head & 63];
            q.retiredSeq = q.fseq[q.head & 63];
            q.head++;
        }
        if (q.tail - q.head < 63 && q.wptr + need - q.doneEnd <= q.ringDw - 16)
            break;
        if (spin > 40000) {
            IOLockUnlock(gpuLock);
            return kIOReturnBusy;
        }
        IODelay(50);
    }
    const uint32_t vmid = vmBind(handle);
    if (!vmid) {
        IOLockUnlock(gpuLock);
        return kIOReturnBusy;
    }
    uint32_t k = 0;
    for (uint32_t i = 0; i < n; i++) {
        ringPut(q, k++, 0xC0023F00);                               // INDIRECT_BUFFER
        // the CP wants the canonical (sign-extended) address: an upper-half IB (bit 47, where RADV puts them) with a
        // bare 16-bit high word silently wedges the queue
        const uint64_t cva = (ibVa[i] & (1ull << 47)) ? (ibVa[i] | 0xFFFF000000000000ull) : ibVa[i];
        ringPut(q, k++, static_cast<uint32_t>(cva) & ~3u);
        ringPut(q, k++, static_cast<uint32_t>(cva >> 32));
        // size | VMID, plus VALID on compute (gfx_v11_0_ring_emit_ib_compute; the gfx variant has no VALID bit)
        ringPut(q, k++, ibDw[i] | (q.gfx ? 0u : (1u << 23)) | (vmid << 24));
    }
    const uint64_t seq = ++gSeq;
    vm[handle - 1].lastSeq = seq;
    hwv[vmid - kFirstUserVmid].lastSeq = seq;
    const uint64_t fenceMc = fbMcBase + q.fenceOff;
    ringPut(q, k++, 0xC0064900);                                   // RELEASE_MEM, as gfx_v11_0_ring_emit_fence
    ringPut(q, k++, 0x06603514);                                   // GCR SEQ|GL2_WB|GLM_INV|GLM_WB, CP 3, CACHE_FLUSH_AND_INV_TS, idx 5
    ringPut(q, k++, 0x40000000);                                   // DATA_SEL 2 (64-bit), no interrupt
    ringPut(q, k++, static_cast<uint32_t>(fenceMc));
    ringPut(q, k++, static_cast<uint32_t>(fenceMc >> 32));
    ringPut(q, k++, static_cast<uint32_t>(seq));
    ringPut(q, k++, static_cast<uint32_t>(seq >> 32));
    ringPut(q, k++, 0);
    q.wptr += k;
    q.fseq[q.tail & 63] = seq;
    q.fend[q.tail & 63] = q.wptr;
    __asm__ __volatile__("" ::: "memory");
    q.tail = q.tail + 1;
    // BAR0 is write-combined: drain the WC buffers so the packets are in VRAM before the CP is told about them
    __asm__ __volatile__("sfence" ::: "memory");
    (void)*reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + q.ringOff);
    hdpFlush();
    volatile uint32_t *wb = reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + q.wbOff + 16);
    wb[0] = static_cast<uint32_t>(q.wptr);
    wb[1] = static_cast<uint32_t>(q.wptr >> 32);
    __asm__ __volatile__("sfence" ::: "memory");
    (void)wb[0];
    hdpFlush();
    __asm__ __volatile__("mfence" ::: "memory");
    *reinterpret_cast<volatile uint64_t *>(doorbellMap->getVirtualAddress() + q.dbByte) = q.wptr;
    IOLockUnlock(gpuLock);
    *seqOut = seq;
    return kIOReturnSuccess;
}

IOReturn PhxBringup::doorbellWrite(uint64_t byteOff, uint64_t value) {
    if (!doorbellMap)
        return kIOReturnNotReady;
    if ((byteOff & 7) || !phx780m::rangeWithin(byteOff, 8, doorbellMap->getLength()))
        return kIOReturnBadArgument;
    *reinterpret_cast<volatile uint64_t *>(doorbellMap->getVirtualAddress() + byteOff) = value;
    return kIOReturnSuccess;
}

IOReturn PhxBringup::vramWrite(uint32_t byteOff, uint32_t value) {
    if (!fbAper)
        return kIOReturnNotReady;
    if ((byteOff & 3) || static_cast<uint64_t>(byteOff) + 4 > fbAperLen)
        return kIOReturnBadArgument;
    *reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + byteOff) = value;
    __asm__ __volatile__("sfence" ::: "memory");
    return kIOReturnSuccess;
}

// psp_wait_for(C2PMSG_64, MBOX_TOS_RESP_FLAG, MBOX_TOS_RESP_MASK): response flag set and status 0.
bool PhxBringup::pspWaitTos(uint32_t timeoutMs) const {
    for (uint32_t i = 0; i < timeoutMs * 10; i++) {
        if ((rreg(PHX_PSP_C2PMSG_64) & PHX_MBOX_TOS_MASK) == PHX_MBOX_TOS_READY)
            return true;
        IODelay(100);
    }
    return false;
}

// A locked software snapshot only; it does not reserve ranges or certify ownership.
IOReturn PhxBringup::bootMemory(PhxBootMemory *out) {
    if (!out) return kIOReturnBadArgument;
    *out = PhxBootMemory{};
    if (!smuLock || !gpuLock) return kIOReturnNotReady;
    IOLockLock(gpuLock);
    IOLockLock(smuLock);
    IOReturn result = kIOReturnNotReady;
    if (pspLayoutConfigured) {
        out->version = PHX_BOOT_MEMORY_VERSION;
        out->flags = PHX_BOOT_LAYOUT_CONFIGURED | (ringMc ? PHX_BOOT_RING_ACTIVE : 0) |
                     (tmrSetUp ? PHX_BOOT_TMR_ACTIVE : 0) | (gpuReady() ? PHX_BOOT_GPU_ACTIVE : 0) |
                     (pspSubmissionFaulted ? PHX_BOOT_PSP_FAULTED : 0);
        out->mcBase = fbMcBase; out->physicalBase = fbPhys;
        out->vramBytes = fbSize; out->apertureBytes = fbAperLen;
        out->tmrBytes = tmrSize; out->psp = pspLayout;
        result = kIOReturnSuccess;
    }
    IOLockUnlock(smuLock);
    IOLockUnlock(gpuLock);
    return result;
}

// Debug selector 114: validate/store numeric offsets only. This does not reserve memory or prove ownership.
IOReturn PhxBringup::configurePspLayout(const PhxPspLayout &layout, uint64_t out[4]) {
    if (!out) return kIOReturnBadArgument;
    for (unsigned i = 0; i < 4; ++i) out[i] = 0;
    if (!mmio || !fbAper || !smuLock || !gpuLock) return kIOReturnNotReady;
    IOLockLock(gpuLock);
    IOLockLock(smuLock);
    IOReturn r = kIOReturnSuccess;
    if (pspSubmissionFaulted) {
        r = kIOReturnNotReady;
    } else if (ringMc || tmrSetUp || fwBufSize || gpuReady()) {
        r = kIOReturnExclusiveAccess;
    } else if (!phxPspLayoutValid(&layout, fbMcBase, fbPhys, fbSize, fbAperLen)) {
        r = kIOReturnBadArgument;
    } else {
        pspLayout = layout;
        pspLayoutConfigured = true;
        out[0] = fbMcBase; out[1] = fbPhys; out[2] = fbSize; out[3] = fbAperLen;
    }
    IOLockUnlock(smuLock);
    IOLockUnlock(gpuLock);
    return r;
}

// Debug selector 101: ring creation uses the explicitly configured relative regions.
// BAR0 writes still require independently established target memory ownership.
IOReturn PhxBringup::pspRing(uint32_t op, uint64_t carveOffset, uint64_t out[4]) {
    if (!out) return kIOReturnBadArgument;
    for (unsigned i = 0; i < 4; ++i) out[i] = 0;
    if (!mmio || !fbAper || !fbMcBase || !smuLock)
        return kIOReturnNotReady;
    IOReturn r = kIOReturnSuccess;
    IOLockLock(smuLock);
    if (pspSubmissionFaulted && op != 3) {
        IOLockUnlock(smuLock);
        return kIOReturnNotReady;
    }
    if (op == 1) {
        if (!pspLayoutConfigured) {
            IOLockUnlock(smuLock);
            return kIOReturnNotReady;
        } else if (ringMc) {
            IOLockUnlock(smuLock);
            return kIOReturnExclusiveAccess;
        } else if (carveOffset != pspLayout.ringOffset ||
                   !phxPspLayoutValid(&pspLayout, fbMcBase, fbPhys, fbSize, fbAperLen)) {
            IOLockUnlock(smuLock);
            return kIOReturnBadArgument;
        } else {
            volatile uint32_t *ring = reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + carveOffset);
            uint32_t nonzero = 0;
            for (uint32_t i = 0; i < PHX_PSP_RING_BUF_SIZE / 4; i++)
                nonzero |= ring[i];
            out[2] = nonzero == 0;           // report whether the VRAM region was already clear (informational)
            for (uint32_t i = 0; i < PHX_PSP_RING_BUF_SIZE / 4; i++)
                ring[i] = 0;                 // zero the ring buffer (Linux memsets ring_mem; safe via BAR0)
            if (!pspWaitTos(2000)) {
                r = kIOReturnNotReady;       // SOS not ready to accept the ring
            } else {
                ringMc = fbMcBase + carveOffset;
                wreg(PHX_PSP_C2PMSG_69, static_cast<uint32_t>(ringMc));
                wreg(PHX_PSP_C2PMSG_70, static_cast<uint32_t>(ringMc >> 32));
                wreg(PHX_PSP_C2PMSG_71, PHX_PSP_RING_SIZE);
                wreg(PHX_PSP_C2PMSG_64, PHX_PSP_RING_TYPE_KM << 16);
                IOSleep(20);
                if (!pspWaitTos(2000)) {
                    r = kIOReturnTimeout;    // raw C2PMSG_64 (with PSP status in bits 15:0) returned in out[0]
                    ringMc = 0;
                    pspSubmissionFaulted = true; // acknowledgement is uncertain; do not retry writes
                    tocTmrSize = 0;
                } else {
                    // Ring is live. Lay the GPCOM command + fence buffers just above it and zero them,
                    // then reset the doorbell so wptr agrees with our slot 0 (Linux psp_v13_0_ring_create).
                    ringOff = carveOffset;
                    cmdOff = carveOffset + PHX_PSP_CMD_REL;
                    fenceOff = carveOffset + PHX_PSP_FENCE_REL;
                    cmdMc = fbMcBase + cmdOff;
                    fenceMc = fbMcBase + fenceOff;
                    fenceCounter = 0;
                    tmrOff = pspLayout.tmrOffset;
                    tmrMc = fbMcBase + tmrOff;
                    tmrSize = 0;
                    tmrSetUp = false;
                    fwBufOff = pspLayout.stagingOffset;
                    fwBufMc = fbMcBase + fwBufOff;
                    fwBufSize = pspLayout.stagingCapacity;
                    volatile uint32_t *cmd = reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + cmdOff);
                    volatile uint32_t *fen = reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + fenceOff);
                    for (uint32_t i = 0; i < 0x1000 / 4; i++) {
                        cmd[i] = 0;
                        fen[i] = 0;
                    }
                    wreg(PHX_PSP_C2PMSG_67, 0);
                }
            }
        }
    } else if (op == 2) {
        wreg(PHX_PSP_C2PMSG_64, PHX_GFX_CTRL_CMD_ID_DESTROY_RINGS);
        IOSleep(20);
        if (!pspWaitTos(2000)) {
            r = kIOReturnTimeout;
            pspSubmissionFaulted = true;
            tocTmrSize = 0;
            tmrSetUp = false;
            tmrSize = 0;
        } else {
            clearRing();
        }
    } else if (op != 3) {
        r = kIOReturnBadArgument;
    }
    out[0] = rreg(PHX_PSP_C2PMSG_64);
    out[1] = ringMc;
    out[3] = rreg(PHX_PSP_C2PMSG_67);
    IOLockUnlock(smuLock);
    return r;
}

// Core GPCOM submit (caller holds smuLock and a ring exists): write a prepared command — cmd_id plus up to
// nWords union dwords at +28 — into the VRAM command buffer, ring the doorbell, wait for the PSP's fence and
// read the response. Ports Linux psp_cmd_submit_buf / Cobalt64 psp_ring_cmd_submit.
IOReturn PhxBringup::pspRunCmd(uint32_t cmdId, const uint32_t *unionWords, uint32_t nWords, uint64_t out[4]) {
    if (!out) return kIOReturnBadArgument;
    for (unsigned i = 0; i < 4; ++i) out[i] = 0;
    if (!mmio || !fbAper || !ringMc || pspSubmissionFaulted)
        return kIOReturnNotReady;
    if (nWords > 14 || (nWords && !unionWords) || (cmdOff & 3) || (fenceOff & 3) || (ringOff & 63) ||
        !phx780m::rangeWithin(cmdOff, PHX_PSP_CMD_BUF_SIZE, fbAperLen) ||
        !phx780m::rangeWithin(fenceOff, 4, fbAperLen) ||
        !phx780m::rangeWithin(ringOff, PHX_PSP_RING_SIZE, fbAperLen))
        return kIOReturnBadArgument;
    if (fenceCounter == UINT32_MAX)
        return kIOReturnNoResources;
    const uint32_t ringSizeDw = PHX_PSP_RING_SIZE / 4;
    const uint32_t frameSizeDw = PHX_PSP_GFX_FRAME_SIZE / 4;
    uint32_t wptr = rreg(PHX_PSP_C2PMSG_67);
    if (wptr > ringSizeDw || wptr % frameSizeDw)
        return kIOReturnBadArgument;
    const uint32_t slot = (wptr % ringSizeDw) / frameSizeDw;
    volatile uint8_t *base = reinterpret_cast<volatile uint8_t *>(fbAper->getVirtualAddress());
    volatile uint32_t *cmd = reinterpret_cast<volatile uint32_t *>(base + cmdOff);
    volatile uint32_t *fen = reinterpret_cast<volatile uint32_t *>(base + fenceOff);

    // Command buffer: zero it, set cmd_id (buf_size/buf_version stay 0, as upstream does), then the union.
    for (uint32_t i = 0; i < PHX_PSP_CMD_BUF_SIZE / 4; i++)
        cmd[i] = 0;
    cmd[PHX_PSP_CMD_HDR_CMD_ID_OFFSET / 4] = cmdId;
    for (uint32_t i = 0; i < nWords; i++)
        cmd[PHX_PSP_GFX_CMD_UNION_OFFSET / 4 + i] = unionWords[i];

    uint32_t fence = ++fenceCounter;
    fen[0] = 0;

    // Ring frame at the slot the current wptr points to.
    PhxGfxRbFrame frame;
    bzero(&frame, sizeof(frame));
    frame.cmd_buf_addr_lo = static_cast<uint32_t>(cmdMc);
    frame.cmd_buf_addr_hi = static_cast<uint32_t>(cmdMc >> 32);
    frame.fence_addr_lo = static_cast<uint32_t>(fenceMc);
    frame.fence_addr_hi = static_cast<uint32_t>(fenceMc >> 32);
    frame.fence_value = fence;
    volatile uint32_t *slotp =
        reinterpret_cast<volatile uint32_t *>(base + ringOff + static_cast<uint64_t>(slot) * PHX_PSP_GFX_FRAME_SIZE);
    for (uint32_t i = 0; i < PHX_PSP_GFX_FRAME_SIZE / 4; i++) {
        uint32_t word;
        memcpy(&word, reinterpret_cast<const uint8_t *>(&frame) + i * 4, sizeof(word));
        slotp[i] = word;
    }

    // Drain CPU write buffers, flush the host data path, then ring the doorbell.
    __asm__ __volatile__("sfence" ::: "memory");
    hdpFlush();
    wptr = (wptr + frameSizeDw) % ringSizeDw;
    wreg(PHX_PSP_C2PMSG_67, wptr);

    // Wait for the PSP to write the fence value into VRAM (BAR0 read bypasses the CPU cache).
    uint32_t observed = 0, us = 0;
    const uint32_t budgetUs = 5000000;
    while (us < budgetUs) {
        observed = fen[0];
        if (observed == fence)
            break;
        IOSleep(1);
        us += 1000;
    }
    uint32_t status = cmd[PHX_PSP_GFX_RESP_OFFSET / 4];
    out[0] = (observed == fence) ? status : 0xFFFFFFFFu;
    out[1] = us;
    if (observed != fence || status != 0) {
        pspSubmissionFaulted = true;
        tocTmrSize = 0;
        tmrSetUp = false;
        tmrSize = 0;
        // IOKit need not return output scalars on error; the non-success return is authoritative.
        return observed != fence ? kIOReturnTimeout : kIOReturnError;
    }
    out[2] = cmd[(PHX_PSP_GFX_RESP_OFFSET + 8) / 4];   // resp.fw_addr_lo / session_id
    out[3] = cmd[(PHX_PSP_GFX_RESP_OFFSET + 12) / 4];  // resp.fw_addr_hi
    return kIOReturnSuccess;
}

// Selector 103: no-payload query command (FB_FW_RESERV_ADDR/EXT only) — validates the ring without touching GPU power.
IOReturn PhxBringup::pspSubmit(uint32_t cmdId, uint64_t out[4]) {
    if (!mmio || !fbAper)
        return kIOReturnNotReady;
    if (cmdId != PHX_PSP_GFX_CMD_FB_FW_RESERV_ADDR && cmdId != PHX_PSP_GFX_CMD_FB_FW_RESERV_EXT_ADDR)
        return kIOReturnNotPermitted;
    IOLockLock(smuLock);
    IOReturn r = ringMc ? pspRunCmd(cmdId, nullptr, 0, out) : kIOReturnNotReady;
    IOLockUnlock(smuLock);
    return r;
}

// Selector 104: stage a chunk of firmware bytes into the VRAM fw_buf through BAR0 (no submit).
IOReturn PhxBringup::fwStage(uint32_t dstOffset, const void *bytes, uint32_t len) {
    IOLockLock(smuLock);
    if (!fbAper || !fwBufSize || pspSubmissionFaulted) {
        IOLockUnlock(smuLock);
        return kIOReturnNotReady;
    }
    const uint64_t padded = (static_cast<uint64_t>(len) + 3) & ~3ull;
    if (!bytes || !len || (dstOffset & 3) ||
        !phx780m::rangeWithin(dstOffset, padded, fwBufSize) ||
        !phx780m::rangeWithin(fwBufOff, fwBufSize, fbAperLen)) {
        IOLockUnlock(smuLock);
        return kIOReturnBadArgument;
    }
    volatile uint8_t *dst = reinterpret_cast<volatile uint8_t *>(fbAper->getVirtualAddress() + fwBufOff + dstOffset);
    const uint8_t *s = static_cast<const uint8_t *>(bytes);
    uint32_t i = 0;
    for (; static_cast<uint64_t>(i) + 4 <= len; i += 4) {
        uint32_t v;
        memcpy(&v, s + i, 4);
        *reinterpret_cast<volatile uint32_t *>(dst + i) = v;
    }
    if (i < len) {
        uint32_t v = 0;
        memcpy(&v, s + i, len - i);
        *reinterpret_cast<volatile uint32_t *>(dst + i) = v;
    }
    __asm__ __volatile__("sfence" ::: "memory");
    IOLockUnlock(smuLock);
    return kIOReturnSuccess;
}

// Selector 115: load a staged TOC and observe its required TMR size, without setting up the TMR.
IOReturn PhxBringup::loadToc(uint32_t fwBufOffset, uint32_t size, uint64_t out[4]) {
    if (!out) return kIOReturnBadArgument;
    for (unsigned i = 0; i < 4; ++i) out[i] = 0;
    if (!mmio || !fbAper || !smuLock) return kIOReturnNotReady;
    IOLockLock(smuLock);
    IOReturn r;
    if (!ringMc || !pspLayoutConfigured || pspSubmissionFaulted) {
        r = kIOReturnNotReady;
    } else if (tmrSetUp) {
        r = kIOReturnExclusiveAccess;
    } else if (!size || (fwBufOffset & 0xfff) ||
               !phxPspLayoutValid(&pspLayout, fbMcBase, fbPhys, fbSize, fbAperLen) ||
               !phx780m::rangeWithin(fwBufOffset, size, fwBufSize) ||
               !phx780m::rangeWithin(fwBufOff, fwBufSize, fbAperLen) ||
               fwBufMc > UINT64_MAX - fwBufOffset || ((fwBufMc + fwBufOffset) & 0xfff)) {
        r = kIOReturnBadArgument;
    } else {
        tocTmrSize = 0;
        tmrSize = 0;
        const uint64_t mc = fwBufMc + fwBufOffset;
        uint32_t words[3] = {static_cast<uint32_t>(mc), static_cast<uint32_t>(mc >> 32), size};
        r = pspRunCmd(PHX_PSP_LOAD_TOC_COMMAND, words, 3, out);
        out[2] = out[3] = 0;
        if (r == kIOReturnSuccess) {
            volatile uint32_t *cmd = reinterpret_cast<volatile uint32_t *>(fbAper->getVirtualAddress() + cmdOff);
            tocTmrSize = cmd[(PHX_PSP_GFX_RESP_OFFSET + PHX_PSP_TOC_SIZE_RESPONSE_REL) / 4];
            if (!tocTmrSize) {
                pspSubmissionFaulted = true;
                r = kIOReturnError;
            } else {
                out[2] = tocTmrSize;
                out[3] = phxPspTmrFits(&pspLayout, fbMcBase, fbPhys, tocTmrSize) ? 1 : 0;
            }
        }
    }
    IOLockUnlock(smuLock);
    return r;
}

// Selector 105: load engine firmware only after the managed TMR setup completed.
IOReturn PhxBringup::loadIpFw(uint32_t fwType, uint32_t fwBufOffset, uint32_t size, uint64_t out[4]) {
    if (!mmio || !fbAper)
        return kIOReturnNotReady;
    IOLockLock(smuLock);
    IOReturn r;
    if (!ringMc || pspSubmissionFaulted || !tmrSetUp) {
        r = kIOReturnNotReady;
    } else if ((fwBufOffset & 3) || !size ||
               !phx780m::rangeWithin(fwBufOffset, size, fwBufSize) ||
               !phx780m::rangeWithin(fwBufOff, fwBufSize, fbAperLen) ||
               fwBufMc > UINT64_MAX - fwBufOffset) {
        r = kIOReturnBadArgument;
    } else {
        uint64_t mc = fwBufMc + fwBufOffset;
        uint32_t u[4] = {static_cast<uint32_t>(mc), static_cast<uint32_t>(mc >> 32), size, fwType};
        r = pspRunCmd(PHX_PSP_GFX_CMD_LOAD_IP_FW, u, 4, out);
    }
    IOLockUnlock(smuLock);
    return r;
}

// Selector 106: op 1 = SETUP_TMR (driver-managed TMR, Phoenix psp_13_0_4 is not in psp_skip_tmr), op 2 = AUTOLOAD_RLC.
IOReturn PhxBringup::pspCtl(uint32_t op, uint32_t arg, uint64_t out[4]) {
    if (!mmio || !fbAper)
        return kIOReturnNotReady;
    IOLockLock(smuLock);
    IOReturn r;
    if (!ringMc || pspSubmissionFaulted) {
        r = kIOReturnNotReady;
    } else if (op == 1) {
        if (tmrSetUp) {
            IOLockUnlock(smuLock);
            return kIOReturnExclusiveAccess;
        }
        uint32_t size = arg;
        if (!tocTmrSize) {
            IOLockUnlock(smuLock);
            return kIOReturnNotReady;
        }
        if (!pspLayoutConfigured || size != tocTmrSize ||
            !phxPspTmrFits(&pspLayout, fbMcBase, fbPhys, size)) {
            IOLockUnlock(smuLock);
            return kIOReturnBadArgument;
        }
        // psp_gfx_cmd_setup_tmr (Linux psp_prep_tmr_cmd_buf): buf_phy_addr = TMR MC address, buf_size,
        // bitfield(virt_phy_addr=1 => 0x2), system_phy_addr = the REAL system-physical address of the TMR
        // (amdgpu_gmc_vram_pa = mc - vram_start + vram_base_offset = fbPhys + tmrOff on this UMA part).
        uint64_t tmrPa = fbPhys + tmrOff;
        uint32_t u[6] = {static_cast<uint32_t>(tmrMc), static_cast<uint32_t>(tmrMc >> 32), size, 0x2u,
                         static_cast<uint32_t>(tmrPa), static_cast<uint32_t>(tmrPa >> 32)};
        r = pspRunCmd(PHX_PSP_GFX_CMD_SETUP_TMR, u, 6, out);
        tmrSetUp = r == kIOReturnSuccess;
        tmrSize = tmrSetUp ? size : 0;
    } else if (op == 2) {
        r = tmrSetUp ? pspRunCmd(PHX_PSP_GFX_CMD_AUTOLOAD_RLC, nullptr, 0, out) : kIOReturnNotReady;
    } else {
        r = kIOReturnBadArgument;
    }
    IOLockUnlock(smuLock);
    return r;
}

// Selector 107: submit an arbitrary GPCOM command with six caller-supplied union dwords. For bring-up
// experiments (SETUP_TMR / LOAD_TOC parameter sweeps) without rebuilding the kext.
IOReturn PhxBringup::pspRaw(uint32_t cmdId, const uint32_t words[6], uint64_t out[4]) {
    if (!mmio || !fbAper)
        return kIOReturnNotReady;
    IOLockLock(smuLock);
    IOReturn r = ringMc ? pspRunCmd(cmdId, words, 6, out) : kIOReturnNotReady;
    IOLockUnlock(smuLock);
    return r;
}

// Polls the SMU response register for up to 2 s (Linux: usec_timeout * 20); 0 means no answer.
uint32_t PhxBringup::smuPoll() const {
    for (uint32_t i = 0; i < 200000; i++) {
        uint32_t r = rreg(PHX_SMU_RESP_REG);
        if (r)
            return r;
        IODelay(10);
    }
    return 0;
}

// One SMU 13.0.4 mailbox transaction, the sequence of Linux smu_msg_v1_send_msg().
IOReturn PhxBringup::smuMessage(uint32_t msg, uint32_t arg, uint32_t *resp, uint32_t *argAfter) {
    if (!mmio || !smuLock)
        return kIOReturnNotReady;
    IOLockLock(smuLock);
    // The first message of the boot skips the pre-poll (Linux SMU_FW_INIT): nothing may have been sent yet.
    if (smuUsed && smuPoll() == 0) {
        IOLockUnlock(smuLock);
        return kIOReturnBusy;
    }
    smuUsed = true;
    wreg(PHX_SMU_RESP_REG, 0);
    wreg(PHX_SMU_ARG_REG, arg);
    wreg(PHX_SMU_MSG_REG, msg);
    uint32_t r = smuPoll();
    *resp = r;
    *argAfter = rreg(PHX_SMU_ARG_REG);
    IOLockUnlock(smuLock);
    return r ? kIOReturnSuccess : kIOReturnTimeout;
}

bool PhxBringup::claimSession() { return OSCompareAndSwap(0, 1, &sessionOpen); }

void PhxBringup::releaseSession() { OSCompareAndSwap(1, 0, &sessionOpen); }

IOReturn PhxBringup::readRegs(uint32_t first, uint32_t count, uint32_t *out) {
    if (!mmio)
        return kIOReturnNotReady;
    uint64_t len = mmio->getLength();
    if ((static_cast<uint64_t>(first) + count) * 4 > len)
        return kIOReturnBadArgument;
    volatile uint32_t *r = reinterpret_cast<volatile uint32_t *>(mmio->getVirtualAddress());
    for (uint32_t i = 0; i < count; i++)
        out[i] = r[first + i];
    return kIOReturnSuccess;
}

IOReturn PhxBringup::newUserClient(task_t owningTask, void *securityID, UInt32 type, IOUserClient **handler) {
    // the sysctls go up with the first client, from user space, rather than in start(): the bootloader injects this
    // kext into the boot collection, and it starts long before the rest of BSD
    if (!gSysctlUp && OSCompareAndSwap(0, 1, &gSysctlUp)) {
        sysctl_register_oid(&sysctl__debug_phxbos_flush);
        sysctl_register_oid(&sysctl__debug_phxbos_flush_bytes);
        sysctl_register_oid(&sysctl__debug_phxbos_handles_high);
        sysctl_register_oid(&sysctl__debug_phxbos_handles_full);
    }
    if (type != PHXN_UC_TYPE)
        return kIOReturnBadArgument;
    IOAccelPhxNativeClient *client = OSTypeAlloc(IOAccelPhxNativeClient);
    if (!client)
        return kIOReturnNoMemory;
    if (!client->initWithTask(owningTask, securityID, type) || !client->attach(this)) {
        client->release();
        return kIOReturnNoMemory;
    }
    if (!client->start(this)) {
        client->detach(this);
        client->release();
        return kIOReturnExclusiveAccess;
    }
    *handler = client;
    return kIOReturnSuccess;
}

// ---- user client ----------------------------------------------------------------------------------------

bool IOAccelPhxNativeClient::initWithTask(task_t owningTask, void *securityID, UInt32 type) {
    if (!IOUserClient::initWithTask(owningTask, securityID, type))
        return false;
    privileged = clientHasPrivilege(owningTask, kIOClientPrivilegeAdministrator) == kIOReturnSuccess;
    task = owningTask;
    lock = IOLockAlloc();
    bufferStorage = static_cast<PhxRetiredBuffers *>(IOMallocZero(sizeof(PhxRetiredBuffers)));
    bos = bufferStorage ? bufferStorage->entries : nullptr;
    maps = static_cast<Map *>(IOMallocZero(sizeof(Map) * kMaxMaps));
    return lock && bos && maps;
}

bool IOAccelPhxNativeClient::start(IOService *provider) {
    owner = OSDynamicCast(PhxBringup, provider);
    if (!owner)
        return false;
    // E9: several processes at once, each in its own GPUVM context (vmidAlloc); the first one still marks the session
    if (owner->claimSession())
        sessionClaimed = true;
    return IOUserClient::start(provider);
}

void IOAccelPhxNativeClient::freeAll() {
    if (!bos)
        return;
    for (uint32_t h = 1; h < PHXN_MAX_BOS; h++)
        if (bos[h].md)
            boRelease(bos[h]);
}

// Caller holds the client lock, or is the final destructor with no concurrent methods.
void IOAccelPhxNativeClient::closeResources() {
    if (closed) return;
    closed = true;
    if (vmid && owner) {
        owner->deferClient(vmid, lastSeq, bufferStorage);
        bufferStorage = nullptr;
        bos = nullptr;
        vmid = 0;
    } else {
        freeAll();
    }
}

IOReturn IOAccelPhxNativeClient::clientClose() {
    if (lock) IOLockLock(lock);
    closeResources();
    if (lock) IOLockUnlock(lock);
    if (sessionClaimed && owner) {
        owner->releaseSession();
        sessionClaimed = false;
    }
    terminate();
    return kIOReturnSuccess;
}

void IOAccelPhxNativeClient::free() {
    closeResources();
    if (sessionClaimed && owner) owner->releaseSession();
    if (bufferStorage) IOFree(bufferStorage, sizeof(PhxRetiredBuffers));
    if (maps) IOFree(maps, sizeof(Map) * kMaxMaps);
    if (lock) IOLockFree(lock);
    IOUserClient::free();
}

IOAccelPhxNativeClient::Bo *IOAccelPhxNativeClient::findBo(uint32_t h) {
    if (!bos || h == 0 || h >= PHXN_MAX_BOS || !bos[h].md || bos[h].pendingFree)
        return nullptr;
    return &bos[h];
}

IOReturn IOAccelPhxNativeClient::clientMemoryForType(UInt32 type, IOOptionBits *options, IOMemoryDescriptor **memory) {
    IOLockLock(lock);
    if (closed) { IOLockUnlock(lock); return kIOReturnNotReady; }
    Bo *b = findBo(type);
    if (!b) {
        IOLockUnlock(lock);
        return kIOReturnNotFound;
    }
    b->md->retain();
    *memory = b->md;
    *options = 0;
    IOLockUnlock(lock);
    return kIOReturnSuccess;
}

// Exact shape check, as in the contract: scalar counts and struct sizes must match.
static bool shape(const IOExternalMethodArguments *a, uint32_t sin, uint32_t sout, uint32_t stin, uint32_t stout) {
    return a->scalarInputCount == sin && a->scalarOutputCount == sout && a->structureInputSize == stin &&
           a->structureOutputSize == stout && !a->structureInputDescriptor && !a->structureOutputDescriptor;
}

IOReturn IOAccelPhxNativeClient::externalMethod(uint32_t selector, IOExternalMethodArguments *a,
                                                IOExternalMethodDispatch *, OSObject *, void *) {
    if (selector == PHXN_SEL_WAITSEQ)
        return doWaitSeq(a);

    IOLockLock(lock);
    IOReturn r;
    if (closed || (selector != PHXN_SEL_HELLO && !hello)) {
        r = kIOReturnNotReady;
    } else {
        reapPending();
        switch (selector) {
        case PHXN_SEL_HELLO:     r = doHello(a); break;
        case PHXN_SEL_QUERYINFO: r = doQueryInfo(a); break;
        case PHXN_SEL_READREGS:  r = doReadRegs(a); break;
        case PHXN_SEL_BOCREATE:  r = doBoCreate(a); break;
        case PHXN_SEL_BOFREE:    r = doBoFree(a); break;
        case PHXN_SEL_BOIMPORTHOST: r = doBoImportHost(a); break;
        case PHXN_SEL_GEMVA:     r = doGemVa(a); break;
        case PHXN_SEL_CTX:       r = doCtx(a); break;
        case PHXN_SEL_SUBMIT:    r = doSubmit(a); break;
        case PHXN_SEL_DBG_SMU:   r = doDbgSmu(a); break;
        case PHXN_SEL_DBG_PSP_RING: r = doDbgPspRing(a); break;
        case PHX_PSP_LAYOUT_SELECTOR: r = doDbgPspLayout(a); break;
        case PHX_BOOT_MEMORY_SELECTOR: r = doDbgBootMemory(a); break;
        case PHX_PSP_LOAD_TOC_SELECTOR: r = doDbgLoadToc(a); break;
        case PHXN_SEL_DBG_VRAM_READ: r = doDbgVramRead(a); break;
        case PHXN_SEL_DBG_PSP_SUBMIT: r = doDbgPspSubmit(a); break;
        case PHXN_SEL_DBG_FW_STAGE: r = doDbgFwStage(a); break;
        case PHXN_SEL_DBG_PSP_LOADIPFW: r = doDbgLoadIpFw(a); break;
        case PHXN_SEL_DBG_PSP_CTL: r = doDbgPspCtl(a); break;
        case PHXN_SEL_DBG_PSP_RAW: r = doDbgPspRaw(a); break;
        case PHXN_SEL_DBG_WRITE_REG: r = doDbgWriteReg(a); break;
        case PHXN_SEL_DBG_VRAM_WRITE: r = doDbgVramWrite(a); break;
        case PHXN_SEL_DBG_DOORBELL: r = doDbgDoorbell(a); break;
        case PHXN_SEL_DBG_SYSMEM: r = doDbgSysMem(a); break;
        case PHXN_SEL_DBG_ADOPTQ: r = doDbgAdoptQueue(a); break;
        case PHXN_SEL_DBG_CLAIM: r = doDbgClaim(a); break;
        default:                 r = kIOReturnBadArgument; break;
        }
    }
    IOLockUnlock(lock);
    return r;
}

IOReturn IOAccelPhxNativeClient::doHello(IOExternalMethodArguments *a) {
    if (!shape(a, 2, 4, 0, 0))
        return kIOReturnBadArgument;
    if (a->scalarInput[1] != 0 && a->scalarInput[1] != PHXN_HELLO_F_MINOR)
        return kIOReturnBadArgument;
    if (a->scalarInput[0] != PHXN_ABI_VERSION)
        return kIOReturnUnsupported;
    hello = true;
    a->scalarOutput[0] = PHXN_ABI_VERSION | (a->scalarInput[1] ? static_cast<uint64_t>(PHXN_ABI_MINOR) << 16 : 0);
    a->scalarOutput[1] = PHX_KEXT_BUILD;
    a->scalarOutput[2] = PHXN_MAX_IBS;
    a->scalarOutput[3] = PHXN_VMID;
    return kIOReturnSuccess;
}

IOReturn IOAccelPhxNativeClient::doQueryInfo(IOExternalMethodArguments *a) {
    if (!shape(a, 0, 0, 0, sizeof(phxn_info)))
        return kIOReturnBadArgument;
    phxn_info inf;
    bzero(&inf, sizeof(inf));
    inf.abi_version = PHXN_ABI_VERSION;
    inf.kext_build = PHX_KEXT_BUILD;
    inf.reserved[2] = PHXN_ABI_MINOR;
    inf.flags = PHXN_INFO_NATIVE_BOOT | PHXN_INFO_ASSUMED_PROFILE | PHXN_INFO_SOFTWARE_BUDGETS |
        (owner->gpuReady() ? PHXN_INFO_S1B_POSITIVE : 0);
    inf.vmid = PHXN_VMID;
    inf.gb_addr_config = kGbAddrConfig;
    inf.gc_version = kGcVersion;
    inf.ring_size_dw = 4096;
    inf.max_ibs = PHXN_MAX_IBS;
    inf.vram_vis_total = kVisTotal;
    inf.vram_vis_free = kVisTotal - visUsed;
    inf.vram_hi_total = kHiTotal;
    inf.vram_hi_free = kHiTotal - hiUsed;
    inf.gtt_cap = kGttCap;
    inf.gtt_used = gttUsed;
    inf.gtt_max_bo = kGttMaxBo;
    inf.seq_emitted = emitted;
    inf.seq_retired = owner->gpuReady() ? owner->gpuRetired() : 0;
    inf.va_low_first = 0x10000;
    inf.va_low_last = 0x7FFFFFFFFFFFull;
    inf.va_high_first = 0xFFFF800000000000ull;
    inf.va_high_last = 0xFFFFFFFFFFFFFFFFull;
    inf.max_bos = PHXN_MAX_BOS;
    inf.fence_slots = PHXN_FENCE_SLOTS;
    bcopy(&inf, a->structureOutput, sizeof(inf));
    return kIOReturnSuccess;
}

static constexpr uint64_t kGoldenTscUpper = 0x16a2d;
IOReturn IOAccelPhxNativeClient::doReadRegs(IOExternalMethodArguments *a) {
    if (a->scalarInputCount != 3 || a->scalarOutputCount != 0 || a->structureInputSize != 0)
        return kIOReturnBadArgument;
    uint64_t count = a->scalarInput[1];
    if (count < 1 || count > 16 || a->scalarInput[2] != 0xFFFFFFFFull || a->structureOutputSize != count * 4 ||
        a->scalarInput[0] > 0xFFFFFFFFull)
        return kIOReturnBadArgument;
    // SMUIO's GOLDEN_TSC (upper 0x16a2d, lower 0x16a2e on Phoenix, SMUIO 13.0.7 base 0x16a00) is the 100 MHz counter the
    // CP stamps command buffers with: every client may read it (Mesa's AMDGPU_INFO_TIMESTAMP, which calibrates GPU
    // times against the host's; without it Metal's GPUStartTime/GPUEndTime were 0 in every app).
    const uint64_t first = a->scalarInput[0];
    const bool tsc = first >= kGoldenTscUpper && first + count <= kGoldenTscUpper + 2;
    if (!privileged && !tsc)
        return kIOReturnNotPrivileged;
    return owner->readRegs(static_cast<uint32_t>(a->scalarInput[0]), static_cast<uint32_t>(count),
                           static_cast<uint32_t *>(a->structureOutput));
}

IOReturn IOAccelPhxNativeClient::doBoCreate(IOExternalMethodArguments *a) {
    if (!shape(a, 0, 4, sizeof(phxn_gem_create_in), 0))
        return kIOReturnBadArgument;
    const phxn_gem_create_in *in = static_cast<const phxn_gem_create_in *>(a->structureInput);
    uint64_t size = 0;
    if (!phx780m::boPageSize(in->bo_size, &size))
        return kIOReturnBadArgument;
    uint64_t align = in->alignment;
    if (align && ((align & (align - 1)) || align > (2ull << 20)))
        return kIOReturnBadArgument;
    if (align < 4096)
        align = 4096;
    const uint64_t d = in->domains, f = in->domain_flags;
    if (d == 0 || (d & ~static_cast<uint64_t>(PHX_AMDGPU_GEM_DOMAIN_GTT | PHX_AMDGPU_GEM_DOMAIN_VRAM)))
        return kIOReturnUnsupported;
    if (f & (PHX_AMDGPU_GEM_CREATE_ENCRYPTED | PHX_AMDGPU_GEM_CREATE_CP_MQD_GFX9 | PHX_AMDGPU_GEM_CREATE_PREEMPTIBLE))
        return kIOReturnUnsupported;

    uint32_t domain, bits;
    uint64_t *pool;
    if (d & PHX_AMDGPU_GEM_DOMAIN_VRAM) {
        if (phx780m::boBudgetFits(visUsed, size, kVisTotal)) {
            domain = 4;
            bits = PHXN_PLACED_CPU_MAPPABLE | PHXN_PLACED_ZEROED;
            pool = &visUsed;
        } else if ((f & PHX_AMDGPU_GEM_CREATE_NO_CPU_ACCESS) && !(f & PHX_AMDGPU_GEM_CREATE_CPU_ACCESS_REQUIRED) &&
                   phx780m::boBudgetFits(hiUsed, size, kHiTotal)) {
            domain = 4;
            bits = PHXN_PLACED_HI_POOL | PHXN_PLACED_ZEROED;
            pool = &hiUsed;
        } else {
            return kIOReturnNoMemory;
        }
    } else {
        if (size > kGttMaxBo || !phx780m::boBudgetFits(gttUsed, size, kGttCap))
            return kIOReturnNoMemory;
        domain = 2;
        bits = PHXN_PLACED_ZEROED;
        pool = &gttUsed;
    }

    uint32_t h = 1;
    while (h < PHXN_MAX_BOS && bos[h].md)
        h++;
    if (h >= PHXN_MAX_BOS) {
        // Counted, and logged once per session: on hardware this is the difference between "every texture
        // allocation failed" and a line that names the limit that ran out (docs/RADEARC-REFERENCE.md §2).
        OSAddAtomic64(1, &gBosHandlesFull);
        if (OSCompareAndSwap(0, 1, &gBosHandlesFullLogged))
            IOLog("PhxBringup: bos: no free handle below PHXN_MAX_BOS (%u): refusing allocations until a BO is "
                  "freed; debug.phxbos_handles_full counts these\n", PHXN_MAX_BOS);
        return kIOReturnNoResources;
    }
    if (static_cast<SInt64>(h) > gBosHandlesHigh) gBosHandlesHigh = static_cast<SInt64>(h);

    // Page alignment only: the GPU maps BOs page by page, and the client picks the VA (GEMVA) with its own alignment.
    // Handed to IOBufferMemoryDescriptor, RADV's 64 KiB..2 MiB alignment made every allocation PHYSICALLY CONTIGUOUS
    // (XNU allocates an alignment above the page size with kmem_alloc_contig): once memory was fragmented, every
    // buffer of 8 MiB or more failed after a 400 ms search, and each Metal app spent ~0.8 s at launch (2026-10-21).
    (void)align;
    IOBufferMemoryDescriptor *md = IOBufferMemoryDescriptor::inTaskWithOptions(
        kernel_task, kIODirectionInOut | kIOMemoryKernelUserShared, size, PAGE_SIZE);
    if (!md)
        return kIOReturnNoMemory;
    void *bytes = md->getBytesNoCopy();
    if (!bytes) {
        md->release();
        return kIOReturnNoMemory;
    }
    bzero(bytes, size);
    *pool += size;
    bos[h] = Bo{md, size, domain, bits, static_cast<uint8_t *>(bytes), false, false};
    a->scalarOutput[0] = h;
    a->scalarOutput[1] = size;
    a->scalarOutput[2] = domain;
    a->scalarOutput[3] = bits;
    return kIOReturnSuccess;
}

// Client lock held. A logical free keeps its handle slot, budgets, descriptor and pins until cleanup succeeds.
bool IOAccelPhxNativeClient::hasPending() const {
    if (!bos || !maps) return false;
    for (uint32_t h = 1; h < PHXN_MAX_BOS; ++h) if (bos[h].md && bos[h].pendingFree) return true;
    for (int i = 0; i < kMaxMaps; ++i) if (maps[i].used && maps[i].pending) return true;
    return false;
}

void IOAccelPhxNativeClient::reapPending() {
    if (closed || !bos || !maps) return;
    for (int i = 0; i < kMaxMaps; ++i) {
        Map &m = maps[i];
        if (!m.used || !m.pending) continue;
        if (!m.handle || m.handle >= PHXN_MAX_BOS || !bos[m.handle].md) return;
        if (vmid && owner && owner->vmUnmap(vmid, m.va, m.size) == kIOReturnSuccess) m = Map{};
    }
    uint64_t mapped[(PHXN_MAX_BOS + 63) / 64]{};
    for (int i = 0; i < kMaxMaps; ++i) {
        const Map &m = maps[i];
        if (!m.used) continue;
        if (!m.handle || m.handle >= PHXN_MAX_BOS) return;
        mapped[m.handle / 64] |= 1ull << (m.handle & 63);
    }
    for (uint32_t h = 1; h < PHXN_MAX_BOS; ++h) {
        Bo &b = bos[h];
        if (!b.md || !b.pendingFree) continue;
        if ((mapped[h / 64] & (1ull << (h & 63))) ||
            (vmid && (!owner || owner->vmCanReclaim(vmid) != kIOReturnSuccess))) continue;
        uint64_t *pool = b.host ? &hostUsed : b.domain == 2 ? &gttUsed :
            (b.bits & PHXN_PLACED_HI_POOL) ? &hiUsed : &visUsed;
        if (*pool < b.size) continue;
        *pool -= b.size;
        boRelease(b);
    }
}

IOReturn IOAccelPhxNativeClient::doBoFree(IOExternalMethodArguments *a) {
    if (!shape(a, 1, 0, 0, 0) || a->scalarInput[0] > UINT32_MAX) return kIOReturnBadArgument;
    const uint32_t h = static_cast<uint32_t>(a->scalarInput[0]);
    Bo *b = findBo(h);
    if (!b) return kIOReturnNotFound;
    b->pendingFree = true;
    for (int i = 0; i < kMaxMaps; ++i)
        if (maps[i].used && maps[i].handle == h) maps[i].pending = true;
    if (pendFenceHandle == h) { pendFenceHandle = pendFenceOffset = 0; pendFenceSeq = 0; }
    reapPending();
    return kIOReturnSuccess;
}

void IOAccelPhxNativeClient::boRelease(Bo &b) {
    if (b.host)
        b.md->complete();
    b.md->release();
    b = Bo{};
}

// PHXN_SEL_BOIMPORTHOST (ABI 1.9, VK_EXT_external_memory_host): a BO over the caller's own pages, wired for as long as
// it lives, GPU-mapped later through GemVa like any other. The kext reported ABI 1.12 without it, so every import
// RADV made (no-copy buffers, IOSurface textures over their surfaces' pages) failed and fell back to copies
// (2026-10-20). in: [0] host VA [1] size (both page-aligned) [2] flags 0 [3] GPU VA 0; out: [0] handle [1] size
// [2] GPU VA 0 [3] placement bits.
IOReturn IOAccelPhxNativeClient::doBoImportHost(IOExternalMethodArguments *a) {
    if (!shape(a, 4, 4, 0, 0))
        return kIOReturnBadArgument;
    const uint64_t va = a->scalarInput[0], size = a->scalarInput[1];
    if (!va || !size || (va & 4095) || (size & 4095) || a->scalarInput[2] || a->scalarInput[3] || !task)
        return kIOReturnBadArgument;
    if (size > kHostMaxBo || !phx780m::boBudgetFits(hostUsed, size, kHostCap))
        return kIOReturnNoMemory;
    uint32_t h = 1;
    while (h < PHXN_MAX_BOS && bos[h].md)
        h++;
    if (h >= PHXN_MAX_BOS) {
        OSAddAtomic64(1, &gBosHandlesFull);
        if (OSCompareAndSwap(0, 1, &gBosHandlesFullLogged))
            IOLog("PhxBringup: bos: no free handle below PHXN_MAX_BOS (%u) for a host import; "
                  "debug.phxbos_handles_full counts these\n", PHXN_MAX_BOS);
        return kIOReturnNoResources;
    }
    if (static_cast<SInt64>(h) > gBosHandlesHigh) gBosHandlesHigh = static_cast<SInt64>(h);
    IOMemoryDescriptor *md = IOMemoryDescriptor::withAddressRange(va, size, kIODirectionInOut, task);
    if (!md)
        return kIOReturnNoMemory;
    const IOReturn r = md->prepare();
    if (r != kIOReturnSuccess) {
        md->release();
        return r;
    }
    hostUsed += size;
    bos[h] = Bo{md, size, 2, 0, nullptr, true, false};
    a->scalarOutput[0] = h;
    a->scalarOutput[1] = size;
    a->scalarOutput[2] = 0;
    a->scalarOutput[3] = 0;
    return kIOReturnSuccess;
}

IOReturn IOAccelPhxNativeClient::doGemVa(IOExternalMethodArguments *a) {
    if (!shape(a, 0, 0, sizeof(phxn_gem_va), 0))
        return kIOReturnBadArgument;
    const phxn_gem_va *v = static_cast<const phxn_gem_va *>(a->structureInput);
    if (v->_pad || v->vm_timeline_point || v->vm_timeline_syncobj_out || v->num_syncobj_handles ||
        v->input_fence_syncobj_handles)
        return kIOReturnBadArgument;
    if (v->handle == 0 || (v->flags & PHX_AMDGPU_VM_PAGE_PRT))
        return kIOReturnUnsupported;
    if (v->operation == PHX_AMDGPU_VA_OP_CLEAR || v->operation == PHX_AMDGPU_VA_OP_REPLACE)
        return kIOReturnUnsupported;
    if (v->operation != PHX_AMDGPU_VA_OP_MAP && v->operation != PHX_AMDGPU_VA_OP_UNMAP)
        return kIOReturnBadArgument;
    Bo *b = findBo(v->handle);
    if (!b)
        return kIOReturnNotFound;
    if (!vaCanonical(v->va_address))
        return kIOReturnBadArgument;
    const uint64_t va = v->va_address & kVaMask;
    if (((v->va_address | v->offset_in_bo | v->map_size) & 4095) || v->map_size == 0)
        return kIOReturnBadArgument;
    if (va < 0x10000 || !phx780m::rangeWithin(va, v->map_size, 1ull << 48))
        return kIOReturnBadArgument;
    if (!phx780m::rangeWithin(v->offset_in_bo, v->map_size, b->size))
        return kIOReturnBadArgument;

    if (v->operation == PHX_AMDGPU_VA_OP_MAP) {
        int freei = -1;
        for (int i = 0; i < kMaxMaps; i++) {
            if (!maps[i].used) {
                if (freei < 0)
                    freei = i;
                continue;
            }
            if (va < maps[i].va + maps[i].size && maps[i].va < va + v->map_size)
                return maps[i].pending ? kIOReturnBusy : kIOReturnBadArgument;
        }
        if (freei < 0)
            return kIOReturnNoMemory;
        if (!owner || !owner->gpuReady()) return kIOReturnNotReady;
        if (!ensureVmid()) return kIOReturnNoResources;
        maps[freei] = Map{true, v->handle, va, v->map_size, v->offset_in_bo, v->flags, true};
        bool cleanupRequired = false;
        const IOReturn r = owner->vmMap(vmid, va, b->md, v->offset_in_bo, v->map_size, &cleanupRequired);
        if (r == kIOReturnSuccess) maps[freei].pending = false;
        else if (!cleanupRequired) maps[freei] = Map{};
        return r;
    }
    for (int i = 0; i < kMaxMaps; i++) {
        if (maps[i].used && maps[i].handle == v->handle && maps[i].va == va && maps[i].size == v->map_size) {
            if (!vmid || !owner) return kIOReturnNotReady;
            const IOReturn r = owner->vmUnmap(vmid, va, v->map_size);
            if (r == kIOReturnSuccess) maps[i] = Map{};
            else if (r == kIOReturnTimeout || r == kIOReturnVMError) maps[i].pending = true;
            return r;
        }
    }
    // Retrying a completed cleanup is idempotent; never accept a partial overlap as an unmap.
    for (int i = 0; i < kMaxMaps; ++i)
        if (maps[i].used && va < maps[i].va + maps[i].size && maps[i].va < va + v->map_size)
            return kIOReturnBadArgument;
    return kIOReturnSuccess;
}

IOReturn IOAccelPhxNativeClient::doCtx(IOExternalMethodArguments *a) {
    if (!shape(a, 0, 0, sizeof(phxn_ctx), sizeof(phxn_ctx)))
        return kIOReturnBadArgument;
    phxn_ctx in, out;
    bcopy(a->structureInput, &in, sizeof(in));
    bzero(&out, sizeof(out));
    if (in.op == PHX_AMDGPU_CTX_OP_ALLOC_CTX) {
        uint32_t id = 1;
        while (id <= PHXN_MAX_CTX && ctx[id])
            id++;
        if (id > PHXN_MAX_CTX)
            return kIOReturnNoResources;
        ctx[id] = true;
        out.op = id;
    } else if (in.op == PHX_AMDGPU_CTX_OP_FREE_CTX) {
        if (in.ctx_id == 0 || in.ctx_id > PHXN_MAX_CTX || !ctx[in.ctx_id])
            return kIOReturnNotFound;
        ctx[in.ctx_id] = false;
    } else if (in.op != PHX_AMDGPU_CTX_OP_QUERY_STATE2) {
        return kIOReturnBadArgument;
    }
    bcopy(&out, a->structureOutput, sizeof(out));
    return kIOReturnSuccess;
}

bool IOAccelPhxNativeClient::ibCovered(uint64_t vaCanon, uint64_t bytes) {
    uint64_t cur = vaCanon & kVaMask;
    const uint64_t end = cur + bytes;
    while (cur < end) {
        bool ok = false;
        for (int i = 0; i < kMaxMaps; i++) {
            const Map &mp = maps[i];
            if (mp.used && !mp.pending && findBo(mp.handle) && (mp.flags & PHX_AMDGPU_VM_PAGE_EXECUTABLE) && cur >= mp.va && cur < mp.va + mp.size) {
                cur = mp.va + mp.size < end ? mp.va + mp.size : end;
                ok = true;
                break;
            }
        }
        if (!ok)
            return false;
    }
    return true;
}

IOReturn IOAccelPhxNativeClient::doSubmit(IOExternalMethodArguments *a) {
    if (a->scalarInputCount != 0 || a->scalarOutputCount != 1 || a->structureOutputSize != 0 ||
        a->structureInputDescriptor || a->structureInputSize < 64 ||
        a->structureInputSize > 32 + 32 * PHXN_MAX_IBS)
        return kIOReturnBadArgument;
    const uint8_t *in = static_cast<const uint8_t *>(a->structureInput);
    phxn_cs_in h;
    bcopy(in, &h, sizeof(h));
    if (h.abi != PHXN_ABI_VERSION || h.num_ibs < 1 || h.num_ibs > PHXN_MAX_IBS ||
        a->structureInputSize != sizeof(h) + h.num_ibs * sizeof(phxn_cs_ib) || h.reserved != 0 ||
        (h.flags & ~PHXN_CS_HAS_FENCE))
        return kIOReturnBadArgument;
    if (h.ctx_id == 0 || h.ctx_id > PHXN_MAX_CTX || !ctx[h.ctx_id])
        return kIOReturnNotFound;
    reapPending();
    if (hasPending()) return kIOReturnBusy;

    phxn_cs_ib firstIb;
    bcopy(in + sizeof(h), &firstIb, sizeof(firstIb));
    for (uint32_t i = 0; i < h.num_ibs; i++) {
        phxn_cs_ib ib;
        bcopy(in + sizeof(h) + i * sizeof(ib), &ib, sizeof(ib));
        if (!phx780m::sameEngine(firstIb.ip_type, ib.ip_type))
            return kIOReturnUnsupported;
        if (ib._pad || (ib.ip_type != PHX_AMDGPU_HW_IP_GFX && ib.ip_type != PHX_AMDGPU_HW_IP_COMPUTE) || ib.ip_instance != 0 || ib.ring != 0)
            return kIOReturnBadArgument;
        if (ib.ib_bytes == 0 || (ib.ib_bytes & 3) || ib.ib_bytes > 0xFFFFFu * 4)
            return kIOReturnBadArgument;
        if (!vaCanonical(ib.va_start) || (ib.va_start & 3))
            return kIOReturnBadArgument;
        if (ib.flags & (PHX_AMDGPU_IB_FLAG_CE | PHX_AMDGPU_IB_FLAG_RESET_GDS_MAX_WAVE_ID | PHX_AMDGPU_IB_FLAGS_SECURE |
                        PHX_AMDGPU_IB_FLAG_EMIT_MEM_SYNC))
            return kIOReturnUnsupported;
        if (ib.flags & ~static_cast<uint32_t>(PHX_AMDGPU_IB_FLAG_PREAMBLE | PHX_AMDGPU_IB_FLAG_PREEMPT |
                                              PHX_AMDGPU_IB_FLAG_TC_WB_NOT_INVALIDATE))
            return kIOReturnBadArgument;
        if (!ibCovered(ib.va_start, ib.ib_bytes))
            return kIOReturnBadArgument;
    }

    Bo *fb = nullptr;
    if (h.flags & PHXN_CS_HAS_FENCE) {
        fb = findBo(h.fence_handle);
        if (!fb)
            return kIOReturnNotFound;
        if (!fb->kva || (h.fence_offset & 7) || static_cast<uint64_t>(h.fence_offset) + 8 > fb->size)
            return kIOReturnBadArgument;   // the kernel writes the fence: not into a host import
    } else if (h.fence_handle || h.fence_offset) {
        return kIOReturnBadArgument;
    }

    if (owner->gpuReady()) {
        // E8: real execution on the adopted compute queue, IBs run in VMID 8
        uint64_t va[PHXN_MAX_IBS];
        uint32_t dw[PHXN_MAX_IBS];
        for (uint32_t i = 0; i < h.num_ibs; i++) {
            phxn_cs_ib ib;
            bcopy(in + sizeof(h) + i * sizeof(ib), &ib, sizeof(ib));
            va[i] = ib.va_start & kVaMask;
            dw[i] = ib.ib_bytes / 4;
        }
        // log the IBs RADV sends (first 96 dwords each) for bring-up: a client's first submissions only, as every
        // WindowServer frame dumped its IBs and the log held nothing else (2026-10-20)
        if (owner->debugEnabled() && emitted < 4) {
            for (uint32_t i = 0; i < h.num_ibs; i++) {
                for (int m = 0; m < kMaxMaps; m++) {
                    const Map &mp = maps[m];
                    if (!mp.used || mp.pending || !(mp.flags & PHX_AMDGPU_VM_PAGE_EXECUTABLE) ||
                        va[i] < mp.va || va[i] - mp.va >= mp.size)
                        continue;
                    Bo *bo = findBo(mp.handle);
                    if (!bo || !bo->kva || !bo->md)
                        break;
                    const uint64_t relative = va[i] - mp.va;
                    if (!phx780m::rangeWithin(mp.off, relative, bo->size)) break;
                    const uint64_t offset = mp.off + relative;
                    const uint64_t descriptorBytes = bo->md->getLength();
                    if (offset > descriptorBytes) break;
                    uint64_t available = mp.size - relative;
                    if (available > bo->size - offset) available = bo->size - offset;
                    if (available > descriptorBytes - offset) available = descriptorBytes - offset;
                    uint32_t cnt = dw[i] < 96 ? dw[i] : 96;
                    if (cnt > available / 4) cnt = static_cast<uint32_t>(available / 4);
                    const uintptr_t base = reinterpret_cast<uintptr_t>(bo->kva);
                    if (!cnt || offset > UINTPTR_MAX - base) break;
                    const uintptr_t address = base + offset;
                    if ((address & 3) || static_cast<uint64_t>(cnt) * 4 > UINTPTR_MAX - address) break;
                    // A valid IB can span adjacent BO mappings; log only this CPU-visible prefix.
                    const uint32_t *d = reinterpret_cast<const uint32_t *>(address);
                    for (uint32_t j = 0; j < cnt; j += 8)
                        IOLog("PhxIB %u.%u +%02x: %08x %08x %08x %08x %08x %08x %08x %08x\n", (unsigned)(emitted + 1), i, j,
                              d[j], j + 1 < cnt ? d[j + 1] : 0, j + 2 < cnt ? d[j + 2] : 0, j + 3 < cnt ? d[j + 3] : 0,
                              j + 4 < cnt ? d[j + 4] : 0, j + 5 < cnt ? d[j + 5] : 0, j + 6 < cnt ? d[j + 6] : 0,
                              j + 7 < cnt ? d[j + 7] : 0);
                    break;
                }
            }
        }
        flushBos();
        uint64_t seq = 0;
        phxn_cs_ib ib0;
        bcopy(in + sizeof(h), &ib0, sizeof(ib0));
        if (!ensureVmid())
            return kIOReturnNoResources;
        const IOReturn r = owner->gpuSubmit(vmid, ib0.ip_type == PHX_AMDGPU_HW_IP_GFX, va, dw, h.num_ibs, &seq);
        if (r != kIOReturnSuccess)
            return r;
        lastSeq = seq;
        emitted = seq;   // externalMethod already holds `lock`
        if (fb) {
            pendFenceHandle = h.fence_handle;
            pendFenceOffset = h.fence_offset;
            pendFenceSeq = seq;
        }
        a->scalarOutput[0] = seq;
        return kIOReturnSuccess;
    }
    // No synthetic fence retirement: success requires a real hardware submission.
    return kIOReturnNotReady;
}

IOReturn IOAccelPhxNativeClient::doDbgSmu(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 2, 2, 0, 0) || a->scalarInput[1] > 0xFFFFFFFFull)
        return kIOReturnBadArgument;
    switch (a->scalarInput[0]) {
    case PHX_PPSMC_TestMessage:
    case PHX_PPSMC_GetPmfwVersion:
    case PHX_PPSMC_GetDriverIfVersion:
    case PHX_PPSMC_GetEnabledSmuFeatures:
    case PHX_PPSMC_AllowGfxOff:
    case PHX_PPSMC_DisallowGfxOff:
    case PHX_PPSMC_EnableGfxImu:
        break;
    default:
        return kIOReturnNotPermitted;
    }
    uint32_t resp = 0, after = 0;
    IOReturn r = owner->smuMessage(static_cast<uint32_t>(a->scalarInput[0]), static_cast<uint32_t>(a->scalarInput[1]),
                                   &resp, &after);
    a->scalarOutput[0] = resp;
    a->scalarOutput[1] = after;
    return r;
}

IOReturn IOAccelPhxNativeClient::doDbgLoadToc(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled()) return kIOReturnUnsupported;
    if (!privileged) return kIOReturnNotPrivileged;
    if (!shape(a, 2, 4, 0, 0) || a->scalarInput[0] > UINT32_MAX || a->scalarInput[1] > UINT32_MAX)
        return kIOReturnBadArgument;
    uint64_t out[4]{};
    IOReturn r = owner->loadToc(static_cast<uint32_t>(a->scalarInput[0]), static_cast<uint32_t>(a->scalarInput[1]), out);
    if (r == kIOReturnSuccess)
        for (unsigned i = 0; i < 4; ++i) a->scalarOutput[i] = out[i];
    return r;
}

IOReturn IOAccelPhxNativeClient::doDbgBootMemory(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled()) return kIOReturnUnsupported;
    if (!privileged) return kIOReturnNotPrivileged;
    if (!shape(a, 0, 0, 0, sizeof(PhxBootMemory)) || !a->structureOutput) return kIOReturnBadArgument;
    PhxBootMemory memory{};
    IOReturn result = owner->bootMemory(&memory);
    memcpy(a->structureOutput, &memory, sizeof(memory));
    return result;
}

IOReturn IOAccelPhxNativeClient::doDbgPspLayout(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled()) return kIOReturnUnsupported;
    if (!privileged) return kIOReturnNotPrivileged;
    if (!shape(a, 0, 4, sizeof(PhxPspLayout), 0) || !a->structureInput)
        return kIOReturnBadArgument;
    PhxPspLayout layout;
    memcpy(&layout, a->structureInput, sizeof(layout));
    uint64_t out[4]{};
    IOReturn r = owner->configurePspLayout(layout, out);
    if (r == kIOReturnSuccess)
        for (unsigned i = 0; i < 4; ++i) a->scalarOutput[i] = out[i];
    return r;
}

IOReturn IOAccelPhxNativeClient::doDbgPspRing(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 2, 4, 0, 0))
        return kIOReturnBadArgument;
    uint64_t out[4] = {0, 0, 0, 0};
    IOReturn r = owner->pspRing(static_cast<uint32_t>(a->scalarInput[0]), a->scalarInput[1], out);
    for (int i = 0; i < 4; i++)
        a->scalarOutput[i] = out[i];
    return r;
}

IOReturn IOAccelPhxNativeClient::doDbgVramRead(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (a->scalarInputCount != 2 || a->scalarOutputCount != 0 || a->structureInputSize != 0)
        return kIOReturnBadArgument;
    uint64_t off = a->scalarInput[0], count = a->scalarInput[1];
    if (count < 1 || count > 256 || off > 0xFFFFFFFFull || a->structureOutputSize != count * 4)
        return kIOReturnBadArgument;
    return owner->vramRead(static_cast<uint32_t>(off), static_cast<uint32_t>(count),
                           static_cast<uint32_t *>(a->structureOutput));
}

IOReturn IOAccelPhxNativeClient::doDbgPspSubmit(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 1, 4, 0, 0) || a->scalarInput[0] > 0xFFFFFFFFull)
        return kIOReturnBadArgument;
    uint64_t out[4] = {0, 0, 0, 0};
    IOReturn r = owner->pspSubmit(static_cast<uint32_t>(a->scalarInput[0]), out);
    for (int i = 0; i < 4; i++)
        a->scalarOutput[i] = out[i];
    return r;
}

IOReturn IOAccelPhxNativeClient::doDbgFwStage(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (a->scalarInputCount != 1 || a->scalarOutputCount != 0 || a->structureOutputSize != 0)
        return kIOReturnBadArgument;
    if (a->structureInputDescriptor || !a->structureInput || a->structureInputSize == 0 ||
        a->structureInputSize > 4096 || a->scalarInput[0] > 0xFFFFFFFFull)
        return kIOReturnBadArgument;
    return owner->fwStage(static_cast<uint32_t>(a->scalarInput[0]), a->structureInput, a->structureInputSize);
}

IOReturn IOAccelPhxNativeClient::doDbgLoadIpFw(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 3, 4, 0, 0) || a->scalarInput[0] > 0xFFFFFFFFull || a->scalarInput[1] > 0xFFFFFFFFull ||
        a->scalarInput[2] > 0xFFFFFFFFull)
        return kIOReturnBadArgument;
    uint64_t out[4] = {0, 0, 0, 0};
    IOReturn r = owner->loadIpFw(static_cast<uint32_t>(a->scalarInput[0]), static_cast<uint32_t>(a->scalarInput[1]),
                                 static_cast<uint32_t>(a->scalarInput[2]), out);
    for (int i = 0; i < 4; i++)
        a->scalarOutput[i] = out[i];
    return r;
}

IOReturn IOAccelPhxNativeClient::doDbgPspCtl(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 2, 4, 0, 0) || a->scalarInput[0] > 0xFFFFFFFFull || a->scalarInput[1] > 0xFFFFFFFFull)
        return kIOReturnBadArgument;
    uint64_t out[4] = {0, 0, 0, 0};
    IOReturn r = owner->pspCtl(static_cast<uint32_t>(a->scalarInput[0]), static_cast<uint32_t>(a->scalarInput[1]), out);
    for (int i = 0; i < 4; i++)
        a->scalarOutput[i] = out[i];
    return r;
}

IOReturn IOAccelPhxNativeClient::doDbgPspRaw(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 7, 4, 0, 0))
        return kIOReturnBadArgument;
    uint32_t w[6];
    for (int i = 0; i < 6; i++)
        w[i] = static_cast<uint32_t>(a->scalarInput[i + 1]);
    uint64_t out[4] = {0, 0, 0, 0};
    IOReturn r = owner->pspRaw(static_cast<uint32_t>(a->scalarInput[0]), w, out);
    for (int i = 0; i < 4; i++)
        a->scalarOutput[i] = out[i];
    return r;
}

IOReturn IOAccelPhxNativeClient::doDbgWriteReg(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 2, 1, 0, 0) || a->scalarInput[0] > 0xFFFFFFFFull || a->scalarInput[1] > 0xFFFFFFFFull)
        return kIOReturnBadArgument;
    uint32_t rb = 0;
    IOReturn r = owner->writeReg(static_cast<uint32_t>(a->scalarInput[0]), static_cast<uint32_t>(a->scalarInput[1]), &rb);
    a->scalarOutput[0] = rb;
    return r;
}

IOReturn IOAccelPhxNativeClient::doDbgVramWrite(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 2, 0, 0, 0) || a->scalarInput[0] > 0xFFFFFFFFull || a->scalarInput[1] > 0xFFFFFFFFull)
        return kIOReturnBadArgument;
    return owner->vramWrite(static_cast<uint32_t>(a->scalarInput[0]), static_cast<uint32_t>(a->scalarInput[1]));
}

IOReturn IOAccelPhxNativeClient::doDbgDoorbell(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 3, 0, 0, 0))
        return kIOReturnBadArgument;
    return owner->doorbellWrite(a->scalarInput[0], a->scalarInput[1] | (a->scalarInput[2] << 32));
}

IOReturn IOAccelPhxNativeClient::doDbgSysMem(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 3, 2, 0, 0))
        return kIOReturnBadArgument;
    return owner->sysMem(a->scalarInput[0], a->scalarInput[1], a->scalarInput[2], &a->scalarOutput[0], &a->scalarOutput[1]);
}

IOReturn IOAccelPhxNativeClient::doDbgAdoptQueue(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 6, 0, 0, 0))
        return kIOReturnBadArgument;
    return owner->adoptQueue(a->scalarInput);
}

IOReturn IOAccelPhxNativeClient::doDbgClaim(IOExternalMethodArguments *a) {
    if (!owner->debugEnabled())
        return kIOReturnUnsupported;
    if (!privileged)
        return kIOReturnNotPrivileged;
    if (!shape(a, 1, 0, 0, 0) || a->scalarInput[0] != 1)
        return kIOReturnBadArgument;
    return owner->claimAccel();
}

// Write back and invalidate the CPU caches over every BO: CPU-written data must be in memory before the GPU reads
// it, and the CPU must not read stale lines after the GPU wrote. Coarse: WindowServer's BOs (full-screen surfaces
// among them) made this its hottest loop, hence debug.phxbos_flush.
void IOAccelPhxNativeClient::flushBos() {
    const int mode = gBosFlush;
    if (!mode)
        return;
    uint64_t bytes = 0;
    for (uint32_t h = 1; h < PHXN_MAX_BOS; h++) {
        if (!bos[h].kva)   // host imports: the CPU's own pages, which the GPU reads and writes snooped
            continue;
        const uint8_t *p = bos[h].kva;
        if (mode == 1) {
            for (uint64_t o = 0; o < bos[h].size; o += 64)
                __asm__ __volatile__("clflushopt (%0)" ::"r"(p + o) : "memory");
        } else {
            for (uint64_t o = 0; o < bos[h].size; o += 64)
                __asm__ __volatile__("clflush (%0)" ::"r"(p + o) : "memory");
        }
        bytes += bos[h].size;
    }
    __asm__ __volatile__("mfence" ::: "memory");
    OSAddAtomic64((SInt64)bytes, &gBosFlushBytes);
}

IOReturn IOAccelPhxNativeClient::doWaitSeq(IOExternalMethodArguments *a) {
    if (!shape(a, 3, 3, 0, 0)) return kIOReturnBadArgument;
    IOLockLock(lock);
    if (!hello || closed) { IOLockUnlock(lock); return kIOReturnNotReady; }
    uint64_t target = a->scalarInput[0];
    const uint64_t em = emitted;
    IOLockUnlock(lock);
    if (target == PHXN_SEQ_LAST)
        target = em;
    if (target > em)
        return kIOReturnBadArgument;
    if (owner->gpuReady()) {
        // E8: poll the RELEASE_MEM fence the adopted queue writes after each submission
        uint64_t timeout = a->scalarInput[1];
        if (timeout > PHXN_WAIT_CAP_NS)
            timeout = PHXN_WAIT_CAP_NS;
        uint64_t retired = owner->gpuRetired();
        for (uint64_t waited = 0; retired < target && waited < timeout; waited += 100000) {
            IODelay(100);
            retired = owner->gpuRetired();
        }
        if (retired >= target) {
            // drop CPU cache lines so the CPU sees what the GPU wrote; under the lock, as another thread of the same
            // client (WindowServer) freed a BO mid-flush and the walk dereferenced its NULL descriptor (panic 2026-10-20)
            IOLockLock(lock);
            if (closed) { IOLockUnlock(lock); return kIOReturnNotReady; }
            owner->reapContexts();
            reapPending();
            flushBos();
            if (pendFenceSeq && pendFenceSeq <= retired) {
                Bo *fb = findBo(pendFenceHandle);
                if (fb && fb->kva && pendFenceOffset + 8 <= fb->size)
                    bcopy(&pendFenceSeq, fb->kva + pendFenceOffset, 8);
                pendFenceSeq = 0;
            }
            IOLockUnlock(lock);
        }
        a->scalarOutput[0] = retired < target;
        a->scalarOutput[1] = retired;
        a->scalarOutput[2] = em;
        return kIOReturnSuccess;
    }
    // Hardware disappearance is not evidence that the caller's work completed.
    return kIOReturnNotReady;
}
