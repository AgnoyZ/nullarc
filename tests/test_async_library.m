#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <dispatch/dispatch.h>
#include <sys/sysctl.h>
#include <assert.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

static void nvlog(const char *fmt, ...) { (void)fmt; }
#include "async_library_queue.inc"

static _Atomic unsigned calls, active, peak, completions, destructions;
static _Atomic int holdBuild;
static dispatch_semaphore_t buildEntered, buildRelease;
@interface TestLibrary : NSObject
@property(nonatomic, copy) NSString *value;
@end
@implementation TestLibrary
@end
@interface TestDevice : NSObject
- (id<MTLLibrary>)newLibraryWithSource:(NSString *)source options:(MTLCompileOptions *)options error:(NSError **)error;
- (id<MTLLibrary>)newLibraryWithStitchedDescriptor:(id)descriptor error:(NSError **)error;
- (void)newLibraryWithSource:(NSString *)source options:(MTLCompileOptions *)options completionHandler:(MTLNewLibraryCompletionHandler)handler;
- (void)newLibraryWithStitchedDescriptor:(id)descriptor completionHandler:(MTLNewLibraryCompletionHandler)handler;
@end

static id<MTLLibrary> build(NSString *value, NSError **error) {
    assert(NSOperationQueue.currentQueue == nvmtl_pipeline_compile_queue());
    unsigned n = atomic_fetch_add(&active, 1) + 1, old = atomic_load(&peak);
    while (n > old && !atomic_compare_exchange_weak(&peak, &old, n)) {}
    atomic_fetch_add(&calls, 1);
    if (atomic_load(&holdBuild)) {
        dispatch_semaphore_signal(buildEntered);
        assert(dispatch_semaphore_wait(buildRelease, dispatch_time(DISPATCH_TIME_NOW, 15ll * NSEC_PER_SEC)) == 0);
    }
    if ([value containsString:@"fail"] || [value containsString:@"warn"])
        *error = [NSError errorWithDomain:@"SyntheticCompile" code:17 userInfo:nil];
    TestLibrary *lib = nil;
    if (![value containsString:@"fail"]) { lib = [TestLibrary new]; lib.value = value; }
    atomic_fetch_sub(&active, 1);
    return (id<MTLLibrary>)lib;
}
@implementation TestDevice
- (void)dealloc { atomic_fetch_add(&destructions, 1); }
- (id<MTLLibrary>)newLibraryWithSource:(NSString *)source options:(MTLCompileOptions *)options error:(NSError **)error {
    return build(source ? [NSString stringWithFormat:@"source:%@:%@", source, options.preprocessorMacros[@"VALUE"] ?: @0]
                        : @"fail:nil-source", error);
}
- (id<MTLLibrary>)newLibraryWithStitchedDescriptor:(id)desc error:(NSError **)error {
    MTLStitchedLibraryDescriptor *descriptor = desc;
    NSString *name = descriptor.functionGraphs.firstObject.functionName ?: @"empty";
    return build(descriptor ? [@"stitched:" stringByAppendingString:name] : @"fail:nil-descriptor", error);
}
#include "async_library_methods.inc"
@end

