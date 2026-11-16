#!/usr/bin/env python3
"""Exercise extracted PR15/16/19/22 production code on CPU, never a GPU.

Foundation/Objective-C and POSIX are real; descriptors, surfaces and injected
I/O failures are doubles. Each binary runs under ASan/UBSan with a timeout.
"""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/tests/upstream34_plugin_prs"
DEVICE = ROOT / "src/nmplugin/NVMTLDevice.m"
PRELUDE = r'''
#import <Foundation/Foundation.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdatomic.h>
#import <objc/message.h>
#import <objc/runtime.h>
static void nvlog(const char *format, ...) { (void)format; }
'''


def function(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class PluginPRs(unittest.TestCase):
    def compile(self, name, source):
        BUILD.mkdir(parents=True, exist_ok=True)
        path, binary = BUILD / (name + ".m"), BUILD / name
        path.write_text(PRELUDE + source)
        subprocess.run([
            "xcrun", "clang", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-Wno-unused-parameter", "-fobjc-arc", "-fblocks",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
            "-fno-omit-frame-pointer", str(path), "-framework", "Foundation",
            "-o", str(binary),
        ], check=True, timeout=60)
        return binary

    def run_binary(self, binary, *args, optout=False):
        env = {k: v for k, v in os.environ.items() if not k.startswith("NVMTL_")}
        env["ASAN_OPTIONS"] = "detect_leaks=0"
        if optout:
            env["NVMTL_NO_SURF_UNKNOWN"] = "1"
        subprocess.run([str(binary), *args], env=env, check=True, timeout=10)

    def test_surface_cache_key(self):
        text = DEVICE.read_text()
        start = text.index("NSString *key = surf ?")
        code = text[start:text.index("NVMTLTexture *backing =", start)]
        binary = self.compile("surface_cache_key", r'''
@interface Descriptor : NSObject
@property NSUInteger pixelFormat;
@end
@implementation Descriptor
@end
@interface Texture : NSObject { @public NSUInteger _ropt; BOOL _fbo; }
@end
@implementation Texture
@end
// Foundation may discard expired weak entries before count is queried. This
// double keeps tombstones visible to exercise both sides of the sweep gate.
@interface SweepMap : NSObject <NSFastEnumeration> {
@public NSMutableDictionary *entries; NSUInteger removed;
}
- (NSUInteger)count;
- (id)objectForKey:(id)key;
- (void)removeObjectForKey:(id)key;
@end
@implementation SweepMap
- (instancetype)init { if ((self = [super init])) entries = [NSMutableDictionary new]; return self; }
- (NSUInteger)count { return entries.count; }
- (id)objectForKey:(id)key { id v = entries[key]; return v == [NSNull null] ? nil : v; }
- (void)removeObjectForKey:(id)key { [entries removeObjectForKey:key]; ++removed; }
- (NSUInteger)countByEnumeratingWithState:(NSFastEnumerationState *)state
                                objects:(id __unsafe_unretained [])buffer count:(NSUInteger)len {
    return [entries countByEnumeratingWithState:state objects:buffer count:len];
}
@end
static uint32_t IOSurfaceGetID(uint32_t surf) { return surf; }
static NSString *keyFor(NSMapTable *cache, uint32_t surf, NSUInteger plane,
                        size_t w, size_t h, NSUInteger format, NSUInteger ropt, BOOL fbo) {
    Descriptor *d = [Descriptor new]; d.pixelFormat = format;
    Texture *t = [Texture new]; t->_ropt = ropt; t->_fbo = fbo;
''' + code + r'''
    return key;
}
int main(void) { @autoreleasepool {
    NSMapTable *cache = [NSMapTable strongToWeakObjectsMapTable];
    NSString *base = keyFor(cache, 7, 0, 128, 64, 80, 32, NO);
    assert([base isEqual:keyFor(cache, 7, 0, 128, 64, 80, 32, NO)]);
    NSArray *different = @[base,
        keyFor(cache, 8, 0, 128, 64, 80, 32, NO),
        keyFor(cache, 7, 1, 128, 64, 80, 32, NO),
        keyFor(cache, 7, 0, 129, 64, 80, 32, NO),
        keyFor(cache, 7, 0, 128, 65, 80, 32, NO),
        keyFor(cache, 7, 0, 128, 64, 81, 32, NO),
        keyFor(cache, 7, 0, 128, 64, 80, 33, NO),
        keyFor(cache, 7, 0, 128, 64, 80, 32, YES)];
    assert([NSSet setWithArray:different].count == 8);
    assert(!keyFor(cache, 0, 0, 128, 64, 80, 32, NO));
    NSMutableSet *hashes = [NSMutableSet new];
    for (unsigned i = 1; i <= 300; ++i)
        [hashes addObject:@([keyFor(cache, i, 0, 128, 64, 80, 32, NO) hash])];
    assert(hashes.count > 16);
    NSMutableDictionary *live = [NSMutableDictionary new];
    for (unsigned i = 1; i <= 60; ++i) {
        NSString *k = keyFor(cache, i, 0, 128, 64, 80, 32, NO);
        Texture *t = [Texture new]; live[k] = t; [cache setObject:t forKey:k];
    }
    // Insert without invoking the sweep, then release all these weak values.
    @autoreleasepool {
        for (unsigned i = 1000; i < 1300; ++i) {
            NSString *k = keyFor(nil, i, 0, 128, 64, 80, 32, NO);
            Texture *t = [Texture new]; [cache setObject:t forKey:k];
        }
    }
    NSUInteger before = cache.count;
    (void)keyFor(cache, 2000, 0, 128, 64, 80, 32, NO);
    for (NSString *k in live) assert([cache objectForKey:k] == live[k]);
    if (before > 256) for (NSString *k in cache) assert([cache objectForKey:k]);
    SweepMap *sweep = [SweepMap new]; Texture *kept = [Texture new];
    sweep->entries[@"live"] = kept;
    for (unsigned i = 0; i < 255; ++i) sweep->entries[@(i)] = [NSNull null];
    (void)keyFor((NSMapTable *)sweep, 7, 0, 128, 64, 80, 32, NO);
    assert(sweep.count == 256 && sweep->removed == 0);
    sweep->entries[@255] = [NSNull null];
    (void)keyFor((NSMapTable *)sweep, 0, 0, 128, 64, 80, 32, NO);
    assert(sweep.count == 257 && sweep->removed == 0);
    (void)keyFor((NSMapTable *)sweep, 7, 0, 128, 64, 80, 32, NO);
    assert(sweep.count == 1 && sweep->removed == 256 && [sweep objectForKey:@"live"] == kept);
    printf("seven fields, nil surface, %lu distinct hashes, weak count %lu -> %lu, live identities: PASS\n",
           (unsigned long)hashes.count, (unsigned long)before, (unsigned long)cache.count);
    puts("controlled weak-map sweep: 256 no-op, 257 nil-surface no-op, 256 dead removed: PASS");
} return 0; }
''')
        self.run_binary(binary)

    def test_unknown_usage(self):
        text = DEVICE.read_text()
        start = text.index("// MTLTextureUsageUnknown means")
        code = text[start:text.index("int wantStex", start)]
        binary = self.compile("unknown_usage", r'''
#import <Metal/Metal.h>
@interface FakeDescriptor : NSObject <NSCopying>
@property MTLTextureUsage usage;
@end
@implementation FakeDescriptor
- (id)copyWithZone:(NSZone *)zone {
    FakeDescriptor *other = [FakeDescriptor new]; other.usage = self.usage; return other;
}
@end
#define MTLTextureDescriptor FakeDescriptor
static const char *program;
static size_t planes;
static int storage;
static const char *test_program(void) { return program; }
#define getprogname test_program
static size_t test_plane_count(int surf) { return planes; }
#define IOSurfaceGetPlaneCount test_plane_count
int nvmtl_vk_format_is_storage(uint32_t vkf) { return storage; }
static FakeDescriptor *promoteDescriptor(FakeDescriptor *d, int surf, int a8) {
    uint32_t vkf = 37;
''' + code + r'''
    return d;
}
int main(int argc, char **argv) { @autoreleasepool {
    assert(argc == 2); program = argv[1];
    BOOL enabled = strcmp(program, "WindowServer") && !getenv("NVMTL_NO_SURF_UNKNOWN");
    unsigned count = 0;
    for (planes = 0; planes <= 2; ++planes) for (storage = 0; storage <= 1; ++storage)
    for (int a8 = 0; a8 <= 1; ++a8) for (int surf = 0; surf <= 1; ++surf)
    for (int explicitUsage = 0; explicitUsage <= 1; ++explicitUsage) {
        FakeDescriptor *d = [FakeDescriptor new];
        d.usage = explicitUsage ? MTLTextureUsageShaderRead : MTLTextureUsageUnknown;
        MTLTextureUsage old = d.usage;
        FakeDescriptor *out = promoteDescriptor(d, surf, a8);
        BOOL eligible = enabled && surf && !explicitUsage && planes <= 1;
        MTLTextureUsage expected = eligible ?
            MTLTextureUsageShaderRead | MTLTextureUsageRenderTarget | MTLTextureUsagePixelFormatView |
            ((!a8 && storage) ? MTLTextureUsageShaderWrite : 0) : old;
        assert(out.usage == expected); assert(d.usage == old);
        assert((out != d) == eligible); ++count;
    }
    printf("Unknown usage %s (optout=%d): %u cases PASS\n", program,
           getenv("NVMTL_NO_SURF_UNKNOWN") != NULL, count);
} return 0; }
''')
        self.run_binary(binary, "CameraApp")
        self.run_binary(binary, "WindowServer")
        self.run_binary(binary, "CameraApp", optout=True)

    def test_drawable(self):
        device = DEVICE.read_text()
        objects = (ROOT / "src/nmplugin/NVMTLObjects.m").read_text()
        header = (ROOT / "src/nmplugin/NVMTLObjects.h").read_text()
        self.assertEqual(device.count("t->_drawable = nvmtl_desc_drawable(d);"), 2)
        self.assertIn("alias->_drawable = t->_drawable;", device)
        self.assertIn("@public BOOL _drawable;", header)
        code = function(device, "static BOOL nvmtl_desc_drawable(")
        getter = function(objects, "- (BOOL)isDrawable {")
        binary = self.compile("drawable", r'''
@interface FakeDescriptor : NSObject
@property BOOL flag;
- (BOOL)isDrawable;
@end
@implementation FakeDescriptor
- (BOOL)isDrawable { return self.flag; }
@end
#define MTLTextureDescriptor FakeDescriptor
''' + code + r'''
@interface FakeTexture : NSObject { @public BOOL _drawable; FakeTexture *_parent; }
- (BOOL)isDrawable;
@end
@implementation FakeTexture
''' + getter + r'''
@end
int main(void) { @autoreleasepool {
    assert(!nvmtl_desc_drawable(nil)); assert(!nvmtl_desc_drawable((id)[NSObject new]));
    FakeDescriptor *d = [FakeDescriptor new];
    assert(!nvmtl_desc_drawable((id)d)); d.flag = YES; assert(nvmtl_desc_drawable((id)d));
    FakeTexture *root = [FakeTexture new], *view = [FakeTexture new]; view->_parent = root;
    assert(!root.isDrawable && !view.isDrawable);
    root->_drawable = YES; assert(root.isDrawable && view.isDrawable);
    root->_drawable = NO; view->_drawable = YES; assert(view.isDrawable);
    puts("drawable descriptor, missing selector, texture and parent flags: PASS");
} return 0; }
''')
        self.run_binary(binary)

    def test_cache_store(self):
        text = (ROOT / "src/nmplugin/NVMTLLibraryLoad.m").read_text()
        start = text.index("static BOOL nvmtl_cache_store(")
        code = text[start:text.index("static BOOL nvmtl_dir_writable(", start)]
        binary = self.compile("cache_store", r'''
static const char *mode;
static int writes;
static int test_open(const char *p, int f, mode_t m) {
    if (!strcmp(mode, "open")) { errno = EACCES; return -1; }
    return open(p, f, m);
}
static ssize_t test_write(int fd, const void *b, size_t n) {
    ++writes;
    if (!strcmp(mode, "zero")) { if (writes > 3) _exit(90); return 0; }
    if (!strcmp(mode, "write")) { errno = ENOSPC; return -1; }
    if (!strcmp(mode, "eintr") && writes == 1) { errno = EINTR; return -1; }
    return write(fd, b, MIN(n, (size_t)3));
}
static int test_close(int fd) {
    int r = close(fd);
    if (!strcmp(mode, "close")) { errno = EIO; return -1; }
    return r;
}
static int test_rename(const char *from, const char *to) {
    if (!strcmp(mode, "rename")) { errno = EACCES; return -1; }
    return rename(from, to);
}
#define open test_open
#define write test_write
#define close test_close
#define rename test_rename
''' + code + r'''
#undef open
#undef write
#undef close
#undef rename
int main(int argc, char **argv) { @autoreleasepool {
    assert(argc == 2); mode = argv[1];
    char tmp[] = "/tmp/nullarc-cache-test-XXXXXX"; assert(mkdtemp(tmp));
    NSString *dir = @(tmp), *path = [dir stringByAppendingPathComponent:@"entry"];
    NSData *old = [@"old-complete-entry" dataUsingEncoding:NSUTF8StringEncoding];
    assert([old writeToFile:path atomically:NO]);
    NSData *next = [@"new-complete-entry" dataUsingEncoding:NSUTF8StringEncoding];
    if (!strcmp(mode, "empty")) next = [NSData data];
    BOOL expected = !strcmp(mode, "normal") || !strcmp(mode, "eintr") || !strcmp(mode, "empty") || !strcmp(mode, "text");
    BOOL result;
    if (!strcmp(mode, "nil")) result = nvmtl_cache_store(nil, path);
    else if (!strcmp(mode, "nilpath")) result = nvmtl_cache_store(next, nil);
    else if (!strcmp(mode, "long")) result = nvmtl_cache_store(next, [@"/" stringByPaddingToLength:PATH_MAX+10 withString:@"x" startingAtIndex:0]);
    else if (!strcmp(mode, "text")) result = nvmtl_cache_store_text(@"new-complete-entry", path);
    else result = nvmtl_cache_store(next, path);
    assert(result == expected);
    assert([[NSData dataWithContentsOfFile:path] isEqual:expected ? next : old]);
    NSArray *files = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:dir error:NULL];
    assert(files.count == 1 && [files[0] isEqual:@"entry"]);
    assert([[NSFileManager defaultManager] removeItemAtPath:dir error:NULL]);
    printf("cache write %s (%d write calls): PASS\n", mode, writes);
} return 0; }
''')
        for mode in ("normal", "eintr", "empty", "text", "open", "write", "zero",
                     "close", "rename", "nil", "nilpath", "long"):
            with self.subTest(mode=mode):
                self.run_binary(binary, mode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
