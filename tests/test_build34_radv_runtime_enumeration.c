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
extern void phx34_cpu_select(unsigned scenario);
extern unsigned phx34_cpu_attempts(void), phx34_cpu_sessions(void), phx34_cpu_hellos(void), phx34_cpu_releases(void);

static void report_r3(unsigned scenario, unsigned devices)
{
   printf("{\"scenario\":%u,\"physical_devices\":%u,\"opens\":%u,\"closes\":%u,\"open_attempts\":%u,"
          "\"service_releases\":%u,\"session_calls\":%u,\"hello_calls\":%u,\"BO_creates\":%u,"
          "\"fake_IOKit_calls\":%u,\"native_submits\":0,\"GPU_executed\":false}\n",
          scenario, devices, phx34_cpu_opens(), phx34_cpu_closes(), phx34_cpu_attempts(),
          phx34_cpu_releases(), phx34_cpu_sessions(), phx34_cpu_hellos(), phx34_cpu_creates(), phx34_cpu_calls());
}
#endif
static void fixture_require(int okay, unsigned line)
{
   if (!okay) { fprintf(stderr, "FAIL full-runtime CPU enumeration at %u\n", line); exit(78); }
}
#define require(okay) fixture_require((okay), __LINE__)

int main(int argc, char **argv)
{
#ifdef PHX34_CPU_R3
   require(argc == 3 && strlen(argv[2]) == 1 && argv[2][0] >= '0' && argv[2][0] <= '3');
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
   if (scenario) {
      const unsigned opened = scenario != 1;
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
   VkDevice device = VK_NULL_HANDLE; require(vkCreateDevice(physical, &di, NULL, &device) == VK_SUCCESS);
   require(phx34_cpu_opens() == (enabled ? 1u : 3u) && phx34_cpu_closes() == (enabled ? 0u : 2u));
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
