/* SPDX-License-Identifier: MIT */
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <IOKit/IOKitLib.h>
#include <dlfcn.h>
#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/utsname.h>
#include "radv_ib_tail_runtime_guard.h"
#include "runtime_probe_spv.h"

static void require(int okay, const char *why) { if (!okay) phx34_runtime_hold(why); }
#define CHECK(expression) require((expression) == VK_SUCCESS, #expression)
static void guard_selftest(void)
{
    struct phx34_runtime_counts c; phx34_runtime_counts(&c);
    require(!c.blocked && !c.opens && !c.submits, "initial guard state");
    io_connect_t connection = 0;
    require(IOServiceOpen(0, mach_task_self(), 0, &connection) == kIOReturnNotPermitted && !connection,
            "dependent-dylib open interposition");
    phx34_runtime_counts(&c);
    require(c.blocked == 1 && !c.opens && phx34_runtime_platform_selftest(), "interposition/forwarding self-test");
}
int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "--guard-selftest")) {
        guard_selftest();
        puts("GUARD-SELFTEST: passed; no service enumeration or GPU client"); return 0;
    }
    if (argc != 3 || strcmp(argv[1], "--run-tail")) {
        fputs("usage: build34-radv-runtime-probe --guard-selftest | --run-tail /private/path/libvulkan_radeon.dylib\n", stderr); return 64;
    }
    struct utsname host;
    if (uname(&host) || strcmp(host.sysname, "Darwin") || strcmp(host.machine, "x86_64") || strncmp(host.release, "25.", 3)) return 4;
    extern char **environ;
    for (char **p = environ; *p; ++p)
        if (!strncmp(*p,"RADV_",5) || !strncmp(*p,"MESA_",5) || !strncmp(*p,"AMD_",4) || !strncmp(*p,"VK_",3) || !strncmp(*p,"DYLD_",5)) {
            fputs("REFUSED: inherited driver/loader override\n", stderr); return 4;
        }
    guard_selftest();
    require(!setenv("RADV_DARWIN_BUILD34_IB_TAIL","1",1) && !setenv("MESA_SHADER_CACHE_DISABLE","true",1), "local test policy");
    void *library = dlopen(argv[2], RTLD_NOW | RTLD_LOCAL);
    require(library != NULL, "private runtime loading");
    struct phx34_runtime_counts observed; phx34_runtime_counts(&observed);
    require(observed.blocked == 1 && !observed.opens && !observed.submits, "no target constructor IOKit activity");
    int (*service)(const char *) = (int (*)(const char *))dlsym(library,"radv_darwin_set_service_class");
    PFN_vkGetInstanceProcAddr gpa = (PFN_vkGetInstanceProcAddr)dlsym(library,"vk_icdGetInstanceProcAddr");
    require(service && gpa && !service("PhxBringup") && service("Navi48Bringup") == -EINVAL, "Phoenix-only ICD exports");
    PFN_vkCreateInstance create = (PFN_vkCreateInstance)gpa(VK_NULL_HANDLE,"vkCreateInstance");
    require(create != NULL,"CreateInstance export");
    VkApplicationInfo app = {.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO, .pApplicationName="build34-bounded-runtime", .apiVersion=VK_API_VERSION_1_2};
    VkInstanceCreateInfo ici = {.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo=&app};
    VkInstance instance = VK_NULL_HANDLE; CHECK(create(&ici,NULL,&instance));
#define IFN(name) PFN_##name name = (PFN_##name)gpa(instance,#name); require(name != NULL,#name)
    IFN(vkEnumeratePhysicalDevices); IFN(vkGetPhysicalDeviceProperties); IFN(vkGetPhysicalDeviceMemoryProperties);
    IFN(vkGetPhysicalDeviceQueueFamilyProperties); IFN(vkCreateDevice); IFN(vkGetDeviceProcAddr); IFN(vkDestroyInstance);
