#include <stdio.h>
#include <string.h>

#include "../src/nmplugin/nvmtl_video_decode_gate.h"

static int failures;

static void expect(const char *name, int actual, int expected)
{
    if (actual != expected) {
        fprintf(stderr, "FAIL %s: got %d, expected %d\n", name, actual, expected);
        failures++;
    }
}

int main(void)
{
    expect("AMD opt-in", nvmtl_nmxvt_registration_allowed(0x1002, "Zen", "1"), 1);
    expect("AMD decode service opt-in", nvmtl_nmxvt_registration_allowed(0x1002, "VTDecoderXPCService", "1"), 1);
    expect("off by default", nvmtl_nmxvt_registration_allowed(0x1002, "Zen", NULL), 0);
    expect("zero disables", nvmtl_nmxvt_registration_allowed(0x1002, "Zen", "0"), 0);
    expect("noncanonical opt-in refused", nvmtl_nmxvt_registration_allowed(0x1002, "Zen", "true"), 0);
    expect("WindowServer excluded", nvmtl_nmxvt_registration_allowed(0x1002, "WindowServer", "1"), 0);
    expect("NVIDIA excluded", nvmtl_nmxvt_registration_allowed(0x10de, "Zen", "1"), 0);
    expect("Intel excluded from AMD fork", nvmtl_nmxvt_registration_allowed(0x8086, "Zen", "1"), 0);
    expect("missing process refused", nvmtl_nmxvt_registration_allowed(0x1002, NULL, "1"), 0);

    if (failures) return 1;
    puts("video decode registration gate: all cases passed");
    return 0;
}
