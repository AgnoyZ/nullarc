# Experimental Metal capability contract

The 780M downstream plugin is not a Metal-conformance-certified driver. Previously
several queries always answered yes, including queries whose dependencies were
missing or whose Vulkan device feature was never enabled. This change makes the
following declarations conservative without removing implementation entry points.

| Query | Current rule |
| --- | --- |
| Compute/render function pointers | Live Vulkan backend, loaded base translator/free function, and all of `nvmtl_visible_refs`, `nvmtl_link_visible`, `nvmtl_link_runtime`. These exports are used by the existing linking/table implementation. |
| Compute/render dynamic libraries | Live Vulkan backend, loaded base translator/free function, and `nvmtl_link_externs`, used by existing external-symbol linking. |
| Both barycentric query names | False. This backend does not enable the required fragment-shader-barycentric Vulkan device feature. |
| `supportsFamily:` / `supportsFeatureSet:` | False for all values until whole-family feature/limit coverage exists. The old Mac/Common/Metal3 positive claims were not justified by such coverage. |
| `hasUnifiedMemory` | Existing false retained. APU identity does not validate this plugin's shared/managed/private storage and CPU/GPU-coherence semantics. |
| Texture sample counts / maximum buffer length | Existing backend-derived queries retained, returning false/zero when unavailable. |

The dependency mask describes available implementation paths. It is **not**
evidence that a linked shader executed correctly on the target, that every Metal
feature is implemented, or that this initial audit covers all plugin methods.
Argument-buffer/read-write tiers, heaps, texture-format limits, synchronization
and other remaining declarations still need their own feature-level audit.
Some applications may now decline this experimental device because no complete
family is advertised; restoring unconditional yes would hide the missing proof.

`tools/test_metal_capabilities.py` extracts the actual nine selector bodies and
backend/translator-mask functions. It compiles their bodies into a C++ host
harness, with dependency presence explicitly faked. All 96 combinations of
backend state, translator presence and optional-export mask exercise positive
paths, each missing dependency, loss/uninitialized states, denied family/feature
values and both denied barycentric aliases under ASan/UBSan. This is decision
logic coverage. The real Objective-C plugin is separately compiled and signed
by focused CI; neither check submits GPU work.

To promote a capability, add compiler/translator fixtures, correct pipeline and
device-feature enabling checks, and positive **real target execution** evidence,
including missing-dependency/lost-device failure cases. Record the actual Tahoe
build; hosted CI's macOS version is not the target's version. Revert the isolated
capability commit for source rollback; no deployed driver is modified here.
