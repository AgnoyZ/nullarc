// PhxFB: the 780M's display as an IOFramebuffer that PhxAccel (NMXAccel) composites for WindowServer.
// Like NullMoth's NMIntelFB (phase 1), it takes over the mode the firmware (GOP) already lit, at boot in place of the
// firmware framebuffer (IONDRV), and writes nothing to the display engine: the scan-out surface is the boot console's
// (IOPlatformExpert::getConsoleInfo), the accelerator's display pipe copies each finished frame into a write-combined CPU
// mapping of it, and a timer at the panel's refresh (measured on the display engine, measureRefresh) stands in for the VBL
// interrupt WindowServer paces an accelerated display on.
#include <IOKit/IOLib.h>
#include <IOKit/pci/IOPCIDevice.h>
#include <IOKit/graphics/IOFramebuffer.h>
#include <IOKit/graphics/IODisplay.h>
#include <IOKit/IODeviceMemory.h>
#include <IOKit/pwr_mgt/RootDomain.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <pexpert/pexpert.h>
#include <IOKit/IOTimerEventSource.h>
#include <IOKit/IOWorkLoop.h>
#include <IOKit/IOBufferMemoryDescriptor.h>
#include <IOKit/IORangeAllocator.h>
#include <IOKit/IOSubMemoryDescriptor.h>
#include <libkern/c++/OSObject.h>
#include <libkern/OSAtomic.h>
#include <libkern/locks.h>
#include <libkern/c++/OSData.h>
#include <sys/sysctl.h>
#include "nvrm_vram_abi.h"
#include "nvrm_gpuva_abi.h"
#include "../PhxHardwarePolicy.hpp"
#include "phx_panel_timing.h"
#include "phx_dcn_zerocopy.h"
#include "phx_dcn_cursor.h"

void phxAgdcInstall();   // phxagdc.cpp: the AppleGraphicsDeviceControl that reports this panel (debug.phxagdc)
void phxAgdcRemove();
void phxHoldInit(IOService *fb, unsigned bootHoldSec);   // phxagdc.cpp: debug.phxfb_hold keeps this framebuffer (and so the GPU) busy

#define PFBLOG(fmt, ...) IOLog("PhxFB: " fmt "\n", ##__VA_ARGS__)

static int gAlias = 1;
SYSCTL_INT(_debug, OID_AUTO, phxfb_alias, CTLFLAG_RW | CTLFLAG_LOCKED, &gAlias, 0,
           "1 = frames are copied into the scan-out through its system-RAM address (the carve-out), 0 = through the GPU's BAR");
int gPhxZeroCopy = 0;
static SInt64 gZcFlips, gZcFaults, gZcFallbacks, gZcReuses, gZcTlbFlushes, gZcPendingWaits;
static int gZcLastStatus = 0;
static unsigned int gZcLastFmt = 0;
int gPhxHwCursor = 0;
static SInt64 gCurImages, gCurMoves, gCurErrors;
class PhxAMDFB;
static PhxAMDFB *gPhxFbInstance = nullptr;
static int phxfb_zerocopy_sysctl SYSCTL_HANDLER_ARGS;
static int phxfb_hwcursor_sysctl SYSCTL_HANDLER_ARGS;
SYSCTL_PROC(_debug, OID_AUTO, phxfb_zerocopy, CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_LOCKED, nullptr, 0,
            phxfb_zerocopy_sysctl, "I",
            "1 = allow opt-in DCN VMID flat-page-table scanout; 0 = immediate HOME return and CPU-copy fallback");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_zc_flips, CTLFLAG_RD | CTLFLAG_LOCKED, &gZcFlips, "DCN zero-copy scanout flips issued");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_zc_faults, CTLFLAG_RD | CTLFLAG_LOCKED, &gZcFaults, "DCN VM faults observed by zero-copy scanout");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_zc_fallbacks, CTLFLAG_RD | CTLFLAG_LOCKED, &gZcFallbacks, "zero-copy scanout requests refused");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_zc_reuses, CTLFLAG_RD | CTLFLAG_LOCKED, &gZcReuses, "DCN zero-copy VMID slots safely recycled via MMHUB TLB flush");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_zc_tlb_flushes, CTLFLAG_RD | CTLFLAG_LOCKED, &gZcTlbFlushes, "MMHUB ENG16 TLB invalidations completed for DCN zero-copy");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_zc_pending_waits, CTLFLAG_RD | CTLFLAG_LOCKED, &gZcPendingWaits, "DCN zero-copy flips that waited for a prior flip to latch");
SYSCTL_INT(_debug, OID_AUTO, phxfb_zc_last_status, CTLFLAG_RD | CTLFLAG_LOCKED, &gZcLastStatus, 0, "last zero-copy flip status");
SYSCTL_UINT(_debug, OID_AUTO, phxfb_zc_last_fmt, CTLFLAG_RD | CTLFLAG_LOCKED, &gZcLastFmt, 0, "last zero-copy request pixelFormat");
SYSCTL_PROC(_debug, OID_AUTO, phxfb_hwcursor, CTLTYPE_INT | CTLFLAG_RW | CTLFLAG_LOCKED, nullptr, 0,
            phxfb_hwcursor_sysctl, "I",
            "1 = enable opt-in DCN 3.1.4 hardware cursor while zero-copy is active; 0 = disable HW cursor (SW fallback)");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_hwcur_images, CTLFLAG_RD | CTLFLAG_LOCKED, &gCurImages, "DCN hardware cursor images programmed");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_hwcur_moves, CTLFLAG_RD | CTLFLAG_LOCKED, &gCurMoves, "DCN hardware cursor state updates");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_hwcur_errors, CTLFLAG_RD | CTLFLAG_LOCKED, &gCurErrors, "DCN hardware cursor fallback or programming errors");

// The VBL tick. XNU's timer coalescing moves a kernel deadline by up to an eighth of its delay, at most 1 ms, so a
// 120 Hz tick could land anywhere in the first millisecond after the vblank it stands for. The system-critical urgency
// that is never moved is not exported to kexts (thread_call_enter_delayed_with_leeway), so the tick is armed 1.5 ms
// early and re-armed for its deadline from there, each stage with an eighth of the previous slop, until less than
// 50 us remain (debug.phxfb_vbl_staged, 0 = one plain deadline). The lateness of each tick is summed for the
// measurements, and nvrm-accel.cpp times its presents against the last tick (gPhxVblLastAbs, gPhxFrameAbs).
static int gVblStaged = 1;
static SInt64 gVblN, gVblLateUsSum, gVblLateUsMax;
uint64_t gPhxVblLastAbs, gPhxFrameAbs;
volatile uint64_t gPhxVblSeq;   // ticks so far, counted before the handlers run: the display pipe completes on the next one
SYSCTL_INT(_debug, OID_AUTO, phxfb_vbl_staged, CTLFLAG_RW | CTLFLAG_LOCKED, &gVblStaged, 0,
           "1 = the VBL tick is armed early and re-armed until its deadline (little coalescing slop), 0 = one plain deadline");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_vbl_n, CTLFLAG_RD | CTLFLAG_LOCKED, &gVblN, "VBL ticks fired");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_vbl_late_us_sum, CTLFLAG_RW | CTLFLAG_LOCKED, &gVblLateUsSum, "microseconds the VBL ticks fired past their deadlines, summed");
SYSCTL_QUAD(_debug, OID_AUTO, phxfb_vbl_late_us_max, CTLFLAG_RW | CTLFLAG_LOCKED, &gVblLateUsMax, "the latest VBL tick, microseconds past its deadline (writable: 0 restarts it)");
// The panel's backlight is the display block's PWM (DCN 3.1.4 PWRSEQ0, segment 2 base 0x34c0): ACPI's _BCM only asks the
// GPU driver through ATIF (AFN7), and the firmware leaves the PWM on at full duty (period 4000, 12 bits). It is set as
// Linux's panel_cntl does without DMUB: lock the group, write the active count, unlock, wait for the pending update.
// tools/phxctl/phxbl does the same from user space. -phxbloff leaves the panel without a brightness control.
enum : uint32_t { kBlCntl = 0x34c0 + 0x2f19, kBlPeriod = 0x34c0 + 0x2f1b, kBlLock = 0x34c0 + 0x2f1c };
// The firmware runs both PWM generators, PWRSEQ0 and PWRSEQ1 (+0x6c), at full duty, and PWRSEQ0 alone left the panel's
// brightness as it was (2026-10-25: eDP DPCD 0x721 says the panel follows its PWM pin): both get the level.
static constexpr uint32_t kBlSeqs[] = { 0, 0x2f85 - 0x2f19 };
static constexpr uint32_t kBlMax = 1024;   // the brightness parameter's range
static IOService *phxBacklightCreate(PhxAMDFB *fb);

static struct sysctl_oid *const kFbOids[] = { &sysctl__debug_phxfb_alias, &sysctl__debug_phxfb_zerocopy,
                                              &sysctl__debug_phxfb_zc_flips, &sysctl__debug_phxfb_zc_faults,
                                              &sysctl__debug_phxfb_zc_fallbacks, &sysctl__debug_phxfb_zc_reuses,
                                              &sysctl__debug_phxfb_zc_tlb_flushes, &sysctl__debug_phxfb_zc_pending_waits,
                                              &sysctl__debug_phxfb_zc_last_status, &sysctl__debug_phxfb_zc_last_fmt,
                                              &sysctl__debug_phxfb_hwcursor, &sysctl__debug_phxfb_hwcur_images,
                                              &sysctl__debug_phxfb_hwcur_moves, &sysctl__debug_phxfb_hwcur_errors,
                                              &sysctl__debug_phxfb_vbl_staged,
                                              &sysctl__debug_phxfb_vbl_n, &sysctl__debug_phxfb_vbl_late_us_sum,
                                              &sysctl__debug_phxfb_vbl_late_us_max };
static bool gFbSysctl;

// The class name carries "AMD": CoreDisplay tells the GPU vendor from the framebuffer's class name (Intel, AMD, NVDA,
// AppleParavirt), and for any other name it turns IOPresentment off, which left the panel on the software compositor
// with the Metal compositor up for the accelerator (GetGPUVendorForFramebufferService -> 1, 2026-10-20).
class PhxAMDFB : public IOFramebuffer {
    OSDeclareDefaultStructors(PhxAMDFB)
    IOPCIDevice *fPCI = nullptr;
    IOMemoryMap *fSurfMap = nullptr;   // write-combined CPU view of the scan-out surface through the BAR
    // The same surface through its system-RAM address: the 780M's VRAM is a carve-out of system memory, and amdgpu maps
    // it there on APUs rather than through the BAR. Through the BAR a 2560x1600 frame took ~110 ms to copy (~7 fps, the
    // whole desktop lagged, 2026-10-20). This view comes out write-back although it asks for write-combined (frames
    // copied with plain stores stayed in the CPU cache: stripes), so the display pipe writes it with non-temporal stores.
    IOMemoryMap *fAliasMap = nullptr;
    IOMemoryMap *fMmio = nullptr;      // BAR5, for the backlight PWM
    IOLock *fZcLock = nullptr;
    IOService *fBacklight = nullptr;   // the brightness parameter handler, named "backlight"
    unsigned fAliasTries = 0;    // mapping/pixel verification attempts
    unsigned fAliasWaits = 0;    // metadata waits do not spend verification attempts
    static constexpr unsigned kAliasVerifyLimit = phx780m::kAliasVerifyLimit;
    static constexpr unsigned kAliasWaitLimit = phx780m::kAliasWaitLimit;
    volatile UInt32 fAliasBusy = 0;
    struct Irq { IOFBInterruptProc proc = nullptr; OSObject *target = nullptr; void *ref = nullptr; };
    Irq fVbl[4], fConnect;   // IOFramebuffer itself and, when it asks, IOAccelDisplayPipe each register a VBL handler
    IOTimerEventSource *fVblTimer = nullptr;
    IOWorkLoop *fVblWorkLoop = nullptr;
    uint64_t fVblNext = 0;
    volatile bool fStopping = false;
    bool fBeside = false;   // another framebuffer (the firmware's IONDRV one) already drives this GPU: not the console
    IOPhysicalAddress fBase = 0;
    uint32_t fWidth = 0, fHeight = 0, fRowBytes = 0;
    struct ZcSlot {
        OSObject *surface = nullptr;
        IOMemoryDescriptor *memory = nullptr;
        IOBufferMemoryDescriptor *pageTable = nullptr;
        uint64_t *pageTableKva = nullptr;
        uint64_t pageTablePhys = 0;
        uint32_t surfaceID = 0;
        uint32_t pixelFormat = 0;
        uint64_t lastUseSeq = 0;
        uint32_t expectedContext[phx::dcnzc::kContextFieldCount]{};
        bool prepared = false;
        bool active = false;
        bool contextReady = false;
        bool contextOwned = false;
    };
    ZcSlot fZcSlots[phx::dcnzc::kSlotCount]{};
    phx::dcnzc::ApertureSnapshot fZcAperture{};
    uint64_t fZcHomeAddr = 0;
    uint64_t fZcUseSeq = 0;
    uint32_t fZcOrigSysLow = 0, fZcOrigSysHigh = 0, fZcOrigL1Tlb = 0;
    uint32_t fZcOrigSurfCfg = 0, fZcOrigCnvcFmt = 0;
    uint32_t fZcVmidsConsumed = 0;
    int fZcFrontSlot = -1;
    bool fZcArmed = false, fZcTripped = false;
    IOBufferMemoryDescriptor *fCurBuf = nullptr;
    uint32_t *fCurKva = nullptr;
    uint64_t fCurPtes[phx::dcncur::kCursorTotalPages]{};
    uint32_t *fCurScratch = nullptr;
    uint32_t fCurBufIdx = 0;
    uint32_t fCurWidth = 0, fCurHeight = 0;
    uint32_t fCurPitchPixels = 0, fCurHwPitch = 0, fCurLpc = 0;
    int32_t fCurX = 0, fCurY = 0;
    bool fCurBufReady = false;
    bool fCurVisible = false, fCurHasImage = false, fCurHwEnabled = false, fCurTripped = false;
    bool fHiRes = false;
    static constexpr uint64_t kFrameNs = 16666667ull;   // 60 Hz, when the refresh cannot be measured
    uint64_t fFrameNs = kFrameNs;
    uint32_t fRefreshMilliHz = 60000, fHTotal = 0, fVTotal = 0;
    phx::PanelTiming fPanelTiming = {};
    bool fPanelTimingValid = false;
    uint16_t fPanelWidthMm = 0, fPanelHeightMm = 0;
    uintptr_t fGammaScale[3] = { 0x10000, 0x10000, 0x10000 };
    static constexpr unsigned kBootHoldSec = 120;   // the boot daemon releases it sooner (debug.phxfb_hold=0)
    // The accelerator is NullMoth's, written against an NVIDIA RM: it backs each IOAccel surface with "VRAM" from the
    // framebuffer (nvAllocVram) and a GPU address from the RM (nvGpuVaAlloc/Map). On the 780M nothing on the GPU reads
    // those surfaces -- the display pipe copies finished frames by CPU, and RADV keeps its own GPU addresses in
    // PhxBringup -- so VRAM here is physically contiguous system memory (the 780M has no other kind) and a GPU address
    // is a number from a private range that never enters a page table. Without them every surface_flush WindowServer
    // makes failed ("failed to alloc GART space"), 30 times a second, and no frame reached the panel (2026-10-20).
    static constexpr uint64_t kVaBase = 0x100000000000ull, kVaSize = 1ull << 40, kVramCap = 1024ull << 20;
    IORangeAllocator *fVa = nullptr;
    volatile SInt64 fVramBytes = 0;
    volatile SInt32 fHandles = 0;
    unsigned fRmLogged = 0;
    // VRAM comes from one physically contiguous pool taken at start, while memory is still unfragmented: allocated one
    // by one, a 16 MB surface found no contiguous run hours into a session, and when WindowServer re-allocated its frame
    // on display wake the panel kept the frame from before the display slept (2026-10-21). An allocation is a
    // sub-descriptor of the pool (its handle); past the pool each one is contiguous memory of its own, as before.
    static constexpr uint64_t kPoolTry[3] = { 512ull << 20, 256ull << 20, 128ull << 20 };
    IOBufferMemoryDescriptor *fPool = nullptr;
    IORangeAllocator *fPoolRange = nullptr;
    uint8_t *fPoolKva = nullptr;
    uint64_t fPoolPhys = 0, fPoolBytes = 0;

