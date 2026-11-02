/*
 * phxctl.c — talk to PhxBringup.kext (service PhxBringup, user client 'N48N') from the command line.
 *
 *   phxctl regs <dword> [<dword> ...]     ReadRegs, absolute dword offsets (root)
 *   phxctl gc                             the GC 11.0.1 status registers of step E2 (root)
 *   phxctl smu <msg> [<arg>]              one SMU 13.0.4 message from the kext's allow-list (root, phxdebug=1)
 *   phxctl smuinfo                        TestMessage, PMFW / driver-if versions, enabled features
 *   phxctl psp status|create <off>|destroy  PSP 13.0.4 KM ring in the UMA carve-out at byte offset <off> (root, phxdebug=1)
 *
 * Absolute offsets = IP discovery segment base + Linux register offset (hardware/dumps/firebat_u6c/ip_discovery.txt):
 * GC segment 0 = 0x1260, segment 1 = 0xA000.
 */
#include <IOKit/IOKitLib.h>
#include <assert.h>
#include <CommonCrypto/CommonDigest.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#include "../../src/phxbringup/PhxNativeABI.h"
#include "../../src/phxbringup/PhxPspLayout.h"
static_assert(sizeof(struct PhxPspLayout) == 64, "PSP layout wire size");
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define UC_TYPE 0x4E34384Eu
#define SEL_HELLO 0
#define SEL_READREGS 2
#define SEL_DBG_SMU 100
#define SEL_DBG_PSP_RING 101
#define SEL_DBG_VRAM_READ 102
#define SEL_DBG_PSP_SUBMIT 103
#define SEL_DBG_FW_STAGE 104
#define SEL_DBG_PSP_LOADIPFW 105
#define SEL_DBG_PSP_CTL 106
#define SEL_DBG_PSP_RAW 107
#define SEL_DBG_WRITE_REG 108
#define SEL_DBG_VRAM_WRITE 109

static io_connect_t conn;
static uint8_t *staging_snapshot;

static _Noreturn void control_failure(int status, const char *what)
{
   free(staging_snapshot);
   staging_snapshot = NULL;
   fprintf(stderr, "phxctl checked failure: %s; stopping (no rollback)\n", what);
   exit(status);
}

static kern_return_t checked_scalar(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t input_count, uint64_t *output, uint32_t *output_count)
{
   const uint32_t expected = output_count ? *output_count : 0;
   kern_return_t kr = IOConnectCallScalarMethod(connection, selector, input, input_count, output, output_count);
   if (kr != KERN_SUCCESS || (output_count && *output_count != expected))
      control_failure(74, "IOKit scalar status or reply length");
   if (selector == SEL_HELLO && output[0] != input[0])
      control_failure(75, "incompatible kernel ABI");
   if ((selector == SEL_DBG_PSP_SUBMIT || selector == SEL_DBG_PSP_CTL ||
        selector == SEL_DBG_PSP_LOADIPFW || selector == SEL_DBG_PSP_RAW ||
        selector == PHX_PSP_LOAD_TOC_SELECTOR) && output[0] != 0)
      control_failure(75, "PSP completion/status not confirmed");
   if (selector == SEL_DBG_SMU && output[0] != 1)
      control_failure(75, "SMU response not successful");
   return kr;
}

static kern_return_t checked_method(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t input_count, const void *input_data, size_t input_size,
    uint64_t *output, uint32_t *output_count, void *output_data, size_t *output_size)
{
   const uint32_t expected_count = output_count ? *output_count : 0;
   const size_t expected_size = output_size ? *output_size : 0;
   kern_return_t kr = IOConnectCallMethod(connection, selector, input, input_count, input_data, input_size,
                                         output, output_count, output_data, output_size);
   if (kr != KERN_SUCCESS || (output_count && *output_count != expected_count) ||
       (output_size && *output_size != expected_size))
      control_failure(74, "IOKit method status or reply length");
   return kr;
}

