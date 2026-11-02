#!/bin/sh
# Ordered, fail-safe bring-up runner for the experimental 780M kexts.
#
# This is the downstream replacement for the reference workflow's full.sh/bringup5.sh/phxboot.sh control flow, not a
# port of its register sequence: it runs an operator-supplied, lexically ordered list of stage executables, stops at the
# first failure or timeout, and always runs the operator's release hook so a failed attempt cannot leave PhxAMDFB
# holding the GPU (a held GPU keeps WindowServer from opening the panel).
#
# What it deliberately never does: reboot or shut down, write or delete NVRAM variables, kill processes it did not
# start, install or copy anything, or invent register/address constants. Every path and the expected kext build come
# from the command line; the only facts it reads are the host platform and the kext's published IORegistry properties.
#
# Usage:
#   phx_boot_gate.sh --state DIR --stages DIR --expected-build N [--release PATH] [--timeout SECONDS] [--check]
#
#   --state DIR           private directory for the pending marker, lock, log and per-stage output (created 0700)
#   --stages DIR          directory of executable stage files, run in bytewise name order (00-x, 10-y, ...)
#   --expected-build N    required value of PhxBringup's "phx-build" property
#   --release PATH        executable run on every exit path once the gate has started (optional, bounded)
#   --timeout SECONDS     per-stage limit, default 60
#   --check               validate the host, kext properties and stage list, print the plan, then run nothing
#
# Exit codes:
#   0  success (or --check passed, or the kill-switch file asked for no work)
#   64 usage error       74 host refused        75 another instance is running
#   76 previous attempt did not finish (marker present)   77 a stage failed
#   78 a stage timed out 79 kext properties do not match the policy
#
# A stage that fails is a handled failure: the marker is removed and the exit code says why. A stage that hangs until
# the gate is killed leaves the marker in place, so the next boot refuses to run stages and leaves the panel on the
# firmware framebuffer.

PATH=/usr/bin:/bin:/usr/sbin:/sbin
LC_ALL=C
export PATH LC_ALL
umask 077

if [ "${PHX_BOOT_GATE_TEST:-0}" = 1 ]; then
    UNAME=${PHX_UNAME:-/usr/bin/uname}
    IOREG=${PHX_IOREG:-/usr/sbin/ioreg}
else
    UNAME=/usr/bin/uname
    IOREG=/usr/sbin/ioreg
fi

fail() { printf '%s\n' "phx-boot-gate: $1" >&2; exit "$2"; }
log() { printf '%s %s\n' "$(/bin/date '+%F %T')" "$1"; }

STATE= STAGES= RELEASE= EXPECTED= TIMEOUT=60 CHECK=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --state) [ "$#" -ge 2 ] || fail 'usage: --state needs a directory' 64; STATE=$2; shift 2 ;;
        --stages) [ "$#" -ge 2 ] || fail 'usage: --stages needs a directory' 64; STAGES=$2; shift 2 ;;
        --expected-build) [ "$#" -ge 2 ] || fail 'usage: --expected-build needs a number' 64; EXPECTED=$2; shift 2 ;;
        --release) [ "$#" -ge 2 ] || fail 'usage: --release needs a path' 64; RELEASE=$2; shift 2 ;;
        --timeout) [ "$#" -ge 2 ] || fail 'usage: --timeout needs seconds' 64; TIMEOUT=$2; shift 2 ;;
        --check) CHECK=1; shift ;;
        *) fail "unknown argument: $1" 64 ;;
    esac
done