    volatile uint32_t *zcRegs() const {
        return fMmio ? reinterpret_cast<volatile uint32_t *>(fMmio->getVirtualAddress()) : nullptr;
    }

    uint32_t zcRead(uint32_t reg) const {
        volatile uint32_t *regs = zcRegs();
        return regs && (static_cast<uint64_t>(reg) + 1) * sizeof(uint32_t) <= fMmio->getLength() ? regs[reg] : UINT32_MAX;
    }

    bool zcWrite(uint32_t reg, uint32_t value) {
        volatile uint32_t *regs = zcRegs();
        if (!regs || (static_cast<uint64_t>(reg) + 1) * sizeof(uint32_t) > fMmio->getLength()) return false;
        regs[reg] = value;
        __asm__ __volatile__("mfence" ::: "memory");
        return true;
    }

    uint64_t zcAddress(uint32_t lowReg, uint32_t highReg) const {
        const uint32_t high = zcRead(highReg), low = zcRead(lowReg);
        return (high == UINT32_MAX || low == UINT32_MAX) ? UINT64_MAX :
            (static_cast<uint64_t>(high & 0xffffu) << 32) | low;
    }

    bool zcHubpPeersIdle() const {
        return fMmio && fMmio->getLength() >= phx::dcnzc::kMinMmioBytes &&
            phx::dcnzc::hubpPeersIdle([this](uint32_t reg) { return zcRead(reg); });
    }

    bool zcLockOtg(bool lock) {
        if (lock) {
            const uint32_t state = zcRead(phx::dcnzc::kRegOtgMasterLock);
            const uint32_t flip = zcRead(phx::dcnzc::kRegHubpFlipCtl);
            if (state == UINT32_MAX || flip == UINT32_MAX ||
                (state & phx::dcnzc::kOtgLockReqStatus) || (flip & phx::dcnzc::kFlipUpdateLocked)) return false;
        }
        if (!zcWrite(phx::dcnzc::kRegOtgMasterLock, lock ? 1u : 0u)) return false;
        for (unsigned attempt = 0; attempt < 100; ++attempt) {
            const uint32_t state = zcRead(phx::dcnzc::kRegOtgMasterLock);
            const uint32_t flip = zcRead(phx::dcnzc::kRegHubpFlipCtl);
            if (state == UINT32_MAX || flip == UINT32_MAX) return false;
            const bool registerLocked = (state & phx::dcnzc::kOtgLockReqStatus) ==
                (lock ? phx::dcnzc::kOtgLockReqStatus : 0);
            const bool hubpLocked = bool(flip & phx::dcnzc::kFlipUpdateLocked) == lock;
            if (registerLocked && hubpLocked) return true;
            IODelay(10);
        }
        if (lock) (void)zcWrite(phx::dcnzc::kRegOtgMasterLock, 0);
        return false;
    }

    bool zcFlushMmhubTlb(uint32_t vmid) {
        using namespace phx::dcnzc;
        if (vmid < kFirstVmid || vmid >= kFirstVmid + kSlotCount) return false;
        if (!fMmio || fMmio->getLength() < kMinMmioBytes) return false;
        bool gotSem = false;
        for (unsigned attempt = 0; attempt < 200; ++attempt) {
            const uint32_t sem = zcRead(kRegMmhubInvEng16Sem);
            if (sem == UINT32_MAX) return false;
            if (sem & 1u) {
                gotSem = true;
                break;
            }
            IODelay(5);
        }
        if (!gotSem) return false;
        const uint32_t mask = 1u << (vmid & 0xfu);
        bool acked = false;
        if (zcWrite(kRegMmhubInvEng16Req, mmhubInvalidateReq(vmid))) {
            for (unsigned attempt = 0; attempt < 500; ++attempt) {
                const uint32_t ack = zcRead(kRegMmhubInvEng16Ack);
                if (ack == UINT32_MAX) break;
                if (ack & mask) {
                    acked = true;
                    break;
                }
                IODelay(2);
            }
        }
        (void)zcWrite(kRegMmhubInvEng16Sem, 0u);
        if (!acked) return false;
        const uint32_t cid2 = zcRead(kRegMmhubL2ReservedCid2);
        if (cid2 == UINT32_MAX || !zcWrite(kRegMmhubL2ReservedCid2, cid2 | kMmhubL2PrivateInvBit))
            return false;
        (void)zcRead(kRegMmhubL2ReservedCid2);
        OSAddAtomic64(1, &gZcTlbFlushes);
        return true;
    }

    bool zcFlipTo(uint32_t vmid, uint64_t address, uint32_t dcnFormat) {
        if (!zcHubpPeersIdle()) return false;
        if (!phx::dcnzc::supportedDcnFormat(dcnFormat)) return false;
        const uint32_t priorFlip = zcRead(phx::dcnzc::kRegHubpFlipCtl);
        const uint32_t priorVmid = zcRead(phx::dcnzc::kRegHubpVmid0);
        const uint64_t priorProgrammed = zcAddress(phx::dcnzc::kRegHubpPrimLo, phx::dcnzc::kRegHubpPrimHi);
        const uint64_t priorEarliest = zcAddress(phx::dcnzc::kRegHubpEarliestLo, phx::dcnzc::kRegHubpEarliestHi);
        if (priorFlip == UINT32_MAX || priorVmid == UINT32_MAX || priorProgrammed == UINT64_MAX ||
            priorEarliest == UINT64_MAX ||
            (priorFlip & (phx::dcnzc::kFlipPending | phx::dcnzc::kFlipUpdateLocked)) ||
            priorProgrammed != priorEarliest || !zcLockOtg(true)) return false;
        const bool baselineCurrent = zcHubpPeersIdle() && zcApertureCurrent() &&
            phx::dcnzc::hubpGeometryReady(fWidth, fHeight, fRowBytes,
                [this](uint32_t reg) { return zcRead(reg); }, true) &&
            zcRead(phx::dcnzc::kRegHubpVmid0) == priorVmid &&
            zcAddress(phx::dcnzc::kRegHubpPrimLo, phx::dcnzc::kRegHubpPrimHi) == priorProgrammed &&
            zcAddress(phx::dcnzc::kRegHubpEarliestLo, phx::dcnzc::kRegHubpEarliestHi) == priorEarliest;
        uint32_t vmidReg = zcRead(phx::dcnzc::kRegHubpVmid0);
        const uint32_t surfCfg = zcRead(phx::dcnzc::kRegHubpSurfaceConfig);
        const uint32_t cnvcFmt = zcRead(phx::dcnzc::kRegCnvcPixelFormat);
        bool fmtOk = surfCfg != UINT32_MAX && cnvcFmt != UINT32_MAX;
        if (fmtOk && (surfCfg & phx::dcnzc::kFormatMask) != dcnFormat)
            fmtOk = zcWrite(phx::dcnzc::kRegHubpSurfaceConfig, (surfCfg & ~phx::dcnzc::kFormatMask) | dcnFormat);
        if (fmtOk && (cnvcFmt & phx::dcnzc::kFormatMask) != dcnFormat)
            fmtOk = zcWrite(phx::dcnzc::kRegCnvcPixelFormat, (cnvcFmt & ~phx::dcnzc::kFormatMask) | dcnFormat);
        bool ok = baselineCurrent && fmtOk && vmidReg != UINT32_MAX &&
            zcWrite(phx::dcnzc::kRegHubpVmid0, (vmidReg & ~0xfu) | (vmid & 0xfu)) &&
            zcWrite(phx::dcnzc::kRegHubpPrimHi, static_cast<uint32_t>(address >> 32)) &&
            zcWrite(phx::dcnzc::kRegHubpPrimLo, static_cast<uint32_t>(address));
        if (ok) curSyncInOtgLock(vmid);
        const bool unlocked = zcLockOtg(false);
        return ok && unlocked;
    }

    void curFlushSlot(uint32_t bufIdx) {
        uint8_t *base = reinterpret_cast<uint8_t *>(fCurKva) +
            static_cast<uint64_t>(bufIdx % phx::dcncur::kCursorBufferCount) * phx::dcncur::kCursorSlotBytes;
        for (uint64_t offset = 0; offset < phx::dcncur::kCursorSlotBytes; offset += 64)
            __asm__ __volatile__("clflush (%0)" :: "r"(base + offset) : "memory");
        __asm__ __volatile__("mfence" ::: "memory");
    }

    void curInitBuffer() {
        if (fCurBuf || !fMmio || fMmio->getLength() < phx::dcnzc::kMinMmioBytes) return;
        IOBufferMemoryDescriptor *buffer = IOBufferMemoryDescriptor::inTaskWithPhysicalMask(
            kernel_task, kIODirectionInOut | kIOMemoryPhysicallyContiguous,
            phx::dcncur::kCursorTotalBytes, phx::dcnzc::kPhysPageMask);
        if (!buffer || buffer->prepare() != kIOReturnSuccess) {
            OSSafeReleaseNULL(buffer);
            return;
        }
        uint32_t *kva = static_cast<uint32_t *>(buffer->getBytesNoCopy());
        if (!kva) {
            buffer->complete();
            buffer->release();
            return;
        }
        bool pagesOk = true;
        for (uint32_t page = 0; page < phx::dcncur::kCursorTotalPages; ++page) {
            IOByteCount segLen = 0;
            const uint64_t phys = buffer->getPhysicalSegment(
                static_cast<uint64_t>(page) * phx::dcnzc::kPageBytes, &segLen, kIOMemoryMapperNone);
            uint64_t pte = 0;
            if (segLen < phx::dcnzc::kPageBytes || !phx::dcnzc::encodeLeafPte(phys, pte)) {
                pagesOk = false;
                break;
            }
            fCurPtes[page] = pte;
        }
        if (!pagesOk) {
            bzero(fCurPtes, sizeof(fCurPtes));
            buffer->complete();
            buffer->release();
            return;
        }
        uint32_t *scratch = static_cast<uint32_t *>(IOMalloc(phx::dcncur::kCursorSlotBytes));
        if (!scratch) {
            bzero(fCurPtes, sizeof(fCurPtes));
            buffer->complete();
            buffer->release();
            return;
        }
        fCurBuf = buffer;
        fCurKva = kva;
        fCurScratch = scratch;
        bzero(fCurKva, phx::dcncur::kCursorTotalBytes);
        curFlushSlot(0);
        curFlushSlot(1);
        fCurBufReady = true;
    }

    void curFreeBuffer() {
        fCurBufReady = false;
        fCurHasImage = false;
        fCurHwEnabled = false;
        if (fCurScratch) {
            IOFree(fCurScratch, phx::dcncur::kCursorSlotBytes);
            fCurScratch = nullptr;
        }
        if (fCurBuf) {
            fCurBuf->complete();
            fCurBuf->release();
            fCurBuf = nullptr;
        }
        fCurKva = nullptr;
        bzero(fCurPtes, sizeof(fCurPtes));
    }

    void curWriteDisabledInLock() {
        using namespace phx::dcncur;
        const uint32_t ctl = zcRead(kRegCursorControl);
        if (ctl != UINT32_MAX && (ctl & kCurCtlEnable))
            (void)zcWrite(kRegCursorControl, ctl & ~kCurCtlEnable);
        const uint32_t cnvc = zcRead(kRegCnvcCur0Control);
        if (cnvc != UINT32_MAX && (cnvc & kCnvcCur0Enable))
            (void)zcWrite(kRegCnvcCur0Control, cnvc & ~kCnvcCur0Enable);
        fCurHwEnabled = false;
    }

    void curProgramActiveInLock(uint32_t slotIndex, uint32_t bufIdx) {
        using namespace phx::dcncur;
        const uint32_t pixelClkKhz = fPanelTimingValid ? static_cast<uint32_t>(fPanelTiming.pixelClock / 1000ull) : 0u;
        const PositionRegs pos = computeCursorPosition(
            fCurX, fCurY, fCurVisible, fCurWidth, fCurHeight, fWidth, fHeight, 100000u, pixelClkKhz);
        const uint32_t pwr = zcRead(kRegCursorMemPwrCtrl);
        if (pwr != UINT32_MAX && (pwr & kCurMemPwrForceMask))
            (void)zcWrite(kRegCursorMemPwrCtrl, pwr & ~kCurMemPwrForceMask);
        const uint64_t va = cursorVaForSlot(slotIndex, bufIdx);
        const uint32_t priorCtl = zcRead(kRegCursorControl);
        const uint32_t priorCnvc = zcRead(kRegCnvcCur0Control);
        if (priorCtl == UINT32_MAX || priorCnvc == UINT32_MAX) {
            fCurTripped = true;
            OSAddAtomic64(1, &gCurErrors);
            curWriteDisabledInLock();
            return;
        }
        bool ok = true;
        ok &= zcWrite(kRegCursorSurfAddrHi, static_cast<uint32_t>(va >> 32));
        ok &= zcWrite(kRegCursorSurfAddrLo, static_cast<uint32_t>(va));
        ok &= zcWrite(kRegCursorSize, encodeCursorSize(fCurWidth, fCurHeight));
        ok &= zcWrite(kRegCursorSettings, kCurSettingsChunkHdlAdjust);
        if (pos.visible) {
            ok &= zcWrite(kRegCursorPosition, pos.positionReg);
            ok &= zcWrite(kRegCursorHotSpot, pos.hotSpotReg);
            ok &= zcWrite(kRegCursorDstOffset, pos.dstOffsetReg);
        }
        ok &= zcWrite(kRegCursorControl, encodeCursorControl(
            priorCtl, pos.visible, kCursorModeColorUnPreMultAlpha, fCurHwPitch, fCurLpc));
        ok &= zcWrite(kRegCnvcCur0Control, encodeCnvcCursorControl(
            priorCnvc, pos.visible, kCursorModeColorUnPreMultAlpha));
        if (!ok) {
            fCurTripped = true;
            OSAddAtomic64(1, &gCurErrors);
            curWriteDisabledInLock();
            return;
        }
        fCurHwEnabled = pos.visible;
    }

    void curSyncInOtgLock(uint32_t vmid) {
        if (vmid >= phx::dcnzc::kFirstVmid &&
            vmid < phx::dcnzc::kFirstVmid + phx::dcnzc::kSlotCount &&
            fCurBufReady && fCurHasImage && !fCurTripped &&
            __atomic_load_n(&gPhxHwCursor, __ATOMIC_ACQUIRE)) {
            curProgramActiveInLock(vmid - phx::dcnzc::kFirstVmid, fCurBufIdx);
        } else if (fCurHwEnabled) {
            curWriteDisabledInLock();
        }
    }

    void curDisableLocked() {
        if (!fMmio || fMmio->getLength() < phx::dcnzc::kMinMmioBytes) {
            fCurHwEnabled = false;
            return;
        }
        if (!fCurHwEnabled) {
            const uint32_t ctl = zcRead(phx::dcncur::kRegCursorControl);
            const uint32_t cnvc = zcRead(phx::dcncur::kRegCnvcCur0Control);
            if ((ctl == UINT32_MAX || !(ctl & phx::dcncur::kCurCtlEnable)) &&
                (cnvc == UINT32_MAX || !(cnvc & phx::dcncur::kCnvcCur0Enable)))
                return;
        }
        if (zcLockOtg(true)) {
            curWriteDisabledInLock();
            (void)zcLockOtg(false);
        } else {
            curWriteDisabledInLock();
        }
    }

