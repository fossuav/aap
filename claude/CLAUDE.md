# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Playbook version:** 1.7.50

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
| `/hwdef-check <PR>` | Reviewing an hwdef PR — checks out the PR in a worktree, runs DMA/board-ID/file/commit checks plus a playbook pass, drafts a review comment |
| `/explain <topic>` | Explaining code or architecture |
| `/swd-debug` | Flashing and debugging a board over SWD when USB/serial is dead |
| `/lua <task>` | Writing or modifying Lua applets |
| `/lua-crsf <menu>` | Writing CRSF transmitter menu scripts |
| `/lua-vehicle <task>` | Lua vehicle control and movement commands |
| `/log-analyze <logfile>` | Analyzing DataFlash .bin flight logs |
| `/pr-checks [PR]` | Downloading a PR's failing CI checks and identifying the failing tests/build errors |
| `/pr-review [PR]` | Reviewing **your own** PR before a maintainer does - CI gates, parallel review, Codex cross-check, then fixing what it finds |
| `/aap-update` | Checking the local playbook version against GitHub and updating |
| `/prepare-for-push` | **User-invoked only.** Authorising Claude to push named branches; pushes are blocked by a git pre-push hook until this is run |

## Tooling and Permissions

Permissions in `.claude/settings.json` authorize **specific skill scripts**, not the underlying tools. There is intentionally no blanket `python3`, `git`, `timeout`, `rm`, or `gh api` grant: a wide-open tool permission means any future command - including a destructive one - runs unprompted. Each repeatable operation is instead a script under `.claude/skills/<skill>/`, and the script's path is what gets allow-listed. Machine-specific allows (out-of-repo log paths, personal helpers) belong in `.claude/settings.local.json`, which the installer never touches.

The corollary for how you work:

- When you catch yourself about to run the same ad-hoc command shape more than once - a `mavlogdump`/`python3 -c` one-liner, a `gh api`/`gh run` loop, a `timeout`-wrapped invocation - that is a signal to **offer to fold it into a skill script**, not to ask for a broad tool permission. A script can be granted narrowly (`python3 .claude/skills/<skill>/<tool>.py:*`) and wraps the messy parts (timeouts, multi-step `gh` calls, output handling) so subprocess calls inside it never prompt.
- A genuinely one-off custom script should just prompt once - approve it and move on. Do not reach for a blanket grant to avoid a single prompt, and do not dodge the prompt by collapsing it into a one-liner.
- Prefer existing skills over hand-rolled commands: `/autotest` (runs via `run_autotest.py`, results via `autotest_results.py`), `/log-analyze` (`log_extract.py`), `/pr-checks` (`ci_failures.py`). Reach for a raw command only when no skill covers the task - and if it recurs, propose a script.
- Hooks are anchored with `"$CLAUDE_PROJECT_DIR/.claude/hooks/..."` so they survive a `cd` into a worktree or sibling clone; keep new hook entries anchored the same way.

When you propose a new script, say what it folds in and which narrow permission it would need, then add it under the relevant skill (with a row in `install-claude.sh`, the README table, and this file if it is a new slash command).

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

### Subsystem Playbooks

The root playbook carries the general rules. Where a subsystem has its own playbook, read it before touching that code and hold reviews of that code against it. In particular, when a change hinges on a named state flag or term, look that term up there before building on it - the playbooks carry which flags are unreliable and why, and that is exactly the knowledge a fix silently assumes. The installed playbooks are untracked, so a worktree or fresh clone made for a fix does not have them: read them from the checkout they were installed in, and point any review agent there. The subsystem playbooks:

- `libraries/AP_NavEKF3/CLAUDE.md` - EKF3 state vector, DAL and Replay rules, bias inhibition, yaw source handling, log analysis method. Some sections are flagged as branch-specific; confirm a mechanism exists on the base branch before citing it.
- `libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md` - board porting, hwdef review rules (applied by `/hwdef-check`)
- `Tools/autotest/CLAUDE.md` - autotest authoring, harness gotchas, before/after A/B runs
- `libraries/AP_Scripting/CLAUDE.md` - Lua applets (with companions for CRSF menus and vehicle control)
- `ArduPlane/CLAUDE.md` - Plane modes, log messages, QuadPlane transitions, GPS-denied flight

**Architectural rules.** These playbooks also carry assumptions maintainers hold about how the code fits together - what a shared flag promises, who may rely on it - which no single diff shows. They are added only with the user's agreement. A candidate goes into `RULES_PROPOSED.md` in the `aap` repository, which is never installed, so nothing proposed is a standard. A rule is a general principle a maintainer would agree with on reading it, without knowing the incident that exposed it; the incident is its example, not its subject. It carries a check a reviewer can apply, and moves into the playbook for the code it constrains only once the user confirms it. A rejected candidate stays in the queue with the reason, so it does not come back. A rule that holds only on a fork's own branches lives in that fork's repository, in a tracked `ARCHITECTURE_RULES.md` with its own queue beside it (find it with `git ls-files '*ARCHITECTURE_RULES.md'`), and is read alongside the playbook for the code it covers. When a bug turns out to rest on an assumption nobody wrote down, propose the rule in the same turn the bug is explained.

## C++ Development Guidelines

### Architectural Principles

