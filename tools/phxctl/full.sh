#!/bin/bash
# full.sh <mesboot step>: power the GPU up (bringup5.sh), open the doorbells, unhalt the CP and start MES with the GART,
# then run one mesboot step with its options from the environment (phxboot: MC=1 CS=1 ADOPT=1 GFX=1 AG=1 ... kiqsched).
# Run as root (phxboot) or as a user with sudo. A reboot is armed for 4 minutes in case the GPU hangs the bus.
set -e
set -o pipefail
SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo
# Retain initializer stderr in phxboot's log even when stdout is filtered.
if bash ~/gpu/bringup5.sh >/dev/null; then :; else
    rc=$?
    echo "upstream34-full: bringup5.sh failed with status $rc; GPU queue initialization not started" >&2
    exit "$rc"
fi
if [ -z "${PHX34_WATCHDOG_ACK:-}" ]; then
    $SUDO bash -c "nohup shutdown -r +4 >/dev/null 2>&1 &"
else
    [ -f "$PHX34_WATCHDOG_ACK" ] || exit 75
fi
$SUDO ~/gpu/phxctl/phxctl wreg 0xDE0 1 | tail -1
$SUDO ~/gpu/phxctl/phxctl wreg 0xA802 0 | tail -1
$SUDO ~/gpu/phxctl/phxctl wreg 0xA803 0x01000000 | tail -1
$SUDO ~/gpu/phxctl/mesboot gart
$SUDO ~/gpu/phxctl/mesboot mes
$SUDO env MESBOOT_MC=$MC MESBOOT_CS=$CS MESBOOT_VMT=$VMT PTE_SYS=$PS PTE_NOFB=$NF FAULT_DEFAULT=$FD PT_SYS=$PTS VARONLY=$VAR PTE_EXTRA=$PX ROOT_FL=$RF AGPTEST=$AGP CTX0_OFF=$C0 VM8=$V8 VM8_MT=$VMT8 IB0=$IB0 VM8_FLAT=$FLAT VM8_SYS=$VSYS ADOPT=$ADOPT MESBOOT_GFX=$GFX ADOPT_GFX=$AG VM8_IBSYS=$IBSYS VM8_HI=$VHI ~/gpu/phxctl/mesboot "$1" 2>&1 | tail -12
if [ -z "${PHX34_WATCHDOG_ACK:-}" ]; then
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