    void curDisableImmediate() {
        if (!fZcLock) return;
        IOLockLock(fZcLock);
        fCurHasImage = false;
        curDisableLocked();
        IOLockUnlock(fZcLock);
    }

    bool zcWaitLatched(uint32_t vmid, uint64_t address, uint32_t timeoutMs) {
        uint64_t deadline = 0;
        clock_interval_to_deadline(timeoutMs, kMillisecondScale, &deadline);
        uint32_t spins = 0;
        while (mach_absolute_time() < deadline) {
            const uint32_t flip = zcRead(phx::dcnzc::kRegHubpFlipCtl);
            const uint32_t vmidReg = zcRead(phx::dcnzc::kRegHubpVmid0);
            const uint64_t programmed = zcAddress(phx::dcnzc::kRegHubpPrimLo, phx::dcnzc::kRegHubpPrimHi);
            const uint64_t earliest = zcAddress(phx::dcnzc::kRegHubpEarliestLo, phx::dcnzc::kRegHubpEarliestHi);
            if (flip == UINT32_MAX || vmidReg == UINT32_MAX || programmed == UINT64_MAX ||
                earliest == UINT64_MAX)
                return false;
            if (!(flip & (phx::dcnzc::kFlipPending | phx::dcnzc::kFlipUpdateLocked)) &&
                (vmidReg & 0xfu) == vmid &&
                programmed == address && earliest == address)
                return true;
            if (spins++ < 5) IODelay(100);
            else IOSleep(1);
        }
        return false;
    }

    bool zcWaitCurrentLatched(uint32_t timeoutMs) {
        uint64_t deadline = 0;
        clock_interval_to_deadline(timeoutMs, kMillisecondScale, &deadline);
        uint32_t spins = 0;
        while (mach_absolute_time() < deadline) {
            const uint32_t flip = zcRead(phx::dcnzc::kRegHubpFlipCtl);
            const uint64_t programmed = zcAddress(phx::dcnzc::kRegHubpPrimLo, phx::dcnzc::kRegHubpPrimHi);
            const uint64_t earliest = zcAddress(phx::dcnzc::kRegHubpEarliestLo, phx::dcnzc::kRegHubpEarliestHi);
            if (flip == UINT32_MAX || programmed == UINT64_MAX || earliest == UINT64_MAX)
                return false;
            if (!(flip & (phx::dcnzc::kFlipPending | phx::dcnzc::kFlipUpdateLocked)) &&
                programmed == earliest) return true;
            if (spins++ < 5) IODelay(100);
            else IOSleep(1);
        }
        return false;
    }

    void zcFlushTable(ZcSlot &slot) {
        const uint64_t bytes = phx::dcnzc::kPageTableBytes;
        for (uint64_t offset = 0; offset < bytes; offset += 64)
            __asm__ __volatile__("clflush (%0)" :: "r"(reinterpret_cast<uint8_t *>(slot.pageTableKva) + offset) : "memory");
        __asm__ __volatile__("mfence" ::: "memory");
    }

    bool zcEnsurePageTable(ZcSlot &slot) {
        if (slot.pageTable && slot.pageTableKva && slot.pageTablePhys) return true;
        IOBufferMemoryDescriptor *buffer = IOBufferMemoryDescriptor::inTaskWithPhysicalMask(
            kernel_task, kIODirectionInOut | kIOMemoryPhysicallyContiguous, phx::dcnzc::kPageTableBytes,
            phx::dcnzc::kPhysPageMask);
        if (!buffer || buffer->prepare() != kIOReturnSuccess) {
            OSSafeReleaseNULL(buffer);
            return false;
        }
        const uint64_t phys = buffer->getPhysicalSegment(0, nullptr, kIOMemoryMapperNone);
        if (!phx::dcnzc::validPhysPage(phys) || !buffer->getBytesNoCopy()) {
            buffer->complete();
            buffer->release();
            return false;
        }
        slot.pageTable = buffer;
        slot.pageTableKva = static_cast<uint64_t *>(buffer->getBytesNoCopy());
        slot.pageTablePhys = phys;
        bzero(slot.pageTableKva, phx::dcnzc::kPageTableBytes);
        zcFlushTable(slot);
        return true;
    }

    bool zcContextFields(uint32_t vmid, uint32_t fields[phx::dcnzc::kContextFieldCount]) const {
        const uint32_t base = phx::dcnzc::vmCtxBase(vmid);
        for (uint32_t field = 0; field < phx::dcnzc::kContextFieldCount; ++field) {
            fields[field] = zcRead(base + field);
            if (fields[field] == UINT32_MAX) return false;
        }
        return true;
    }

    bool zcClearContext(uint32_t vmid, ZcSlot &slot) {
        if (!slot.contextOwned) return true;
        uint32_t current[phx::dcnzc::kContextFieldCount]{};
        if (!zcContextFields(vmid, current) ||
            !phx::dcnzc::contextMatchesOwnedState(slot.expectedContext, current)) {
            slot.active = false;
            slot.contextReady = false;
            return false;
        }
        const uint32_t base = phx::dcnzc::vmCtxBase(vmid);
        bool writesOk = true;
        writesOk &= zcWrite(base + 3, 0);
        writesOk &= zcWrite(base + 4, 0);
        writesOk &= zcWrite(base + 5, 0);
        writesOk &= zcWrite(base + 6, 0);
        writesOk &= zcWrite(base + 0, 0);
        writesOk &= zcWrite(base + 1, 0);
        writesOk &= zcWrite(base + 2, 0);
        if (!writesOk || !zcContextFields(vmid, current) ||
            !phx::dcnzc::contextFieldsClear(current)) {
            slot.active = false;
            slot.contextReady = false;
            return false;
        }
        if (!zcFlushMmhubTlb(vmid)) {
            slot.active = false;
            slot.contextReady = false;
            return false;
        }
        slot.contextOwned = false;
        slot.contextReady = false;
        return true;
    }

    bool zcProgramContext(uint32_t vmid, uint64_t vaBase, uint32_t pageCount, uint64_t ptPhys, ZcSlot &slot) {
        uint64_t root = 0;
        if (!phx::dcnzc::encodeRootEntry(ptPhys, root) || !pageCount || pageCount > phx::dcnzc::kMaxPages) return false;
        const uint64_t firstPage = vaBase / phx::dcnzc::kPageBytes;
        const uint64_t lastPage = firstPage + pageCount - 1;
        const uint32_t base = phx::dcnzc::vmCtxBase(vmid);
        slot.expectedContext[0] = 0;
        slot.expectedContext[1] = static_cast<uint32_t>(root >> 32);
        slot.expectedContext[2] = static_cast<uint32_t>(root);
        slot.expectedContext[3] = static_cast<uint32_t>(firstPage >> 32);
        slot.expectedContext[4] = static_cast<uint32_t>(firstPage);
        slot.expectedContext[5] = static_cast<uint32_t>(lastPage >> 32);
        slot.expectedContext[6] = static_cast<uint32_t>(lastPage);
        uint32_t current[phx::dcnzc::kContextFieldCount]{};
        if (!zcContextFields(vmid, current) || !phx::dcnzc::contextFieldsClear(current)) return false;
        (void)zcRecordVmidUsed(vmid);
        slot.contextOwned = true;
        if (!zcWrite(base + 3, static_cast<uint32_t>(firstPage >> 32)) ||
            !zcWrite(base + 4, slot.expectedContext[4]) ||
            !zcWrite(base + 5, slot.expectedContext[5]) ||
            !zcWrite(base + 6, slot.expectedContext[6]) ||
            !zcWrite(base + 0, 0) ||
            !zcWrite(base + 1, slot.expectedContext[1])) return false;
        if (!zcContextFields(vmid, current) ||
            !phx::dcnzc::contextMatchesOwnedState(slot.expectedContext, current) || current[2] != 0 ||
            !zcWrite(base + 2, slot.expectedContext[2])) return false;
        for (unsigned attempt = 0; attempt < 1000; ++attempt) {
            const uint32_t ready = zcRead(base + 2);
            if (ready == UINT32_MAX) return false;
            if (ready == slot.expectedContext[2])
                return zcContextFields(vmid, current) &&
                    phx::dcnzc::contextMatchesExactState(slot.expectedContext, current) &&
                    zcFlushMmhubTlb(vmid);
            IODelay(10);
        }
        return false;
    }

    bool zcRestoreAperture() {
        return zcWrite(phx::dcnzc::kRegHubpL1TlbCntl, fZcOrigL1Tlb) &&
            zcWrite(phx::dcnzc::kRegHubpSysAperLow, fZcOrigSysLow) &&
            zcWrite(phx::dcnzc::kRegHubpSysAperHigh, fZcOrigSysHigh) &&
            zcRead(phx::dcnzc::kRegHubpL1TlbCntl) == fZcOrigL1Tlb &&
            zcRead(phx::dcnzc::kRegHubpSysAperLow) == fZcOrigSysLow &&
            zcRead(phx::dcnzc::kRegHubpSysAperHigh) == fZcOrigSysHigh;
    }

    bool zcRecordVmidUsed(uint32_t vmid) {
        if (vmid < phx::dcnzc::kFirstVmid || vmid >= phx::dcnzc::kFirstVmid + phx::dcnzc::kSlotCount)
            return false;
        const uint32_t slotIndex = vmid - phx::dcnzc::kFirstVmid;
        const uint32_t consumed = fZcVmidsConsumed | (1u << slotIndex);
        if (consumed != fZcVmidsConsumed && fPCI)
            (void)fPCI->setProperty("PhxDcnZeroCopyVmidsConsumed", consumed, 32);
        fZcVmidsConsumed = consumed;
        return true;
    }

    void zcReleaseSurface(ZcSlot &slot) {
        if (slot.memory) {
            if (slot.prepared) slot.memory->complete(kIODirectionOut);
            slot.memory->release();
        }
        if (slot.surface) slot.surface->release();
        slot.memory = nullptr;
        slot.surface = nullptr;
        slot.surfaceID = 0;
        slot.pixelFormat = 0;
        slot.lastUseSeq = 0;
        slot.prepared = false;
        slot.active = false;
        slot.contextReady = false;
        slot.contextOwned = false;
        bzero(slot.expectedContext, sizeof(slot.expectedContext));
    }

    IOReturn zcHomeLocked(bool teardownAll) {
        if (!fZcArmed) return kIOReturnSuccess;
        curDisableLocked();
        const uint32_t fault = zcRead(phx::dcnzc::kRegVmFaultStatus);
        if ((fault == UINT32_MAX || (fault & 0xffffu) != 0) && !fZcTripped) {
            fZcTripped = true;
            OSAddAtomic64(1, &gZcFaults);
        }
        const uint32_t vmid = zcRead(phx::dcnzc::kRegHubpVmid0);
        const uint64_t current = zcAddress(phx::dcnzc::kRegHubpPrimLo, phx::dcnzc::kRegHubpPrimHi);
        if (vmid == UINT32_MAX || current == UINT64_MAX) return kIOReturnNotReady;
        const uint32_t homeFmt = fZcOrigSurfCfg & phx::dcnzc::kFormatMask;
        const uint32_t liveFmt = zcRead(phx::dcnzc::kRegHubpSurfaceConfig) & phx::dcnzc::kFormatMask;
        if ((vmid & 0xfu) != 0 || current != fZcHomeAddr || liveFmt != homeFmt) {
            if (!zcWaitCurrentLatched(50)) return kIOReturnBusy;
            if (!zcFlipTo(0, fZcHomeAddr, homeFmt) || !zcWaitLatched(0, fZcHomeAddr, 50)) return kIOReturnBusy;
        } else if (!zcWaitLatched(0, fZcHomeAddr, 50)) {
            return kIOReturnBusy;
        }
        fZcFrontSlot = -1;
        if (!teardownAll) return kIOReturnSuccess;
        bool contextsCleared = true;
        for (uint32_t index = 0; index < phx::dcnzc::kSlotCount; ++index) {
            ZcSlot &slot = fZcSlots[index];
            if (slot.contextOwned && !zcClearContext(phx::dcnzc::kFirstVmid + index, slot)) {
                contextsCleared = false;
                continue;
            }
            zcReleaseSurface(slot);
        }
        if (!contextsCleared) return kIOReturnNotReady;
        if (!zcRestoreAperture()) return kIOReturnNotReady;
        fZcArmed = false;
        fZcHomeAddr = 0;
        return kIOReturnSuccess;
    }

    IOReturn zcHome(bool teardownAll) {
        if (!fZcLock) return kIOReturnNotReady;
        IOLockLock(fZcLock);
        IOReturn result = zcHomeLocked(teardownAll);
        IOLockUnlock(fZcLock);
        return result;
    }

    bool zcArm() {
        if (fZcArmed) return true;
        using namespace phx::dcnzc;
        if (!fMmio || fMmio->getLength() < kMinMmioBytes) return false;
        const uint32_t fault = zcRead(kRegVmFaultStatus);
        const uint32_t vmidReg = zcRead(kRegHubpVmid0);
        const uint32_t sysLow = zcRead(kRegHubpSysAperLow), sysHigh = zcRead(kRegHubpSysAperHigh);
        const uint32_t l1 = zcRead(kRegHubpL1TlbCntl);
        const uint32_t surfCfg = zcRead(kRegHubpSurfaceConfig);
        const uint32_t cnvcFmt = zcRead(kRegCnvcPixelFormat);
        const uint32_t fbBase = zcRead(kRegFbBase), fbTop = zcRead(kRegFbTop);
        const uint32_t agpBot = zcRead(kRegAgpBot), agpTop = zcRead(kRegAgpTop);
        const uint64_t address = zcAddress(kRegHubpPrimLo, kRegHubpPrimHi);
        const uint64_t earliest = zcAddress(kRegHubpEarliestLo, kRegHubpEarliestHi);
        const uint64_t bytes = round_page_64(static_cast<uint64_t>(fRowBytes) * fHeight);
        if (fault == UINT32_MAX || (fault & 0xffffu) != 0 || vmidReg == UINT32_MAX || (vmidReg & 0xfu) != 0 || address == UINT64_MAX ||
            earliest != address || !zcHubpPeersIdle() ||
            fbBase == UINT32_MAX || fbTop == UINT32_MAX || agpBot == UINT32_MAX || agpTop == UINT32_MAX ||
            sysLow == UINT32_MAX || sysHigh == UINT32_MAX || l1 == UINT32_MAX ||
            surfCfg == UINT32_MAX || cnvcFmt == UINT32_MAX ||
            !addressInFbAperture(address, bytes, {fbBase, fbTop, agpBot, agpTop})) return false;
        for (uint32_t vmid = kFirstVmid; vmid < kFirstVmid + kSlotCount; ++vmid)
            for (uint32_t field = 0; field < kVmCtxStride; ++field)
                if (zcRead(vmCtxBase(vmid) + field) != 0) return false;
        for (uint32_t index = 0; index < kSlotCount; ++index)
            if (!slotVaClearOfApertures(slotVa(index), static_cast<uint64_t>(kMaxPages) * kPageBytes,
                                        {fbBase, fbTop, agpBot, agpTop})) return false;
        fZcHomeAddr = address;
        fZcAperture = {fbBase, fbTop, agpBot, agpTop};
        fZcOrigSysLow = sysLow;
        fZcOrigSysHigh = sysHigh;
        fZcOrigL1Tlb = l1;
        fZcOrigSurfCfg = surfCfg;
        fZcOrigCnvcFmt = cnvcFmt;
        uint32_t low = 0, high = 0;
        computeSystemApertureRegs(fZcAperture, low, high);
        fZcArmed = true;
        if (!zcWrite(kRegHubpSysAperLow, low) || !zcWrite(kRegHubpSysAperHigh, high) ||
            !zcWrite(kRegHubpL1TlbCntl, kL1TlbEnableSysMode3) ||
            !zcApertureCurrent()) {
            if (zcRestoreAperture()) {
                fZcArmed = false;
                fZcHomeAddr = 0;
            }
            return false;
        }
        return true;
    }