#undef IFN
    phx34_runtime_arm();
    uint32_t physical_count = 2; VkPhysicalDevice physicals[2] = {VK_NULL_HANDLE,VK_NULL_HANDLE};
    CHECK(vkEnumeratePhysicalDevices(instance,&physical_count,physicals));
    require(physical_count == 1 && physicals[0], "one Vulkan physical device"); VkPhysicalDevice physical = physicals[0];
    VkPhysicalDeviceProperties properties; vkGetPhysicalDeviceProperties(physical,&properties);
    require(properties.vendorID == 0x1002 && properties.deviceID == 0x1900,"Vulkan PCI identity");
    uint32_t family_count = 0; vkGetPhysicalDeviceQueueFamilyProperties(physical,&family_count,NULL);
    require(family_count && family_count <= 16,"queue family count"); VkQueueFamilyProperties families[16];
    vkGetPhysicalDeviceQueueFamilyProperties(physical,&family_count,families);
    uint32_t family = UINT32_MAX;
    for (uint32_t i=0;i<family_count;++i)
        if (families[i].queueCount && (families[i].queueFlags & VK_QUEUE_COMPUTE_BIT) && !(families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) { family=i; break; }
    require(family != UINT32_MAX,"compute-only queue mandatory; no family-zero fallback");
    float priority = 1;
    VkDeviceQueueCreateInfo qci = {.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,.queueFamilyIndex=family,.queueCount=1,.pQueuePriorities=&priority};
    VkDeviceCreateInfo dci = {.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,.queueCreateInfoCount=1,.pQueueCreateInfos=&qci};
    VkDevice device = VK_NULL_HANDLE; CHECK(vkCreateDevice(physical,&dci,NULL,&device));
#define DFN(name) PFN_##name name = (PFN_##name)vkGetDeviceProcAddr(device,#name); require(name != NULL,#name)
    DFN(vkCreateBuffer); DFN(vkGetBufferMemoryRequirements); DFN(vkAllocateMemory); DFN(vkBindBufferMemory); DFN(vkMapMemory);
    DFN(vkCreateShaderModule); DFN(vkCreateDescriptorSetLayout); DFN(vkCreatePipelineLayout); DFN(vkCreateComputePipelines);
    DFN(vkCreateDescriptorPool); DFN(vkAllocateDescriptorSets); DFN(vkUpdateDescriptorSets);
    DFN(vkCreateCommandPool); DFN(vkAllocateCommandBuffers); DFN(vkBeginCommandBuffer); DFN(vkEndCommandBuffer); DFN(vkResetCommandBuffer);
    DFN(vkCmdBindPipeline); DFN(vkCmdBindDescriptorSets); DFN(vkCmdPushConstants); DFN(vkCmdDispatch); DFN(vkCmdPipelineBarrier);
    DFN(vkGetDeviceQueue); DFN(vkCreateFence); DFN(vkResetFences); DFN(vkQueueSubmit); DFN(vkWaitForFences);
    DFN(vkDestroyFence); DFN(vkDestroyCommandPool); DFN(vkDestroyDescriptorPool); DFN(vkDestroyPipeline);
    DFN(vkDestroyPipelineLayout); DFN(vkDestroyDescriptorSetLayout); DFN(vkDestroyShaderModule);
    DFN(vkUnmapMemory); DFN(vkDestroyBuffer); DFN(vkFreeMemory); DFN(vkDestroyDevice);
#undef DFN
    VkBufferCreateInfo bci = {.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=16384,.usage=VK_BUFFER_USAGE_STORAGE_BUFFER_BIT,.sharingMode=VK_SHARING_MODE_EXCLUSIVE};
    VkBuffer buffer; CHECK(vkCreateBuffer(device,&bci,NULL,&buffer));
    VkMemoryRequirements mr; vkGetBufferMemoryRequirements(device,buffer,&mr);
    VkPhysicalDeviceMemoryProperties mp; vkGetPhysicalDeviceMemoryProperties(physical,&mp);
    uint32_t type = UINT32_MAX; const VkMemoryPropertyFlags want = VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT;
    for (uint32_t i=0;i<mp.memoryTypeCount;++i)
        if ((mr.memoryTypeBits & (1u<<i)) && (mp.memoryTypes[i].propertyFlags & want) == want &&
            !(mp.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)) { type=i; break; }
    require(type != UINT32_MAX && mr.size >= 16384,"host-visible coherent GTT arena");
    VkMemoryAllocateInfo mai = {.sType=VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,.allocationSize=mr.size,.memoryTypeIndex=type};
    VkDeviceMemory memory; CHECK(vkAllocateMemory(device,&mai,NULL,&memory)); CHECK(vkBindBufferMemory(device,buffer,memory,0));
    uint8_t *data = NULL; CHECK(vkMapMemory(device,memory,0,16384,0,(void **)&data)); require(data != NULL,"arena pointer");
    phx34_runtime_bind_arena(data,16384);
    uint8_t expected[16384]; memset(expected,0xa5,sizeof(expected)); memcpy(data,expected,sizeof(expected));
    VkShaderModuleCreateInfo smci = {.sType=VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,.codeSize=sizeof(runtime_probe_spv),.pCode=runtime_probe_spv};
    VkShaderModule shader; CHECK(vkCreateShaderModule(device,&smci,NULL,&shader));
    VkDescriptorSetLayoutBinding binding = {.binding=0,.descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.descriptorCount=1,.stageFlags=VK_SHADER_STAGE_COMPUTE_BIT};
    VkDescriptorSetLayoutCreateInfo slci = {.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,.bindingCount=1,.pBindings=&binding};
    VkDescriptorSetLayout set_layout; CHECK(vkCreateDescriptorSetLayout(device,&slci,NULL,&set_layout));
    VkPushConstantRange push = {.stageFlags=VK_SHADER_STAGE_COMPUTE_BIT,.offset=0,.size=16};
    VkPipelineLayoutCreateInfo plci = {.sType=VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,.setLayoutCount=1,.pSetLayouts=&set_layout,.pushConstantRangeCount=1,.pPushConstantRanges=&push};
    VkPipelineLayout layout; CHECK(vkCreatePipelineLayout(device,&plci,NULL,&layout));
    VkComputePipelineCreateInfo cpci = {.sType=VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO,
        .stage={.sType=VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,.stage=VK_SHADER_STAGE_COMPUTE_BIT,.module=shader,.pName="main"},.layout=layout};
    VkPipeline pipeline; CHECK(vkCreateComputePipelines(device,VK_NULL_HANDLE,1,&cpci,NULL,&pipeline));
    VkDescriptorPoolSize pool_size = {.type=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.descriptorCount=1};
    VkDescriptorPoolCreateInfo dpci = {.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,.maxSets=1,.poolSizeCount=1,.pPoolSizes=&pool_size};
    VkDescriptorPool descriptor_pool; CHECK(vkCreateDescriptorPool(device,&dpci,NULL,&descriptor_pool));
    VkDescriptorSetAllocateInfo dsai = {.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,.descriptorPool=descriptor_pool,.descriptorSetCount=1,.pSetLayouts=&set_layout};
    VkDescriptorSet descriptor_set; CHECK(vkAllocateDescriptorSets(device,&dsai,&descriptor_set));
    VkDescriptorBufferInfo dbi = {.buffer=buffer,.offset=0,.range=16384};
    VkWriteDescriptorSet write = {.sType=VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,.dstSet=descriptor_set,.dstBinding=0,.descriptorCount=1,.descriptorType=VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,.pBufferInfo=&dbi};
    vkUpdateDescriptorSets(device,1,&write,0,NULL);
    VkCommandPoolCreateInfo cpi = {.sType=VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,.flags=VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,.queueFamilyIndex=family};
    VkCommandPool command_pool; CHECK(vkCreateCommandPool(device,&cpi,NULL,&command_pool));
    VkCommandBufferAllocateInfo cbai = {.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=command_pool,.level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,.commandBufferCount=1};
    VkCommandBuffer command; CHECK(vkAllocateCommandBuffers(device,&cbai,&command));
    VkQueue queue; vkGetDeviceQueue(device,family,0,&queue); require(queue != VK_NULL_HANDLE,"compute queue");
    VkFenceCreateInfo fci = {.sType=VK_STRUCTURE_TYPE_FENCE_CREATE_INFO}; VkFence fence; CHECK(vkCreateFence(device,&fci,NULL,&fence));
    for (unsigned pass=0;pass<2;++pass) {
        uint32_t pattern[4] = {0x7800c0deu ^ pass,0x13579bdfu + pass,0x2468ace0u ^ (pass<<16),0xc001d00du-pass};
        if (pass) { CHECK(vkResetCommandBuffer(command,0)); CHECK(vkResetFences(device,1,&fence)); }
        for (unsigned i=0;i<256;++i) { uint32_t poison=~pattern[i&3]; memcpy(data+0x2010+4*i,&poison,4); memcpy(expected+0x2010+4*i,&pattern[i&3],4); }
        __sync_synchronize();
        VkCommandBufferBeginInfo begin = {.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO}; CHECK(vkBeginCommandBuffer(command,&begin));
        VkMemoryBarrier before = {.sType=VK_STRUCTURE_TYPE_MEMORY_BARRIER,.srcAccessMask=VK_ACCESS_HOST_WRITE_BIT,.dstAccessMask=VK_ACCESS_SHADER_WRITE_BIT};
        vkCmdPipelineBarrier(command,VK_PIPELINE_STAGE_HOST_BIT,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,0,1,&before,0,NULL,0,NULL);
        vkCmdBindPipeline(command,VK_PIPELINE_BIND_POINT_COMPUTE,pipeline);
        vkCmdBindDescriptorSets(command,VK_PIPELINE_BIND_POINT_COMPUTE,layout,0,1,&descriptor_set,0,NULL);
        vkCmdPushConstants(command,layout,VK_SHADER_STAGE_COMPUTE_BIT,0,16,pattern); vkCmdDispatch(command,4,1,1);
        VkMemoryBarrier after = {.sType=VK_STRUCTURE_TYPE_MEMORY_BARRIER,.srcAccessMask=VK_ACCESS_SHADER_WRITE_BIT,.dstAccessMask=VK_ACCESS_HOST_READ_BIT};
        vkCmdPipelineBarrier(command,VK_PIPELINE_STAGE_COMPUTE_SHADER_BIT,VK_PIPELINE_STAGE_HOST_BIT,0,1,&after,0,NULL,0,NULL);
        CHECK(vkEndCommandBuffer(command));
        VkSubmitInfo submit = {.sType=VK_STRUCTURE_TYPE_SUBMIT_INFO,.commandBufferCount=1,.pCommandBuffers=&command}; CHECK(vkQueueSubmit(queue,1,&submit,fence));
        const uint64_t budgets[3] = {0,50000,2000000000ull}; VkResult wait=VK_TIMEOUT;
        for (unsigned i=0;i<3 && wait==VK_TIMEOUT;++i) wait=vkWaitForFences(device,1,&fence,VK_TRUE,budgets[i]);
        require(wait==VK_SUCCESS,"Vulkan fence positive completion");
        phx34_runtime_counts(&observed);
        require(observed.submits==pass+1 && observed.last_sequence && observed.retired_sequence>=observed.last_sequence,
                "native positive retirement before arena verification");
        __sync_synchronize();
        const volatile uint8_t *actual=data;
        for (size_t i=0;i<sizeof(expected);++i) if (actual[i]!=expected[i]) {
            fprintf(stderr,"FAIL: runtime whole-arena mismatch offset=%zu pass=%u actual=0x%02x expected=0x%02x\n",i,pass,actual[i],expected[i]);
            phx34_runtime_hold("whole 16-KiB arena verification");
        }
        phx34_runtime_verify_pass(pass);
        printf("{\"arena_pass\":%u,\"whole_bytes\":16384,\"offset_0x2010\":\"0x%08x\",\"fence_complete\":true,\"last_sequence\":%" PRIu64 ",\"retired_sequence\":%" PRIu64 "}\n",
               pass,pattern[0],observed.last_sequence,observed.retired_sequence); fflush(stdout);
    }
    vkDestroyFence(device,fence,NULL); vkDestroyCommandPool(device,command_pool,NULL); vkDestroyDescriptorPool(device,descriptor_pool,NULL);
    vkDestroyPipeline(device,pipeline,NULL); vkDestroyPipelineLayout(device,layout,NULL); vkDestroyDescriptorSetLayout(device,set_layout,NULL);
    vkDestroyShaderModule(device,shader,NULL); vkUnmapMemory(device,memory); vkDestroyBuffer(device,buffer,NULL); vkFreeMemory(device,memory,NULL);
    vkDestroyDevice(device,NULL); vkDestroyInstance(instance,NULL); require(!dlclose(library),"runtime unload");
    phx34_runtime_finish(); phx34_runtime_counts(&observed);
    printf("RUNTIME-PASS: real Vulkan compute path; opens=%u closes=%u submits=%u arena_passes=%u tail=%u reused_changed_IB=%u CPU_platform=%u first_IB_bytes=%u second_IB_bytes=%u; no desktop/FPS acceptance\n",
           observed.opens,observed.closes,observed.submits,observed.arena_passes,observed.tail_published,observed.reused_changed_IB,observed.CPU_platform,
           observed.first_reused_IB_bytes,observed.second_reused_IB_bytes);
    return 0;
}
