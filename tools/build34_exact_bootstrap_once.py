# SPDX-License-Identifier: MIT
"""Derive the one-attempt-per-boot full.sh for the contained R3 startup."""

from build34_exact_submit import once


GATE = r'''# Reserve before bringup5.sh: its writes are outside mesboot's adoption gate.
phx34_reserve_bootstrap() (
    export LC_ALL=C
    local state=/private/var/db/phx34-r3-bootstrap boot
    # The scope installer must provision this dedicated directory once, under /private/var/db.
    cd -P -- "$state" && [ "$PWD" = "$state" ] || return 1
    [ "$(/usr/bin/stat -f '%u:%Lp' .)" = '0:700' ] || return 1
    boot=$(/usr/sbin/sysctl -n kern.bootsessionuuid) || return 1
    [[ $boot =~ ^[[:xdigit:]]{8}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{4}-[[:xdigit:]]{12}$ ]] || return 1
    boot=$(printf '%s' "$boot" | /usr/bin/tr 'A-F' 'a-f') || return 1
    # Atomic across workers; keep the reservation even after a failure or signal.
    /bin/mkdir -m 700 -- "$boot"
)
if [ "$(/usr/bin/id -u)" != 0 ] || [ "$#" != 1 ] || [ "$1" != kiqsched ] ||
    [ "$MC:$CS:$ADOPT:$GFX:$AG" != 1:1:1:1:1 ] ||
    { [ -n "${NO_CSB:-}" ] && [ "${NO_CSB:0:1}" != 0 ]; } ||
    [ ! -f "${PHX34_WATCHDOG_ACK:-}" ]; then
    echo 'build34 R3: checked, externally supervised bootstrap required' >&2
    exit 75
fi
if ! phx34_reserve_bootstrap 2>/dev/null; then
    echo 'build34 R3: boot reservation unavailable or consumed; GPU initialization skipped' >&2
    exit 75
fi
SUDO=""
'''

WATCHDOG = '''if [ -z "${PHX34_WATCHDOG_ACK:-}" ]; then
    $SUDO bash -c "nohup shutdown -r +4 >/dev/null 2>&1 &"
else
    [ -f "$PHX34_WATCHDOG_ACK" ] || exit 75
fi
'''

BRINGUP_WATCHDOG = '''if [ -z "${PHX34_WATCHDOG_ACK:-}" ]; then
    echo "== watchdog: reboot in 3 min unless cancelled =="
    $SUDO bash -c 'nohup shutdown -r +3 >/dev/null 2>&1 &'
else
    [ -f "$PHX34_WATCHDOG_ACK" ] || exit 75
fi
'''

REQUIRE_SUPERVISION = 'if [ ! -f "${PHX34_WATCHDOG_ACK:-}" ]; then exit 75; fi\n'

CANCEL = r'''if [ -z "${PHX34_WATCHDOG_ACK:-}" ]; then
    if watchdog_output=$($SUDO env LC_ALL=C killall shutdown 2>&1); then
        echo "upstream34-watchdog: shutdown timer cancelled" >&2
    else
        rc=$?
        if [ "$rc" -eq 1 ] && [ "$watchdog_output" = "No matching processes were found" ]; then
            echo "upstream34-watchdog: no shutdown timer remains" >&2
        else
            printf 'upstream34-watchdog: cancellation failed with status %s: %s\n' "$rc" "$watchdog_output" >&2
            exit "$rc"
        fi
    fi
fi
'''


def stage_full(source):
    source = once(source, '# Run as root (phxboot) or as a user with sudo. A reboot is armed for 4 minutes in case the GPU hangs the bus.\n',
                  '# R3 scope: root startup with external supervision only.\n')
    source = once(source, 'SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo\n', GATE)
    source = once(source, WATCHDOG, REQUIRE_SUPERVISION)
    return once(source, CANCEL, '')


def stage_bringup(source):
    source = once(source, '# A reboot is armed for 3 minutes in case the PSP hangs and cancelled at the end.\n',
                  '# R3 scope: recovery power actions belong to the external supervisor.\n')
    source = once(source, BRINGUP_WATCHDOG, REQUIRE_SUPERVISION)
    return once(source, CANCEL, '')
