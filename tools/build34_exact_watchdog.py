#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Stage checked, generation-bound watchdog recovery; never deploy this stage."""
from build34_exact_cpu_fences import stage as previous_stage, stage_header
from build34_exact_submit import once
from test_build34_exact_ownership import method


FIELDS = '''    struct WatchdogRecovery {
        bool active{false}, terminal{false}, globalAttempted{false};
        uint32_t queue{0}, slot{0}, vmid{0}, context{0};
        uint32_t head[2]{}, tail[2]{};
        uint32_t ringOff{0}, ringDw{0}, wbOff{0}, fenceOff{0};
        uint64_t sequence{0}, generation{0}, allocation{0}, submitted{0};
        uint64_t epoch{0}, postGeneration[2]{}, queueSubmitted[2]{};
        uint64_t wptr{0}, doneEnd{0}, end{0}, dbByte{0}, newest{0}, hwLast{0};
        uint64_t contextSequence[2]{}, contextGeneration[2]{};
        uint64_t started{0}, limitNs{0}, length{0}, apertureLength{0}, registerLength{0}, doorbellLength{0};
        uintptr_t base{0}, registerBase{0}, doorbellBase{0};
        const void *client{nullptr}, *mapping{nullptr}, *registerMapping{nullptr}, *doorbells{nullptr};
        ExactDwordReader reader{nullptr};
        // Diagnostic only: never read by receipts, retirement or resource cleanup.
        phx34_exact::FenceWindow32 window;
    } watchdogRecovery;
    bool watchdogQueueLocked(uint32_t, uint64_t &, uint32_t &);
    bool captureWatchdogLocked(uint32_t, uint32_t, uint64_t, uint64_t);
    bool watchdogRecoveryCurrentLocked() const;
    bool readWatchdogRecoveryLocked(uint64_t *);
    bool killWavesLocked(uint32_t, bool); // caller owns gpuLock and service lease
'''

QUEUE = '''bool PhxBringup::watchdogQueueLocked(uint32_t qi, uint64_t &done, uint32_t &oldest) {
    if (qi >= 2) return false;
    const GpuQueue &q = gq[qi];
    oldest = UINT32_MAX;
    if (!exactQueueGeneration[qi]) return !q.ready && !exactQueueLive[qi];
    if (!fbAper || !doorbellMap || !q.ready || !exactQueueLive[qi] || q.gfx != (qi == 1) ||
        q.ringDw < 256 || q.ringDw > 65536 || (q.ringDw & (q.ringDw - 1)) || (q.ringOff & 255) ||
        (q.wbOff & 7) || (q.fenceOff & 7) || (q.dbByte & 7)) return false;
    const uint64_t length = fbAper->getLength(), doorLength = doorbellMap->getLength();
    if (q.ringOff > fbAperLen || fbAperLen - q.ringOff < uint64_t{q.ringDw} * 4 ||
        q.ringOff > length || length - q.ringOff < uint64_t{q.ringDw} * 4 ||
        q.wbOff > fbAperLen || fbAperLen - q.wbOff < 32 || q.wbOff > length || length - q.wbOff < 32 ||
        q.fenceOff > fbAperLen || fbAperLen - q.fenceOff < 8 || q.fenceOff > length || length - q.fenceOff < 8 ||
        q.dbByte > doorLength || doorLength - q.dbByte < 8 || q.wptr < q.doneEnd ||
        q.wptr - q.doneEnd > q.ringDw - 16 || q.tail - q.head > 63u || !readExactFence32(qi, &done)) return false;
    uint64_t previous = 0, end = q.doneEnd;
    for (uint32_t i = q.head; i != q.tail; ++i) {
        const uint32_t slot = i & 63u;
        const uint64_t seq = q.fseq[slot];
        if (!seq || seq == UINT64_MAX || seq <= previous || seq > exactQueueSubmitted[qi] ||
            q.fend[slot] <= end || q.fend[slot] > q.wptr) return false;
        previous = seq; end = q.fend[slot];
        if (seq <= done) continue; // completed history need not own a still-live VM allocation
        const uint32_t h = q.fctx[slot], hw = q.fvmid[slot];
        if (!h || h > kMaxCtx || hw < kFirstUserVmid || hw >= kFirstUserVmid + kNumUserVmids) return false;
        const VmCtx &c = vm[h - 1];
        const HwVmid &v = hwv[hw - kFirstUserVmid];
        if (!c.busy || !c.client || !c.generation || c.generation == UINT64_MAX ||
            q.fallocation[slot] != c.generation || !vmWorkCurrent(c) || c.hw != hw ||
            v.ctx != h || v.generation != c.generation || v.lastSeq != c.newest || v.lastSeq < seq ||
            c.queueGeneration[qi] != exactQueueGeneration[qi] || c.queueSequence[qi] < seq) return false;
        if (oldest == UINT32_MAX) oldest = slot;
    }
    if (q.head != q.tail && previous != exactQueueSubmitted[qi]) return false;
    return !exactCallbacks.closed() && !exactStopped && !isSleeping && !exactVMFault;
}
'''

