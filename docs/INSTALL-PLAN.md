# Install plan: the OpenCore part, written as steps, never performed

`tools/phx_install_plan.py` answers one narrow question: *if I install these kexts into this EFI, exactly which
files and plist keys change, and how do I put it all back?* It reads an existing `config.plist`, checks the
bundles, and writes a plan. It has **no apply mode**: nothing outside its `--out` directory is written, and it
never touches NVRAM, a sysctl, a kext or the EFI partition.

```sh
python3 tools/phx_install_plan.py --efi-root /Volumes/OC/EFI \
    --kext build/PhxBringup.kext --expect-sha256 PhxBringup.kext=<digest> --out build/install-plan
```

`build/install-plan/plan.md` is for reading, `plan.json` for diffing between builds. Both say `plan-only`.

## What it writes

A fixed, numbered sequence, each step an operator action: make the backup first, copy the bundles (with their
tree digests), add the `Kernel > Add` entries with `MinKernel 25.0.0`, append `phx780m=1` to `boot-args`, reboot
and watch `ioreg -l | grep phx-build`, then run the phase-1 capture. Then the rollback, which is the same list
backwards plus the restore of the timestamped config copy.

If the configuration already has an entry for the bundle, an existing `phx780m=1`, or a non-default
`csr-active-config`/`SecureBootModel`, the plan says *verify* instead of *add* and leaves those values alone.

## What it refuses

| refusal | why |
| --- | --- |
| EFI root under `/System`, `/Library`, `/usr`, `/Applications`, `/private/var/db` | this repository never writes a system location |
| no `EFI/OC/config.plist`, or a plist without `Kernel > Add` and `NVRAM` | not an OpenCore layout it can reason about |
| a bundle that is not a `.kext`, has no `Contents/Info.plist`, or declares an identifier this project does not build | a wrong or foreign kext is not something a plan should install |
| a binary that is not a thin x86_64 `MH_KEXT_BUNDLE` | `tools/verify_artifacts.py` decides this, not the plan |
| an `--expect-sha256` that does not match the bundle it names | the build is not the reviewed one |
| only `PhxAccel.kext` given | there is nothing an OpenCore plan can install; see below |

## Where the plan stops, and why that is not an oversight

Upstream's install needs more than a kext and a boot argument: `docs/INSTALL.md` §1 asks for
`amfi=0x80 amfi_get_out_of_my_way=0x1 -amfipassbeta` with AMFIPass.kext, `csr-active-config` set and
`SecureBootModel` disabled, and §2 asks for `PhxAccel.kext` in `/Library/Extensions`, a LaunchDaemon, and files
under `/System/Library/CoreServices`. That is library validation off for the whole system, plus writes into
system locations.

This repository does not do those things for you — not in a script, and not in a plan. The plan therefore ends
at the OpenCore part and lists the security changes as **operator decisions**, with the consequence stated
plainly: with only the planned steps the kexts are in the EFI and **the driver still will not attach**. That is
the honest state of this project: the mechanical part can be prepared and reverted, the security trade is the
owner's to make deliberately, and neither the plan nor CI can make it for them.

`PhxAccel.kext` is reported the same way: it is not an OpenCore kext, so it is never written into the step list.

## What it establishes

Nothing about the driver. It proves that a configuration is one a plan can describe, that the bundles are the
project's kexts of the expected build, and that the steps and their reverse are listed. The kext may still fail
to load, the panel may still stay dark, and no frame rate is measured. `docs/SUPPORT-STATUS.md` keeps that
distinction for every area.

`tests/test_install_plan.py` runs the planner against synthetic OpenCore layouts in `source-tests`: the steps it
writes, every refusal above, that a configuration with weakening tokens already present is *reported* rather
than *changed*, and that the EFI tree is byte-identical after a run.
