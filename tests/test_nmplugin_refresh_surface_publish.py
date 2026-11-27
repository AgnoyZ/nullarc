#!/usr/bin/env python3
"""CPU-only regression tests for the build34 surface-publish refresh candidate.

Verifies SHA-256 baselines, applies tools/build34_refresh_surface_publish.patch
in a temporary directory, and compiles the patched scheduling and host-backed
surface-out logic with CPU doubles under ASan/UBSan. No GPU, Metal device, or
driver loading is involved.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/tests/refresh_surface_publish"
PATCH = ROOT / "tools/build34_refresh_surface_publish.patch"
BASELINES = {
    Path("src/nmplugin/NVMTLEventSync.m"): "6b73c8cbf06d84499398355d3d776a0413340d8d49950265420612e9cbe1a95b",
    Path("src/nmplugin/NVMTLObjects.m"): "38dc8070cddb8368115ad41aec365a3463f59b27323b5b277238e74a5de50b34",
}


def function(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def extract_range(text, start_marker, end_marker):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def apply_candidate():
    with tempfile.TemporaryDirectory() as directory:
        for rel, expected in BASELINES.items():
            raw = (ROOT / rel).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError(f"Refresh surface-publish source drift: {rel}")
            dst = Path(directory) / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(raw)
        subprocess.run(["git", "apply", "--unidiff-zero", str(PATCH)], cwd=directory, check=True)
        return {rel.name: (Path(directory) / rel).read_text() for rel in BASELINES}


HARNESS_PREFIX = r"""
#import <Foundation/Foundation.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef kIOReturnSuccess
#define kIOReturnSuccess 0
#endif
#ifndef kIOReturnError
#define kIOReturnError   (-1)
#endif
#ifndef kIOSurfaceLockAvoidSync
#define kIOSurfaceLockAvoidSync 0x00000002u
#endif

typedef struct FakeSurface {
    uint32_t seed;
    int lockCalls;
    int unlockCalls;
    uint32_t lastLockOpt;
    uint32_t lastUnlockOpt;
    int lockResult;
    int unlockResult;
} FakeSurface;

static const char *gProgramName = "ZenApp";
static const char *fake_getprogname(void) { return gProgramName; }
#define getprogname fake_getprogname

static int gNoSeed = 0;
static int nvmtl_noseed(void) { return gNoSeed; }

static int fake_IOSurfaceLock(FakeSurface *surf, uint32_t opt, uint32_t *seed) {
    surf->lockCalls++;
    surf->lastLockOpt = opt;
    if (surf->lockResult != kIOReturnSuccess) return surf->lockResult;
    if (seed) *seed = surf->seed;
    return kIOReturnSuccess;
}
static int fake_IOSurfaceUnlock(FakeSurface *surf, uint32_t opt, uint32_t *seed) {
    surf->unlockCalls++;
    surf->lastUnlockOpt = opt;
    if (surf->unlockResult != kIOReturnSuccess) return surf->unlockResult;
    if (!(opt & 1u)) surf->seed++;
    if (seed) *seed = surf->seed;
    return kIOReturnSuccess;
}
static uint32_t fake_IOSurfaceGetSeed(FakeSurface *surf) { return surf ? surf->seed : 0; }
#define IOSurfaceLock fake_IOSurfaceLock
#define IOSurfaceUnlock fake_IOSurfaceUnlock
#define IOSurfaceGetSeed fake_IOSurfaceGetSeed

@interface NVMTLTexture : NSObject {
@public
    NVMTLTexture *_parent;
    FakeSurface *_surf;
    BOOL _hostOn;
    BOOL _bufCopy;
    BOOL _surfSynced;
    uint32_t _surfSeed;
}
@end
@implementation NVMTLTexture @end

@interface NVMTLSubmissionPart : NSObject {
@public
    NSSet *surfaces;
}
@end
@implementation NVMTLSubmissionPart @end

