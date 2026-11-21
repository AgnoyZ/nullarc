#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Make the source-only R3 stage a complete native translation unit.

This does not bind a reader, negotiate exact mode or admit a kernel candidate.
"""
from build34_exact_service_timer import stage as previous_stage, stage_header
from build34_exact_submit import once


def stage(source):
    return once(previous_stage(source), 'class PhxBringup : public IOService {',
                'class IOAccelPhxNativeClient;\n\nclass PhxBringup : public IOService {')
