#include "rdna3_vcn_firmware.h"

namespace rdna3 {

namespace {

uint16_t read_u16_le(const uint8_t *data) {
    return static_cast<uint16_t>(data[0]) | (static_cast<uint16_t>(data[1]) << 8);
}

uint32_t read_u32_le(const uint8_t *data) {
    return static_cast<uint32_t>(data[0]) |
           (static_cast<uint32_t>(data[1]) << 8) |
           (static_cast<uint32_t>(data[2]) << 16) |
           (static_cast<uint32_t>(data[3]) << 24);
}

bool equal_string(const char *left, const char *right) {
    if (!left || !right)
        return false;
    while (*left && *right && *left == *right) {
        ++left;
        ++right;
    }
    return *left == '\0' && *right == '\0';
}

}

bool vcn_firmware_image_parse(const char *firmware_name,
                              const uint8_t *data,
                              size_t size,
                              const VcnFirmwareProfile &profile,
                              VcnFirmwareImage &image) {
    constexpr size_t common_header_size = 32;
    image = {};
    if (!firmware_name || !data || !profile.firmware_file || size < common_header_size || size > UINT32_MAX ||
        profile.ip.major != 4 || profile.ip.minor != 0 || profile.ip.revision != 2 ||
        !equal_string(profile.firmware_file, "vcn_4_0_2.bin") ||
        !equal_string(firmware_name, profile.firmware_file))
        return false;

    const uint32_t file_size = read_u32_le(data);
    const uint32_t header_size = read_u32_le(data + 4);
    const uint16_t header_major = read_u16_le(data + 8);
    const uint16_t header_minor = read_u16_le(data + 10);
    const uint16_t ip_major = read_u16_le(data + 12);
    const uint16_t ip_minor = read_u16_le(data + 14);
    const uint32_t version = read_u32_le(data + 16);
    const uint32_t payload_size = read_u32_le(data + 20);
    const uint32_t payload_offset = read_u32_le(data + 24);

    if (file_size != size || header_size < common_header_size || header_size > file_size ||
        !((header_major == 1 || header_major == 2) && header_minor == 0) || ip_major != profile.ip.major ||
        ip_minor != profile.ip.minor || payload_size == 0 || payload_offset < header_size ||
        static_cast<uint64_t>(payload_offset) + payload_size > file_size)
        return false;

    image.version = version;
    image.payload_offset = payload_offset;
    image.payload_size = payload_size;
    return true;
}

}