@interface NVMTLCommandBuffer : NSObject {
@public
    NVMTLTexture *_present;
    BOOL _scheduleAfterPublish;
    BOOL _wasScheduled;
    int _cbstatus;
    int _scheduledDispatches;
    NSCondition *_completionCondition;
    NSMutableArray *_scheduledHandlers;
}
- (void)nvmtlSealSchedulePolicy:(NVMTLSubmissionPart *)part;
- (void)nvmtlMarkScheduled;
- (void)nvmtlDispatchHandlers:(NSArray *)handlers scheduled:(BOOL)scheduled;
@end

enum { MTLCommandBufferStatusScheduled = 3 };
"""

HARNESS_CASES = r"""
@implementation NVMTLCommandBuffer
- (instancetype)init {
    if ((self = [super init])) {
        _completionCondition = [NSCondition new];
        _scheduledHandlers = [NSMutableArray new];
    }
    return self;
}
- (void)nvmtlDispatchHandlers:(NSArray *)handlers scheduled:(BOOL)scheduled {
    if (scheduled && handlers.count) _scheduledDispatches += (int)handlers.count;
}
- (void)nvmtlSealSchedulePolicy:(NVMTLSubmissionPart *)part {
    __SCHEDULE_SNIPPET__
}
__MARK_SCHEDULED__
@end

