// Actual VM/queue/client methods; CPU fakes only, including the fence read observer.
#define PHX_NO_BO_TEST_MAIN
#include "test_bo_retirement.cpp"
#include <cstdio>

static PhxBringup *active;
static std::vector<std::string> messages;
static bool expectGpuLock = true;
static void capture(const char *format, va_list arguments) {
    assert(active && bool(active->mutex) == expectGpuLock);
    char text[2048];
    const int length = vsnprintf(text, sizeof(text), format, arguments);
    assert(length > 0 && size_t(length) < sizeof(text));
    messages.emplace_back(text);
}
static void contains(const std::string &text) {
    assert(!messages.empty() && messages.back().find(text) != std::string::npos);
}
static void pending(PhxBringup &p, bool invalid = false) {
    p.aperture.words[32] = invalid ? 6 : 4;
}

int main(int argc, char **argv) {
    assert(argc == 2); const std::string test = argv[1];
    PhxBringup p; active = &p; logHook = capture;
    IOAccelPhxNativeClient c(p); IOMemoryDescriptor md;
    c.bos[1] = {&md, 8192, 2, 0, nullptr, false, false}; c.gttUsed = 8192;
    auto v = gem();
    if (test.rfind("progress-", 0) == 0) {
        using Reason = PhxQueueObservationReason;
        auto &q = p.gq[0]; Reason expected = Reason::Valid; bool read = true;
        if (test == "progress-missing-output") { expected = Reason::MissingOutput; read = false; }
        else if (test == "progress-no-aperture") { p.fbAper = nullptr; expected = Reason::NoAperture; read = false; }
        else if (test == "progress-inactive") { q.ready = false; expected = Reason::Inactive; read = false; }
        else if (test == "progress-unaligned-fence") { q.fenceOff++; expected = Reason::UnalignedFence; read = false; }
        else if (test == "progress-history-overflow") { q.tail = 64; expected = Reason::HistoryOverflow; read = false; }
        else if (test == "progress-future-floor") { q.retiredSeq = 6; expected = Reason::FutureFloor; read = false; }
        else if (test == "progress-all-ones-fence") { p.aperture.words[32] = UINT64_MAX; expected = Reason::AllOnesFence; }
        else if (test == "progress-regressed-fence") { p.aperture.words[32] = 3; expected = Reason::RegressedFence; }
        else if (test == "progress-future-fence") { p.aperture.words[32] = 6; expected = Reason::FutureFence; }
        else if (test == "progress-zero-sequence") { q.fseq[0] = 0; expected = Reason::ZeroSequence; }
        else if (test == "progress-nonmonotonic-sequence") { q.fseq[0] = 4; expected = Reason::NonmonotonicSequence; }
        else if (test == "progress-future-sequence") { q.fseq[0] = 6; expected = Reason::FutureSequence; }
        else if (test == "progress-unknown-fence") { q.retiredSeq = 2; q.fseq[0] = 5; p.aperture.words[32] = 4; expected = Reason::UnknownFence; }
        else if (test == "progress-pending") pending(p);
        else assert(test == "progress-complete");
        PhxQueueObservation observation; observation.done = 999; observation.fenceRead = true;
        uint64_t done = 777, plainDone = 777;
        IOLockLock(p.gpuLock);
        const bool result = p.queueProgress(q, test == "progress-missing-output" ? nullptr : &done, &observation);
        const unsigned reads = p.aperture.observations;
        const bool plain = p.queueProgress(q, test == "progress-missing-output" ? nullptr : &plainDone);
        IOLockUnlock(p.gpuLock);
        assert(result == plain && done == plainDone && result == (expected == Reason::Valid));
        assert(observation.reason == expected && observation.fenceRead == read && reads == unsigned(read));
        assert(p.aperture.observations == reads * 2 && messages.empty());
        assert(observation.done == (read ? p.aperture.words[32] : 0));
        assert(result || done == 777);
        assert(test.substr(9) == phxQueueObservationName(expected) || expected == Reason::Valid);
    } else if (test == "pending-overlap" || test == "pending-overlap-cap" || test == "ordinary-overlap-silent") {
        mapped(p, c); c.maps[0].pending = test != "ordinary-overlap-silent";
        const auto before = p.leaves; expectGpuLock = false;
        const unsigned attempts = test == "pending-overlap-cap" ? 300 : 1;
        for (unsigned i = 0; i < attempts; ++i)
            assert(gemCall(c, v) == (c.maps[0].pending ? kIOReturnBusy : kIOReturnBadArgument));
        assert(messages.size() == (c.maps[0].pending ? (attempts > 4 ? 4 : 1) : 0));
        if (c.maps[0].pending) { contains("op=GPU_MAP reason=pending-overlap"); contains("bytes=8192"); }
        assert(p.leaves == before && !p.aperture.observations && !p.writes && !p.allocations);
        assert(c.maps[0].used && !md.releases);
        assert(!c.allocationFailureLogs[1] && !c.allocationFailureLogs[2]);
        if (attempts > 4) assert(c.allocationFailureLogs[0] == 4);
    } else if (test == "retirement-cap-matrix") {
        mapped(p, c); const auto before = p.leaves;
        for (unsigned op = 0; op < 2; ++op) {
            for (unsigned invalid = 0; invalid < 2; ++invalid) {
                pending(p, invalid); const auto start = messages.size();
                auto request = gem(op == 1); if (!op) request.va_address += 0x20000;
                for (unsigned i = 0; i < 300; ++i) assert(gemCall(c, request) == kIOReturnBusy);
                assert(messages.size() == start + 4 && p.vm[0].busyLogs[op][invalid] == 4);
                contains("sample=4 limit=4");
            }
        }
        assert(messages.size() == 16 && p.leaves == before && !p.writes && !p.allocations);
        assert(!md.releases && !flushes && !delays);
    } else if (test == "independent-context-cap") {
        pending(p);
        for (unsigned i = 0; i < 300; ++i) assert(gemCall(c, v) == kIOReturnBusy);
        PhxBringup peer; active = &peer; pending(peer);
        IOAccelPhxNativeClient other(peer); other.bos[1] = c.bos[1];
        assert(gemCall(other, v) == kIOReturnBusy);
        assert(messages.size() == 5 && peer.vm[0].busyLogs[0][0] == 1 && p.vm[0].busyLogs[0][0] == 4);
    } else if (test == "diagnostic-sample-saturation") {
        for (unsigned seed : {0u, 3u, 4u, 255u}) {
            uint8_t count = seed;
            for (unsigned i = 0; i < 1024; ++i) {
                const unsigned before = count;
                assert(phxAllocationDiagnosticSample(count) == (before < 4));
                assert(count == (before < 4 ? before + 1 : before));
            }
        }
        assert(std::string(phxQueueObservationName(static_cast<PhxQueueObservationReason>(999))) == "unknown-reason");
    } else if (test == "bo-lifetime-unchanged") {
        mapped(p, c); pending(p);
        assert(freeBo(c) == kIOReturnSuccess); retained(c, md);
        assert(messages.size() == 1); contains("op=GPU_UNMAP reason=retirement-pending");
        p.aperture.words[32] = 5;
        c.reapPending(); released(c, md);
        assert(messages.size() == 1);
    } else {
        const bool unmap = test == "unmap-pending" || test == "unmap-invalid";
        if (unmap) { mapped(p, c); v = gem(true); }
        const auto before = p.leaves;
        if (test == "map-pending") pending(p);
        else if (test == "map-not-ready-silent") p.mmio = nullptr;
        else if (test == "map-zero-sequence-silent") p.vm[0].lastSeq = 0;
        else pending(p, test == "map-invalid" || test == "unmap-invalid" || test == "map-invalid-short-circuit");
        if (test == "map-other-queue-pending" || test == "map-other-queue-invalid") {
            p.gq[1] = p.gq[0]; p.gq[1].fenceOff = 0x180;
            p.gq[1].retiredSeq = 2; p.gq[1].fseq[0] = 3;
            p.aperture.words[32] = 5; p.aperture.words[48] = test == "map-other-queue-invalid" ? 6 : 2;
        }
        if (test == "map-invalid-short-circuit") { p.gq[1] = p.gq[0]; p.gq[1].fenceOff = 0x180; }
        if (test == "map-snapshot-once")
            p.aperture.observationHook = [&p] { if (p.aperture.observations > 1) p.aperture.words[32] = 5; };
        if (test == "reclaim-silent") {
            assert(p.vmCanReclaim(1) == kIOReturnBusy && messages.empty());
        } else {
            const auto result = gemCall(c, v);
            if (test == "map-not-ready-silent") assert(result == kIOReturnNotReady && messages.empty());
            else if (test == "map-zero-sequence-silent") assert(result == kIOReturnSuccess && messages.empty());
            else {
                assert(result == kIOReturnBusy && messages.size() == 1);
                contains(unmap ? "op=GPU_UNMAP" : "op=GPU_MAP");
                contains("last=5 submitted=5 retired=");
                const bool invalid = test.find("invalid") != std::string::npos;
                contains(invalid ? "reason=retirement-invalid" : "reason=retirement-pending");
                contains(invalid ? "future-fence" : "q0_reason=valid");
                contains(invalid ? "retired=0 " : test == "map-other-queue-pending" ? "retired=2 " : "retired=4 ");
                if (test == "map-other-queue-pending") { contains("q0_done=5"); contains("q1_pending=3"); }
                if (test == "map-other-queue-invalid") contains("q1_reason=future-fence");
                if (test == "map-invalid-short-circuit") { contains("q1_reason=unobserved q1_read=0"); assert(p.aperture.observations == 1); }
                if (test == "map-snapshot-once") { contains("q0_done=4"); assert(p.aperture.observations == 1); }
                if (!unmap) assert(!c.maps[0].used);
                else assert(c.maps[0].used && !c.maps[0].pending);
                assert(p.leaves == before && !p.writes && !p.allocations && !md.calls && !md.releases && !md.completes);
                assert(!flushes && !delays);
                if (test == "map-late-completion") {
                    p.aperture.words[32] = 5;
                    assert(gemCall(c, v) == kIOReturnSuccess && messages.size() == 1 && c.maps[0].used && !c.maps[0].pending);
                }
            }
        }
    }
    for (const auto &message : messages) {
        assert(message.rfind("PhxAlloc: v1 ", 0) == 0);
        for (const char *forbidden : {"0x10000", "0x400000", "0x200000", "0x180", "handle=", "pid=", "va=", "ptr="})
            assert(message.find(forbidden) == std::string::npos);
    }
    assert(!p.mutex);
    std::cout << "{\"case\":\"" << test << "\",\"passed\":true,\"hardware_executed\":false}\n";
}
