/* SPDX-License-Identifier: MIT */
#include <IOKit/IOKitLib.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static char *mockEnv(const char *);
static int mockOpen(void);
static kern_return_t mockClose(io_connect_t client) { (void)client; return KERN_SUCCESS; }
static int mockPrint(const char *format, ...) { (void)format; return 0; }
static int mockSleep(useconds_t duration) { (void)duration; return 0; }
#define IOServiceClose mockClose
#define getenv mockEnv
#define printf mockPrint
#define usleep mockSleep
#define main mesboot_main
#include "cpu-mesboot.inc"
#undef main
#undef printf
#undef IOConnectCallScalarMethod
#undef IOConnectCallMethod

static unsigned checks;
#define CHECK(cond) do { ++checks; if (!(cond)) { fprintf(stderr, "failed %d: %s\n", __LINE__, #cond); exit(86); } } while (0)

static uint32_t words[(0x2590000u - KIQ_RING) / 4];
static uint32_t regs[0x10000];
static unsigned opens, mesBells, cmpBells, gfxBells, adoptions, accepted, traffic;
static unsigned mesPublished, cmpPublished, gfxPublished, mesPolls;
static unsigned badMes, badMesStatus, lateMes, badCmp, badGfx, rejectAdoption, missingGfx, noClearState;
static unsigned staleMes, staleCmp, staleGfx, shortSelector, failedBell;

static uint32_t *word(uint64_t addr)
{
    if (addr < KIQ_RING || (addr & 3) || (addr - KIQ_RING) / 4 >= sizeof(words) / sizeof(words[0])) abort();
    return &words[(addr - KIQ_RING) / 4];
}

static char *mockEnv(const char *name)
{
    if (!strcmp(name, "ADOPT_GFX")) return missingGfx ? NULL : "1";
    if (!strcmp(name, "NO_CSB")) return noClearState ? "1" : NULL;
    if (!strcmp(name, "ADOPT") || !strcmp(name, "MESBOOT_CS") || !strcmp(name, "MESBOOT_MC") || !strcmp(name, "MESBOOT_GFX")) return "1";
    return NULL;
}

static int mockOpen(void)
{
    ++opens;
    conn = 19;
    const struct Phx34Geometry synthetic = {0x8000000000ull, 0x10000000ull, 0x10000000ull, 0x10000000ull};
    phx34_ready = phx34_plan(&synthetic, &phx34_live);
    return !phx34_ready;
}

/* Resolve the fake transport below the unchanged layout wrappers. */
kern_return_t IOConnectCallScalarMethod(io_connect_t client, uint32_t selector, const uint64_t *in,
                                        uint32_t count, uint64_t *out, uint32_t *outCount)
{
    ++traffic;
    if (client != conn || failedBell == 0xffffffffu) abort();
    if (selector == SEL_DBG_ADOPTQ) {
        if (count != 6 || adoptions >= 2) abort();
        unsigned queue = in[5] & 1u;
        if (!queue && (accepted || in[0] != CMP_RING || in[1] != 1024 || in[2] != CMP_WB ||
                       in[3] != 24 || in[4] != 8 || in[5] != 0x2550000)) abort();
        if (queue && ((accepted & 2) || in[0] != GFX_RING || in[1] != GFX_RDW || in[2] != GFX_WB ||
                      in[3] != GFX_DB * 4 || in[4] != sizeof(kCsbGfx11) / 4 + 8 || in[5] != 0x2580001)) abort();
        if (++adoptions == rejectAdoption) return KERN_FAILURE;
        accepted |= 1u << queue;
        return KERN_SUCCESS;
    }
    if (accepted) abort();
    if (selector == SEL_DBG_WRITE_REG) {
        if (count != 2 || !outCount || *outCount != 1 || in[0] >= sizeof(regs) / sizeof(regs[0])) abort();
        regs[in[0]] = (uint32_t)in[1];
        out[0] = regs[in[0]];
        if (shortSelector == selector) *outCount = 0;
    } else if (selector == SEL_DBG_VRAM_WRITE) {
        if (count != 2) abort();
        *word(in[0]) = (uint32_t)in[1];
        if (in[1] && in[0] == SCH_WB + 16) ++mesPublished;
        if (in[1] && in[0] == CMP_WB + 16) ++cmpPublished;
        if (in[1] && in[0] == GFX_WB + 16) ++gfxPublished;
    } else if (selector == SEL_DBG_DOORBELL) {
        if (count != 3) abort();
        if (in[0] == 0x16 * 4) {
            ++mesBells;
            if (mesPublished != mesBells) abort();
            *word(SCH_WB + 64) = mesBells == badMesStatus ? 0 : 1;
            if (mesBells != badMes && mesBells != lateMes) *word(SCH_WB + 32) = (uint32_t)sch_seq;
        } else if (in[0] == 24) {
            ++cmpBells;
            if (cmpPublished != cmpBells) abort();
            if (!badCmp) { regs[SEG1(0x2040)] = 0xDEADBEEF; *word(TESTBUF) = 0xFEEDF00D; }
        } else if (in[0] == GFX_DB * 4) {
            ++gfxBells;
            if (gfxPublished != gfxBells) abort();
            if (!badGfx) { regs[SEG1(0x2041)] = 0xDEADBEEF; *word(TESTBUF + 0x40) = 0x6F7A6F7A; }
        } else abort();
        if (in[0] == failedBell) { failedBell = 0xffffffffu; return KERN_FAILURE; }
    } else abort();
    return KERN_SUCCESS;
}

