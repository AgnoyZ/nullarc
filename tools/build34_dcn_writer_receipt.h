#pragma once

#include "build34_dcn_present_backing.h"
#include "build34_dcn_writer_wire.h"

namespace build34::dcn {

struct WriterMapIdentity {
    uint64_t mapping{}, preparation{}, vmAllocation{}, boOffset{};
    uint32_t vmContext{};

    bool matches(const WriterMapIdentity &other) const {
        return mapping && preparation && vmAllocation && vmContext && mapping == other.mapping &&
            preparation == other.preparation && vmAllocation == other.vmAllocation &&
            boOffset == other.boOffset && vmContext == other.vmContext;
    }
};

struct WriterMapping {
    WriterMapIdentity identity{};
    PinnedDescriptorSlice slice{};
};

inline bool sameWriterReceipt(const build34_dcn_native_submit &a, const build34_dcn_native_submit &b) {
    return build34_dcn_valid_native_submit(a, a.sequence) && a.owner != UINT64_MAX &&
        a.context && a.context <= PHXN_MAX_CTX && a.context == b.context &&
        a.sequence == b.sequence && a.owner == b.owner && a.serial == b.serial &&
        a.generation == b.generation && a.slot == b.slot && a.queue == b.queue;
}

struct WriterReceipt {
    build34_dcn_native_submit native{};
    build34_dcn_writer_range range{};
    WriterMapIdentity map{};
    bool complete{false};

    bool matches(const build34_dcn_native_submit &receipt, const build34_dcn_writer_range &span,
                 const WriterMapIdentity &current) const {
        return sameWriterReceipt(native, receipt) && range.va == span.va && range.bo == span.bo &&
            range.bytes == span.bytes && !span.reserved && map.matches(current);
    }
};

inline bool matchesNominatedIb(const phx34_r3_submit_request &submit, const build34_dcn_writer_nomination &nomination) {
    if (!build34_dcn_valid_writer_nomination(&nomination) || submit.submit.num_ibs > PHXN_MAX_IBS ||
        nomination.ib.index >= submit.submit.num_ibs)
        return false;
    constexpr uint64_t vaMask = (1ull << 48) - 1;
    for (uint32_t index = 0; index < submit.submit.num_ibs; ++index) {
        const auto &ib = submit.ibs[index];
        if (ib.ip_type != PHX_AMDGPU_HW_IP_GFX || ib.ip_instance || ib.ring)
            return false;
        if (index == nomination.ib.index) {
            if (ib.va_start != nomination.ib.va || ib.ib_bytes != nomination.ib.bytes ||
                (ib.flags & PHX_AMDGPU_IB_FLAG_PREAMBLE))
                return false;
        } else if ((ib.va_start & vaMask) == (nomination.ib.va & vaMask)) {
            return false;
        }
    }
    return true;
}

}
