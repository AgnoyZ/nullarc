/* SPDX-License-Identifier: MIT */
#ifndef PHX34_IB_TARGET_SUMMARY_H
#define PHX34_IB_TARGET_SUMMARY_H
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* CPU observations only. Neither a destination nor a pattern identifies what
 * the command processor fetched. Never print raw bytes or runtime addresses. */
static inline bool phx34ReportIbTargets(const volatile uint8_t *actual,
    const uint8_t *expected, unsigned pass, bool switched, size_t scan_first)
{
    constexpr size_t arena_bytes = 16384, region_bytes = 1024;
    constexpr size_t offsets[2] = {0x2010, 0x2810};
    if (!actual || !expected || pass > 1 || scan_first > arena_bytes) {
        fputs("IB-TARGET-SUMMARY {\"classification_valid\":false}\n", stderr);
        return false;
    }
    uint8_t snapshot[arena_bytes];
    for (size_t i = 0; i < arena_bytes; ++i) snapshot[i] = actual[i];
    unsigned mismatch = 0, shader = 0, command = 0, region[2]{}, guard = 0;
    size_t first = arena_bytes;
    for (size_t i = 0; i < arena_bytes; ++i) if (snapshot[i] != expected[i]) {
        if (!mismatch) first = i;
        ++mismatch;
        if (i < 0x1000) ++shader;
        else if (i < 0x2000) ++command;
        else if (i >= offsets[0] && i < offsets[0] + region_bytes) ++region[0];
        else if (i >= offsets[1] && i < offsets[1] + region_bytes) ++region[1];
        else ++guard;
    }
    const uint32_t previous[4] = {0x7800c0deu, 0x13579bdfu, 0x2468ace0u, 0xc001d00du};
    const uint32_t current[4] = {previous[0] ^ pass, previous[1] + pass,
        previous[2] ^ (pass << 16), previous[3] - pass};
    unsigned match[2]{}, now[2]{}, old[2]{}, poison[2]{}, other[2]{};
    for (unsigned r = 0; r < 2; ++r) for (unsigned i = 0; i < region_bytes / 4; ++i) {
        uint32_t value, want;
        memcpy(&value, snapshot + offsets[r] + i * 4, 4);
        memcpy(&want, expected + offsets[r] + i * 4, 4);
        if (value == want) ++match[r];
        if (value == current[i & 3]) ++now[r];
        else if (pass && value == previous[i & 3]) ++old[r];
        else if (value == ~current[i & 3]) ++poison[r];
        else ++other[r];
    }
    unsigned changed = 0;
    for (size_t i = 0; i < arena_bytes; ++i) if (actual[i] != snapshot[i]) ++changed;
    const bool passed = scan_first == arena_bytes && !mismatch && !changed;
    fprintf(stderr,
        "IB-TARGET-SUMMARY {\"classification_valid\":true,\"pass\":%u,\"policy\":\"target-%s\","
        "\"arena_bytes\":16384,\"selected_region\":\"%s\",\"first_scan_mismatch\":%zu,"
        "\"first_snapshot_mismatch\":%zu,\"mismatch_bytes\":%u,\"shader_page_mismatch_bytes\":%u,"
        "\"command_page_mismatch_bytes\":%u,\"a_mismatch_bytes\":%u,\"b_mismatch_bytes\":%u,"
        "\"guard_mismatch_bytes\":%u,\"a_expected_words\":%u,\"a_current_words\":%u,"
        "\"a_previous_words\":%u,\"a_poison_words\":%u,\"a_other_words\":%u,"
        "\"b_expected_words\":%u,\"b_current_words\":%u,\"b_previous_words\":%u,"
        "\"b_poison_words\":%u,\"b_other_words\":%u,\"changed_during_observation_bytes\":%u,"
        "\"validation_passed\":%s}\n",
        pass, switched ? "switch" : "control", switched && pass ? "B" : "A", scan_first,
        first, mismatch, shader, command, region[0], region[1], guard,
        match[0], now[0], old[0], poison[0], other[0],
        match[1], now[1], old[1], poison[1], other[1], changed, passed ? "true" : "false");
    fflush(stderr);
    return passed;
}
#endif
