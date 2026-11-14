/* SPDX-License-Identifier: MIT OR GPL-2.0-only
 * Fixed read-only GC observation, not a readiness or ownership grant.
 * Numeric definitions reviewed against Linux 7d0a66e4bb9081d75c82ec4957c50034cb0ea449;
 * no Linux implementation bodies or headers copied. Never run on a stopped boot.
 */
#define main phx_mesboot_legacy_main
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-variable"
#include "mesboot.c"
#pragma clang diagnostic pop
#undef main
#include <fcntl.h>
#include <sys/stat.h>

static int observation_tmr_ready;
struct observation_register { const char *name; uint32_t index; };
static const struct observation_register observation_registers[] = {
   {"PSP_INITIALIZATION_STATUS", 0x16061},
   {"RCC_CONFIG_MEMSIZE", 0x0de3},
   {"GRBM_STATUS", SEG0(0x0da4)},
   {"GRBM_STATUS2", SEG0(0x0da2)},
   {"GB_ADDR_CONFIG", SEG0(0x13de)},
   {"CP_STAT", SEG0(0x0f40)},
   {"GRBM_GFX_CNTL", SEG1(0x0900)},
   {"CP_MES_CNTL", SEG1(0x2807)},
   {"RLC_CNTL", SEG1(0x4c00)},
   {"RLC_STAT", SEG1(0x4c04)},
   {"RLC_PG_CNTL", SEG1(0x4c43)},
   {"RLC_CGCG_CGLS_CTRL", SEG1(0x4c49)},
   {"RLC_GPM_STAT", SEG1(0x4e6b)},
   {"RLC_RLCS_BOOTLOAD_STATUS_GC_11_0_1", SEG1(0x4e7e)},
   {"GFX_IMU_SCRATCH_0", SEG1(0x4068)},
   {"GRBM_SOFT_RESET", SEG0(0x0da8)},
   {"CP_ME_CNTL", SEG1(0x0803)},
   {"CP_SOFT_RESET_CNTL", SEG0(0x1f59)},
   {"GRBM_CNTL", SEG0(0x0da0)}
};
#define OBSERVATION_COUNT (sizeof(observation_registers) / sizeof(observation_registers[0]))

static _Noreturn void observation_failure(int code, const char *message)
{
   fprintf(stderr, "GC observation: %s; stopping without retry or restoration\n", message);
   exit(code);
}

static struct PhxBootMemory observation_memory(void)
{
   struct PhxBootMemory memory = {0};
   size_t size = sizeof(memory);
   checked_method(conn, PHX_BOOT_MEMORY_SELECTOR, NULL, 0, NULL, 0,
                  NULL, NULL, &memory, &size);
   const uint64_t flags = PHX_BOOT_LAYOUT_CONFIGURED |
       (observation_tmr_ready ? PHX_BOOT_RING_ACTIVE | PHX_BOOT_TMR_ACTIVE : 0);
   if (memory.version != PHX_BOOT_MEMORY_VERSION || memory.flags != flags || memory.reserved ||
       (observation_tmr_ready ? (!memory.tmrBytes || memory.tmrBytes > memory.psp.tmrCapacity) : memory.tmrBytes != 0) ||
       memory.mcBase != vram_mc || memory.physicalBase != fb_pa ||
       !memory.apertureBytes || memory.apertureBytes > memory.vramBytes ||
       memory.vramBytes < (128ull << 20) || memory.vramBytes > (1ull << 40) ||
       (memory.vramBytes & ((1ull << 20) - 1)) ||
       !phxPspLayoutValid(&memory.psp, memory.mcBase, memory.physicalBase,
                          memory.vramBytes, memory.apertureBytes))
      observation_failure(75, "bootstrap metadata does not match the explicit configured/TMR-ready phase");
   return memory;
}

static int observation_main(int argc, char **argv)
{
   if (argc != 3 || !argv[1] || (strcmp(argv[1], "configured") && strcmp(argv[1], "tmr-ready")) ||
       !argv[2] || argv[2][0] != '/' || strlen(argv[2]) < 8 ||
       strcmp(argv[2] + strlen(argv[2]) - 8, ".partial"))
      observation_failure(64, "requires explicit phase and an absolute private .partial output path");
   observation_tmr_ready = !strcmp(argv[1], "tmr-ready");
   if (geteuid() != 0) observation_failure(77, "administrator privileges required");
   int fd = open(argv[2], O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
   if (fd < 0) observation_failure(73, "output exists or cannot be created exclusively");
   if (open_kext(1)) observation_failure(74, "service/ABI/published-geometry gate failed");
   const struct PhxBootMemory before = observation_memory();
   uint32_t values[OBSERVATION_COUNT];
   for (unsigned i = 0; i < OBSERVATION_COUNT; ++i) {
      values[i] = rd(observation_registers[i].index);
      if (values[i] == UINT32_MAX) observation_failure(75, "all-ones register observation");
      if (i == 0 && !(values[i] & 0x80000000u))
         observation_failure(75, "PSP initialization status not ready");
      if (i == 1 && (!values[i] || ((uint64_t)values[i] << 20) != before.vramBytes))
         observation_failure(75, "always-on memory-size control does not match geometry");
   }
   const struct PhxBootMemory after = observation_memory();
   if (memcmp(&before, &after, sizeof(before)))
      observation_failure(75, "bootstrap metadata changed during observation");
   if (IOServiceClose(conn) != KERN_SUCCESS) observation_failure(74, "service close failed");
   FILE *output = fdopen(fd, "w");
   if (!output) observation_failure(73, "private output stream failed");
   if (fprintf(output, "{\"schema\":1,\"observation_only\":true,\"phase\":\"%s\",\"GPU_register_writes\":0,\"registers\":[",
               argv[1]) < 0) observation_failure(73, "private output write failed");
   for (unsigned i = 0; i < OBSERVATION_COUNT; ++i)
      if (fprintf(output, "%s{\"name\":\"%s\",\"index\":%u,\"value\":%u}",
                  i ? "," : "", observation_registers[i].name, observation_registers[i].index, values[i]) < 0)
         observation_failure(73, "private output write failed");
   if (fprintf(output, "]}\n") < 0 || fflush(output) || fsync(fd) || fclose(output))
      observation_failure(73, "private output synchronization failed");
   puts("GC observation complete: 19 fixed register reads; zero GPU register writes; power/access conclusions unverified");
   return 0;
}

#ifndef PHX_GC_OBSERVATION_TEST
int main(int argc, char **argv) { return observation_main(argc, argv); }
#endif