    bool zcApertureCurrent() const {
        uint32_t low = 0, high = 0;
        phx::dcnzc::computeSystemApertureRegs(fZcAperture, low, high);
        return zcRead(phx::dcnzc::kRegHubpSysAperLow) == low &&
            zcRead(phx::dcnzc::kRegHubpSysAperHigh) == high &&
            zcRead(phx::dcnzc::kRegHubpL1TlbCntl) == phx::dcnzc::kL1TlbEnableSysMode3;
    }

    int zcFindSlot(uint32_t surfaceID, IOMemoryDescriptor *memory, uint32_t pixelFormat) {
        for (uint32_t index = 0; index < phx::dcnzc::kSlotCount; ++index) {
            const ZcSlot &slot = fZcSlots[index];
            if (slot.active && slot.contextReady && slot.surfaceID == surfaceID &&
                slot.memory == memory && slot.pixelFormat == pixelFormat)
                return static_cast<int>(index);
        }
        return -1;
    }

    int zcAcquireSlot(PhxZeroCopyFlipRequest *request, IOMemoryDescriptor *memory, uint64_t bytes, uint32_t pageCount) {
        int selected = -1;
        bool recycled = false;
        for (uint32_t index = 0; index < phx::dcnzc::kSlotCount; ++index)
            if (!fZcSlots[index].surface && !fZcSlots[index].memory && !fZcSlots[index].contextOwned) {
                selected = static_cast<int>(index);
                break;
            }
        if (selected < 0) {
            // Recycle the least recently used non-front slot once current scanout has latched.
            if (!zcWaitCurrentLatched(50)) { request->status = phx::dcnzc::kLockTimeout; return -1; }
            const uint32_t liveVmid = zcRead(phx::dcnzc::kRegHubpVmid0);
            if (liveVmid == UINT32_MAX) { request->status = phx::dcnzc::kHwNotReady; return -1; }
            const uint32_t activeVmid = liveVmid & 0xfu;
            uint64_t oldestSeq = UINT64_MAX;
            for (uint32_t index = 0; index < phx::dcnzc::kSlotCount; ++index) {
                const uint32_t vmid = phx::dcnzc::kFirstVmid + index;
                if (static_cast<int>(index) == fZcFrontSlot || vmid == activeVmid) continue;
                if (fZcSlots[index].lastUseSeq < oldestSeq) {
                    oldestSeq = fZcSlots[index].lastUseSeq;
                    selected = static_cast<int>(index);
                }
            }
            if (selected < 0) { request->status = phx::dcnzc::kNoEvictableSlot; return -1; }
            const uint32_t victimVmid = phx::dcnzc::kFirstVmid + static_cast<uint32_t>(selected);
            ZcSlot &victim = fZcSlots[selected];
            if (victim.contextOwned && !zcClearContext(victimVmid, victim)) {
                request->status = phx::dcnzc::kCtxTimeout;
                return -1;
            }
            zcReleaseSurface(victim);
            if (victim.pageTableKva) {
                bzero(victim.pageTableKva, phx::dcnzc::kPageTableBytes);
                zcFlushTable(victim);
            }
            recycled = true;
        }
        if (selected < 0) { request->status = phx::dcnzc::kNoEvictableSlot; return -1; }
        if (!zcWaitCurrentLatched(50)) { request->status = phx::dcnzc::kLockTimeout; return -1; }
        ZcSlot &slot = fZcSlots[selected];
        if (!zcEnsurePageTable(slot)) { request->status = phx::dcnzc::kPrepareFailed; return -1; }
        if (!phx::dcnzc::validPhysPage(slot.pageTablePhys) ||
            slot.pageTablePhys > phx::dcnzc::kAddressLimit - phx::dcnzc::kPageTableBytes) {
            request->status = phx::dcnzc::kBadPhysPage;
            return -1;
        }
        OSObject *surface = static_cast<OSObject *>(request->surface);
        if (!surface || !memory) { request->status = phx::dcnzc::kBadArgs; return -1; }
        surface->retain();
        memory->retain();
        if (memory->prepare(kIODirectionOut) != kIOReturnSuccess) {
            memory->release();
            surface->release();
            request->status = phx::dcnzc::kPrepareFailed;
            return -1;
        }
        if (memory->getLength() < bytes) {
            memory->complete(kIODirectionOut);
            memory->release();
            surface->release();
            request->status = phx::dcnzc::kGeometryMismatch;
            return -1;
        }
        bzero(slot.pageTableKva, phx::dcnzc::kPageTableBytes);
        for (uint32_t page = 0; page < pageCount; ++page) {
            IOByteCount segmentLength = 0;
            const uint64_t phys = memory->getPhysicalSegment(static_cast<uint64_t>(page) * phx::dcnzc::kPageBytes,
                                                              &segmentLength, kIOMemoryMapperNone);
            uint64_t pte = 0;
            if (segmentLength < phx::dcnzc::kPageBytes ||
                !phx::dcnzc::encodeLeafPte(phys, pte)) {
                memory->complete(kIODirectionOut);
                memory->release();
                surface->release();
                bzero(slot.pageTableKva, phx::dcnzc::kPageTableBytes);
                zcFlushTable(slot);
                request->status = phx::dcnzc::kBadPhysPage;
                return -1;
            }
            slot.pageTableKva[page] = pte;
        }
        const uint32_t contextPages = fCurBufReady ? phx::dcnzc::kMaxPages : pageCount;
        if (fCurBufReady) {
            for (uint32_t curPage = 0; curPage < phx::dcncur::kCursorTotalPages; ++curPage)
                slot.pageTableKva[phx::dcncur::kCursorPageStart + curPage] = fCurPtes[curPage];
        }
        zcFlushTable(slot);
        const uint32_t vmid = phx::dcnzc::kFirstVmid + static_cast<uint32_t>(selected);
        slot.surface = surface;
        slot.memory = memory;
        slot.surfaceID = request->surfaceID;
        slot.pixelFormat = request->pixelFormat;
        slot.prepared = true;
        if (!zcProgramContext(vmid, phx::dcnzc::slotVa(static_cast<uint32_t>(selected)), contextPages,
                              slot.pageTablePhys, slot)) {
            if (slot.contextOwned && zcClearContext(vmid, slot)) {
                zcReleaseSurface(slot);
                bzero(slot.pageTableKva, phx::dcnzc::kPageTableBytes);
                zcFlushTable(slot);
            } else if (!slot.contextOwned) {
                zcReleaseSurface(slot);
                bzero(slot.pageTableKva, phx::dcnzc::kPageTableBytes);
                zcFlushTable(slot);
            }
            request->status = phx::dcnzc::kCtxTimeout;
            return -1;
        }
        slot.active = true;
        slot.contextReady = true;
        slot.lastUseSeq = ++fZcUseSeq;
        if (recycled) OSAddAtomic64(1, &gZcReuses);
        return selected;
    }

    IOReturn zcFlip(PhxZeroCopyFlipRequest *request) {
        if (!fZcLock) return kIOReturnNotReady;
        IOLockLock(fZcLock);
        if (!gPhxZeroCopy || fZcTripped || fStopping || !request ||
            request->version != PHX_FB_ABI_ZEROCOPY_VERSION || !request->surface || !request->memoryDescriptor) {
            gZcLastStatus = !gPhxZeroCopy ? phx::dcnzc::kDisabled : (fZcTripped ? phx::dcnzc::kTripped : phx::dcnzc::kBadArgs);
            IOReturn result = (fZcArmed && !gPhxZeroCopy) ? zcHomeLocked(true) : kIOReturnNotReady;
            IOLockUnlock(fZcLock);
            OSAddAtomic64(1, &gZcFallbacks);
            return result == kIOReturnSuccess ? kIOReturnNotOpen : result;
        }
        gZcLastFmt = request->pixelFormat;
        request->status = phx::dcnzc::kBadArgs;
        uint64_t bytes = 0;
        uint32_t pageCount = 0;
        if (!phx::dcnzc::validSurfaceRequest(request->pixelFormat, request->width, request->height,
                                             request->pitch, fWidth, fHeight, fRowBytes, bytes, pageCount)) {
            uint32_t dummyDcnFmt = 0;
            request->status = phx::dcnzc::dcnPixelFormatFor(request->pixelFormat, dummyDcnFmt) ?
                phx::dcnzc::kGeometryMismatch : phx::dcnzc::kUnsupportedFormat;
            gZcLastStatus = request->status;
            IOReturn home = zcHomeLocked(false);
            IOLockUnlock(fZcLock);
            OSAddAtomic64(1, &gZcFallbacks);
            return home == kIOReturnSuccess ? kIOReturnUnsupported : home;
        }
        const uint32_t fault = zcRead(phx::dcnzc::kRegVmFaultStatus);
        if (fault == UINT32_MAX || (fault & 0xffffu) != 0) {
            fZcTripped = true;
            gPhxZeroCopy = 0;
            OSAddAtomic64(1, &gZcFaults);
            request->status = phx::dcnzc::kVmFault;
            gZcLastStatus = request->status;
            IOReturn home = zcHomeLocked(true);
            IOLockUnlock(fZcLock);
            OSAddAtomic64(1, &gZcFallbacks);
            return home == kIOReturnSuccess ? kIOReturnError : home;
        }
        if (fZcArmed && !zcApertureCurrent()) {
            request->status = phx::dcnzc::kHwNotReady;
            gZcLastStatus = request->status;
            IOReturn home = zcHomeLocked(true);
            IOLockUnlock(fZcLock);
            OSAddAtomic64(1, &gZcFallbacks);
            return home == kIOReturnSuccess ? kIOReturnNotReady : home;
        }
        if (!phx::dcnzc::hubpGeometryReady(fWidth, fHeight, fRowBytes,
                [this](uint32_t reg) { return zcRead(reg); }, false, true) || !zcHubpPeersIdle()) {
            request->status = phx::dcnzc::kHwNotReady;
            gZcLastStatus = request->status;
            IOReturn home = zcHomeLocked(true);
            IOLockUnlock(fZcLock);
            OSAddAtomic64(1, &gZcFallbacks);
            return home == kIOReturnSuccess ? kIOReturnNotReady : home;
        }
        const uint32_t entryFlip = zcRead(phx::dcnzc::kRegHubpFlipCtl);
        if (entryFlip == UINT32_MAX) {
            request->status = phx::dcnzc::kHwNotReady;
            gZcLastStatus = request->status;
            IOReturn home = zcHomeLocked(true);
            IOLockUnlock(fZcLock);
            OSAddAtomic64(1, &gZcFallbacks);
            return home == kIOReturnSuccess ? kIOReturnNotReady : home;
        }
        if (entryFlip & phx::dcnzc::kFlipPending) {
            OSAddAtomic64(1, &gZcPendingWaits);
            if (!zcWaitCurrentLatched(25)) {
                request->status = phx::dcnzc::kHwNotReady;
                gZcLastStatus = request->status;
                IOReturn home = zcHomeLocked(false);
                IOLockUnlock(fZcLock);
                OSAddAtomic64(1, &gZcFallbacks);
                return home == kIOReturnSuccess ? kIOReturnNotReady : home;
            }
        }
        if (!zcArm()) {
            request->status = phx::dcnzc::kApertureConflict;
            gZcLastStatus = request->status;
            IOReturn home = fZcArmed ? zcHomeLocked(true) : kIOReturnSuccess;
            IOLockUnlock(fZcLock);
            OSAddAtomic64(1, &gZcFallbacks);
            return home == kIOReturnSuccess ? kIOReturnNotReady : home;
        }
        IOMemoryDescriptor *memory = static_cast<IOMemoryDescriptor *>(request->memoryDescriptor);
        uint32_t targetDcnFmt = phx::dcnzc::kDcnFormatArgb8888;
        (void)phx::dcnzc::dcnPixelFormatFor(request->pixelFormat, targetDcnFmt);
        int slotIndex = zcFindSlot(request->surfaceID, memory, request->pixelFormat);
        if (slotIndex < 0) slotIndex = zcAcquireSlot(request, memory, bytes, pageCount);
        if (slotIndex < 0) {
            if (request->status == phx::dcnzc::kBadArgs) request->status = phx::dcnzc::kNoEvictableSlot;
            gZcLastStatus = request->status;
            IOReturn home = zcHomeLocked(false);
            IOLockUnlock(fZcLock);
            OSAddAtomic64(1, &gZcFallbacks);
            return home == kIOReturnSuccess ? kIOReturnBusy : home;
        }
        const uint64_t address = phx::dcnzc::slotVa(static_cast<uint32_t>(slotIndex));
        const uint32_t vmid = phx::dcnzc::kFirstVmid + static_cast<uint32_t>(slotIndex);
        fZcSlots[slotIndex].lastUseSeq = ++fZcUseSeq;
        if (slotIndex != fZcFrontSlot || (zcRead(phx::dcnzc::kRegHubpVmid0) & 0xfu) != vmid ||
            zcAddress(phx::dcnzc::kRegHubpPrimLo, phx::dcnzc::kRegHubpPrimHi) != address ||
            (zcRead(phx::dcnzc::kRegHubpSurfaceConfig) & phx::dcnzc::kFormatMask) != targetDcnFmt) {
            if (!zcWaitCurrentLatched(50) || !zcFlipTo(vmid, address, targetDcnFmt)) {
                request->status = phx::dcnzc::kLockTimeout;
                gZcLastStatus = request->status;
                IOReturn home = zcHomeLocked(true);
                IOLockUnlock(fZcLock);
                OSAddAtomic64(1, &gZcFallbacks);
                return home == kIOReturnSuccess ? kIOReturnBusy : home;
            }
            fZcFrontSlot = slotIndex;
        }
        request->status = phx::dcnzc::kOk;
        gZcLastStatus = request->status;
        IOLockUnlock(fZcLock);
        OSAddAtomic64(1, &gZcFlips);
        return kIOReturnSuccess;
    }

    void zcCleanupPageTables() {
        for (uint32_t index = 0; index < phx::dcnzc::kSlotCount; ++index) {
            ZcSlot &slot = fZcSlots[index];
            if (slot.contextOwned || slot.memory || slot.surface) continue;
            if (slot.pageTable) {
                slot.pageTable->complete();
                slot.pageTable->release();
            }
            slot.pageTable = nullptr;
            slot.pageTableKva = nullptr;
            slot.pageTablePhys = 0;
        }
    }

