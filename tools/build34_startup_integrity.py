#!/usr/bin/env python3
"""Bound memory while reading every byte for local build34 startup admission.

This module has no installation, hardware, caching or policy side effects.
The owner wrapper must separately pin it before using sha256_file as its
protected-file hash function. Expected digests and admission gates stay intact.
"""

import hashlib
import os
from pathlib import Path
import stat
from concurrent.futures import ThreadPoolExecutor


HASH_CHUNK_BYTES = 1024 * 1024


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_uid, info.st_gid, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, getattr(info, "st_flags", 0))


def sha256_file(path):
    """Return the full SHA-256, refusing observed file/path changes while reading.

    Follow existing protected aliases, then check that the path still resolves
    to the same regular file. Never reuse a prior digest or a metadata cache.
    The extra identity checks detect observed changes, not an atomic snapshot
    against a privileged concurrent writer.
    """
    path = Path(path)
    digest = hashlib.sha256()
    buffer = bytearray(HASH_CHUNK_BYTES)
    view = memoryview(buffer)
    total = 0
    with path.open("rb", buffering=0) as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise OSError("startup integrity requires a regular file")
        while True:
            count = handle.readinto(buffer)
            if not count:
                break
            total += count
            if total > before.st_size:
                raise OSError("startup integrity file grew while reading")
            digest.update(view[:count])
        after = os.fstat(handle.fileno())
        if (total != before.st_size or _identity(before) != _identity(after)
                or _identity(after) != _identity(path.stat())):
            raise OSError("startup integrity file or path changed while reading")
    return digest.hexdigest()


def verify_sha256_files(expected, *, workers=2):
    """Check every supplied full digest with at most two bounded-memory readers.

    Each invocation reads every file again; no digest or metadata result is
    cached. The caller retains policy, path selection, missing-marker handling
    and all other admission gates. All workers finish before this call returns
    or raises. This is one verification phase, not a cross-phase snapshot.
    """
    if type(workers) is not int or workers not in (1, 2):
        raise ValueError("startup integrity permits one or two workers")
    entries = tuple(expected.items())
    for _, digest in entries:
        if (not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise ValueError("startup integrity requires a full lowercase SHA-256")

    def verify(entry):
        path, digest = entry
        if sha256_file(path) != digest:
            raise AssertionError(str(path))

    if workers == 1:
        for entry in entries:
            verify(entry)
    elif entries:
        with ThreadPoolExecutor(max_workers=2,
                                thread_name_prefix="build34-integrity") as pool:
            for _ in pool.map(verify, entries):
                pass
