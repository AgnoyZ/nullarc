/* Complete native CLI, synthetic register banks/VRAM/completions, fake IOKit only. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#define IORegistryEntryCreateCFProperty ignored_default_property
#include <IOKit/IOKitLib.h>
#undef IORegistryEntryCreateCFProperty
static CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t, CFStringRef, CFAllocatorRef, uint32_t);
static int fake_usleep(useconds_t);
#define main mesboot_actual_main
#define usleep fake_usleep
#include "mesboot.c"
#undef main
#undef usleep
static const char *fault, *variant;
static struct PhxBootMemory memory;
static struct PhxDesktopLayout saved;
static uint32_t words[0x400000 / 4], registers[0x20000], banks[16][0x20000];
static unsigned opens, snapshots, reservations, seals, claims, writes, vwrites, reads, scheduler_bells, compute_bells, graphics_bells, closes;
static unsigned grbm_writes;
static int terminal, preflight;
static int is(const char *name) { return !strcmp(fault, name); }
static void summary(void) {
    fprintf(stderr, "fake-desktop-summary {\"opens\":%u,\"snapshots\":%u,\"reservations\":%u,\"seals\":%u,\"claims\":%u,"
        "\"writes\":%u,\"vwrites\":%u,\"reads\":%u,\"scheduler_bells\":%u,\"compute_bells\":%u,\"graphics_bells\":%u,\"closes\":%u}\n",
        opens, snapshots, reservations, seals, claims, writes, vwrites, reads, scheduler_bells, compute_bells, graphics_bells, closes);
}
static int fail(const char *name) { if (!is(name)) return 0; terminal = 1; return 5; }
static uint32_t *reg(uint32_t address) {
    assert(address < 0x20000 && registers[SEG1(0x900)] < 256);
    if ((address >= SEG0(0x1fa9) && address <= SEG0(0x1fcb)) ||
        address == SEG0(0x323f) || address == SEG0(0x3240) ||
        address == SEG1(0x2800) || address == SEG1(0x289d)) {
        assert(registers[SEG1(0x900)] < 16);
        return &banks[registers[SEG1(0x900)]][address];
    }
    return &registers[address];
}
static void put64(uint64_t offset, uint64_t value) {
    assert(!(offset & 7) && offset + 8 <= sizeof(words));
    words[offset / 4] = (uint32_t)value; words[offset / 4 + 1] = (uint32_t)(value >> 32);
}
static uint64_t get64(uint64_t offset) {
    assert(!(offset & 3) && offset + 8 <= sizeof(words));
    return words[offset / 4] | (uint64_t)words[offset / 4 + 1] << 32;
}
static CFTypeRef IORegistryEntryCreateCFProperty(io_registry_entry_t service, CFStringRef key,
                                                CFAllocatorRef allocator, uint32_t options) {
    assert(service == 1 && allocator == kCFAllocatorDefault && options == 0);
    if (!strcmp(key, "phx-build")) return phxFakePropertyNumber(39);
    if (!strcmp(key, "phx-fb-mc-base")) return phxFakePropertyNumber((long long)memory.mcBase);
    if (!strcmp(key, "phx-fb-phys")) return phxFakePropertyNumber((long long)memory.physicalBase);
    if (!strcmp(key, "phx-fb-size")) return phxFakePropertyNumber((long long)memory.vramBytes);
    assert(0); return NULL;
}
void *IOServiceMatching(const char *name) { assert(!strcmp(name, "PhxBringup")); return (void *)1; }
io_service_t IOServiceGetMatchingService(mach_port_t port, void *matching) { assert(!port && matching); return 1; }
mach_port_t mach_task_self(void) { return 42; }
kern_return_t IOServiceOpen(io_service_t service, mach_port_t task, uint32_t type, io_connect_t *connection) {
    assert(service == 1 && task == 42 && type == UC_TYPE); ++opens; *connection = 7; return 0;
}
kern_return_t IOObjectRelease(io_service_t service) { assert(service == 1); return 0; }
kern_return_t IOServiceClose(io_connect_t connection) { assert(connection == 7); ++closes; return fail("close-status"); }
static int fake_usleep(useconds_t delay) {
    assert(delay == 500 || delay == 1000 || delay == 5000 || delay == 10000);
    if (is("delay-error")) { errno = EIO; return -1; }
    return 0;
}
static void load_compute(uint64_t mqd) {
    const uint32_t pairs[][2] = {{0x1fab, 130}, {0x1fac, 131}, {0x1fa9, 128}, {0x1faa, 129},
        {0x1fb1, 136}, {0x1fb2, 137}, {0x1fb4, 139}, {0x1fb5, 140}, {0x1fb6, 141}, {0x1fb7, 142},
        {0x1fb8, 143}, {0x1fba, 145}};
    for (unsigned i = 0; i < sizeof(pairs) / sizeof(pairs[0]); ++i)
        banks[4][SEG0(pairs[i][0])] = words[mqd / 4 + pairs[i][1]];
}
static void scheduler(void) {
    assert(scheduler_bells >= 1 && scheduler_bells <= 4);
    const uint64_t packet_offset = saved.scheduler.arenaOffset + (scheduler_bells - 1) * 512;
    const uint32_t *packet = words + packet_offset / 4;
    if (scheduler_bells >= 3) {
        union MESAPI__ADD_QUEUE queue; memcpy(&queue, packet, sizeof(queue));
        const int graphics = scheduler_bells == 4;
        const uint64_t arena = graphics ? saved.graphics.arenaOffset : saved.compute.arenaOffset;
        const uint64_t base = graphics ? memory.mcBase : saved.gart.virtualBase;
        const uint64_t mqd = arena + (graphics ? 0x5000 : 0x2000);
        assert(queue.header.opcode == MES_SCH_API_ADD_QUEUE && queue.map_legacy_kq && !queue.queue_id && !queue.pipe_id);
        assert(queue.queue_type == (graphics ? MES_QUEUE_TYPE_GFX : MES_QUEUE_TYPE_COMPUTE));
        assert(queue.mqd_addr == base + mqd && queue.wptr_addr == base + arena + (graphics ? 0x4010 : 0x1010));
        assert(queue.doorbell_offset == (graphics ? saved.graphics.doorbellIndex : saved.compute.doorbellIndex));
        if (graphics) {
            registers[SEG0(0x1e80)] = words[mqd / 4 + 130];
            registers[SEG0(0x1e86)] = words[mqd / 4 + 136];
            registers[SEG0(0x1e87)] = words[mqd / 4 + 137];
            registers[SEG0(0x1e8d)] = words[mqd / 4 + 143];
        } else load_compute(mqd);
    }
    union MESAPI__QUERY_MES_STATUS query; memcpy(&query, packet + 64, sizeof(query));
    assert(query.header.opcode == MES_SCH_API_QUERY_SCHEDULER_STATUS);
    assert(query.api_status.api_completion_fence_addr == saved.gart.virtualBase + saved.scheduler.arenaOffset + 0x1020);
    assert(query.api_status.api_completion_fence_value == scheduler_bells);
    uint64_t completion = scheduler_bells;
    if (is("scheduler-timeout")) --completion;
    if (is("scheduler-fence-high")) completion ^= 1ull << 32;
    put64(saved.scheduler.arenaOffset + 0x1020, completion);
    put64(saved.scheduler.arenaOffset + 0x1040, is("scheduler-token-high") ? (1ull << 32) | 1 : 1);
}
static void work(int graphics, uint64_t wptr) {
    assert(scheduler_bells == (graphics ? 4u : 3u));
    const uint64_t arena = graphics ? saved.graphics.arenaOffset : saved.compute.arenaOffset;
    const unsigned preamble = graphics ? PHX_DESKTOP_CSB_DWORDS : 0;
    const uint64_t fence = arena + (graphics ? 0x7000 : 0x5000);
    uint64_t token = graphics ? PHX_DESKTOP_GRAPHICS_TOKEN : PHX_DESKTOP_COMPUTE_TOKEN;
    const uint32_t *packet = words + arena / 4 + preamble;
    assert(wptr == preamble + 16 && packet[0] == 0xc0017900 && packet[1] == (graphics ? 0x41u : 0x40u));
    assert(packet[3] == 0xc0033700 && packet[4] == 0x00100500);
    uint64_t target = packet[5] | (uint64_t)packet[6] << 32;
    const uint64_t expected_target = saved.compute.arenaOffset + 0x4000 + (graphics ? 0x40 : 0);
    assert(target == (graphics ? memory.mcBase : saved.gart.virtualBase) + expected_target);
    assert(packet[8] == 0xc0064900 && packet[9] == 0x06603514 && packet[10] == 0x40000000);
    assert((packet[11] | (uint64_t)packet[12] << 32) == memory.mcBase + fence);
    assert((packet[13] | (uint64_t)packet[14] << 32) == token && packet[15] == 0);
    assert(get64(fence) == ~token); // Neither a stale token nor a CPU-published adopted fence.
    if (graphics) for (unsigned i = 0; i < preamble; ++i) assert(words[arena / 4 + i] == kCsbGfx11[i]);
    const int timeout = graphics ? is("graphics-timeout") : is("compute-timeout");
    const int bad_scratch = graphics ? is("graphics-scratch") : is("compute-scratch");
    const int bad_memory = graphics ? is("graphics-memory") : is("compute-memory");
    const int high = graphics ? is("graphics-fence-high") : is("compute-fence-high");
    if (!timeout && !bad_scratch) registers[SEG1(graphics ? 0x2041 : 0x2040)] = packet[2];
    if (!timeout && !bad_memory) words[expected_target / 4] = packet[7];
    if (!timeout) put64(fence, high ? token ^ (1ull << 32) : token);
}
kern_return_t IOConnectCallScalarMethod(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t input_count, uint64_t *output, uint32_t *output_count) {
    assert(connection == 7 && input && !terminal);
    if (selector == SEL_HELLO) {
        assert(input_count == 2 && output && output_count && *output_count == 4);
        memset(output, 0, 4 * sizeof(*output)); output[0] = 1; return fail("hello-status");
    }
    assert(reservations == 1 && !seals && !claims);
    if (selector == SEL_DBG_WRITE_REG) {
        assert(input_count == 2 && output && output_count && *output_count == 1);
        if (preflight) assert(input[0] == SEG1(0x900));
        ++writes; if (fail("write-status")) return 5;
        *reg((uint32_t)input[0]) = (uint32_t)input[1]; *output = input[1];
        if (input[0] == SEG1(0x900)) {
            ++grbm_writes;
            if (is("select-immediate-and-readback") && grbm_writes == 1) {
                *reg((uint32_t)input[0]) ^= 1; *output ^= 1;
            }
            if (is("select-zero-readbacks") && grbm_writes == 1) {
                *reg((uint32_t)input[0]) = 0; *output = 0;
            }
        }
        if (is("setup-readback") && input[0] == 0xde0) *output ^= 1;
        return 0;
    }
    if (selector == SEL_DBG_VRAM_WRITE) {
        assert(!preflight);
        assert(input_count == 2 && !output && !output_count && input[0] + 4 <= sizeof(words));
        assert(!(input[0] & 3)); ++vwrites; if (fail("vwrite-status")) return 5;
        words[input[0] / 4] = (uint32_t)input[1]; return 0;
    }
    assert(selector == SEL_DBG_DOORBELL && input_count == 3 && !output && !output_count && !input[2]);
    assert(!preflight);
    if (input[0] == saved.scheduler.doorbellIndex * 4) { ++scheduler_bells; scheduler(); }
    else if (input[0] == saved.compute.doorbellIndex * 4) { ++compute_bells; work(0, input[1]); }
    else { assert(input[0] == saved.graphics.doorbellIndex * 4); ++graphics_bells; work(1, input[1]); }
    return fail("doorbell-status");
}
kern_return_t IOConnectCallMethod(io_connect_t connection, uint32_t selector,
    const uint64_t *input, uint32_t input_count, const void *input_data, size_t input_size,
    uint64_t *output, uint32_t *output_count, void *output_data, size_t *output_size) {
    assert(connection == 7 && !output && !output_count && !terminal);
    if (selector == PHX_BOOT_MEMORY_SELECTOR) {
        assert(!input && !input_count && !input_data && !input_size && output_data && *output_size == sizeof(memory));
        ++snapshots; memcpy(output_data, &memory, sizeof(memory));
        if (is("snapshot-short")) --*output_size;
        return fail("snapshot-status");
    }
    if (selector == PHX_DESKTOP_SELECTOR) {
        assert(!input && !input_count && input_data && input_size == sizeof(struct PhxDesktopRequest) && !output_data && !output_size);
        const struct PhxDesktopRequest *request = input_data;
        if (preflight) assert(request->operation == PHX_DESKTOP_RESERVE);
        if (request->operation == PHX_DESKTOP_RESERVE) {
            assert(!writes && !vwrites && !reads && !reservations && phxDesktopLayoutValid(&request->layout, &memory));
            ++reservations; saved = request->layout; return fail("reserve-status");
        }
        if (request->operation == PHX_DESKTOP_SEAL) {
            assert(reservations == 1 && scheduler_bells == 4 && compute_bells == 1 && graphics_bells == 1);
            assert(!memcmp(&saved, &request->layout, sizeof(saved)) && request->computeWptr == 16 && request->graphicsWptr == 976);
            assert(get64(saved.compute.arenaOffset + 0x5000) == PHX_DESKTOP_COMPUTE_TOKEN);
            assert(get64(saved.graphics.arenaOffset + 0x7000) == PHX_DESKTOP_GRAPHICS_TOKEN);
            ++seals; return fail("seal-status");
        }
        assert(request->operation == PHX_DESKTOP_CLAIM && !reservations && !reads && !writes && !vwrites);
        assert(request->computeWptr == 16 && request->graphicsWptr == 976); ++claims; return fail("claim-status");
    }
    assert(reservations && !seals && !claims && input && !input_data && !input_size && output_data && output_size);
    if (selector == SEL_READREGS) {
        assert(input_count == 3 && input[1] == 1 && *output_size == 4); ++reads;
        if (preflight) assert(input[0] == SEG1(0x900) || input[0] == SEG1(0x2807) ||
                              input[0] == SEG0(0x1fab) || input[0] == SEG0(0x1e80));
        if (fail("read-status")) return 5;
        uint32_t value = *reg((uint32_t)input[0]);
        if (input[0] == SEG0(0x16bd + 17)) value = is("gart-timeout") ? 0 : 1;
        if (is("already-mes") && input[0] == SEG1(0x2807)) value = 0x0c000000;
        if (is("already-queue") && input[0] == SEG0(0x1fab)) value = 1;
        if (input[0] == SEG1(0x900)) {
            const char *select_faults[] = {"select-kiq", "select-scheduler", "select-compute", "select-graphics"};
            for (unsigned i = 0; i < 4; ++i)
                if (is(select_faults[i]) && grbm_writes == 1 + 2 * i) value ^= 1;
            if (is("restore-selection") && grbm_writes == 2) value = 13;
        }
        memcpy(output_data, &value, sizeof(value)); return 0;
    }
    assert(selector == SEL_DBG_VRAM_READ && input_count == 2 && input[0] + *output_size <= sizeof(words));
    assert(!preflight);
    if (fail("vread-status")) return 5;
    memcpy(output_data, (const char *)words + input[0], *output_size); return 0;
}
int main(int argc, char **argv) {
    assert(argc == 4); variant = argv[1]; fault = argv[2]; assert(atexit(summary) == 0);
    preflight = !strcmp(argv[3], "desktop-preflight");
    memory = (struct PhxBootMemory){1, 7, !strcmp(variant, "relocated") ? 0x6000000000ull : 0x8000000000ull,
        !strcmp(variant, "relocated") ? 0x300000000ull : 0x6a0000000ull, 0x8000000, sizeof(words), 0x1000, 0,
        {1, 0, 0x100000, 0x10000, 0x200000, 0x10000, {0, 0}}};
    registers[0xee7e] = 0x80000000;
    if (is("pre-adopted")) memory.flags |= PHX_BOOT_GPU_ACTIVE;
    if (is("psp-fault")) memory.flags |= PHX_BOOT_PSP_FAULTED;
    char *arguments[] = {argv[0], argv[3], "0x4000000000", "0x400000", "0x300000", "0x302000",
        "0x310000", "0x18", "0x314000", "0x16", "0x318000", "6", "0x320000", "0x116"};
    if (is("bad-argument")) arguments[6] = "-1";
    if (is("overlap")) arguments[10] = arguments[12];
    if (is("env-override")) assert(setenv("NO_CSB", "1", 1) == 0);
    return mesboot_actual_main(is("bad-count") ? 13 : 14, arguments);
}