    void poolInit() {
        for (uint64_t bytes : kPoolTry) {
            IOBufferMemoryDescriptor *b = IOBufferMemoryDescriptor::inTaskWithPhysicalMask(kernel_task,
                kIODirectionInOut | kIOMemoryPhysicallyContiguous, bytes, 0x0000FFFFFFFFF000ull);
            if (b && b->prepare() != kIOReturnSuccess) OSSafeReleaseNULL(b);
            if (!b) continue;
            fPoolRange = IORangeAllocator::withRange(bytes, PAGE_SIZE, 0, IORangeAllocator::kLocking);
            if (!fPoolRange) { b->complete(); b->release(); continue; }   // try a smaller pool
            fPool = b; fPoolKva = (uint8_t *)b->getBytesNoCopy(); fPoolBytes = bytes;
            fPoolPhys = b->getPhysicalSegment(0, nullptr, kIOMemoryMapperNone);
            PFBLOG("VRAM pool: %llu MB at phys 0x%llx", bytes >> 20, fPoolPhys);
            return;
        }
        PFBLOG("VRAM pool: no contiguous run of %llu MB or less, every allocation on its own", kPoolTry[2] >> 20);
    }
    void poolFree() {
        OSSafeReleaseNULL(fPoolRange);
        if (fPool) { fPool->complete(); OSSafeReleaseNULL(fPool); }
        fPoolKva = nullptr; fPoolPhys = fPoolBytes = 0;
    }
    bool poolAlloc(NVRMVramRequest *r, uint64_t bytes) {
        IORangeScalar off = 0;
        if (!fPoolRange || !fPoolRange->allocate(bytes, &off, PAGE_SIZE)) return false;
        IOSubMemoryDescriptor *s = IOSubMemoryDescriptor::withSubRange(fPool, off, bytes, kIODirectionInOut);
        if (!s) { fPoolRange->deallocate(off, bytes); return false; }
        bzero(fPoolKva + off, bytes);
        r->handle = s; r->kva = fPoolKva + off; r->actualSize = bytes; r->allocationCookie = 0;
        r->phys = fPoolPhys + off;
        return true;
    }

    IOReturn vramAlloc(NVRMVramRequest *r) {
        if (!r || r->version != NVRM_VRAM_ABI_VERSION || !r->size) return kIOReturnBadArgument;
        const uint64_t bytes = round_page_64(r->size);
        if ((uint64_t)OSAddAtomic64((SInt64)bytes, &fVramBytes) + bytes > kVramCap) {
            OSAddAtomic64(-(SInt64)bytes, &fVramBytes);
            if (fRmLogged++ < 16) PFBLOG("VRAM: %llu bytes refused, %lld already out (cap %llu)", bytes, fVramBytes, kVramCap);
            return kIOReturnNoMemory;
        }
        if (poolAlloc(r, bytes)) {
            r->mappedTotal = (uint64_t)fVramBytes;
            if (fRmLogged++ < 16) PFBLOG("VRAM: %llu bytes at phys 0x%llx from the pool (%lld out)", bytes, r->phys, fVramBytes);
            return kIOReturnSuccess;
        }
        IOBufferMemoryDescriptor *b = IOBufferMemoryDescriptor::inTaskWithPhysicalMask(kernel_task,
            kIODirectionInOut | kIOMemoryPhysicallyContiguous, bytes, 0x0000FFFFFFFFF000ull);
        if (b && b->prepare() != kIOReturnSuccess) OSSafeReleaseNULL(b);
        if (!b) {
            OSAddAtomic64(-(SInt64)bytes, &fVramBytes);
            if (fRmLogged++ < 16) PFBLOG("VRAM: no contiguous %llu bytes", bytes);
            return kIOReturnNoMemory;
        }
        bzero(b->getBytesNoCopy(), bytes);
        r->handle = b; r->kva = b->getBytesNoCopy(); r->actualSize = bytes; r->allocationCookie = 0;
        r->phys = b->getPhysicalSegment(0, nullptr, kIOMemoryMapperNone);
        r->mappedTotal = (uint64_t)fVramBytes;
        if (fRmLogged++ < 16) PFBLOG("VRAM: %llu bytes at phys 0x%llx (%lld out)", bytes, r->phys, fVramBytes);
        return kIOReturnSuccess;
    }
    IOReturn vramFree(NVRMVramRequest *r) {
        if (!r || r->version != NVRM_VRAM_ABI_VERSION) return kIOReturnBadArgument;
        if (IOSubMemoryDescriptor *s = OSDynamicCast(IOSubMemoryDescriptor, (OSObject *)r->handle)) {
            // Validate the handle as integers before the range allocator sees it: subtracting a pointer that need not
            // point into the pool is undefined, and the old `off + len` check could wrap. Either one could hand the
            // allocator a partial or foreign extent to release. Pool allocations are page-granular and never zero.
            const uint64_t kva = (uint64_t)(uintptr_t)r->kva, base = (uint64_t)(uintptr_t)fPoolKva;
            const uint64_t len = s->getLength();
            if (!fPoolRange || !fPoolKva || kva < base || !phx780m::poolReleaseValid(kva - base, len, fPoolBytes)) {
                PFBLOG("VRAM: release refused: kva 0x%llx len 0x%llx outside the %llu-byte pool", kva, len, fPoolBytes);
                return kIOReturnBadArgument;
            }
            const uint64_t off = kva - base;
            OSAddAtomic64(-(SInt64)len, &fVramBytes);
            fPoolRange->deallocate(off, len);
            s->release();
            return kIOReturnSuccess;
        }
        IOBufferMemoryDescriptor *b = OSDynamicCast(IOBufferMemoryDescriptor, (OSObject *)r->handle);
        if (!b) return kIOReturnBadArgument;
        OSAddAtomic64(-(SInt64)b->getLength(), &fVramBytes);
        b->complete(); b->release();
        return kIOReturnSuccess;
    }
    IOReturn rmCall(const OSSymbol *fn, void *p1) {
        if (fn->isEqualTo(NVRM_GPUVA_FN_HANDLES)) {
            NVRMRmHandles *h = (NVRMRmHandles *)p1;
            if (!h || h->version != NVRM_GPUVA_ABI_VERSION) return kIOReturnBadArgument;
            h->kapiDevice = this; h->hClient = 0x50480001; h->hDevice = 0x50480002; h->hSubDevice = 0x50480003;
            return kIOReturnSuccess;
        }
        NVRMGpuVaRequest *g = (NVRMGpuVaRequest *)p1;
        if (!g || g->version != NVRM_GPUVA_ABI_VERSION) return kIOReturnBadArgument;
        if (fn->isEqualTo(NVRM_GPUVA_FN_ALLOC)) {
            const uint64_t len = round_page_64(g->size);
            uint64_t align = g->align > PAGE_SIZE ? g->align : PAGE_SIZE;
            if (align & (align - 1)) align = PAGE_SIZE;
            IORangeScalar off = 0;
            if (!fVa || !len || !fVa->allocate(len, &off, align)) { g->status = 1; return kIOReturnNoSpace; }
            g->gpuva = kVaBase + off; g->hVirt = (unsigned)OSIncrementAtomic(&fHandles) + 1; g->status = 0;
            return kIOReturnSuccess;
        }
        if (fn->isEqualTo(NVRM_GPUVA_FN_MAP)) {   // nothing to map: no GPU work reaches these surfaces
            g->hMemory = (unsigned)OSIncrementAtomic(&fHandles) + 1; g->status = 0;
            return kIOReturnSuccess;
        }
        if (fn->isEqualTo(NVRM_GPUVA_FN_FREE)) {
            if (!(g->flags & NVRM_GPUVA_FLAG_UNMAP_ONLY) && fVa && g->gpuva >= kVaBase && g->gpuva - kVaBase < kVaSize)
                fVa->deallocate(g->gpuva - kVaBase, round_page_64(g->size));
            g->status = 0;
            return kIOReturnSuccess;
        }
        return kIOReturnUnsupported;
    }

    static void vblFire(OSObject *p0, IOTimerEventSource *) {
        PhxAMDFB *me = (PhxAMDFB *)p0;
        if (__atomic_load_n(&me->fStopping, __ATOMIC_ACQUIRE)) return;
        const uint64_t at = mach_absolute_time(), due = me->fVblNext;
        uint64_t near; nanoseconds_to_absolutetime(50000, &near);
        if (gVblStaged && due > at + near) { me->fVblTimer->wakeAtTime(due); return; }   // an early stage
        if (due && at > due) {
            uint64_t ns; absolutetime_to_nanoseconds(at - due, &ns);
            const SInt64 us = (SInt64)(ns / 1000);
            OSAddAtomic64(us, &gVblLateUsSum);
            if (us > gVblLateUsMax) gVblLateUsMax = us;
        }
        OSAddAtomic64(1, &gVblN);
        gPhxVblLastAbs = due ? due : at;   // the vblank this tick stands for
        __atomic_add_fetch(&gPhxVblSeq, 1, __ATOMIC_RELEASE);
        for (const Irq &q : me->fVbl) {
            const IOFBInterruptProc proc = __atomic_load_n(&q.proc, __ATOMIC_ACQUIRE);
            if (proc) proc(q.target, q.ref);
        }
        uint64_t period; nanoseconds_to_absolutetime(me->fFrameNs, &period);
        const uint64_t now = mach_absolute_time();
        me->fVblNext = (me->fVblNext && me->fVblNext + period > now) ? me->fVblNext + period : now + period;
        uint64_t lead; nanoseconds_to_absolutetime(1500000, &lead);
        me->fVblTimer->wakeAtTime(gVblStaged ? me->fVblNext - lead : me->fVblNext);
    }

    static IOReturn vblRetire(OSObject *owner, void *, void *, void *, void *) {
        PhxAMDFB *me = (PhxAMDFB *)owner;
        // runAction holds the same gate as the timer action: an in-flight action
        // has returned before its pending successor is disabled and detached.
        me->fVblTimer->disable();
        me->fVblTimer->cancelTimeout();
        me->fVblWorkLoop->removeEventSource(me->fVblTimer);
        return kIOReturnSuccess;
    }

    // The firmware lit the panel at its native refresh, which the VBL timer and the mode must report: they said 60 Hz while
    // the panel scanned at 120 (OTG frame counter: 392 frames in 3.28 s), and WindowServer composited at 60 fps (2026-10-20).
    // Read-only: OTG0's H/V totals (DCN 3.1.4: segment 2 base 0x34c0 + 0x1b2a / 0x1b2f) and its frame counter (+0x1b4c)
    // over ~2 s, snapped to a standard rate when within the existing 2 %.
    // Integer frame-counter endpoints can differ by one frame: at 120 Hz,
    // 200 ms has ~4.2 % quantization, but 2 s has ~0.42 % (and ~1.04 % at
    // the lowest snapped rate, 48 Hz). Use actual elapsed time after sleeping.
    void measureRefresh() {
        IOMemoryMap *mm = fPCI ? fPCI->mapDeviceMemoryWithRegister(kIOPCIConfigBaseAddress5) : nullptr;
        if (!mm || mm->getLength() < 0x5100u * 4) { OSSafeReleaseNULL(mm); PFBLOG("refresh: no MMIO view, 60 Hz assumed"); return; }
        const volatile uint32_t *r = (const volatile uint32_t *)mm->getVirtualAddress();
        const auto timingBefore = phx::readOtgTiming(r);
        const uint32_t ctl = r[0x34c0 + 0x1b41], ht = r[0x34c0 + 0x1b2a] + 1, vt = r[0x34c0 + 0x1b2f] + 1;
        const uint32_t c0 = r[0x34c0 + 0x1b4c] & 0xffffff; const uint64_t t0 = mach_absolute_time();
        IOSleep(2000);
        const uint32_t c1 = r[0x34c0 + 0x1b4c] & 0xffffff; const uint64_t t1 = mach_absolute_time();
        const auto timingAfter = phx::readOtgTiming(r);
        mm->release();
        uint64_t ns; absolutetime_to_nanoseconds(t1 - t0, &ns);
        const uint32_t frames = (c1 - c0) & 0xffffff;
        if (!(ctl & 1) || !ns || frames < 4 || ht < 100 || vt < 100) { PFBLOG("refresh: OTG0 not running (ctl 0x%x, %u frames), 60 Hz assumed", ctl, frames); return; }
        uint32_t mhz = (uint32_t)(((uint64_t)frames * 1000000000000ull) / ns);
        static const uint32_t kStd[] = { 48000, 50000, 60000, 75000, 90000, 100000, 120000, 144000, 165000, 240000 };
        for (uint32_t k : kStd) if (mhz > k * 49 / 50 && mhz < k * 51 / 50) { mhz = k; break; }
        if (mhz < 24000 || mhz > 360000) { PFBLOG("refresh: %u mHz measured, out of range - 60 Hz assumed", mhz); return; }
        fRefreshMilliHz = mhz; fHTotal = ht; fVTotal = vt;
        fFrameNs = 1000000000000ull / mhz;
        fPanelTimingValid = phx::decodePanelTiming(timingBefore, timingAfter, fWidth, fHeight, mhz, fPanelTiming);
        PFBLOG("detailed timing: %s (clock estimated from measured refresh)", fPanelTimingValid ? "validated" : "unavailable; legacy fallback");
        PFBLOG("refresh: OTG0 %ux%u totals, %u frames in %llu us -> %u.%03u Hz", ht, vt, frames, ns / 1000, mhz / 1000, mhz % 1000);
    }

    bool tryReadEdidSizeFromEntry(IORegistryEntry *entry) {
        if (!entry) return false;
        static const char *const kEdidKeys[] = { kIODisplayEDIDKey, kIODisplayEDIDOriginalKey };
        for (const char *key : kEdidKeys) {
            OSObject *obj = entry->copyProperty(key);
            const auto *data = OSDynamicCast(OSData, obj);
            uint16_t widthMm = 0, heightMm = 0;
            const bool ok = data && data->getBytesNoCopy() &&
                phx::decodeEdidPanelSizeMm(static_cast<const uint8_t *>(data->getBytesNoCopy()),
                                           data->getLength(), fWidth, fHeight, widthMm, heightMm);
            OSSafeReleaseNULL(obj);
            if (ok) {
                fPanelWidthMm = widthMm;
                fPanelHeightMm = heightMm;
                return true;
            }
        }
        return false;
    }

