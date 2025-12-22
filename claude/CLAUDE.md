# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build System

ArduPilot uses the Waf build system. Always run `./waf` from the repository root.

### Common Build Commands

```bash
# Configure for a target board (required before first build or when switching boards)
./waf configure --board sitl              # SITL simulator (most common for development)
./waf configure --board sitl --debug      # SITL with debug symbols
./waf configure --board CubeOrange        # Hardware target example

# Build vehicles
./waf copter                              # Build ArduCopter (all multirotor types)
./waf plane                               # Build ArduPlane
./waf rover                               # Build Rover
./waf sub                                 # Build ArduSub
./waf heli                                # Build helicopter variant
./waf AP_Periph                           # Build AP Peripheral firmware

# Build specific target
./waf --targets bin/arducopter            # Single vehicle binary
./waf --targets tests/test_math           # Single test

# List available boards
./waf list_boards

# Run unit tests
./waf configure --board sitl
./waf tests                               # Build all tests
./waf check                               # Build and run tests that changed
./waf check-all                           # Build and run all tests

# Clean builds
./waf clean                               # Clean current board
./waf distclean                           # Clean everything

# Upload to connected board
./waf --targets bin/arducopter --upload

# Generate compile_commands.json for IDE support
./waf configure --board sitl && ./waf --compdb

# Advanced build options
./waf configure --board sitl --enable-littlefs   # Enable LittleFS filesystem
./waf configure --board sitl --enable-DDS        # Enable ROS2/DDS integration
./waf configure --board sitl --consistent-builds # Force version consistency
```

### Running SITL Simulation

```bash
# Start SITL simulator with MAVProxy
Tools/autotest/sim_vehicle.py -v ArduCopter           # Copter
Tools/autotest/sim_vehicle.py -v ArduPlane            # Plane
Tools/autotest/sim_vehicle.py -v Rover                # Rover
Tools/autotest/sim_vehicle.py -v ArduCopter --debug   # With GDB

# Multi-instance SITL (for swarm/multi-vehicle testing)
Tools/autotest/sim_vehicle.py -v ArduCopter -I 0      # First instance
Tools/autotest/sim_vehicle.py -v ArduCopter -I 1      # Second instance (different port)
```

### Running Autotest Suite

```bash
# Run specific vehicle tests
Tools/autotest/autotest.py build.Copter test.Copter
Tools/autotest/autotest.py build.Plane test.Plane
```

## Architecture Overview

### Vehicle Directories

- `ArduCopter/` - Multicopter and helicopter firmware
- `ArduPlane/` - Fixed-wing aircraft firmware
- `Rover/` - Ground vehicle and boat firmware
- `ArduSub/` - Underwater ROV firmware
- `AntennaTracker/` - Antenna tracking firmware
- `Blimp/` - Blimp firmware
- `Tools/AP_Periph/` - CAN peripheral firmware

Each vehicle has a main class (e.g., `Copter`, `Plane`) that inherits from `AP_Vehicle` and implements vehicle-specific behavior including flight modes in `mode_*.cpp` files.

### Hardware Abstraction Layer (HAL)

The `libraries/AP_HAL/` defines the hardware abstraction interface. All hardware interactions go through AP_HAL, making core flight code portable across boards. Platform-specific implementations:

- `AP_HAL_ChibiOS/` - STM32 microcontrollers (most flight controllers)
- `AP_HAL_Linux/` - Linux-based boards (Raspberry Pi, BeagleBone, etc.)
- `AP_HAL_SITL/` - Software-in-the-loop simulator
- `AP_HAL_ESP32/` - ESP32 microcontrollers

### Key Libraries (in `libraries/`)

**Sensor/IO Libraries:**
- `AP_InertialSensor/` - IMU handling
- `AP_Baro/` - Barometer
- `AP_GPS/` - GPS receivers
- `AP_Compass/` - Magnetometer
- `AP_RangeFinder/` - Distance sensors
- `AP_OpticalFlow/` - Optical flow sensors

**Navigation/Control:**
- `AP_AHRS/` - Attitude and Heading Reference System
- `AP_NavEKF2/`, `AP_NavEKF3/` - Extended Kalman Filter implementations
- `AC_AttitudeControl/` - Attitude controllers
- `AC_PosControl/` - Position controller
- `AC_WPNav/` - Waypoint navigation
- `AP_Mission/` - Mission handling

