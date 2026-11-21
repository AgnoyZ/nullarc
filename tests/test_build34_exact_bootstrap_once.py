# SPDX-License-Identifier: MIT
"""Run the staged shell guards with real mkdir and synthetic startup commands."""

import hashlib
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build34_exact_bootstrap_once import stage_bringup, stage_full
from build34_exact_submit import once


FULL = ROOT / 'tools/phxctl/full.sh'
BRINGUP = ROOT / 'tools/phxctl/bringup5.sh'
PINNED = ('36f5c8a01773a3687e6b633c5b0b5e1b3b2031329c5a2065b669b27c45cf0a71',
          'a0906cceab45f747a1b89d5c75972463e52071b05ae1e6a6c71fac1d207b771d')


class BootstrapOnceTests(unittest.TestCase):
    def script(self, path, body):
        path.write_text('#!/bin/bash\n' + body)
        path.chmod(0o700)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='build34-once-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.state = self.root / 'boot state'
        self.state.mkdir(mode=0o700)
        self.trace = self.root / 'trace'
        self.trace.touch()
        self.ack = self.root / 'ack'
        self.ack.touch()
        self.full = self.root / 'full.sh'
        self.gpu = self.root / 'gpu'
        ctl = self.gpu / 'phxctl'
        ctl.mkdir(parents=True)
        self.boot = str(uuid.uuid4())  # deliberately independent of the host boot
        self.env = dict(PATH='/usr/bin:/bin', HOME=str(self.root), TRACE=str(self.trace), LC_ALL='C', BOOT=self.boot,
                        PHX34_WATCHDOG_ACK=str(self.ack), MC='1', CS='1', ADOPT='1', GFX='1', AG='1')
        full = stage_full(FULL.read_text())
        sysctl = self.root / 'sysctl-double'
        user = self.root / 'id-double'
        self.script(sysctl, '''[ "$*" = '-n kern.bootsessionuuid' ] || exit 100
if [ -n "${SYSCTL_ERROR:-}" ]; then exit 1; fi
printf '%s\n' "$BOOT"
''')
        self.script(user, 'printf "%s\\n" "${FAKE_UID:-0}"\n')
        for old, new in [('state=/private/var/db/phx34-r3-bootstrap', 'state=' + shlex.quote(str(self.state))),
                         ("= '0:700'", f"= '{os.geteuid()}:700'"), ('/usr/sbin/sysctl', shlex.quote(str(sysctl))),
                         ('/usr/bin/id', shlex.quote(str(user)))]:
            full = once(full, old, new)
        self.full.write_text(full)
        self.script(self.gpu / 'bringup5.sh', '''printf 'bringup\n' >> "$TRACE"
if [ -n "${REMOVE_ACK:-}" ]; then /bin/rm -- "$PHX34_WATCHDOG_ACK"; fi
if [ -n "${KILL_STARTUP:-}" ]; then kill -KILL "$PPID"; exit 0; fi
exit "${BRINGUP_STATUS:-0}"
''')
        self.script(ctl / 'phxctl', 'printf "phxctl %s\\n" "$*" >> "$TRACE"\n')
        self.script(ctl / 'mesboot', '''printf 'mesboot %s\n' "$*" >> "$TRACE"
if [ "$1" = kiqsched ]; then
    [ "$MESBOOT_MC:$MESBOOT_CS:$ADOPT:$MESBOOT_GFX:$ADOPT_GFX" = 1:1:1:1:1 ] || exit 99
    exit "${MES_STATUS:-0}"
fi
''')

    def launch(self, *args, **env):
        return subprocess.run(['/bin/bash', str(self.full), *args], env={**self.env, **env},
                              cwd=self.root, capture_output=True, timeout=8)

    def invoked(self):
        return self.trace.read_text().splitlines()

    def test_sources_and_supervision(self):
        for path, pin, stage in zip((FULL, BRINGUP), PINNED, (stage_full, stage_bringup)):
            with self.subTest(path=path.name):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), pin)
                source = stage(path.read_text())
                self.assertNotIn('shutdown', source)
                self.assertNotIn('killall', source)
                self.assertIn('PHX34_WATCHDOG_ACK', source)
                subprocess.run(['/bin/bash', '-n'], input=source.encode(), check=True, timeout=8)

    def test_exact_startup_and_new_boot(self):
        self.assertEqual(self.launch('kiqsched').returncode, 0)
        expected = ['bringup', 'phxctl wreg 0xDE0 1', 'phxctl wreg 0xA802 0', 'phxctl wreg 0xA803 0x01000000',
                    'mesboot gart', 'mesboot mes', 'mesboot kiqsched']
        self.assertEqual(self.invoked(), expected)
        refused = self.launch('kiqsched', BOOT=self.boot.upper())
        self.assertEqual(refused.returncode, 75)
        self.assertNotIn(self.boot.encode(), refused.stderr.lower())
        self.assertEqual(self.invoked(), expected)
        self.assertEqual((self.state / self.boot).stat().st_mode & 0o777, 0o700)
        second_boot = str(uuid.uuid4())
        self.assertEqual(self.launch('kiqsched', BOOT=second_boot).returncode, 0)
        self.assertEqual(self.invoked(), expected * 2)
        self.assertEqual(set(p.name for p in self.state.iterdir()), {self.boot, second_boot})

    def test_concurrent_workers(self):
        args = ['/bin/bash', str(self.full), 'kiqsched']
        with subprocess.Popen(args, env=self.env, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as a:
            with subprocess.Popen(args, env=self.env, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as b:
                a.communicate(timeout=8)
                b.communicate(timeout=8)
                self.assertEqual(sorted([a.returncode, b.returncode]), [0, 75])
        self.assertEqual(self.invoked().count('bringup'), 1)
        self.assertEqual(self.invoked().count('mesboot kiqsched'), 1)

    def test_initializer_failure_consumes_boot(self):
        self.assertEqual(self.launch('kiqsched', BRINGUP_STATUS='74').returncode, 74)
        self.assertEqual(self.launch('kiqsched').returncode, 75)
        self.assertEqual(self.invoked(), ['bringup'])

    def test_partial_queue_setup_consumes_boot(self):
        self.assertEqual(self.launch('kiqsched', MES_STATUS='74').returncode, 74)
        self.assertEqual(self.launch('kiqsched').returncode, 75)
        self.assertEqual(self.invoked().count('mesboot kiqsched'), 1)

    def test_interruption_consumes_boot(self):
        self.assertEqual(self.launch('kiqsched', KILL_STARTUP='1').returncode, -signal.SIGKILL)
        self.assertEqual(self.launch('kiqsched').returncode, 75)
        self.assertEqual(self.invoked(), ['bringup'])

    def test_refuses_missing_or_lost_supervision(self):
        self.assertEqual(self.launch('kiqsched', PHX34_WATCHDOG_ACK='').returncode, 75)
        self.assertEqual(list(self.state.iterdir()), [])
        self.assertEqual(self.launch('kiqsched', REMOVE_ACK='1').returncode, 75)
        self.assertEqual(self.invoked(), ['bringup'])
        self.ack.touch()
        self.assertEqual(self.launch('kiqsched').returncode, 75)
        self.assertEqual(self.invoked(), ['bringup'])

    def test_no_device_work_for_wrong_scope_or_boot(self):
        for args, env in [((), {}), (('kiqsched', 'extra'), {}), (('mes',), {}), (('kiqsched',), {'FAKE_UID': '501'}),
                          (('kiqsched',), {'ADOPT': '0'}), (('kiqsched',), {'NO_CSB': '1'}), (('kiqsched',), {'GFX': ''}),
                          (('kiqsched',), {'BOOT': '../invalid'}), (('kiqsched',), {'BOOT': self.boot + '\nextra'}),
                          (('kiqsched',), {'BOOT': ''}), (('kiqsched',), {'SYSCTL_ERROR': '1'})]:
            with self.subTest(args=args, env=tuple(env)):
                self.assertEqual(self.launch(*args, **env).returncode, 75)
        self.assertEqual(self.invoked(), [])
        self.assertEqual(list(self.state.iterdir()), [])

    def test_bad_reservation_directory_fails_closed(self):
        self.state.chmod(0o755)
        self.assertEqual(self.launch('kiqsched').returncode, 75)
        self.state.rmdir()
        self.assertEqual(self.launch('kiqsched').returncode, 75)
        target = self.root / 'actual'
        target.mkdir(mode=0o700)
        self.state.symlink_to(target, target_is_directory=True)
        self.assertEqual(self.launch('kiqsched').returncode, 75)
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(self.invoked(), [])


    def test_staged_bringup_checks_layout_and_supervision_before_writes(self):
        bringup = stage_bringup(BRINGUP.read_text())
        # Keep its command order and admission logic, replacing the transport and sleep.
        bringup = once(bringup, 'SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo\n', '')
        bringup = once(bringup, 'P(){ $SUDO ~/gpu/phxctl/phxctl "$@"; }\n', '''P() {
    printf '%s\n' "$1" >> "$TRACE"
    case "$1" in
        layout) printf '%s\n' "$LAYOUT" ;;
        loadfw) echo loadfw ;;
    esac
}
''')
        bringup = once(bringup, 'sleep 2\n', '')
        script = self.root / 'staged-bringup.sh'
        script.write_text(bringup)
        for layout, ack, status, expected in [
            ('1 2 3 4 5', str(self.ack), 75, ['layout']),
            ('1 2 3 4 5 6', '', 75, ['layout']),
            ('1 2 3 4 5 6', str(self.ack), 0, ['layout', 'psp', 'psp', 'stage', 'raw', 'raw'] +
             ['loadfw'] * 17 + ['autoload', 'smu', 'smu', 'smu', 'regs']),
        ]:
            with self.subTest(layout=layout, supervised=bool(ack)):
                self.trace.write_text('')
                result = subprocess.run(['/bin/bash', str(script)], cwd=self.root, capture_output=True, timeout=8,
                                        env={**self.env, 'LAYOUT': layout, 'PHX34_WATCHDOG_ACK': ack})
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(self.invoked(), expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