    void refreshPanelSizeFromEdid() {
        if (fPanelWidthMm && fPanelHeightMm) return;
        bool found = tryReadEdidSizeFromEntry(this);
        if (!found) {
            if (OSIterator *children = getChildIterator(gIOServicePlane)) {
                while (!found) {
                    OSObject *childObj = children->getNextObject();
                    if (!childObj) break;
                    IORegistryEntry *child = OSDynamicCast(IORegistryEntry, childObj);
                    if (!child) continue;
                    found = tryReadEdidSizeFromEntry(child);
                    if (!found) {
                        if (OSIterator *grand = child->getChildIterator(gIOServicePlane)) {
                            while (!found) {
                                OSObject *grandObj = grand->getNextObject();
                                if (!grandObj) break;
                                found = tryReadEdidSizeFromEntry(OSDynamicCast(IORegistryEntry, grandObj));
                            }
                            grand->release();
                        }
                    }
                }
                children->release();
            }
        }
        if (!found && fPCI) found = tryReadEdidSizeFromEntry(fPCI);
        if (found) {
            setProperty("PhxFBPanelWidthMm", fPanelWidthMm, 32);
            setProperty("PhxFBPanelHeightMm", fPanelHeightMm, 32);
            PFBLOG("panel physical size from EDID: %ux%u mm", fPanelWidthMm, fPanelHeightMm);
        }
    }

public:
    // the backlight as 0..kBlMax of full duty; false without a running PWM
    bool backlightRead(uint32_t *level) {
        if (!fMmio || !level) return false;
        volatile uint32_t *r = (volatile uint32_t *)fMmio->getVirtualAddress();
        const uint32_t pc = r[kBlPeriod], period = pc & 0xffff, bits = (pc >> 16) & 0xf, cntl = r[kBlCntl];
        const uint64_t full = bits ? ((uint64_t)0x10000 * period) >> bits : 0;
        if (!full || !(cntl >> 31)) return false;
        const uint64_t l = (uint64_t)(cntl & 0xffff) * kBlMax / full;
        *level = l > kBlMax ? kBlMax : (uint32_t)l;
        return true;
    }
    // level 0 is dark, as on a MacBook: AppleBacklightDisplay puts the panel to sleep with brightness 0
    bool backlightWrite(uint32_t level) {
        if (!fMmio) return false;
        volatile uint32_t *r = (volatile uint32_t *)fMmio->getVirtualAddress();
        if (level > kBlMax) level = kBlMax;
        uint64_t frac = (uint64_t)level * 0x10000 / kBlMax;   // 16.16
        if (level && frac < 0x10000 / 100) frac = 0x10000 / 100;   // above dark, at least 1 % of full duty
        bool any = false;
        for (uint32_t q : kBlSeqs) {
            const uint32_t pc = r[kBlPeriod + q], period = pc & 0xffff, bits = (pc >> 16) & 0xf;
            if (!period || !bits || !(r[kBlCntl + q] >> 31)) continue;
            const uint64_t duty = frac * period;
            uint32_t cnt = (uint32_t)((duty >> bits) & 0xffff) + (uint32_t)((duty >> (bits - 1)) & 1);
            if (cnt > 0xffff) cnt = 0xffff;
            r[kBlLock + q] = r[kBlLock + q] | 0x80000000u | 1u;                 // IGNORE_MASTER_LOCK_EN, REG_LOCK
            r[kBlCntl + q] = (r[kBlCntl + q] & ~0xffffu) | cnt;                 // BL_ACTIVE_INT_FRAC_CNT
            r[kBlLock + q] = (r[kBlLock + q] | 0x80000000u) & ~1u;
            for (int i = 0; i < 100 && (r[kBlLock + q] & 0x100); i++) IODelay(100);   // REG_UPDATE_PENDING
            any = true;
        }
        return any;
    }
    // Display sleep left the backlight lit over a black or torn frame (2026-10-25). Besides brightness 0, a connection
    // powered down goes dark and gets its level back on power-up; a brightness set while dark waits.
    bool fBlDark = false;
    uint32_t fBlSaved = kBlMax;
    bool backlightSet(uint32_t level) {
        if (fBlDark) { fBlSaved = level > kBlMax ? kBlMax : level; return true; }
        return backlightWrite(level);
    }
    void displayPower(bool on) {
        if (!on) {
            curDisableImmediate();
            (void)zcHome(true);
        }
        if (!fBacklight || on != fBlDark) return;
        if (!on && !(backlightRead(&fBlSaved) && backlightWrite(0))) return;
        fBlDark = !on;
        if (on) backlightWrite(fBlSaved);
        fBacklight->setProperty("PhxDark", fBlDark);
        PFBLOG("backlight: display power %s, level %u", on ? "on" : "off", fBlSaved);
    }
    bool backlightDark() const { return fBlDark; }
    // which calls reach the panel, newest first, as the registry property PhxTrace (the brightness slider moved and no
    // brightness parameter arrived, 2026-10-25); the log does not reach the unified log
    char fTrace[16][48] = {}; unsigned fTraceN = 0;
    void trace(const char *what, uint32_t a, uint64_t v) {
        char line[48]; snprintf(line, sizeof line, "%s %c%c%c%c=0x%llx", what, (char)(a >> 24), (char)(a >> 16), (char)(a >> 8), (char)a,
                                (unsigned long long)v);
        if (fTraceN && !strcmp(line, fTrace[(fTraceN - 1) % 16])) return;   // repeats of the last call
        strlcpy(fTrace[fTraceN++ % 16], line, sizeof fTrace[0]);
        char all[16 * 48 + 16] = ""; for (unsigned i = 0; i < 16 && i < fTraceN; i++) { strlcat(all, fTrace[(fTraceN - 1 - i) % 16], sizeof all); strlcat(all, "; ", sizeof all); }
        setProperty("PhxTrace", all);
    }
    // the built-in panel is a TFT: AppleBacklightDisplay then drives it (brightness, dimming), as on a MacBook
    IOReturn getAppleSense(IOIndex idx, UInt32 *senseType, UInt32 *primary, UInt32 *extended, UInt32 *displayType) override {
        if (idx != 0 || !fBacklight) return kIOReturnUnsupported;
        if (senseType) *senseType = 0;
        if (primary) *primary = 0;
        if (extended) *extended = 0;
        if (displayType) *displayType = 2;   // kPanelTFTConnect (IOMacOSVideo.h, the NDRV headers)
        return kIOReturnSuccess;
    }
    bool start(IOService *provider) override;
    void stop(IOService *provider) override;
    IOReturn zcDisableImmediate() { return zcHome(true); }
    void hwCursorDisableImmediate() { curDisableImmediate(); }
    IOReturn enableController() override { return kIOReturnSuccess; }
    bool isConsoleDevice() override { return !fBeside; }
    IODeviceMemory *getApertureRange(IOPixelAperture aperture) override {
        if (aperture != kIOFBSystemAperture) return nullptr;
        return IODeviceMemory::withRange(fBase, (IOPhysicalLength)fRowBytes * fHeight);
    }
    IODeviceMemory *getVRAMRange() override { return getApertureRange(kIOFBSystemAperture); }
    const char *getPixelFormats() override { return IO32BitDirectPixels "\0"; }
    IOItemCount getDisplayModeCount() override { return 1; }
    IOReturn getDisplayModes(IODisplayModeID *modes) override { modes[0] = 1; return kIOReturnSuccess; }
    IOReturn getInformationForDisplayMode(IODisplayModeID mode, IODisplayModeInformation *info) override {
        if (mode != 1 || !info) return kIOReturnBadArgument;
        bzero(info, sizeof(*info));
        refreshPanelSizeFromEdid();
        info->maxDepthIndex = 0; info->nominalWidth = fWidth; info->nominalHeight = fHeight;
        info->imageWidth = fPanelWidthMm; info->imageHeight = fPanelHeightMm;
        info->refreshRate = (IOFixed1616)(((uint64_t)fRefreshMilliHz << 16) / 1000);
        info->flags = kDisplayModeValidFlag | kDisplayModeSafeFlag | kDisplayModeDefaultFlag |
            kFramebufferSupportsGammaCorrection | kDisplayModeAcceleratorBackedFlag;
        if (fHiRes) info->flags |= kDisplayModeValidForHiResFlag;
        return kIOReturnSuccess;
    }
    UInt64 getPixelFormatsForDisplayMode(IODisplayModeID, IOIndex) override { return 0; }
    IOReturn getPixelInformation(IODisplayModeID mode, IOIndex depth, IOPixelAperture aperture, IOPixelInformation *pi) override {
        if (mode != 1 || depth != 0 || aperture != kIOFBSystemAperture || !pi) return kIOReturnUnsupportedMode;
        bzero(pi, sizeof(*pi));
        pi->bytesPerRow = fRowBytes; pi->bitsPerPixel = 32; pi->pixelType = kIORGBDirectPixels;
        pi->componentCount = 3; pi->bitsPerComponent = 8;
        pi->componentMasks[0] = 0x00FF0000; pi->componentMasks[1] = 0x0000FF00; pi->componentMasks[2] = 0x000000FF;
        strlcpy(pi->pixelFormat, IO32BitDirectPixels, sizeof(pi->pixelFormat));
        pi->activeWidth = fWidth; pi->activeHeight = fHeight;
        return kIOReturnSuccess;
    }
    IOReturn getCurrentDisplayMode(IODisplayModeID *mode, IOIndex *depth) override { *mode = 1; *depth = 0; return kIOReturnSuccess; }
    IOReturn getStartupDisplayMode(IODisplayModeID *mode, IOIndex *depth) override { return getCurrentDisplayMode(mode, depth); }
    IOReturn setDisplayMode(IODisplayModeID mode, IOIndex depth) override { return (mode == 1 && depth == 0) ? kIOReturnSuccess : kIOReturnUnsupported; }
    IOReturn getTimingInfoForDisplayMode(IODisplayModeID mode, IOTimingInformation *info) override {
        if (mode != 1 || !info) return kIOReturnUnsupportedMode;
        bzero(info, sizeof(*info));
        info->appleTimingID = kIOTimingIDInvalid;
        if (fPanelTimingValid) {
            const auto &p = fPanelTiming;
            auto &t = info->detailedInfo.v2;
            t.pixelClock = p.pixelClock;
            // Clock error bounds are unknown. Leave min/max zero: do not opt into IOFB's clock-based VBL throttling.
            t.horizontalActive = p.width; t.horizontalBlanking = p.hTotal - p.width;
            t.horizontalSyncOffset = p.hSyncOffset; t.horizontalSyncPulseWidth = p.hSyncWidth;
            t.verticalActive = p.height; t.verticalBlanking = p.vTotal - p.height;
            t.verticalSyncOffset = p.vSyncOffset; t.verticalSyncPulseWidth = p.vSyncWidth;
            t.signalConfig = kIODigitalSignal;
            t.horizontalSyncConfig = p.hPositive ? kIOSyncPositivePolarity : 0;
            t.verticalSyncConfig = p.vPositive ? kIOSyncPositivePolarity : 0;
            info->flags = kIODetailedTimingValid;
        }
        return kIOReturnSuccess;
    }
    IOItemCount getConnectionCount() override { return 1; }
    IOReturn registerForInterruptType(IOSelect type, IOFBInterruptProc proc, OSObject *target, void *ref, void **iref) override {
        if (type == kIOFBVBLInterruptType) {
            for (Irq &q : fVbl) if (!q.proc) {
                q.target = target; q.ref = ref; __atomic_store_n(&q.proc, proc, __ATOMIC_RELEASE);
                PFBLOG("VBL handler %u: %s", (unsigned)(&q - fVbl), target ? target->getMetaClass()->getClassName() : "(no target)");
                if (iref) *iref = &q;
                return kIOReturnSuccess;
            }
            PFBLOG("VBL handler refused: all %u taken", (unsigned)(sizeof fVbl / sizeof fVbl[0]));
            return kIOReturnNoResources;
        }
        if (type == kIOFBConnectInterruptType) { fConnect = { proc, target, ref }; if (iref) *iref = &fConnect; return kIOReturnSuccess; }
        return kIOReturnUnsupported;
    }
    IOReturn unregisterInterrupt(void *iref) override {
        for (Irq &q : fVbl) if (iref == &q) __atomic_store_n(&q.proc, (IOFBInterruptProc)nullptr, __ATOMIC_RELEASE);
        return kIOReturnSuccess;
    }
    IOReturn setInterruptState(void *, UInt32) override { return kIOReturnSuccess; }
    IOReturn setGammaTable(UInt32, UInt32, UInt32, void *) override { return kIOReturnSuccess; }
    IOReturn setGammaTable(UInt32, UInt32, UInt32, void *, bool) override { return kIOReturnSuccess; }
    IOReturn setCLUTWithEntries(IOColorEntry *, UInt32, UInt32, IOOptionBits) override { return kIOReturnSuccess; }
    IOReturn setApertureEnable(IOPixelAperture, IOOptionBits) override { return kIOReturnSuccess; }
    IOReturn setStartupDisplayMode(IODisplayModeID, IOIndex) override { return kIOReturnSuccess; }
    // power and connection answers as NullMoth's NMIntelFB/NVRMFB give them: acknowledge at once, never queue on the
    // controller thread (a base-class power change waited 45 s for an acknowledge and froze WindowServer restarts)
    IOReturn setPowerState(unsigned long ordinal, IOService *) override {
        if (ordinal == 0) {
            curDisableImmediate();
            (void)zcHome(true);
        }
        handleEvent(ordinal ? kIOFBNotifyDidPowerOn : kIOFBNotifyWillPowerOff);
        return kIOPMAckImplied;
    }
    IOReturn setAttribute(IOSelect attribute, uintptr_t value) override {
        trace("attr", attribute, value);
        if (attribute == kIOFBRedGammaScaleAttribute || attribute == kIOFBGreenGammaScaleAttribute ||
            attribute == kIOFBBlueGammaScaleAttribute) {
            const unsigned channel = attribute == kIOFBRedGammaScaleAttribute ? 0 :
                (attribute == kIOFBGreenGammaScaleAttribute ? 1 : 2);
            fGammaScale[channel] = value;
            return kIOReturnSuccess;
        }
        if (attribute == kIOWindowServerActiveAttribute) return kIOReturnSuccess;
        if (attribute == kIOPowerAttribute) {
            displayPower(value != 0);
            if (value) { IOReturn r = IOFramebuffer::setAttribute(attribute, value); handleEvent(kIOFBNotifyDidPowerOn);
                         return r == kIOReturnUnsupported ? kIOReturnSuccess : r; }
            handleEvent(kIOFBNotifyWillPowerOff);
            IOReturn r = IOFramebuffer::setAttribute(attribute, value);
            return r == kIOReturnUnsupported ? kIOReturnSuccess : r;
        }
        return IOFramebuffer::setAttribute(attribute, value);
    }
    IOReturn getAttribute(IOSelect attribute, uintptr_t *value) override {
        if (attribute == kIOHardwareCursorAttribute) {
            if (value) *value = (fCurBufReady && fMmio && fMmio->getLength() >= phx::dcnzc::kMinMmioBytes &&
                                 !fCurTripped) ? 1u : 0u;
            return kIOReturnSuccess;
        }
        if (attribute == kIOFBRedGammaScaleAttribute || attribute == kIOFBGreenGammaScaleAttribute ||
            attribute == kIOFBBlueGammaScaleAttribute) {
            const unsigned channel = attribute == kIOFBRedGammaScaleAttribute ? 0 :
                (attribute == kIOFBGreenGammaScaleAttribute ? 1 : 2);
            if (value) *value = fGammaScale[channel];
            return kIOReturnSuccess;
        }
        if (attribute == kIOWindowServerActiveAttribute) { if (value) *value = 1; return kIOReturnSuccess; }
        return IOFramebuffer::getAttribute(attribute, value);
    }
    IOReturn setCursorImage(void *cursorImage) override {
        if (!fZcLock) return kIOReturnUnsupported;
        if (fCurTripped || fStopping || !fCurBufReady || !fCurScratch) {
            IOLockLock(fZcLock);
            fCurHasImage = false;
            curDisableLocked();
            IOLockUnlock(fZcLock);
            return kIOReturnUnsupported;
        }

        // IOFramebuffer passes cursor frame index 0..N as cursorImage (0 is the normal cursor
        // AND is also used during postOpen/processConnectChange capability probing to populate
        // IOFBCursorInfo). Always invoke convertCursorImage first so IOFBCursorInfo is recorded.
        IOHardwareCursorDescriptor desc;
        bzero(&desc, sizeof(desc));
        desc.majorVersion = kHardwareCursorDescriptorMajorVersion;
        desc.minorVersion = kHardwareCursorDescriptorMinorVersion;
        desc.height = phx::dcncur::kMaxCursorDim;
        desc.width = phx::dcncur::kMaxCursorDim;
        desc.bitDepth = 32;
        desc.numColors = 0;
        desc.flags = 0;
        desc.supportedSpecialEncodings = 0;

        IOHardwareCursorInfo info;
        bzero(&info, sizeof(info));
        info.majorVersion = kHardwareCursorInfoMajorVersion;
        info.minorVersion = kHardwareCursorInfoMinorVersion;
        info.hardwareCursorData = reinterpret_cast<UInt8 *>(fCurScratch);
        if (!convertCursorImage(cursorImage, &desc, &info)) {
            IOLockLock(fZcLock);
            fCurHasImage = false;
            curDisableLocked();
            IOLockUnlock(fZcLock);
            return kIOReturnUnsupported;
        }
        if (!__atomic_load_n(&gPhxHwCursor, __ATOMIC_ACQUIRE)) {
            IOLockLock(fZcLock);
            fCurHasImage = false;
            curDisableLocked();
            IOLockUnlock(fZcLock);
            return kIOReturnUnsupported;
        }
        uint32_t pitchPixels = 0, hwPitch = 0, lpc = 0;
        if (!phx::dcncur::selectCursorPitch(info.cursorWidth, pitchPixels, hwPitch) ||
            !phx::dcncur::selectLinesPerChunk32bpp(info.cursorWidth, lpc) ||
            info.cursorHeight == 0 || info.cursorHeight > phx::dcncur::kMaxCursorDim) {
            OSAddAtomic64(1, &gCurErrors);
            IOLockLock(fZcLock);
            fCurHasImage = false;
            curDisableLocked();
            IOLockUnlock(fZcLock);
            return kIOReturnUnsupported;
        }

        IOLockLock(fZcLock);
        if (!__atomic_load_n(&gPhxHwCursor, __ATOMIC_ACQUIRE) || fCurTripped || fStopping ||
            !fCurBufReady || !fZcArmed || fZcTripped || fZcFrontSlot < 0 ||
            fZcFrontSlot >= static_cast<int>(phx::dcnzc::kSlotCount)) {
            fCurHasImage = false;
            curDisableLocked();
            IOLockUnlock(fZcLock);
            return kIOReturnUnsupported;
        }
        const uint32_t nextBuf = fCurBufIdx ^ 1u;
        uint32_t *dst = fCurKva + static_cast<uint64_t>(nextBuf) *
            (phx::dcncur::kCursorSlotBytes / sizeof(uint32_t));
        if (!phx::dcncur::repackCursorImage32(
                fCurScratch, info.cursorWidth, info.cursorHeight,
                dst, pitchPixels, phx::dcncur::kCursorSlotBytes / sizeof(uint32_t))) {
            OSAddAtomic64(1, &gCurErrors);
            fCurHasImage = false;
            curDisableLocked();
            IOLockUnlock(fZcLock);
            return kIOReturnUnsupported;
        }
        curFlushSlot(nextBuf);
        fCurBufIdx = nextBuf;
        fCurWidth = info.cursorWidth;
        fCurHeight = info.cursorHeight;
        fCurPitchPixels = pitchPixels;
        fCurHwPitch = hwPitch;
        fCurLpc = lpc;
        fCurHasImage = true;
        if (!zcLockOtg(true)) {
            OSAddAtomic64(1, &gCurErrors);
            fCurHasImage = false;
            curDisableLocked();
            IOLockUnlock(fZcLock);
            return kIOReturnUnsupported;
        }
        curProgramActiveInLock(static_cast<uint32_t>(fZcFrontSlot), fCurBufIdx);
        const bool unlocked = zcLockOtg(false);
        const bool ok = unlocked && !fCurTripped;
        if (!ok) {
            fCurHasImage = false;
            curDisableLocked();
        }
        IOLockUnlock(fZcLock);
        if (!ok) {
            OSAddAtomic64(1, &gCurErrors);
            return kIOReturnUnsupported;
        }
        OSAddAtomic64(1, &gCurImages);
        return kIOReturnSuccess;
    }
    IOReturn setCursorState(SInt32 x, SInt32 y, bool visible) override {
        if (!fZcLock) return kIOReturnSuccess;
        IOLockLock(fZcLock);
        fCurX = x;
        fCurY = y;
        fCurVisible = visible;
        if (!__atomic_load_n(&gPhxHwCursor, __ATOMIC_ACQUIRE) || fCurTripped || fStopping ||
            !fCurBufReady || !fCurHasImage || !fZcArmed || fZcTripped || fZcFrontSlot < 0 ||
            fZcFrontSlot >= static_cast<int>(phx::dcnzc::kSlotCount)) {
            curDisableLocked();
            IOLockUnlock(fZcLock);
            return kIOReturnSuccess;
        }
        using namespace phx::dcncur;
        const uint32_t pixelClkKhz = fPanelTimingValid ? static_cast<uint32_t>(fPanelTiming.pixelClock / 1000ull) : 0u;
        const PositionRegs pos = computeCursorPosition(
            fCurX, fCurY, fCurVisible, fCurWidth, fCurHeight, fWidth, fHeight, 100000u, pixelClkKhz);
        if (!zcLockOtg(true)) {
            OSAddAtomic64(1, &gCurErrors);
            IOLockUnlock(fZcLock);
            return kIOReturnSuccess;
        }
        const uint32_t priorCtl = zcRead(kRegCursorControl);
        const uint32_t priorCnvc = zcRead(kRegCnvcCur0Control);
        bool ok = priorCtl != UINT32_MAX && priorCnvc != UINT32_MAX;
        if (ok && pos.visible) {
            ok &= zcWrite(kRegCursorPosition, pos.positionReg);
            ok &= zcWrite(kRegCursorHotSpot, pos.hotSpotReg);
            ok &= zcWrite(kRegCursorDstOffset, pos.dstOffsetReg);
        }
        if (ok) {
            ok &= zcWrite(kRegCursorControl, encodeCursorControl(
                priorCtl, pos.visible, kCursorModeColorUnPreMultAlpha, fCurHwPitch, fCurLpc));
            ok &= zcWrite(kRegCnvcCur0Control, encodeCnvcCursorControl(
                priorCnvc, pos.visible, kCursorModeColorUnPreMultAlpha));
        }
        if (ok) {
            fCurHwEnabled = pos.visible;
        } else {
            fCurTripped = true;
            OSAddAtomic64(1, &gCurErrors);
            curWriteDisabledInLock();
        }
        (void)zcLockOtg(false);
        IOLockUnlock(fZcLock);
        if (ok) OSAddAtomic64(1, &gCurMoves);
        return kIOReturnSuccess;
    }
    IOReturn setAttributeForConnection(IOIndex idx, IOSelect attribute, uintptr_t value) override {
        trace("conn", attribute, value);
        switch (attribute) {
        case kConnectionPower:
            displayPower(value != 0);
            return kIOReturnSuccess;
        case kConnectionColorModesSupported: case kConnectionColorDepthsSupported:
        case kConnectionControllerColorDepth: case kConnectionControllerDepthsSupported: case kConnectionColorMode:
        case kConnectionDisplayFlags: case kConnectionFlags:
            return kIOReturnSuccess;
        default: return IOFramebuffer::setAttributeForConnection(idx, attribute, value);
        }
    }
    IOReturn getAttributeForConnection(IOIndex idx, IOSelect attr, uintptr_t *value) override {
        if (idx != 0 || !value) return kIOReturnBadArgument;
        switch (attr) {
        case kConnectionEnable: case kConnectionCheckEnable: *value = 1; return kIOReturnSuccess;
        case kConnectionFlags: *value = kIOConnectionBuiltIn; return kIOReturnSuccess;
        case kConnectionColorModesSupported: case kConnectionColorMode: *value = 0x00000001; return kIOReturnSuccess;
        case kConnectionColorDepthsSupported: case kConnectionControllerColorDepth: case kConnectionControllerDepthsSupported:
            *value = 0x00000002; return kIOReturnSuccess;
        default: return IOFramebuffer::getAttributeForConnection(idx, attr, value);
        }
    }
    IOReturn connectFlags(IOIndex, IODisplayModeID, IOOptionBits *flags) override {
        if (flags) *flags = kDisplayModeValidFlag | kDisplayModeSafeFlag | kDisplayModeDefaultFlag;
        return kIOReturnSuccess;
    }
    // The accelerator's display pipe asks for the scan-out: its CPU mapping (frames are copied in) and its physical
    // address in the GPU's VRAM aperture. With no address the pipe got no framebuffer resource, and IOAcceleratorFamily
    // marks a display pipe active only once one exists (init_framebuffer_resource sets +0x298): every WindowServer
    // transaction ended kIOReturnNotReady and no frame reached the panel (2026-10-20).
    // The scan-out through the carve-out, once PhxBringup has published where the carve-out sits (phx-fb-phys) and only
    // if that view holds the pixels the BAR shows. NULL (copy through the BAR) until then.
    IOMemoryMap *aliasMap() {
        if (fAliasMap || phx780m::aliasExhausted(fAliasTries, fAliasWaits)) return fAliasMap;
        if (!OSCompareAndSwap(0, 1, &fAliasBusy)) return nullptr;
        if (!fAliasMap) {
            uint64_t fbPhys = 0, barOff = ~0ull;
            if (OSIterator *it = fPCI->getChildIterator(gIOServicePlane)) {
                while (OSObject *o = it->getNextObject()) {
                    IORegistryEntry *e = OSDynamicCast(IORegistryEntry, o);
                    OSNumber *n = e ? OSDynamicCast(OSNumber, e->getProperty("phx-fb-phys")) : nullptr;
                    if (n) { fbPhys = n->unsigned64BitValue(); break; }
                }
                it->release();
            }
            for (uint32_t i = 0; i < fPCI->getDeviceMemoryCount(); i++) {
                IODeviceMemory *dm = fPCI->getDeviceMemoryWithIndex(i);
                if (dm && fBase >= dm->getPhysicalAddress() && fBase - dm->getPhysicalAddress() < dm->getLength()) {
                    barOff = fBase - dm->getPhysicalAddress();
                    break;
                }
            }
            // PhxBringup can publish the carve-out after this framebuffer's first presents. That is a wait, not a
            // failed check: counting three early presents as verification failures pinned the session to the BAR copy
            // path (~110 ms a frame at 2560x1600) for its whole life. Only a real pixel mismatch uses the budget.
            if (!phx780m::aliasCarveOutReady(fbPhys, barOff)) {
                if (!fAliasWaits++) PFBLOG("alias: carve-out not published yet (ram 0x%llx, BAR offset 0x%llx): retrying", fbPhys, barOff);
                fAliasBusy = 0;
                return fAliasMap;
            }
            fAliasTries++;
            const uint64_t phys = fbPhys + barOff, bytes = (uint64_t)fRowBytes * fHeight;
            IOMemoryMap *m = nullptr;
            if (IODeviceMemory *dm = IODeviceMemory::withRange(phys, bytes)) { m = dm->map(kIOMapWriteCombineCache); dm->release(); }
            if (m) {
                const volatile uint32_t *a = (const volatile uint32_t *)m->getVirtualAddress();
                const volatile uint32_t *b = (const volatile uint32_t *)fSurfMap->getVirtualAddress();
                const uint64_t words = bytes / 4, step = phx780m::aliasSampleStep(words);
                unsigned same = 0, nz = 0, n = 0;
                for (uint64_t w = 0; w < words; w += step, n++) { const uint32_t x = a[w], y = b[w]; same += x == y; nz += y != 0; }
                PFBLOG("alias: scan-out at BAR offset 0x%llx = system RAM 0x%llx: %u of %u samples match the BAR (%u non-zero)",
                       barOff, phys, same, n, nz);
                if (phx780m::aliasSamplesMatch(same, n, nz)) fAliasMap = m; else m->release();
            } else {
                PFBLOG("alias: carve-out 0x%llx, scan-out BAR offset 0x%llx: no system-RAM view, copying through the BAR", fbPhys, barOff);
            }
        }
        fAliasBusy = 0;
        return fAliasMap;
    }
    IOReturn callPlatformFunction(const OSSymbol *fn, bool wait, void *p1, void *p2, void *p3, void *p4) override {
        if (fn && fn->isEqualTo(PHX_FB_FN_ZEROCOPY_FLIP))
            return zcFlip(static_cast<PhxZeroCopyFlipRequest *>(p1));
        if (fn && fn->isEqualTo(PHX_FB_FN_ZEROCOPY_HOME))
            return zcHome(true);
        if (fn && fn->isEqualTo(NVRM_VRAM_FN_SCANOUT)) {
            NVRMVramRequest *r = (NVRMVramRequest *)p1;
            if (!r || r->version != NVRM_VRAM_ABI_VERSION) return kIOReturnBadArgument;
            if (!fSurfMap) return kIOReturnNotReady;
            IOMemoryMap *alias = gAlias ? aliasMap() : nullptr;
            r->kva = (void *)(alias ? alias : fSurfMap)->getVirtualAddress();
            r->phys = fBase; r->actualSize = round_page_64((uint64_t)fRowBytes * fHeight);
            r->width = fWidth; r->height = fHeight; r->pitch = fRowBytes;
            return kIOReturnSuccess;
        }
        if (fn && fn->isEqualTo(NVRM_VRAM_FN_ALLOC)) return vramAlloc((NVRMVramRequest *)p1);
        if (fn && fn->isEqualTo(NVRM_VRAM_FN_FREE)) return vramFree((NVRMVramRequest *)p1);
        if (fn && (fn->isEqualTo(NVRM_GPUVA_FN_HANDLES) || fn->isEqualTo(NVRM_GPUVA_FN_ALLOC) || fn->isEqualTo(NVRM_GPUVA_FN_MAP) ||
                   fn->isEqualTo(NVRM_GPUVA_FN_FREE)))
            return rmCall(fn, p1);
        return IOFramebuffer::callPlatformFunction(fn, wait, p1, p2, p3, p4);
    }
};