CAPTURE = '''bool PhxBringup::captureWatchdogLocked(uint32_t qi, uint32_t slot, uint64_t done, uint64_t limitNs) {
    WatchdogRecovery &w = watchdogRecovery;
    if (w.active || qi >= 2 || slot >= 64 || !limitNs || !mmio || !fbAper || !doorbellMap ||
        !exactDwordReader || exactCallbacks.closed() || exactStopped || isSleeping || exactVMFault || hangStop) return false;
    const GpuQueue &q = gq[qi];
    const uint32_t context = q.fctx[slot], hw = q.fvmid[slot];
    if (!context || context > kMaxCtx || hw < kFirstUserVmid || hw >= kFirstUserVmid + kNumUserVmids ||
        !q.fseq[slot] || q.fseq[slot] <= done || exactQueueSubmitted[qi] <= done) return false;
    const uintptr_t registerBase = mmio->getVirtualAddress();
    const uint64_t registerLength = mmio->getLength();
    const uint64_t lastRegister = uint64_t{kRegRlcSafeMode > kRegSqCmd ? kRegRlcSafeMode : kRegSqCmd} * 4;
    if (!registerBase || (registerBase & 3) || registerLength < lastRegister + 4 ||
        registerBase > UINTPTR_MAX - lastRegister - 3) return false;
    w.active = true; // one service episode; no reseeding after uncertain recovery
    w.queue = qi; w.slot = slot; w.vmid = hw; w.context = context;
    w.sequence = q.fseq[slot]; w.generation = exactQueueGeneration[qi]; w.allocation = q.fallocation[slot];
    w.submitted = exactQueueSubmitted[qi]; w.limitNs = limitNs;
    w.mapping = fbAper; w.base = fbAper->getVirtualAddress(); w.length = fbAper->getLength(); w.apertureLength = fbAperLen;
    w.registerMapping = mmio; w.registerBase = registerBase; w.registerLength = registerLength;
    w.doorbells = doorbellMap; w.doorbellBase = doorbellMap->getVirtualAddress(); w.doorbellLength = doorbellMap->getLength();
    w.reader = exactDwordReader;
    w.ringOff = q.ringOff; w.ringDw = q.ringDw; w.wbOff = q.wbOff; w.fenceOff = q.fenceOff;
    w.wptr = q.wptr; w.doneEnd = q.doneEnd; w.end = q.fend[slot]; w.dbByte = q.dbByte;
    const VmCtx &c = vm[context - 1];
    w.client = c.client; w.newest = c.newest; w.hwLast = hwv[hw - kFirstUserVmid].lastSeq;
    for (uint32_t i = 0; i < 2; ++i) {
        w.head[i] = gq[i].head; w.tail[i] = gq[i].tail; w.queueSubmitted[i] = exactQueueSubmitted[i];
        w.contextSequence[i] = c.queueSequence[i]; w.contextGeneration[i] = c.queueGeneration[i];
    }
    // Construct a separate bounded decoder. Copying the ordinary window is forbidden.
    if (!w.window.seed(w.generation, done) || !w.window.submit(w.generation, w.submitted)) {
        w.terminal = true;
        return false;
    }
    exactVMFault = true; // prohibit submit, VM mutation/reuse and adoption BEFORE the first recovery write
    invalidateExactQueues();
    w.epoch = exactInvalidationEpoch;
    for (uint32_t i = 0; i < 2; ++i) w.postGeneration[i] = exactQueueGeneration[i];
    return watchdogRecoveryCurrentLocked();
}
'''

