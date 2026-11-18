#!/usr/bin/env python3
"""CPU-only full-digest, bounded-read and concurrent-change refusal checks."""

import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "build34_startup_integrity",
    Path(__file__).resolve().parents[1] / "tools/build34_startup_integrity.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class ObservedReader:
    def __init__(self, handle, before_read):
        self.handle = handle
        self.before_read = before_read
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.handle.close()

    def fileno(self):
        return self.handle.fileno()

    def readinto(self, buffer):
        self.calls += 1
        self.before_read(self.calls, buffer)
        return self.handle.readinto(buffer)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "protected-fixture"
        self.payload = b"build34-check\x00\xff" * 1000
        self.path.write_bytes(self.payload)

    def observed_hash(self, before_read):
        reader = ObservedReader(io.FileIO(self.path, "r"), before_read)
        with mock.patch.object(m.Path, "open", return_value=reader):
            result = m.sha256_file(self.path)
        self.assertTrue(reader.handle.closed)
        return result

    def test_full_digest_at_empty_chunk_and_multiple_chunk_boundaries(self):
        for length in [0, 1, m.HASH_CHUNK_BYTES - 1, m.HASH_CHUNK_BYTES,
                       m.HASH_CHUNK_BYTES + 1, 3 * m.HASH_CHUNK_BYTES + 17]:
            with self.subTest(length=length):
                payload = (bytes(range(256)) * (length // 256 + 1))[:length]
                self.path.write_bytes(payload)
                self.assertEqual(m.sha256_file(self.path), hashlib.sha256(payload).hexdigest())

    def test_every_read_uses_the_same_one_megabyte_buffer(self):
        payload = b"x" * (3 * m.HASH_CHUNK_BYTES + 19)
        self.path.write_bytes(payload)
        buffers = []
        result = self.observed_hash(lambda call, buffer: buffers.append(buffer))
        self.assertEqual(result, hashlib.sha256(payload).hexdigest())
        self.assertEqual(len(buffers), 5)
        self.assertTrue(all(buffer is buffers[0] for buffer in buffers))
        self.assertEqual(len(buffers[0]), 1024 * 1024)

    def test_no_digest_is_reused_after_same_length_rewrite(self):
        first = m.sha256_file(self.path)
        updated = b"y" * len(self.payload)
        self.path.write_bytes(updated)
        self.assertNotEqual(m.sha256_file(self.path), first)
        self.assertEqual(m.sha256_file(self.path), hashlib.sha256(updated).hexdigest())

    def test_existing_symlink_alias_retains_full_digest_semantics(self):
        alias = self.path.with_name("alias-fixture")
        alias.symlink_to(self.path.name)
        self.assertEqual(m.sha256_file(alias), hashlib.sha256(self.payload).hexdigest())

    def test_missing_file_refused(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            m.sha256_file(self.path)

    def test_nonregular_file_refused(self):
        with self.assertRaisesRegex(OSError, "regular file"):
            m.sha256_file(os.devnull)

    def test_growth_while_reading_refused(self):
        def grow(call, buffer):
            if call == 1:
                with io.FileIO(self.path, "a") as handle:
                    handle.write(b"extra")
        with self.assertRaisesRegex(OSError, "grew"):
            self.observed_hash(grow)

    def test_truncation_while_reading_refused(self):
        def truncate(call, buffer):
            if call == 1:
                os.truncate(self.path, 0)
        with self.assertRaisesRegex(OSError, "changed"):
            self.observed_hash(truncate)

    def test_path_replacement_with_identical_bytes_refused(self):
        replacement = self.path.with_name("replacement-fixture")
        replacement.write_bytes(self.payload)
        def replace(call, buffer):
            if call == 1:
                os.replace(replacement, self.path)
        with self.assertRaisesRegex(OSError, "changed"):
            self.observed_hash(replace)

    def test_metadata_change_while_reading_refused(self):
        self.path.chmod(0o600)
        def change_mode(call, buffer):
            if call == 1:
                self.path.chmod(0o400)
        with self.assertRaisesRegex(OSError, "changed"):
            self.observed_hash(change_mode)

    def test_read_failure_is_propagated_and_handle_closed(self):
        reader = ObservedReader(io.FileIO(self.path, "r"), lambda *args: None)
        with mock.patch.object(m.Path, "open", return_value=reader), \
                mock.patch.object(reader, "readinto", side_effect=OSError("injected read failure")):
            with self.assertRaisesRegex(OSError, "injected read failure"):
                m.sha256_file(self.path)
        self.assertTrue(reader.handle.closed)


if __name__ == "__main__":
    unittest.main()
