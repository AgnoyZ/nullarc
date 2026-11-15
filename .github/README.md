# Actions execution policy

At the owner's request on 2026-11-15, downstream validation runs manually.
`build.yml`, `priority-validation.yml`, `edid-validation.yml` and
`hidpi-validation.yml` retain `workflow_dispatch` and no longer subscribe to
push or pull-request events. Their jobs, permissions and artifact limits are
unchanged. The other downstream workflows were already manual-only.

The inherited `CI` workflow (`ci.yml`) is disabled through the repository's
Actions setting. This also prevents the unchanged upstream copy on `main`
from automatically running on pushes and pull requests. Its source is kept
intact to preserve the upstream mirror and original34 default-branch source.

Keep automatic triggers off unless the owner requests otherwise. Re-enabling
the inherited workflow or adding an automatic event changes this policy.
Manual artifact workflows retain their separate provenance and publication
limits in `docs/KEXT-PROVENANCE.md` and `docs/RADV-PROVENANCE.md`; disabling
automatic CI does not expand those permissions.
