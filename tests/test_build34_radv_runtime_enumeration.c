/* SPDX-License-Identifier: MIT */
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <IOKit/IOKitLib.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern unsigned phx34_cpu_opens(void), phx34_cpu_closes(void), phx34_cpu_creates(void);
extern unsigned phx34_cpu_calls(void), phx34_cpu_blocked(void);
extern void phx34_cpu_arm(void);
#ifdef PHX34_CPU_R3
#include "build34_radv_runtime_cpu.h"
extern void phx34_cpu_select(unsigned scenario);
extern unsigned phx34_cpu_attempts(void), phx34_cpu_sessions(void), phx34_cpu_hellos(void), phx34_cpu_releases(void);

static void report_r3(unsigned scenario, unsigned devices)
{
   const struct cpu_exact_trace *trace = phx34_cpu_exact_trace();
   printf("{\"scenario\":%u,\"physical_devices\":%u,\"opens\":%u,\"closes\":%u,\"open_attempts\":%u,"
          "\"service_releases\":%u,\"session_calls\":%u,\"hello_calls\":%u,\"BO_creates\":%u,"
          "\"fake_IOKit_calls\":%u,\"modeled_exact_submits\":%u,\"zero_polls\":%u,\"positive_waits\":%u,"
          "\"positive_pending\":%u,"
          "\"prefix_snapshots\":%u,\"exact_acks\":%u,\"gap_prefixes\":%u,\"closed_prefixes\":%u,"
          "\"native_submits\":0,\"GPU_executed\":false}\n",
          scenario, devices, phx34_cpu_opens(), phx34_cpu_closes(), phx34_cpu_attempts(),
          phx34_cpu_releases(), phx34_cpu_sessions(), phx34_cpu_hellos(), phx34_cpu_creates(), phx34_cpu_calls(),
          trace->submits, trace->zero_polls, trace->positive_waits, trace->positive_pending, trace->prefixes, trace->acks,
          trace->gap_prefixes, trace->closed_prefixes);
}
#endif
static void fixture_require(int okay, unsigned line)
{
   if (!okay) { fprintf(stderr, "FAIL full-runtime CPU enumeration at %u\n", line); exit(78); }
}
#define require(okay) fixture_require((okay), __LINE__)

#ifdef PHX34_CPU_R3
static void test_submit(VkDevice device, const VkDeviceQueueCreateInfo *families, PFN_vkGetDeviceProcAddr get_proc,
                        unsigned scenario)
{
#define DFN(name) PFN_##name name = (PFN_##name)get_proc(device, #name); require(name != NULL)
   DFN(vkGetDeviceQueue);
   DFN(vkCreateCommandPool); DFN(vkDestroyCommandPool); DFN(vkAllocateCommandBuffers);
   DFN(vkBeginCommandBuffer); DFN(vkEndCommandBuffer);
   DFN(vkCreateFence); DFN(vkDestroyFence); DFN(vkGetFenceStatus); DFN(vkQueueSubmit); DFN(vkWaitForFences);
#undef DFN
   const uint32_t count = scenario == CPU_EXACT_DUAL ? 2 : 1;
   VkCommandPool pools[CPU_QUEUE_COUNT] = {0};
   VkFence fences[CPU_QUEUE_COUNT] = {0};
   for (uint32_t index = 0; index < count; ++index) {
      const uint32_t family = families[index].queueFamilyIndex;
      VkQueue queue = VK_NULL_HANDLE;
      vkGetDeviceQueue(device, family, 0, &queue);
      require(queue != VK_NULL_HANDLE);
      const VkCommandPoolCreateInfo pool_info = {.sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
                                                .queueFamilyIndex = family};
      require(vkCreateCommandPool(device, &pool_info, NULL, &pools[index]) == VK_SUCCESS);
      VkCommandBuffer command = VK_NULL_HANDLE;
      const VkCommandBufferAllocateInfo alloc = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
         .commandPool = pools[index], .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY, .commandBufferCount = 1};
      require(vkAllocateCommandBuffers(device, &alloc, &command) == VK_SUCCESS);
      const VkCommandBufferBeginInfo begin = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
      require(vkBeginCommandBuffer(command, &begin) == VK_SUCCESS);
      require(vkEndCommandBuffer(command) == VK_SUCCESS);
      const VkFenceCreateInfo fence_info = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
      require(vkCreateFence(device, &fence_info, NULL, &fences[index]) == VK_SUCCESS);
      require(vkGetFenceStatus(device, fences[index]) == VK_NOT_READY);
      const VkSubmitInfo submit = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
                                   .commandBufferCount = 1, .pCommandBuffers = &command};
      const VkResult expected = scenario == CPU_SUBMIT_REFUSED ? VK_ERROR_DEVICE_LOST : VK_SUCCESS;
      require(vkQueueSubmit(queue, 1, &submit, fences[index]) == expected);
   }
   const struct cpu_exact_trace *trace = phx34_cpu_exact_trace();
   if (scenario == CPU_SUBMIT_REFUSED) {
      require(!trace->submits);
   } else if (scenario == CPU_EXACT_SUBMIT) {
      require(trace->submits == 1 && !trace->positive_waits && !trace->acks);
      require(vkGetFenceStatus(device, fences[0]) == VK_NOT_READY);
      require(vkWaitForFences(device, 1, fences, VK_TRUE, 0) == VK_TIMEOUT);
      require(trace->zero_polls >= 2 && !trace->positive_waits && !trace->acks);
      require(vkWaitForFences(device, 1, fences, VK_TRUE, 200000000ull) == VK_SUCCESS);
      require(trace->positive_waits == 1 && trace->prefixes == trace->zero_polls + 1 && trace->acks == 1);
      const unsigned calls = phx34_cpu_calls();
      require(vkGetFenceStatus(device, fences[0]) == VK_SUCCESS && phx34_cpu_calls() == calls);
   } else {
      require(trace->submits == 2 && !trace->acks && !trace->completed_mask);
      require(vkWaitForFences(device, count, fences, VK_FALSE, 0) == VK_TIMEOUT);
      phx34_cpu_schedule_completion(CPU_GFX);
      require(vkWaitForFences(device, count, fences, VK_FALSE, 0) == VK_SUCCESS);
      require(trace->completed_mask == (1u << CPU_GFX) && trace->acks == 1 &&
              trace->ack_order[0] == CPU_GFX && trace->gap_prefixes && !trace->closed_prefixes);
      const unsigned calls = phx34_cpu_calls();
      require(vkGetFenceStatus(device, fences[1]) == VK_SUCCESS && phx34_cpu_calls() == calls);
      require(vkGetFenceStatus(device, fences[0]) == VK_NOT_READY);
      require(vkWaitForFences(device, count, fences, VK_TRUE, 0) == VK_TIMEOUT);
      require(vkWaitForFences(device, count, fences, VK_TRUE, 25000000ull) == VK_TIMEOUT);
      require(trace->positive_pending && trace->acks == 1 && !trace->closed_prefixes);
      phx34_cpu_schedule_completion(CPU_COMPUTE);
      require(vkWaitForFences(device, count, fences, VK_TRUE, 200000000ull) == VK_SUCCESS);
      require(trace->positive_waits == trace->positive_pending + 1 &&
              trace->prefixes == trace->zero_polls + trace->positive_waits &&
              trace->closed_prefixes == 1 && trace->acks == 2 && trace->ack_order[1] == CPU_COMPUTE);
      require(vkWaitForFences(device, count, fences, VK_TRUE, 0) == VK_SUCCESS);
   }
   for (uint32_t index = 0; index < count; ++index) {
      vkDestroyFence(device, fences[index], NULL);
      vkDestroyCommandPool(device, pools[index], NULL);
   }
}
#endif