static uint64_t checked_u64(const char *text)
{
   char *end = NULL;
   if (!text || text[0] < '0' || text[0] > '9') control_failure(64, "invalid unsigned argument");
   errno = 0;
   unsigned long long value = strtoull(text, &end, 0);
   if (errno || end == text || *end || value > UINT64_MAX) control_failure(64, "invalid unsigned argument");
   return (uint64_t)value;
}

static uint32_t checked_u32(const char *text)
{
   uint64_t value = checked_u64(text);
   if (value > UINT32_MAX) control_failure(64, "invalid unsigned argument");
   return (uint32_t)value;
}

static uint8_t *firmware_snapshot(const char *path, const char *expected_hash, uint32_t *file_size)
{
   if (!expected_hash || strlen(expected_hash) != CC_SHA256_DIGEST_LENGTH * 2)
      control_failure(64, "a reviewed lowercase SHA-256 is required");
   for (unsigned i = 0; i < CC_SHA256_DIGEST_LENGTH * 2; ++i)
      if (!((expected_hash[i] >= '0' && expected_hash[i] <= '9') || (expected_hash[i] >= 'a' && expected_hash[i] <= 'f')))
         control_failure(64, "invalid lowercase SHA-256");
   int fd = open(path, O_RDONLY | O_NONBLOCK);
   struct stat st;
   if (fd < 0) control_failure(65, "firmware file unavailable");
   if (fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size <= 0 || (uint64_t)st.st_size > PHX_VRAM_FWBUF_SIZE) {
      close(fd); control_failure(65, "firmware must be a bounded regular file");
   }
   *file_size = (uint32_t)st.st_size;
   uint8_t *bytes = malloc(*file_size);
   if (!bytes) { close(fd); control_failure(65, "firmware snapshot allocation failed"); }
   size_t read_bytes = 0;
   while (read_bytes < *file_size) {
      ssize_t got = read(fd, bytes + read_bytes, *file_size - read_bytes);
      if (got < 0 && errno == EINTR) continue;
      if (got <= 0) { free(bytes); close(fd); control_failure(65, "firmware snapshot short read or I/O error"); }
      read_bytes += (size_t)got;
   }
   if (close(fd)) { free(bytes); control_failure(65, "firmware file close failed"); }
   unsigned char digest[CC_SHA256_DIGEST_LENGTH];
   if (!CC_SHA256(bytes, *file_size, digest)) { free(bytes); control_failure(65, "firmware digest failed"); }
   const char hex[] = "0123456789abcdef";
   for (unsigned i = 0; i < CC_SHA256_DIGEST_LENGTH; ++i) {
      if (expected_hash[2*i] != hex[digest[i] >> 4] || expected_hash[2*i+1] != hex[digest[i] & 15]) {
         free(bytes); control_failure(65, "firmware SHA-256 mismatch");
      }
   }
   return bytes;
}

static void stage_firmware(const char *path, uint32_t offset, uint32_t size, uint32_t destination, const char *hash)
{
   const uint64_t padded = ((uint64_t)size + 3) & ~3ull;
   if (!size || (destination & 3) || destination > PHX_VRAM_FWBUF_SIZE ||
       padded > PHX_VRAM_FWBUF_SIZE - destination)
      control_failure(64, "invalid firmware staging extent");
   uint32_t file_size = 0;
   uint8_t *bytes = firmware_snapshot(path, hash, &file_size);
   if (offset > file_size || size > file_size - offset) {
      free(bytes); control_failure(65, "firmware slice exceeds the authenticated snapshot");
   }
   staging_snapshot = bytes;
   for (uint32_t staged = 0; staged < size;) {
      uint32_t chunk = size - staged > 4096 ? 4096 : size - staged;
      uint64_t input[] = {destination + staged};
      checked_method(conn, SEL_DBG_FW_STAGE, input, 1, bytes + offset + staged, chunk, NULL, NULL, NULL, NULL);
      staged += chunk;
   }
   free(bytes);
   staging_snapshot = NULL;
}

