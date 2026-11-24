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

class RenderInvalidateEdges {
public:
    explicit RenderInvalidateEdges(uint32_t mask) : mask_(mask) {}

    bool observe(uint32_t bits, uint64_t elapsed) {
        if (!mask_ || bits == UINT32_MAX || elapsed < previous_ || elapsed >= 1000000) {
            mask_ = 0;
            return false;
        }
        previous_ = elapsed;
        cleared_ |= ~bits & mask_;
        return (cleared_ & bits) == mask_;
    }

    bool failed() const { return mask_ == 0; }

private:
    uint32_t mask_, cleared_{0};
    uint64_t previous_{0};
};

class RenderTlbAck {
public:
    RenderTlbAck() = default;

    static RenderTlbAck observe(RenderVmTranslation request, void *context,
                                bool (*sample)(void *, RenderTlbSample *), uint32_t companionMask = 0) {
        if (!sample || !request.mapping.client || !request.provider || !request.context ||
            request.vmid < 8 || request.vmid > 15 || !validRenderGeneration(request.mapping.generation) ||
            !validRenderGeneration(request.contextGeneration) || !validRenderGeneration(request.bindingGeneration) ||
            !validRenderGeneration(request.tableGeneration) || !validRenderGeneration(request.invalidateGeneration))
            return {};

        const uint32_t mask = (1u << request.vmid) | companionMask;
        if ((mask & 0xffffu) != mask)
            return {};
        RenderInvalidateEdges edges(mask);
        for (unsigned attempt = 0; attempt < 1000; ++attempt) {
            RenderTlbSample reading{};
            if (!sample(context, &reading) || !sameRenderTranslation(request, reading.current))
                return {};
            if (edges.observe(reading.ackBits, reading.elapsedNs)) {
                RenderTlbAck result;
                result.translation_ = request;
                return result;
            }
            if (edges.failed())
                return {};
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
