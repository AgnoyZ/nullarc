#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR GPL-2.0-only
"""Resume one explicitly configured active Codex goal after a new host boot."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys

try:
    import fcntl
except ImportError:
    fcntl = None

CONFIG_KEYS = {'version', 'thread_id', 'goal_id', 'repository', 'branch', 'codex',
               'codex_sha256', 'goals_database', 'state_database', 'checkpoint',
               'armed_boot', 'prompt'}


class ResumeError(Exception):
    pass


def require(condition, code):
    if not condition:
        raise ResumeError(code)


def plain_path(value):
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'path')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'path')
    return path


def private_directory(path):
    path = plain_path(path)
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, 'private-directory')
    return path


def trusted_file(path, private=False):
    path = plain_path(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
            and info.st_uid in (0, os.geteuid())
            and not info.st_mode & (0o077 if private else 0o022), 'file-permissions')
    return path


def read_json(path):
    path = trusted_file(path, private=True)
    require(path.stat().st_size <= 65536, 'file-size')
    with path.open() as stream:
        return json.load(stream)


def persist(root, name, value):
    pending = root / (name + '.pending')
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, root / name)
    sync_directory(root)


def sync_directory(root):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def query(path, sql, thread):
    path = trusted_file(path)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5) as db:
        return db.execute(sql, (thread,)).fetchone()


def boot_identity():
    value = subprocess.check_output(
        ['/usr/sbin/sysctl', '-n', 'kern.bootsessionuuid'], timeout=10).decode().strip()
    require(bool(value) and len(value) < 128, 'boot-identity')
    return value


def run_once(config_path, *, boot=None, runner=None, allow_current_boot=False, check=False):
    require(fcntl is not None, 'host-lock')
    config_path = plain_path(config_path)
    root = private_directory(config_path.parent)
    if (root / 'disabled').exists():
        return {'status': 'disabled'}
    lock_fd = os.open(root / 'resume.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'already-running'}
        config = read_json(config_path)
        require(type(config) is dict and set(config) == CONFIG_KEYS
                and type(config['version']) is int and config['version'] == 1, 'configuration')
        require(all(type(config[k]) is str and config[k] for k in CONFIG_KEYS - {'version'}),
                'configuration')
        checkpoint = read_json(config['checkpoint'])
        require(type(checkpoint) is dict and checkpoint.get('thread_id') == config['thread_id']
                and checkpoint.get('goal_id') == config['goal_id'], 'checkpoint-identity')
        row = query(config['goals_database'],
                    'SELECT goal_id,status FROM thread_goals WHERE thread_id=?', config['thread_id'])
        require(row is not None and row[0] == config['goal_id'], 'goal-identity')
        if row[1] != 'active':
            return {'status': 'goal-inactive'}
        thread = query(config['state_database'],
                       'SELECT archived FROM threads WHERE id=?', config['thread_id'])
        require(thread == (0,), 'thread-unavailable')
        repo = plain_path(config['repository'])
        actual = subprocess.check_output(
            ['git', '-C', str(repo), 'rev-parse', '--show-toplevel'], timeout=10).decode().strip()
        branch = subprocess.check_output(
            ['git', '-C', str(repo), 'branch', '--show-current'], timeout=10).decode().strip()
        require(actual == str(repo) and branch == config['branch'], 'repository')
        codex = trusted_file(config['codex'])
        require(os.access(codex, os.X_OK), 'executable')
        with codex.open('rb') as stream:
            digest = hashlib.sha256()
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        require(digest.hexdigest() == config['codex_sha256'], 'executable-pin')
        boot = boot_identity() if boot is None else boot
        require(type(boot) is str and bool(boot), 'boot-identity')
        if boot == config['armed_boot'] and not allow_current_boot:
            return {'status': 'armed-for-next-boot'}
        claims = root / 'attempts'
        if not claims.exists():
            claims.mkdir(mode=0o700)
        private_directory(claims)
        key = hashlib.sha256(boot.encode()).hexdigest()
        claim = claims / (key + '.json')
        if claim.exists():
            return {'status': 'boot-already-claimed'}
        if check:
            return {'status': 'ready', 'no_child_started': True}
        # Publish before starting Codex. An interrupted/failed launch is never replayed automatically.
        fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'claimed_at': datetime.datetime.now().astimezone().isoformat()}, stream)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        sync_directory(claims)
        command = [str(codex), 'exec', '--cd', str(repo), 'resume',
                   config['thread_id'], config['prompt']]
        log_fd = os.open(claims / (key + '.log'),
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        result = {'status': 'launching', 'automatic_replay': False}
        persist(root, 'last-result.json', result)
        with os.fdopen(log_fd, 'wb') as log:
            try:
                execute = subprocess.run if runner is None else runner
                child = execute(command, cwd=str(repo), stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, close_fds=True)
                result.update(status='exited', returncode=child.returncode)
            except BaseException:
                result['status'] = 'launch-interrupted-or-failed'
                persist(root, 'last-result.json', result)
                raise
        persist(root, 'last-result.json', result)
        return result
    finally:
        os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--check', action='store_true', help='Validate without starting Codex')
    parser.add_argument('--resume-now', action='store_true',
                        help='Explicitly permit this installation boot; existing claims still refuse')
    args = parser.parse_args()
    try:
        require(sys.platform == 'darwin', 'host')
        result = run_once(args.config, check=args.check, allow_current_boot=args.resume_now)
    except (ResumeError, OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as exc:
        code = str(exc) if isinstance(exc, ResumeError) else 'input-or-runtime'
        print('Goal continuation refused: ' + code, file=sys.stderr)
        return 74
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('returncode', 0) == 0 else 75


if __name__ == '__main__':
    raise SystemExit(main())
