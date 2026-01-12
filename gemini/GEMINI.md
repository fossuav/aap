# GEMINI.md

This file provides guidance to Gemini when working with code in this repository.

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
- `AP_Scripting/` - Lua scripting engine (see `libraries/AP_Scripting/GEMINI.md`)
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

---

# AI Playbook for ArduPilot C++ Development

<MANDATORY_RULE>  
CRITICAL DIRECTIVE: THIS PLAYBOOK MUST BE USED AS THE PRIMARY AND AUTHORITATIVE GUIDE FOR ALL C++ CODE GENERATION FOR ARDUPILOT. ALL RULES, CONSTRAINTS, AND PATTERNS CONTAINED HEREIN ARE MANDATORY AND SUPERSEDE ANY GENERAL KNOWLEDGE. ADHERENCE IS NOT OPTIONAL.  
</MANDATORY_RULE>  
<MANDATORY_RULE>  
CRITICAL DIRECTIVE: THE ARDUPILOT SOURCE CODE AND THE OFFICIAL STYLE GUIDE ARE THE ABSOLUTE AND ONLY SOURCES OF TRUTH. Any deviation from established patterns, function signatures, or style conventions is a critical failure. No assumptions about the API or coding style are permitted.  
</MANDATORY_RULE>

## **1. Core Concepts**

This playbook is designed to provide a Large Language Model (LLM) with the necessary context to generate C++ code for the ArduPilot firmware. Unlike Lua scripting, C++ development involves modifying the core firmware directly. This allows for creating new features, drivers, and flight modes, but requires a deeper understanding of the ArduPilot architecture.

**Key Principles:**

* **Direct Firmware Modification:** All C++ changes are compiled directly into the firmware that runs on the flight controller.  
* **Performance is Critical:** Code runs on resource-constrained microcontrollers. It must be efficient in terms of both CPU usage and memory.  
* **ArduPilot Libraries:** Development should leverage the extensive set of existing libraries for everything from sensor drivers to attitude control and navigation. Reinventing the wheel is strongly discouraged.  
* **Hardware Abstraction Layer (HAL):** All hardware interactions are managed through the AP_HAL library, which allows the core flight code to be portable across different flight controller boards.

### **1.5. Architectural Principles & Pre-computation**

Before proposing any refactoring or new architecture, the following principles must be explicitly considered and verified. This is a mandatory pre-computation step.

* **Compile-Time Dependency Analysis (CRITICAL):**  
  * **Mandatory Rule:** Before proposing to refactor or couple classes, you **must** analyze their compile-time dependencies. Check the source files for guards like `#if HAL_CRSF_TELEM_ENABLED` or `#if AP_SOME_FEATURE_ENABLED`.  
  * **Mandatory Rule:** A core, non-optional component (e.g., AP_RCProtocol_CRSF) **must never** be refactored to depend on a compile-time optional component (e.g., AP_CRSF_Telem). The base system must always be compilable and functional, even when optional features are disabled. Proposing such a dependency is a critical failure.  
* **UART Management Models:**  
  * Acknowledge the two primary UART management patterns in ArduPilot:  
    1. **Passthrough/RCIN Mode:** The UART is managed by a high-level frontend (like the main RC input protocol discriminator). The backend class is a passive consumer of bytes and does not initialize or read from the port directly.  
    2. **Direct-Attach Mode:** The driver class is assigned a specific SERIALn_PROTOCOL value. It takes direct ownership of the UART, initializing it and actively polling it for data in its own update() loop (e.g., VTX drivers, GPS drivers).  
  * **Mandatory Rule:** For any task involving a serial port, you must first determine which of these two models is appropriate. If creating a new driver-like feature, Direct-Attach is the default. If modifying the core RC input path, Passthrough must be respected.  
* **Singleton vs. Instantiable Class Pattern:**  
  * Many older ArduPilot classes are singletons. Refactoring a singleton into an instantiable class is a significant architectural change.  
  * **Mandatory Rule:** Only propose refactoring a singleton if the user's request explicitly requires multiple, independent, and simultaneously active instances of that class's functionality (e.g., managing two separate CRSF ports for different purposes). If the goal can be achieved without this change, the original pattern should be respected.

## **2. Environment Setup**

To develop in C++, a complete ArduPilot development environment must be set up. This allows for compiling the firmware and running simulations.

* **Build Environment:** Follow the official documentation to set up the ArduPilot build environment for your operating system (Linux, WSL on Windows, or macOS).  
* **SITL (Software In The Loop):** Use SITL to test new code in a simulated environment before deploying to a real vehicle.  
* **Compilation:** After making code changes, the firmware must be recompiled for the target flight controller (e.g., ./waf copter --board CubeOrange).