**Compile-Time Dependency Analysis:**
- Before refactoring or coupling classes, analyze their compile-time dependencies. Check for guards like `#if HAL_CRSF_TELEM_ENABLED` or `#if AP_SOME_FEATURE_ENABLED`.
- A core, non-optional component must never depend on a compile-time optional component. The base system must compile when optional features are disabled.
- Build options are defined in `Tools/scripts/build_options.py` (400+ options). Use `/build-options` to search them.
- Features can be enabled/disabled via `hwdef.dat` files using `define` directives.
- A feature not every vehicle needs costs nothing to the users who do not use it (ARCH-4, confirmed 2026-10-14): it has its own enable define, defaulted in the library's `_config.h` and listed in `build_options.py`, is off where flash is tight, and compiles out completely, with guards around whole functions and `case`s rather than inside them. The PR states its flash cost on a small board.

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

**Scheduler Integration:** Any feature requiring periodic execution must have its `update()` function called from an appropriate scheduler or main loop. The main loop never waits (ARCH-9, confirmed 2026-10-14): flight code does not block, busy-wait or sleep on the main thread; slow or waiting work runs as a state machine across calls or on another thread, periodic work runs at a rate set by its measured cost, and data shared between threads is protected (`WITH_SEMAPHORE`).

**Flight-State Flags Are Per-Vehicle Opinions:**
- `onGround`, `inFlight`, `takeOffDetected`, `land_complete`, `likely_flying`/`get_time_flying_ms()` and Plane's `is_flying()` each mean something different on each vehicle, and each has a recorded case of reading wrong in flight. The EKF3 playbook's Flight-State Flags section lists how each is set and where it lies.
- Before using one as evidence of flight, contact or stillness, write down how it is set on every vehicle class the code runs on and when it reads wrong there. Where it does not hold, require an independent second signal. In the EKF that cannot be a vehicle-class test: the EKF carries no vehicle-specific code, so vehicle differences arrive through generic signals the vehicle sets (ARCH-17, and the EKF3 playbook).
- Code that fabricates a measurement on the strength of such a flag (zero velocity, zero flow, a height reference) is the highest-risk case: a wrong flag in flight becomes a confident wrong observation. A Copter-only autotest cannot see a Plane failure.

**Shared State Is a Contract Between Subsystems** (ARCH-1, confirmed 2026-10-13):
- A subsystem owns its state, and what it shares with others is a contract between them. A change to what shared state means, or when it is set, changes the contract: every reader is checked against the new meaning, and the PR says which readers it checked.
- Libraries publish shared state through read-only `const` accessors rather than public members, and so does `AP_Vehicle` wherever it can. A vehicle's own state is read directly by its modes and failsafes, which are part of the vehicle, but the contract applies to those reads all the same.
- #32514 changed when Copter's EKF failsafe clears; #34696 relied on the old meaning, and on a branch carrying both its restore was refused.

**Test for What You Need, Not for What Usually Comes With It** (ARCH-2, confirmed 2026-10-13):
- Code that needs a capability - a position, a healthy sensor, a link - tests for that capability directly, not for a proxy such as a failsafe having cleared. A proxy holds only until someone changes what it means.
- Where code acts on a proxy, ask what it actually needs and whether there is a direct test for it. #34696's restore needed a position and waited for the EKF failsafe to clear; once #32514 let the failsafe clear without a position, the restore was refused.

