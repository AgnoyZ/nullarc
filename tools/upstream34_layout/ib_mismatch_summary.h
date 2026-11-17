/* SPDX-License-Identifier: MIT */
#ifndef PHX34_IB_MISMATCH_SUMMARY_H
#define PHX34_IB_MISMATCH_SUMMARY_H
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Read-only diagnostics after a mismatch and positive native retirement.
 * Counts describe CPU observations, never CP fetches or a coherency proof.
 * Do not print addresses, raw arena bytes, shader code or firmware contents. */
static inline void phx34ReportIbMismatch(const volatile uint8_t *actual,
    const uint8_t *expected, unsigned pass, size_t first_offset, uint8_t first_byte)
{
    constexpr size_t arena_bytes = 16384, output_begin = 0x2010, output_bytes = 1024;
    if (!actual || !expected || pass > 1 || first_offset >= arena_bytes) {
        fputs("IB-MISMATCH-SUMMARY {\"classification_valid\":false}\n", stderr);
        return;
    }
    uint8_t snapshot[arena_bytes];
    for (size_t i = 0; i < arena_bytes; ++i) snapshot[i] = actual[i];
    unsigned mismatch = 0, shader = 0, command = 0, output = 0, guard = 0;
    size_t snapshot_first = arena_bytes;
    for (size_t i = 0; i < arena_bytes; ++i) if (snapshot[i] != expected[i]) {
        if (!mismatch) snapshot_first = i;
        ++mismatch;
        if (i < 0x1000) ++shader;
        else if (i < 0x2000) ++command;
        else if (i >= output_begin && i < output_begin + output_bytes) ++output;
        else ++guard;
    }
    const uint32_t previous[4] = {0x7800c0deu, 0x13579bdfu, 0x2468ace0u, 0xc001d00du};
    unsigned current_words = 0, previous_words = 0, poisoned_words = 0, other_words = 0;
    for (unsigned i = 0; i < output_bytes / 4; ++i) {
        uint32_t value, want;
        memcpy(&value, snapshot + output_begin + i * 4, sizeof(value));
        memcpy(&want, expected + output_begin + i * 4, sizeof(want));
        if (value == want) ++current_words;
        else if (pass && value == previous[i & 3]) ++previous_words;
        else if (value == ~want) ++poisoned_words;
        else ++other_words;
    }
    unsigned changed_during_observation = 0;
    for (size_t i = 0; i < arena_bytes; ++i)
        if (actual[i] != snapshot[i]) ++changed_during_observation;
    fprintf(stderr,
        "IB-MISMATCH-SUMMARY {\"classification_valid\":true,\"pass\":%u,\"arena_bytes\":16384,"
        "\"first_snapshot_mismatch\":%zu,\"mismatch_bytes\":%u,\"shader_page_mismatch_bytes\":%u,"
        "\"command_page_mismatch_bytes\":%u,\"output_mismatch_bytes\":%u,\"guard_mismatch_bytes\":%u,"
        "\"output_current_words\":%u,\"output_previous_words\":%u,\"output_poison_words\":%u,\"output_other_words\":%u,"
        "\"original_mismatch_reobserved\":%s,\"changed_during_observation_bytes\":%u}\n",
        pass, snapshot_first, mismatch, shader, command, output, guard,
        current_words, previous_words, poisoned_words, other_words,
        snapshot[first_offset] == first_byte && snapshot[first_offset] != expected[first_offset] ? "true" : "false",
        changed_during_observation);
    fflush(stderr);
}
#endif