## **3. ArduPilot C++ Style Guide**

Adherence to the official style guide is mandatory. The following is a summary of the most important rules. For a complete reference, see the [ArduPilot Style Guide](https://ardupilot.org/dev/docs/style-guide.html).

### **3.1. Formatting**

* **Braces:** Braces for if, for, while, etc., go on their own lines:
```cpp
  // Right:  
  if (condition)   
  {  
      foo();  
  }  
  // Wrong:  
  if (condition) { foo(); }
```
* **Spacing:**  
  * No spaces around unary operators (e.g., i++;, *p;).  
  * Spaces between control statements and their parentheses (e.g., if (condition)).  
  * No spaces between a function and its parentheses (e.g., foo(a, 10);).  
* **Statements:** Each statement must be on its own line.  
* **Trailing Whitespace:** Do not leave trailing whitespace.

### **3.2. Naming Conventions**

* **Enums:** Use enum class instead of raw enums. They should be PascalCase and singular.
```cpp
  // Right:  
  enum class CompassType {  
      FOO,  
      BAR,  
  };
```

* **Functions and Variables with Units:** Suffix the name with the physical unit.  
  * _mss for meters/second/second  
  * _cmss for centimeters/second/second  
  * _deg for degrees  
  * _rad for radians  
  * _degs for degrees/second  
  * _rads for radians/second  
    Example:
```cpp
  uint16_t get_angle_rad();  
  float distance_m;
```
* **Parameters:**  
  * Order words from most to least important (e.g., RTL_ALT_MIN is better than RTL_MIN_ALT).  
  * Reuse existing words like MIN and MAX.  
  * Names are uppercase with underscores.

### **3.3. Comments**

* **Parameter Documentation:** All user-facing parameters (AP_Param) must have a documentation block for display in Ground Control Stations.
```cpp
  // @Param: RTL_ALT  
  // @DisplayName: RTL Altitude  
  // @Description: The altitude the vehicle will return at.  
  // @User: Standard  
  // @Units: cm  
  // @Range: 200 8000  
  AP_Int16 rtl_alt;
```
* **Function Comments:** Every function declaration should be preceded by a comment explaining its purpose. For non-trivial functions, this comment should also describe each parameter and the function's return value.  
* **General Comments:** Use // for single-line comments and /* ... */ for multi-line comments.  
* **Header Comments:** Every new .h and .cpp file should begin with a comment block that briefly describes its purpose and functionality. This helps other developers understand the scope of the file at a glance. Also new .h and .cpp files should start with the GPLv3 licenses statement.
* **Descriptive Logic Comments:** It is mandatory to add comments that explain the purpose of new or modified code blocks, especially for complex logic like state machines, algorithms, or non-obvious calculations. Comments should explain the "why" behind the code, not just re-state what the code does.
* **CRITICAL COMMENT RULE: NON-CONVERSATIONAL STYLE (MANDATORY)**  
  * **Rule:** All generated comments (excluding parameter documentation) **must** be written as descriptive statements about the code's operation, intent, or limitations.  
  * **Forbidden Content:** Comments **must not** contain information about the **development process, conversation history, debugging steps, build errors, or reasoning for a specific commit/change** (e.g., "Fixing layering violation," "As requested by the user," "Renamed variable to fix shadowing error").  
  * **Focus:** The focus must be on the code's function as if a new developer is reading it for the first time.  
  * **Example:**  
    * **Right:** `// Filter IMU data to ensure sender index matches configured source.`
    * **Wrong:** `// Updated this filter after user noted a bug in step 3.`

### **3.4. C++ Best Practices**

* **Literals:** Use 1.0f for single-precision float literals, not 1.0.  
* **Multiplication vs. Division:** Use multiplication where possible as it is generally faster.
```cpp
  // Right:  
  const float foo_m = foo_cm * 0.01f;  
  // Wrong:  
  const float foo_m = foo_cm / 100.0f;
```
* **Memory:** new and malloc zero their memory. Stack-stored variables must be explicitly initialized.

## **4. Development Constraints**

### **4.1. General Constraints**

* **No printf:** Do not use printf. For debugging, use the `gcs().send_text()` method to send messages to the Ground Control Station. For complex code `hal.console->printf()` maybe used as long as the statements are compiled out by default.
* **No Dynamic Memory in Flight Code:** Avoid using malloc, new, free, or any other form of dynamic memory allocation in performance-critical paths like the main flight loop. Memory should be pre-allocated.  
* **Stack Size:** Be mindful of stack usage. Avoid deep recursion and large local variables.  
* **Header Inclusion:** Include headers in the following order: The corresponding .h file, C system headers, C++ standard library headers, other libraries' headers, your project's headers.

### **4.2. Mandatory API Verification Protocol**

* **Rule of First Reference:** The first time code is written that references a method, class, or variable from another part of the ArduPilot codebase, it is **mandatory** to first consult that component's header file. Never invent or "hallucinate" function calls, classes, or methods. The ArduPilot C++ API is extensive but specific. If you are uncertain about the existence or exact signature of a function, you **must** request the user to provide the relevant C++ header file(s) for verification. This ensures that the generated code is compilable and correct. 
* **Verification Checklist:** Before writing a call, verify the following in the header:  
  1. **Exact Method/Variable Name:** Confirm spelling and capitalization (e.g., `SERIALMANAGER_MAX_PORTS`, not `num_ports()`).  
  2. **Full Signature:** Confirm parameter types and return type.  
  3. **const Correctness:** If calling a method from within a const method, verify the target method is also const.  
  4. **Namespace and Singleton Access:** Confirm the correct namespace (AP::) and the specific static accessor function (e.g., `AP::rc_protocol()`, not `rc_protocol()`).  
* **Example Interaction:** "To correctly call the serial manager, I need to see its API. Please provide the contents of libraries/AP_SerialManager/AP_SerialManager.h."
* **Red Flag Rule:** If a required method seems plausible but cannot be found in the provided header files (e.g., a `get_backend()` accessor), **do not invent it**. You must stop and explicitly state that the required functionality does not appear to exist in the known API and ask the user for guidance or the correct header file.

### **4.3. C++ Language Correctness Rules**

* **Proactive const-Correctness:** When a method is declared const, all methods it calls on class members must also be const. It is mandatory to trace the call chain to verify this. If a called method needs to be changed to const, its own call chain must also be verified.  
* **Strict Typing for Operations:** In all arithmetic or bitwise operations involving different integer sizes or types (e.g., uint8_t, int), it is mandatory to use static_cast to promote operands to the target type *before* the operation. This prevents compiler warnings and errors related to implicit narrowing conversions.  
  * **Right:**
```cpp
  uint32_t val = (static_cast<uint32_t>(payload[1]) << 8) | payload[0];
``` 
  * **Wrong:**
```cpp
  uint32_t val = (payload[1] << 8) | payload[0];
```
* **Variable Shadowing:** Avoid naming local variables with the same name as class member variables, especially AP_Param members. This causes shadowing warnings/errors (e.g., naming a local variable `rngf` when `AP_OSD_Screen::rngf` exists). Use descriptive names or synonyms (e.g., `rangefinder` instead of `rngf`).

## **5. System Design and Integration**

Beyond writing correct C++ syntax, it is critical to integrate new code into the ArduPilot architecture correctly. Failure to do so can result in features that compile but do not run.

### **5.1. Initialization Order and Dependencies**

A common source of bugs is incorrect initialization order. When a new class or feature depends on another (e.g., a high-level driver depending on a low-level protocol instance), you must guarantee the dependency is ready before it is used.

* **Rule:** The `init()` method of a class **must only** be called after all of its dependencies have been fully constructed and registered.
* **Verification:** Before calling an `init()` method, trace the code path to confirm that any required singletons or manager instances are created and available first. Do not assume they exist.

### **5.2. Respecting Architectural Layers**

ArduPilot is a layered architecture. Functions related to a specific system should be called from within that system's layer or the one directly above it. Calling functions across unrelated modules is a "layering violation" that makes the code difficult to maintain.

* **Rule:** A module's update and management functions should be driven by its parent layer.
* **Example:** A protocol-specific manager (like `AP_RCProtocol_CRSF::manager_update`) should be called from the generic protocol layer (`AP_RCProtocol::update`), not from an adjacent, unrelated manager (like `AP_SerialManager::update`).

### **5.3. Scheduler and Main Loop Integration**

If a new feature needs to run periodically (e.g., polling a sensor, sending data at a fixed rate), its update function must be called from an appropriate main loop. A function that is defined but never called will never execute.

* **Rule:** For any feature that requires periodic execution, the final deliverable **must** include the modification that calls its main `update()` function from a suitable vehicle scheduler or high-frequency loop (e.g., `Plane::loop()`, `AP_RCProtocol::update()`).
* **Verification:** Explicitly state which file and function will be modified to call the new periodic task.

### 5.4. Designing APIs for Sandboxed Lua

ArduPilot's Lua environment is strictly sandboxed for safety. Scripts run in isolated memory spaces and cannot directly share state or interact with ach other. Furthermore, the C++ firmware **cannot** directly call functions within a Lua script. These constraints significantly impact how C++ APIs hould be designed for Lua interaction, especially when dealing with shared resources.

* **No C++-to-Lua Callbacks:** Do not design APIs that require C++ to call back into Lua. All interactions must be initiated from Lua.
* **Mediating Shared Resources:** When multiple independent Lua scripts need to access a shared C++ resource (e.g., a hardware peripheral, a communication queue like the CRSF menu event queue), the C++ API must act as a safe broker.
* **Event Queue Pattern (Peek/Pop):** For shared event queues, the recommended pattern is to provide two C++ functions accessible from Lua:
    1.  `peek_event()`: Allows a script to view the next event **without removing it**. This lets the script check if the event belongs to it.
    2.  `pop_event()`: Allows a script to **remove** the next event after it has peeked and confirmed ownership.
    This "Peek-and-Yield" pattern, implemented in the Lua helper library, allows multiple sandboxed scripts to safely share the queue without race conditions or needing direct communication. Simple getters or filtered queues are often insufficient or add unnecessary flash cost.
* **Thread Safety (Locking):** If Lua scripts can trigger C++ actions that modify shared C++ state from different script contexts (which run sequentially but without guaranteed ordering relative to C++ tasks), the C++ code accessing that shared state **must** be protected by mutexes or other appropriate locking mechanisms to prevent race conditions. The CRSF menu API's use of locking for menu building/modification triggered by Lua is an example of this.

## **6. Surgical Modification**

<MANDATORY_RULE>  
When asked to modify an existing file, you must strictly limit your changes to the scope of the user's explicit request. Do not perform any unrelated "tidy-up", refactoring, or stylistic changes. The goal is to produce the smallest possible diff that correctly implements the user's request, respecting the original author's coding style and structure.  
</MANDATORY_RULE>

This principle extends beyond just the scope of the user's request to the preservation of existing file structure.

* **Mandatory Rule:** Never remove existing code, such as #define statements, constants, or helper functions, unless their removal is a direct and necessary consequence of the refactoring. Code that may appear unused in one context is often present for completeness across the entire codebase or for use in other build configurations. When in doubt, leave it in place.

## **7. Commit Conventions**

<MANDATORY_RULE>  
When committing changes to the ArduPilot repository, all commits must follow the standard ArduPilot conventions.  
</MANDATORY_RULE>

* **Atomic Commits:** Each commit should represent a single, logical change.  
* **Commit Message Prefix:** The subject line **must** be prefixed with the name of the top-level module being changed, followed by a colon.  
  * Example for a library change:  
    AP_Nav: Refactor loiter controller  
  * Example for an autotest change:  
    Tools: Add autotest for new NAV_CMD
* **Per-Subsystem Commits:** If a task involves modifying multiple distinct subsystems (e.g., `AC_AutoTune`, `AP_Vehicle`, `ArduCopter`, and `AP_OSD`), you **must** split the work into individual commits for each subsystem. Do not submit a monolithic commit.
* **DO NOT list Gemini as author or co-author** - commits should only show the human author.

## **8. Deliverable Format and Autotest Generation**

* **Default Deliverable:** The primary output should be the necessary C++ source (.cpp) and header (.h) files for the new feature or modification.  
* **Autotest Generation:** For every new feature that affects vehicle behavior, offer to generate a corresponding SITL autotest.  
  * Autotests are Python scripts located in Tools/autotest/.  
  * Tests for vehicle-specific features should be added as new methods to the appropriate test suite (e.g., arducopter.py).  
  * The test should set necessary parameters, perform actions to trigger the new code, and assert the expected outcome, often by checking for specific STATUSTEXT messages.

## **9. Final Deliverable Checklist**

Before concluding a C++ development task, the following checklist **must** be completed.

1. **[ ] C++ Source Files (.cpp/.h):**  
   * Does the code adhere strictly to the ArduPilot Style Guide?  
   * Are all new parameters properly documented for the GCS?  
   * Is the code free of dynamic memory allocation in critical sections?  
   * Are descriptive comments included for complex logic?  
   * Are all functions and their parameters clearly commented?
   * Do all new files, classes, and public methods have documentation comments (file-level, class-level, and function-level) that explain their purpose?
   * Does the code comply with all Correctness Protocols (API Verification, const, Strict Typing)?
2. Architectural Soundness:
   * Have compile-time dependencies (#if...) been checked to ensure the proposed architecture is valid even when optional features are disabled?  
   * Has the correct UART handling model (Direct-Attach vs. Passthrough) been identified and implemented?  
   * If a singleton was refactored, was this change strictly necessary to meet the user's requirements?
3. Feature Activation & Integration:
   * If a new high-level feature, driver, or class was created, have its init() and update() (or equivalent) methods been called from an appropriate manager, scheduler, or main vehicle loop?  
   * Has a mental walk-through been performed to ensure the new code is actually executed in the program flow?
4. **[ ] SITL Autotest Offer:**
   * Have you explicitly offered to generate a SITL autotest to verify the new functionality?
   * Are you prepared to add the test as a new method to the appropriate vehicle test suite?

## **10. Linux HAL Development Patterns**

When developing drivers for AP_HAL_Linux, the following patterns and pitfalls are critical.

### **10.1. Driver Selection in HAL_Linux_Class.cpp**

Driver selection uses `#elif` chains based on `CONFIG_HAL_BOARD_SUBTYPE`. Order matters critically:

* **Pitfall:** If a board subtype appears in an earlier `#elif` block, it will never reach a later block intended for it.
* **Verification:** When adding a new driver for an existing board subtype, search HAL_Linux_Class.cpp for ALL occurrences of that subtype and ensure the correct block is selected.
* **Example:** `HAL_BOARD_SUBTYPE_LINUX_RPI` must NOT appear in the `RCInput_RPI` block if you want it to use `RCInput_Pigpio` instead.

### **10.2. Early Initialization Pattern**

Some external libraries (like pigpio) create internal threads during initialization. These threads inherit the CPU affinity of the calling thread. On real-time systems with isolated CPUs, this can cause failures.

* **Pattern:** Add an `early_init()` virtual method to the base class that runs BEFORE `scheduler->init()` sets CPU affinity.
* **Implementation:**
```cpp
// In RCInput.h base class:
virtual void early_init() {}

// In HAL_Linux_Class.cpp run():
RCInput::from(rcin)->early_init();  // Before CPU affinity is set
scheduler->init();                   // Sets CPU affinity here
```
* **Use Case:** Any driver that uses libraries with internal thread pools (pigpio, etc.) must initialize those libraries in `early_init()`, not `init()`.

### **10.3. Signal Handler Conflicts with systemd**

Libraries that install their own signal handlers (SIGCHLD, SIGCONT, etc.) conflict with systemd service management.

* **Symptom:** Service hangs on stop/restart, or fails to start on boot but works when started manually after login.
* **Solution:** Disable library signal handlers before initialization:
```cpp
gpioCfgSetInternals(PI_CFG_NOSIGHANDLER);  // For pigpio
int ret = gpioInitialise();
```
* **Rule:** Always check if external libraries have options to disable signal handling.

### **10.4. Real-Time Linux and systemd Configuration**

ArduPilot's internal scheduler handles `SCHED_FIFO` for its own threads. Setting scheduling policy in systemd can break external library threads.

* **Wrong:** `CPUSchedulingPolicy=fifo` in systemd service file
* **Right:** Let ArduPilot handle scheduling internally; only set `CPUAffinity` and `Nice` in systemd
* **Verification:** After boot, check thread scheduling with:
```bash
ps -L -p $(pgrep arducopter) -o tid,psr,cls,rtprio,comm
```
  ArduPilot threads should show `FF` (FIFO) with priorities 10-15. Library threads may show `TS` (normal) - this is correct.

### **10.5. UART Latency Considerations**

The default Linux UART driver uses a 100Hz timer thread for I/O, introducing up to 10ms latency.

* **Low-latency reads:** `_available()` can pull data directly from device when not in timer context
* **Low-latency writes:** `_flush()` can bypass the timer thread using a semaphore for coordination
* **Coordination:** Use a semaphore (`_device_sem`) to prevent timer thread and direct access from conflicting

### **10.6. Serial RC Protocol Data Flow**

When implementing RC input drivers that feed serial protocols (SBUS, CRSF, etc.):

* **Feed bytes to AP_RCProtocol:** Use `AP::RC().add_uart_byte(AP_RCProtocol::RCPROTOCOL_PARSE_ONLY, byte, baudrate)` to let the protocol layer handle detection and parsing.
* **Don't double-invert:** SBUS is an inverted protocol. If your hardware or driver inverts the signal, don't apply software inversion - the SBUS backend handles inversion internally.
* **Framing considerations:** SBUS uses 8E2 (8 data bits, even parity, 2 stop bits). Edge-detection drivers must account for this non-standard framing.
