#!/bin/bash
# NOT RUN BY THIS REPOSITORY. This is the reference workflow: it arms reboot watchdogs, writes NVRAM and
# sysctls, and is built on reference-machine constants and firmware offsets. The audited entry points here are
# tools/phx_boot_gate.sh (staged bring-up), the phxctl/mesboot subcommands, and tools/phx_baseline.sh
# (read-only capture). See docs/BRINGUP-AUDIT.md and docs/BOOT-GATE.md.
# full.sh <mesboot step>: power the GPU up (bringup5.sh), open the doorbells, unhalt the CP and start MES with the GART,
# then run one mesboot step with its options from the environment (phxboot: MC=1 CS=1 ADOPT=1 GFX=1 AG=1 ... kiqsched).
# Run as root (phxboot) or as a user with sudo. A reboot is armed for 4 minutes in case the GPU hangs the bus.
SUDO=""; [ "$(id -u)" = 0 ] || SUDO=sudo
bash ~/gpu/bringup5.sh >/dev/null 2>&1 || exit $?
$SUDO bash -c "nohup shutdown -r +4 >/dev/null 2>&1 &" || exit $?
# Capture PIPESTATUS immediately: tail can succeed after the helper failed.
# Keep the helper's status when both commands fail; never cancel the watchdog on failure.
$SUDO ~/gpu/phxctl/phxctl wreg 0xDE0 1 | tail -1
pipeline_status=( "${PIPESTATUS[@]}" )
[ "${pipeline_status[0]}" -eq 0 ] || exit "${pipeline_status[0]}"
[ "${pipeline_status[1]}" -eq 0 ] || exit "${pipeline_status[1]}"
$SUDO ~/gpu/phxctl/phxctl wreg 0xA802 0 | tail -1
pipeline_status=( "${PIPESTATUS[@]}" )
[ "${pipeline_status[0]}" -eq 0 ] || exit "${pipeline_status[0]}"
[ "${pipeline_status[1]}" -eq 0 ] || exit "${pipeline_status[1]}"
$SUDO ~/gpu/phxctl/phxctl wreg 0xA803 0x01000000 | tail -1
pipeline_status=( "${PIPESTATUS[@]}" )
[ "${pipeline_status[0]}" -eq 0 ] || exit "${pipeline_status[0]}"
[ "${pipeline_status[1]}" -eq 0 ] || exit "${pipeline_status[1]}"
$SUDO ~/gpu/phxctl/mesboot gart || exit $?
$SUDO ~/gpu/phxctl/mesboot mes || exit $?
$SUDO env MESBOOT_MC=$MC MESBOOT_CS=$CS MESBOOT_VMT=$VMT PTE_SYS=$PS PTE_NOFB=$NF FAULT_DEFAULT=$FD PT_SYS=$PTS VARONLY=$VAR PTE_EXTRA=$PX ROOT_FL=$RF AGPTEST=$AGP CTX0_OFF=$C0 VM8=$V8 VM8_MT=$VMT8 IB0=$IB0 VM8_FLAT=$FLAT VM8_SYS=$VSYS ADOPT=$ADOPT MESBOOT_GFX=$GFX ADOPT_GFX=$AG VM8_IBSYS=$IBSYS VM8_HI=$VHI ~/gpu/phxctl/mesboot "$1" 2>&1 | tail -12
pipeline_status=( "${PIPESTATUS[@]}" )
[ "${pipeline_status[0]}" -eq 0 ] || exit "${pipeline_status[0]}"
[ "${pipeline_status[1]}" -eq 0 ] || exit "${pipeline_status[1]}"
$SUDO killall shutdown 2>/dev/null
