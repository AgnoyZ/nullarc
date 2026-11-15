#!/bin/bash
# Phoenix GFX power-up in the Linux driver's order: PSP ring, TOC and TMR, the firmware of every engine through
# LOAD_IP_FW, RLC autoload, then the SMU messages that switch GFX on (EnableGfxImu with 1). Firmware from ~/gpu/fw at
# the offsets and sizes of linux-firmware's gc_11_0_1/psp_13_0_4 files. Run as root (phxboot) or as a user with sudo.
# A reboot is armed for 3 minutes in case the PSP hangs and cancelled at the end.
set -eu
set -o pipefail
SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo
P(){ $SUDO ~/gpu/phxctl/phxctl "$@"; }
# Original build-34 metadata/ABI admission precedes the watchdog or first hardware write.
layout=$(P layout)
read -r TOC_LO TOC_HI TMR_LO TMR_HI TMR_PA_LO TMR_PA_HI extra <<< "$layout"
[ -z "$extra" ] || exit 75
for value in "$TOC_LO" "$TOC_HI" "$TMR_LO" "$TMR_HI" "$TMR_PA_LO" "$TMR_PA_HI"; do
    case "$value" in ''|*[!0-9]*) echo "invalid target layout" >&2; exit 75;; esac
done
if [ -z "${PHX34_WATCHDOG_ACK:-}" ]; then
    echo "== watchdog: reboot in 3 min unless cancelled =="
    $SUDO bash -c 'nohup shutdown -r +3 >/dev/null 2>&1 &'
else
    [ -f "$PHX34_WATCHDOG_ACK" ] || exit 75
fi
P psp destroy >/dev/null 2>&1
P psp create 0x1100000 >/dev/null
P stage ~/gpu/fw/psp_13_0_4_toc.bin 256 2304 0x0 >/dev/null
P raw 0x20 "$TOC_LO" "$TOC_HI" 0x900 0 0 0 >/dev/null
P raw 0x5 "$TMR_LO" "$TMR_HI" 0x4000000 0x2 "$TMR_PA_LO" "$TMR_PA_HI" >/dev/null
echo "== load firmware =="
L(){ P loadfw "$@" 2>&1 | grep loadfw >> ~/gpu/fwaddr.log; }
: > ~/gpu/fwaddr.log
L ~/gpu/fw/gc_11_0_1_pfp.bin 256 263168 2 0x000000
L ~/gpu/fw/gc_11_0_1_me.bin  256 263168 1 0x100000
L ~/gpu/fw/gc_11_0_1_mec.bin 256 267008 4 0x200000
L ~/gpu/fw/sdma_6_0_1.bin    256 17408 71 0x380000
L ~/gpu/fw/sdma_6_0_1.bin    17664 16896 72 0x3C0000
L ~/gpu/fw/gc_11_0_1_mes_2.bin 256 135648 33 0x400000
L ~/gpu/fw/gc_11_0_1_mes_2.bin 135904 131072 34 0x440000
L ~/gpu/fw/gc_11_0_1_mes1.bin 256 104272 81 0x480000
L ~/gpu/fw/gc_11_0_1_mes1.bin 104528 131072 82 0x4C0000
L ~/gpu/fw/gc_11_0_1_imu.bin 256 66048 68 0x500000
L ~/gpu/fw/gc_11_0_1_imu.bin 66304 66048 69 0x600000
L ~/gpu/fw/gc_11_0_1_rlc.bin 25344 2560 20 0x700000
L ~/gpu/fw/gc_11_0_1_rlc.bin 27904 21104 21 0x720000
L ~/gpu/fw/gc_11_0_1_rlc.bin 49008 66048 26 0x800000
L ~/gpu/fw/gc_11_0_1_rlc.bin 115056 33280 48 0x840000
L ~/gpu/fw/gc_11_0_1_rlc.bin 148336 8704 25 0x880000
L ~/gpu/fw/gc_11_0_1_rlc.bin 256 25088  8 0x300000
echo "== AUTOLOAD_RLC =="
P autoload
echo "== SMU 0x3, 0x2, EnableGfxImu(param=1) (linux order) =="
P smu 0x3 0 | tail -1
P smu 0x2 0 | tail -1
P smu 0x16 1 | tail -1
sleep 2
P regs 0xee7e 0x21a0 0x2004 0x263e
if [ -z "${PHX34_WATCHDOG_ACK:-}" ]; then $SUDO killall shutdown 2>/dev/null; echo "watchdog cancelled rc=$?"; fi