[ -n "$STAGES" ] && [ -n "$EXPECTED" ] || fail 'usage: --stages and --expected-build are required' 64
[ -n "$STATE" ] || [ "$CHECK" -eq 1 ] || fail 'usage: --state is required unless --check is given' 64
case "$EXPECTED" in ''|*[!0-9]*) fail '--expected-build must be a decimal integer' 64 ;; esac
case "$TIMEOUT" in ''|*[!0-9]*) fail '--timeout must be a decimal integer' 64 ;; esac
[ "$TIMEOUT" -ge 1 ] || fail '--timeout must be at least one second' 64
[ -d "$STAGES" ] || fail "stage directory does not exist: $STAGES" 64
STAGES=$(cd "$STAGES" && pwd -P) || fail 'cannot resolve the stage directory' 64
if [ -n "$RELEASE" ]; then
    case "$RELEASE" in /*) ;; *) fail '--release must be an absolute path' 64 ;; esac
    [ -x "$RELEASE" ] || fail "release hook is not executable: $RELEASE" 64
fi

# ---- preconditions: read-only, no side effects ---------------------------------------------------------------
host=$($UNAME -s 2>/dev/null) || fail 'cannot identify the host platform' 74
arch=$($UNAME -m 2>/dev/null) || fail 'cannot identify the host architecture' 74
[ "$host" = Darwin ] || fail "host is $host, not Darwin" 74
[ "$arch" = x86_64 ] || fail "host architecture is $arch, not x86_64" 74

planned=
for path in "$STAGES"/*; do
    [ -f "$path" ] || continue
    name=${path##*/}
    case "$name" in .*) continue ;; esac
    case "$name" in *[!A-Za-z0-9._-]*) fail "stage name has unsupported characters: $name" 64 ;; esac
    [ -x "$path" ] || fail "stage is not executable: $name" 64
    planned="$planned $name"
done
[ -n "$planned" ] || fail "no executable stages in $STAGES" 64

if [ "$CHECK" -eq 0 ]; then
    case "$STATE" in /*) ;; *) fail '--state must be an absolute path' 64 ;; esac
    /bin/mkdir -p "$STATE" 2>/dev/null || fail "cannot create the state directory: $STATE" 64
    STATE=$(cd "$STATE" && pwd -P) || fail 'cannot resolve the state directory' 64
    /bin/chmod 700 "$STATE" 2>/dev/null || fail 'cannot protect the state directory' 64
    LOG=$STATE/gate.log
    MARK=$STATE/attempt.pending
    LOCK=$STATE/gate.lock
    OFF=$STATE/off
    exec >>"$LOG" 2>&1
    log "== gate $STATE expected build $EXPECTED timeout ${TIMEOUT}s"
    log "stages:$planned"
fi

ioreg_out=$($IOREG -r -c PhxBringup -l -w 0 2>/dev/null)
[ -n "$ioreg_out" ] || fail 'PhxBringup is not loaded (no IORegistry properties)' 79
int_prop() { printf '%s\n' "$ioreg_out" | /usr/bin/sed -n "s/.*\"$1\" = \([0-9][0-9]*\).*/\1/p" | /usr/bin/head -n 1; }
str_prop() { printf '%s\n' "$ioreg_out" | /usr/bin/sed -n "s/.*\"$1\" = \"\([^\"]*\)\".*/\1/p" | /usr/bin/head -n 1; }

policy=$(str_prop phx-780m-policy)
[ "$policy" = strict-execution-v1 ] || fail "kext policy is '$policy', not strict-execution-v1" 79
build=$(int_prop phx-build)
[ "$build" = "$EXPECTED" ] || fail "kext build is '$build', expected $EXPECTED" 79
fb_phys=$(int_prop phx-fb-phys)
fb_len=$(int_prop phx-fb-aper-len)
[ -n "$fb_phys" ] && [ "$fb_phys" -gt 0 ] || fail 'kext published no framebuffer physical address' 79
[ -n "$fb_len" ] && [ "$fb_len" -gt 0 ] || fail 'kext published no framebuffer aperture length' 79

if [ "$CHECK" -eq 1 ]; then
    printf 'check ok: Darwin %s, kext build %s, policy %s, fb 0x%s len 0x%s\n' \
        "$arch" "$build" "$policy" "$fb_phys" "$fb_len"
    printf 'stages (would run in this order):%s\n' "$planned"
    printf 'no stage was run and no state was written\n'
    exit 0
fi

