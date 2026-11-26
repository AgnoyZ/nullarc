# Makefile for AMD RDNA 3 (Radeon 780M) macOS Driver Project

CXX ?= clang++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Werror -O2
INCLUDES = -Isrc -Isrc/amd -Isrc/uapi -Isrc/winsys

TEST_BIN_DIR = build/tests
TESTS = $(TEST_BIN_DIR)/test_rdna3_discovery_uma \
        $(TEST_BIN_DIR)/test_rdna3_ip_dcn \
        $(TEST_BIN_DIR)/test_rdna3_ucode \
        $(TEST_BIN_DIR)/test_r3n_abi \
        $(TEST_BIN_DIR)/test_phx_topology \
        $(TEST_BIN_DIR)/test_phx_dcn_zerocopy \
        $(TEST_BIN_DIR)/test_build34_dcn_page_layout \
        $(TEST_BIN_DIR)/test_build34_dcn_flip_readback

.PHONY: all test clean kext fixtures

all: test

$(TEST_BIN_DIR):
	mkdir -p $(TEST_BIN_DIR)

$(TEST_BIN_DIR)/test_phx_topology: tests/test_phx_topology.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

$(TEST_BIN_DIR)/test_phx_dcn_zerocopy: tests/test_phx_dcn_zerocopy.cpp src/phxaccel/accel/phx_dcn_zerocopy.h | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $< -o $@

$(TEST_BIN_DIR)/test_rdna3_discovery_uma: src/amd/rdna3_ip_discovery.cpp src/amd/rdna3_rebar_uma.cpp tests/test_rdna3_discovery_uma.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

$(TEST_BIN_DIR)/test_rdna3_ip_dcn: src/amd/rdna3_ip_blocks.cpp src/amd/rdna3_dcn314_scanout.cpp src/amd/rdna3_rebar_uma.cpp tests/test_rdna3_ip_dcn.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

$(TEST_BIN_DIR)/test_build34_dcn_page_layout: tests/test_build34_dcn_page_layout.cpp tools/build34_dcn_page_layout.h \
        tools/build34_dcn_descriptor_backing.h tools/build34_dcn_render_lease.h tools/build34_dcn_render_binding.h \
        tools/build34_dcn_render_tlb.h tools/build34_dcn_physical_pages.h \
        tests/build34_dcn/IOKit/IOMemoryDescriptor.h | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) -Itests/build34_dcn $< -o $@

$(TEST_BIN_DIR)/test_build34_dcn_flip_readback: tests/test_build34_dcn_flip_readback.cpp \
        tools/build34_dcn_firmware_home.h tools/build34_dcn_firmware_aperture.h tools/build34_dcn_flat_context.h \
        tools/build34_dcn_flip_program.h tools/build34_dcn_flip_geometry.h \
        tools/build34_dcn_flip_readback.h tools/build34_dcn_scanout_pin.h tools/build34_dcn_page_layout.h \
        tools/build34_dcn_render_lease.h tools/build34_dcn_descriptor_backing.h \
        tests/build34_dcn/IOKit/IOMemoryDescriptor.h src/amd/phx_dcn314_prog_regs.h | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) -Itests/build34_dcn $< -o $@

$(TEST_BIN_DIR)/test_rdna3_ucode: src/amd/rdna3_ucode_extract.cpp tests/test_rdna3_ucode.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

$(TEST_BIN_DIR)/test_r3n_abi: src/uapi/r3n_user_client.cpp src/winsys/radv_r3n_winsys.cpp tests/test_r3n_abi.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

