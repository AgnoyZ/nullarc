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
            if (!reader.readDword(reader.ioContext, base + field, value) || value || !inactive()) return false;
        }
        return true;
    }

    template<typename Inactive, typename WriteAllowed>
    static bool install(const DcnFlatContext &context, const HubpFlipReader &reader, HubpFlipWriter writer,
                        const Inactive &inactive, const WriteAllowed &writeAllowed) {
        if (!context.valid() || !writer.writeDword || !writer.delayUs || !empty(context.vmid, reader, inactive)) return false;
        const uint32_t base = dcnVm::base(context.vmid);
        const auto write = [&](uint32_t field, uint32_t value) {
            return writeAllowed() && inactive() && writer.writeDword(reader.ioContext, base + field, value);
        };
        const uint32_t rootLow = static_cast<uint32_t>(context.rootEntry);
        uint32_t low = 0;
        if (!write(3, static_cast<uint32_t>(context.firstPage >> 32)) || !write(4, static_cast<uint32_t>(context.firstPage)) ||
            !write(5, static_cast<uint32_t>(context.lastPage >> 32)) || !write(6, static_cast<uint32_t>(context.lastPage)) ||
            !write(0, 0) || !write(1, static_cast<uint32_t>(context.rootEntry >> 32)) ||
            !inactive() || !reader.readDword(reader.ioContext, base + 2, low) || low || !write(2, rootLow)) return false;

        for (unsigned attempt = 0; attempt < 10; ++attempt) {
            if (!inactive() || !reader.readDword(reader.ioContext, base + 2, low)) return false;
            if (low == rootLow) return matchDcnFlatContext(context, reader, inactive);
            if (low && low != (rootLow & ~1u)) return false;
            if (attempt < 9 && inactive()) writer.delayUs(reader.ioContext, 1);
        }
        return false;
    }

    template<typename Current, typename WriteAllowed>
    static bool clear(const DcnFlatContext &context, const HubpFlipReader &reader, HubpFlipWriter writer,
                      const Current &current, const WriteAllowed &writeAllowed) {
        if (!writer.writeDword || !context.valid() || !canReadDcnContext(context.vmid, reader)) return false;
        const uint32_t base = dcnVm::base(context.vmid);
        constexpr uint32_t order[]{3, 4, 5, 6, 0, 1, 2};
        uint32_t expected[]{0, static_cast<uint32_t>(context.rootEntry >> 32), static_cast<uint32_t>(context.rootEntry),
            static_cast<uint32_t>(context.firstPage >> 32), static_cast<uint32_t>(context.firstPage),
            static_cast<uint32_t>(context.lastPage >> 32), static_cast<uint32_t>(context.lastPage)};
        for (const auto field : order) {
            if (!writeAllowed()) return false;
            for (uint32_t offset = 0; offset < dcnVm::kStride; ++offset) {
                uint32_t value = 0;
                if (!current() || !reader.readDword(reader.ioContext, base + offset, value) || value != expected[offset])
                    return false;
            }
            if (!current() || !writer.writeDword(reader.ioContext, base + field, 0)) return false;
            expected[field] = 0;
        }
        return empty(context.vmid, reader, current);
    }
};

}
