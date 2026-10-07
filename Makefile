CXX ?= g++
PKGS = hyprland lua5.4 egl glesv2 pangocairo
CPPFLAGS += $(shell pkg-config --cflags $(PKGS))
CXXFLAGS += -std=c++23 -O2 -g -fPIC -fno-gnu-unique -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers
LDLIBS += $(shell pkg-config --libs $(PKGS))
SOURCES = src/main.cpp src/Flow.cpp src/FlowRenderer.cpp src/Capture.cpp src/Config.cpp
OBJECTS = $(SOURCES:src/%.cpp=build/%.o)

.PHONY: all test check format-check
all: build/hyprflow.so

build:
	mkdir -p build

build/%.o: src/%.cpp | build
	$(CXX) $(CPPFLAGS) $(CXXFLAGS) -MMD -MP -c $< -o $@

build/hyprflow.so: $(OBJECTS)
	$(CXX) -shared $(OBJECTS) $(LDLIBS) -o $@

build/motion-tests: tests/motion.cpp src/Motion.hpp | build
	$(CXX) -std=c++23 -O2 -Wall -Wextra -Werror -Isrc $< -o $@

test: build/motion-tests
	./build/motion-tests

format-check:
	clang-format --dry-run --Werror src/*.cpp src/*.hpp tests/*.cpp

check: all test
	python3 -m py_compile scripts/*.py
	cppcheck --enable=warning,performance,portability --error-exitcode=1 --std=c++23 --suppress=missingIncludeSystem src tests

-include $(OBJECTS:.o=.d)