**Lower Layers Detect, Higher Layers Decide** (ARCH-3, confirmed 2026-10-14):
- A library reports what it sees and the vehicle decides what to do about it, since different vehicles need different responses: motor failure detection belongs in AP_Motors, the response in the vehicle (rmackay9, #20856).
- Callers go through a layer's interface (AHRS rather than an EKF backend, AP_HAL rather than a platform), never into its internals, and lower layers never call up. Asking the EKF where its data comes from is a layering violation (peterbarker, #31177).
- Generic behaviour lives in a shared library usable by every vehicle, not in one vehicle's directory.

**Safety Logic Is Judged by What It Does When It Is Wrong** (ARCH-5, confirmed 2026-10-14):
- A failsafe triggers when the vehicle loses something its current flight depends on, and what it then does is a separate, configurable decision.
- Improve an existing failsafe rather than adding an overlapping one, and never let one feature disable or bypass another's protection (rmackay9, #34210).
- Anything that can disarm, land or change mode in flight is designed for the case where it fires wrongly as much as for the case where it is right: landing detector false positives disarm vehicles in flight (rmackay9, #20929).

**Do Not Break What Users Already Have** (ARCH-6, confirmed 2026-10-14):
- Existing configurations, ground stations, log consumers and scripts keep working across an update. A change to user-visible behaviour, a default or a parameter's meaning is stated, migrated and released with notes, and old tools stay supported until they are deprecated. Changed log numbering broke QGC in #14299.

**New Behaviour Is Opt-In, and Lands as the Last and Smallest Commits of a PR** (ARCH-19, confirmed 2026-10-16):
- A change to what a vehicle does is off by default - behind a parameter, an option bit or a feature define - so no one's aircraft behaves differently after an update they did not ask for. The exceptions are a fix for an actual bug, and a change a maintainer agrees should be on by default; the PR says which.
- Within a PR the structure comes first: refactoring and plumbing in commits that change no behaviour, shown where possible to leave the compiler output unchanged (`Tools/scripts/size_compare_branches.py`, or `--consistent-builds` builds hashed per commit), then the behaviour change last, as a small surgical set of commits a reviewer can read on its own. A refactor mixed into a functional change hides what actually changed and makes both harder to review. On the RP2350 branch (#32995) MatekH743 copter stayed binary-identical through the first 45 commits, and the six that changed STM32 output came after them, each saying so.

**Prefer the Simplest Design That Does the Job** (ARCH-7, confirmed 2026-10-14):
- Do not add a queue, an option, a state flag or a mechanism for a small or hypothetical gain. Use the constructs the codebase already uses, and keep one source of truth rather than mirroring it in new state. For each new option, flag or mechanism, ask what fails without it.

**Reuse Before You Write** (ARCH-8, confirmed 2026-10-14):
- Extend or factor the existing implementation, through a common base class or shared library, rather than copying it or adding a second one.

**Do Not Add Code Before It Is Used, and Remove What Your Change Leaves Unused** (ARCH-14, confirmed 2026-10-16):
- Code that nothing calls costs flash on every board and review time, and rots, since nothing exercises it. A PR adds methods, members, parameters and options only when something in it uses them (rmackay9, #11795: "a golden rule in AP that we don't add things before they are used"); a helper first used by a later PR belongs in that PR, or that PR stacks on this one.
- When a change replaces a mechanism or stops calling a helper, the old one goes in the same PR (peterbarker, #31919: "why are we keeping any of the old calibration code?"). That is what "required by the change" means in the Surgical Modification Principle; dead code the change did not touch is a separate PR. Removing something users see - a parameter, a log field, a mode - is still governed by ARCH-6.

**Nothing From Outside Is Trusted** (ARCH-10, confirmed 2026-10-14):
- Bound every loop and buffer, check every index and length before use, validate values from parameters, sensors and the wire, and treat an impossible state as an internal error rather than a crash. Never index an array from a user-set parameter (peterbarker, #26887).

**A Driver Change Holds for Every Variant and Failure It Can Meet** (ARCH-13, confirmed 2026-10-16):
- A driver serves a family of chips and meets lost devices, bus glitches and timeouts. Check a change against the datasheet of every variant the driver supports, take the timeout path first so a lost sensor always reaches no-data, do not trust a single sample, and behave like the sibling backends: pass on what the sensor reported, and flag every kind of new data. Limit a risky change to the variant that needs it. An SPL06 change would have written the wrong configuration into the SPA06 (peterbarker, #28983).

**Data Crosses From a Driver's Thread to the Main Loop Only at the Frontend's Copy** (ARCH-18, confirmed 2026-10-16):
- Sensor drivers split into a backend, whose periodic callback runs on the device's bus thread, and a frontend that runs in the main loop. The callback reads the device and writes only the backend's own accumulators, under the backend's semaphore (`_sem`). The frontend's `update()` calls the backend's `update()` or `read()`, which takes the same semaphore, copies the accumulated data into the frontend's state and resets it.
- That copy is the synchronisation point: the frontend's state, and everything downstream of it - AHRS, the EKF, the vehicle - is read and written only on the main thread (the shared-data line of ARCH-9). A callback never calls out of its backend into the frontend or another library, and code that adds state on a path a callback can reach first checks which thread runs it. The BMP280 barometer (`_timer()` accumulates, `update()` copies out with `_copy_to_frontend()`), the VL53L1X range finder and the HereFlow flow driver (a `new_data` flag set in the callback, published from `update()`) keep this. Not every driver does yet: PulsedLightLRF writes the frontend's state from its I2C callback, Pixart reads the AHRS gyro in its, the compass publishes its raw field from the bus thread, and PX4Flow called `_update_frontend()` from its timer, which ran the EKF and the Replay logging on the bus thread (#33484).

**internal_error Is for the Impossible, Not the Unexpected** (ARCH-15, confirmed 2026-10-16):
- `INTERNAL_ERROR` marks a state the code believes cannot happen - "land now, do not fly again until the bug is fixed" (peterbarker, #24196) - so it reaches the logs and watchdog dumps without asserts. If a sensor, a GCS or a parameter can cause the condition, it is input handling, not an internal error. Harmless misuse is not raised either, and a non-critical fault at startup is recorded rather than leaving the board unbootable.

**Libraries Carry No Vehicle-Specific Code; the Vehicle Moderates Them** (ARCH-17, confirmed 2026-10-16):
- A library serves every vehicle, including ones that do not use a feature today but may tomorrow, and a library with vehicle-specific code has to be built once per vehicle, which slows every multi-vehicle build. So a library never tests at run time which vehicle it is in: behaviour that differs by vehicle lives in the vehicle's code, which moderates the library through a mechanism the library offers - a setter, an option, or a generic signal the vehicle sets for itself (`get_fly_forward()`, `takeoff_expected()`).
- Compiling part of a library out of one vehicle's build (`APM_BUILD_TYPE`) is the exception: only for something that could never make sense on that vehicle, only where strictly necessary, and the PR says why. Replay is built as its own vehicle type, so it still runs that code on the vehicle's logs; there, and only there, the code follows the logged vehicle class (`dal.get_vehicle_class()` under `APM_BUILD_TYPE(APM_BUILD_Replay)`), since Replay's job is to reproduce the build that made the log. #34292 compiled a landing floor out of Rover, which never lands, rather than take a runtime vehicle-class test, and gates the floor on the logged class in Replay, which then replays Rover logs exactly.

**Use the Weakest Spatial Reference the Job Needs, and Name the One You Use** (ARCH-16, confirmed 2026-10-16):
- A position is relative to the EKF origin (NED from the AHRS) and needs no absolute reference: a flow-only copter has one with no GPS and no origin. A location is latitude, longitude and altitude; converting between the two needs the EKF origin (`Location::get_vector_from_origin_NEU()` asks the AHRS for it), and an absolute location needs an absolute source such as GPS. The EKF origin is the frame positions are measured in: once valid its horizontal position never moves, and its altitude is re-referenced only by a height datum reset on the ground (#32768 works towards making the origin fully immutable). Home is where the vehicle returns to, and it can move: a GCS can set it at any time, and Plane moves it while disarmed.
- Ask for the weakest of these that does the job: nothing where no spatial reference is needed, a position where a position will do, a location only where an absolute fix is genuinely required, and home or origin only as what each is. On Copter home is not the origin, most modes need only a position (`requires_position()`), RTL needs home and lat/lon targets need the origin; on Plane home and origin are set together from the first good GPS fixes and kept together while disarmed, and it navigates by locations. Never move the origin's horizontal position, do not change the altitude reference a vehicle measures against from one flight to the next, and use home-relative height for above-home semantics (peterbarker, #31619: "home is not the same as origin"; rmackay9, #32505: the position controller relies on the origin not moving).

**Coordinate System Convention:**
- ArduPilot uses **North-East-Down (NED)** coordinate frame for navigation.
- X = North, Y = East, Z = Down (positive Z is below the vehicle).
- Recent refactoring has standardized APIs to explicitly use `_NED` suffix.
- When working with positions/velocities, always verify the expected frame.

### Code Style

**Formatting:**
- 4-space indentation (spaces, not tabs)
- LF line endings
- Braces follow `Tools/CodeStyle/astylerc` (`style=linux`): a function's opening brace goes on its own line, a control statement's on the same line, and a one-line body still gets braces:
```cpp
// Correct:
void Foo::bar()
{
    if (condition) {
        foo();
    }
}

// Wrong:
if (condition) foo();
```
- Headers use `#pragma once`, not `#ifndef` include guards.
- Spaces between control statements and parentheses: `if (condition)`
- No spaces between function names and parentheses: `foo(a, 10)`
- Python: a file that opts into linting carries the `AP_FLAKE8_CLEAN` marker, and a new Python file should add it; flake8's line limit is 127.

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
- Memory is paid for only where it is used (ARCH-12, confirmed 2026-10-16): an optional feature allocates its state at init or on first use, only when the hardware or the feature is present. Check every allocation, report a failure rather than skip it in silence, and make every path that uses the object cope with it being absent. Free what an option stops using and clear the pointer, and keep large buffers out of BSS, which on some boards shares a full first memory block with the vehicle objects (tridge, #13923, #11795).
- `new` and `malloc` zero their memory; stack variables must be explicitly initialized
- ArduPilot zeroes BSS at startup, and class instances reach you either through BSS (singletons, statics), through `new`-zeroed heap, or through an explicit constructor. Do not add `{0}` / `= 0` / `{}` initializers to POD class members in headers as a defensive habit; they are redundant noise and a strong LLM-tell. The only places explicit init is required are stack locals and members where a non-zero default is intended.
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
- No `printf`; use `GCS_SEND_TEXT()` for GCS messages, which compiles out with the GCS where a bare `gcs().send_text()` does not
- Time comes from `AP_HAL::millis()` / `AP_HAL::micros()`, never a platform call
- `hal.console->printf()` acceptable for debug code compiled out by default

**Project conventions** (from upstream `AGENTS.md`, which CI and maintainers hold to):
- Compare floats with `is_zero()`, `is_positive()`, `is_negative()` and `is_equal()`, not `==` or `> 0`.
- Never change an existing `AP_GROUPINFO` index: it is baked into every user's stored parameters.
- Do not modify submodules under `modules/`; they are separate upstream projects.
- No platform-specific code in shared libraries; go through `AP_HAL`.
- Do not remove or weaken an existing test without a documented reason.
- A singleton gets `get_singleton()` and `CLASS_NO_COPY()`.

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

**Self-consistency between description and code:**
- If your PR description, commit message, or a comment treats a value as valid (e.g. "0 is valid for pit mode"), the code path must handle that value without crashing.
- Domain math (`log`, `log10f`, `sqrt`, `acos`, `asin`, division) has restricted inputs. Before adding such a call, identify every value that can reach it, especially the edge cases your own design admits.
- Reviewers will read the prose and the diff together. A description that promises behaviour the code does not deliver wastes their time and yours.

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
Use every annotation that applies: `@Units`, `@Range`, `@Increment`, `@Values` or `@Bitmask`, `@RebootRequired`, and `@Vehicles` for a vehicle-specific one. A parameter's full name, prefix included, is at most 16 characters.

**Code Comments:**
- Match the comment density of the surrounding file. If the neighbouring functions are uncommented or use one-line comments, do not add a paragraph to yours. New comments that stand out from the existing style are the clearest sign code was machine-written.
- A multi-line comment on a one- or two-line change is a red flag. Cut it to a single line stating the non-obvious "why", or delete it.
- Describe every method in both places, split by length: a short one-line purpose comment above the declaration in the `.h`, and the longer description - what it does, its inputs and units, the edge cases and the non-obvious why - above the definition in the `.cpp`. Maintainers ask for this (rmackay9 on #34208: "a description above each method in both the .h and .cpp"). Do not repeat the explanation at call sites or across files.
- Inside a function body, comment only what the code cannot say itself. A trivial getter, setter or wrapper defined inline in the header needs only its one-line comment.
- Comments explain "why", not "what". Never narrate what the next line does or record development process ("now we add", "changed to", "previously this was").
- ASCII only: write `-`, `->`, `"`, `...`. Never use em-dashes, en-dashes, arrows, smart quotes, or the ellipsis character in comments or strings.
- New `.h` and `.cpp` files should start with GPLv3 license and purpose description.

### Surgical Modification Principle

When modifying existing files:
- Limit changes strictly to the scope of the request
- No unrelated refactoring or style changes
- Produce the smallest possible diff
- Never remove existing code (defines, constants, helpers) unless directly required by the change; what the change itself leaves unused counts as required (ARCH-14)
- Do not "tidy up" sibling code in a class you are touching. Adding default-initializers (`{0}`, `= 0`, `{}`) to existing members that were uninitialized before, normalising whitespace on neighbouring lines, or reordering declarations are all out of scope. Touch only the lines the change requires; defensive initialization sprayed across siblings is a reliable LLM-tell and reviewers will flag it.

## Commit Conventions

- **Atomic Commits:** Each commit represents a single logical change
- **What CI enforces:** `Tools/scripts/check_branch_conventions.py` is the check CI runs: a `Subsystem:` prefix from `Tools/scripts/allowed_subsystems.py`, every file in a commit inside that one subsystem, no merge commits and no `fixup!` commits. Run it before pushing. `git subsystems-split` (`Tools/gittools/git-subsystems-split`, `-n` for a dry run) splits a multi-subsystem commit or relabels a wrong prefix across a stack.
- **Each Commit Must Compile:** Every commit must leave the codebase in a buildable state. Order changes so dependencies are added before code that uses them.
- **Structure before behaviour:** refactoring commits that change no behaviour go first, each saying whether it changes the compiler output, and the behaviour change goes last in as few commits as it needs (ARCH-19).
- **Checkpoint Commits:** During development, create checkpoint commits when reaching milestones to avoid losing work. These can be squashed or cleaned up later before final PR submission. Good checkpoint opportunities:
  - After completing a logical unit of work (e.g., adding a new struct, implementing a function)
  - Before attempting risky refactoring or experimentation
  - When all tests pass after a significant change
  - Before running tools that modify files (like formatters)

  Always verify the build succeeds before creating a checkpoint: `./waf copter` (or appropriate target)
- **One module per commit:** Each commit must only touch files from a single subsystem/module. Never mix changes to different libraries or directories in one commit. If a feature requires changes to multiple modules, split into separate commits per module.
- **Squash per subsystem:** When squashing commits, group by subsystem prefix (AP_GyroFFT, RC_Channel, Tools, etc.)
- **Never squash an unflown behaviour change into a flown commit.** A change has flown when a flight ran its code, not when a flown build carried it: the log has to show the changed path running - an event, message or state only that path produces, or a configuration and flight that put the vehicle through it. A change behind a parameter the vehicle has off, a branch the flight never entered (a range that never left its range, a sensor that never went silent), or a vehicle type that did not fly has no flight evidence, however many flights carried it. Until it has flown, a change that alters behaviour goes on top of the flown commit as its own commit, with any test that needs it in a commit after it; squash it once a flight has run it, as the 2026-10-08 batch did. Otherwise the flown commit's flight evidence silently covers code that never ran: this is "Coverage is a trace, not a green run" for flights. Changes that do not affect behaviour may be squashed in: commit messages, comments, parameter documentation and test fixes that do not depend on the new behaviour. The 2026-10-11 round broke this, autosquashing unflown review fixes into five flown PRs (#34457, #34292, #33484, #33359, #32270); on 2026-10-16 TD25's flights had carried eight on-top changes but run only two in full, as EK3_RNG_USE_HGT was off, the range finder never left its range and the flow never went silent.
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
  - `libraries/AP_HAL_ChibiOS/hwdef/` uses `hwdef:` for board definition changes
  - `libraries/AP_HAL_ChibiOS/` outside `hwdef/` uses `AP_HAL_ChibiOS:`
  - Examples:
    - `AP_AHRS: Refactor loiter controller`
    - `autotest: Add test for new NAV_CMD`
    - `Copter: Fix altitude hold in mode_althold.cpp`
    - `AP_Bootloader: add board ID for NewBoard`
    - `bootloaders: add NewBoard bootloader binaries`
    - `hwdef: add NewBoard hwdef`
    - `scripts: add build option for new feature`
    - `ardupilotwaf: add library to vehicle dependent list`

## Git Safety

### Pushing requires an explicit grant

`.claude/githooks/pre-push` refuses every push from a Claude Code session unless
the user has authorised it by typing `/prepare-for-push <branch>`, which mints a
short-lived, branch- and remote-scoped token. Git runs that hook itself, so unlike
the `PreToolUse` Bash hook it cannot be sidestepped by hiding `git push` inside a
shell script. Force-pushing or deleting `master`/`main` is refused
unconditionally, token or not.

The hook identifies a Claude push by walking the process tree for a `claude`
ancestor, falling back to the `CLAUDE*` environment markers where `/proc` is
unavailable. The user's own pushes from their own terminal are not gated and never
need a grant, so never suggest a grant to explain a push of theirs that failed.
Clearing those markers to pass as the user is itself blocked.

`pre_bash_check.py` gates `push`, `rebase`, `reset` and `amend` on the same token,
so it refuses early with a message naming the command to ask for, and lets the
operation through once a matching grant exists.

Consequences for how you work:

- **Never run `grant_push.py` on your own initiative.** It is the authorisation
  itself. Ask the user for `/prepare-for-push` and wait; do not mint your own
  permission. A broad `python3` permission is not licence to do so.
- Rebasing a PR does **not** imply permission to push it. Ask separately.
- Never use `git push --no-verify`, and never touch `core.hooksPath` or the
  `push-authorization` token file. `pre_bash_check.py` blocks all three, including
  when they are buried inside a script passed to an interpreter. Wrapping a
  guarded command in a helper script does not get it past the hook.
- The hook needs `core.hooksPath` pointed at it once per clone or sibling checkout:
  `git config core.hooksPath .claude/githooks`. It is local git config, so a clone
  does not carry it. Verify with `git rev-parse --git-path hooks`.
- Check the current state any time with
  `python3 .claude/skills/prepare-for-push/grant_push.py --status`, and hand
  permission back early with `--revoke` once the pushes are done.

### General

- **NEVER run `git clean` without explicit permission** - this removes untracked files which may include important local configuration or notes
- If git clean is absolutely necessary, first backup untracked files to a safe location
- **NEVER run `git add -A` or `git add .`**, including when scoped to a directory - they stage untracked files, which here include the installed playbooks and local notes. Anything swept in becomes tracked, so a later checkout of a commit without it **deletes it from the working tree**, and `git status` then looks clean because the file is gone rather than modified. That is how three playbook files were lost on 2026-09-02. Stage the exact paths the commit is meant to contain (`git add path/one path/two`); use `git add -u` when you really do mean every tracked file you changed.
- Prefer `git checkout` or `git restore` to discard changes to tracked files
- **Verify rebased commits before force pushing:** After rebasing or squashing, verify the final tree content matches the original by comparing relevant files:
  ```bash
  # Compare specific files between original and rebased commits
  git diff <original-commit> <rebased-commit> -- path/to/file1 path/to/file2
  # Empty output means files are identical
  ```

## Pull Requests

- **Check nothing already covers it:** before starting a change, look for an open PR on the same feature or fix, and do not duplicate one.
- **Discuss first when it touches flight safety:** a change to failsafe or flight-safety behaviour, or a refactor of a core library, gets a Discourse (development) or Discord thread before the code.
- **Say what parameters change:** a PR that adds, removes or changes the meaning of a parameter says so in its description, with any migration a user needs.
- **CI must pass:** investigate a failure and fix it, or show it is unrelated; never ask a maintainer to merge over a red check.
- **Review it before you open it, and size later reviews to the push:** run a full `/pr-review` on the branch before creating the PR, and before pushing new commits to an open PR that has never been reviewed, locally or by the review bot. A branch sweep that finds a commit already on a PR has found it pushed, not reviewed; #27893 reached the dev-call review that way with a two-year-old gate no local review had ever read. The full run executes the mechanical CI gates, reviews the diff against the rules in this playbook, cross-checks the findings with an independent Codex pass, and drives the fixes. Clearing the gate first spends a maintainer's attention on the design rather than on whitespace and commit prefixes.
- **A push that answers review findings or fixes a bug gets `/pr-review --quick`:** the mechanical gate, the thread, and one cold read of the new commits only. A full run costs a great many tokens and a long wait, and on a PR labelled `AIReview`, `DevCallTopic` or `DevCallEU` the bot reviews the new head anyway, so there the quick pass is the ceiling. Escalate to the full run when the new commits redesign rather than patch (new state, a new mechanism, files the PR did not touch), when the quick pass finds something material, or when the user asks.
- **Follow the repo's PR template:** Before drafting a PR body, read `.github/PULL_REQUEST_TEMPLATE.md` from the repository root and use its sections, headings, and ordering. Do not invent your own structure.
- **Trim the checklist — don't dump it verbatim.** PR templates often ship with a long boilerplate ticklist that maintainers don't want copied wholesale. Include only:
  - items that have already been done (check them with `[x]`), and
  - items still outstanding that need to land before merge / approval (leave as `[ ]`).
  Drop checklist items that don't apply to the change. If the template has nothing left to include after trimming, omit the checklist section entirely.
- **Keep the rest of the template intact:** Summary / description / testing sections from the template should still be filled in, even when the checklist is short or removed.
- **Before/after SITL plots for behavior changes:** When a PR changes runtime behavior (control loops, EKF, flight modes, sensors, autotune, mixers, etc.), attempt to include before/after plots from SITL logs to show the effect. Reviewers respond well to side-by-side comparisons — they communicate impact in seconds where prose can't. Skip this for PRs with no runtime effect (build system, docs, pure refactors with verified no-op behavior). Use `/log-analyze` to extract and plot the relevant fields from a baseline SITL run (pre-change branch) and a post-change run. GitHub does not accept image uploads via the `gh` CLI, so save plots as PNGs locally and either attach them via the GitHub web UI to embed in the description, or post them in a follow-up PR comment. The runnable recipe for the baseline run (merge-base build in a scratch worktree, throwaway harness, logs moved aside between runs) is under "Before/after A/B runs" in `Tools/autotest/CLAUDE.md`.
- **Editing an existing PR from the CLI:** `gh pr edit` fails against ArduPilot/ardupilot with a "Projects (classic) is being deprecated" GraphQL error and leaves the PR untouched. Patch title and body through the REST endpoint instead, then read back:
  ```bash
  gh api -X PATCH repos/ArduPilot/ardupilot/pulls/<N> -f title="..." -F body=@body.md
  gh pr view <N> --json title,body
  ```

## Writing for Reviewers

These rules apply to **commit message bodies, PR descriptions, and PR comments**. Reviewers are time-poor; wordy text gets skimmed or skipped, so it fails to communicate.

- **Be pithy.** Tell the reviewer exactly what is being done in as few words as possible. The diff carries the "what" — your prose carries the "why".
- **Keep it to the size a maintainer writes.** Ten recent merged rmackay9 PRs run 47 to 447 words of prose, median 180, with no tables and at most a handful of bullets; seven of ours ran 471 to 3322, median 1126. Aim at 200 words of prose and treat 400 as the ceiling for a complex change; only the user-visible failure earns more than that, and 500 is the end of it. That budget is the part above the detail heading below, not the whole body. Past that the description is carrying something that belongs somewhere else.
- **What the description holds:** the symptom, or the issue it fixes with a link to it; what was wrong; what the change does; what you tested and what it showed. Before and after as a plot, a screenshot or two numbers.
- **A table earns its place when every row is a measurement or a decision.** A change that behaves differently across ten configurations says so in ten rows of scenario, master, this PR - denser than the same numbers spread through paragraphs, and a reviewer can find their own configuration in it. The same goes for a table of state a reset moves and deliberately does not: it stops each reader re-finding the same omission. What does not earn a table is a list of runs, of files touched, or of findings you triaged. Count prose words against the budget, not table rows.
- **Open with what the user does and what goes wrong for them.** Start on the mechanism and the reader is lost in the first paragraph, even one who has worked on the subsystem for months. Write it the way a failing test reads: what the user does, what the vehicle does, what that costs them - then what the change does in those same terms, and only then the mechanism. Name the effect a pilot can see ("flies the whole sortie with its height above sea level wrong by a metre"), not the state that produces it; an internal identifier in the opening paragraphs means the order is wrong.
- **Second person for the failure, third person for everything else.** "If you leave a copter powered while waiting for a GPS lock, the autopilot warms up along with its barometer" puts the reader in front of the vehicle; the mechanism, the tests and the residuals then read as a plain report. Keep first person out of a description altogether: "our test vehicles", "I measured", "happy to expand" reads as a chat reply pasted into a PR, and whose airframe produced a number is not what makes it evidence.
- **Everything else goes below a clear heading, not into a comment.** The budget above buys the first screen: the failure, the change, and the evidence a maintainer needs in order to decide. What a careful reviewer will ask for next - the state a change moves and deliberately does not, the parts of the diff that look wrong without the reason, alternatives you measured and rejected, what is left open - goes under the template's Description section, behind a line saying it is detail for reviewers and not needed to review the change in outline. #32768 splits 510 words above that heading and 959 below. A reviewer who does not want it skips one heading; one who does is not made to ask, and neither is the next automated pass, which does not read PR comments at all.
- **A reply answers the question and stops.** One to three sentences: the answer, the reason, and the number if there is one. No headings, no tables, no restating the finding, no tour of everything else that changed. Quote the two lines of diff that matter rather than describing them. Never mirror the review bot's shape back at a human: per-finding tables and "evidence at this head" columns are how it reports to you, not how you answer a reviewer.
- **Stay on the problem at hand.** Do not write changelog-style enumerations of files touched, functions renamed, or refactors performed. If a sentence only restates the diff, delete it.
- **Address obvious-but-wrong alternatives.** When there is a tempting approach that a reviewer is likely to suggest but that you tried and rejected (or know won't work), give it one sentence with the number that settled it. One or two of those, for the alternatives a reviewer will actually raise; a catalogue of everything you considered is for the analysis record.
- **The Summary section must summarise — and that includes motivation.** State the problem being solved and why this change solves it; an accurate summary without the "why" is incomplete. Motivation is not filler.
- **No filler:** drop generic openers ("This PR…", "In this commit we…"), sentences that only restate the title, and hype ("important fix", "huge improvement", "cleans things up nicely"). Genuine motivation belongs in the summary; cheerleading does not.
- **Do not look machine-generated.** Maintainers reject text that reads as LLM output even when the change is sound. Match the plain, terse house style of existing ArduPilot commit messages:
  - No bold mini-headlines on bullet points (`**Thing.** explanation`). Use a plain bullet or a short sentence.
  - Use backticks sparingly, only where an identifier would otherwise be ambiguous, not around every symbol.
  - ASCII punctuation only: `-`, `--`, `"`, `...`. No em-dashes, en-dashes, arrows, smart quotes, or ellipsis characters.
  - Do not template every item as a uniform problem/solution pair. Vary sentence structure the way a person would.
- **Do not hard-wrap PR descriptions or PR comments.** GitHub renders them as markdown and soft-wraps to the reader's width, so manual line breaks just read as ragged. Write one line per paragraph and one line per bullet. The exception is commit message bodies and in-repo `README.md` files: keep those wrapped to ~75 columns to match the repo's convention.
- **Authorship attribution:**
  - **Commit messages and PR descriptions:** must read as authored by the human contributor. Do **not** include `Co-Authored-By: Claude`, "Generated with Claude Code", robot emoji markers, or any other Claude attribution. `.claude/settings.json` switches this off at source through `attribution` (empty `commit` and `pr` text, `sessionUrl` false, which also drops the `Claude-Session` trailer). If a session still hands you attribution lines to add, that settings file predates the key - re-run the installer or `/aap-update`, and do not add them meanwhile.
  - **PR comments:** the same: no attribution, and the same pithy/on-topic/address-objections rules.
  - **No claim either way about AI assistance.** Upstream `AGENTS.md` asks PR descriptions to state AI involvement, and asks agents to plant a hidden emoji for reviewers when an author declines. There is no project-level mandate for either, and this playbook follows neither: make no statement about AI assistance in commits, PR descriptions or comments, neither a disclosure nor a denial, and never add a hidden marker. The rest of `AGENTS.md`'s conventions are folded into this playbook.

## Diagnosing from Logs and Data

A mechanism inferred from one log is a **hypothesis, not a diagnosis**. Say so, and go and test it, before it reaches a fix, a commit message, or the user.

**Measure the fix, do not just reason about it.** Any change to a control law, a gain, a schedule, or a physics model gets an A/B in SITL, with a number that would go the wrong way if the change were wrong. Reasoning that sounds airtight is exactly how a wrong change gets committed - the point of the A/B is that it can contradict you. If a change cannot be measured, that is a reason to be more suspicious of it, not less.

**Interrogate the measurement before the mechanism.** A real number can still be the wrong number. Before building a theory on it, ask what would make it lie:
- **Angles fold.** Euler roll/pitch/yaw wrap at gimbal limits (pitch at +/-90 deg), so any angle difference is meaningless through an aerobatic or near-vertical attitude. Work from the rotation matrix or quaternion, or from a fold-free quantity - a dot product between two vectors has no such problem.
- **Dead parameter names read as "absent", not as an error.** `param:get`/`AP_Param::get` on a renamed parameter returns nil/false, which surrounding code often treats as "no limit" or "default". Verify the name exists in the source (4.7 renamed `WPNAV_*` to `WP_*` and moved it to SI units).
- **Saturated sensors.** Accelerometers clip (`VIBE.Clip`). Past that point the EKF's velocity and attitude are contaminated, and no estimator or lane change can recover information the sensor never captured.
- **Degenerate fits.** A two-point slope measured across a small lever is noise divided by a small number. Check the leverage before believing the slope.
- **Simulator-only artifacts.** Cross-check any conclusion that rests on one model against another model, or against the real vehicle. A high-fidelity sim is still a model, and its drag/inertia will differ.

**A comment that warns against your change is evidence.** If the code you are about to modify explicitly documents the failure your change would re-create, that is a record of someone already hitting it. Reproduce the failure or A/B the change before deleting the comment. Do not assume it is stale.

**A fix that changes nothing is evidence about the mechanism.** When the change your account of a bug predicts should work leaves the symptom exactly as it was, the account is the first thing to re-derive, not the fix. Two rounds of fix-shaped changes went onto a wrong mechanism for #33585's flat-ground carry-over - the flag was held up by `gndOffsetValid`, not the `flatGroundAssumed()` path being tightened - and the failing fix said so on the first attempt. Treat it as a refutation and go back to the measurement.

**Correct the record loudly.** When a claim that reached a commit message, a code comment, or the user turns out to be wrong, say so plainly and revert it. An invented mechanism is worse than no mechanism, because it gets built on.

**A claim marked checked is a hypothesis to the next reader.** A conclusion posted as verified in a note, a PR comment or your own earlier analysis carries no more weight than the evidence behind it, and once it reads as settled every later review inherits it instead of testing it. PR #32768 listed "cannot fire in flight" under things checked, resting on an EKF guard whose flag is the armed state inverted; three review rounds accepted it before an outside review re-read the flag. Re-derive such claims from the source whenever the change touches them.

**Coverage is a trace, not a green run.** A test cited as covering a path has to be shown reaching the changed lines: read its setup for anything that steers around the branch, then confirm from the run (an EV event, a STATUSTEXT, a log field only that branch writes) that it went through. RudderDisarmMidair passed three times while its set_home() locked home and skipped the very branch it was cited for.

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
