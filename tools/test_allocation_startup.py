"""Characterize pinned startup fragments with command fakes; never run the reference script."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SHA256 = '6c0271c306b8edbe0bc5b294794a8f47480a6bd25eae9c0a9207471f8fd794d8'
START = 'touch "$MARK"; sync\napps_only\n'
END = 'for i in $(seq 1 20); do ioreg -rc NMXAccel'

# Only fixture commands and shell builtins run. The reference fragment's bash
# call is a function; full.sh is deliberately absent. The one path command is
# a newly written, guarded claim fake. grep processes fixture text only.
PRELUDE = r'''[[ "$SAFE_TEST" == allocation-startup-cpu-only && -n "$G" && "$G" == "$SAFE_ROOT" ]] || exit 96
exec 9>>"$TRACE"
event() { printf '%s\n' "$1" >&9; }
touch() { event marker-touch; }
sync() { event sync; }
apps_only() { event apps-only; }
nvram() { event nvram-fake; }
nv_commit() { event nvram-commit-fake; }
rm() { event remove-marker-fake; }
shutdown() { event shutdown-fake; }
grep() { /usr/bin/grep "$@"; local result=$?; event "grep-exit:$result"; return "$result"; }
bash() {
    [[ $# == 2 && "$1" == "$G/full.sh" && "$2" == kiqsched && "$MC$CS$ADOPT$GFX$AG" == 11111 ]] || { event unsafe-call; exit 97; }
    event initializer-enter
    if [[ "$BLOCK" == initializer ]]; then IFS= read -r proceed || return 98; fi
    if [[ "$EMIT_MATCH" == 1 ]]; then printf 'compute: cpu-fixture\n'; else printf 'cpu-fixture-no-match\n'; fi
    event "initializer-exit:$INIT_STATUS"
    return "$INIT_STATUS"
}
sysctl() {
    event sysctl-enter
    if [[ "$BLOCK" == recovery ]]; then IFS= read -r proceed || return 98; fi
    event sysctl-exit
    return 0
}
'''
CLAIM_FAKE = r'''#!/bin/bash
[[ "$SAFE_TEST" == allocation-startup-cpu-only && -n "$G" && "$G" == "$SAFE_ROOT" && $# == 1 && "$1" == claim ]] || exit 96
printf 'claim-enter\n' >&9
if [[ "$BLOCK" == claim ]]; then IFS= read -r proceed || exit 98; fi
printf 'claim-exit:%s\n' "$CLAIM_STATUS" >&9
exit "$CLAIM_STATUS"
'''


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def extract(raw):
    require(hashlib.sha256(raw).hexdigest() == REFERENCE_SHA256, 'Reference source changed; re-audit before execution')
    text = raw.decode('utf-8')
    require(text.count(START) == 1 and text.count(END) == 1, 'Startup extraction anchors')
    start, end = text.index(START), text.index(END)
    require(start < end, 'Startup extraction order')
    opening = 'm2_fail() {\n'
    require(text.count(opening) == 1, 'Recovery extraction anchor')
    recovery_start = text.index(opening)
    recovery_end = text.index('\n}\n', recovery_start) + 3
    require(text.rindex('[ $M2 = 1 ] && watch_hangs') > end and
            text.index('watch_hangs() {') > end, 'Review changed recovery control flow')
    return {'startup.inc': text[start:end], 'recovery.inc': text[recovery_start:recovery_end]}


def write_private(path, content, executable=False):
    with path.open('xb') as stream:
        os.fchmod(stream.fileno(), 0o700 if executable else 0o600)
        stream.write(content)


def events(path):
    return path.read_text().splitlines() if path.exists() else []


def run_case(root, name, fragment, *, initializer=0, claim=0, matching=True, block=''):
    folder = root / name
    folder.mkdir(mode=0o700)
    gpu = folder / 'fake-inputs'
    gpu.mkdir(mode=0o700)
    (gpu / 'phxctl').mkdir(mode=0o700)
    write_private(gpu / 'phxctl/mesboot', CLAIM_FAKE.encode(), executable=True)
    require(not (gpu / 'full.sh').exists(), 'Initializer fixture must not exist')
    empty_path = folder / 'empty-path'
    empty_path.mkdir(mode=0o700)
    script = folder / 'fragment-test.sh'
    suffix = '\nm2_fail cpu-fixture\n' if name == 'blocked-recovery-sysctl' else ''
    write_private(script, (PRELUDE + fragment + suffix).encode())
    trace = folder / 'events-private.log'
    write_private(trace, b'')
    env = {'SAFE_TEST': 'allocation-startup-cpu-only', 'SAFE_ROOT': str(gpu), 'G': str(gpu),
           'TRACE': str(trace), 'PATH': str(empty_path), 'HOME': str(folder), 'LC_ALL': 'C',
           'MARK': str(folder / 'unused-marker'), 'INIT_STATUS': str(initializer),
           'CLAIM_STATUS': str(claim), 'EMIT_MATCH': '1' if matching else '0', 'BLOCK': block}
    child = subprocess.Popen(['/bin/bash', '--noprofile', '--norc', str(script)],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             env=env, start_new_session=True)
    before_release = None
    try:
        if block:
            marker = {'initializer': 'initializer-enter', 'claim': 'claim-enter',
                      'recovery': 'sysctl-enter'}[block]
            deadline = time.monotonic() + 3
            while marker not in events(trace):
                require(child.poll() is None and time.monotonic() < deadline, 'Fake stage did not block')
                time.sleep(0.01)
            # The control pipe remains open and unsignalled; no kernel method is involved.
            time.sleep(0.05)
            require(child.poll() is None, 'Fake stage unexpectedly completed')
            before_release = events(trace)
            child.stdin.write(b'continue\n')
            child.stdin.flush()
        stdout, stderr = child.communicate(timeout=3)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate(timeout=3)
    write_private(folder / 'stdout-private.log', stdout)
    write_private(folder / 'stderr-private.log', stderr)
    trace.chmod(0o600)
    trail = events(trace)
    require(child.returncode == 0 and 'unsafe-call' not in trail and not stderr, 'Unexpected fake fragment result')
    if name == 'blocked-recovery-sysctl':
        require('shutdown-fake' not in before_release and 'nvram-fake' not in before_release,
                'Recovery advanced past blocked fake sysctl')
        require(trail[-1] == 'shutdown-fake', 'Fake recovery did not complete after release')
    else:
        require('initializer-exit:' + str(initializer) in trail and
                'claim-exit:' + str(claim) in trail and
                ('grep-exit:0' if matching else 'grep-exit:1') in trail and
                trail[-1] == 'sysctl-exit',
                'Expected current source continuation')
        if block == 'initializer':
            require('claim-enter' not in before_release and 'sysctl-enter' not in before_release,
                    'Initializer block did not serialize startup')
        if block == 'claim':
            require('sysctl-enter' not in before_release, 'Claim block did not serialize startup')
    return {'case': name, 'exit_status': child.returncode, 'events': trail,
            'events_before_fake_release': before_release}


def exercise(out, source=ROOT / 'tools/phxctl/phxboot.sh'):
    source = Path(source)
    require(source.is_file() and not source.is_symlink(), 'Expected ordinary reference source')
    raw = source.read_bytes()
    fragments = extract(raw)  # Refuse unknown commands before creating files or starting a child.
    out = Path(out).absolute()
    require(not out.exists() and not out.is_symlink(), 'Output exists; no replay or overwrite')
    require(not any(c.isspace() for c in str(out)), 'Use a whitespace-free private fixture path')
    require(Path('/bin/bash').is_file() and Path('/usr/bin/grep').is_file(), 'CPU shell tools unavailable')
    out.mkdir(mode=0o700, parents=True)
    for name, text in fragments.items():
        write_private(out / name, text.encode())
    startup = fragments['startup.inc']
    cases = [
        run_case(out, 'successful-stubs', startup),
        run_case(out, 'initializer-fails-with-matching-output', startup, initializer=17),
        run_case(out, 'initializer-fails-without-matching-output', startup, initializer=17, matching=False),
        run_case(out, 'claim-fails', startup, claim=23),
        run_case(out, 'blocked-initializer', startup, block='initializer'),
        run_case(out, 'blocked-claim', startup, block='claim'),
        run_case(out, 'blocked-recovery-sysctl', fragments['recovery.inc'], block='recovery'),
    ]
    require(source.read_bytes() == raw, 'Reference source changed during audit')
    result = {
        'cases': len(cases), 'passed': True, 'reference_sha256': REFERENCE_SHA256,
        'inputs_sha256': {'tools/phxctl/phxboot.sh': REFERENCE_SHA256,
                          'tools/test_allocation_startup.py': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        'fragments_sha256': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in fragments.items()},
        'observations': {
            'initializer_failure_does_not_block_claim_in_reference': True,
            'nonzero_pipeline_status_does_not_block_claim_in_reference': True,
            'claim_failure_does_not_block_later_setup_in_reference': True,
            'startup_waits_for_initializer_and_claim': True,
            'recovery_sysctl_precedes_its_shutdown_request': True,
            'watch_hangs_definition_and_call_follow_startup': True,
        },
        'results': cases,
        'hardware_executed': False, 'target_services_opened': False,
        'reference_script_executed_as_a_whole': False, 'installed_monitor_read_or_changed': False,
        'real_sysctl_nvram_marker_or_shutdown_commands': False,
        'limitation': ('Pinned actual source fragments; fake initializer, claim, system commands and blocking pipes. '
                       'No complete reference/installed monitor, startup integration, actual GPU/sysctl hang, '
                       'independent system recovery, target service or reboot is exercised or proven.'),
    }
    write_private(out / 'report.json', (json.dumps(result, indent=2) + '\n').encode())
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    exercise(parser.parse_args().out)
