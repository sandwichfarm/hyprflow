CXX ?= g++
VULKAN ?= 0
ifeq ($(VULKAN),1)
BUILD_DIR ?= build-vulkan
else
BUILD_DIR ?= build
endif
PKGS = hyprland lua5.4 egl glesv2 pangocairo
CPPFLAGS += $(EXTRA_CPPFLAGS) $(shell pkg-config --cflags $(PKGS))
CXXFLAGS += -std=c++23 -O2 -g -fPIC -fno-gnu-unique -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers
# Avoid loading unused compositor dependencies before the plugin's ABI guard can run.
LDFLAGS += -Wl,--as-needed
LDLIBS += $(shell pkg-config --libs $(PKGS))
SOURCES = src/main.cpp src/Flow.cpp src/FlowRenderer.cpp src/Capture.cpp src/Config.cpp
ifeq ($(VULKAN),1)
CPPFLAGS += -DHYPRFLOW_VULKAN
LDLIBS += -lvulkan
SOURCES := $(filter-out src/FlowRenderer.cpp,$(SOURCES)) src/FlowRendererVulkan.cpp
endif
OBJECTS = $(patsubst src/%.cpp,$(BUILD_DIR)/%.o,$(SOURCES))

.PHONY: all test check format-check
all: $(BUILD_DIR)/hyprflow.so

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: src/%.cpp | $(BUILD_DIR)
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -MMD -MP -c $< -o $@

$(BUILD_DIR)/hyprflow.so: $(OBJECTS)
	$(CXX) -shared $(LDFLAGS) $(OBJECTS) $(LDLIBS) -o $@

$(BUILD_DIR)/motion-tests: tests/motion.cpp src/Motion.hpp | $(BUILD_DIR)
	$(CXX) -std=c++23 -O2 -Wall -Wextra -Werror -Isrc $< -o $@

test: $(BUILD_DIR)/motion-tests
	./$(BUILD_DIR)/motion-tests

format-check:
	clang-format --dry-run --Werror src/*.cpp src/*.hpp tests/*.cpp

check: all test
	python3 -m py_compile scripts/*.py
	cppcheck --enable=warning,performance,portability --error-exitcode=1 --std=c++23 --suppress=missingIncludeSystem src tests

-include $(OBJECTS:.o=.d)
