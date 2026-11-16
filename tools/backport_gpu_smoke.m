// SPDX-License-Identifier: MIT OR GPL-2.0-only
// Bounded real-GPU regression for the isolated build-34 backports.
// This program neither installs a driver nor arms/initializes a display.
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <IOSurface/IOSurface.h>
#import <IOKit/IOKitLib.h>
#import <objc/runtime.h>
#include <mach-o/dyld.h>
#include <mach-o/loader.h>
#include <uuid/uuid.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static BOOL targetDevice(id<MTLDevice> device) {
    io_registry_entry_t entry = IOServiceGetMatchingService(kIOMainPortDefault,
        IORegistryEntryIDMatching(device.registryID));
    for (unsigned depth = 0; entry && depth < 32; ++depth) {
        if (IOObjectConformsTo(entry, "IOPCIDevice")) {
            CFTypeRef v = IORegistryEntryCreateCFProperty(entry, CFSTR("vendor-id"), kCFAllocatorDefault, 0);
            CFTypeRef p = IORegistryEntryCreateCFProperty(entry, CFSTR("device-id"), kCFAllocatorDefault, 0);
            uint32_t vendor = 0, product = 0;
            BOOL valid = v && p && CFGetTypeID(v) == CFDataGetTypeID() && CFGetTypeID(p) == CFDataGetTypeID()
                && CFDataGetLength(v) == 4 && CFDataGetLength(p) == 4;
            if (valid) { memcpy(&vendor, CFDataGetBytePtr(v), 4); memcpy(&product, CFDataGetBytePtr(p), 4); }
            if (v) CFRelease(v);
            if (p) CFRelease(p);
            IOObjectRelease(entry);
            return valid && vendor == 0x1002 && product == 0x1900;
        }
        io_registry_entry_t parent = IO_OBJECT_NULL;
        kern_return_t status = IORegistryEntryGetParentEntry(entry, kIOServicePlane, &parent);
        IOObjectRelease(entry);
        entry = status == KERN_SUCCESS ? parent : IO_OBJECT_NULL;
    }
    if (entry) IOObjectRelease(entry);
    return NO;
}

static BOOL expectedPlugin(id<MTLDevice> device) {
    const char *expected = getenv("NULLARC_EXPECT_PLUGIN_UUID");
    const char *image = class_getImageName([device class]);
    if (!expected || !image || !strstr(image, "/NVMTLDriver.bundle/Contents/MacOS/NVMTLDriver")) return NO;
    for (uint32_t i = 0; i < _dyld_image_count(); ++i) {
        if (strcmp(_dyld_get_image_name(i), image)) continue;
        const struct mach_header_64 *header = (const struct mach_header_64 *)_dyld_get_image_header(i);
        if (header->magic != MH_MAGIC_64) return NO;
        const struct load_command *command = (const struct load_command *)(header + 1);
        for (uint32_t j = 0; j < header->ncmds; ++j) {
            if (command->cmd == LC_UUID && command->cmdsize == sizeof(struct uuid_command)) {
                uuid_string_t value;
                uuid_unparse_upper(((const struct uuid_command *)command)->uuid, value);
                return !strcasecmp(expected, value);
            }
            if (command->cmdsize < sizeof(*command)) return NO;
            command = (const struct load_command *)((const char *)command + command->cmdsize);
        }
    }
    return NO;
}

static BOOL finish(id<MTLCommandBuffer> command) {
    if (!command) return NO;
    dispatch_semaphore_t done = dispatch_semaphore_create(0);
    [command addCompletedHandler:^(id<MTLCommandBuffer> completed) { (void)completed; dispatch_semaphore_signal(done); }];
    [command commit];
    if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 15LL * NSEC_PER_SEC))) {
        fprintf(stderr, "FAIL: GPU completion deadline; no automatic retry\n");
        return NO;
    }
    if (command.status != MTLCommandBufferStatusCompleted) {
        fprintf(stderr, "FAIL: command status=%lu\n", (unsigned long)command.status);
        return NO;
    }
    return YES;
}

static NSString *const shader = @"#include <metal_stdlib>\nusing namespace metal;\n"
    "vertex float4 triangle(uint i [[vertex_id]]) { const float2 p[3]={float2(-1,-1),float2(3,-1),float2(-1,3)}; return float4(p[i],0,1); }\n"
    "fragment float4 pixels(float4 p [[position]]) { return float4(uint(p.x)&1u,uint(p.y)&1u,1,1); }\n"
    "kernel void sample0(texture2d<float,access::sample> t [[texture(0)]], sampler s [[sampler(0)]], device uint4 *o [[buffer(0)]], uint2 i [[thread_position_in_grid]]) { if(i.x<4&&i.y<4) o[i.y*4+i.x]=uint4(round(t.sample(s,float2(i)+0.5)*255.0)); }\n"
    "kernel void sample15(texture2d<float,access::sample> t [[texture(0)]], sampler s [[sampler(15)]], device uint4 *o [[buffer(0)]], uint2 i [[thread_position_in_grid]]) { if(i.x<4&&i.y<4) o[i.y*4+i.x]=uint4(round(t.sample(s,float2(i)+0.5)*255.0)); }\n";

