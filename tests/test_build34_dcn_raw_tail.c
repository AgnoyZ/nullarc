#include "mes-status-fixture.inc"

static unsigned missingTail, tornTail;

static void completeTail(uint64_t ring, uint64_t end, uint64_t fence, unsigned mask)
{
    const uint64_t packet = ring + (end - 8) * 4;
    CHECK(end > 8 && *word(packet) == 0xc0064900u && *word(packet + 4) == 0x06603514u &&
          *word(packet + 8) == 0x40000000u && !*word(packet + 28));
    CHECK((((uint64_t)*word(packet + 16) << 32) | *word(packet + 12)) == MC(fence));
    CHECK((*word(packet + 20) & 1) && (*word(packet + 24) & 0x80000000u));
    if (!(missingTail & mask)) *word(fence) = *word(packet + 20);
    if (!((missingTail | tornTail) & mask)) *word(fence + 4) = *word(packet + 24);
}

int main(void)
{
    resetFaults();
    CHECK(invoke() == 0 && mesBells == 4 && cmpBells == 1 && gfxBells == 1 && accepted == 3);
    for (unsigned queue = 1; queue <= 2; ++queue) {
        resetFaults();
        missingTail = queue;
        CHECK(invoke() == 74 && cmpBells == 1 && gfxBells == (queue == 2) && !adoptions);
        resetFaults();
        missingTail = 0;
        tornTail = queue;
        CHECK(invoke() == 74 && cmpBells == 1 && gfxBells == (queue == 2) && !adoptions);
        resetFaults();
        tornTail = 0;
        *word((queue == 1 ? PHX34_CMP_TAIL_FENCE : PHX34_GFX_TAIL_FENCE) + 4) = 7;
        CHECK(invoke() == 74 && cmpBells == (queue == 2) && !gfxBells && !adoptions);
    }
    return 0;
}
