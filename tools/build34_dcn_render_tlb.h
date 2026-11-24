#pragma once

#include <stdint.h>

namespace build34::dcn {

struct RenderMapIdentity {
    const void *client;
    uint64_t generation;
};

struct RenderVmTranslation {
    RenderMapIdentity mapping;
    const void *provider;
    uint64_t contextGeneration;
    uint64_t bindingGeneration;
    uint64_t tableGeneration;
    uint64_t invalidateGeneration;
    uint32_t context;
    uint32_t vmid;
};

inline bool validRenderGeneration(uint64_t value) {
    return value && value != UINT64_MAX;
}

inline bool sameRenderTranslation(const RenderVmTranslation &left, const RenderVmTranslation &right) {
    return left.mapping.client == right.mapping.client && left.mapping.generation == right.mapping.generation &&
           left.provider == right.provider && left.contextGeneration == right.contextGeneration &&
           left.bindingGeneration == right.bindingGeneration && left.tableGeneration == right.tableGeneration &&
           left.invalidateGeneration == right.invalidateGeneration && left.context == right.context &&
           left.vmid == right.vmid;
}

struct RenderTlbSample {
    RenderVmTranslation current;
    uint64_t elapsedNs;
    uint32_t ackBits;
};

class RenderTlbAck {
public:
    RenderTlbAck() = default;

    static RenderTlbAck observe(RenderVmTranslation request, void *context,
                                bool (*sample)(void *, RenderTlbSample *)) {
        if (!sample || !request.mapping.client || !request.provider || !request.context ||
            request.vmid < 8 || request.vmid > 15 || !validRenderGeneration(request.mapping.generation) ||
            !validRenderGeneration(request.contextGeneration) || !validRenderGeneration(request.bindingGeneration) ||
            !validRenderGeneration(request.tableGeneration) || !validRenderGeneration(request.invalidateGeneration))
            return {};

        const uint32_t mask = 1u << request.vmid;
        uint64_t previousElapsed = 0;
        bool observedClear = false;
        for (unsigned attempt = 0; attempt < 1000; ++attempt) {
            RenderTlbSample reading{};
            if (!sample(context, &reading) || !sameRenderTranslation(request, reading.current) ||
                reading.ackBits == UINT32_MAX || reading.elapsedNs < previousElapsed || reading.elapsedNs >= 1000000)
                return {};

            if (!(reading.ackBits & mask))
                observedClear = true;
            else if (observedClear) {
                RenderTlbAck result;
                result.translation_ = request;
                return result;
            }
            previousElapsed = reading.elapsedNs;
        }
        return {};
    }

    bool matches(const RenderVmTranslation &current) const {
        return translation_.provider && sameRenderTranslation(translation_, current);
    }

private:
    RenderVmTranslation translation_{};
};

}
