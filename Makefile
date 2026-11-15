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
