/* SPDX-License-Identifier: MIT */
#include "base-fixture.inc"

static uint64_t statusSlots[4];
static unsigned replay, wrongMarker, dirtySlotWord, dirtyAfterPacketWord;

static void completeMes(uint64_t wptr)
{
    if (mesBells > 4 || wptr != mesBells * 2 * API_FRAME_SIZE_IN_DWORDS) abort();
    const uint64_t packet = SCH_RING + (wptr - 2 * API_FRAME_SIZE_IN_DWORDS) * 4;
    union MES_API_HEADER header;
    header.u32All = *word(packet);
    size_t offset;
    if (header.opcode == MES_SCH_API_SET_HW_RSRC) offset = offsetof(union MESAPI_SET_HW_RESOURCES, api_status);
    else if (header.opcode == MES_SCH_API_QUERY_SCHEDULER_STATUS) offset = offsetof(union MESAPI__QUERY_MES_STATUS, api_status);
    else if (header.opcode == MES_SCH_API_ADD_QUEUE) offset = offsetof(union MESAPI__ADD_QUEUE, api_status);
    else abort();
    const uint64_t field = packet + offset;
    const uint64_t address = ((uint64_t)*word(field + 4) << 32) | *word(field);
    if (address < VA(SCH_WB + 64) || address >= VA(SCH_WB + 128) || (address & 15) ||
        *word(field + 8) != 1 || *word(field + 12)) abort();
    const uint64_t slot = SCH_WB + (address - VA(SCH_WB));
    statusSlots[mesBells - 1] = slot;
    if (badMesStatus != mesBells && replay != mesBells) *word(slot) = wrongMarker == mesBells ? 7 : 1;
    if (replay == mesBells) *word(statusSlots[mesBells - 2]) = 1;
    if (mesBells == 1 && dirtySlotWord) *word(SCH_WB + 80 + 4 * (dirtySlotWord - 1)) = 7;
}

static void injectDuringPacket(uint64_t addr)
{
    if (dirtyAfterPacketWord && addr == SCH_RING + 2 * API_FRAME_SIZE_IN_DWORDS * 4 && mesBells == 1)
        *word(SCH_WB + 80 + 4 * (dirtyAfterPacketWord - 1)) = 7;
}

static void resetFaults(void)
{
    reset();
    memset(statusSlots, 0, sizeof(statusSlots));
    replay = wrongMarker = dirtySlotWord = dirtyAfterPacketWord = 0;
}

int main(int argc, char **argv)
{
    if (argc == 2) {
        if (strcmp(argv[1], "slots")) return progress_main(argc, argv);
    } else {
        return progress_main(argc, argv);
    }
    resetFaults();
    CHECK(invoke() == 0 && mesBells == 4 && cmpBells == 1 && gfxBells == 1 && adoptions == 2 && accepted == 3);
    for (unsigned i = 0; i < 4; ++i)
        CHECK(statusSlots[i] == SCH_WB + 64
#ifdef ISOLATED
              + 16 * i
#endif
        );
    for (unsigned phase = 2; phase <= 4; ++phase) {
        resetFaults();
        replay = phase;
#ifdef ISOLATED
        CHECK(invoke() == 74 && mesBells == phase && mesPublished == phase && !adoptions && !gfxBells);
        CHECK(*word(statusSlots[phase - 1]) == 0 && *word(statusSlots[phase - 2]) == 1);
#else
        CHECK(invoke() == 0 && mesBells == 4 && adoptions == 2 && accepted == 3);
#endif
    }
#ifdef ISOLATED
    resetFaults();
    wrongMarker = 2;
    CHECK(invoke() == 74 && mesBells == 2 && !adoptions);
    for (unsigned wordIndex = 1; wordIndex <= 4; ++wordIndex) {
        resetFaults();
        dirtySlotWord = wordIndex;
        CHECK(invoke() == 74 && mesBells == 1 && mesPublished == 1 && !adoptions);
        CHECK(*word(SCH_WB + 80 + 4 * (wordIndex - 1)) == 7);
        CHECK(*word(SCH_RING + 2 * API_FRAME_SIZE_IN_DWORDS * 4) == 0);
        resetFaults();
        dirtyAfterPacketWord = wordIndex;
        CHECK(invoke() == 74 && mesBells == 1 && mesPublished == 1 && !adoptions);
    }
    resetFaults();
    CHECK(!mockOpen());
    phx34CheckedBoot = true;
    sch_seq = 4;
    union MESAPI__QUERY_MES_STATUS q = {0};
    CHECK(mes_submit(&q, sizeof(q), offsetof(union MESAPI__QUERY_MES_STATUS, api_status), "fifth") == 1);
    CHECK(sch_seq == 4 && !traffic && !mesBells && !mesPublished);
#endif
    printf("PASS %u MES status checks\n", checks);
    return 0;
}