int main(int argc, const char *argv[]) { @autoreleasepool {
    (void)argv;
    if (argc != 1) return 2;
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (!device || !targetDevice(device) || !expectedPlugin(device)) {
        fprintf(stderr, "FAIL: target PCI device or expected loaded plugin image not verified\n"); return 3;
    }
    NSError *error = nil;
    id<MTLLibrary> library = [device newLibraryWithSource:shader options:nil error:&error];
    if (!library) { fprintf(stderr, "FAIL: shader compile: %s\n", error.description.UTF8String); return 4; }
    MTLRenderPipelineDescriptor *renderDescriptor = [MTLRenderPipelineDescriptor new];
    renderDescriptor.vertexFunction = [library newFunctionWithName:@"triangle"];
    renderDescriptor.fragmentFunction = [library newFunctionWithName:@"pixels"];
    renderDescriptor.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
    id<MTLRenderPipelineState> render = [device newRenderPipelineStateWithDescriptor:renderDescriptor error:&error];
    if (!render) { fprintf(stderr, "FAIL: render pipeline: %s\n", error.description.UTF8String); return 5; }
    size_t row = IOSurfaceAlignProperty(kIOSurfaceBytesPerRow, 16);
    IOSurfaceRef surface = IOSurfaceCreate((__bridge CFDictionaryRef)@{
        (__bridge NSString *)kIOSurfaceWidth:@4, (__bridge NSString *)kIOSurfaceHeight:@4,
        (__bridge NSString *)kIOSurfaceBytesPerElement:@4, (__bridge NSString *)kIOSurfaceBytesPerRow:@(row),
        (__bridge NSString *)kIOSurfaceAllocSize:@(row * 4), (__bridge NSString *)kIOSurfacePixelFormat:@(0x52474241u)});
    if (!surface) return 6;
    MTLTextureDescriptor *textureDescriptor = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:4 height:4 mipmapped:NO];
    textureDescriptor.storageMode = MTLStorageModeShared;
    textureDescriptor.usage = MTLTextureUsageRenderTarget | MTLTextureUsageShaderRead;
    id<MTLTexture> writer = [device newTextureWithDescriptor:textureDescriptor iosurface:surface plane:0];
    id<MTLTexture> reader = [device newTextureWithDescriptor:textureDescriptor iosurface:surface plane:0];
    if (!writer || !reader) { CFRelease(surface); return 7; }
    id<MTLCommandQueue> queue = [device newCommandQueue];
    if (!queue) { CFRelease(surface); return 8; }
    MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture = writer;
    pass.colorAttachments[0].loadAction = MTLLoadActionClear;
    pass.colorAttachments[0].storeAction = MTLStoreActionStore;
    pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 0);
    id<MTLCommandBuffer> command = [queue commandBuffer];
    id<MTLRenderCommandEncoder> encoder = [command renderCommandEncoderWithDescriptor:pass];
    if (!command || !encoder) { CFRelease(surface); return 9; }
    [encoder setRenderPipelineState:render];
    [encoder drawPrimitives:MTLPrimitiveTypeTriangle vertexStart:0 vertexCount:3];
    [encoder endEncoding];
    if (!finish(command)) { CFRelease(surface); return 10; }
    for (NSUInteger slot = 0; slot <= 15; slot += 15) {
        id<MTLComputePipelineState> compute = [device newComputePipelineStateWithFunction:[library newFunctionWithName:slot ? @"sample15" : @"sample0"] error:&error];
        MTLSamplerDescriptor *samplerDescriptor = [MTLSamplerDescriptor new];
        samplerDescriptor.normalizedCoordinates = NO;
        samplerDescriptor.minFilter = MTLSamplerMinMagFilterNearest;
        samplerDescriptor.magFilter = MTLSamplerMinMagFilterNearest;
        id<MTLSamplerState> sampler = [device newSamplerStateWithDescriptor:samplerDescriptor];
        id<MTLBuffer> output = [device newBufferWithLength:16 * 4 * sizeof(uint32_t) options:MTLResourceStorageModeShared];
        if (!compute || !sampler || !output || !output.contents) { CFRelease(surface); return 11; }
        memset(output.contents, 0xa5, output.length);
        command = [queue commandBuffer];
        id<MTLComputeCommandEncoder> c = [command computeCommandEncoder];
        if (!command || !c) { CFRelease(surface); return 12; }
        [c setComputePipelineState:compute];
        [c setTexture:reader atIndex:0];
        [c setSamplerState:sampler atIndex:slot];
        [c setBuffer:output offset:0 atIndex:0];
        [c dispatchThreadgroups:MTLSizeMake(4,4,1) threadsPerThreadgroup:MTLSizeMake(1,1,1)];
        [c endEncoding];
        if (!finish(command)) { CFRelease(surface); return 13; }
        const uint32_t *values = output.contents;
        for (unsigned y = 0; y < 4; ++y) for (unsigned x = 0; x < 4; ++x) {
            const uint32_t expected[4] = {(x & 1u) * 255, (y & 1u) * 255, 255, 255};
            for (unsigned channel = 0; channel < 4; ++channel) {
                uint32_t actual = values[(y * 4 + x) * 4 + channel];
                if (actual != expected[channel]) {
                    fprintf(stderr, "FAIL: slot=%lu pixel=%u,%u channel=%u got=%u expected=%u\n", (unsigned long)slot, x,y,channel,actual,expected[channel]);
                    CFRelease(surface); return 14;
                }
            }
        }
    }
    CFRelease(surface);
    puts("{\"target_PCI_verified\":true,\"loaded_plugin_image_verified\":true,\"completed_commands\":3,\"sampler_slots\":[0,15],\"IOSurface_sampled_pixels\":32,\"verified_channels\":128}");
    return 0;
} }
