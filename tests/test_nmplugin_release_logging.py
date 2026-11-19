#!/usr/bin/env python3
"""CPU-only replay of the actual release logger; never emits a system log.

The publication deadline's format, logger and rate limiter are extracted from
production. Only syslog is replaced with a private in-process collector.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class ReleaseLogging(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        device = (ROOT / "src/nmplugin/NVMTLDevice.m").read_text()
        events = (ROOT / "src/nmplugin/NVMTLEventSync.m").read_text()
        timeout_format = re.search(
            r'nvlog\(("surface commit wait: deadline expired[^"\n]*")', events
        )
        if timeout_format is None:
            raise RuntimeError("production publication-timeout message was not found")
        rate_limiter = device[device.index("#define NVLOG_SITES"):device.index("const char *nvmtl_log_path(")]
        logger = function(device, "void nvlog(")
        source = r'''
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <syslog.h>
#include "nvmtl_log_failure.h"
#define NVMTL_RELEASE 1
static unsigned emitted;
static int severity;
static char last[1024];
static void test_syslog(int priority, const char *format, ...) {
    va_list args; va_start(args, format);
    vsnprintf(last, sizeof last, format, args);
    va_end(args);
    severity = priority; emitted++;
}
#define syslog test_syslog
'''
        source += rate_limiter + "\n" + logger + "\n"
        source += "static void publication_timeout(void) { nvlog(" + timeout_format.group(1)
        source += ", 250123ull, 250u, 1ul); }\n"
        source += r'''
static int check(int good, const char *message) {
    if (good) return 0;
    fprintf(stderr, "%s\n", message);
    return 1;
}
int main(int argc, char **argv) {
    if (argc != 2) return 64;
    if (!strcmp(argv[1], "timeout")) {
        publication_timeout();
        if (check(emitted == 1, "release logger dropped actual publication-timeout message")) return 1;
        if (check(severity == LOG_ERR, "publication timeout lost its error severity")) return 1;
        if (check(strstr(last, "NullMoth: surface commit wait: deadline expired after 250123 us (budget 250 ms, #1)") != NULL,
                  "production formatting or release syslog prefix was not preserved")) return 1;
        return check(strstr(last, "publication unconfirmed, retaining pending work") != NULL,
                     "timeout log lost pending-publication qualification");
    }
    if (!strcmp(argv[1], "failures")) {
        const char *messages[] = {
            "vk: vkCreateDevice -> -8", "render FAILED", "device REFUSED",
            "GPU fault at address", "GPU FAULT at address", "binding missing",
            "cannot reflect", "unsupported texture", "import refused",
            "draw is skipped", "draw skipped", "draws are being skipped", "no device"
        };
        for (unsigned i = 0; i < sizeof messages / sizeof messages[0]; ++i) {
            unsigned before = emitted;
            nvlog(messages[i]);
            if (check(emitted == before + 1 && severity == LOG_ERR, messages[i])) return 1;
        }
        return 0;
    }
    if (!strcmp(argv[1], "quiet")) {
        const char *messages[] = {
            "surface commit wait: ready after 250 us (budget 250 ms)",
            "surface commit wait: deadline expires soon",
            "unrelated task: deadline expired",
            "library cache HIT", "default sampler", "faultless frame", "GPU faults counter: 0", ""
        };
        if (check(!nvmtl_log_failure(NULL), "null log was classified as a failure")) return 1;
        for (unsigned i = 0; i < sizeof messages / sizeof messages[0]; ++i) {
            nvlog(messages[i]);
            if (check(emitted == 0, messages[i])) return 1;
        }
        return 0;
    }
    if (!strcmp(argv[1], "rate-limit")) {
        for (unsigned i = 0; i < NVLOG_VERBATIM; ++i) publication_timeout();
        if (check(emitted == NVLOG_VERBATIM, "initial timeout messages were not retained")) return 1;
        for (unsigned i = NVLOG_VERBATIM; i < NVLOG_EVERY - 1; ++i) publication_timeout();
        if (check(emitted == NVLOG_VERBATIM, "normal per-site suppression was changed")) return 1;
        publication_timeout();
        if (check(emitted == NVLOG_VERBATIM + 1, "periodic repeated-message report was lost")) return 1;
        return check(strstr(last, "[logged 4096 times now]") != NULL, "repeat count was lost");
    }
    return 64;
}
'''
        temp = tempfile.TemporaryDirectory(prefix="nullarc-release-log-")
        cls.addClassCleanup(temp.cleanup)
        path = Path(temp.name) / "production.c"
        cls.binary = Path(temp.name) / "test"
        path.write_text(source)
        run = subprocess.run([
            "xcrun", "clang", "-std=c11", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
            "-pthread", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
            "-fno-omit-frame-pointer", "-I" + str(ROOT / "src/nmplugin"), str(path),
            "-o", str(cls.binary),
        ], capture_output=True, text=True, timeout=60)
        if run.returncode:
            raise RuntimeError(run.stderr)

    def run_case(self, name):
        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0")
        run = subprocess.run([str(self.binary), name], capture_output=True,
                             text=True, timeout=10, env=env)
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_actual_publication_timeout_reaches_release_syslog(self):
        self.run_case("timeout")

    def test_existing_failure_classes_remain_visible(self):
        self.run_case("failures")

    def test_success_and_unrelated_deadlines_remain_quiet(self):
        self.run_case("quiet")

    def test_existing_rate_limit_remains_in_force(self):
        self.run_case("rate-limit")


if __name__ == "__main__":
    unittest.main(verbosity=2)
