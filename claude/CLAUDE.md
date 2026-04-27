# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Playbook version:** 1.2.0

## Available Skills

If skills are installed (`.claude/skills/`), prefer using them over manual commands. They pre-authorize tools and provide structured workflows:

| Skill | Use for |
|-------|---------|
| `/build <vehicle> [--board board]` | Configuring and building firmware |
| `/boards [search]` | Listing/searching available board targets |
| `/sitl <vehicle>` | Launching SITL simulator |
| `/autotest <vehicle> [test]` | Running SITL integration tests |
| `/check [test_name]` | Running unit tests |
| `/style-check [files]` | Checking code style before committing |
| `/find-code <feature>` | Finding where features, modes, commands are implemented |
| `/find-param <NAME>` | Finding parameter definitions in source |
| `/build-options [search]` | Searching compile-time feature flags |
| `/hwdef-info <board>` | Showing board hardware definitions |
| `/explain <topic>` | Explaining code or architecture |
| `/lua <task>` | Writing or modifying Lua applets |
| `/lua-crsf <menu>` | Writing CRSF transmitter menu scripts |
| `/lua-vehicle <task>` | Lua vehicle control and movement commands |
| `/log-analyze <logfile>` | Analyzing DataFlash .bin flight logs |
| `/aap-update` | Checking the local playbook version against GitHub and updating |

## Build System

ArduPilot uses the Waf build system. Always run `./waf` from the repository root. **Always use `/build` (or `./waf` directly) for all building — never use `autotest.py build.*` for builds.** Use `/boards` to search targets.

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

Use `/sitl` for interactive launch with automatic vehicle name mapping.

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

Use `/autotest` for guided test execution with argument parsing. **Always build first using `/build` or `./waf`, then run tests separately:**

```bash
# Step 1: Build the vehicle (use /build skill or ./waf directly)
./waf configure --board sitl
./waf copter

# Step 2: Run tests (do NOT use build.Vehicle - build separately above)
Tools/autotest/autotest.py test.Copter
Tools/autotest/autotest.py test.Plane.QuadPlane
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

Hardware definitions are in `libraries/AP_HAL_ChibiOS/hwdef/`. Use `/hwdef-info <board>` to inspect a board's definition. Each board has a directory with:
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
- Build options are defined in `Tools/scripts/build_options.py` (400+ options). Use `/build-options` to search them.
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

**Style Verification:** Use `/style-check` for automated checking of modified files.
- Check for trailing whitespace before finalizing changes: `git diff --check HEAD`
- Use astyle to verify formatting of modified code only (never entire files):
```bash
# Check what would change (dry run)
astyle --options=Tools/CodeStyle/astylerc --dry-run path/to/modified_file.cpp

# Apply formatting to specific file
astyle --options=Tools/CodeStyle/astylerc path/to/modified_file.cpp
```
- IMPORTANT: Only format code you have actually modified. Running astyle on entire files that contain unrelated code will create noise in the diff and is not acceptable.
- After running astyle, review the changes to ensure only your modifications were affected.

### Development Constraints

**Memory:**
- No dynamic memory allocation (`malloc`, `new`) in performance-critical flight code paths
- `new` and `malloc` zero their memory; stack variables must be explicitly initialized
- Be mindful of stack size; avoid deep recursion and large local variables
- Prefer `calloc`/`free` over `new[]`/`delete[]` for arrays - less allocation overhead:
```cpp
// Preferred for arrays:
auto *leds = (SerialLed *)calloc(num_leds, sizeof(SerialLed));
free(leds);

// Avoid for arrays (more overhead):
auto *leds = new SerialLed[num_leds];
delete[] leds;
```
- Prefer embedding objects over dynamic allocation when the object lifetime matches the parent:
```cpp
// Preferred - embedded object:
class Parent {
    Child _child;  // embedded, no heap allocation
};

