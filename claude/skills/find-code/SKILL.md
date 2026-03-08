---
name: find-code
description: Find where features, modes, commands, or messages are implemented in the ArduPilot codebase. Use when the user asks where something is defined, implemented, or handled.
argument-hint: "<feature, mode, command, or message>"
allowed-tools: Read, Grep, Glob
---

# Find ArduPilot Code

Find the implementation of `$ARGUMENTS` in the ArduPilot codebase.

IMPORTANT: Use the built-in Grep and Glob tools, NOT shell grep or find commands.

## Search strategies by type

### Flight modes
Flight modes are classes in vehicle directories:
```
Glob: ArduCopter/mode_*.cpp
Glob: ArduPlane/mode_*.cpp
Glob: Rover/mode_*.cpp
```
Mode classes inherit from `Mode` and are defined in `mode.h`:
```
Grep for: class Mode.*$ARGUMENTS
```
Mode enum values:
```
Grep for: $ARGUMENTS in ArduCopter/mode.h or ArduPlane/mode.h
```

### MAVLink message handlers
Incoming messages dispatched in GCS_MAVLINK:
```
Grep for: case MAVLINK_MSG_ID_$ARGUMENTS
Grep for: handle_message_$ARGUMENTS
```

### Features / subsystems
Library implementations in `libraries/`:
```
Grep for: class.*$ARGUMENTS in libraries/**/*.h
```
Singleton access:
```
Grep for: AP::$ARGUMENTS
Grep for: $ARGUMENTS::get_singleton
```

### Vehicle-specific features
Check the vehicle's main header and cpp files:
```
Grep for: $ARGUMENTS in ArduCopter/Copter.h
Grep for: $ARGUMENTS in ArduCopter/*.cpp
```

### Parameters
Parameter definitions (use /find-param for detailed search):
```
Grep for: @Param:.*$ARGUMENTS
Grep for: AP_GROUPINFO.*"$ARGUMENTS"
```

### Scheduler tasks
Tasks registered in vehicle scheduler:
```
Grep for: SCHED_TASK.*$ARGUMENTS
Grep for: $ARGUMENTS in ArduCopter/Copter.cpp (scheduler_tasks array)
```

### RC auxiliary functions
Auxiliary switch functions:
```
Grep for: $ARGUMENTS in libraries/RC_Channel/RC_Channel.h
Grep for: case.*$ARGUMENTS in libraries/RC_Channel/RC_Channel.cpp
```

### Log messages
Log message definitions:
```
Grep for: $ARGUMENTS in libraries/AP_Logger/LogStructure.h
Grep for: Write_$ARGUMENTS in libraries/**/*.cpp
```

### Build options / feature flags
Compile-time enables:
```
Grep for: $ARGUMENTS in Tools/scripts/build_options.py
Grep for: #if.*$ARGUMENTS in libraries/**/*.h
```

## Search tips

- Start broad with Grep across the whole repo, then narrow down
- Use Glob to find files by naming convention first, then Read specific files
- Check `.h` files for declarations, `.cpp` for implementations
- ArduPilot uses `_enabled` suffix for feature guards: `AP_FEATURE_ENABLED`
- Singleton classes: look for `_singleton` member and `get_singleton()` method
- Frontend/backend split: frontend in `AP_Foo.h`, backends in `AP_Foo_Backend*.h`
