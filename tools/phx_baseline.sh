#!/bin/sh
# Phase-1 baseline capture for the 780M display path: read-only counters, no state changes.
#
# This is the measurement docs/analysis.md needs before any optimisation is implemented. It only READS
# sysctls and IORegistry properties; it never writes a sysctl, never touches NVRAM, the kernel
# collections, the EFI partition or the installed kexts, and it writes only inside the --out directory
# it creates.
#
#   sh tools/phx_baseline.sh --out /Users/Shared/phx-baseline-$(date +%Y%m%d-%H%M) --window 60
#
# Two samples are taken --window seconds apart; the delta is the measurement (frames on the panel,
# present rate, the cost of one copied frame as a share of one refresh, VBL tick lateness, and the present
# cadence against the tick). Without --window the counters are captured once: a state snapshot, not a
# measurement. The capture is then decided by tools/phx_baseline_report.py (thresholds: docs/analysis.md §9).
#
# Exit codes: 0 captured, 2 usage, 3 not Darwin/x86_64, 4 output directory exists, 5 a counter is
# missing (kexts not loaded, or a name changed -- the code is authoritative, not the docs).
set -u

SYSCTL_BIN=${PHX_SYSCTL:-sysctl}
IOREG_BIN=${PHX_IOREG:-ioreg}
UNAME_BIN=${PHX_UNAME:-uname}

# Read-only knobs: they say which code path was measured, so a baseline is not comparable without them.
KNOBS='debug.phxfb_alias debug.phxfb_vbl_staged debug.nvaccel_iop debug.nvaccel_iop_sse debug.nvaccel_iop_damage debug.nvaccel_iop_vsync debug.nvaccel_vm_sticky debug.phxbos_flush'
# Monotonic counters (src/phxaccel/accel/phxfb.cpp, src/phxaccel/accel/nvrm-accel.cpp). The last six are the
# present cadence H3 is decided from: frames one, two, three and four-or-more refreshes after the previous
# one, completion checks answered "not yet", and frames completed past two refreshes without a tick. The last
# two are the BO handle high-water mark and the BO creates refused for a full table: that limit is per client,
# and failing allocations look like anything but "out of handles" from user space (docs/analysis.md §4).
COUNTERS='debug.phxfb_vbl_n debug.phxfb_vbl_late_us_sum debug.phxfb_vbl_late_us_max debug.nvaccel_iop_ok debug.nvaccel_iop_ok_h0 debug.nvaccel_iop_src_res debug.nvaccel_iop_src_surf debug.nvaccel_iop_copy_skip debug.nvaccel_iop_blank debug.nvaccel_iop_fail debug.nvaccel_iop_copy_us debug.nvaccel_iop_copy_us_max debug.nvaccel_iop_copy_us_sum debug.nvaccel_vm_parked debug.nvaccel_vm_unparked debug.nvaccel_iop_gap1 debug.nvaccel_iop_gap2 debug.nvaccel_iop_gap3 debug.nvaccel_iop_gap4 debug.nvaccel_iop_vsync_waits debug.nvaccel_iop_vsync_late debug.nvaccel_iop_damage_sum debug.nvaccel_iop_damage_full debug.phxbos_handles_high debug.phxbos_handles_full'

usage() {
    cat <<'EOF'
usage: phx_baseline.sh --out DIR [--window SEC] [--samples N]

  --out DIR       new directory for baseline.json and summary.txt (refused if it exists)
  --window SEC    seconds between two samples (default 0: one snapshot, no deltas)
  --samples N     with --window, repeat the window N times (default 1)

Read-only: nothing on the system is written. Run it on the target laptop from a normal session.
EOF
}

die() {
    echo "phx_baseline: $1" >&2
    exit "$2"
}

out=''
window=0
samples=1
while [ $# -gt 0 ]; do
    case $1 in
        --out) if [ $# -lt 2 ]; then die '--out needs a directory' 2; fi; out=$2; shift 2 ;;
        --window) if [ $# -lt 2 ]; then die '--window needs seconds' 2; fi; window=$2; shift 2 ;;
        --samples) if [ $# -lt 2 ]; then die '--samples needs a count' 2; fi; samples=$2; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "unknown argument: $1" 2 ;;
    esac
done
if [ -z "$out" ]; then usage >&2; die '--out is required' 2; fi
case $window in ''|*[!0-9]*) die '--window must be a whole number of seconds' 2 ;; esac
case $samples in ''|*[!0-9]*) die '--samples must be a whole number' 2 ;; esac
if [ "$samples" -lt 1 ]; then die '--samples must be at least 1' 2; fi

