import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import allocation_source_packet as packet


class SourcePacketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'repository'
        self.root.mkdir()
        self.env = {**os.environ, 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull}
        self.git('init', '-b', packet.BRANCH)
        self.git('config', 'user.name', 'Source Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('config', 'core.hooksPath', str(self.root / '.git/no-hooks'))
        for name in packet.SOURCE_PATHS:
            source, target = ROOT / name, self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
        # This temporary repository supplies a synthetic review commit, not the real
        # historical review. Keep its positive fixture on the exporter's fixed build 37
        # without requiring historical Git objects in shallow CI checkouts.
        kernel = self.root / 'src/phxbringup/PhxBringup.cpp'
        source, replacements = re.subn(r'^#define PHX_KEXT_BUILD [0-9]+u$',
                                       '#define PHX_KEXT_BUILD 37u', kernel.read_text(), flags=re.M)
        self.assertEqual(replacements, 1)
        kernel.write_text(source)
        self.commit()
        self.reviewed = self.head()
        self.out = self.root / 'build/packet'

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], env=self.env,
                                       stderr=subprocess.PIPE, timeout=30)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'Synthetic source input')

    def head(self):
        return self.git('rev-parse', 'HEAD').decode().strip()

    def export(self, **kwargs):
        return packet.export_packet(kwargs.pop('out', self.out), kwargs.pop('commit', self.head()),
                                    self.root, reviewed=kwargs.pop('reviewed', self.reviewed), **kwargs)

    def test_synthetic_reviewed_export_matches_git_blobs_modes_checksums_and_limits(self):
        result = self.export()
        self.assertTrue(result['source_only'])
        self.assertFalse(result['target_binary_included'])
        self.assertEqual(self.git('status', '--porcelain').strip(), b'')
        self.assertEqual(stat.S_IMODE(self.out.stat().st_mode), 0o700)
        self.assertEqual({p.name for p in self.out.iterdir()},
                         {'nullarc-allocation-source.tar.gz', 'source-manifest.json', 'SHA256SUMS'})
        for path in self.out.iterdir():
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        for line in (self.out / 'SHA256SUMS').read_text().splitlines():
            sha, name = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((self.out / name).read_bytes()).hexdigest(), sha)
        manifest = json.loads((self.out / 'source-manifest.json').read_text())
        self.assertEqual(manifest['source_commit'], self.head())
        self.assertTrue(all(value is False for value in manifest['limits'].values()))
        self.assertEqual(manifest['external_build_inputs']['MacKernelSDK_commit'], packet.SDK)
        self.assertNotIn(str(self.root), json.dumps(manifest))
        with tarfile.open(fileobj=io.BytesIO(gzip.decompress(
                (self.out / 'nullarc-allocation-source.tar.gz').read_bytes()))) as archive:
            files = {m.name.removeprefix('nullarc/'): m for m in archive if m.isfile()}
            self.assertEqual(set(files), set(manifest['files']))
            self.assertFalse(any(p.startswith(('src/phxaccel/', 'src/nmplugin/', 'fw/')) for p in files))
            for name, info in manifest['files'].items():
                content = archive.extractfile(files[name]).read()
                self.assertEqual(packet.blob_id(content), info['git_blob'])
                self.assertEqual(hashlib.sha256(content).hexdigest(), info['sha256'])
                self.assertEqual(files[name].mode, int(info['git_mode'], 8) & 0o777)

    def test_export_is_repeatable_and_only_invokes_git_reads(self):
        real_run = subprocess.run
        calls = []
        def guarded(args, **kwargs):
            self.assertEqual(args[0], 'git')
            self.assertFalse(kwargs.get('shell', False))
            verbs = args[3:]
            if verbs[0] == '-c':
                verbs = verbs[2:]
            self.assertIn(verbs[0], ('rev-parse', 'branch', 'status', 'ls-tree', 'archive'))
            calls.append(verbs[0])
            return real_run(args, **kwargs)
        with patch.object(packet.subprocess, 'run', side_effect=guarded):
            first = self.export()
            second_out = self.root / 'build/second'
            second = self.export(out=second_out)
        self.assertTrue(calls)
        self.assertEqual(first, second)
        for name in ('nullarc-allocation-source.tar.gz', 'source-manifest.json', 'SHA256SUMS'):
            self.assertEqual((self.out / name).read_bytes(), (second_out / name).read_bytes())

    def test_exact_head_and_full_commit_are_required(self):
        with self.assertRaisesRegex(packet.PacketError, 'exact full commit'):
            self.export(commit=self.head()[:12])
        old = self.head()
        (self.root / 'extra.txt').write_text('unrelated committed text')
        self.commit()
        with self.assertRaisesRegex(packet.PacketError, 'HEAD does not match'):
            self.export(commit=old)
        self.assertFalse(self.out.exists())

    def test_wrong_branch_is_refused(self):
        self.git('switch', '-c', 'different-branch')
        with self.assertRaisesRegex(packet.PacketError, 'Unexpected branch'):
            self.export()

    def test_dirty_or_untracked_source_is_refused(self):
        source = self.root / 'tools/allocation_snapshot.cpp'
        original = source.read_bytes()
        source.write_bytes(original + b'\n')
        with self.assertRaisesRegex(packet.PacketError, 'not clean'):
            self.export()
        source.write_bytes(original)
        (self.root / 'private-input.txt').write_text('not exported')
        with self.assertRaisesRegex(packet.PacketError, 'not clean'):
            self.export()
        self.assertFalse(self.out.exists())

    def test_changed_core_and_notices_require_new_review(self):
        for name in ('tools/allocation_snapshot.cpp', 'docs/kext-notices/Navi48-BSD-3-Clause.txt'):
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b'\n')
            self.commit()
            with self.assertRaisesRegex(packet.PacketError, 'changed since reviewed snapshot'):
                self.export()
            path.write_bytes(original)
            self.commit()

    def test_existing_output_and_output_outside_build_are_refused(self):
        self.export()
        before = (self.out / 'SHA256SUMS').read_bytes()
        with self.assertRaisesRegex(packet.PacketError, 'already exists'):
            self.export()
        self.assertEqual((self.out / 'SHA256SUMS').read_bytes(), before)
        with self.assertRaisesRegex(packet.PacketError, 'direct child'):
            self.export(out=self.root.parent / 'outside')

    def test_symlinked_build_parent_is_refused(self):
        ignore = self.root / '.gitignore'
        ignore.write_text(ignore.read_text() + '\nbuild\n')
        self.commit()
        (self.root / 'build').symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaisesRegex(packet.PacketError, 'Symlink'):
            self.export()

    def test_symlinked_committed_source_is_refused(self):
        path = self.root / 'docs/ALLOCATION-SOURCE-PACKET.md'
        path.unlink()
        path.symlink_to('/not-read-by-exporter')
        self.commit()
        with self.assertRaisesRegex(packet.PacketError, 'Non-regular'):
            self.export()
        self.assertFalse(self.out.exists())

    def test_binary_or_non_utf8_source_is_refused(self):
        path = self.root / 'docs/ALLOCATION-SOURCE-PACKET.md'
        for content, message in ((b'private\0payload', 'Binary content'), (b'\xff', 'UTF-8')):
            path.write_bytes(content)
            self.commit()
            with self.assertRaisesRegex(packet.PacketError, message):
                self.export()
        self.assertFalse(self.out.exists())

    def test_missing_required_source_is_refused(self):
        (self.root / 'tools/allocation_source_packet.py').unlink()
        self.commit()
        with self.assertRaisesRegex(packet.PacketError, 'Required source or notice missing'):
            self.export()

    def test_archive_export_ignore_is_not_silent(self):
        (self.root / '.gitattributes').write_text('src/phxbringup/Info.plist export-ignore\n')
        self.commit()
        with self.assertRaisesRegex(packet.PacketError, 'omitted a committed source'):
            self.export()

    def test_archive_export_subst_is_not_silent(self):
        (self.root / '.gitattributes').write_text('docs/ALLOCATION-SOURCE-PACKET.md export-subst\n')
        (self.root / 'docs/ALLOCATION-SOURCE-PACKET.md').write_text('$Format:%H$\n')
        self.commit()
        with self.assertRaisesRegex(packet.PacketError, 'differs from committed blob'):
            self.export()

    def test_missing_quoted_include_is_refused_even_at_reviewed_commit(self):
        path = self.root / 'tools/allocation_snapshot.cpp'
        path.write_text(path.read_text() + '\n#include "missing-diagnostic-header.h"\n')
        self.commit()
        with self.assertRaisesRegex(packet.PacketError, 'Missing quoted include'):
            self.export(reviewed=self.head())

    def test_wrong_sdk_pin_is_refused_even_at_reviewed_commit(self):
        path = self.root / 'upstream.lock.json'
        lock = json.loads(path.read_text())
        lock['MacKernelSDK']['commit'] = '0' * 40
        path.write_text(json.dumps(lock))
        self.commit()
        with self.assertRaisesRegex(packet.PacketError, 'Unreviewed SDK pin'):
            self.export(reviewed=self.head())

    def test_new_kernel_build_does_not_reuse_build37_review(self):
        path = self.root / 'src/phxbringup/PhxBringup.cpp'
        original = path.read_text()
        self.assertIn('#define PHX_KEXT_BUILD 37u', original)
        path.write_text(original.replace('#define PHX_KEXT_BUILD 37u', '#define PHX_KEXT_BUILD 38u'))
        self.commit()
        with self.assertRaisesRegex(packet.PacketError, 'changed since reviewed snapshot'):
            self.export()
        with self.assertRaisesRegex(packet.PacketError, 'Not reviewed build37 source'):
            self.export(reviewed=self.head())
        self.assertFalse(self.out.exists())

    def test_checkout_change_during_export_is_refused_before_output(self):
        original = packet.checked_archive
        def changed(*args):
            data = original(*args)
            path = self.root / 'tools/allocation_snapshot.cpp'
            path.write_bytes(path.read_bytes() + b'\n')
            return data
        with patch.object(packet, 'checked_archive', side_effect=changed):
            with self.assertRaisesRegex(packet.PacketError, 'changed during export'):
                self.export()
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
