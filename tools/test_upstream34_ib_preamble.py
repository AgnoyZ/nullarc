#!/usr/bin/env python3
"""Run the actual original34 preamble probe with fake IOKit; no GPU execution."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess

from upstream34_layout import mec_range

ROOT = Path(__file__).resolve().parents[1]

PASS = 'PASS: native GPUVM shader probe; two guarded dispatches, not Metal or display acceptance'
CHECK = 'CHECK: target identity and ABI readiness only; no GPU work submitted'


def cases():
    yield from ('ok', 'number-ok', 'create-mappable', 'va-exact', 'check-ok', 'arg-missing', 'arg-mode',
        'arg-option', 'arg-many', 'host-status', 'host-linux', 'host-arm', 'host-sonoma', 'host-prefix',
        'matching-null', 'enumerate-status', 'iterator-null', 'no-service', 'parent-status', 'non-pci',
        'ambiguous', 'mixed-services', 'release-parent', 'release-iterator', 'release-service',
        'release-open-service', 'open-status', 'open-null', 'hello-abi', 'hello-limit', 'hello-vmid',
        'info-abi', 'info-minor', 'info-build', 'info-vmid', 'info-gc', 'info-limit', 'info-hung',
        'info-not-native', 'info-not-ready', 'va-unaligned', 'va-reversed', 'va-short', 'va-hole',
        'va-noncanonical', 'va-null', 'va-wrap', 'va-low-wide', 'ctx-alloc-zero', 'ctx-alloc-wide',
        'ctx-alloc-flags', 'ctx-alloc-id', 'ctx-alloc-priority', 'create-zero', 'create-wide',
        'create-limit', 'create-size', 'create-domain', 'create-unzeroed', 'create-bits', 'cpu-map-zero',
        'cpu-map-unaligned', 'cpu-map-wrap', 'cpu-map-short', 'cpu-map-long', 'cpu-map-status',
        'gpu-map-status', 'cpu-unmap-status', 'gpu-unmap-status', 'free-status', 'close-status',
        'ctx-free-nonzero', 'ctx-free-flags', 'ctx-free-id', 'ctx-free-priority', 'submit-2-repeat')
    for field in ('vendor', 'device'):
        for suffix in ('missing', 'wrong', 'negative', 'wide', 'number-status', 'type', 'short', 'long', 'null'):
            yield f'{field}-{suffix}'
    for operation in ('hello', 'info', 'ctx-alloc', 'create', 'ctx-free', 'submit-1', 'submit-2', 'wait-1', 'wait-2'):
        for suffix in ('status', 'short', 'long'):
            yield f'{operation}-{suffix}'
    for stage in (1, 2):
        for suffix in ('zero', 'last'):
            yield f'submit-{stage}-{suffix}'
        for suffix in ('timeout', 'retired', 'last', 'emitted', 'missing'):
            yield f'wait-{stage}-{suffix}'
        for prefix, count in (('code', 79), ('ib', 80), ('output', 256)):
            for index in range(count): yield f'{prefix}-{stage}-{index}'
        for offset in (316, 4095, 4416, 8191, 8192, 8207, 9232, 12287, 12288, 16383):
            yield f'byte-{stage}-{offset}'


BASE_CASES = tuple(cases())
CASE_SET = frozenset(BASE_CASES)


def baseline_expected(fault):
    if fault not in CASE_SET: raise ValueError('Unknown native probe test case')
    e = []
    if fault.startswith('arg-'): return 64, e
    e.append('host')
    if fault.startswith('host-'): return 4, e
    e.append('matching')
    if fault == 'matching-null': return 4, e
    e.append('enumerate')
    if fault in ('enumerate-status', 'iterator-null'): return 74, e
    if fault == 'no-service': return 4, e + ['release-iterator']
    if fault == 'mixed-services': e += ['parent', 'release-parent', 'release-service']
    e.append('parent')
    if fault == 'parent-status': return 4, e + ['release-service', 'release-iterator']
    if fault == 'non-pci': return 4, e + ['release-parent', 'release-service', 'release-iterator']
    e.append('vendor')
    if fault.startswith('vendor-'):
        if fault == 'vendor-wrong': e.append('device')
        return 4, e + ['release-parent', 'release-service', 'release-iterator']
    e.append('device')
    if fault.startswith('device-'): return 4, e + ['release-parent', 'release-service', 'release-iterator']
    e.append('release-parent')
    if fault == 'ambiguous':
        return 4, e + ['parent', 'vendor', 'device', 'release-parent', 'release-service', 'release-iterator', 'release-service']
    e.append('release-iterator')
    if fault in ('release-parent', 'release-iterator'): return 74, e + ['release-service']
    e += ['open', 'release-service']
    if fault in ('open-status', 'open-null'): return 74, e
    if fault in ('release-service', 'release-open-service'): return 74, e + ['close']
    mapped = False

    def stop(code): return code, e + (['cpu-unmap'] if mapped else []) + ['close']

    def transport(name): return fault in (name + '-status', name + '-short', name + '-long')

    e.append('hello')
    if transport('hello'): return stop(74)
    if fault.startswith('hello-'): return stop(75)
    e.append('info')
    if transport('info'): return stop(74)
    if fault.startswith('info-'): return stop(75)
    if fault == 'check-ok': return stop(0)
    if fault.startswith('va-') and fault != 'va-exact': return stop(75)
    e.append('ctx-alloc')
    if transport('ctx-alloc'): return stop(74)
    if fault.startswith('ctx-alloc-'): return stop(75)
    e.append('create')
    if transport('create'): return stop(74)
    if fault.startswith('create-') and fault != 'create-mappable': return stop(75)
    e.append('cpu-map')
    if fault == 'cpu-map-status': return stop(74)
    mapped = True
    if fault.startswith('cpu-map-'): return stop(75)
    e.append('gpu-map')
    if fault == 'gpu-map-status': return stop(74)
    for stage in (1, 2):
        submit, wait = f'submit-{stage}', f'wait-{stage}'
        e.append(submit)
        if transport(submit): return stop(74)
        if fault.startswith(submit + '-'): return stop(75)
        e.append(wait)
        if transport(wait): return stop(74)
        if fault.startswith(wait + '-') or any(fault.startswith(f'{prefix}-{stage}-') for prefix in ('code', 'ib', 'output', 'byte')):
            return stop(75)
    e.append('cpu-unmap'); mapped = False
    if fault == 'cpu-unmap-status': return stop(74)
    for name in ('gpu-unmap', 'free', 'ctx-free'):
        e.append(name)
        if transport(name): return stop(74)
        if fault.startswith(name + '-'): return stop(75)
    return stop(74 if fault == 'close-status' else 0)


EXTRA_CASES = (
    'legacy-run', 'legacy-fresh', 'legacy-reuse', 'legacy-publish',
    'info-build41', 'info-build42', 'stale-output-2', 'poison-output-2', 'mixed-output-2',
    'late-output-current', 'late-output-mixed', 'late-sleep-error', 'late-clock-backwards',
) + tuple(f'wait-{stage}-pending-{kind}' for stage in (1, 2) for kind in ('short', 'cap'))
EXTRA_CASES += tuple(f'slot-{word}' for word in range(80))
EXTRA_CASES += tuple(f'preamble-{stage}-{byte}' for stage in (1, 2) for byte in range(32))
CASES = BASE_CASES + EXTRA_CASES
POLICIES = ('single', 'control', 'nop-tail', 'memsync', 'single-observe-late')
TARGET_POLICIES = ('target-control', 'target-switch')
ALL_POLICIES = POLICIES + TARGET_POLICIES
TARGET_MODELS = ('model-old-command', 'model-new-address-old-pattern', 'model-no-write',
                 'model-old-address-current-pattern', 'model-both-current')
TARGET_CASES = TARGET_MODELS + tuple(f'target-{r}-{s}-{i}' for r in ('a','b')
                                    for s in (1,2) for i in range(1024))
TARGET_CASES += tuple(f'byte-{s}-{i}' for s in (1,2)
                     for i in (0x240f,0x2410,0x280f,0x2810,0x2c0f,0x2c10)
                     if f'byte-{s}-{i}' not in CASES)
EXEC_EQUIVALENCE_CASES = ('ok', 'arg-mode', 'info-build41', 'stale-output-2',
                          'poison-output-2', 'mixed-output-2', 'late-output-current',
                          'late-output-mixed', 'late-sleep-error', 'late-clock-backwards', 'submit-2-status',
                          'byte-2-16383', 'wait-2-pending-cap', 'check-ok')


def policy_cases(policy):
    if policy not in ALL_POLICIES:
        raise ValueError('Unknown preamble policy')
    return CASES + TARGET_CASES if policy in TARGET_POLICIES else CASES


def marker(policy):
    if policy not in ALL_POLICIES:
        raise ValueError('Unknown preamble policy')
    return f'DIAGNOSTIC-PASS: original34 preamble={policy}; two guarded dispatches; no driver or display acceptance'


def expected(fault, policy='control'):
    if fault not in policy_cases(policy):
        raise ValueError('Unknown preamble case')
    if fault.startswith('legacy-'):
        return 64, []
    base = fault
    if fault in TARGET_MODELS:
        base = 'ok' if policy == 'target-control' and fault == 'model-old-address-current-pattern' else 'output-2-0'
    elif fault in TARGET_CASES:
        base = f'output-{fault.split("-")[1 if fault.startswith("byte-") else 2]}-0'
    elif fault in ('info-build41', 'info-build42'):
        base = 'info-build'
    elif fault.startswith(('slot-', 'late-')) or fault in ('stale-output-2', 'poison-output-2', 'mixed-output-2'):
        base = 'output-2-0'
    elif fault.startswith('preamble-'):
        base = f'ib-{fault.split("-")[1]}-0'
    elif fault in EXTRA_CASES:
        base = 'ok'
    code, events = baseline_expected(base)
    events = list(events)
    for stage in (1, 2):
        count = 3 if fault in (f'wait-{stage}-timeout', f'wait-{stage}-pending-cap') else (
            2 if fault == f'wait-{stage}-pending-short' else 1)
        name = f'wait-{stage}'
        if name in events:
            index = events.index(name)
            events[index:index + 1] = [name] * count
    if code and 'hello' in events and 'gpu-unmap' not in events and fault != 'cpu-unmap-status':
        assert events[-1] == 'close'
        events.pop()
        if events[-1] == 'cpu-unmap':
            events.pop()
        events.append('hold')
    if policy == 'single-observe-late' and expected_mismatch_summary(fault) is not None:
        assert events[-1] == 'hold'
        events.insert(-1, 'late-observation')
    return code, events


def expected_mismatch_summary(fault):
    """Independent oracle for the fixture's exact injected bytes, not GPU behavior."""
    if fault.startswith('late-'):
        fault = 'stale-output-2'
    if fault in ('stale-output-2', 'poison-output-2', 'mixed-output-2'):
        stage, offset = 1, 0x2010
    elif fault in ('wait-1-missing', 'wait-2-missing'):
        stage, offset = int(fault.split('-')[1]) - 1, 0x2010
    elif re.fullmatch(r'(?:code|ib|output|byte|preamble)-[12]-\d+', fault):
        kind, stage, index = fault.split('-'); stage = int(stage) - 1; index = int(index)
        offset = {'code':0, 'ib':4096, 'output':0x2010, 'byte':0, 'preamble':0x1400}[kind]
        offset += index * (4 if kind in ('code', 'ib', 'output') else 1)
    elif fault.startswith('slot-'):
        stage, offset = 1, 0x1200 + int(fault[5:]) * 4
    else:
        return None
    row = {'classification_valid':True, 'pass':stage, 'arena_bytes':16384,
           'first_snapshot_mismatch':offset, 'mismatch_bytes':1,
           'shader_page_mismatch_bytes':int(offset < 4096),
           'command_page_mismatch_bytes':int(4096 <= offset < 8192),
           'output_mismatch_bytes':int(0x2010 <= offset < 0x2410),
           'guard_mismatch_bytes':int(8192 <= offset < 0x2010 or offset >= 0x2410),
           'output_current_words':256, 'output_previous_words':0,
           'output_poison_words':0, 'output_other_words':0,
           'original_mismatch_reobserved':True, 'changed_during_observation_bytes':0}
    if fault in ('stale-output-2', 'poison-output-2', 'mixed-output-2', 'wait-1-missing', 'wait-2-missing'):
        counts = {'stale-output-2':(256,0,256,0,0), 'poison-output-2':(1024,0,0,256,0),
                  'mixed-output-2':(576,64,64,64,64),
                  'wait-1-missing':(1024,0,0,256,0), 'wait-2-missing':(1024,0,0,256,0)}[fault]
        row.update(zip(('mismatch_bytes','output_current_words','output_previous_words',
                        'output_poison_words','output_other_words'),counts))
        row['output_mismatch_bytes'] = row['mismatch_bytes']
    elif 0x2010 <= offset < 0x2410:
        row['output_current_words'] = 255
        # The fixture XORs one byte. Only three pass-1 lane/byte pairs
        # equal their previous value (the second lane changes df -> e0).
        lane, byte = ((offset - 0x2010) // 4) % 4, (offset - 0x2010) % 4
        previous = int(stage == 1 and (lane,byte) in ((0,0),(2,2),(3,0)))
        row['output_previous_words'], row['output_other_words'] = previous, 1 - previous
    return row


def expected_late_summary(fault):
    row = expected_mismatch_summary(fault)
    if row is not None and fault in ('late-output-current', 'late-output-mixed'):
        count = 256 if fault == 'late-output-current' else 128
        row.update(first_snapshot_mismatch=16384 if count == 256 else 0x2010 + count * 4,
                   mismatch_bytes=256-count, output_mismatch_bytes=256-count,
                   output_current_words=count, output_previous_words=256-count,
                   original_mismatch_reobserved=False)
    return row


def expected_late_timing(fault):
    return {'requested_delay_us':100000, 'sleep_status':-1 if fault == 'late-sleep-error' else 0,
            'clock_valid':fault != 'late-clock-backwards',
            'elapsed_ns':0 if fault == 'late-clock-backwards' else 100004000}


def expected_target_summaries(fault, policy):
    """Independent byte oracle: output values and injected corruption, no ISA."""
    if policy not in TARGET_POLICIES:
        return []
    _, events = expected(fault, policy)
    rows = []
    for stage in (1,2):
        if f'wait-{stage}' not in events:
            break
        if fault.startswith(f'wait-{stage}-') and fault.split('-',2)[2] not in ('missing','pending-short','pending-cap'):
            break
        pass_index = stage - 1
        selected = 0x2810 if policy == 'target-switch' and pass_index else 0x2010
        previous = (0x7800c0de,0x13579bdf,0x2468ace0,0xc001d00d)
        current = (previous[0]^pass_index, previous[1]+pass_index,
                   previous[2]^(pass_index<<16), previous[3]-pass_index)
        want = bytearray(16384)

        def put(arena, offset, values):
            for i in range(256):
                arena[offset+i*4:offset+i*4+4] = values[i%len(values)].to_bytes(4,'little')

        poison = tuple(v ^ 0xffffffff for v in current)
        for offset in (0x2010,0x2810):
            put(want,offset,poison)
        actual = bytearray(want)
        put(want,selected,current)
        if fault != f'wait-{stage}-missing':
            put(actual,selected,current)
        if pass_index and (fault == 'stale-output-2' or fault.startswith('late-')):
            put(actual,selected,previous)
        if pass_index and fault == 'poison-output-2':
            put(actual,selected,poison)
        if pass_index and fault == 'mixed-output-2':
            for i in range(256):
                value = (previous if i < 64 else poison if i < 128 else current)[i&3]
                if i >= 192: value ^= 0x01010101
                actual[selected+i*4:selected+i*4+4] = value.to_bytes(4,'little')
        if pass_index and fault in TARGET_MODELS:
            for offset in (0x2010,0x2810): put(actual,offset,poison)
            if fault == 'model-old-command': put(actual,0x2010,previous)
            elif fault == 'model-new-address-old-pattern': put(actual,selected,previous)
            elif fault == 'model-old-address-current-pattern': put(actual,0x2010,current)
            elif fault == 'model-both-current':
                for offset in (0x2010,0x2810): put(actual,offset,current)
        mutation = None
        if re.fullmatch(r'(?:code|ib|output|byte|preamble)-[12]-\d+',fault):
            kind, s, index = fault.split('-'); index = int(index)
            if int(s) == stage:
                mutation = {'code':0,'ib':4096,'output':selected,'byte':0,'preamble':0x1400}[kind]
                mutation += index * (4 if kind in ('code','ib','output') else 1)
        elif fault.startswith('slot-') and pass_index:
            mutation = 0x1200 + int(fault[5:])*4
        elif re.fullmatch(r'target-[ab]-[12]-\d+',fault):
            _,region,s,index = fault.split('-')
            if int(s) == stage: mutation = (0x2010 if region == 'a' else 0x2810)+int(index)
        if mutation is not None: actual[mutation] ^= 1
        mismatch = [i for i,(a,b) in enumerate(zip(actual,want)) if a != b]
        first = mismatch[0] if mismatch else 16384
        row = {'classification_valid':True,'pass':pass_index,'policy':policy,'arena_bytes':16384,
               'selected_region':'B' if selected == 0x2810 else 'A','first_scan_mismatch':first,
               'first_snapshot_mismatch':first,'mismatch_bytes':len(mismatch),
               'shader_page_mismatch_bytes':sum(i < 4096 for i in mismatch),
               'command_page_mismatch_bytes':sum(4096 <= i < 8192 for i in mismatch),
               'a_mismatch_bytes':sum(0x2010 <= i < 0x2410 for i in mismatch),
               'b_mismatch_bytes':sum(0x2810 <= i < 0x2c10 for i in mismatch),
               'guard_mismatch_bytes':sum(i >= 8192 and not (0x2010 <= i < 0x2410 or 0x2810 <= i < 0x2c10) for i in mismatch)}
        for region,offset in (('a',0x2010),('b',0x2810)):
            counts = dict.fromkeys(('expected','current','previous','poison','other'),0)
            for i in range(256):
                a = int.from_bytes(actual[offset+i*4:offset+i*4+4],'little')
                b = int.from_bytes(want[offset+i*4:offset+i*4+4],'little')
                counts['expected'] += a == b
                kind = 'current' if a == current[i&3] else 'previous' if pass_index and a == previous[i&3] else 'poison' if a == poison[i&3] else 'other'
                counts[kind] += 1
            row.update({f'{region}_{k}_words':v for k,v in counts.items()})
        row.update(changed_during_observation_bytes=0,validation_passed=not mismatch)
        rows.append(row)
        if mismatch: break
    return rows


def check_result(result, fault, policy):
    code, events = expected(fault, policy)
    prefix = 'fake-native-shader-summary '
    if result.returncode != code or result.stderr.count(prefix) != 1:
        raise RuntimeError(f'Preamble {policy}/{fault}: exit {result.returncode}, wanted {code}: {result.stderr}')
    if json.loads(result.stderr.split(prefix)[1].strip()) != {'events': events}:
        raise RuntimeError(f'Preamble {policy}/{fault}: unexpected continuation')
    if any(word in result.stderr for word in ('AddressSanitizer', 'UndefinedBehaviorSanitizer', 'runtime error:')):
        raise RuntimeError('Sanitizer finding')
    lines = result.stdout.splitlines()
    if code:
        if 'DIAGNOSTIC-PASS:' in result.stdout or CHECK in result.stdout:
            raise RuntimeError('Failed case printed success')
    elif fault == 'check-ok':
        if lines != [CHECK]:
            raise RuntimeError('Readiness check changed scope')
    elif not lines or lines[-1] != marker(policy) or result.stdout.count('DIAGNOSTIC-PASS:') != 1:
        raise RuntimeError('Missing or false diagnostic marker')
    if ('HOLD:' in result.stderr) != ('hold' in events):
        raise RuntimeError('Missing or spurious HOLD')
    if 'hold' in events and any(e in events for e in ('cpu-unmap', 'gpu-unmap', 'free', 'ctx-free', 'close')):
        raise RuntimeError('Exercise failure continued into cleanup')
    summaries = [json.loads(line.removeprefix('IB-MISMATCH-SUMMARY '))
                 for line in result.stderr.splitlines() if line.startswith('IB-MISMATCH-SUMMARY ')]
    targets = policy in TARGET_POLICIES
    wanted = None if targets else expected_mismatch_summary(fault)
    late = policy == 'single-observe-late' and wanted is not None
    wanted_summaries = [] if wanted is None else [wanted]
    if late:
        wanted_summaries.append(expected_late_summary(fault))
    if summaries != wanted_summaries:
        raise RuntimeError('Missing, unexpected or inaccurate mismatch classification')
    if any(type(row[key]) is not type(value) for row, want in zip(summaries,wanted_summaries) for key,value in want.items()):
        raise RuntimeError('Mismatch summary field type changed')
    target_rows = [json.loads(line.split(' ',1)[1]) for line in result.stderr.splitlines()
                   if line.startswith('IB-TARGET-SUMMARY ')]
    wanted_targets = expected_target_summaries(fault,policy)
    if target_rows != wanted_targets or any(type(row[k]) is not type(v)
            for row,want in zip(target_rows,wanted_targets) for k,v in want.items()):
        raise RuntimeError('Missing, unexpected or inaccurate target classification')
    if targets:
        framed = [line.split(' ',1)[0] for line in result.stderr.splitlines()
                  if line.startswith(('IB-TARGET-SUMMARY ', 'HOLD:'))]
        if framed != ['IB-TARGET-SUMMARY']*len(wanted_targets)+(['HOLD:'] if 'hold' in events else []):
            raise RuntimeError('Target observation/HOLD order changed')
    timing_lines = [line for line in result.stderr.splitlines() if line.startswith('IB-LATE-OBSERVATION ')]
    timings = [json.loads(line.split(' ',1)[1]) for line in timing_lines]
    wanted_timing = [expected_late_timing(fault)] if late else []
    if timings != wanted_timing or any(type(row[key]) is not type(value)
            for row,want in zip(timings,wanted_timing) for key,value in want.items()):
        raise RuntimeError('Missing, unexpected or inaccurate delayed observation timing')
    if late:
        framed = [line.split(' ',1)[0] for line in result.stderr.splitlines()
                  if line.startswith(('IB-MISMATCH-SUMMARY ', 'IB-LATE-OBSERVATION ', 'HOLD:'))]
        if framed != ['IB-MISMATCH-SUMMARY','IB-LATE-OBSERVATION','IB-MISMATCH-SUMMARY','HOLD:']:
            raise RuntimeError('Delayed observation/HOLD order changed')
    waits = [json.loads(line) for line in lines if line.startswith('{')]
    transport_waits = tuple(f'wait-{stage}-{kind}' for stage in (1, 2) for kind in ('status', 'short', 'long'))
    unlogged = int(fault in transport_waits)
    if len(waits) + unlogged != sum(e.startswith('wait-') for e in events):
        raise RuntimeError('Wait accounting mismatch')
    for row in waits:
        if set(row) != {'pass', 'budget_ns', 'busy', 'elapsed_ns'} or row['pass'] not in (0, 1) or row['busy'] not in (0, 1) or row['elapsed_ns'] != 4000:
            raise RuntimeError('Invalid synthetic wait observation')
    for stage in range(2):
        rows = [row for row in waits if row['pass'] == stage]
        if [row['budget_ns'] for row in rows] != [0, 50000, 2000000000][:len(rows)]:
            raise RuntimeError('Wait order changed')
        if not code and fault != 'check-ok' and (not rows or rows[-1]['busy'] or any(not row['busy'] for row in rows[:-1])):
            raise RuntimeError('Missing positive retirement or continued wait')
    stale_offset = 10256 if policy == 'target-switch' else 8208
    if (fault == 'stale-output-2' or fault.startswith('late-')) and f'mismatch at byte {stale_offset} (pass=1 actual=0xde expected=0xdf)' not in result.stderr:
        raise RuntimeError('Stale pattern was not rejected')
    if fault.startswith('preamble-'):
        _, stage, byte = fault.split('-')
        if f'mismatch at byte {0x1400 + int(byte)} (pass={int(stage) - 1} ' not in result.stderr:
            raise RuntimeError('Immutable preamble corruption not guarded')
    if fault.startswith('slot-') and f'mismatch at byte {0x1200 + int(fault[5:]) * 4} (pass=1 ' not in result.stderr:
        raise RuntimeError('Unused slot corruption not guarded')
    return {'events': events, 'wait_observations': waits}


def batch_results(result, count):
    """Require complete, matching frames from both streams before checking cases."""
    if result.returncode:
        raise RuntimeError('Mock batch process failed')
    streams = []
    for text in (result.stdout, result.stderr):
        frames = []
        start = 0
        for match in re.finditer(r'^fake-native-case-end (\{[^\n]*\})\n', text, re.MULTILINE):
            meta = json.loads(match[1])
            if (set(meta) != {'index', 'returncode'} or type(meta['index']) is not int or
                    type(meta['returncode']) is not int or meta['index'] != len(frames) or
                    not 0 <= meta['returncode'] <= 255):
                raise RuntimeError('Malformed mock batch frame')
            frames.append((meta, text[start:match.start()]))
            start = match.end()
        if len(frames) != count or start != len(text):
            raise RuntimeError('Incomplete or unframed mock output')
        streams.append(frames)
    parsed = []
    for (out_meta, stdout), (err_meta, stderr) in zip(*streams):
        if out_meta != err_meta:
            raise RuntimeError('Mock stdout/stderr case mismatch')
        parsed.append(subprocess.CompletedProcess([], out_meta['returncode'], stdout, stderr))
    return parsed


def exercise(out):
    compiler = shutil.which('clang++')
    if not compiler or platform.system() not in ('Darwin', 'Linux'):
        raise RuntimeError('Requires POSIX Clang++; not a hardware test')
    out = Path(out).resolve()
    if out.exists():
        raise ValueError('Choose a fresh output directory')
    paths = [ROOT / name for name in ('tools/upstream34_layout/ib_preamble_probe.cpp',
             'tools/upstream34_layout/ib_preamble_packets.h', 'tools/upstream34_layout/ib_mismatch_summary.h',
             'tools/upstream34_layout/ib_target_summary.h',
             'tools/upstream34_layout/ib_preamble.py', 'tools/test_upstream34_ib_preamble.py',
             'tests/test_build34_ib_preamble.cpp', 'tests/test_upstream34_ib_preamble_runner.py')]
    paths += sorted((ROOT / 'tests/fake_build34_ib_preamble').rglob('*.h'))
    snapshots = {p:p.read_bytes() for p in paths}
    protected = mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    out.mkdir(parents=True, mode=0o700)
    binary = out / 'preamble-simulation'
    command = [compiler, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-g',
               '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
               '-I' + str(ROOT / 'tests/fake_build34_ib_preamble'),
               '-I' + str(ROOT / 'src/phxbringup'),
               str(ROOT / 'tests/test_build34_ib_preamble.cpp'), '-o', str(binary)]
    subprocess.run(command, check=True, timeout=90, stdin=subprocess.DEVNULL)
    if platform.system() == 'Darwin':
        linked = subprocess.check_output(['/usr/bin/otool', '-L', str(binary)], text=True, timeout=15)
        if 'IOKit.framework' in linked or 'CoreFoundation.framework' in linked:
            raise RuntimeError('Mock binary linked a real device framework')
    results = []
    for variant in ('low', 'upper'):
        for policy in ALL_POLICIES:
            selected_cases = policy_cases(policy)
            batch = subprocess.run([str(binary), '--batch', variant, policy, *selected_cases], capture_output=True,
                                   text=True, timeout=180, stdin=subprocess.DEVNULL)
            for fault, result in zip(selected_cases, batch_results(batch, len(selected_cases))):
                if fault in EXEC_EQUIVALENCE_CASES + TARGET_MODELS:
                    separate = subprocess.run([str(binary), variant, fault, policy], capture_output=True,
                                              text=True, timeout=10, stdin=subprocess.DEVNULL)
                    if (separate.returncode, separate.stdout, separate.stderr) != (result.returncode, result.stdout, result.stderr):
                        raise RuntimeError(f'Batch/separate-process behavior differs: {variant}/{policy}/{fault}')
                try:
                    checked = check_result(result, fault, policy)
                except Exception as error:
                    raise RuntimeError(f'Preamble {variant}/{policy}/{fault}: {error}') from error
                results.append({'variant': variant, 'policy': policy, 'case': fault, **checked})
            print(json.dumps({'completed': variant + '/' + policy, 'cases': len(selected_cases), 'hardware_executed': False}), flush=True)
    if any(p.read_bytes() != data for p,data in snapshots.items()):
        raise RuntimeError('Diagnostic source changed during CPU tests')
    mec_range.verify_current_inputs(mec_range.protected_base_inputs(), ROOT)
    record = {'base_commit': mec_range.BASE, 'original34_protected_sha256': protected,
              'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              'cases': results, 'sanitizers': 'ASan/UBSan', 'hardware_executed': False,
              'native_IOKit_linked': False, 'shader_executed': False,
              'case_isolation': 'reset fake fixture per case; synthetic clock regresses only for the explicit clock fault; no per-case fork or exec',
              'separate_process_equivalence_cases': len(EXEC_EQUIVALENCE_CASES) * len(ALL_POLICIES) * 2 + len(TARGET_MODELS) * len(TARGET_POLICIES) * 2,
              'limitation': 'Fake IOKit/CF, synthetic clock and injected bytes. No GPU ISA, cache/coherency or synchronization emulation; passing memsync is not a hardware result.'}
    (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'result': 'passed', 'scenarios': len(results), 'hardware_executed': False}), flush=True)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    exercise(parser.parse_args().out)