os=$("$UNAME_BIN" -s 2>/dev/null) || os=unknown
arch=$("$UNAME_BIN" -m 2>/dev/null) || arch=unknown
if [ "$os" != Darwin ]; then die "this host is $os, not Darwin: a baseline needs the target macOS install" 3; fi
if [ "$arch" != x86_64 ]; then die "this host is $arch, not x86_64" 3; fi
if [ -e "$out" ]; then die "output directory already exists: $out (choose a fresh one)" 4; fi
mkdir -p "$out" || die "could not create $out" 1
chmod 700 "$out" || die "could not restrict $out to the session user" 1

# One sample: knob and counter values as "name value" lines. A missing or non-numeric counter is fatal:
# these counters are the measurement, and a silently absent one makes an incomplete baseline look whole.
sample() {
    : > "$1"
    for name in $KNOBS $COUNTERS; do
        v=$("$SYSCTL_BIN" -n "$name" 2>/dev/null) || die "sysctl $name is not readable (kexts loaded? name changed in code?)" 5
        case $v in
            ''|*[!0-9-]*) die "sysctl $name returned '$v', which is not a number" 5 ;;
        esac
        echo "$name $v" >> "$1"
    done
}

echo "phx_baseline: $(date -u '+%Y-%m-%dT%H:%M:%SZ') sampling (window ${window}s x ${samples})"
sample "$out/sample-0.txt"
"$IOREG_BIN" -rc PhxAMDFB -d2 2>/dev/null | grep -E 'phx-fb-phys|phx-build|phx-780m-policy|IOClass' > "$out/ioreg.txt" || true
"$IOREG_BIN" -rc NMXAccel -d1 2>/dev/null | grep -E 'IOAccelDisplayPipeCapabilities|NVAccelSurfaceWait|IOClass' >> "$out/ioreg.txt" || true

i=0
while [ "$i" -lt "$samples" ]; do
    i=$((i + 1))
    if [ "$window" -gt 0 ]; then
        sleep "$window"
        sample "$out/sample-$i.txt"
    fi
done

