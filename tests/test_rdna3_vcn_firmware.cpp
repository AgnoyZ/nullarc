#include "rdna3_vcn_firmware.h"
#include <assert.h>
#include <stdint.h>
#include <vector>

using namespace rdna3;

static void write_u16_le(std::vector<uint8_t> &data, size_t offset, uint16_t value) {
    data[offset] = static_cast<uint8_t>(value);
    data[offset + 1] = static_cast<uint8_t>(value >> 8);
}

static void write_u32_le(std::vector<uint8_t> &data, size_t offset, uint32_t value) {
    data[offset] = static_cast<uint8_t>(value);
    data[offset + 1] = static_cast<uint8_t>(value >> 8);
    data[offset + 2] = static_cast<uint8_t>(value >> 16);
    data[offset + 3] = static_cast<uint8_t>(value >> 24);
}

static void rejected(const char *name, const std::vector<uint8_t> &data, const VcnFirmwareProfile &profile) {
    VcnFirmwareImage image{1, 2, 3};
    assert(!vcn_firmware_image_parse(name, data.data(), data.size(), profile, image));
    assert(image.version == 0 && image.payload_offset == 0 && image.payload_size == 0);
}

static std::vector<uint8_t> valid_image() {
    std::vector<uint8_t> data(96, 0);
    write_u32_le(data, 0, static_cast<uint32_t>(data.size()));
    write_u32_le(data, 4, 48);
    write_u16_le(data, 8, 1);
    write_u16_le(data, 10, 0);
    write_u16_le(data, 12, 4);
    write_u16_le(data, 14, 0);
    write_u32_le(data, 16, 0x04001234);
    write_u32_le(data, 20, 32);
    write_u32_le(data, 24, 64);
    return data;
}

int main() {
    const VcnFirmwareProfile profile = {{4, 0, 2}, "vcn_4_0_2.bin"};
    const VcnFirmwareProfile other_revision = {{4, 0, 3}, "vcn_4_0_3.bin"};
    VcnFirmwareImage image{};
    std::vector<uint8_t> data = valid_image();

    assert(vcn_firmware_image_parse("vcn_4_0_2.bin", data.data(), data.size(), profile, image));
    assert(image.version == 0x04001234);
    assert(image.payload_offset == 64);
    assert(image.payload_size == 32);
    rejected("vcn_4_0_3.bin", data, profile);
    rejected("vcn_4_0_3.bin", data, other_revision);
    assert(!vcn_firmware_image_parse("vcn_4_0_2.bin", nullptr, data.size(), profile, image));
    assert(!vcn_firmware_image_parse("vcn_4_0_2.bin", data.data(), 31, profile, image));

    auto malformed = data;
    write_u32_le(malformed, 0, 95);
    rejected("vcn_4_0_2.bin", malformed, profile);
    malformed = data;
    write_u32_le(malformed, 4, 31);
    rejected("vcn_4_0_2.bin", malformed, profile);
    malformed = data;
    write_u32_le(malformed, 4, 97);
    rejected("vcn_4_0_2.bin", malformed, profile);
    malformed = data;
    write_u16_le(malformed, 8, 3);
    rejected("vcn_4_0_2.bin", malformed, profile);
    malformed = data;
    write_u16_le(malformed, 10, 1);
    rejected("vcn_4_0_2.bin", malformed, profile);
    malformed = data;
    write_u16_le(malformed, 12, 5);
    rejected("vcn_4_0_2.bin", malformed, profile);
    malformed = data;
    write_u32_le(malformed, 20, 0);
    rejected("vcn_4_0_2.bin", malformed, profile);
    malformed = data;
    write_u32_le(malformed, 24, 47);
    rejected("vcn_4_0_2.bin", malformed, profile);
    malformed = data;
    write_u32_le(malformed, 24, UINT32_MAX);
    rejected("vcn_4_0_2.bin", malformed, profile);
    const VcnFirmwareProfile wrong_name = {{4, 0, 2}, "vcn.bin"};
    rejected("vcn.bin", data, wrong_name);
    return 0;
}