**Communication:**
- `GCS_MAVLink/` - MAVLink protocol implementation
- `AP_SerialManager/` - Serial port management

**Utilities:**
- `AP_Math/` - Math utilities, vectors, matrices, quaternions
- `AP_Param/` - Parameter system
- `AP_Scheduler/` - Task scheduler
- `AP_Logger/` - DataFlash logging

**Scripting & External Integration:**
- `AP_Scripting/` - Lua scripting engine (see `libraries/AP_Scripting/CLAUDE.md`)
- `AP_DDS/` - ROS2/DDS integration for external control and telemetry
- `AP_ExternalControl/` - Interface for external control sources (DDS, Lua)

### Board Configuration

Hardware definitions are in `libraries/AP_HAL_ChibiOS/hwdef/`. Each board has a directory with:
- `hwdef.dat` - Pin mappings, peripheral configuration
- Optional `hwdef-bl.dat` for bootloader configuration

### AP_Periph (CAN Peripherals)

AP_Periph firmware runs on dedicated CAN nodes (GPS, airspeed sensors, etc.). Key patterns:
- Build with: `./waf configure --board <periph-board> && ./waf AP_Periph`
- Modular build flags: `AP_PERIPH_GPS_ENABLED`, `AP_PERIPH_BARO_ENABLED`, etc.
- Each subsystem can be independently enabled for minimal firmware size.
- Peripheral boards defined in `libraries/AP_HAL_ChibiOS/hwdef/` with `-periph` suffix.

## C++ Development Guidelines

### Architectural Principles

**Compile-Time Dependency Analysis:**
- Before refactoring or coupling classes, analyze their compile-time dependencies. Check for guards like `#if HAL_CRSF_TELEM_ENABLED` or `#if AP_SOME_FEATURE_ENABLED`.
- A core, non-optional component must never depend on a compile-time optional component. The base system must compile when optional features are disabled.
- Build options are defined in `Tools/scripts/build_options.py` (150+ options available).
- Features can be enabled/disabled via `hwdef.dat` files using `define` directives.

**Named Constructor Pattern:**
- Core classes like `Location` use named constructors for clarity and type safety:
```cpp
// Preferred: explicit named constructor
Location loc = Location::from_ekf_offset_NED_m(ekf_origin, offset_ned);

// Less clear: implicit conversions
Location loc = Location(ekf_origin);
loc.offset(offset_ned.x, offset_ned.y);
```
- Use named constructors when intent or coordinate system matters.

**UART Management Models:**
1. **Passthrough/RCIN Mode:** UART managed by high-level frontend; backend is passive consumer of bytes.
2. **Direct-Attach Mode:** Driver assigned specific `SERIALn_PROTOCOL` value, takes direct UART ownership.

**Singleton Pattern:** Many ArduPilot classes are singletons. Only refactor to instantiable class if multiple independent instances are explicitly required.

**Initialization Order:** The `init()` method of a class must only be called after all dependencies are fully constructed and registered.

**Scheduler Integration:** Any feature requiring periodic execution must have its `update()` function called from an appropriate scheduler or main loop.

**Coordinate System Convention:**
- ArduPilot uses **North-East-Down (NED)** coordinate frame for navigation.
- X = North, Y = East, Z = Down (positive Z is below the vehicle).
- Recent refactoring has standardized APIs to explicitly use `_NED` suffix.
- When working with positions/velocities, always verify the expected frame.

### Code Style

**Formatting:**
- 4-space indentation (spaces, not tabs)
- LF line endings
- Braces on their own lines:
```cpp
// Correct:
if (condition)
{
    foo();
}

// Wrong:
if (condition) { foo(); }
```
- Spaces between control statements and parentheses: `if (condition)`
- No spaces between function names and parentheses: `foo(a, 10)`

**Naming Conventions:**
- Use `enum class` instead of raw enums, PascalCase and singular
- Suffix variables/functions with units:
  - Distance: `_m` (meters), `_cm` (centimeters), `_mm` (millimeters)
  - Angles: `_rad` (radians), `_deg` (degrees), `_cdeg` (centidegrees)
  - Rates: `_rads` (rad/s), `_dps` (deg/s), `_mss` (m/s²)
  - Speed: `_ms` (m/s), `_cms` (cm/s)
  - Time: `_ms` (milliseconds), `_us` (microseconds)