CURRENT = '''bool PhxBringup::watchdogRecoveryCurrentLocked() const {
    const WatchdogRecovery &w = watchdogRecovery;
    if (!w.active || w.terminal || !exactVMFault || exactCallbacks.closed() || exactStopped || isSleeping || hangStop ||
        w.queue >= 2 || w.slot >= 64 || !w.context || w.context > kMaxCtx ||
        w.vmid < kFirstUserVmid || w.vmid >= kFirstUserVmid + kNumUserVmids ||
        exactInvalidationEpoch != w.epoch || !fbAper || fbAper != w.mapping || !mmio || mmio != w.registerMapping ||
        !doorbellMap || doorbellMap != w.doorbells || !w.reader || exactDwordReader != w.reader ||
        fbAper->getVirtualAddress() != w.base || fbAper->getLength() != w.length || fbAperLen != w.apertureLength ||
        mmio->getVirtualAddress() != w.registerBase || mmio->getLength() != w.registerLength ||
        doorbellMap->getVirtualAddress() != w.doorbellBase || doorbellMap->getLength() != w.doorbellLength) return false;
    for (uint32_t i = 0; i < 2; ++i)
        if (exactQueueLive[i] || exactQueueGeneration[i] != w.postGeneration[i] ||
            exactQueueSubmitted[i] != w.queueSubmitted[i] || gq[i].head != w.head[i] || gq[i].tail != w.tail[i]) return false;
    const GpuQueue &q = gq[w.queue];
    const VmCtx &c = vm[w.context - 1];
    const HwVmid &v = hwv[w.vmid - kFirstUserVmid];
    if (!q.ready || q.gfx != (w.queue == 1) || q.ringOff != w.ringOff || q.ringDw != w.ringDw ||
        q.wbOff != w.wbOff || q.fenceOff != w.fenceOff || q.dbByte != w.dbByte ||
        q.wptr != w.wptr || q.doneEnd != w.doneEnd || q.fseq[w.slot] != w.sequence || q.fend[w.slot] != w.end ||
        q.fctx[w.slot] != w.context || q.fallocation[w.slot] != w.allocation || q.fvmid[w.slot] != w.vmid ||
        !c.busy || c.client != w.client || c.generation != w.allocation || c.hw != w.vmid || c.newest != w.newest ||
        v.ctx != w.context || v.generation != w.allocation || v.lastSeq != w.hwLast) return false;
    for (uint32_t i = 0; i < 2; ++i)
        if (c.queueSequence[i] != w.contextSequence[i] || c.queueGeneration[i] != w.contextGeneration[i]) return false;
    return !exactCallbacks.closed() && !exactStopped && !isSleeping && !hangStop;
}
'''

READ = '''bool PhxBringup::readWatchdogRecoveryLocked(uint64_t *completed) {
    if (!completed || !watchdogRecoveryCurrentLocked()) return false;
    WatchdogRecovery &w = watchdogRecovery;
    if (!w.base || (w.fenceOff & 7) || w.fenceOff > w.length || w.length - w.fenceOff < 8 ||
        w.fenceOff > w.apertureLength || w.apertureLength - w.fenceOff < 8 ||
        w.base > UINTPTR_MAX - w.fenceOff || ((w.base + w.fenceOff) & 3)) return false;
    uint32_t raw = 0;
    if (!w.reader(reinterpret_cast<const volatile uint32_t *>(w.base + w.fenceOff), &raw) ||
        !watchdogRecoveryCurrentLocked()) return false; // close may happen independently of gpuLock
    uint64_t value;
    if (!w.window.observe(w.generation, raw, value)) return false;
    *completed = value; // diagnostic only, never a completion/resource-release proof
    return true;
}
'''

