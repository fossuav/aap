---
name: lua-vehicle
description: Write ArduPilot Lua scripts involving vehicle control, movement commands, RC input, or telemetry. Use when the user asks to control the vehicle from Lua.
argument-hint: "<control task description>"
allowed-tools: Read, Grep, Glob
---

# ArduPilot Lua Vehicle Control

Before writing vehicle control code, read the full playbooks:

1. **Read the vehicle control playbook:** `libraries/AP_Scripting/CLAUDE_VEHICLE_CONTROL.md` — complete reference for movement commands, controller behavior, state/telemetry, RC input
2. **Read the general playbook:** `libraries/AP_Scripting/CLAUDE.md` — applet structure, parameter system, code constraints
3. **Read the API docs:** `libraries/AP_Scripting/docs/docs.lua` — verify all function signatures

## Task: $ARGUMENTS

## Quick Reference

### Control Type Hierarchy (safest to most direct)
1. **Position** — `set_target_location()`, `set_target_pos_NED()` — fire-and-forget, fights wind
2. **Velocity** — `set_target_velocity_NED()` — continuous command, drifts without correction
3. **Angle** — `set_target_angle_and_climbrate()` — continuous, cannot go inverted
4. **Rate** — `set_target_rate_and_throttle()` — continuous, full control, CAN go inverted

### Critical Rules
- Movement commands only work in **Guided mode** (or Auto with NAV_SCRIPT_TIME)
- **Never mix controller types** in the same update() cycle
- Rate controllers need continuous commands — stops rotating if commands stop
- Velocity controllers need continuous commands — drifts if not called
- Position controllers are fire-and-forget

### State & Telemetry
- `ahrs:get_location()` — vehicle position
- `ahrs:get_velocity_NED()` — velocity in NED frame
- `ahrs:get_roll_rad()`, `get_pitch_rad()`, `get_yaw_rad()` — attitude (use `_rad` variants, not deprecated bare names)
- `ahrs:airspeed_EAS()` — airspeed (not deprecated `airspeed_estimate()`)

### RC Input
- `rc:get_aux_cached(aux_func)` — aux switch position (0/1/2)
- `rc:get_channel(n):norm_input_dz()` — normalized stick input with deadzone
- Read `RCMAP_ROLL/PITCH/THROTTLE/YAW` params to find control channels

### Safety
- Check `arming:is_armed()` before motor commands
- Check flight mode before movement commands
- Pilot RC input has highest priority — relinquish on stick input
- Never interfere with failsafe mechanisms
