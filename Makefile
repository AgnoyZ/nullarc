# Makefile for AMD RDNA 3 (Radeon 780M) macOS Driver Project

CXX ?= clang++
CXXFLAGS ?= -std=c++17 -Wall -Wextra -Werror -O2
INCLUDES = -Isrc -Isrc/amd -Isrc/uapi -Isrc/winsys

TEST_BIN_DIR = build/tests
TESTS = $(TEST_BIN_DIR)/test_rdna3_discovery_uma \
        $(TEST_BIN_DIR)/test_rdna3_ip_dcn \
        $(TEST_BIN_DIR)/test_rdna3_ucode \
        $(TEST_BIN_DIR)/test_r3n_abi \
        $(TEST_BIN_DIR)/test_phx_topology

.PHONY: all test clean kext fixtures

all: test

$(TEST_BIN_DIR):
	mkdir -p $(TEST_BIN_DIR)

$(TEST_BIN_DIR)/test_phx_topology: tests/test_phx_topology.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

$(TEST_BIN_DIR)/test_rdna3_discovery_uma: src/amd/rdna3_ip_discovery.cpp src/amd/rdna3_rebar_uma.cpp tests/test_rdna3_discovery_uma.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

$(TEST_BIN_DIR)/test_rdna3_ip_dcn: src/amd/rdna3_ip_blocks.cpp src/amd/rdna3_dcn314_scanout.cpp src/amd/rdna3_rebar_uma.cpp tests/test_rdna3_ip_dcn.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

$(TEST_BIN_DIR)/test_rdna3_ucode: src/amd/rdna3_ucode_extract.cpp tests/test_rdna3_ucode.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

$(TEST_BIN_DIR)/test_r3n_abi: src/uapi/r3n_user_client.cpp src/winsys/radv_r3n_winsys.cpp tests/test_r3n_abi.cpp | $(TEST_BIN_DIR)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $^ -o $@

test: $(TESTS)
	python3 -B tests/test_release_pci_matches.py
	python3 -B tests/test_render_surface_clear.py
	python3 -B tests/test_nmplugin_render_pass_integrity.py
	python3 -B tests/test_nmplugin_release_logging.py
	python3 -B tests/test_build34_wait_deadline.py
	python3 -B tests/test_build34_ring_backpressure.py
	python3 -B tests/test_build34_startup_recovery.py
	python3 -B tests/test_build34_startup_host.py
	python3 -B tests/test_build34_vbl_resume_host.py
	python3 -B tests/test_build34_acpi_resume_host.py
	python3 -B tests/test_build34_r1b_resume_host.py
	python3 -B tests/test_build34_ring_pressure_trace.py
	python3 -B tests/test_build34_ring_pressure_evidence.py
	@echo "=== Running RDNA 3 Driver Unit Tests ==="
	@for t in $(TESTS); do \
		echo "Running $$t..."; \
		$$t || exit 1; \
	done
	@echo "All unit tests passed successfully!"

fixtures:
	bash tools/fetch_test_firmware.sh tests/fixtures/phoenix

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

# CPU clock/scheduler doubles only; never initializes or submits to a GPU.
.PHONY: test-build34-vbl-scheduling
test-build34-vbl-scheduling:
	python3 -B tests/test_build34_vbl_scheduling.py

# Read-only complete-cache policy comparison; no installation or GPU use.
.PHONY: test-build34-cache-metadata
test-build34-cache-metadata:
	python3 -B tests/test_build34_cache_metadata.py
