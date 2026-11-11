# Upload-prologue submission failure contract

The command buffer may depend on managed uploads or zero fills recorded into a
pre-submit prologue. Previously, if ending that prologue failed, the backend
dropped it and still submitted the main command buffer. A caller could receive
success while the GPU consumed old bytes. The downstream change refuses that
main submission instead.

On a prologue End failure, neither command buffer has reached QueueSubmit. The
backend invokes retirement for both known-unsubmitted buffers (main retirement
also owns its counter-reset recording), drops retained prologue holds once,
destroys the unsubmitted fence, restores the submit mutex and returns failure.
`VK_ERROR_DEVICE_LOST` additionally disables the backend and returns -2; other
End errors return -1. The empty-prologue and successful command ordering
(counter reset, prologue, main) remain unchanged.

A QueueSubmit or fence-wait failure has different ownership uncertainty. Those
existing paths still disable the backend and retain uncertain resources. A
missing completion witness likewise remains a loss without retirement. This
change does not implement AMD device reset, power management, sleep or resume.
The device-loss return alone is not evidence of safe physical GPU recovery.

`tools/test_submit_begin.py` extracts the actual submit-begin and hold-release
bodies from the current source, hashes inputs and runs 33 cases under ASan/UBSan
on Linux/macOS. Explicit API/timing/witness/retirement fakes observe calls. Cases
cover unavailable backend/handles, counter/main-End/fence failures, both reset
configurations, absent/empty/active prologues, prologue End error/device loss,
queue failure and backend loss during the pre-submit hook. The tests check
no QueueSubmit after failed uploads, fence/hold/retirement calls, successful
command ordering, state/error propagation, unchanged uncertain-resource
retention and mutex/hook-context restoration. They do not execute Vulkan or
prove the internal retirement implementation, hardware fence completion or
actual shader results; existing lifetime suites and real native compilation
remain separate checks. Record CI results after the revision completes.

Rollback: revert the isolated source commit; there is no deployment, firmware,
EFI, BIOS, NVRAM or security-policy change. Target execution acceptance still
requires an actual 780M session, the installed OS build and reproducible
positive/fault behavior before considering sleep/reset work.
