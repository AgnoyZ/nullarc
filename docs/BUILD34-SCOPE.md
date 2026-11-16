# Default build34 only

The owner clarified the development scope on 2026-11-16: focus exclusively on
PhxBringup build34 on the default branch `upstream34/vram-layout-fix`. Its
approved source checkpoint is `64f3d991a4ddc3af5bbf30cbced9f11d3e7dd50c`,
including the already validated A1, A2 and corrected A3 changes. Documentation
commits may advance the branch without changing this driver-source baseline.

Build41 and build42 are withdrawn, not candidates. Do not continue preparing,
compiling, installing, loading or testing them as candidates. Do not rename a
downstream kernel to build34 or relax the original build34 admission checks.
The earlier instruction to do general development on downstream is superseded;
other branches, source experiments and validation records remain historical.

Continue IB wrong-value investigation only against default build34. A further
authorized fix must be a minimal isolated change, preserve the accepted A1/A2/
corrected-A3 changes and keep unrelated downstream wait, lifecycle, ABI and
initialization changes out. A subsequent item must not be promoted on the basis
of a host-only test or a simulated GPU result. The observed IB wrong value
remains unresolved; wait promotion and accelerated desktop remain on HOLD.

The interrupted build42 user-tool preparation was stopped, and its eight
uncommitted files were withdrawn. No driver was installed or loaded, no native
GPU test was executed and no reboot was requested during that preparation or
this scope correction. Old one-use hardware scopes remain consumed. Existing
installation, recovery, privacy, licensing and explicit-execution boundaries
continue to apply; this scope correction does not arm a new hardware trial.

The subsequent [MEC range diagnostic](BUILD34-MEC-RANGE-DIAGNOSTIC.md) keeps
one upstream initialization lead available as original34-only offline tooling
on this branch. It does not change the production helper/kernel, adopt a
hardware fix or restore either withdrawn candidate.

The owner's subsequent request to test and integrate several PRs authorizes
the narrow [plugin source batch](BUILD34-PLUGIN-PR-INTEGRATION.md): upstream
PR16, PR19 with a tested zero-progress-write correction, PR15 and PR22. Each
stage passes CPU behavior tests and native compilation before the next is
applied. This extends only four nmplugin source files from the accepted
checkpoint; original34 kernel, ABI, production helper and A1/A2/corrected-A3
behavior remain preserved. It is source integration, not hardware promotion:
the IB result and existing GPU/desktop HOLDs remain unchanged.
