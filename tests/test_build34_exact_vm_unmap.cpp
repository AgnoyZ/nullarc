
static void logicalOnly(bool activate) {
    reset();
    PhxBringup service;
    IOAccelPhxNativeClient client;
    setup(service, client);
    IOMemoryDescriptor host;
    std::vector<uint8_t> bytes(4096);
    attach(client, 1, host, bytes, 2, true);
    service.gq[0].ready = service.gq[1].ready = false;
    CHECK(map(client) == kIOReturnSuccess && !client.vmid && client.maps[0].used);
    CHECK(!host.segments && tableStorage.empty());
    if (activate) {
        service.gq[0].ready = service.gq[1].ready = true;
        IOLockLock(client.lock);
        CHECK(client.ensureVmid());
        IOLockUnlock(client.lock);
        CHECK(service.vm[client.vmid - 1].used == 1 && tableStorage.size() == 1);
    }
    const auto flushes = lineFlushes.load();
    CHECK(boFree(client) == kIOReturnSuccess);
    CHECK(!client.maps[0].used && !client.bos[1].md && !client.hostUsed && !service.exactVMFault);
    CHECK(host.completes == 1 && host.releases == 1 && !host.segments && lineFlushes == flushes);
}

static void resident(const char *scenario) {
    reset();
    PhxBringup service;
    IOAccelPhxNativeClient client;
    setup(service, client);
    IOMemoryDescriptor host, filler;
    std::vector<uint8_t> bytes(8192);
    attach(client, 1, host, bytes, 2, true);
    IOLockLock(client.lock);
    CHECK(client.ensureVmid());
    IOLockUnlock(client.lock);
    const auto handle = client.vmid;
    const auto generation = client.vmGeneration;
    auto &context = service.vm[handle - 1];
    for (unsigned index = 0; index < 12; ++index) {
        const uint64_t va = 0x10000 + (static_cast<uint64_t>(index) << 21);
        CHECK(service.vmMap(handle, generation, &client, va, &filler, 0, 4096) == kIOReturnSuccess);
    }
    constexpr uint64_t boundary = 13ull << 21;
    CHECK(context.used == 15 && tableStorage.size() == 1);
    CHECK(map(client, 1, boundary - 4096, 0, bytes.size()) == kIOReturnSuccess);
    CHECK(context.used == 17 && tableStorage.size() == 2 && host.segments == 2);
    IOLockLock(service.gpuLock);
    auto *first = service.vmPte(context, boundary - 4096, false);
    auto *second = service.vmPte(context, boundary, false);
    const auto hw = service.vmBind(handle, generation, &client, service.gSeq);
    IOLockUnlock(service.gpuLock);
    CHECK(hw == kFirstUserVmid && first && second && *first && *second);
    const auto originalMap = client.maps[0];
    auto *chunk = context.chunk[1];
    CHECK(chunk && second == chunk->words.data());
    const auto secondPte = *second;
    const auto writes = service.registers.size();
    const auto flushes = lineFlushes.load();
    const bool missingChunk = !std::strcmp(scenario, "missing-chunk");
    const bool missingView = !std::strcmp(scenario, "missing-view");
    const bool ok = !std::strcmp(scenario, "resident");
    CHECK(ok || missingChunk || missingView);
    auto removal = mapping(1, boundary - 4096, 0, bytes.size());
    removal.operation = PHX_AMDGPU_VA_OP_UNMAP;
    if (missingChunk) context.chunk[1] = nullptr;
    if (missingView) chunk->mapped = false;
    if (ok) eventHook = [&](const char *name) {
        if (!std::strcmp(name, "register-write")) {
            CHECK(!*first && !*second && host.alive && mapsEqual(client.maps[0], originalMap));
            CHECK(lineFlushes == flushes + 2 && service.registers.back().first == kRegInvEng17Req);
        } else if (!std::strcmp(name, "md-complete")) {
            CHECK(service.registers.size() == writes + 1 && !client.bos[1].md && !client.maps[0].used);
        }
    };
    const auto result = missingView ? gem(client, removal) : boFree(client);
    eventHook = {};
    const bool falseSuccess = !ok && result == kIOReturnSuccess;
    if (falseSuccess) {
        CHECK(!client.maps[0].used && !*first && *second == secondPte);
        if (missingView) CHECK(boFree(client) == kIOReturnSuccess);
        CHECK(!client.bos[1].md && host.completes == 1 && host.releases == 1);
    }
    CHECK(!falseSuccess);
    CHECK(result == (ok ? kIOReturnSuccess : kIOReturnVMError));
    if (ok) {
        CHECK(!client.hostUsed && !client.boCleanupFault && !service.exactVMFault);
        CHECK(host.completes == 1 && host.releases == 1 && service.registers.size() == writes + 1);
        return;
    }
    CHECK(!*first && *second == secondPte && lineFlushes == flushes + 1);
    CHECK(service.exactVMFault && client.boCleanupFault && service.registers.size() == writes);
    CHECK(client.hostUsed == bytes.size() && client.bos[1].md == &host && !client.releasePermit);
    CHECK(mapsEqual(client.maps[0], originalMap) && host.alive && host.prepared && !host.completes && !host.releases);
    context.chunk[1] = chunk;
    chunk->mapped = true;
    CHECK(boFree(client) == kIOReturnNotReady && gem(client, removal) == kIOReturnNotReady);
    CHECK(!service.vmidFree(handle, generation, &client, 0));
    IOAccelPhxNativeClient other;
    uint64_t newGeneration = 0;
    CHECK(!service.vmidAlloc(&other, &newGeneration) && !newGeneration);
    CHECK(context.busy && context.generation == generation && context.hw == hw);
    CHECK(service.hwv[hw - kFirstUserVmid].ctx == handle && service.registers.size() == writes);
    CHECK(host.alive && !host.completes && !host.releases && *second == secondPte);
}

int main(int argc, char **argv) {
    CHECK(argc == 2);
    if (!std::strcmp(argv[1], "no-context")) logicalOnly(false);
    else if (!std::strcmp(argv[1], "empty-branch")) logicalOnly(true);
    else resident(argv[1]);
    CHECK(groups == 1 && threaded == 0);
    std::printf("PASS %llu checks; GPU_executed=false\n", static_cast<unsigned long long>(checks.load()));
}