test: $(TESTS)
	python3 -B tests/test_release_pci_matches.py
	python3 -B tests/test_render_surface_clear.py
	python3 -B tests/test_nmplugin_render_pass_integrity.py
	python3 -B tests/test_nmplugin_release_logging.py
	python3 -B tests/test_nmplugin_ws_mark_once.py
	python3 -B tests/test_nmplugin_multisample_copy_guard.py
	python3 -B tests/test_build34_wait_deadline.py
	python3 -B tests/test_build34_ring_backpressure.py
	python3 -B tests/test_build34_startup_recovery.py
	python3 -B tests/test_build34_startup_host.py
	python3 -B tests/test_build34_vbl_resume_host.py
	python3 -B tests/test_build34_acpi_resume_host.py
	python3 -B tests/test_build34_r1b_resume_host.py
	python3 -B tests/test_build34_ring_pressure_trace.py
	python3 -B tests/test_build34_ring_pressure_evidence.py
	python3 -B tests/test_build34_r3_wait_overlap.py
	python3 -B tests/test_build34_r3_eop_evidence.py
	python3 -B tests/test_build34_r3_writeback_layout.py
	python3 -B tests/test_build34_present_profile.py
	python3 -B tests/test_build34_present_copy.py
	CXX="$(CXX)" python3 -B tests/test_build34_dcn_render_map.py
	CXX="$(CXX)" python3 -B tests/test_build34_dcn_exact_writer.py
	python3 -B tests/test_build34_dcn_render_write.py
	python3 -B tests/test_build34_dcn_radv_binding.py
	python3 -B tests/test_build34_present_copy_host.py
	python3 -B tests/test_build34_map_observation.py
	python3 -B tests/test_build34_dcn_mapper_observation.py
	CXX="$(CXX)" python3 -B tests/test_build34_dcn_mapper_probe.py
	python3 -B tests/test_build34_dcn_route_observation.py
	python3 -B tests/test_build34_dcn_firmware_observation.py
	python3 -B tests/test_build34_dcn_firmware_observer_candidate.py
	python3 -B tests/test_build34_pci_irq_observation.py
	python3 -B tests/test_build34_pci_irq_candidate.py
	python3 -B tests/test_build34_pci_irq_scope.py
	python3 -B tests/test_build34_map_candidate.py
	python3 -B tests/test_build34_map_observer_host.py
	python3 -B tests/test_build34_exact_bootstrap_launcher.py
	python3 -B tests/test_build34_exact_bootstrap_once.py
	@echo "=== Running RDNA 3 Driver Unit Tests ==="
	@for t in $(TESTS); do \
		echo "Running $$t..."; \
		$$t || exit 1; \
	done
	@echo "All unit tests passed successfully!"

fixtures:
	bash tools/fetch_test_firmware.sh tests/fixtures/phoenix

R3_PREBOOT_PCI_OUT ?= $(TEST_BIN_DIR)/r3-preboot-pci

.PHONY: test-build34-r3-preboot-pci
test-build34-r3-preboot-pci:
	@test -r "$(R3_PREBOOT_EDK2_INCLUDE)/Uefi.h" || { echo "Set R3_PREBOOT_EDK2_INCLUDE to the pinned EDK II MdePkg/Include"; exit 1; }
	mkdir -p "$(R3_PREBOOT_PCI_OUT)"
	clang -std=c11 -O1 -g -Wall -Wextra -Werror -fshort-wchar '-DEFIAPI=__attribute__((ms_abi))' \
		-fsanitize=address,undefined -fno-sanitize-recover=all -isystem "$(R3_PREBOOT_EDK2_INCLUDE)" \
		-isystem "$(R3_PREBOOT_EDK2_INCLUDE)/X64" -Itools tools/build34_r3_preboot_pci.c \
		tests/test_build34_r3_preboot_pci.c -o "$(R3_PREBOOT_PCI_OUT)/test_preboot_pci"
	"$(R3_PREBOOT_PCI_OUT)/test_preboot_pci"
	clang -std=c11 -O1 -g -Wall -Wextra -Werror -fshort-wchar '-DEFIAPI=__attribute__((ms_abi))' \
		-fsanitize=address,undefined -fno-sanitize-recover=all -isystem "$(R3_PREBOOT_EDK2_INCLUDE)" \
		-isystem "$(R3_PREBOOT_EDK2_INCLUDE)/X64" -Itools tools/build34_r3_preboot_capture.c \
		tests/test_build34_r3_preboot_capture.c -o "$(R3_PREBOOT_PCI_OUT)/test_preboot_capture"
	"$(R3_PREBOOT_PCI_OUT)/test_preboot_capture"
	clang -target x86_64-pc-windows-msvc -std=c11 -O2 -Wall -Wextra -Werror -fshort-wchar \
		-ffreestanding -fno-builtin -fno-stack-protector -isystem "$(R3_PREBOOT_EDK2_INCLUDE)" \
		-isystem "$(R3_PREBOOT_EDK2_INCLUDE)/X64" -c tools/build34_r3_preboot_pci.c \
		-o "$(R3_PREBOOT_PCI_OUT)/attribution.obj"

