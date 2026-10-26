CXX := clang++
CXXFLAGS := -std=c++20 -Wall -Wextra -Wpedantic -O2 -g -Icore/include -Icore/src
CORE := core/src/cpu.cpp core/src/machine.cpp core/src/audio.cpp core/src/api.cpp
DOS_BUILD ?= .build/dos-command-editor-v2
DOS_LIBRARIES ?= original
DOS_SHELL ?= enhanced
APPLE_BUILD ?= .build/apple-speed-control
BUILD_CONFIGURATION ?= Release
MOUSE_BUILD ?= .build/cutemouse-build
DOS_SEED ?=
DOS_SEED_BUILD ?= .build/dos-full-build
.PHONY: all test input-tests ui-state-tests hardware bootstrap dos mouse guests guest-tests packaging-tests mac ios clean
all: .build/p86 .build/libproject86.dylib
.build:
	mkdir -p .build
.build/p86: $(CORE) cli/main.cpp core/src/machine.hpp core/include/project86.h | .build
	$(CXX) $(CXXFLAGS) $(CORE) cli/main.cpp -o $@
.build/libproject86.dylib: $(CORE) core/src/machine.hpp core/include/project86.h | .build
	$(CXX) $(CXXFLAGS) -fPIC -dynamiclib $(CORE) -o $@
.build/core-tests: $(CORE) tests/core_tests.cpp core/src/machine.hpp core/include/project86.h | .build
	$(CXX) $(CXXFLAGS) $(CORE) tests/core_tests.cpp -o $@
.build/device-tests: $(CORE) tests/device_tests.cpp core/src/machine.hpp core/include/project86.h | .build
	$(CXX) $(CXXFLAGS) $(CORE) tests/device_tests.cpp -o $@
test: .build/core-tests .build/device-tests
	.build/core-tests
	.build/device-tests
.build/mouse-input-tests: apple/Project86/MouseInput.swift tests/mouse_input_tests.swift | .build
	swiftc -O $^ -o $@
input-tests: .build/mouse-input-tests
	.build/mouse-input-tests
.build/frame-observation-tests: apple/Project86/MouseInput.swift apple/Project86/EmulatorModel.swift tests/frame_observation_tests.swift .build/libproject86.dylib core/include/project86.h | .build
	swiftc -O -swift-version 5 -import-objc-header core/include/project86.h apple/Project86/MouseInput.swift apple/Project86/EmulatorModel.swift tests/frame_observation_tests.swift .build/libproject86.dylib -o $@
.build/cpu-speed-control-tests: apple/Project86/CPUSpeedControl.swift tests/cpu_speed_control_tests.swift | .build
	swiftc -O -swift-version 5 $^ -o $@
ui-state-tests: .build/frame-observation-tests .build/cpu-speed-control-tests
	.build/frame-observation-tests --demo
	.build/cpu-speed-control-tests
hardware: .build/libproject86.dylib
	python3 scripts/hardware_tests.py
bootstrap:
	python3 scripts/fetch_bootstrap.py
dos: .build/p86
	python3 scripts/rebuild_dos.py --ensure --fetch --libraries "$(DOS_LIBRARIES)" --shell "$(DOS_SHELL)" --output "$(DOS_BUILD)" $(if $(DOS_SEED),--seed "$(DOS_SEED)" --seed-build "$(DOS_SEED_BUILD)")
mouse:
	python3 scripts/rebuild_cutemouse.py --ensure --output "$(MOUSE_BUILD)"
guests: dos mouse
	python3 scripts/fetch_bootstrap.py --source-only
	python3 scripts/prepare_guests.py --dos-build "$(DOS_BUILD)" --mouse-build "$(MOUSE_BUILD)"
guest-tests: all guests
	python3 scripts/test_guests.py --dos-build "$(DOS_BUILD)" --mouse-build "$(MOUSE_BUILD)"
packaging-tests: guests all
	P86_DOS_BUILD_DIR="$(abspath $(DOS_BUILD))" P86_MOUSE_BUILD_DIR="$(abspath $(MOUSE_BUILD))" python3 -m unittest discover -s tests -p 'test_*.py' -v
mac: guests
	xcodegen generate
	xcodebuild -project Project86.xcodeproj -scheme Project86Mac -configuration "$(BUILD_CONFIGURATION)" -derivedDataPath "$(APPLE_BUILD)" CODE_SIGNING_ALLOWED=NO P86_DOS_BUILD_DIR="$(abspath $(DOS_BUILD))" P86_MOUSE_BUILD_DIR="$(abspath $(MOUSE_BUILD))" build
ios: guests
	xcodegen generate
	xcodebuild -project Project86.xcodeproj -scheme Project86iPad -configuration "$(BUILD_CONFIGURATION)" -sdk iphonesimulator -derivedDataPath "$(APPLE_BUILD)" CODE_SIGNING_ALLOWED=NO P86_DOS_BUILD_DIR="$(abspath $(DOS_BUILD))" P86_MOUSE_BUILD_DIR="$(abspath $(MOUSE_BUILD))" build
clean:
	rm -rf .build
