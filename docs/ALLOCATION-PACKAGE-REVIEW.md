# Allocation candidate package and recovery review

Status on 2026-11-14: **build-37 target package not established; passive reads
remain unavailable**. This file records a read-only inventory, not a new build,
delivery, installation or execution receipt. The [execution plan](ALLOCATION-EXECUTION-PLAN.md)
still governs the next target gates. The allocation root cause remains unconfirmed.

## Retained candidate inventory

The repository Actions artifact API returned six artifacts: four two-kext
packages with source build numbers 34, 34, 35 and 36, and two RADV packages.
There was no build-37 kernel/reader package among them. Build numbers here
come from the referenced committed source, not a loaded-image readback.
Build-37 scoped run `43463527011`, attempt 2, still reports success at
`1c17a1712cb3a64db31148cb33d0c2c9741e7e5d` with zero artifacts. The compile-only
workflow has no upload step; its runner output is not a retained delivery.

A local inventory found 28 archive or named executable paths under ignored
`build/`, excluding fixture, backup and `OC` trees. It identified older retained
kext/RADV materials and no standalone `allocation-snapshot` executable. This
bounded search does not establish absence elsewhere on the machine and does
not convert CPU snapshot/reader harnesses into native target packages.

The reviewed kernel, snapshot headers, reader and two workflow files at
`eab936d7d636abe5585d920016d0d17d418428f5` match their build-37 source versions.
Their hashes are retained with the private inventory; no source change or
new compile result is implied by that comparison.

## Build-36 package revalidation

Existing artifact `14046979860`, from manual two-kext run `43446700859` at
`3948e122d6ae26fa0644a70838bc0bfb76d91752`, was still unexpired at review time.
The API listed expiry at **2026-11-20 14:52:10 UTC**; retained local bytes do
not depend on continued remote retention.

- The retained ZIP matches API digest
  `d38e0c83fa5c7faaf7f7ec9a558447b05208f84f71d0bf1522bcc615cc89b382`.
- Its inner package matches
  `890b64e65d12bd62e4cd098ec5dd7581b39d2b0aa64131b32ac40c2840db3575`.
- All 25 package files match the archive and checksum inventory. The 85
  project source files match a fresh archive of the pinned local Git commit.
  The 1,226 SDK blobs match the previously retained pinned SDK tree; this
  review did not fetch a new SDK tree.
- Both retained kexts pass structural identity and strict signature checks.
  Build-36 PhxBringup executable SHA-256 is
  `3ac7816a80504bf587d3c684c0941e12dd6c686c2d8f48e3dcff093fdd2b176b`.

These checks establish retained-byte integrity and the stated source/archive
relationships. They neither reproduce the native build nor prove loadability,
current loaded identity or successful GPU execution. The package report's
`installed=false` describes packaging time; later build-36 deployment and its
failed M2 result remain in the [postboot record](validation/allocation-kernel-build36-postboot-20261113.json).

## Recovery materials and remaining gap

The retained pre-build36 EFI backup contains 334 files. All bytes, the saved
configuration hash and the build-35 PhxBringup bundle match the saved manifest;
that bundle's strict signature also passes. The historical post-deployment
manifest retains its previously verified digest. Comparing the saved manifests
shows one active executable content change and three added retained-build35
files. The 331 files outside the active three-file bundle are unchanged.
The two remaining active bundle files have identical bytes across these builds.

This is an offline backup/manifest check. No live EFI was mounted or read,
and no currently loaded driver identity was rechecked. The historical record
did not verify separate bootable recovery media. An intact backup alone does
not establish how it can be restored if the normal OS cannot boot. Build 35
is an earlier diagnostic image, not evidence of a working accelerated desktop.

## Exact scope still needed before Phase A

The smallest candidate change is a reviewed build-37 **PhxBringup-only**
replacement plus a separately retained standalone reader. Phase A does not
require replacing PhxAccel, plugins, runtime libraries or startup scripts.
The existing public two-kext exception cannot be expanded to publish the
reader, and neither retained RADV package supplies it. No workflow was
dispatched and no private delivery mechanism was created in this review.

Before any target grant can be concrete, select and review a native Intel
macOS build/delivery route that retains the exact kernel and reader bytes,
source and SDK pins, compiler/link commands, signatures and checksums. A
private reader handoff must remain outside the existing public upload scope.
Then specify the exact installation delta, a freshly verified backup, a usable
operator recovery route, and the normal reboot/load scope separately from the
two passive invocations. The [Phase A contract](ALLOCATION-EXECUTION-PLAN.md#phase-a-prove-passive-read-feasibility-on-the-firmware-desktop)
requires one baseline and one matching second read, with no added workload or
automatic escalation to M2. Missing package or recovery fields remain a no-go;
do not substitute build 36 or rerun an old helper.

The [machine-readable review](validation/allocation-package-review-20261114.json)
records the checks and their limits. The next permitted work is source-only
review of a precise delivery route and startup admission/recovery design;
target installation, reads and any later display attempt remain separate.
The [source-only handoff](ALLOCATION-SOURCE-PACKET.md) now defines the scoped
in-tree input export; it does not supply or authorize native binary delivery.
