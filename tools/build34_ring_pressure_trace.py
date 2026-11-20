#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Capture only the authorized native probe's exact queue-backpressure sleep."""
import json
import os
import subprocess
import time

# In the admitted x86_64 image, gpuSubmit+0x1f1 loads 1 and calls IOSleep.
# The code bytes at the return PC distinguish it from doWaitSeq and vmidFree.
CALL_RETURN_OFFSET = 0x27BF
RETURN_BYTES = (0x45, 0x31, 0xff, 0x49, 0x89, 0xdd, 0xe9, 0x76, 0xfe, 0xff, 0xff)
CALL_BYTES = (0xbf, 1, 0, 0, 0, 0xe8)
TRACE_SECONDS = 12
ARM_SECONDS = 20
PROBE_RETIRE_SECONDS = 5
TRACE_RETIRE_SECONDS = TRACE_SECONDS + 3


def record(root, name, value):
    with (root / name).open('x') as handle:
        os.fchmod(handle.fileno(), 0o600)
        json.dump(value, handle)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def trace_program(pid):
    assert type(pid) is int and pid > 1
    before = [(-10 + i, b) for i, b in enumerate(CALL_BYTES)]
    after = list(enumerate(RETURN_BYTES))
    # caller is the actual runtime address. Compare only the page offset first:
    # kmutil's address for the OpenCore image is not a usable live text address.
    exact = ' && '.join(f'*(uint8_t *)(caller {"-" if i < 0 else "+"} {abs(i)}) == 0x{b:02x}'
                        for i, b in before + after)
    return f'''#pragma D option quiet
#pragma D option bufsize=1m
#pragma D option dynvarsize=256k
#pragma D option switchrate=20hz

dtrace:::BEGIN {{ printf("READY\\n"); }}
fbt:mach_kernel:IOSleep:entry
/pid == {pid} && arg0 == 1 && (caller & 0xfff) == 0x{CALL_RETURN_OFFSET & 0xfff:x} && {exact}/
{{ self->armed = timestamp; self->wall = walltimestamp; self->pc = caller; self->blocked = (uint64_t)0; self->depth = (uint64_t)0; }}
fbt:mach_kernel:thread_block_reason:entry
/pid == {pid} && self->blocked/
{{ self->depth = self->depth + 1; }}
fbt:mach_kernel:thread_block_reason:entry
/pid == {pid} && self->armed && !self->blocked && caller == self->pc/
{{ self->blocked = self->armed; self->armed = 0; self->depth = 1; }}
fbt:mach_kernel:thread_block_reason:return
/pid == {pid} && self->blocked && self->depth == 1/
{{
    printf("WAIT_BLOCK %d %llu %llu %llu %llu 2\\n", tid, (uint64_t)self->wall, (uint64_t)walltimestamp, (uint64_t)self->blocked, (uint64_t)timestamp);
    self->blocked = 0; self->wall = 0; self->depth = 0;
}}
fbt:mach_kernel:thread_block_reason:return
/pid == {pid} && self->blocked && self->depth > 1/
{{ self->depth = self->depth - 1; }}
dtrace:::ERROR {{ printf("ERROR\\n"); }}
profile:::tick-{TRACE_SECONDS}sec {{ exit(0); }}
dtrace:::END {{ printf("END\\n"); }}
'''


def capture(root):
    probe = root / 'ring-pressure-probe'
    with (root / 'pressure.stdout').open('xb') as out, (root / 'pressure.stderr').open('xb') as err:
        p = subprocess.Popen(['/usr/bin/nice', '-n', '10', str(probe), '--run'], stdin=subprocess.PIPE,
                             stdout=out, stderr=err, start_new_session=True)
    trace_source = root / 'pressure-scope-private.d'
    with trace_source.open('x') as f:
        f.write(trace_program(p.pid))
    trace_out, trace_err = root / 'pressure-trace.stdout', root / 'pressure-trace.stderr'
    q = None
    released = False
    ready = False
    with trace_out.open('xb') as out, trace_err.open('xb') as err:
        try:
            q = subprocess.Popen(['/usr/sbin/dtrace', '-s', str(trace_source)], stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=err, start_new_session=True)
            record(root, 'pressure-processes-private.json', {'probe_pid': p.pid, 'trace_pid': q.pid})
            start = time.monotonic()
            while trace_out.read_bytes().splitlines()[:1] != [b'READY']:
                if q.poll() is not None or time.monotonic() - start >= ARM_SECONDS or trace_err.stat().st_size:
                    raise RuntimeError('trace did not arm; no GPU requests made')
                time.sleep(0.05)
            if q.poll() is not None or trace_err.stat().st_size:
                raise RuntimeError('trace retired or diagnosed before release; no GPU requests made')
            ready = True
            record(root, 'pressure-trace-ready-private.json', {'elapsed_seconds': time.monotonic() - start})
            record(root, 'pressure-G-release.intent', {'probe_pid': p.pid, 'automatic_retry': False})
            # Once dispatch may have happened, never treat it as a pre-GPU
            # refusal, even if write/flush raises or tracing exits unexpectedly.
            released = True
            p.stdin.write(b'G'); p.stdin.flush()
            record(root, 'pressure-G-released-private.json', {'probe_pid': p.pid})
            p.stdin.close()
            qcode = q.wait(timeout=TRACE_RETIRE_SECONDS)
            try:
                code = p.wait(timeout=PROBE_RETIRE_SECONDS)
            except subprocess.TimeoutExpired:
                (root / 'pressure-probe-held-private.txt').write_text(f'{p.pid}\n')
                raise RuntimeError('pressure probe did not retire; keep GPU ownership') from None
            return code, qcode
        finally:
            if not released:
                p.stdin.close()  # EOF means no device is opened.
                p.wait(timeout=3)
            if q is not None and q.poll() is None:
                q.terminate()
                try:
                    q.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    q.kill()
                    q.wait(timeout=2)
            if released and p.poll() is None and not (root / 'pressure-probe-held-private.txt').exists():
                (root / 'pressure-probe-held-private.txt').write_text(f'{p.pid}\n')
            record(root, 'pressure-trace-lifecycle-private.json', {
                'trace_ready': ready, 'G_dispatch_may_have_occurred': released,
                'probe_exit': p.poll(), 'trace_exit': q.poll() if q is not None else None,
                'probe_terminated_by_controller': False})
