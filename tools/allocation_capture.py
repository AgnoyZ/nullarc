#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR GPL-2.0-only
"""Save one baseline and one pre-fallback software snapshot; never manage recovery."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import signal
import stat
import subprocess
import sys
import time
import uuid
from xml.parsers.expat import ExpatError

LIMIT = 128 * 1024
READER_LIMIT = 16 * 1024 * 1024
WAIT_SECONDS = 5.0
U64 = (1 << 64) - 1
REASONS = ('map-retirement-pending', 'map-retirement-invalid',
           'unmap-retirement-pending', 'unmap-retirement-invalid',
           'map-pending-overlap', 'host-descriptor', 'host-prepare')
QUEUES = ('unobserved', 'valid', 'missing-output', 'no-aperture', 'inactive',
          'unaligned-fence', 'history-overflow', 'future-floor', 'all-ones-fence',
          'regressed-fence', 'future-fence', 'zero-sequence',
          'nonmonotonic-sequence', 'future-sequence', 'unknown-fence')
COMMANDS = {
    'boot': ('/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'),
    'os': ('/usr/bin/sw_vers', '-buildVersion'),
    'service': ('/usr/sbin/ioreg', '-a', '-r', '-c', 'PhxBringup', '-d', '1'),
    'image': ('/usr/sbin/kextstat', '-l', '-b', 'org.drip.PhxBringup'),
}
ENV = {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LC_ALL': 'C',
       'SYSTEM_VERSION_COMPAT': '0'}


class CaptureError(Exception):
    """Public messages are fixed codes, never raw command output or identities."""


def require(condition, code):
    if not condition:
        raise CaptureError(code)


def host_check():
    require(platform.system() == 'Darwin' and platform.machine() == 'x86_64'
            and os.geteuid() == 0, 'host-refused')


def keys(value, expected):
    require(type(value) is dict and set(value) == set(expected.split()), 'schema')


def integer(value, maximum=U64):
    require(type(value) is int and 0 <= value <= maximum, 'schema')
    return value


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'schema')
        value[key] = item
    return value


def decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=unique,
                          parse_constant=lambda _: require(False, 'schema'))
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise CaptureError('schema') from exc


def canonical_uuid(value):
    try:
        require(type(value) is str and len(value) == 36, 'identity')
        return str(uuid.UUID(value)).upper()
    except ValueError as exc:
        raise CaptureError('identity') from exc


def checked_path(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'path')
    for parent in reversed((path, *path.parents)):
        require(not parent.is_symlink(), 'path')
    return path


def directory(path):
    path = checked_path(path)
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'private-directory')
    return path


def read_file(path, limit=LIMIT):
    path = checked_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == os.geteuid() and not info.st_mode & 0o077
                and info.st_size <= limit, 'private-file')
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'file-size')
    return raw


def write_file(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def write_json(path, value):
    write_file(path, (json.dumps(value, indent=2, sort_keys=True) + '\n').encode())


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish_json(path, value):
    pending = path.with_name(path.name + '.incomplete')
    write_json(pending, value)
    # Publish only a fully written, fsynced file, without replacing an existing result.
    os.link(pending, path, follow_symlinks=False)
    pending.unlink()


def reader_pin(path, digest):
    path = checked_path(path)
    require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest), 'reader-pin')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == os.geteuid() and info.st_mode & 0o111
                and not info.st_mode & 0o022 and info.st_size <= READER_LIMIT, 'reader-pin')
        raw = stream.read(READER_LIMIT + 1)
    require(len(raw) <= READER_LIMIT and hashlib.sha256(raw).hexdigest() == digest, 'reader-pin')
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def child_limits():
    import resource  # Live collection is Intel macOS only; offline parsing is portable.
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMIT, LIMIT))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_command(args, folder, label, deadline):
    """Bound child output and waits; no shell, polling or retry."""
    remaining = deadline - time.monotonic()
    require(remaining > 0, 'deadline')
    out_fd = os.open(folder / (label + '.stdout'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    err_fd = os.open(folder / (label + '.stderr'), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    timed_out = False
    with os.fdopen(out_fd, 'wb') as stdout, os.fdopen(err_fd, 'wb') as stderr:
        child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                 env=ENV, start_new_session=True, close_fds=True,
                                 preexec_fn=child_limits)
        try:
            child.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
        finally:
            # Only the new group owned by this invocation; never a monitor or GPU helper.
            if child.returncode is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                try:
                    child.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass  # A kernel-blocked process cannot be made cancellable here.
        stdout.flush()
        stderr.flush()
        os.fsync(stdout.fileno())
        os.fsync(stderr.fileno())
    write_json(folder / (label + '.status.json'),
               {'returncode': child.returncode, 'timed_out': timed_out})
    require(not timed_out, 'command-timeout')
    require(child.returncode == 0, 'command-failed')
    raw = read_file(folder / (label + '.stdout'))
    read_file(folder / (label + '.stderr'))
    require(raw, 'empty-output')
    return raw


def identity(folder, suffix, deadline, spec, run):
    raw = {key: run(args, folder, key + '-' + suffix, deadline)
           for key, args in COMMANDS.items()}
    boot = canonical_uuid(raw['boot'].decode().strip())
    os_build = raw['os'].decode().strip()
    require(re.fullmatch('[0-9]{2}[A-Z][0-9]+[a-z]?', os_build), 'identity')
    nodes = plistlib.loads(raw['service'])
    require(type(nodes) is list and len(nodes) == 1 and type(nodes[0]) is dict, 'identity')
    node = nodes[0]
    build = integer(node.get('phx-build'), (1 << 32) - 1)
    service = integer(node.get('IORegistryEntryID'))
    require(service > 0 and build == spec['expected_build'], 'identity')
    lines = [line.split() for line in raw['image'].decode().splitlines()
             if 'org.drip.PhxBringup' in line.split()]
    require(len(lines) == 1, 'identity')
    images = re.findall(r'\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b',
                        ' '.join(lines[0]))
    require(len(images) == 1, 'identity')
    image = canonical_uuid(images[0])
    require(image == spec['expected_image_uuid'], 'identity')
    return {'boot_uuid': boot, 'os_build': os_build, 'service_entry_id': service,
            'kext_build': build, 'loaded_image_uuid': image}


def snapshot(raw, expected_build):
    value = decode(raw)
    keys(value, 'version kext_build observed samples_per_reason reasons')
    require(integer(value['version']) == 1 and integer(value['kext_build']) == expected_build
            and integer(value['samples_per_reason']) == 4, 'schema')
    observed = integer(value['observed'])
    reasons = value['reasons']
    require(type(reasons) is list and len(reasons) == len(REASONS), 'schema')
    total = 0
    ordinals = set()
    for reason, expected in zip(reasons, REASONS):
        keys(reason, 'reason count records')
        require(reason['reason'] == expected, 'schema')
        count = integer(reason['count'])
        require(count <= observed and type(reason['records']) is list
                and len(reason['records']) == min(4, count), 'schema')
        total = min(U64, total + count)
        previous = 0
        for record in reason['records']:
            keys(record, 'ordinal status status_hex bytes last_seq submitted retired observation_valid queues')
            ordinal = integer(record['ordinal'])
            require(0 < ordinal <= observed and ordinal >= previous
                    and (ordinal == U64 or ordinal not in ordinals), 'schema')
            previous = ordinal
            ordinals.add(ordinal)
            status = integer(record['status'], (1 << 32) - 1)
            require(record['status_hex'] == f'0x{status:08x}', 'schema')
            for field in ('bytes', 'last_seq', 'submitted', 'retired'):
                integer(record[field])
            integer(record['observation_valid'], 1)
            require(type(record['queues']) is list and len(record['queues']) == 2, 'schema')
            for queue in record['queues']:
                keys(queue, 'reason fence_read done floor count first_pending')
                require(type(queue['reason']) is str and queue['reason'] in QUEUES, 'schema')
                integer(queue['fence_read'], 1)
                integer(queue['count'], (1 << 32) - 1)
                for field in ('done', 'floor', 'first_pending'):
                    integer(queue[field])
    require(total == observed, 'schema')
    return value


def comparison(baseline, failure):
    require(failure['observed'] >= baseline['observed'], 'history-regressed')
    result = []
    for before, after in zip(baseline['reasons'], failure['reasons']):
        require(after['count'] >= before['count'], 'history-regressed')
        require(after['records'][:len(before['records'])] == before['records'], 'history-replaced')
        added = after['records'][len(before['records']):]
        require(all(record['ordinal'] > baseline['observed'] or record['ordinal'] == U64
                    for record in added), 'history-replaced')
        result.append({'reason': before['reason'], 'baseline_count': before['count'],
                       'failure_count': after['count'],
                       'minimum_new_occurrences': after['count'] - before['count'],
                       'delta_exact': after['count'] < U64, 'new_records': added,
                       'detail_capacity_exhausted': after['count'] >= 4})
    return result


def collect(root, phase, spec, run, baseline=None, baseline_raw=None):
    # This exclusive, durable claim is never removed, including on failure.
    write_file(root / (phase + '.started'), b'one attempt; no automatic retry\n')
    sync_directory(root)
    folder = root / phase
    folder.mkdir(mode=0o700)
    deadline = time.monotonic() + WAIT_SECONDS
    pin = reader_pin(spec['reader'], spec['reader_sha256'])
    before = identity(folder, 'before', deadline, spec, run)
    if baseline is not None:
        require(before == baseline['identity'], 'identity-changed')
    raw = run((spec['reader'],), folder, 'snapshot', deadline)
    value = snapshot(raw, spec['expected_build'])
    after = identity(folder, 'after', deadline, spec, run)
    require(before == after, 'identity-changed')
    require(reader_pin(spec['reader'], spec['reader_sha256']) == pin, 'reader-pin')
    result = {'format': 1, 'phase': phase, 'saved_at': datetime.now(timezone.utc).isoformat(),
              'identity': after, 'spec': spec, 'snapshot': value}
    if baseline is not None:
        require(read_file(root / 'baseline.json') == baseline_raw, 'baseline-changed')
        result['baseline_sha256'] = hashlib.sha256(baseline_raw).hexdigest()
        result['comparison'] = comparison(baseline['snapshot'], value)
    sync_directory(folder)
    publish_json(root / (phase + '.json'), result)
    sync_directory(root)
    return result


def begin(root, reader, digest, build, image, run=run_command):
    host_check()
    root = checked_path(root)
    require(integer(build, (1 << 32) - 1) > 0, 'build')
    spec = {'reader': str(checked_path(reader)), 'reader_sha256': digest,
            'expected_build': build, 'expected_image_uuid': canonical_uuid(image)}
    # No parents created, no reuse of an existing output directory.
    root.mkdir(mode=0o700)
    write_file(root / '.gitignore', b'*\n')
    sync_directory(root.parent)
    return collect(directory(root), 'baseline', spec, run)


def finish(root, run=run_command):
    host_check()
    root = directory(root)
    require(read_file(root / '.gitignore') == b'*\n'
            and read_file(root / 'baseline.started') == b'one attempt; no automatic retry\n', 'baseline')
    baseline_raw = read_file(root / 'baseline.json')
    baseline = decode(baseline_raw)
    keys(baseline, 'format phase saved_at identity spec snapshot')
    require(baseline['format'] == 1 and baseline['phase'] == 'baseline', 'baseline')
    spec = baseline['spec']
    keys(spec, 'reader reader_sha256 expected_build expected_image_uuid')
    require(snapshot(json.dumps(baseline['snapshot']).encode(), spec['expected_build'])
            == baseline['snapshot'], 'baseline')
    return collect(root, 'failure', spec, run, baseline, baseline_raw)


def interrupted(_signum, _frame):
    raise CaptureError('interrupted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='phase', required=True)
    start = commands.add_parser('baseline', help='one passive baseline, before the authorized workload')
    start.add_argument('--out', required=True, type=Path)
    start.add_argument('--reader', required=True, type=Path)
    start.add_argument('--reader-sha256', required=True)
    start.add_argument('--expected-build', required=True, type=int)
    start.add_argument('--expected-image-uuid', required=True)
    end = commands.add_parser('failure', help='one passive capture before the existing fallback')
    end.add_argument('--capture', required=True, type=Path)
    args = parser.parse_args()
    for name in ('SIGINT', 'SIGTERM', 'SIGHUP'):
        signum = getattr(signal, name, None)
        if signum is not None:
            signal.signal(signum, interrupted)
    try:
        if args.phase == 'baseline':
            begin(args.out, args.reader, args.reader_sha256, args.expected_build, args.expected_image_uuid)
        else:
            finish(args.capture)
    except (CaptureError, OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, OverflowError,
            plistlib.InvalidFileException, ExpatError, RecursionError) as exc:
        code = str(exc) if isinstance(exc, CaptureError) else 'input-or-io'
        print('allocation-capture refused: ' + code + '; keep partial output private', file=sys.stderr)
        return 74
    print('Private allocation capture saved; no recovery action requested.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