static int open_kext(void)
{
   io_service_t svc = IOServiceGetMatchingService(kIOMainPortDefault, IOServiceMatching("PhxBringup"));
   if (!svc) {
      fprintf(stderr, "PhxBringup service not found\n");
      return -1;
   }
   kern_return_t kr = IOServiceOpen(svc, mach_task_self(), UC_TYPE, &conn);
   IOObjectRelease(svc);
   if (kr) {
      fprintf(stderr, "IOServiceOpen: 0x%08x\n", kr);
      return -1;
   }
   uint64_t in[2] = {1, 0}, out[4];
   uint32_t n = 4;
   kr = checked_scalar(conn, SEL_HELLO, in, 2, out, &n);
   if (kr) {
      fprintf(stderr, "Hello: 0x%08x\n", kr);
      return -1;
   }
   return 0;
}

static int read_reg(uint32_t reg, uint32_t *val)
{
   uint64_t in[3] = {reg, 1, 0xFFFFFFFFull};
   size_t sz = 4;
   kern_return_t kr = checked_method(conn, SEL_READREGS, in, 3, NULL, 0, NULL, NULL, val, &sz);
   return kr ? (int)kr : 0;
}

static int smu(uint32_t msg, uint32_t arg, uint32_t *resp, uint32_t *after)
{
   uint64_t in[2] = {msg, arg}, out[2] = {0, 0};
   uint32_t n = 2;
   kern_return_t kr = checked_scalar(conn, SEL_DBG_SMU, in, 2, out, &n);
   *resp = (uint32_t)out[0];
   *after = (uint32_t)out[1];
   return (int)kr;
}

static const char *smu_resp_name(uint32_t r)
{
   switch (r) {
   case 0x01: return "OK";
   case 0xFF: return "Failed";
   case 0xFE: return "UnknownCmd";
   case 0xFD: return "CmdRejectedPrereq";
   case 0xFC: return "Busy";
   case 0x00: return "no response";
   default: return "?";
   }
}

static void do_smu(uint32_t msg, uint32_t arg, const char *what)
{
   uint32_t resp, after;
   int kr = smu(msg, arg, &resp, &after);
   printf("smu %-22s msg 0x%02x arg 0x%08x -> kr 0x%08x resp 0x%02x (%s) out 0x%08x\n", what, msg, arg, kr, resp,
          smu_resp_name(resp), after);
}

struct named_reg {
   const char *name;
   uint32_t reg;
};

static const struct named_reg gc_regs[] = {
   {"GRBM_STATUS", 0x1260 + 0x0da4},
   {"GRBM_STATUS2", 0x1260 + 0x0da2},
   {"GRBM_STATUS_SE0", 0x1260 + 0x0da5},
   {"CP_STAT", 0x1260 + 0x0f40},
   {"GB_ADDR_CONFIG", 0x1260 + 0x13de},
   {"CC_GC_SHADER_ARRAY_CONFIG", 0x1260 + 0x100f},
   {"GC_USER_SHADER_ARRAY_CONFIG", 0xA000 + 0x5b90},
   {"RLC_CNTL", 0xA000 + 0x4c00},
   {"RLC_STAT", 0xA000 + 0x4c04},
   {"RLC_GPM_STAT", 0xA000 + 0x4e6b},
   {"RLC_RLCS_BOOTLOAD_STATUS", 0xA000 + 0x4e82},
   {"CP_ME_CNTL", 0xA000 + 0x0803},
   {"CP_MEC_RS64_CNTL", 0xA000 + 0x2904},
   {"CP_MES_CNTL", 0xA000 + 0x2807},
   {"CP_RB0_CNTL", 0x1260 + 0x1de1},
   {"SDMA0_STATUS_REG", 0x1260 + 0x0025},
   {"SDMA0_F32_CNTL", 0xA000 + 0x589a},
};

