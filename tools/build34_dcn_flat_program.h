#pragma once

#include "build34_dcn_flat_context.h"
#include "build34_dcn_flip_program.h"

namespace build34::dcn {

class DcnFlatProgram {
    friend class ScanoutFlipCommit;

    template<typename Inactive>
    static bool empty(uint32_t vmid, const HubpFlipReader &reader, const Inactive &inactive) {
        if (!canReadDcnContext(vmid, reader) || !inactive()) return false;
        const uint32_t base = dcnVm::base(vmid);
        for (uint32_t field = 0; field < dcnVm::kStride; ++field) {
            uint32_t value = 0;
            if (!reader.readDword(reader.context, base + field, value) || value || !inactive()) return false;
        }
        return true;
    }

    template<typename Inactive>
    static bool install(const DcnFlatContext &context, const HubpFlipReader &reader, HubpFlipWriter writer,
                        const Inactive &inactive) {
        if (!context.valid() || !writer.writeDword || !writer.delayUs || !empty(context.vmid, reader, inactive)) return false;
        const uint32_t base = dcnVm::base(context.vmid);
        const auto write = [&](uint32_t field, uint32_t value) {
            return inactive() && writer.writeDword(reader.context, base + field, value);
        };
        const uint32_t rootLow = static_cast<uint32_t>(context.rootEntry);
        uint32_t low = 0;
        if (!write(3, static_cast<uint32_t>(context.firstPage >> 32)) || !write(4, static_cast<uint32_t>(context.firstPage)) ||
            !write(5, static_cast<uint32_t>(context.lastPage >> 32)) || !write(6, static_cast<uint32_t>(context.lastPage)) ||
            !write(0, 0) || !write(1, static_cast<uint32_t>(context.rootEntry >> 32)) ||
            !inactive() || !reader.readDword(reader.context, base + 2, low) || low || !write(2, rootLow)) return false;

        for (unsigned attempt = 0; attempt < 10; ++attempt) {
            if (!inactive() || !reader.readDword(reader.context, base + 2, low)) return false;
            if (low == rootLow) return matchDcnFlatContext(context, reader, inactive);
            if (low && low != (rootLow & ~1u)) return false;
            if (attempt < 9 && inactive()) writer.delayUs(reader.context, 1);
        }
        return false;
    }
};

}
