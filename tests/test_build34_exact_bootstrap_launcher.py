# SPDX-License-Identifier: MIT
"""Exercise the derived launcher fragment with only synthetic commands."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build34_exact_bootstrap_launcher import CHECKED, LEGACY, stage_launcher

LAUNCHER = ROOT / 'tools/phxctl/phxboot.sh'
FULL = ROOT / 'tools/phxctl/full.sh'
BEGIN = 'apps_only\n'
END = '# no BO cache flushing per submit/wait'
FULL_TAIL = '"$1" 2>&1 | tail -12\n'


class Build34BootstrapLauncherTests(unittest.TestCase):
    def setUp(self):
        self.source = LAUNCHER.read_text()
        self.checked = stage_launcher(self.source)
        self.tmp = tempfile.TemporaryDirectory(prefix='build34-launcher-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.gpu = self.root / 'gpu path with spaces'
        ctl = self.gpu / 'phxctl'
        ctl.mkdir(parents=True)
        self.full = self.gpu / 'full.sh'
        self.full.write_text('''#!/bin/bash
set -e
set -o pipefail
"$G/phxctl/mesboot" "$1" 2>&1 | tail -12
''')
        mesboot = ctl / 'mesboot'
        mesboot.write_text('''#!/bin/bash
printf '%s\\n' "$1" >> "$TRACE"
case "$1" in
    kiqsched)
        [ "$MC$CS$ADOPT$GFX$AG" = 11111 ] || exit 99
        printf '%s\\n' "$BOOT_OUTPUT"
        exit "$BOOT_STATUS" ;;
    claim) exit "$CLAIM_STATUS" ;;
    *) exit 98 ;;
esac
''')
        mesboot.chmod(0o700)

    def launch(self, *, boot=0, claim=0, output='adopt compute queue', legacy=False, strict=False):
        fragment = (self.source if legacy else self.checked).split('\n' + BEGIN)[1].split(END)[0]
        trace = self.root / 'trace'
        trace.write_text('')
        gpu = self.gpu
        if legacy:
            # The predecessor uses unquoted paths. Isolate its status handling.
            gpu = self.root / 'gpu'
            if not gpu.is_symlink():
                gpu.symlink_to(self.gpu, target_is_directory=True)
        env = dict(PATH='/usr/bin:/bin', G=str(gpu), TRACE=str(trace), BOOT_STATUS=str(boot),
                   CLAIM_STATUS=str(claim), BOOT_OUTPUT=output, LC_ALL='C')
        args = ['/bin/bash', '-e', '-o', 'pipefail'] if strict else ['/bin/bash']
        run = subprocess.run([*args, '-c', fragment + 'printf "post-claim\\n" >> "$TRACE"\n'],
                             cwd=self.root, env=env, capture_output=True, text=True, timeout=5)
        return run, trace.read_text().splitlines()

    def test_exact_two_line_replacement_and_syntax(self):
        self.assertEqual(self.checked.replace(CHECKED, LEGACY), self.source)
        self.assertIn('set -o pipefail\n', FULL.read_text())
        self.assertIn(FULL_TAIL, FULL.read_text())
        subprocess.run(['/bin/bash', '-n'], input=self.checked, text=True, check=True, timeout=5)
        subprocess.run(['/bin/bash', '-n'], input=self.checked.split('# A GPU hang leaves WindowServer')[0],
                       text=True, check=True, timeout=5)

    def test_unknown_duplicate_or_already_staged_input_refuses(self):
        for mismatched in (self.source.replace('mesboot claim', 'mesboot dump'), self.source + '\n' + LEGACY,
                           self.checked, self.source.replace('#!/bin/bash', '#!/bin/sh')):
            with self.subTest(), self.assertRaises(ValueError):
                stage_launcher(mismatched)

    def test_predecessor_claims_after_failed_second_adoption(self):
        run, trace = self.launch(boot=74, legacy=True)
        self.assertEqual((run.returncode, trace), (0, ['kiqsched', 'claim', 'post-claim']))

    def test_failed_bootstrap_never_claims(self):
        for status in (74, 75, 127):
            for output in ('adopt compute queue', '', 'unmatched'):
                with self.subTest(status=status, output=output):
                    run, trace = self.launch(boot=status, output=output)
                    self.assertEqual((run.returncode, trace), (status, ['kiqsched']))
                    self.assertIn('accelerator claim skipped', run.stderr)

    def test_claim_failure_cannot_continue_desktop_configuration(self):
        run, trace = self.launch(claim=74)
        self.assertEqual((run.returncode, trace), (74, ['kiqsched', 'claim']))
        self.assertIn('accelerator claim failed', run.stderr)

    def test_logging_filter_cannot_veto_success(self):
        for strict in (False, True):
            for output, visible in (('adopt gfx queue', 'adopt gfx queue\n'), ('unmatched', ''), ('', '')):
                with self.subTest(strict=strict, output=output):
                    run, trace = self.launch(output=output, strict=strict)
                    self.assertEqual((run.returncode, trace), (0, ['kiqsched', 'claim', 'post-claim']))
                    self.assertEqual((run.stdout, run.stderr), (visible, ''))


if __name__ == '__main__':
    unittest.main()
