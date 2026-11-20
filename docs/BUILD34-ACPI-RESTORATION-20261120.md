# November 20 ACPI restoration with R1a and VBL

Current status: the exact tested VBL and ACPI treatments are loaded with R1a
and the accepted plugin. Separate independent current-boot readback passed
after the loading restart. The installation and preparation checkpoints below
remain historical records; their pending-loading status is superseded.

The owner's latest instruction is to install and enable the already tested
ACPI optimization now, alongside the staged VBL restoration. It supersedes
the earlier separate-VBL-boot prerequisite. There is no new performance-test
waiting round before this installation.

At the earlier source checkpoint the VBL executable/corrected cache were installed
on disk, while the original accelerator and original ACPI remain loaded.
The new combined adapter was prepared in source before ACPI installation
in a fresh private scope. No ordinary restart was requested by that change.

## Exact treatment

Reuse the byte-identical configuration input/output and 172-byte
`SSDT-BFCOPY.aml` from the historical tested treatment. The configuration
appends one enabled declaration-only DSDT rename Patch and one enabled Add.
All existing ACPI entries, NVRAM, kernel settings and other configuration
remain unchanged. Preserve the original method body, call site, EC query
ordering, acknowledgments, sleeps and power-limit paths. The preview DSDT
is an offline validation input and must never be installed as a whole DSDT.

The complete EFI changes from 357 to 358 files: replace only
`OC/config.plist` and add only `OC/ACPI/SSDT-BFCOPY.aml`. Preserve the R1a
kernel at `568e80b205c10b00cba4f21c6d324d239d725bfd`, the exact staged VBL
pair, accepted plugin and the three individually pinned pre-existing
Microsoft records. No Weather/render-clear or later optimization is included.

Historical AML equivalence, loaded-table and GUI/timer evidence remains
in [the original ACPI record](BUILD34-AML-BUFFER-COPY.md). Reusing exact files
does not turn those historical results into new current-boot measurements.

## Compatible startup and recovery

The [new adapter](../tools/build34_acpi_resume_host.py) uses a distinct scope
kind. Small validation hooks preserve the unchanged original R1a and VBL-only
admission restrictions. The combined scope permits only the exact two-path
EFI delta and pins the historical AML hash, exact configuration copies,
declaration-only preview and complete source/stage manifests. It checks the
actual loaded table set after the next boot, including the original method
body/call site, unrelated table bytes, and only defined FADT/root-pointer
relocations.

Fresh compatible startup jobs replace the unloaded VBL-only scope; its files
and unconsumed journals stay preserved. The original 45/150/300-second gates,
complete 416-record/29-codeless selected-cache metadata checks, daily PR28
250 ms/WindowServer exclusion and disabled resident monitors remain.

The startup-only watcher retains the one-use recovery policy. Before recovery
it must verify every EFI/image/job target against a known original, staged or
candidate state. It restores original ACPI configuration, removes only the
exact added AML, restores original accepted accelerator/cache and R1a startup
jobs, then independently reads back the accepted disk state. Already loaded
ACPI cannot change until restart: recovery validates either exact known table
set without falsely requiring original AML to be loaded in the failed boot.
Ordinary candidate startup still requires candidate AML. The finite first
trial allows at most one persisted recovery restart; later daily startup
failure is disk-only and cannot request power. No resident monitoring or
pre-launchd/hard-deadlock recovery is added.

Success keeps combined-compatible startup jobs. It must not restore original
job pointers while retaining VBL/ACPI files, or replay any old controller.

## Source checks and current limitations

Nineteen new CPU fixture methods check exact manifest/configuration deltas,
unchanged kernel/Microsoft/NVRAM settings, historical-host refusal, immutable
source derivation, current-vs-next-boot ACPI admission, known-table recovery
and refusal before unknown-file mutation. The original ten host and eighteen
VBL host methods continue to pass. These fixtures contain no real firmware
and cannot install files, submit GPU work or request power.

Initial preparation refused a stale hash copied from an old helper constant
before creating a new scope or changing live files. The final pin is taken
from three agreeing inputs: the actual 172-byte candidate, the historical
sealed activation copy and the passed 28-case equivalence record. The old
helper's unrelated deployment constants are not used.

The current R1a boot has one existing surface GPU timeout. Preserve the count
and record whether it increases; do not claim zero-error acceptance, FPS or
long-term stability from installation checks. Actual loaded VBL/ACPI status
requires post-restart readback.

## Installed-state and independent readback

Implementation commit `15231ec917e75a8cb62e8d006afcafb37007a301` was pushed
and independently matched against the default remote branch before the final
installation readback. The full default suite and 25 complete-cache regression
methods passed, alongside the 19 new adapter methods. The actual sealed
EFI-transaction functions also passed a temporary synthetic-tree application,
rollback and unknown-file refusal check. The old 28-case AML equivalence and
official configuration-validator results are reused only for byte-identical
historical files; they were not rerun or represented as new hardware tests.