KILL = '''bool PhxBringup::killWavesLocked(uint32_t vmid, bool all) {
    // Existing build34 register protocol only. Native ACK freshness remains unproved.
    WatchdogRecovery &w = watchdogRecovery;
    if (!watchdogRecoveryCurrentLocked() || (all ? vmid != 0 : vmid != w.vmid)) return false;
    uint64_t done;
    if (!readWatchdogRecoveryLocked(&done) || done >= w.sequence) return false;
    const uint64_t start = mach_absolute_time();
    if (!watchdogRecoveryCurrentLocked()) return false;
    wreg(kRegRlcSafeMode, 0x3); // enter, with admitted callback/mapping pins still held
    bool issued = false;
    for (uint32_t attempt = 0; attempt < 1000; ++attempt) {
        if (!watchdogRecoveryCurrentLocked()) break;
        uint64_t elapsed = 0;
        absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
        if (elapsed >= 1000000ull) break;
        const bool ready = !(rreg(kRegRlcSafeMode) & 1);
        if (!watchdogRecoveryCurrentLocked()) break;
        absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
        if (elapsed >= 1000000ull) break; // include register-read and scheduling delay
        if (ready) {
            if (!readWatchdogRecoveryLocked(&done) || done >= w.sequence) break;
            absolutetime_to_nanoseconds(mach_absolute_time() - start, &elapsed);
            if (elapsed >= 1000000ull || !watchdogRecoveryCurrentLocked()) break;
            wreg(kRegSqCmd, 0x13u | (all ? 0u : (0x80u | (vmid & 0xfu) << 28)));
            OSIncrementAtomic(&gHangKills); // actual SQ attempt, never a drain/success counter
            issued = true;
            break;
        }
        if (attempt + 1 < 1000) IODelay(1);
    }
    // Exactly one paired exit, even if close became visible after enter.
    // The caller's admitted callback pins the original mappings through this write.
    wreg(kRegRlcSafeMode, 0x1);
    if (!issued || !watchdogRecoveryCurrentLocked()) w.terminal = true;
    return issued;
}
'''

HANG = '''void PhxBringup::hangCheck() {
    phx34_exact::CallbackGate<>::Lease callback(exactCallbacks);
    if (!callback || !gpuLock) return;
    IOLockLock(gpuLock);
    auto check = [&]() {
        WatchdogRecovery &w = watchdogRecovery;
        const int limitMs = gHangMs;
        if (limitMs <= 0 || !mmio || hangStop || exactCallbacks.closed() || exactStopped || isSleeping) {
            if (w.active) w.terminal = true;
            return;
        }
        if (w.active) {
            if (w.terminal) return;
            uint64_t done;
            if (!readWatchdogRecoveryLocked(&done) || done >= w.sequence) {
                w.terminal = true;
                return; // completion stops escalation, NEVER clears the fault or releases resources
            }
            uint64_t elapsed = 0;
            absolutetime_to_nanoseconds(mach_absolute_time() - w.started, &elapsed);
            // Preserve the old effective escalation interval: a SECOND FULL threshold.
            if (elapsed < w.limitNs || w.globalAttempted) return;
            w.globalAttempted = true; // at most one all-waves attempt
            if (killWavesLocked(0, true)) gq[w.queue].killedAll = true;
            w.terminal = true;
            return;
        }
        if (exactVMFault) return;
        uint64_t retired, done[2]{};
        uint32_t oldest[2]{UINT32_MAX, UINT32_MAX};
        if (!exactGlobalRetiredLocked(retired)) return;
        for (uint32_t i = 0; i < 2; ++i)
            if (!watchdogQueueLocked(i, done[i], oldest[i])) return;
        const uint64_t now = mach_absolute_time();
        const uint64_t limitNs = static_cast<uint64_t>(limitMs) * 1000000ull;
        for (uint32_t qi = 0; qi < 2; ++qi) {
            GpuQueue &q = gq[qi];
            if (!q.ready) continue;
            if (oldest[qi] == UINT32_MAX || q.lastDone != done[qi]) {
                q.lastDone = done[qi]; q.lastProgress = now;
                continue;
            }
            uint64_t elapsed = 0;
            absolutetime_to_nanoseconds(now - q.lastProgress, &elapsed);
            if (elapsed < limitNs) continue;
            if (!captureWatchdogLocked(qi, oldest[qi], done[qi], limitNs)) {
                if (w.active) w.terminal = true;
                return;
            }
            uint64_t latest;
            if (!readWatchdogRecoveryLocked(&latest) || latest >= w.sequence) {
                w.terminal = true;
                return;
            }
            if (killWavesLocked(w.vmid, false)) {
                w.started = mach_absolute_time();
                q.killedSeq = w.sequence; q.killedAll = false;
            } else w.terminal = true;
            return; // one frozen recovery episode; other queue metadata cannot be reset
        }
    };
    check();
    IOLockUnlock(gpuLock);
}
'''