// Avoid when not necessary:
class Parent {
    Child *_child;  // requires new/delete
};
```

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
- **Checkpoint Commits:** During development, create checkpoint commits when reaching milestones to avoid losing work. These can be squashed or cleaned up later before final PR submission. Good checkpoint opportunities:
  - After completing a logical unit of work (e.g., adding a new struct, implementing a function)
  - Before attempting risky refactoring or experimentation
  - When all tests pass after a significant change
  - Before running tools that modify files (like formatters)

  Always verify the build succeeds before creating a checkpoint: `./waf copter` (or appropriate target)
- **One module per commit:** Each commit must only touch files from a single subsystem/module. Never mix changes to different libraries or directories in one commit. If a feature requires changes to multiple modules, split into separate commits per module.
- **Squash per subsystem:** When squashing commits, group by subsystem prefix (AP_GyroFFT, RC_Channel, Tools, etc.)
- **DO NOT list Claude as author or co-author** - commits should only show the human author
- **Message Prefix:** Subject line prefixed with the specific subsystem or directory name, not a generic parent directory. Use the most specific prefix that matches the changed files:
  - `libraries/` changes use the library name: `AP_AHRS:`, `AC_PosControl:`, `AP_Scripting:`
  - `ArduCopter/`, `ArduPlane/`, `Rover/` etc. use the short vehicle name: `Copter:`, `Plane:`, `Rover:`
  - `Tools/` subdirectories use the subdirectory name as the prefix:
    - `Tools/scripts/` uses `scripts:` (e.g., build option changes)
    - `Tools/ardupilotwaf/` uses `ardupilotwaf:` (e.g., library list changes)
    - `Tools/AP_Bootloader/` uses `AP_Bootloader:` (e.g., board ID additions to `board_types.txt`)
    - `Tools/bootloaders/` uses `bootloaders:` (e.g., bootloader binary additions)
    - `Tools/autotest/` uses `autotest:` for autotest changes
  - `libraries/AP_HAL_ChibiOS/hwdef/` uses `AP_HAL_ChibiOS:` for hwdef additions
  - Examples:
    - `AP_AHRS: Refactor loiter controller`
    - `autotest: Add test for new NAV_CMD`
    - `Copter: Fix altitude hold in mode_althold.cpp`
    - `AP_Bootloader: add board ID for NewBoard`
    - `bootloaders: add NewBoard bootloader binaries`
    - `AP_HAL_ChibiOS: add NewBoard hwdef`
    - `scripts: add build option for new feature`
    - `ardupilotwaf: add library to vehicle dependent list`

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

## Pull Requests

- **Follow the repo's PR template:** Before drafting a PR body, read `.github/PULL_REQUEST_TEMPLATE.md` from the repository root and use its sections, headings, and ordering. Do not invent your own structure.
- **Trim the checklist — don't dump it verbatim.** PR templates often ship with a long boilerplate ticklist that maintainers don't want copied wholesale. Include only:
  - items that have already been done (check them with `[x]`), and
  - items still outstanding that need to land before merge / approval (leave as `[ ]`).
  Drop checklist items that don't apply to the change. If the template has nothing left to include after trimming, omit the checklist section entirely.
- **Keep the rest of the template intact:** Summary / description / testing sections from the template should still be filled in, even when the checklist is short or removed.
- **Before/after SITL plots for behavior changes:** When a PR changes runtime behavior (control loops, EKF, flight modes, sensors, autotune, mixers, etc.), attempt to include before/after plots from SITL logs to show the effect. Reviewers respond well to side-by-side comparisons — they communicate impact in seconds where prose can't. Skip this for PRs with no runtime effect (build system, docs, pure refactors with verified no-op behavior). Use `/log-analyze` to extract and plot the relevant fields from a baseline SITL run (pre-change branch) and a post-change run. GitHub does not accept image uploads via the `gh` CLI, so save plots as PNGs locally and either attach them via the GitHub web UI to embed in the description, or post them in a follow-up PR comment.

## Writing for Reviewers

These rules apply to **commit message bodies, PR descriptions, and PR comments**. Reviewers are time-poor; wordy text gets skimmed or skipped, so it fails to communicate.

- **Be pithy.** Tell the reviewer exactly what is being done in as few words as possible. The diff carries the "what" — your prose carries the "why".
- **Stay on the problem at hand.** Do not write changelog-style enumerations of files touched, functions renamed, or refactors performed. If a sentence only restates the diff, delete it.
- **Address obvious-but-wrong alternatives.** When there is a tempting approach that a reviewer is likely to suggest but that you tried and rejected (or know won't work), include a brief sentence explaining why. This pre-empts back-and-forth and shows the alternative was considered.
- **The Summary section must summarise — and that includes motivation.** State the problem being solved and why this change solves it; an accurate summary without the "why" is incomplete. Motivation is not filler.
- **No filler:** drop generic openers ("This PR…", "In this commit we…"), sentences that only restate the title, and hype ("important fix", "huge improvement", "cleans things up nicely"). Genuine motivation belongs in the summary; cheerleading does not.
- **Authorship attribution:**
  - **Commit messages and PR descriptions:** must read as authored by the human contributor. Do **not** include `Co-Authored-By: Claude`, "Generated with Claude Code", robot emoji markers, or any other Claude attribution.
  - **PR comments:** *may* be attributed to Claude (e.g. when responding to review feedback or posting status updates from Claude). The same pithy/on-topic/address-objections rules still apply.

## Testing

Use `/check` for unit tests, `/autotest` for integration tests. Unit tests use Google Test framework in `libraries/*/tests/`. Tests require SITL board configuration.

```bash
./waf configure --board sitl
./waf --targets tests/test_math
./build/sitl/tests/test_math
```

**Autotests:** Vehicle behavior tests are Python scripts in `Tools/autotest/`. See `Tools/autotest/CLAUDE.md` for authoring conventions (event waits over delays, test registration, SITL speedup, Lua applet patterns). Use `/autotest` to run them.

## Lua Scripting API Design

When designing C++ APIs for Lua interaction:
- No C++-to-Lua callbacks; all interactions initiated from Lua
- Lua scripts are sandboxed and cannot share state directly
- For shared event queues, use peek/pop pattern allowing scripts to check ownership before consuming
- Protect shared C++ state with mutexes when accessible from Lua

# Bash Guidelines

## IMPORTANT: Avoid commands that cause output buffering issues
- DO NOT pipe output through `head`, `tail`, `less`, or `more` when monitoring or checking command output
- DO NOT use `| head -n X` or `| tail -n X` to truncate output - these cause buffering problems
- Instead, let commands complete fully, or use `--max-lines` flags if the command supports them
- For log monitoring, prefer reading files directly rather than piping through filters

## When checking command output:
- Run commands directly without pipes when possible
- If you need to limit output, use command-specific flags (e.g., `git log -n 10` instead of `git log | head -10`)
- Avoid chained pipes that can cause output to buffer indefinitely
