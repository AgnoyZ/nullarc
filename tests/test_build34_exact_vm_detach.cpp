// SPDX-License-Identifier: MIT
// Appended to the existing CPU-only legacy close fixture, before its old cases.

static void closeAfterDetach(bool ack) {
    reset();
    PhxBringup d;
    IOAccelPhxNativeClient c;
    setup(d, c);
    d.vm[0].generation = 3; // simulate reuse of a previously reclaimed context slot
    IOMemoryDescriptor host;
    std::vector<uint8_t> bytes(4096);
    attach(c, 1, host, bytes, 2, true);
    CHECK(map(c) == kIOReturnSuccess);
    const auto seq = accepted(c);
    const auto handle = c.vmid;
    const auto generation = c.vmGeneration;
    CHECK(handle == 1 && generation == 4);
    auto &vm = d.vm[handle - 1];
    const auto hw = vm.hw;
    auto &slot = d.hwv[hw - kFirstUserVmid];
    d.setFence(1, seq);

    IOLockLock(d.gpuLock);
    CHECK(d.ptTablePhys(vm, 1));
    vm.used = 17;
    IOLockUnlock(d.gpuLock);
    const auto flushed = lineFlushes.load();
    const auto requests = d.registers.size();
    const auto reads = d.ackReads;
    const auto originalMap = c.maps[0];

    // An older allocation must not clear the table or request invalidation.
    CHECK(!d.vmidFree(handle, generation - 1, &c, seq));
    CHECK(!vm.closing && lineFlushes == flushed && d.registers.size() == requests);

    unsigned writes = 0, completions = 0;
    d.ackAfter = reads + 2;
    d.ackBits = ack ? (1u << hw) : 0;
    eventHook = [&](const char *name) {
        if (!std::strcmp(name, "register-write")) {
            CHECK(gpuHeld && d.registers.back().first == kRegInvEng17Req);
            CHECK(lineFlushes == flushed + 17 * 64);
            const auto zero = [](uint8_t b) { return b == 0; };
            CHECK(std::all_of(vm.chunk[0]->bytes.begin(), vm.chunk[0]->bytes.end(), zero));
            CHECK(std::all_of(vm.chunk[1]->bytes.begin(), vm.chunk[1]->bytes.begin() + 4096, zero));
            CHECK(vm.chunk[1]->bytes[4096] == 0xa5);
            CHECK(vm.busy && vm.closing && slot.ctx == handle && slot.generation == generation);
            CHECK(c.vmid == handle && c.bos[1].md == &host && host.alive && !host.completes);
            ++writes;
        } else if (!std::strcmp(name, "md-complete")) {
            CHECK(ack && writes == 1 && !gpuHeld && !vm.busy && !slot.ctx && !c.vmid);
            CHECK(d.ackReads == reads + 3);
            ++completions;
        }
    };
    CHECK(c.clientClose() == (ack ? kIOReturnSuccess : kIOReturnNotReady));
    eventHook = {};
    CHECK(writes == 1 && d.registers.size() == requests + 1);
    if (ack) {
        CHECK(completions == 1 && host.completes == 1 && host.releases == 1 && !host.alive);
        CHECK(!slot.generation && vm.generation == generation && !c.maps[0].used);
        CHECK(c.clientClose() == kIOReturnSuccess && host.completes == 1 && host.releases == 1);
        c.release();
        CHECK(c.finalized);
    } else {
        CHECK(d.exactVMFault && vm.busy && vm.closing && vm.generation == generation && vm.used == 17);
        CHECK(slot.ctx == handle && slot.generation == generation && vm.hw == hw);
        CHECK(c.vmid == handle && c.vmGeneration == generation && c.bos[1].md == &host && c.hostUsed == 4096);
        CHECK(mapsEqual(c.maps[0], originalMap) && !completions && host.alive && !host.completes && !host.releases);
        d.ackBits = 1u << hw; // a late level bit cannot authorize retry or release
        CHECK(!d.vmidFree(handle, generation, &c, seq));
        CHECK(c.clientClose() == kIOReturnNotReady);
        c.release();
        PhxBringup::hangTick(&d, nullptr);
        CHECK(d.registers.size() == requests + 1 && c.refs == 1 && c.legacyClientPinned && !c.finalized);
        CHECK(host.alive && !host.completes && !host.releases);
    }
}

int main() {
    closeAfterDetach(true);
    closeAfterDetach(false);
    CHECK(groups == 2 && threaded == 0);
    std::printf("PASS %llu checks; GPU_executed=false\n", static_cast<unsigned long long>(checks.load()));
}