static BOOL run_host_surface_out(NVMTLTexture *tex, BOOL dirtied) {
    NVMTLTexture *r = tex->_parent ? tex->_parent : tex;
    __HOST_SURFACE_OUT__
    return NO;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        assert(argc >= 3);
        const char *mode = argv[1];
        gProgramName = argv[2];

        if (!strcmp(mode, "schedule")) {
            assert(argc >= 6);
            const int isDrawable = atoi(argv[3]);
            const int hasSurf = atoi(argv[4]);
            const int expectedDefer = atoi(argv[5]);

            FakeSurface fs = { .seed = 10 };
            NVMTLTexture *tex = [NVMTLTexture new];
            tex->_surf = hasSurf ? &fs : NULL;

            NVMTLSubmissionPart *part = [NVMTLSubmissionPart new];
            part->surfaces = [NSSet setWithObject:tex];

            NVMTLCommandBuffer *cb = [NVMTLCommandBuffer new];
            if (isDrawable) cb->_present = tex;
            [cb->_scheduledHandlers addObject:^(id ignored){ (void)ignored; }];

            [cb nvmtlSealSchedulePolicy:part];
            assert((cb->_scheduleAfterPublish ? 1 : 0) == expectedDefer);

            [cb nvmtlMarkScheduled];
            if (expectedDefer) {
                assert(!cb->_wasScheduled);
                assert(cb->_scheduledDispatches == 0);
                cb->_scheduleAfterPublish = NO;
                [cb nvmtlMarkScheduled];
            }
            assert(cb->_wasScheduled);
            assert(cb->_scheduledDispatches == 1);
            return 0;
        }

        if (!strcmp(mode, "host-seed")) {
            assert(argc >= 4);
            gNoSeed = atoi(argv[3]);
            FakeSurface fs = { .seed = 41, .lockResult = kIOReturnSuccess, .unlockResult = kIOReturnSuccess };
            NVMTLTexture *root = [NVMTLTexture new];
            root->_surf = &fs;
            root->_hostOn = YES;
            root->_surfSeed = 41;
            root->_surfSynced = NO;
            NVMTLTexture *view = [NVMTLTexture new];
            view->_parent = root;

            BOOL ok = run_host_surface_out(view, NO);
            assert(ok);
            assert(root->_surfSynced == YES);
            if (gNoSeed) {
                assert(fs.lockCalls == 0 && fs.unlockCalls == 0);
                assert(IOSurfaceGetSeed(&fs) == 41);
                assert(root->_surfSeed == 41);
            } else {
                assert(fs.lockCalls == 1 && fs.unlockCalls == 1);
                assert(fs.lastLockOpt == kIOSurfaceLockAvoidSync);
                assert(fs.lastUnlockOpt == kIOSurfaceLockAvoidSync);
                assert(IOSurfaceGetSeed(&fs) == 42);
                assert(root->_surfSeed == 42);
            }
            return 0;
        }

        if (!strcmp(mode, "host-seed-lock-fail")) {
            FakeSurface fs = { .seed = 7, .lockResult = kIOReturnError, .unlockResult = kIOReturnSuccess };
            NVMTLTexture *tex = [NVMTLTexture new];
            tex->_surf = &fs;
            tex->_hostOn = YES;
            tex->_surfSeed = 7;
            BOOL ok = run_host_surface_out(tex, NO);
            assert(ok);
            assert(fs.lockCalls == 1 && fs.unlockCalls == 0);
            assert(tex->_surfSeed == 7);
            assert(tex->_surfSynced == YES);
            return 0;
        }

        return 2;
    }
}
"""


class RefreshSurfacePublishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        patched = apply_candidate()
        events = patched["NVMTLEventSync.m"]
        objects = patched["NVMTLObjects.m"]

        commit_wait_fn = function(events, "static BOOL nvmtl_surface_commit_wait_on(")
        mark_sched_fn = function(events, "- (void)nvmtlMarkScheduled {")
        schedule_snippet = extract_range(
            events,
            "// Another process may read an IOSurface once its writer is scheduled",
            "    part->scratch = [_scratch copy];",
        )
        host_surface_out = extract_range(
            objects,
            "    if (!r->_surf) return YES;",
            "    @synchronized (nvmtl_surface_sync(r)) {",
        )

        source = (
            HARNESS_PREFIX
            + "\n"
            + commit_wait_fn
            + "\n"
            + HARNESS_CASES
                .replace("__SCHEDULE_SNIPPET__", schedule_snippet)
                .replace("__MARK_SCHEDULED__", mark_sched_fn)
                .replace("__HOST_SURFACE_OUT__", host_surface_out)
        )
        BUILD.mkdir(parents=True, exist_ok=True)
        src_path = BUILD / "candidate.m"
        src_path.write_text(source)
        cls.binary = BUILD / "test"
        subprocess.run([
            "xcrun", "clang", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-parameter", "-fobjc-arc", "-fblocks",
            "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
            "-fno-omit-frame-pointer", str(src_path), "-framework", "Foundation",
            "-o", str(cls.binary),
        ], check=True, timeout=60)

    def run_bin(self, args, env_overrides=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith("NVMTL_")}
        env["ASAN_OPTIONS"] = "detect_leaks=0"
        if env_overrides:
            env.update(env_overrides)
        subprocess.run([str(self.binary)] + args, env=env, check=True, timeout=10)

    def test_schedule_after_publish_policy(self):
        cases = [
            # (commit_wait, explicit_sched, prog, is_drawable, has_surf, expected_defer)
            (None, None, "ZenApp", 0, 1, 0),
            ("1", None, "ZenApp", 0, 1, 1),
            ("1", None, "ZenApp", 1, 1, 1),
            ("1", None, "ZenApp", 0, 0, 0),
            ("1", "0", "ZenApp", 0, 1, 0),
            ("1", "0", "ZenApp", 1, 1, 0),
            (None, "1", "ZenApp", 0, 1, 1),
            (None, "1", "ZenApp", 1, 1, 0),
            ("1", None, "WindowServer", 0, 1, 0),
            ("1", None, "WindowServer", 1, 1, 0),
            ("1", "1", "WindowServer", 0, 1, 1),
        ]
        for commit_wait, explicit_sched, prog, is_drawable, has_surf, expected in cases:
            env = {}
            if commit_wait is not None:
                env["NVMTL_SURFACE_COMMIT_WAIT"] = commit_wait
            if explicit_sched is not None:
                env["NVMTL_SCHEDULE_AFTER_SURFACE_WRITES"] = explicit_sched
            with self.subTest(cw=commit_wait, sched=explicit_sched, prog=prog,
                              drawable=is_drawable, surf=has_surf):
                self.run_bin(
                    ["schedule", prog, str(is_drawable), str(has_surf), str(expected)],
                    env_overrides=env,
                )

    def test_host_surface_out_advances_seed_with_avoid_sync(self):
        self.run_bin(["host-seed", "ZenApp", "0"])

    def test_host_surface_out_respects_noseed(self):
        self.run_bin(["host-seed", "ZenApp", "1"])

    def test_host_surface_out_lock_failure_stays_nonfatal(self):
        self.run_bin(["host-seed-lock-fail", "ZenApp"])


if __name__ == "__main__":
    unittest.main()
