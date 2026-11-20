# November 20 VBL and ACPI restoration on R1a

The owner requested restoring the earlier VBL scheduling and ACPI/EC log-buffer
batch-copy optimizations after confirming those treatments were no longer
active. The owner identifies the Weather-plugin trial as the context for the
repeated restarts. This restoration excludes Weather and the other plugin
experiments; the preserved failure record does not establish a panic cause.

Work remains exclusively on default `upstream34/vram-layout-fix`, build34.
Preserve the loaded R1a kernel at `568e80b205c10b00cba4f21c6d324d239d725bfd`
and the accepted accelerator/plugin baseline at
`1d4968fbc2ce988c77bdd85b2ec36f435b57f496` except for the isolated VBL
accelerator treatment. PR28 daily waiting remains 250 ms with WindowServer
excluded; resident monitors remain disabled.

## Restore one treatment at a time

1. Restore only the exact VBL accelerator from
   `439f8a5bc3e086770df7b576897fbb11d7ccc9f1` and its corrected AuxKC. Keep
   original ACPI, R1a and the accepted plugin. The candidate executable hash is
   `a206d983fca62dd7959cc701fb9f95d5490da78986aac02dbb67ed00410325e7`; the
   corrected cache hash is
   `f0dbaacf423819c29af7ac0503d6f6c80d897a327dabb6a235385e1cd52728da`.
2. Verify actual selected-cache metadata and installed/recovery files, then
   obtain fresh exact loaded-image and bounded-startup acceptance after an
   authorized restart. Only finite normal-priority GUI/timer observations may
   supply new smoothness evidence; the historical samples are not new results.
3. Restore the ACPI log-buffer treatment only after that VBL boot is accepted,
   using a new configuration delta and recovery scope based on this R1a/VBL
   combination. Do not copy an old complete personal EFI configuration or replay
   a consumed AML controller. Keep the original method/call site, query ordering,
   acknowledgments and power-limit paths unchanged.

## Startup and recovery

The new [VBL adapter](../tools/build34_vbl_resume_host.py) admits only the exact
previously tested accelerator/corrected-cache pair. It derives only two protected
file hashes and the accelerator image identity from the accepted R1a contract.
The native kernel identity, ABI, plugin and EFI/ACPI contract stay unchanged.
Complete-cache comparison preserves all 416 records/29 codeless entries and
the automatic-load policy, paths, dependencies and boot/system collection links.

A fresh private scope must retain exact current accelerator/cache backups and
ordinary R1a startup jobs. Its installation supersedes the earlier unloaded
R1a-only watcher by exact hash; the old scope and records remain preserved and
must not be replayed. The original 45/150/300-second startup limits remain.
One new-boot finite watcher can restore the exact R1a images/jobs, independently
read back disk/cache/ACPI/security, then commit the panel flag before at most one
persisted automatic recovery restart. A failed check consumes permission.

Success removes the finite watcher and retains VBL-compatible startup jobs.
Those jobs recognize the accepted trial on later boots. Their bounded startup
failure path restores R1a on disk without any power request, even if a daily
journal were incorrectly prepared with restart permission. They add no resident
monitor and cannot recover a pre-launchd or hard kernel deadlock. Merely restoring
the original R1a job pointers after VBL success would be incompatible with the
retained VBL image; this adapter explicitly avoids that transition.

## Current validation checkpoint

The journal, original R1a adapter, VBL adapter, complete-cache and extracted VBL
production checks are CPU-only. Source validation and historical candidate hashes
do not establish that this new R1a/VBL combination is installed, loaded or stable.
The default suite passes, including 15 journal, ten original-host and 18 new
VBL-host methods. All 25 complete-cache methods and 60 extracted-production VBL
assertions pass. Optional firmware fixtures are absent. An initial unprivileged
VBL harness link was refused by the pre-existing root-owned test output; running
that same CPU-only harness with its existing owner passed without changing live
drivers or launching a GPU workload.
Actual read-only preflight also passes full current R1a admission, strict bundle
signature verification with the pinned candidate executable in a private copy
of the unchanged bundle, and candidate cache comparison allowing only PhxAccel's
image. The prelink identity is decoded from its 16-byte plist value and checked
against the original candidate identity. No cache is built or live file replaced
by that preflight.
At this source checkpoint no new VBL image or startup job has been installed.
The earlier ordinary reboot grants are consumed; no new ordinary reboot is
authorized or requested by this checkpoint.

The existing R1a boot has one surface GPU timeout, with no increase in the later
installation readback. Keep that observation visible; do not clear counters or
claim strict zero-error acceptance, physical FPS or long-term stability.

Historical evidence: [VBL boot](validation/build34-vbl-corrected-cache-boot-20261118.json),
[ACPI comparison](validation/build34-aml-buffer-boot-20261119.json),
[rollback](validation/build34-weather-boot-rollback-20261120.json).