The fresh combined scope supersedes only the staged VBL-only startup files.
Installation added the exact SSDT, replaced only the expected ACPI configuration,
installed the two compatible bounded-startup job files and finite watcher, and
retired the exact unloaded superseded watcher file. It did not reinstall VBL,
modify R1a/plugin/security or execute a consumed controller. Exact original
configuration, accelerator/cache and accepted R1a startup copies remain private
for recovery. No preview DSDT was installed.

A separate process reopened the actual EFI, selected cache and installed jobs.
It passed all 358 EFI file records, the sole config/table delta, the enabled
Patch/Add entries, all 416 cache records/29 codeless entries, signatures,
unchanged plugin and security, and exact job/recovery hashes and permissions.
The three pinned pre-existing Microsoft records are unchanged. The combined
watcher is unloaded in this boot, the older watcher file is absent and both
new recovery journals are unconsumed.

Current loaded identity still matches R1a with the original accelerator/ACPI.
The same WindowServer survived; VBL advanced and copy completions remained
nonzero. The existing surface timeout stayed at one, the other three checked
errors stayed zero and no matching diagnostic report appeared. Daily PR28
250 ms/WindowServer exclusion and disabled resident monitors are preserved.
No new GPU test, startup bootstrap or power action occurred. This is successful
installation verification, not new-boot loading, FPS or long-term acceptance.

See the [sanitized installation evidence](validation/build34-acpi-restoration-installation-20261120.json).

## Follow-up: one ordinary loading restart prepared

The owner's subsequent “continue” advances this completed installation to
one ordinary restart and read-only new-boot verification. This is a fresh
single-use continuation, not reuse of an old consumed restart dispatcher.
No repeat performance benchmark, new GPU probe or later optimization is added.

Actual preflight again passed the complete 358-file EFI, 416/29 selected-cache
metadata, signatures/security, exact installed startup/recovery files and the
original live accelerator/ACPI with R1a. The watcher remains unloaded and both
recovery journals are unconsumed. The same WindowServer and advancing VBL were
observed, with the existing one surface timeout unchanged and other checked
errors zero. Preparation created only a new private request/readback packet;
it did not alter the installed combined scope or any launch job.

The new dispatcher must verify and commit the existing supported panel flag,
persist one restart intent, then request power once. An uncertain result cannot
be retried. The installed finite watcher supplies its existing bounded startup
admission and exact recovery; no extra observer or resident monitor is installed.
After new-boot acceptance, a separate finite readback must reopen actual files,
confirm exact loaded R1a/VBL/AML and mapped accepted plugin, validate fresh
startup/completion/desktop receipts and independently check unchanged recovery.
At this preparation checkpoint no power request has yet been sent.

See the [sanitized restart preparation](validation/build34-acpi-restoration-reboot-preparation-20261120.json).

## Loading restart and separate retained-boot acceptance

The sole ordinary request was persisted at 18:13:53 Asia/Shanghai on November
20, 2026; shutdown returned zero at 18:13:54. The first trial boot's startup
journal began at 18:14:25 and its finite watcher accepted at 18:16:43. A later
shutdown around 18:18 preceded the current 18:19:02 boot. That intervening
restart is not attributed: no automatic recovery-restart intent exists, and
the first trial had already been accepted. The interrupted request tool was
not retried.

The original independent reader was explicitly bound to the accepted first
trial. It refused the later current boot before mutation. Its refusal remains
intact. A new, separately scoped current-retained-boot reader passed; this does
not manufacture an independent first-trial result. It verified exact loaded
R1a/VBL and mapped accepted plugin, the optimized AML and original method body,
all 358 EFI files, complete 416/29 cache metadata, signatures/security, exact
recovery and unchanged startup files. The current boot has its own successful
startup, desktop and supervision-ended receipts. No startup/recovery/power or
probe process remains; the finite watcher is retired.

The same WindowServer survived the finite observation, with VBL and GPU-copy
progress, all four checked errors zero, no increase and no new matching report.
The previous boot's one surface timeout remains in its historical record;
zero counters after reboot do not prove that issue fixed. Daily PR28 remains
250 ms with WindowServer excluded and resident monitors disabled. No new GPU
probe or FPS benchmark ran, and long-term stability remains unaccepted.

The owner now requests sequential R1–R6 work. This loaded combination is the
recovery baseline for a fresh kernel-only R1b trial; the original combined
restoration and restart scopes must not be replayed. See the
[separate retained-boot record](validation/build34-acpi-restoration-retained-boot-20261120.json).