int main(int argc, char **argv)
{
#ifdef PHX34_CPU_R3
   require(argc == 3 && strlen(argv[2]) == 1 && argv[2][0] >= '0' && argv[2][0] <= '6');
   const unsigned scenario = argv[2][0] - '0';
   phx34_cpu_select(scenario);
#else
   require(argc == 3 && (!strcmp(argv[2], "1") || !strcmp(argv[2], "0")));
#endif
   io_connect_t connection = 0;
   require(IOServiceOpen(0, mach_task_self(), 0, &connection) == kIOReturnNotPermitted &&
           !connection && phx34_cpu_blocked() == 1 && !phx34_cpu_opens());
#ifndef PHX34_CPU_R3
   require(!setenv("RADV_DARWIN_BUILD34_IB_TAIL", argv[2], 1));
#endif
   void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL); require(library != NULL);
   require(phx34_cpu_blocked() == 1 && !phx34_cpu_opens());
   PFN_vkGetInstanceProcAddr gpa = (PFN_vkGetInstanceProcAddr)dlsym(library, "vk_icdGetInstanceProcAddr"); require(gpa != NULL);
   PFN_vkCreateInstance create = (PFN_vkCreateInstance)gpa(NULL, "vkCreateInstance"); require(create != NULL);
   VkApplicationInfo app = {.sType=VK_STRUCTURE_TYPE_APPLICATION_INFO, .apiVersion=VK_API_VERSION_1_2};
   VkInstanceCreateInfo ci = {.sType=VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, .pApplicationInfo=&app};
   VkInstance instance = VK_NULL_HANDLE; require(create(&ci, NULL, &instance) == VK_SUCCESS);
   require(!phx34_cpu_opens() && phx34_cpu_blocked() == 1);
   phx34_cpu_arm();
#define IFN(name) PFN_##name name = (PFN_##name)gpa(instance, #name); require(name != NULL)
   IFN(vkEnumeratePhysicalDevices); IFN(vkGetPhysicalDeviceProperties); IFN(vkGetPhysicalDeviceQueueFamilyProperties);
   IFN(vkCreateDevice); IFN(vkGetDeviceProcAddr); IFN(vkDestroyInstance);