- Parameters: uppercase with underscores, most important word first (e.g., `RTL_ALT_MIN`)

**Literals and Math:**
- Use `1.0f` for float literals, not `1.0`
- Prefer multiplication over division: `foo_cm * 0.01f` not `foo_cm / 100.0f`

### Development Constraints

**Memory:**
- No dynamic memory allocation (`malloc`, `new`) in performance-critical flight code paths
- `new` and `malloc` zero their memory; stack variables must be explicitly initialized
- Be mindful of stack size; avoid deep recursion and large local variables

**Debugging:**
- No `printf`; use `gcs().send_text()` for GCS messages
- `hal.console->printf()` acceptable for debug code compiled out by default

**API Verification:**
- Before calling any ArduPilot API, verify in the header file: exact name, full signature, const correctness, namespace/singleton access pattern
- Never invent or assume function signatures; if uncertain, check the source

**Type Safety:**
- Use `static_cast` for arithmetic/bitwise operations with mixed integer types:
```cpp
// Correct:
uint32_t val = (static_cast<uint32_t>(payload[1]) << 8) | payload[0];

// Wrong:
uint32_t val = (payload[1] << 8) | payload[0];
```

### Comments and Documentation

**Parameter Documentation:** All `AP_Param` parameters require documentation blocks:
```cpp
// @Param: RTL_ALT
// @DisplayName: RTL Altitude
// @Description: The altitude the vehicle will return at.
// @User: Standard
// @Units: cm
// @Range: 200 8000
AP_Int16 rtl_alt;
```

**Code Comments:**
- Every function declaration should have a comment explaining its purpose
- New `.h` and `.cpp` files should start with GPLv3 license and purpose description
- Comments explain "why", not just "what"
- Comments must be descriptive statements about code operation, not development process notes

### Surgical Modification Principle

When modifying existing files:
- Limit changes strictly to the scope of the request
- No unrelated refactoring or style changes
- Produce the smallest possible diff
- Never remove existing code (defines, constants, helpers) unless directly required by the change

## Commit Conventions

- **Atomic Commits:** Each commit represents a single logical change
- **Each Commit Must Compile:** Every commit must leave the codebase in a buildable state. Order changes so dependencies are added before code that uses them.
- **Squash per subsystem:** When squashing commits, group by subsystem prefix (AP_GyroFFT, RC_Channel, Tools, etc.)
- **DO NOT list Claude as author or co-author** - commits should only show the human author
- **Message Prefix:** Subject line prefixed with module name:
  - `AP_Nav: Refactor loiter controller`
  - `Tools: Add autotest for new NAV_CMD`
  - `ArduCopter: Fix altitude hold in mode_althold.cpp`

## Git Safety

- **NEVER run `git clean` without explicit permission** - this removes untracked files which may include important local configuration or notes
- If git clean is absolutely necessary, first backup untracked files to a safe location
- Prefer `git checkout` or `git restore` to discard changes to tracked files
- **Verify rebased commits before force pushing:** After rebasing or squashing, verify the final tree content matches the original by comparing relevant files:
  ```bash
  # Compare specific files between original and rebased commits
  git diff <original-commit> <rebased-commit> -- path/to/file1 path/to/file2
  # Empty output means files are identical
  ```

## Testing

Unit tests use Google Test framework in `libraries/*/tests/`. Tests require SITL board configuration.

```bash
./waf configure --board sitl
./waf --targets tests/test_math
./build/sitl/tests/test_math
```

**Autotests:** Vehicle behavior tests are Python scripts in `Tools/autotest/`. Add new tests as methods to appropriate test suite (e.g., `arducopter.py`).

## Lua Scripting API Design

When designing C++ APIs for Lua interaction:
- No C++-to-Lua callbacks; all interactions initiated from Lua
- Lua scripts are sandboxed and cannot share state directly
- For shared event queues, use peek/pop pattern allowing scripts to check ownership before consuming
- Protect shared C++ state with mutexes when accessible from Lua