static void waitGroup(dispatch_group_t group) {
    assert(dispatch_group_wait(group, dispatch_time(DISPATCH_TIME_NOW, 20ll * NSEC_PER_SEC)) == 0);
}
static void verifyCallback(id<MTLLibrary> library, NSError *error, NSString *expected, BOOL warning) {
    assert(NSOperationQueue.currentQueue != nvmtl_pipeline_compile_queue());
    if ([expected containsString:@"fail"]) assert(!library && error.code == 17);
    else { assert([((TestLibrary *)library).value isEqual:expected]); assert(warning ? error.code == 17 : !error); }
    atomic_fetch_add(&completions, 1);
}
static MTLStitchedLibraryDescriptor *descriptor(NSString *name) {
    MTLFunctionStitchingGraph *graph = [MTLFunctionStitchingGraph new]; graph.functionName = name;
    MTLStitchedLibraryDescriptor *desc = [MTLStitchedLibraryDescriptor new]; desc.functionGraphs = @[graph];
    return desc;
}
static void snapshots(TestDevice *device) {
    NSOperationQueue *queue = nvmtl_pipeline_compile_queue(); queue.suspended = YES;
    NSMutableString *source = [NSMutableString stringWithString:@"before"];
    MTLCompileOptions *options = [MTLCompileOptions new]; options.preprocessorMacros = @{@"VALUE": @7};
    MTLStitchedLibraryDescriptor *desc = descriptor(@"before");
    dispatch_group_t group = dispatch_group_create();
    dispatch_group_enter(group);
    [device newLibraryWithSource:source options:options completionHandler:^(id<MTLLibrary> lib, NSError *error) {
        verifyCallback(lib, error, @"source:before:7", NO); dispatch_group_leave(group);
    }];
    dispatch_group_enter(group);
    [device newLibraryWithStitchedDescriptor:desc completionHandler:^(id<MTLLibrary> lib, NSError *error) {
        verifyCallback(lib, error, @"stitched:before", NO); dispatch_group_leave(group);
    }];
    // Both APIs returned without running their compiler while the pool is suspended.
    assert(atomic_load(&calls) == 0 && atomic_load(&completions) == 0);
    [source setString:@"after"]; options.preprocessorMacros = @{@"VALUE": @9}; desc.functionGraphs = @[];
    queue.suspended = NO; waitGroup(group); [queue waitUntilAllOperationsAreFinished];
    assert(atomic_load(&calls) == 2 && atomic_load(&completions) == 2);
}
static void boundedConcurrency(TestDevice *device, unsigned width) {
    buildEntered = dispatch_semaphore_create(0); buildRelease = dispatch_semaphore_create(0);
    atomic_store(&holdBuild, 1);
    unsigned before = atomic_load(&calls), beforeCallback = atomic_load(&completions);
    dispatch_group_t returned = dispatch_group_create(), completed = dispatch_group_create();
    for (unsigned i = 0; i < width + 3; ++i) {
        dispatch_group_enter(completed);
        dispatch_group_async(returned, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool {
            MTLNewLibraryCompletionHandler handler = ^(id<MTLLibrary> lib, NSError *error) {
                verifyCallback(lib, error, i % 2 ? @"source:held:0" : @"stitched:held", NO);
                dispatch_group_leave(completed);
            };
            if (i % 2) [device newLibraryWithSource:@"held" options:nil completionHandler:handler];
            else [device newLibraryWithStitchedDescriptor:descriptor(@"held") completionHandler:handler];
        }});
    }
    waitGroup(returned);
    for (unsigned i = 0; i < width; ++i)
        assert(dispatch_semaphore_wait(buildEntered, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
    assert(atomic_load(&active) == width && atomic_load(&calls) == before + width);
    assert(atomic_load(&completions) == beforeCallback);
    atomic_store(&holdBuild, 0);
    for (unsigned i = 0; i < width; ++i) dispatch_semaphore_signal(buildRelease);
    waitGroup(completed); [nvmtl_pipeline_compile_queue() waitUntilAllOperationsAreFinished];
    assert(atomic_load(&calls) == before + width + 3 && atomic_load(&active) == 0);
    assert(atomic_load(&completions) == beforeCallback + width + 3);
}
static void errorsAndNilHandlers(TestDevice *device) {
    dispatch_group_t group = dispatch_group_create();
    for (NSString *name in @[@"ok", @"fail", @"warn"]) {
        dispatch_group_enter(group);
        [device newLibraryWithSource:name options:nil completionHandler:^(id<MTLLibrary> lib, NSError *error) {
            verifyCallback(lib, error, [NSString stringWithFormat:@"source:%@:0", name], [name isEqual:@"warn"]);
            dispatch_group_leave(group);
        }];
        dispatch_group_enter(group);
        [device newLibraryWithStitchedDescriptor:descriptor(name) completionHandler:^(id<MTLLibrary> lib, NSError *error) {
            verifyCallback(lib, error, [@"stitched:" stringByAppendingString:name], NO);
            dispatch_group_leave(group);
        }];
    }
    dispatch_group_enter(group);
    [device newLibraryWithSource:nil options:nil completionHandler:^(id<MTLLibrary> lib, NSError *error) {
        verifyCallback(lib, error, @"fail:nil-source", NO); dispatch_group_leave(group);
    }];
    dispatch_group_enter(group);
    [device newLibraryWithStitchedDescriptor:nil completionHandler:^(id<MTLLibrary> lib, NSError *error) {
        verifyCallback(lib, error, @"fail:nil-descriptor", NO); dispatch_group_leave(group);
    }];
    waitGroup(group); [nvmtl_pipeline_compile_queue() waitUntilAllOperationsAreFinished];
    unsigned before = atomic_load(&calls), callbacks = atomic_load(&completions);
    [device newLibraryWithSource:@"nil-handler" options:nil completionHandler:nil];
    [device newLibraryWithStitchedDescriptor:descriptor(@"nil-handler") completionHandler:nil];
    [nvmtl_pipeline_compile_queue() waitUntilAllOperationsAreFinished];
    assert(atomic_load(&calls) == before + 2 && atomic_load(&completions) == callbacks);
}
static void reentrantCompletion(TestDevice *device) {
    dispatch_group_t group = dispatch_group_create(); dispatch_group_enter(group);
    [device newLibraryWithSource:@"outer" options:nil completionHandler:^(id<MTLLibrary> lib, NSError *error) {
        verifyCallback(lib, error, @"source:outer:0", NO);
        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        [device newLibraryWithStitchedDescriptor:descriptor(@"inner") completionHandler:^(id<MTLLibrary> inner, NSError *why) {
            verifyCallback(inner, why, @"stitched:inner", NO); dispatch_semaphore_signal(done);
        }];
        assert(dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, 8ll * NSEC_PER_SEC)) == 0);
        dispatch_group_leave(group);
    }];
    waitGroup(group);
}
static void lifetime(void) {
    NSOperationQueue *queue = nvmtl_pipeline_compile_queue(); queue.suspended = YES;
    dispatch_group_t group = dispatch_group_create(); dispatch_group_enter(group);
    unsigned before = atomic_load(&destructions); __weak TestDevice *weak;
    @autoreleasepool {
        TestDevice *temporary = [TestDevice new]; weak = temporary;
        [temporary newLibraryWithSource:@"retained" options:nil completionHandler:^(id<MTLLibrary> lib, NSError *error) {
            verifyCallback(lib, error, @"source:retained:0", NO); dispatch_group_leave(group);
        }];
    }
    assert(weak && atomic_load(&destructions) == before);
    queue.suspended = NO; waitGroup(group); [queue waitUntilAllOperationsAreFinished];
    // NSOperationQueue may release completed operation objects after its wait.
    uint64_t deadline = clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) + 8ull * NSEC_PER_SEC;
    while (weak) { assert(clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW) < deadline); usleep(1000); }
    assert(atomic_load(&destructions) == before + 1);
}
static void stress(TestDevice *device) {
    dispatch_group_t callers = dispatch_group_create(), callbacks = dispatch_group_create();
    __block _Atomic unsigned received = 0;
    for (unsigned worker = 0; worker < 16; ++worker) dispatch_group_async(callers,
        dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{ @autoreleasepool {
            for (unsigned i = 0; i < 100; ++i) {
                NSString *name = [NSString stringWithFormat:@"stress-%u-%u", worker, i];
                NSString *expected = i % 2 ? [NSString stringWithFormat:@"source:%@:0", name] : [@"stitched:" stringByAppendingString:name];
                dispatch_group_enter(callbacks);
                __block _Atomic unsigned once = 0;
                MTLNewLibraryCompletionHandler handler = ^(id<MTLLibrary> lib, NSError *error) {
                    assert(atomic_fetch_add(&once, 1) == 0); verifyCallback(lib, error, expected, NO);
                    atomic_fetch_add(&received, 1); dispatch_group_leave(callbacks);
                };
                if (i % 2) [device newLibraryWithSource:name options:nil completionHandler:handler];
                else [device newLibraryWithStitchedDescriptor:descriptor(name) completionHandler:handler];
            }
        }});
    waitGroup(callers); waitGroup(callbacks); [nvmtl_pipeline_compile_queue() waitUntilAllOperationsAreFinished];
    assert(atomic_load(&received) == 1600 && atomic_load(&active) == 0);
}
int main(int argc, const char **argv) { @autoreleasepool {
    assert(argc == 2); unsigned width = (unsigned)atoi(argv[1]); assert(width == 1 || width == 2);
    unsetenv("NVMTL_PIPELINE_THREADS"); assert(nvmtl_pipeline_compile_width() >= 1 && nvmtl_pipeline_compile_width() <= 8);
    setenv("NVMTL_PIPELINE_THREADS", "64", 1); assert(nvmtl_pipeline_compile_width() == 64);
    setenv("NVMTL_PIPELINE_THREADS", argv[1], 1); assert(nvmtl_pipeline_compile_queue().maxConcurrentOperationCount == (NSInteger)width);
    TestDevice *device = [TestDevice new]; snapshots(device); boundedConcurrency(device, width);
    errorsAndNilHandlers(device); reentrantCompletion(device); lifetime(); stress(device);
    assert(atomic_load(&peak) == width);
    printf("{\"actual_methods\":2,\"actual_queue\":true,\"width\":%u,\"peak_active\":%u,"
           "\"snapshot_and_return_before_build\":true,\"callback_reentry\":true,\"retained_owner\":true,"
           "\"error_and_warning_propagation\":true,\"stress_requests\":1600,\"hardware_executed\":false}\n", width, atomic_load(&peak));
} }