#undef IFN
   uint32_t count = 1; VkPhysicalDevice physical = VK_NULL_HANDLE;
   require(vkEnumeratePhysicalDevices(instance, &count, &physical) == VK_SUCCESS);
#ifdef PHX34_CPU_R3
   require(phx34_cpu_attempts() == 1 && phx34_cpu_releases() == 1);
   if (scenario >= CPU_OPEN_REFUSED && scenario <= CPU_SESSION_SHORT) {
      const unsigned opened = scenario != CPU_OPEN_REFUSED;
      require(!count && !physical && phx34_cpu_opens() == opened && phx34_cpu_closes() == opened);
      require(phx34_cpu_hellos() == opened && phx34_cpu_sessions() == opened && !phx34_cpu_creates());
      require(phx34_cpu_calls() == 2 * opened);
      vkDestroyInstance(instance, NULL);
      require(!dlclose(library) && phx34_cpu_attempts() == 1 && phx34_cpu_closes() == opened && !phx34_cpu_blocked());
      report_r3(scenario, 0);
      return 0;
   }
#endif
   require(count == 1 && physical);
   VkPhysicalDeviceProperties properties; vkGetPhysicalDeviceProperties(physical, &properties);
   require(properties.vendorID == 0x1002 && properties.deviceID == 0x1900);
#ifdef PHX34_CPU_R3
   const unsigned enabled = 1;
   count = 0;
   require(vkEnumeratePhysicalDevices(instance, &count, NULL) == VK_SUCCESS && count == 1);
   require(phx34_cpu_hellos() == 2 && phx34_cpu_sessions() == 1);
#else
   const unsigned enabled = argv[2][0] == '1';
#endif
   require(phx34_cpu_opens() == (enabled ? 1u : 2u) && phx34_cpu_closes() == (enabled ? 0u : 2u));
   uint32_t family_count = 0; vkGetPhysicalDeviceQueueFamilyProperties(physical, &family_count, NULL);
   require(family_count && family_count <= 16); VkQueueFamilyProperties families[16];
   vkGetPhysicalDeviceQueueFamilyProperties(physical, &family_count, families);
   uint32_t compute = UINT32_MAX;
   for (uint32_t i = 0; i < family_count; ++i)
      if (families[i].queueCount && (families[i].queueFlags & VK_QUEUE_COMPUTE_BIT) &&
          !(families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT)) { compute = i; break; }
   require(compute != UINT32_MAX);
   float priority = 1;
   VkDeviceQueueCreateInfo qi = {.sType=VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO, .queueFamilyIndex=compute,
                                .queueCount=1, .pQueuePriorities=&priority};
   VkDeviceCreateInfo di = {.sType=VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO, .queueCreateInfoCount=1, .pQueueCreateInfos=&qi};
#ifdef PHX34_CPU_R3
   VkDeviceQueueCreateInfo tested_families[CPU_QUEUE_COUNT] = {qi, qi};
   if (scenario == CPU_EXACT_DUAL) {
      uint32_t graphics = 0;
      while (graphics < family_count && (!families[graphics].queueCount ||
                                         !(families[graphics].queueFlags & VK_QUEUE_GRAPHICS_BIT)))
         ++graphics;
      require(graphics < family_count && graphics != compute);
      tested_families[1].queueFamilyIndex = graphics;
      di.queueCreateInfoCount = CPU_QUEUE_COUNT;
      di.pQueueCreateInfos = tested_families;
   }
#endif
   VkDevice device = VK_NULL_HANDLE; require(vkCreateDevice(physical, &di, NULL, &device) == VK_SUCCESS);
   require(phx34_cpu_opens() == (enabled ? 1u : 3u) && phx34_cpu_closes() == (enabled ? 0u : 2u));
#ifdef PHX34_CPU_R3
   if (scenario >= CPU_SUBMIT_REFUSED)
      test_submit(device, tested_families, vkGetDeviceProcAddr, scenario);
#endif
   PFN_vkDestroyDevice destroy = (PFN_vkDestroyDevice)vkGetDeviceProcAddr(device, "vkDestroyDevice"); require(destroy != NULL);
   destroy(device, NULL);
   require(phx34_cpu_closes() == (enabled ? 0u : 3u));
   vkDestroyInstance(instance, NULL);
   require(phx34_cpu_opens() == phx34_cpu_closes() && phx34_cpu_creates() >= enabled && !phx34_cpu_blocked());
   require(!dlclose(library));
#ifdef PHX34_CPU_R3
   require(phx34_cpu_attempts() == 1 && phx34_cpu_sessions() == 1);
   report_r3(scenario, 1);
#else
   printf("{\"CPU_only\":true,\"real_full_Vulkan_enumeration_and_device_lifecycle\":true,\"tail_enabled\":%s,"
          "\"opens\":%u,\"closes\":%u,\"BO_creates\":%u,\"fake_IOKit_calls\":%u,\"native_submits\":0,\"GPU_executed\":false}\n",
          enabled ? "true" : "false", phx34_cpu_opens(), phx34_cpu_closes(), phx34_cpu_creates(), phx34_cpu_calls());
#endif
   return 0;
}
