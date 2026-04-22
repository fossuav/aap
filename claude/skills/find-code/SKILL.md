---
name: find-code
description: "Find where features, flight modes, MAVLink commands, GCS message handlers, or subsystems are implemented in the ArduPilot codebase. Use when the user asks where something is defined, implemented, or handled in ArduPilot source code."
argument-hint: "<feature, mode, command, or message>"
allowed-tools: Read, Grep, Glob
---

# Find ArduPilot Code

Find the implementation of `$ARGUMENTS` in the ArduPilot codebase.

IMPORTANT: Use the built-in Grep and Glob tools, NOT shell grep or find commands.

## Workflow

1. **Identify type** — determine what category the target falls into (flight mode, MAVLink handler, subsystem, parameter, etc.)
2. **Search** — use the appropriate pattern from the sections below
3. **Read and confirm** — open matched files to verify the implementation location

## Search strategies by type

### Flight modes
Flight modes are classes in vehicle directories. Search with Grep tool:
```bash
# Find mode source files
Glob pattern: ArduCopter/mode_*.cpp   # or ArduPlane/, Rover/
# Find mode class definition
Grep pattern: "class Mode.*$ARGUMENTS" path: ArduCopter/mode.h
# Find mode enum value
Grep pattern: "$ARGUMENTS" path: ArduCopter/mode.h
```

### MAVLink message handlers
Incoming messages dispatched in GCS_MAVLINK. Search with Grep tool:
```bash
Grep pattern: "case MAVLINK_MSG_ID_$ARGUMENTS" path: libraries/GCS_MAVLink/
Grep pattern: "handle_message_$ARGUMENTS" path: libraries/GCS_MAVLink/
```

### Features / subsystems
Library implementations in `libraries/`. Search with Grep tool:
```bash
# Find class definition
Grep pattern: "class.*$ARGUMENTS" glob: "*.h" path: libraries/
# Find singleton access
Grep pattern: "AP::$ARGUMENTS" path: libraries/
Grep pattern: "$ARGUMENTS::get_singleton" path: libraries/
```

### Vehicle-specific features
Check the vehicle's main header and cpp files:
```bash
Grep pattern: "$ARGUMENTS" path: ArduCopter/Copter.h
Grep pattern: "$ARGUMENTS" glob: "*.cpp" path: ArduCopter/
```

### Parameters
Parameter definitions (use /find-param for detailed search):
```bash
Grep pattern: "@Param:.*$ARGUMENTS" path: libraries/
Grep pattern: "AP_GROUPINFO.*\"$ARGUMENTS\"" path: libraries/
```

### Scheduler tasks
Tasks registered in vehicle scheduler:
```bash
Grep pattern: "SCHED_TASK.*$ARGUMENTS" path: ArduCopter/Copter.cpp
```

### RC auxiliary functions
```bash
Grep pattern: "$ARGUMENTS" path: libraries/RC_Channel/RC_Channel.h
Grep pattern: "case.*$ARGUMENTS" path: libraries/RC_Channel/RC_Channel.cpp
```

### Log messages
```bash
Grep pattern: "$ARGUMENTS" path: libraries/AP_Logger/LogStructure.h
Grep pattern: "Write_$ARGUMENTS" glob: "*.cpp" path: libraries/
```

### Build options / feature flags
```bash
Grep pattern: "$ARGUMENTS" path: Tools/scripts/build_options.py
Grep pattern: "#if.*$ARGUMENTS" glob: "*.h" path: libraries/
```

## Search tips

- Start broad with Grep across the whole repo, then narrow down
- Use Glob to find files by naming convention first, then Read specific files
- Check `.h` files for declarations, `.cpp` for implementations
- ArduPilot uses `_enabled` suffix for feature guards: `AP_FEATURE_ENABLED`
- Singleton classes: look for `_singleton` member and `get_singleton()` method
- Frontend/backend split: frontend in `AP_Foo.h`, backends in `AP_Foo_Backend*.h`
- If initial search returns no results, try broader terms or check alternate spellings (e.g., `LOITER` vs `Loiter`)
