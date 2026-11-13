# Persistent goal and login continuation

The allocation investigation uses a persistent Codex goal and a private
checkpoint. A user LaunchAgent can invoke `tools/goal_resume.py` at login to
resume that exact saved session after a different host boot. This is agent
session continuity; its installation does not alter the GPU startup monitor,
install a driver, authorize a workload or request a reboot.

The local Codex CLI's `exec resume` interface and read-only goal/session
database checks were inspected on 2026-11-14. The configured native CLI is
SHA-256 pinned. The helper adds no model, approval, sandbox-bypass or remote
control override. Configuration, session identifiers, checkpoint, per-boot
claims and execution logs stay private outside the repository. No credentials
are copied into the LaunchAgent or checkpoint.

## Restart contract

- Installation arms the next boot. Loading the job during the current boot
  validates and defers, avoiding a concurrent second instance of this session.
- An active matching goal, available unarchived session, expected repository
  branch, pinned executable and matching private checkpoint are required.
  Paused/completed/limited goals are not reactivated.
- A nonblocking process lock prevents concurrent helpers. A durable claim is
  published before launching Codex, allowing at most one automatic launch per
  boot, including repeated logins. A failed or interrupted launch is retained
  for review and is not automatically replayed.
- A private `disabled` marker stops future launches. Removing or unloading
  the dedicated user LaunchAgent disables login continuation. An already
  running session is not killed by these actions.
- `--check` validates without starting Codex; `--resume-now` explicitly allows
  the installation boot but still respects existing claims. Neither option
  resets a goal, removes old claims or grants GPU/reboot operations.

The resumed prompt must read the persistent checkpoint and latest private
investigation records first, preserve unfinished work, keep the goal/checkpoint
current and honor consumed M2/reboot grants. Only the authorized source and
read-only investigation continues until a fresh target execution scope exists.
The [execution plan](ALLOCATION-EXECUTION-PLAN.md) defines those pending gates.

## Verification and practical limits

`tests/test_goal_resume.py` exercises simulated new boots, installation-boot
deferral, duplicate login, active-process exclusion, failed launch persistence,
inactive/replaced goals, unavailable sessions, branch/binary/checkpoint changes,
private permissions, symbolic links and check-only behavior. Fake child
execution does not start another agent or GPU workload. Local installation
verification must also read back the LaunchAgent and its current-boot deferral.

A user LaunchAgent runs after login. FileVault unlock, a working OS/user
session, retained local state, a compatible pinned CLI, available authentication
and network/model service are necessary. Power-off time and an unusable OS
cannot be covered. Logs and manual exact-session resume instructions must
remain available when automatic resume fails. No end-to-end reboot result is
claimed without observing a real authorized reboot and subsequent resume.

## Local verification, 2026-11-14

Source commit **`92197dd6911848de1a1f661261cd2335b164ad76`** passed all
**482 Python tests** in 194.164 seconds in a clean committed checkout,
including 17 continuation tests. The recorded source inputs were unchanged,
and the checkout remained clean. The source commit's remote ref/tree/parent
and all three changed files were independently verified through the Git API.
Automatic full-stack run `43481341083` was cancelled and is not a build pass.

The dedicated user LaunchAgent was installed and loaded. Read-back verified
private permissions, the installed helper's source hash, next-boot deferral
on the current boot, empty launch stderr and no automatic attempt claim.
The real saved goal/session/checkpoint/executable also passed check-only
admission with the installation-boot guard explicitly bypassed for validation;
no Codex resume process was started. The goal was independently read back as
active. No goal/session database was directly modified by the helper.

This confirms local configuration and admission, not a completed reboot.
The [validation record](validation/goal-continuity-20261114.json) keeps that
distinction. No GPU startup, driver, runtime, EFI or security setting was
changed, and no reboot or target workload was requested.