kext:
	@echo "Building PhxBringup.kext..."
	python3 tools/build_kext.py

clean:
	rm -rf build/

.PHONY: test-upstream34-layout
test-upstream34-layout:
	python3 tests/test_upstream34_layout.py -v

# Actual integrated compute submit, with CPU fakes and no device frameworks.
.PHONY: test-upstream34-submit-memsync
test-upstream34-submit-memsync:
	python3 -B -m unittest discover -s tests -p test_upstream34_submit_memsync.py -v
	python3 -B tools/upstream34_layout/submit_memsync.py --out build/upstream34-submit-memsync-CPU-private

.PHONY: test-upstream34-mec-range
test-upstream34-mec-range:
	python3 -m unittest discover -s tests -p test_upstream34_mec_range_runner.py -v
	python3 tools/test_upstream34_mec_range.py --out build/upstream34-mec-range-host-private

.PHONY: test-upstream34-mec-runtime
test-upstream34-mec-runtime:
	python3 -m unittest discover -s tests -p test_upstream34_mec_runtime.py -v

.PHONY: test-upstream34-ib-preamble
test-upstream34-ib-preamble:
	python3 -m unittest discover -s tests -p test_upstream34_ib_preamble_runner.py -v
	python3 tools/test_upstream34_ib_preamble.py --out build/upstream34-ib-preamble-host-private

# Actual pinned Mesa source is required; this never links a GPU/IOKit backend.
.PHONY: test-upstream34-radv-ib-tail
test-upstream34-radv-ib-tail:
	@test -n "$(MESA_SOURCE)" || (echo "Set MESA_SOURCE to the verified matching Mesa source"; exit 2)
	python3 tools/test_build34_radv_ib_tail.py --mesa-source "$(MESA_SOURCE)" --out build/upstream34-radv-ib-tail-host-private