# ---- run: single instance, crash marker, release on every exit path ------------------------------------------
release_hook() {
    [ -n "$RELEASE" ] || return 0
    "$RELEASE" >"$STATE/release.out" 2>&1 &
    rchild=$!
    (/bin/sleep 15 & sleep_pid=$!
     trap 'kill -TERM "$sleep_pid" 2>/dev/null; exit 0' TERM INT HUP
     wait "$sleep_pid"
     kill -TERM "$rchild" 2>/dev/null; /bin/sleep 2; kill -KILL "$rchild" 2>/dev/null) >/dev/null 2>&1 &
    watch=$!
    wait "$rchild"; rc=$?
    kill -TERM "$watch" 2>/dev/null; wait "$watch" 2>/dev/null
    log "release: $RELEASE exited $rc"
    return 0
}
HAVE_LOCK=0
CURRENT_CHILD= CURRENT_WATCH=
cleanup() {
    # A signalled gate must not leave a stage touching hardware behind it.
    if [ -n "$CURRENT_WATCH" ]; then kill -TERM "$CURRENT_WATCH" 2>/dev/null; wait "$CURRENT_WATCH" 2>/dev/null; fi
    if [ -n "$CURRENT_CHILD" ]; then
        kill -TERM "$CURRENT_CHILD" 2>/dev/null
        /bin/sleep 2
        kill -KILL "$CURRENT_CHILD" 2>/dev/null
        wait "$CURRENT_CHILD" 2>/dev/null
    fi
    CURRENT_CHILD= CURRENT_WATCH=
    # Never touch a lock this instance did not take: a second gate must not delete the live holder's lock.
    [ "$HAVE_LOCK" -eq 1 ] || return 0
    release_hook
    /bin/rm -f "$LOCK/pid" 2>/dev/null
    /bin/rmdir "$LOCK" 2>/dev/null
}
trap 'cleanup' 0
trap 'exit 130' INT
trap 'exit 143' TERM HUP

if /bin/mkdir "$LOCK" 2>/dev/null; then
    HAVE_LOCK=1
else
    holder=$(/bin/cat "$LOCK/pid" 2>/dev/null)
    if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
        fail 'another gate instance is running' 75
    fi
    log 'replacing a stale lock left by a finished or killed instance'
    /bin/rm -f "$LOCK/pid" 2>/dev/null
    /bin/rmdir "$LOCK" 2>/dev/null
    /bin/mkdir "$LOCK" 2>/dev/null || fail 'cannot take the gate lock' 75
    HAVE_LOCK=1
fi
printf '%s\n' "$$" >"$LOCK/pid" 2>/dev/null || :
if [ -e "$OFF" ]; then log 'kill switch present: nothing to do'; exit 0; fi
if [ -e "$MARK" ]; then
    log 'previous attempt did not finish: refusing to run stages (clear the marker after review)'
    exit 76
fi

: >"$MARK" || fail 'cannot create the pending marker' 64
log "running:$planned"

for path in "$STAGES"/*; do
    [ -f "$path" ] || continue
    name=${path##*/}
    case "$name" in .*) continue ;; esac
    out=$STATE/stage-$name.out
    tmo=$STATE/stage-$name.timeout
    /bin/rm -f "$tmo"
    log "stage $name: start"
    ( ulimit -f 16384 2>/dev/null; exec "$path" ) >"$out" 2>&1 &
    CURRENT_CHILD=$!
    (/bin/sleep "$TIMEOUT" & sleep_pid=$!
     trap 'kill -TERM "$sleep_pid" 2>/dev/null; exit 0' TERM INT HUP
     wait "$sleep_pid"
     : >"$tmo"
     kill -TERM "$CURRENT_CHILD" 2>/dev/null; /bin/sleep 2; kill -KILL "$CURRENT_CHILD" 2>/dev/null) >/dev/null 2>&1 &
    CURRENT_WATCH=$!
    wait "$CURRENT_CHILD"; status=$?
    kill -TERM "$CURRENT_WATCH" 2>/dev/null; wait "$CURRENT_WATCH" 2>/dev/null
    CURRENT_CHILD= CURRENT_WATCH=
    printf '%s %s\n' "$name" "$status" >>"$STATE/results.txt"
    if [ -e "$tmo" ]; then
        log "stage $name: timed out after ${TIMEOUT}s"
        /bin/rm -f "$MARK"
        exit 78
    fi
    if [ "$status" -ne 0 ]; then
        log "stage $name: failed with status $status"
        /bin/rm -f "$MARK"
        exit 77
    fi
    log "stage $name: ok"
done

/bin/rm -f "$MARK"
log 'done'
exit 0