kern_return_t IOConnectCallMethod(io_connect_t client, uint32_t selector, const uint64_t *in, uint32_t count,
                                  const void *structure, size_t structureSize, uint64_t *out, uint32_t *outCount,
                                  void *buffer, size_t *size)
{
    ++traffic;
    if (client != conn || structure || structureSize || out || outCount || accepted || failedBell == 0xffffffffu) abort();
    uint32_t *values = buffer;
    if (selector == SEL_READREGS) {
        if (count != 3 || in[1] != 1 || *size != 4 || in[0] >= sizeof(regs) / sizeof(regs[0])) abort();
        values[0] = regs[in[0]];
    } else if (selector == SEL_DBG_VRAM_READ) {
        if (count != 2 || in[1] != 4 || *size != 16) abort();
        if (lateMes && mesBells == lateMes && in[0] == SCH_WB + 32 && ++mesPolls == 401)
            *word(SCH_WB + 32) = (uint32_t)sch_seq;
        for (unsigned idx = 0; idx < 4; ++idx) values[idx] = *word(in[0] + idx * 4);
        if (staleMes && !mesBells && in[0] == SCH_WB + 32) values[0] = (uint32_t)sch_seq;
        if (staleCmp && !cmpBells && in[0] == TESTBUF) values[0] = 0xFEEDF00D;
        if (staleGfx && !gfxBells && in[0] == TESTBUF + 0x40) values[0] = 0x6F7A6F7A;
    } else abort();
    if (shortSelector == selector) *size -= 4;
    return KERN_SUCCESS;
}

static void reset(void)
{
    memset(words, 0, sizeof(words)); memset(regs, 0, sizeof(regs));
    opens = mesBells = cmpBells = gfxBells = adoptions = accepted = traffic = 0;
    mesPublished = cmpPublished = gfxPublished = mesPolls = 0;
    badMes = badMesStatus = lateMes = badCmp = badGfx = rejectAdoption = missingGfx = noClearState = 0;
    staleMes = staleCmp = staleGfx = shortSelector = failedBell = 0;
    phx34_ready = 0;
    phx34AdoptionPending = phx34AdoptionFault = 0;
    memset(phx34Adoption, 0, sizeof(phx34Adoption));
#ifdef CHECKED_STAGE
    phx34CheckedBoot = false;
#endif
}

static int invoke(void)
{
    char program[] = "mesboot", mode[] = "kiqsched";
    char *argv[] = {program, mode, NULL};
    return mesboot_main(2, argv);
}

int main(int argc, char **argv)
{
    reset();
    if (argc == 2) {
        if (!strcmp(argv[1], "doorbell")) failedBell = 24;
        else if (!strcmp(argv[1], "short-reply")) shortSelector = SEL_READREGS;
        else if (!strcmp(argv[1], "second-adoption")) rejectAdoption = 2;
        else return 86;
        return invoke();
    }
    CHECK(invoke() == 0 && opens == 1 && mesBells == 4 && cmpBells == 1 && gfxBells == 1 && adoptions == 2 && accepted == 3);
#ifdef CHECKED_STAGE
    for (unsigned phase = 1; phase <= 4; ++phase) {
        reset(); badMes = phase;
        CHECK(invoke() == 74 && mesBells == phase && !adoptions && cmpBells == (phase == 4) && !gfxBells);
    }
    reset(); badMesStatus = 1; CHECK(invoke() == 74 && mesBells == 1 && !adoptions);
    reset(); lateMes = 1; CHECK(invoke() == 74 && mesBells == 1 && mesPolls == 401 && !adoptions);
    reset(); badCmp = 1; CHECK(invoke() == 74 && cmpBells == 1 && !gfxBells && !adoptions);
    reset(); badGfx = 1; CHECK(invoke() == 74 && gfxBells == 1 && !adoptions);
    reset(); staleMes = 1; CHECK(invoke() == 74 && !mesPublished && !mesBells && !adoptions);
    reset(); staleCmp = 1; CHECK(invoke() == 74 && mesBells == 3 && !cmpPublished && !cmpBells && !adoptions);
    reset(); staleGfx = 1; CHECK(invoke() == 74 && mesBells == 4 && !gfxPublished && !gfxBells && !adoptions);
    reset(); missingGfx = 1; CHECK(invoke() == 74 && !opens && !traffic);
    reset(); noClearState = 1; CHECK(invoke() == 74 && !opens && !traffic);
#else
    reset(); badMes = 1; CHECK(invoke() == 0 && adoptions == 2 && accepted == 3);
    reset(); badMes = 2; CHECK(invoke() == 0 && adoptions == 2 && accepted == 3);
    reset(); badMesStatus = 1; CHECK(invoke() == 0 && adoptions == 2 && accepted == 3);
    reset(); lateMes = 1; CHECK(invoke() == 0 && adoptions == 2 && accepted == 3);
    reset(); badCmp = 1; CHECK(invoke() == 0 && adoptions == 2 && accepted == 3);
    reset(); badGfx = 1; CHECK(invoke() == 0 && adoptions == 2 && accepted == 3);
    reset(); badMes = 3; CHECK(invoke() == 0 && adoptions == 1 && accepted == 2);
    reset(); badMes = 4; CHECK(invoke() == 0 && adoptions == 1 && accepted == 1);
    reset(); missingGfx = 1; badMes = 3; CHECK(invoke() == 0 && !adoptions && !accepted);
#endif
    printf("PASS %u mesboot progress checks\n", checks);
    return 0;
}