OSDefineMetaClassAndStructors(PhxAMDFB, IOFramebuffer)

// The panel's brightness as a display parameter. IOGraphics looks for parameter handlers under the framebuffer, and
// takes a built-in TFT panel for a backlit one (AppleBacklightDisplay) only while a service named "backlight" exists.
class PhxBacklight : public IODisplayParameterHandler {
    OSDeclareDefaultStructors(PhxBacklight)
    PhxAMDFB *fFB = nullptr;
    uint32_t fLevel = kBlMax;
public:
    static PhxBacklight *withFramebuffer(PhxAMDFB *fb) {
        PhxBacklight *b = new PhxBacklight;
        if (b && !b->init()) OSSafeReleaseNULL(b);
        if (b) { b->fFB = fb; fb->backlightRead(&b->fLevel); }
        return b;
    }
    bool setDisplay(IODisplay *display) override {
        if (!display) return true;
        OSObject *p = display->copyProperty(gIODisplayParametersKey);
        OSDictionary *cur = OSDynamicCast(OSDictionary, p);
        OSDictionary *params = cur ? OSDictionary::withDictionary(cur) : OSDictionary::withCapacity(2);
        OSSafeReleaseNULL(p);
        if (!params) return false;
        fFB->backlightRead(&fLevel);
        IODisplay::addParameter(params, gIODisplayBrightnessKey, 0, kBlMax);
        IODisplay::setParameter(params, gIODisplayBrightnessKey, (SInt32)fLevel);
        // CoreBrightness sets the linear ones, as an Intel MacBook's framebuffer offers them: with "brightness" alone
        // the slider moved and no parameter ever reached the panel (2026-10-25)
        const OSSymbol *linear[] = { gIODisplayLinearBrightnessKey, gIODisplayUsableLinearBrightnessKey };
        for (const OSSymbol *k : linear) { IODisplay::addParameter(params, k, 0, kBlMax); IODisplay::setParameter(params, k, (SInt32)fLevel); }
        display->setProperty(gIODisplayParametersKey, params);
        params->release();
        PFBLOG("backlight: brightness parameter on %s, %u of %u", display->getName(), fLevel, kBlMax);
        return true;
    }
    // the last parameter set, in the registry: PhxAMDFB's log does not reach the unified log
    uint32_t fSets = 0;
    bool doIntegerSet(OSDictionary *, const OSSymbol *paramName, UInt32 value) override {
        setProperty("PhxLastParam", const_cast<OSSymbol *>(paramName)); setProperty("PhxLastValue", value, 32); setProperty("PhxSets", ++fSets, 32);
        fFB->trace(paramName->getCStringNoCopy(), 0x20202020, value);
        setProperty("PhxDark", fFB->backlightDark());
        if (paramName != gIODisplayBrightnessKey && paramName != gIODisplayLinearBrightnessKey
            && paramName != gIODisplayUsableLinearBrightnessKey) return false;
        if (!fFB->backlightSet(value)) return false;
        fLevel = value > kBlMax ? kBlMax : value;
        return true;
    }
    bool doDataSet(const OSSymbol *, OSData *) override { return false; }
    IOReturn setProperties(OSObject *properties) override {
        OSDictionary *d = OSDynamicCast(OSDictionary, properties);
        if (OSCollectionIterator *it = d ? OSCollectionIterator::withCollection(d) : nullptr) {
            while (const OSSymbol *k = OSDynamicCast(OSSymbol, it->getNextObject())) fFB->trace(k->getCStringNoCopy(), 0x2a2a2a2a, 0);
            it->release();
        }
        return kIOReturnUnsupported;
    }
    bool doUpdate() override { return true; }
};
OSDefineMetaClassAndStructors(PhxBacklight, IODisplayParameterHandler)