# All derived numbers are computed once, here, so the JSON and the summary cannot disagree.
awk -v window="$window" -v samples="$samples" -v dir="$out" -v host="$os-$arch" -v knobs="$KNOBS" '
function load(file, A,   line, part) {
    while ((getline line < file) > 0) if (split(line, part, " ") >= 2) A[part[1]] = part[2] + 0
    close(file)
}
function knob_line(name,   v) { return "    \"" name "\": " (name in S0 ? S0[name] : "null") }
BEGIN {
    load(dir "/sample-0.txt", S0)
    nk = split(knobs, K, " ")   # the same list the capture reads: one source of truth
    json = dir "/baseline.json"
    tsv = dir "/windows.tsv"
    printf "{\n  \"tool\": \"phx_baseline\",\n  \"host\": \"%s\",\n  \"window_seconds\": %d,\n  \"samples\": %d,\n", host, window, samples > json
    printf "  \"knobs\": {\n" > json
    for (i = 1; i <= nk; i++) printf "%s%s\n", knob_line(K[i]), (i < nk ? "," : "") > json
    printf "  },\n  \"windows\": [\n" > json
    for (s = 1; s <= samples; s++) {
        delete A
        a = dir "/sample-" (s - 1) ".txt"
        b = dir "/sample-" s ".txt"
        load(a, A)
        delete B
        load(b, B)
        if (window > 0) {
            vbl = B["debug.phxfb_vbl_n"] - A["debug.phxfb_vbl_n"]
            ok = B["debug.nvaccel_iop_ok"] - A["debug.nvaccel_iop_ok"]
            cost = B["debug.nvaccel_iop_copy_us_sum"] - A["debug.nvaccel_iop_copy_us_sum"]
            late = B["debug.phxfb_vbl_late_us_sum"] - A["debug.phxfb_vbl_late_us_sum"]
            skip = B["debug.nvaccel_iop_copy_skip"] - A["debug.nvaccel_iop_copy_skip"]
            blank = B["debug.nvaccel_iop_blank"] - A["debug.nvaccel_iop_blank"]
            fail = B["debug.nvaccel_iop_fail"] - A["debug.nvaccel_iop_fail"]
            g1 = B["debug.nvaccel_iop_gap1"] - A["debug.nvaccel_iop_gap1"]
            g2 = B["debug.nvaccel_iop_gap2"] - A["debug.nvaccel_iop_gap2"]
            g3 = B["debug.nvaccel_iop_gap3"] - A["debug.nvaccel_iop_gap3"]
            g4 = B["debug.nvaccel_iop_gap4"] - A["debug.nvaccel_iop_gap4"]
            vw = B["debug.nvaccel_iop_vsync_waits"] - A["debug.nvaccel_iop_vsync_waits"]
            vl = B["debug.nvaccel_iop_vsync_late"] - A["debug.nvaccel_iop_vsync_late"]
            hz = vbl / window
            frame_us = (hz > 0 ? 1000000.0 / hz : 0)
            avg = (ok > 0 ? cost / ok : 0)
            share = (frame_us > 0 ? 100.0 * avg / frame_us : 0)
            lateavg = (vbl > 0 ? late / vbl : 0)
            printf "    {\"index\": %d, \"vbl_ticks\": %d, \"vbl_hz\": %.1f, \"frames_on_panel\": %d, \"presents_per_s\": %.1f, \"avg_copy_us\": %.1f, \"copy_share_of_refresh_pct\": %.1f, \"copy_skip\": %d, \"blank_frames\": %d, \"iop_fail\": %d, \"vbl_late_avg_us\": %.1f, \"vbl_late_max_us\": %d, \"iop_gap1\": %d, \"iop_gap2\": %d, \"iop_gap3\": %d, \"iop_gap4\": %d, \"iop_vsync_waits\": %d, \"iop_vsync_late\": %d}%s\n", s, vbl, hz, ok, ok / window, avg, share, skip, blank, fail, lateavg, B["debug.phxfb_vbl_late_us_max"], g1, g2, g3, g4, vw, vl, (s < samples ? "," : "") > json
            printf "%d\t%.1f\t%.1f\t%.1f\t%.1f\t%d\t%d\t%d\t%.1f\t%d\t%d\t%d\t%d\t%d\t%d\n", s, hz, ok / window, avg, share, skip, blank, fail, lateavg, g1, g2, g3, g4, vw, vl > tsv
        } else {
            printf "    {\"index\": %d, \"snapshot_only\": true, \"frames_on_panel\": %d, \"last_copy_us\": %d, \"slowest_copy_us\": %d}%s\n", s, A["debug.nvaccel_iop_ok"], A["debug.nvaccel_iop_copy_us"], A["debug.nvaccel_iop_copy_us_max"], (s < samples ? "," : "") > json
        }
    }
    printf "  ],\n  \"claims\": {\"display_path_counters_read\": true, \"gpu_work_submitted\": false, \"hardware_execution_established\": false},\n" > json
    printf "  \"limitation\": \"Display-path counters only: they say how a composited frame reached the panel, not why an application was slow, and they establish no GPU execution or acceleration.\"\n}\n" > json
    close(json)
    close(tsv)

    sum = dir "/summary.txt"
    printf "phx_baseline on %s, resample window %ss x %d\n\nknobs (they decide which path was measured):\n", host, window, samples > sum
    for (i = 1; i <= nk; i++) printf "  %s = %s\n", K[i], (K[i] in S0 ? S0[K[i]] : "missing") > sum
    printf "\n" > sum
    if (window > 0) {
        printf "window   vbl_hz  presents_s avg_copy_us copy_pct skips blanks fails late_avg_us\n" > sum
        while ((getline line < tsv) > 0) {
            split(line, f, "\t")
            printf "%-8s %-7s %-10s %-11s %-8s %-5s %-6s %-5s %s\n", f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8], f[9] > sum
        }
        close(tsv)
        printf "\ncadence (copied frames by the gap since the previous one):\nwindow   gap1  gap2  gap3  gap4  vsync_waits vsync_late\n" > sum
        while ((getline line < tsv) > 0) {
            split(line, f, "\t")
            printf "%-8s %-5s %-5s %-5s %-5s %-11s %s\n", f[1], f[10], f[11], f[12], f[13], f[14], f[15] > sum
        }
        close(tsv)
        printf "\ncopy_pct is one copied frame as a share of one refresh; gap1..4 count copied frames about one, two,\nthree and four-or-more refreshes after the previous one. tools/phx_baseline_report.py applies the\nthresholds in docs/analysis.md §9 to this file and prints which hypothesis the capture supports.\n" > sum
    } else {
        printf "snapshot only (--window 0): the counters were read once, so there is no rate and no delta.\n" > sum
    }
    printf "\nfull record: %s/baseline.json\n", dir > sum
    close(sum)
}' || die "could not derive the baseline from the samples" 1

cat "$out/summary.txt" || die "the summary was not written" 1
echo "phx_baseline: wrote $out/baseline.json"
