#pragma once

struct IODMACommand;

struct IOMapper : OSObject {
    std::function<bool(const IODMACommand &, uint64_t, uint64_t &)> resolve;
    std::function<bool(const IODMACommand &)> confirmUnmap;
};
