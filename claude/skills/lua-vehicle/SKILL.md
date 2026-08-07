---
name: lua-vehicle
description: "Write ArduPilot Lua scripts for vehicle control, movement commands, servo output, RC input, flight mode changes, and telemetry. Use when the user asks to control the vehicle, read RC channels, set waypoints, or interact with autopilot state from Lua."
argument-hint: "<control task description>"
allowed-tools: Read, Grep, Glob
---

# ArduPilot Lua Vehicle Control

## Workflow

1. **Read playbooks** — load the references below before writing control code
2. **Choose controller type** — select from the hierarchy below (prefer safest level)
3. **Implement with safety checks** — verify armed state, flight mode, and RC input priority
4. **Validate** — confirm API signatures in `docs.lua`, test in SITL before hardware

### Required Reading
1. **Vehicle control playbook:** `libraries/AP_Scripting/CLAUDE_VEHICLE_CONTROL.md` — movement commands, controller behavior, state/telemetry, RC input
2. **General playbook:** `libraries/AP_Scripting/CLAUDE.md` — applet structure, parameter system, code constraints
3. **API docs:** `libraries/AP_Scripting/docs/docs.lua` — verify all function signatures

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

### Minimal Guided Mode Velocity Control Example

```lua
local function update()
  if not arming:is_armed() then return update, 1000 end
  if vehicle:get_mode() ~= 4 then  -- 4 = GUIDED for copter
    gcs:send_text(6, "Not in GUIDED mode")
    return update, 1000
  end
  -- Fly north at 2 m/s, maintain altitude
  vehicle:set_target_velocity_NED(Vector3f_ud(2.0, 0.0, 0.0))
  return update, 100  -- 10 Hz continuous command
end
return update, 1000
```

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