int main(int argc, char **argv)
{
   if (argc >= 2 && !strcmp(argv[1], "loadtoc") && argc != 7)
      control_failure(64, "loadtoc requires file, offset, size, staging offset and reviewed SHA-256");
   if (argc >= 2 && !strcmp(argv[1], "psp-layout") && argc != 7)
      control_failure(64, "psp-layout requires ring offset, TMR offset/capacity and staging offset/capacity");
   if (argc >= 2 && !strcmp(argv[1], "verify-file")) {
      if (argc != 4) control_failure(64, "verify-file requires a file and reviewed SHA-256");
      uint32_t size = 0;
      uint8_t *bytes = firmware_snapshot(argv[2], argv[3], &size);
      free(bytes);
      printf("verified firmware snapshot (%u bytes); no IOKit connection\n", size);
      return 0;
   }
   if (argc >= 2 && ((!strcmp(argv[1], "loadfw") && argc != 8) || (!strcmp(argv[1], "stage") && argc != 7)))
      control_failure(64, "firmware commands require the reviewed whole-file SHA-256 as their final argument");
   if (argc < 2) {
      fprintf(stderr, "usage: phxctl regs <dword>... | gc | smu <msg> [arg] | smuinfo | "
                      "psp status|create <off>|destroy | vram <off> [count]\n");
      return 2;
   }
   if (open_kext())
      return 1;

   if (!strcmp(argv[1], "loadtoc")) {
      uint32_t offset = checked_u32(argv[3]), size = checked_u32(argv[4]), destination = checked_u32(argv[5]);
      if (destination & 0xfff) control_failure(64, "TOC staging destination must be page aligned");
      stage_firmware(argv[2], offset, size, destination, argv[6]);
      uint64_t input[2] = {destination, size}, out[4] = {0};
      uint32_t n = 4;
      checked_scalar(conn, PHX_PSP_LOAD_TOC_SELECTOR, input, 2, out, &n);
      if (!out[2] || out[2] > UINT32_MAX || out[3] != 1) {
         fprintf(stderr, "TOC reported %llu TMR bytes; configured region fit=%llu\n",
                 (unsigned long long)out[2], (unsigned long long)out[3]);
         control_failure(75, "TOC size or configured TMR capacity/alignment not usable");
      }
      printf("loadtoc complete; required TMR bytes %llu; TMR not set up\n", (unsigned long long)out[2]);
   } else if (!strcmp(argv[1], "psp-layout")) {
      struct PhxPspLayout layout = {PHX_PSP_LAYOUT_VERSION, checked_u64(argv[2]), checked_u64(argv[3]),
         checked_u64(argv[4]), checked_u64(argv[5]), checked_u64(argv[6]), {0, 0}};
      uint64_t out[4] = {0};
      uint32_t n = 4;
      checked_method(conn, PHX_PSP_LAYOUT_SELECTOR, NULL, 0, &layout, sizeof(layout), out, &n, NULL, NULL);
      printf("psp layout configured; numeric checks only, memory ownership unverified\n");
   } else if (!strcmp(argv[1], "regs")) {
      for (int i = 2; i < argc; i++) {
         uint32_t reg = (uint32_t)strtoul(argv[i], NULL, 0), v = 0;
         int kr = read_reg(reg, &v);
         printf("0x%05x: %s0x%08x\n", reg, kr ? "(error) " : "", v);
      }
   } else if (!strcmp(argv[1], "gc")) {
      for (size_t i = 0; i < sizeof(gc_regs) / sizeof(gc_regs[0]); i++) {
         uint32_t v = 0;
         int kr = read_reg(gc_regs[i].reg, &v);
         printf("%-28s 0x%05x: ", gc_regs[i].name, gc_regs[i].reg);
         if (kr)
            printf("error 0x%08x\n", kr);
         else
            printf("0x%08x\n", v);
      }
   } else if (!strcmp(argv[1], "smu") && argc >= 3) {
      do_smu((uint32_t)strtoul(argv[2], NULL, 0), argc >= 4 ? (uint32_t)strtoul(argv[3], NULL, 0) : 0, "");
   } else if (!strcmp(argv[1], "psp") && argc >= 3) {
      uint64_t op = !strcmp(argv[2], "create") ? 1 : !strcmp(argv[2], "destroy") ? 2 : 3;
      uint64_t in[2] = {op, argc >= 4 ? strtoull(argv[3], NULL, 0) : 0}, out[4] = {0, 0, 0, 0};
      uint32_t n = 4;
      kern_return_t kr = checked_scalar(conn, SEL_DBG_PSP_RING, in, 2, out, &n);
      printf("psp %s -> kr 0x%08x  C2PMSG_64 0x%08x  ring MC 0x%llx  region-zero %llu  wptr 0x%llx\n", argv[2], kr,
             (uint32_t)out[0], (unsigned long long)out[1], (unsigned long long)out[2], (unsigned long long)out[3]);
   } else if (!strcmp(argv[1], "vram") && argc >= 3) {
      uint32_t off = (uint32_t)strtoul(argv[2], NULL, 0);
      uint32_t count = argc >= 4 ? (uint32_t)strtoul(argv[3], NULL, 0) : 8;
      if (count < 1 || count > 256)
         count = 8;
      uint64_t in[2] = {off, count};
      uint32_t buf[256];
      size_t sz = count * 4;
      kern_return_t kr = checked_method(conn, SEL_DBG_VRAM_READ, in, 2, NULL, 0, NULL, NULL, buf, &sz);
      if (kr) {
         printf("vram read error 0x%08x\n", kr);
      } else {
         for (uint32_t i = 0; i < count; i++) {
            if (i % 8 == 0)
               printf("\nvram+0x%08x:", off + i * 4);
            printf(" %08x", buf[i]);
         }
         printf("\n");
      }
   } else if (!strcmp(argv[1], "submit") && argc >= 3) {
      uint64_t in[1] = {strtoull(argv[2], NULL, 0)}, out[4] = {0, 0, 0, 0};
      uint32_t n = 4;
      kern_return_t kr = checked_scalar(conn, SEL_DBG_PSP_SUBMIT, in, 1, out, &n);
      printf("submit cmd 0x%llx -> kr 0x%08x  resp.status 0x%08x  fence %llu us  uresp 0x%08x 0x%08x\n",
             (unsigned long long)in[0], kr, (uint32_t)out[0], (unsigned long long)out[1], (uint32_t)out[2],
             (uint32_t)out[3]);
   } else if (!strcmp(argv[1], "tmr")) {
      uint64_t in[2] = {1, argc >= 3 ? strtoull(argv[2], NULL, 0) : 0}, out[4] = {0, 0, 0, 0};
      uint32_t n = 4;
      kern_return_t kr = checked_scalar(conn, SEL_DBG_PSP_CTL, in, 2, out, &n);
      printf("tmr (size 0x%llx) -> kr 0x%08x  status 0x%08x  %llu us\n", (unsigned long long)in[1], kr,
             (uint32_t)out[0], (unsigned long long)out[1]);
   } else if (!strcmp(argv[1], "autoload")) {
      uint64_t in[2] = {2, 0}, out[4] = {0, 0, 0, 0};
      uint32_t n = 4;
      kern_return_t kr = checked_scalar(conn, SEL_DBG_PSP_CTL, in, 2, out, &n);
      printf("autoload -> kr 0x%08x  status 0x%08x  %llu us\n", kr, (uint32_t)out[0], (unsigned long long)out[1]);
   } else if (!strcmp(argv[1], "loadfw") && argc == 8) {
      const char *path = argv[2];
      uint32_t foff = checked_u32(argv[3]), size = checked_u32(argv[4]),
               fwtype = checked_u32(argv[5]), bufoff = checked_u32(argv[6]);
      stage_firmware(path, foff, size, bufoff, argv[7]);
      uint64_t lin[3] = {fwtype, bufoff, size}, out[4] = {0, 0, 0, 0};
      uint32_t n = 4;
      kern_return_t kr = checked_scalar(conn, SEL_DBG_PSP_LOADIPFW, lin, 3, out, &n);
      printf("loadfw %s[0x%x:+%u] fwtype %u @fwbuf+0x%x -> kr 0x%08x  status 0x%08x  %llu us  fw_addr 0x%08x%08x\n",
             path, foff, size, fwtype, bufoff, kr, (uint32_t)out[0], (unsigned long long)out[1], (uint32_t)out[3],
             (uint32_t)out[2]);
   } else if (!strcmp(argv[1], "stage") && argc == 7) {
      const char *path = argv[2];
      uint32_t foff = checked_u32(argv[3]), size = checked_u32(argv[4]), bufoff = checked_u32(argv[5]);
      stage_firmware(path, foff, size, bufoff, argv[6]);
      printf("staged %s[0x%x:+%u] @fwbuf+0x%x\n", path, foff, size, bufoff);
   } else if (!strcmp(argv[1], "wreg") && argc >= 4) {
      uint64_t in[2] = {strtoull(argv[2], NULL, 0), strtoull(argv[3], NULL, 0)}, out[1] = {0};
      uint32_t n = 1;
      kern_return_t kr = checked_scalar(conn, SEL_DBG_WRITE_REG, in, 2, out, &n);
      printf("wreg 0x%llx = 0x%llx -> kr 0x%08x  readback 0x%08x\n", (unsigned long long)in[0],
             (unsigned long long)in[1], kr, (uint32_t)out[0]);
   } else if (!strcmp(argv[1], "vramw") && argc >= 4) {
      uint64_t in[2] = {strtoull(argv[2], NULL, 0), strtoull(argv[3], NULL, 0)};
      kern_return_t kr = checked_scalar(conn, SEL_DBG_VRAM_WRITE, in, 2, NULL, NULL);
      printf("vramw +0x%llx = 0x%llx -> kr 0x%08x\n", (unsigned long long)in[0], (unsigned long long)in[1], kr);
   } else if (!strcmp(argv[1], "pte") && argc >= 6) {
      // pte <tableoff> <n> <pa> <flags>: flat PTE array, pte[i] = (pa + i*4096) | flags
      uint64_t toff = strtoull(argv[2], NULL, 0), cnt = strtoull(argv[3], NULL, 0);
      uint64_t pa = strtoull(argv[4], NULL, 0), fl = strtoull(argv[5], NULL, 0);
      kern_return_t kr = 0;
      for (uint64_t i = 0; i < cnt && !kr; i++) {
         uint64_t v = (pa + i * 4096) | fl;
         uint64_t lo[2] = {toff + i * 8, v & 0xffffffffu}, hi[2] = {toff + i * 8 + 4, v >> 32};
         kr = checked_scalar(conn, SEL_DBG_VRAM_WRITE, lo, 2, NULL, NULL);
         if (!kr) kr = checked_scalar(conn, SEL_DBG_VRAM_WRITE, hi, 2, NULL, NULL);
      }
      printf("pte table+0x%llx n=%llu pa=0x%llx flags=0x%llx -> kr 0x%08x\n", (unsigned long long)toff,
             (unsigned long long)cnt, (unsigned long long)pa, (unsigned long long)fl, kr);
   } else if (!strcmp(argv[1], "raw") && argc >= 3) {
      uint64_t in[7] = {0, 0, 0, 0, 0, 0, 0}, out[4] = {0, 0, 0, 0};
      in[0] = strtoull(argv[2], NULL, 0);
      for (int i = 3; i < argc && i < 9; i++)
         in[i - 2] = strtoull(argv[i], NULL, 0);
      uint32_t n = 4;
      kern_return_t kr = checked_scalar(conn, SEL_DBG_PSP_RAW, in, 7, out, &n);
      printf("raw cmd 0x%llx -> kr 0x%08x  status 0x%08x  %llu us  resp 0x%08x 0x%08x\n",
             (unsigned long long)in[0], kr, (uint32_t)out[0], (unsigned long long)out[1], (uint32_t)out[2],
             (uint32_t)out[3]);
   } else if (!strcmp(argv[1], "smuinfo")) {
      do_smu(0x01, 0x1234, "TestMessage");
      do_smu(0x02, 0, "GetPmfwVersion");
      do_smu(0x03, 0, "GetDriverIfVersion");
      do_smu(0x12, 0, "GetEnabledFeatures lo");
      do_smu(0x12, 1, "GetEnabledFeatures hi");
   } else {
      fprintf(stderr, "unknown command\n");
      return 2;
   }
   IOServiceClose(conn);
   return 0;
}
