# November 20 ACPI restoration with R1a and VBL

The owner's latest instruction is to install and enable the already tested
ACPI optimization now, alongside the staged VBL restoration. It supersedes
the earlier separate-VBL-boot prerequisite. There is no new performance-test
waiting round before this installation.

At this source checkpoint the VBL executable/corrected cache are installed
on disk, while the original accelerator and original ACPI remain loaded.
The new combined adapter is prepared in source; ACPI installation follows
in a fresh private scope. No ordinary restart is requested by this change.

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