static IOService *phxBacklightCreate(PhxAMDFB *fb)
{
    PhxBacklight *b = PhxBacklight::withFramebuffer(fb);
    if (!b) return nullptr;
    b->setName("backlight");
    if (!b->attach(fb)) { b->release(); return nullptr; }
    b->registerService();
    return b;
}

// One boot per arming: `nvram phxfb-boot=1` lets the next start take the panel, and start removes the variable and
// commits NVRAM at once, so a boot that panics after this point comes back on the firmware framebuffer without hands.
static bool takeBootArming()
{
    IORegistryEntry *opts = IORegistryEntry::fromPath("/options", gIODTPlane);
    if (!opts) return false;
    OSObject *o = opts->copyProperty("phxfb-boot");
    const bool armed = o != nullptr;
    bool stuck = false;
    OSSafeReleaseNULL(o);
    if (armed) {
        opts->removeProperty("phxfb-boot");
        // the forced commit: the throttled one (IONVRAM-SYNCNOW) left the variable in flash once, and the boot after a
        // panic took the panel again (2026-10-20)
        if (OSString *why = OSString::withCString("phxfb")) { opts->setProperty("IONVRAM-FORCESYNCNOW-PROPERTY", why); why->release(); }
        o = opts->copyProperty("phxfb-boot");
        stuck = o != nullptr;
        PFBLOG("NVRAM phxfb-boot taken (%s)", stuck ? "STILL SET: removal refused, not taking the panel" : "removed and committed");
        OSSafeReleaseNULL(o);
    }
    opts->release();
    return armed && !stuck;
}

static bool hiResRequested()
{
    uint32_t bootArg = 0;
    if (PE_parse_boot_argn("phxfbhires", &bootArg, sizeof bootArg) && bootArg == 1) return true;
    IORegistryEntry *opts = IORegistryEntry::fromPath("/options", gIODTPlane);
    if (!opts) return false;
    OSObject *property = opts->copyProperty("phxfb-hidpi");
    opts->release();
    const auto *data = OSDynamicCast(OSData, property);
    const bool enabled = data && data->getLength() == 1 &&
        *static_cast<const uint8_t *>(data->getBytesNoCopy()) == '1';
    OSSafeReleaseNULL(property);
    return enabled;
}

bool PhxAMDFB::start(IOService *provider)
{
    char arg[8];
    if (PE_parse_boot_argn("-phxfboff", arg, sizeof arg)) { PFBLOG("-phxfboff: leaving the firmware framebuffer"); return false; }
    if (!takeBootArming()) { PFBLOG("NVRAM phxfb-boot not set: leaving the firmware framebuffer this boot"); return false; }
    fPCI = OSDynamicCast(IOPCIDevice, provider);
    if (!fPCI) return false;
    if (OSNumber *consumed = OSDynamicCast(OSNumber, fPCI->getProperty("PhxDcnZeroCopyVmidsConsumed"))) {
        const uint32_t mask = consumed->unsigned32BitValue();
        fZcVmidsConsumed = (mask & ~phx::dcnzc::kAllSlotBits) ? phx::dcnzc::kAllSlotBits : mask;
    }
    if (OSIterator *it = fPCI->getChildIterator(gIOServicePlane)) {
        while (OSObject *o = it->getNextObject())
            if (o != this && OSDynamicCast(IOFramebuffer, o)) fBeside = true;
        it->release();
    }
    PE_Video v;
    bzero(&v, sizeof(v));
    IOPlatformExpert *pe = getPlatform();
    if (!pe || pe->getConsoleInfo(&v) != kIOReturnSuccess || !v.v_baseAddr || v.v_depth != 32 || !v.v_width || !v.v_height ||
        v.v_rowBytes < v.v_width * 4 || v.v_width > 16384 || v.v_height > 16384) {
        PFBLOG("no usable boot console (base 0x%lx %lux%lu depth %lu row %lu): leaving the firmware framebuffer",
               v.v_baseAddr, v.v_width, v.v_height, v.v_depth, v.v_rowBytes);
        return false;
    }
    fWidth = (uint32_t)v.v_width; fHeight = (uint32_t)v.v_height; fRowBytes = (uint32_t)v.v_rowBytes;
    // once the video console is up, the platform expert hands out the console's kernel mapping, not the physical
    // address. The GOP surface sits in one of the GPU's BARs (VRAM aperture): find the BAR whose start holds the same
    // pixels as the console mapping. (A descriptor over the mapping would need prepare(): getPhysicalSegment on an
    // unwired one panicked, 2026-10-20.)
    uint64_t base = v.v_baseAddr;
    if (base >= 0xFFFF800000000000ull) {
        const volatile uint32_t *con = (const volatile uint32_t *)(uintptr_t)base;
        const uint32_t probeWords = 64u * 1024u / 4u;
        uint64_t found = 0;
        for (uint32_t i = 0; i < fPCI->getDeviceMemoryCount() && !found; i++) {
            IODeviceMemory *dm = fPCI->getDeviceMemoryWithIndex(i);
            if (!dm || dm->getLength() < (IOByteCount)fRowBytes * fHeight) continue;
            IODeviceMemory *sub = IODeviceMemory::withSubRange(dm, 0, 64u * 1024u);
            IOMemoryMap *m = sub ? sub->map(kIOMapInhibitCache) : nullptr;
            OSSafeReleaseNULL(sub);
            if (!m) continue;
            const volatile uint32_t *bar = (const volatile uint32_t *)m->getVirtualAddress();
            uint32_t same = 0, nz = 0;
            for (uint32_t w = 0; w < probeWords; w++) { const uint32_t a = con[w], b = bar[w]; same += a == b; nz += a != 0; }
            PFBLOG("BAR index %u at 0x%llx: %u of %u words match the console (%u non-zero)", i,
                   (unsigned long long)dm->getPhysicalAddress(), same, probeWords, nz);
            if (same == probeWords && nz) found = dm->getPhysicalAddress();
            m->release();
        }
        if (!found) { PFBLOG("the console surface is in none of the GPU's BARs: leaving the firmware framebuffer"); return false; }
        base = found;
    }
    // early in boot the platform expert hands out the physical address with a flag in its low bits (0x820000001): taken
    // as is, every row WindowServer drew landed one byte off and the panel showed swapped colours (2026-10-20)
    base &= ~(uint64_t)PAGE_MASK;
    fBase = (IOPhysicalAddress)base;
    PFBLOG("console: %ux%u row %u depth %lu at physical 0x%llx", fWidth, fHeight, fRowBytes, v.v_depth, (unsigned long long)fBase);
    if (IODeviceMemory *sm = IODeviceMemory::withRange(fBase, (IOPhysicalLength)fRowBytes * fHeight)) {
        fSurfMap = sm->map(kIOMapWriteCombineCache); sm->release();
    }
    if (!fSurfMap) { PFBLOG("the console surface at 0x%llx would not map write-combined", (unsigned long long)fBase); return false; }
    // IOFramebuffer::start makes the framebuffer's controller only from a dependent ID that is already set
    // (IOFBController::copyController(kDepIDCreate)); without one the controller stays NULL and the first power-change
    // callout dereferences it (IOFramebuffer::powerStateWillChangeTo, panic 2026-10-20)
    setProperty("IOFBDependentID", 0x50485846ull << 32 | 1, 64);   // 'PHXF'
    setProperty("IOFBDependentIndex", 0ull, 32);
    // the backlight's handler comes first: IOGraphics checks for a "backlight" service once, when the framebuffer opens
    fMmio = fPCI->mapDeviceMemoryWithRegister(kIOPCIConfigBaseAddress5);
    if (fMmio && fMmio->getLength() < (kBlLock + kBlSeqs[1] + 1) * 4) OSSafeReleaseNULL(fMmio);
    uint32_t bl = 0;
    if (PE_parse_boot_argn("-phxbloff", arg, sizeof arg)) PFBLOG("backlight: -phxbloff, no brightness control");
    else if (!backlightRead(&bl)) PFBLOG("backlight: the PWM is not running (no MMIO view, or off), no brightness control");
    else if (!(fBacklight = phxBacklightCreate(this))) PFBLOG("backlight: the handler would not attach");
    else PFBLOG("backlight: PWM at %u of %u", bl, kBlMax);
    fHiRes = !((fWidth | fHeight) & 1) && !(fRowBytes & 3) && fRowBytes == v.v_rowBytes
        && hiResRequested();
    setProperty("PhxFBHiResModeFlag", fHiRes);
    fZcLock = IOLockAlloc();
    if (!fZcLock) {
        if (fBacklight) { fBacklight->detach(this); OSSafeReleaseNULL(fBacklight); }
        OSSafeReleaseNULL(fMmio); OSSafeReleaseNULL(fSurfMap); return false;
    }
    uint32_t hwCurArg = 0;
    if (PE_parse_boot_argn("phxfbhwcursor", &hwCurArg, sizeof hwCurArg) && hwCurArg == 1)
        __atomic_store_n(&gPhxHwCursor, 1, __ATOMIC_RELEASE);
    curInitBuffer();
    if (!IOFramebuffer::start(provider)) {
        curFreeBuffer();
        if (fBacklight) { fBacklight->detach(this); OSSafeReleaseNULL(fBacklight); }
        IOLockFree(fZcLock); fZcLock = nullptr;
        OSSafeReleaseNULL(fMmio); OSSafeReleaseNULL(fSurfMap); return false; }
    fVa = IORangeAllocator::withRange(kVaSize - 1, PAGE_SIZE, 0, IORangeAllocator::kLocking);
    poolInit();
    setProperty("built-in", kOSBooleanTrue);
    setProperty("IOFBGammaWidth", 8ull, 32);
    setProperty("IOFBGammaCount", 256ull, 32);
    setProperty("DisplayGammaChannels", 3ull, 32);
    setProperty("DisplayGammaEntryCount", 256ull, 32);
    setProperty("DisplayGammaEntrySize", 1ull, 32);
    setProperty("PhxFBWidth", fWidth, 32); setProperty("PhxFBHeight", fHeight, 32);   // the AGDC's panel timing reads these
    measureRefresh();
    setProperty("PhxFBDetailedTimingValid", fPanelTimingValid ? kOSBooleanTrue : kOSBooleanFalse);
    if (fPanelTimingValid) setProperty("PhxFBEstimatedPixelClock", fPanelTiming.pixelClock, 64);
    setProperty("PhxFBRefreshMilliHz", fRefreshMilliHz, 32);
    if (fHTotal) { setProperty("PhxFBHTotal", fHTotal, 32); setProperty("PhxFBVTotal", fVTotal, 32); }   // the AGDC's panel timing
    nanoseconds_to_absolutetime(fFrameNs, &gPhxFrameAbs);
    // Use the parallel KERNEL timer group without allowing callback reentry.
    // The private workloop gate also synchronizes timer retirement with its action.
    fVblWorkLoop = IOWorkLoop::workLoop();
    if (fVblWorkLoop) {
        fVblTimer = IOTimerEventSource::timerEventSource(
            kIOTimerEventSourceOptionsPriorityKernel, this, vblFire);
        if (!fVblTimer || fVblWorkLoop->addEventSource(fVblTimer) != kIOReturnSuccess) {
            OSSafeReleaseNULL(fVblTimer);
            OSSafeReleaseNULL(fVblWorkLoop);
        }
    }
    if (fVblTimer) { uint64_t d; clock_interval_to_deadline((uint32_t)(fFrameNs / 1000), kMicrosecondScale, &d); fVblNext = d; fVblTimer->wakeAtTime(d); }
    static IOPMPowerState states[2] = {
        { 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0 },
        { 1, kIOPMDeviceUsable, kIOPMPowerOn, kIOPMPowerOn, 0, 0, 0, 0, 0, 0, 0, 0 },
    };
    registerPowerDriver(this, states, 2);
    phxHoldInit(this, kBootHoldSec);
    phxAgdcInstall();
    if (!gFbSysctl) { for (auto *o : kFbOids) sysctl_register_oid(o); gFbSysctl = true; }
    __atomic_store_n(&gPhxFbInstance, this, __ATOMIC_RELEASE);
    PFBLOG("panel published: %ux%u row %u at 0x%llx (vbl timer %s)", fWidth, fHeight, fRowBytes,
           (unsigned long long)fBase, fVblTimer ? "running" : "MISSING");
    return true;
}

void PhxAMDFB::stop(IOService *provider)
{
    __atomic_store_n(&fStopping, true, __ATOMIC_RELEASE);
    __atomic_store_n(&gPhxFbInstance, nullptr, __ATOMIC_RELEASE);
    curDisableImmediate();
    const IOReturn zcHomeResult = zcHome(true);
    if (zcHomeResult == kIOReturnSuccess) {
        zcCleanupPageTables();
        curFreeBuffer();
    }
    if (fVblWorkLoop) {
        fVblWorkLoop->runAction(vblRetire, this);
        OSSafeReleaseNULL(fVblTimer);
        OSSafeReleaseNULL(fVblWorkLoop);
    }
    phxAgdcRemove();
    if (gFbSysctl) { for (auto *o : kFbOids) sysctl_unregister_oid(o); gFbSysctl = false; }
    gPhxFrameAbs = 0;
    if (fBacklight) { fBacklight->terminate(); OSSafeReleaseNULL(fBacklight); }
    OSSafeReleaseNULL(fMmio);
    OSSafeReleaseNULL(fAliasMap);
    OSSafeReleaseNULL(fSurfMap);
    OSSafeReleaseNULL(fVa);
    poolFree();
    IOFramebuffer::stop(provider);
    if (zcHomeResult == kIOReturnSuccess && fZcLock) { IOLockFree(fZcLock); fZcLock = nullptr; }
}

static int phxfb_zerocopy_sysctl SYSCTL_HANDLER_ARGS
{
    int value = __atomic_load_n(&gPhxZeroCopy, __ATOMIC_ACQUIRE);
    const int error = sysctl_handle_int(oidp, &value, 0, req);
    if (error || !req->newptr) return error;
    const int normalized = value ? 1 : 0;
    __atomic_store_n(&gPhxZeroCopy, normalized, __ATOMIC_RELEASE);
    if (!normalized) {
        if (PhxAMDFB *fb = __atomic_load_n(&gPhxFbInstance, __ATOMIC_ACQUIRE))
            (void)fb->zcDisableImmediate();
    }
    return 0;
}

static int phxfb_hwcursor_sysctl SYSCTL_HANDLER_ARGS
{
    int value = __atomic_load_n(&gPhxHwCursor, __ATOMIC_ACQUIRE);
    const int error = sysctl_handle_int(oidp, &value, 0, req);
    if (error || !req->newptr) return error;
    const int normalized = value ? 1 : 0;
    __atomic_store_n(&gPhxHwCursor, normalized, __ATOMIC_RELEASE);
    if (!normalized) {
        if (PhxAMDFB *fb = __atomic_load_n(&gPhxFbInstance, __ATOMIC_ACQUIRE))
            fb->hwCursorDisableImmediate();
    }
    return 0;
}
