"""CPU-only source/archive/identity checks; never build, load or run a driver."""
import io
from pathlib import Path
import struct
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from upstream34_layout import ring_padding_candidate as p


def archive(extra=(), omit=()):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as tar:
        for name in ['LICENSE.txt', 'Headers/IOKit/IOService.h',
                     'Library/x86_64/libkmod.a']:
            if name in omit:
                continue
            item = tarfile.TarInfo(name); item.size = 1
            tar.addfile(item, io.BytesIO(b'x'))
        for item in extra:
            tar.addfile(item, io.BytesIO(b''))
    return stream.getvalue()


def image(commands=None, cpu=0x1000007, kind=11):
    if commands is None:
        commands = [struct.pack('<II16s', 0x1b, 24, bytes(range(16)))]
    blob = b''.join(commands)
    return struct.pack('<8I', 0xfeedfacf, cpu, 3, kind, len(commands), len(blob), 0, 0) + blob


class CandidateTests(unittest.TestCase):
    def test_exact_full_driver_and_source_proposal(self):
        original = (ROOT / p.DRIVER).read_bytes()
        candidate = p.candidate_source(original)
        self.assertEqual(p.sha(candidate), p.CANDIDATE_SHA)
        self.assertEqual((ROOT / p.DRIVER).read_bytes(), original)
        self.assertIn(b'#define PHX_KEXT_BUILD 34u', candidate)

    def test_source_drift_and_reapplication_refused(self):
        original = (ROOT / p.DRIVER).read_bytes()
        for data in (original + b'\n', original.replace(b'34u', b'42u', 1), p.candidate_source(original)):
            with self.assertRaises(ValueError): p.candidate_source(data)

    def test_packaged_metadata_matches_original_control(self):
        source = (ROOT / 'src/phxbringup/Info.plist').read_bytes()
        result = p.control_metadata(source)
        self.assertEqual(p.sha(result), p.CONTROL_PLIST_SHA)
        self.assertEqual((ROOT / 'src/phxbringup/Info.plist').read_bytes(), source)
        self.assertEqual(result, source.replace(b'0x19001002 0x15bf1002 0x15c81002 0x164e1002', b'0x19001002'))

    def test_metadata_drift_and_reapplication_refused(self):
        source = (ROOT / 'src/phxbringup/Info.plist').read_bytes()
        for data in [source + b'\n', source.replace(b'1.0.0', b'1.0.1'), p.control_metadata(source)]:
            with self.assertRaises(ValueError): p.control_metadata(data)

    def test_archive_complete(self):
        self.assertEqual(len(p.archive_inputs(archive())), 3)

    def test_archive_path_traversal_and_unapproved_roots_refused(self):
        for name in ['/tmp/a', '../a', 'Headers/../../a', './Headers/a', 'Library/arm64/a', '.git/config']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                p.archive_inputs(archive([tarfile.TarInfo(name)]))

    def test_archive_links_and_special_files_refused(self):
        for kind in [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]:
            item = tarfile.TarInfo('Headers/link'); item.type = kind; item.linkname = '../outside'
            with self.subTest(kind=kind), self.assertRaises(ValueError): p.archive_inputs(archive([item]))

    def test_archive_duplicates_and_missing_inputs_refused(self):
        with self.assertRaises(ValueError): p.archive_inputs(archive([tarfile.TarInfo('LICENSE.txt')]))
        with self.assertRaises(ValueError): p.archive_inputs(archive(omit=['Library/x86_64/libkmod.a']))

    def test_sdk_ancestor_repository_is_refused(self):
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(p.subprocess, 'check_output', return_value=str(ROOT).encode()) as git:
            with self.assertRaises(ValueError): p.sdk_inputs(directory)
            self.assertEqual(git.call_count, 1)

    def test_sdk_pin_dirty_modes_and_object_mismatch_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            for fault in ['pin', 'dirty', 'mode', 'object']:
                def git(argv, **kwargs):
                    if argv[1:3] == ['rev-parse', '--show-toplevel']:
                        return str(Path(directory).resolve()).encode()
                    if argv[1:3] == ['rev-parse', 'HEAD']:
                        return (('0' * 40) if fault == 'pin' else p.SDK_PIN).encode()
                    if argv[1] == 'status': return b' M Headers/a' if fault == 'dirty' else b''
                    if argv[1] == 'archive': return archive()
                    if argv[1] == 'ls-tree':
                        mode = '100755' if fault == 'mode' else '100644'
                        return (mode + ' blob ' + '0' * 40 + '\tLICENSE.txt\0').encode()
                    raise AssertionError('Unexpected Git operation')
                with self.subTest(fault=fault), mock.patch.object(p.subprocess, 'check_output', side_effect=git):
                    with self.assertRaises(ValueError): p.sdk_inputs(directory)

    def test_candidate_macho_identity(self):
        identity = p.macho_identity(image())
        self.assertEqual(identity['architecture'], 'x86_64')
        self.assertEqual(identity['filetype'], 'MH_KEXT_BUNDLE')
        self.assertEqual(len(identity['binary_sha256']), 64)

    def test_non_kext_and_wrong_architecture_refused(self):
        for data in [b'', image(cpu=0x100000c), image(kind=2), image()[:-1]]:
            with self.assertRaises(ValueError): p.macho_identity(data)

    def test_missing_duplicate_and_zero_image_identities_refused(self):
        command = struct.pack('<II16s', 0x1b, 24, bytes(range(16)))
        for commands in [[], [command, command], [struct.pack('<II16s', 0x1b, 24, bytes(16))]]:
            with self.assertRaises(ValueError): p.macho_identity(image(commands))

    def test_invalid_command_lengths_refused(self):
        for command in [struct.pack('<II', 0x1b, 0), struct.pack('<II', 0x1b, 16),
                        struct.pack('<II', 0x1b, 12) + bytes(4)]:
            with self.assertRaises(ValueError): p.macho_identity(image([command]))

    def test_bundle_links_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'a').write_bytes(b'a')
            self.assertEqual(p.tree_files(root), {'a': p.sha(b'a')})
            (root / 'b').symlink_to(root / 'a')
            with self.assertRaises(ValueError): p.tree_files(root)

    def test_destination_and_platform_refused_before_source_or_build(self):
        with mock.patch.object(p.platform, 'system', return_value='Darwin'), \
                mock.patch.object(p.platform, 'machine', return_value='x86_64'), \
                mock.patch.object(p.mec_range, 'protected_base_inputs') as source:
            for path in ['/Library/Extensions/candidate.kext', str(ROOT)]:
                with self.assertRaises(ValueError): p.build(path, '/unused')
            source.assert_not_called()
        with mock.patch.object(p.platform, 'system', return_value='Linux'):
            with self.assertRaises(RuntimeError): p.build('/unused', '/unused')


if __name__ == '__main__':
    unittest.main()
