#pragma once
#include <stddef.h>
#include <stdint.h>
#include "rdna3_chip_profile.h"

namespace rdna3 {

struct VcnFirmwareImage {
    uint32_t version;
    uint32_t payload_offset;
    uint32_t payload_size;
};

bool vcn_firmware_image_parse(const char *firmware_name,
                              const uint8_t *data,
                              size_t size,
                              const VcnFirmwareProfile &profile,
                              VcnFirmwareImage &image);

}