def stage(source):
    source = previous_stage(source)
    source = once(source, '        uint32_t fvmid[64];',
                  '        uint64_t fallocation[64]; // immutable context allocation generation per submission\n'
                  '        uint32_t fctx[64]; // immutable context handle; VMID alone is reusable\n'
                  '        uint32_t fvmid[64];')
    source = once(source, '    bool vmWorkCurrent(const VmCtx &) const; // gpuLock held\n',
                  FIELDS + '    bool vmWorkCurrent(const VmCtx &) const; // gpuLock held\n')
    source = once(source, '    void killWaves(uint32_t vmid, bool all);\n', '')
    old = method(source, 'IOReturn PhxBringup::adoptQueue(')
    new = once(old, '    if (exactStopped || isSleeping) {',
               '    if (exactStopped || isSleeping || exactVMFault) {')
    new = once(new, '    q.wptr = q.doneEnd = wptr;\n',
               '    q.wptr = q.doneEnd = wptr;\n'
               '    q.lastDone = gSeq; q.lastProgress = mach_absolute_time();\n')
    source = once(source, old, new)
    old = method(source, 'IOReturn PhxBringup::gpuSubmit(')
    new = once(old, '    GpuQueue *qp = nullptr;\n',
               '    GpuQueue *qp = nullptr;\n    bool startsPending = false;\n')
    new = once(new, '    q.fvmid[q.tail & 63] = vmid;\n',
               '    q.fvmid[q.tail & 63] = vmid;\n'
               '    q.fctx[q.tail & 63] = handle;\n'
               '    q.fallocation[q.tail & 63] = generation;\n')
    new = once(new, '            if (vmid) break; // keep the lock through publication/packet/doorbell\n',
               '            if (vmid) {\n'
               '                if (q.head == q.tail) { // idle time never counts against a new pending batch\n'
               '                    q.lastDone = done; startsPending = true;\n'
               '                }\n'
               '                break; // keep the lock through publication/packet/doorbell\n'
               '            }\n')
    new = once(new, '    *reinterpret_cast<volatile uint64_t *>(doorbellMap->getVirtualAddress() + q.dbByte) = q.wptr;\n',
               '    *reinterpret_cast<volatile uint64_t *>(doorbellMap->getVirtualAddress() + q.dbByte) = q.wptr;\n'
               '    if (startsPending) q.lastProgress = mach_absolute_time(); // exclude pre-doorbell CPU delay\n')
    source = once(source, old, new)
    source = once(source, '// Every 500 ms: a queue with unfinished work whose fence has not moved for debug.phx_hang_ms has the waves of its oldest\n'
                  '// unfinished submission killed, the CP then finishes that submission as if it had ended and the queue moves on.\n',
                  '// Every 500 ms: checked pending work may enter one bounded recovery episode.\n'
                  '// Recovery never turns killed work into successful completion or resource-release proof.\n')
    source = once(source, method(source, 'void PhxBringup::hangCheck('), HANG.rstrip() + '\n')
    source = once(source, method(source, 'void PhxBringup::killWaves('),
                  '\n'.join([QUEUE, CAPTURE, CURRENT, READ, KILL]))
    if 'PhxBringup::killWaves(' in source or 'killWaves(q.' in source:
        raise ValueError('Unserialized recovery caller remains')
    return source