# Pinned actual Mesa sync provider, CPU callbacks only; no native/GPU backend.
.PHONY: test-build34-exact-completion
test-build34-exact-completion:
	@test -n "$(MESA_SOURCE)" || (echo "Set MESA_SOURCE to the verified matching Mesa source"; exit 2)
	@test -n "$(EXACT_COMPLETION_OUT)" || (echo "Set EXACT_COMPLETION_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_completion.py --mesa-source "$(MESA_SOURCE)" --out "$(EXACT_COMPLETION_OUT)"

# Separate source-only R3 sweep prerequisite; no production opt-in or GPU work.
.PHONY: test-build34-exact-multitarget
test-build34-exact-multitarget:
	@test -n "$(MESA_SOURCE)" || (echo "Set MESA_SOURCE to the verified matching Mesa source"; exit 2)
	@test -n "$(EXACT_MULTITARGET_OUT)" || (echo "Set EXACT_MULTITARGET_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_multitarget.py --mesa-source "$(MESA_SOURCE)" --out "$(EXACT_MULTITARGET_OUT)"

.PHONY: test-build34-exact-cs-dependencies
test-build34-exact-cs-dependencies:
	@test -n "$(MESA_SOURCE)" || (echo "Set MESA_SOURCE to the verified matching Mesa source"; exit 2)
	@test -n "$(EXACT_CS_OUT)" || (echo "Set EXACT_CS_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_cs_dependencies.py --mesa-source "$(MESA_SOURCE)" --out "$(EXACT_CS_OUT)"

# Unintegrated native ownership contract prototype; no driver/GPU execution.
.PHONY: test-build34-exact-ownership
test-build34-exact-ownership:
	@test -n "$(EXACT_OWNERSHIP_OUT)" || (echo "Set EXACT_OWNERSHIP_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_ownership.py --out "$(EXACT_OWNERSHIP_OUT)"

# Staged real native callsites, CPU doubles only; never builds a kernel image.
.PHONY: test-build34-exact-submit
test-build34-exact-submit:
	@test -n "$(EXACT_SUBMIT_OUT)" || (echo "Set EXACT_SUBMIT_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_submit.py --out "$(EXACT_SUBMIT_OUT)"

# Actual staged power/stop/wave-kill invalidation; CPU doubles, no kext build.
.PHONY: test-build34-exact-lifecycle
test-build34-exact-lifecycle:
	@test -n "$(EXACT_LIFECYCLE_OUT)" || (echo "Set EXACT_LIFECYCLE_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_lifecycle.py --out "$(EXACT_LIFECYCLE_OUT)"

# Selected native callback lifetimes and non-reclaiming stop; CPU threads only.
.PHONY: test-build34-exact-callbacks
test-build34-exact-callbacks:
	@test -n "$(EXACT_CALLBACKS_OUT)" || (echo "Set EXACT_CALLBACKS_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_callbacks.py --out "$(EXACT_CALLBACKS_OUT)"

# Staged exact client closure/BO retention; finite CPU doubles, no kext build.
.PHONY: test-build34-exact-client-lifetime
test-build34-exact-client-lifetime:
	@test -n "$(EXACT_CLIENT_OUT)" || (echo "Set EXACT_CLIENT_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_client_lifetime.py --out "$(EXACT_CLIENT_OUT)"

# Staged target observation; reader injection is CPU-only, default hardware binding absent.
.PHONY: test-build34-exact-observer
test-build34-exact-observer:
	@test -n "$(EXACT_OBSERVER_OUT)" || (echo "Set EXACT_OBSERVER_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_observer.py --out "$(EXACT_OBSERVER_OUT)"

# Embedded registry/provider binding; CPU-only, no native request or kext build.
.PHONY: test-build34-exact-binding
test-build34-exact-binding:
	@test -n "$(EXACT_BINDING_OUT)" || (echo "Set EXACT_BINDING_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_binding.py --out "$(EXACT_BINDING_OUT)"

# Staged owned-ticket wait fallback; CPU-only, no native selector or hardware reader.
.PHONY: test-build34-exact-wait
test-build34-exact-wait:
	@test -n "$(EXACT_WAIT_OUT)" || (echo "Set EXACT_WAIT_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_wait.py --out "$(EXACT_WAIT_OUT)"

# Original low-dword reconstruction arithmetic; no native or device reader.
.PHONY: test-build34-exact-fence32
test-build34-exact-fence32:
	@test -n "$(EXACT_FENCE32_OUT)" || (echo "Set EXACT_FENCE32_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_fence32.py --out "$(EXACT_FENCE32_OUT)"

# Wait-pinned receipt acknowledgement; CPU-only, no native selector or reclaimer.
.PHONY: test-build34-exact-ack
test-build34-exact-ack:
	@test -n "$(EXACT_ACK_OUT)" || (echo "Set EXACT_ACK_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_ack.py --out "$(EXACT_ACK_OUT)"

# Proposed exact-mode CS shapes; actual Mesa call chain with CPU ops only.
.PHONY: test-build34-exact-cs-shape
test-build34-exact-cs-shape:
	@test -n "$(MESA_SOURCE)" -a -n "$(EXACT_CS_SHAPE_OUT)" || (echo "Set MESA_SOURCE and fresh EXACT_CS_SHAPE_OUT"; exit 2)
	python3 -B tools/test_build34_exact_cs_shape.py --mesa-source "$(MESA_SOURCE)" --out "$(EXACT_CS_SHAPE_OUT)"

# Actual Mesa completion/ACK cache with CPU session callbacks, no native binding.
.PHONY: test-build34-exact-transport
test-build34-exact-transport:
	@test -n "$(MESA_SOURCE)" -a -n "$(EXACT_TRANSPORT_OUT)" || (echo "Set MESA_SOURCE and fresh EXACT_TRANSPORT_OUT"; exit 2)
	python3 -B tools/test_build34_exact_transport.py --mesa-source "$(MESA_SOURCE)" --out "$(EXACT_TRANSPORT_OUT)"

.PHONY: test-build34-r3-mesa-wire
test-build34-r3-mesa-wire:
	@test -n "$(MESA_SOURCE)" -a -n "$(R3_MESA_WIRE_OUT)" || (echo "Set MESA_SOURCE and fresh R3_MESA_WIRE_OUT"; exit 2)
	python3 -B tools/test_build34_r3_mesa_wire.py --mesa-source "$(MESA_SOURCE)" --out "$(R3_MESA_WIRE_OUT)"

.PHONY: test-build34-r3-mesa-iokit
test-build34-r3-mesa-iokit:
	@test -n "$(MESA_SOURCE)" -a -n "$(R3_MESA_IOKIT_OUT)" || (echo "Set MESA_SOURCE and fresh R3_MESA_IOKIT_OUT"; exit 2)
	python3 -B tools/test_build34_r3_mesa_wire.py --iokit --mesa-source "$(MESA_SOURCE)" --out "$(R3_MESA_IOKIT_OUT)"

.PHONY: test-build34-r3-mesa-drm
test-build34-r3-mesa-drm:
	@test -n "$(MESA_SOURCE)" -a -n "$(R3_MESA_DRM_OUT)" || (echo "Set MESA_SOURCE and fresh R3_MESA_DRM_OUT"; exit 2)
	python3 -B tools/test_build34_r3_mesa_wire.py --drm --mesa-source "$(MESA_SOURCE)" --out "$(R3_MESA_DRM_OUT)"

.PHONY: test-build34-r3-mesa-exact-open
test-build34-r3-mesa-exact-open:
	@test -n "$(MESA_SOURCE)" -a -n "$(R3_MESA_EXACT_OPEN_OUT)" || (echo "Set MESA_SOURCE and fresh R3_MESA_EXACT_OPEN_OUT"; exit 2)
	python3 -B tools/test_build34_r3_mesa_wire.py --exact-open --mesa-source "$(MESA_SOURCE)" --out "$(R3_MESA_EXACT_OPEN_OUT)"

.PHONY: test-build34-r3-radv-entry
test-build34-r3-radv-entry:
	@test -n "$(MESA_SOURCE)" -a -n "$(R3_RADV_ENTRY_OUT)" || (echo "Set MESA_SOURCE and fresh R3_RADV_ENTRY_OUT"; exit 2)
	python3 -B tools/test_build34_r3_mesa_wire.py --radv-entry --mesa-source "$(MESA_SOURCE)" --out "$(R3_RADV_ENTRY_OUT)"

# Staged native full-receipt dispatch with C peer, CPU objects only.
.PHONY: test-build34-exact-receipt
test-build34-exact-receipt:
	@test -n "$(EXACT_RECEIPT_OUT)" || (echo "Set EXACT_RECEIPT_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_receipt.py --out "$(EXACT_RECEIPT_OUT)"

# Source-only complete-token submit/wait/ACK with CPU objects; never a kext.
.PHONY: test-build34-exact-submit-receipt
test-build34-exact-submit-receipt:
	@test -n "$(EXACT_SUBMIT_RECEIPT_OUT)" || (echo 'Set EXACT_SUBMIT_RECEIPT_OUT to a fresh ignored -private build directory'; exit 2)
	python3 -B tools/test_build34_exact_submit_receipt.py --out "$(EXACT_SUBMIT_RECEIPT_OUT)"

# Staged raw-dword/window callsites with CPU bytes, never device or kernel code.
.PHONY: test-build34-exact-window
test-build34-exact-window:
	@test -n "$(EXACT_WINDOW_OUT)" || (echo 'Set EXACT_WINDOW_OUT to a fresh ignored -private build directory'; exit 2)
	python3 -B tools/test_build34_exact_window.py --out "$(EXACT_WINDOW_OUT)"

# A1 CPU-only regressions. These targets never load the plugin or submit GPU work.
$(TEST_BIN_DIR)/test_nmplugin_sampler_key: tests/test_nmplugin_sampler_key.m src/nmplugin/nvmtl_sampler_key.h Makefile | $(TEST_BIN_DIR)
	xcrun clang -O1 -g -Wall -Wextra -Werror -fobjc-arc -fblocks \
		-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer \
		tests/test_nmplugin_sampler_key.m -framework Foundation -o $@

.PHONY: test-nmplugin-sampler-key test-nmplugin-surface-key test-nmplugin-descriptor-mask
test-nmplugin-sampler-key: $(TEST_BIN_DIR)/test_nmplugin_sampler_key
	./$(TEST_BIN_DIR)/test_nmplugin_sampler_key

test-nmplugin-surface-key:
	python3 tests/test_nmplugin_surface_key.py

test-nmplugin-descriptor-mask:
	python3 tests/test_nmplugin_descriptor_mask.py

# Narrow plugin PR backports: Foundation/POSIX only, no Metal device creation.
.PHONY: test-upstream34-plugin-prs
test-upstream34-plugin-prs:
	python3 tests/test_upstream34_plugin_prs.py

.PHONY: test-nmplugin-surface-commit-wait
test-nmplugin-surface-commit-wait:
	python3 tests/test_nmplugin_surface_commit_wait.py

.PHONY: test-nmplugin-release-logging
test-nmplugin-release-logging:
	python3 -B tests/test_nmplugin_release_logging.py

# Extracted production wait method with CPU-only clocks/fences; no IOKit backend.
.PHONY: test-build34-wait-deadline
test-build34-wait-deadline:
	python3 -B tests/test_build34_wait_deadline.py

.PHONY: test-nmplugin-render-surface-clear
test-nmplugin-render-surface-clear:
	python3 -B tests/test_render_surface_clear.py

.PHONY: test-nmplugin-render-pass-integrity
test-nmplugin-render-pass-integrity:
	python3 -B tests/test_nmplugin_render_pass_integrity.py

$(TEST_BIN_DIR)/test_upstream34_alias_policy: tests/test_upstream34_alias_policy.cpp src/phxaccel/PhxHardwarePolicy.hpp Makefile | $(TEST_BIN_DIR)
	$(CXX) -std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined \
		-fno-sanitize-recover=all -fno-omit-frame-pointer $< -o $@

.PHONY: test-upstream34-framebuffer
test-upstream34-framebuffer: $(TEST_BIN_DIR)/test_upstream34_alias_policy
	./$(TEST_BIN_DIR)/test_upstream34_alias_policy
	python3 tests/test_upstream34_framebuffer.py

$(TEST_BIN_DIR)/test_upstream34_panel_timing: tests/test_upstream34_panel_timing.cpp src/phxaccel/accel/phx_panel_timing.h Makefile | $(TEST_BIN_DIR)
	$(CXX) -std=c++17 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined \
		-fno-sanitize-recover=all -fno-omit-frame-pointer $< -o $@

.PHONY: test-upstream34-panel-timing
test-upstream34-panel-timing: $(TEST_BIN_DIR)/test_upstream34_panel_timing
	./$(TEST_BIN_DIR)/test_upstream34_panel_timing
	python3 tests/test_upstream34_panel_callbacks.py

.PHONY: check-build34-scanout-mode
check-build34-scanout-mode:
	xcrun swift tools/build34_scanout_mode_gate.swift

# CPU clock/scheduler doubles only; never initializes or submits to a GPU.
.PHONY: test-build34-vbl-scheduling
test-build34-vbl-scheduling:
	python3 -B tests/test_build34_vbl_scheduling.py

# Read-only complete-cache policy comparison; no installation or GPU use.
.PHONY: test-build34-cache-metadata
test-build34-cache-metadata:
	python3 -B tests/test_build34_cache_metadata.py

# Source-only R3 global snapshot and actual VMID methods; CPU doubles only.
.PHONY: test-build34-exact-global
test-build34-exact-global:
	@test -n "$(EXACT_GLOBAL_OUT)" || (echo "Set EXACT_GLOBAL_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_global.py --out "$(EXACT_GLOBAL_OUT)"

# Actual staged VM lifecycle methods with CPU IOKit/page-walker/register doubles.
.PHONY: test-build34-exact-vm-lifetime
test-build34-exact-vm-lifetime:
	@test -n "$(EXACT_VM_OUT)" || (echo "Set EXACT_VM_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_vm_lifetime.py --out "$(EXACT_VM_OUT)"

.PHONY: test-build34-exact-bo-lifetime
test-build34-exact-bo-lifetime:
	@test -n "$(EXACT_BO_OUT)" || (echo "Set EXACT_BO_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_bo_lifetime.py --out "$(EXACT_BO_OUT)"

.PHONY: test-build34-exact-legacy-close
test-build34-exact-legacy-close:
	@test -n "$(EXACT_CLOSE_OUT)" || (echo "Set EXACT_CLOSE_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_legacy_close.py --out "$(EXACT_CLOSE_OUT)"

.PHONY: test-build34-exact-close
test-build34-exact-close:
	@test -n "$(EXACT_CLIENT_CLOSE_OUT)" || (echo "Set EXACT_CLIENT_CLOSE_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_close.py --out "$(EXACT_CLIENT_CLOSE_OUT)"

.PHONY: test-build34-exact-cpu-fences
test-build34-exact-cpu-fences:
	@test -n "$(EXACT_CPU_FENCES_OUT)" || (echo "Set EXACT_CPU_FENCES_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_cpu_fences.py --out "$(EXACT_CPU_FENCES_OUT)"

.PHONY: test-build34-exact-watchdog
test-build34-exact-watchdog:
	@test -n "$(EXACT_WATCHDOG_OUT)" || (echo "Set EXACT_WATCHDOG_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_watchdog.py --out "$(EXACT_WATCHDOG_OUT)"

.PHONY: test-build34-exact-service-timer
test-build34-exact-service-timer:
	@test -n "$(EXACT_SERVICE_TIMER_OUT)" || (echo "Set EXACT_SERVICE_TIMER_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_service_timer.py --out "$(EXACT_SERVICE_TIMER_OUT)"

# Complete native source/object check only; private timer KPI admission must refuse.
.PHONY: test-build34-exact-native-sdk
test-build34-exact-native-sdk:
	@test -n "$(KERNEL_SDK)" || (echo "Set KERNEL_SDK to the reviewed matching SDK checkout"; exit 2)
	@test -n "$(KDK)" || (echo "Set KDK to the current OS version/build's KDK"; exit 2)
	@test -n "$(EXACT_NATIVE_SDK_OUT)" || (echo "Set EXACT_NATIVE_SDK_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_native_sdk.py --sdk "$(KERNEL_SDK)" --kdk "$(KDK)" --out "$(EXACT_NATIVE_SDK_OUT)"

# Public timer CPU/native-object prerequisite only, never a kernel candidate.
.PHONY: test-build34-exact-public-timer
test-build34-exact-public-timer:
	@test -n "$(KERNEL_SDK)" || (echo "Set KERNEL_SDK to the reviewed matching SDK checkout"; exit 2)
	@test -n "$(KDK)" || (echo "Set KDK to the current OS version/build's KDK"; exit 2)
	@test -n "$(EXACT_PUBLIC_TIMER_OUT)" || (echo "Set EXACT_PUBLIC_TIMER_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_public_timer.py --sdk "$(KERNEL_SDK)" --kdk "$(KDK)" --out "$(EXACT_PUBLIC_TIMER_OUT)"

# Raw-debug/queue ownership CPU/native-object prerequisite, never a kernel candidate.
.PHONY: test-build34-exact-raw-handoff
test-build34-exact-raw-handoff:
	@test -n "$(KERNEL_SDK)" || (echo "Set KERNEL_SDK to the reviewed SDK checkout"; exit 2)
	@test -n "$(KDK)" || (echo "Set KDK to the current OS version/build's KDK"; exit 2)
	@test -n "$(EXACT_RAW_HANDOFF_OUT)" || (echo "Set EXACT_RAW_HANDOFF_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_raw_handoff.py --sdk "$(KERNEL_SDK)" --kdk "$(KDK)" --out "$(EXACT_RAW_HANDOFF_OUT)"

# Native-factory CPU/native-object prerequisite only; no deployment or GPU work.
.PHONY: test-build34-exact-factory
test-build34-exact-factory:
	@test -n "$(KERNEL_SDK)" || (echo "Set KERNEL_SDK to the reviewed SDK checkout"; exit 2)
	@test -n "$(KDK)" || (echo "Set KDK to the current OS version/build's KDK"; exit 2)
	@test -n "$(EXACT_FACTORY_OUT)" || (echo "Set EXACT_FACTORY_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_exact_factory.py --sdk "$(KERNEL_SDK)" --kdk "$(KDK)" --out "$(EXACT_FACTORY_OUT)"

.PHONY: test-build34-exact-open
test-build34-exact-open:
	@test -n "$(KERNEL_SDK)" -a -n "$(KDK)" -a -n "$(EXACT_OPEN_OUT)" || (echo "Set KERNEL_SDK, KDK and fresh EXACT_OPEN_OUT"; exit 2)
	python3 -B tools/test_build34_exact_open.py --sdk "$(KERNEL_SDK)" --kdk "$(KDK)" --out "$(EXACT_OPEN_OUT)"

# Mapper resolver header compile only; produces a nonloadable SDK object.
.PHONY: test-build34-dcn-mapper-native
test-build34-dcn-mapper-native:
	@test -n "$(KERNEL_SDK)" -a -n "$(KDK)" -a -n "$(DCN_MAPPER_NATIVE_OUT)" || (echo "Set KERNEL_SDK, KDK and fresh DCN_MAPPER_NATIVE_OUT"; exit 2)
	python3 -B tools/test_build34_dcn_mapper_probe_native.py --sdk "$(KERNEL_SDK)" --kdk "$(KDK)" --out "$(DCN_MAPPER_NATIVE_OUT)"

# Passive mapping-metadata preparation only; never a kernel candidate/GPU test.
.PHONY: test-build34-map-observation
test-build34-map-observation:
	@test -n "$(KERNEL_SDK)" || (echo "Set KERNEL_SDK to the reviewed SDK checkout"; exit 2)
	@test -n "$(KDK)" || (echo "Set KDK to the current OS version/build's KDK"; exit 2)
	@test -n "$(MAP_OBSERVATION_OUT)" || (echo "Set MAP_OBSERVATION_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/test_build34_map_observation.py --sdk "$(KERNEL_SDK)" --kdk "$(KDK)" --out "$(MAP_OBSERVATION_OUT)"

# Mapping-only observer on accepted R1b; offline build, no installation/GPU work.
.PHONY: build-build34-map-candidate
build-build34-map-candidate:
	@test -n "$(KERNEL_SDK)" || (echo "Set KERNEL_SDK to the reviewed SDK checkout"; exit 2)
	@test -n "$(MAP_CANDIDATE_OUT)" || (echo "Set MAP_CANDIDATE_OUT to a fresh private worktree build path"; exit 2)
	python3 -B tools/build34_map_candidate.py --sdk "$(KERNEL_SDK)" --out "$(MAP_CANDIDATE_OUT)"
