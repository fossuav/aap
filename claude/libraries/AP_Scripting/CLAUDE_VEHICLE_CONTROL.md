# CLAUDE_VEHICLE_CONTROL.md

This file provides guidance for Lua scripts involving vehicle control. For general script structure and patterns, see CLAUDE.md.

## Reading Vehicle State & Telemetry

Primary objects: `ahrs`, `gps`, `baro`, `battery`

| Function | Description |
|----------|-------------|
| `ahrs:get_location()` | Vehicle's best-estimate position as Location object |
| `ahrs:get_velocity_NED()` | Current velocity in North-East-Down frame |
| `ahrs:get_roll_rad()` | Current roll angle in radians |
| `ahrs:get_pitch_rad()` | Current pitch angle in radians |
| `ahrs:get_yaw_rad()` | Current yaw angle in radians |
| `ahrs:healthy()` | Check if AHRS is providing reliable data |
| `gps:status(instance)` | GPS fix status (3D Fix, RTK Fixed, etc.) |
| `gps:num_sats(instance)` | Number of satellites tracked |
| `baro:get_altitude()` | Barometric altitude in meters |
| `battery:voltage(instance)` | Battery voltage |
| `battery:capacity_remaining_pct(instance)` | Remaining capacity percentage |

**Deprecation Notes:**
- `ahrs:get_roll()`, `ahrs:get_pitch()`, `ahrs:get_yaw()` are deprecated. Use the `_rad` variants above.
- `ahrs:airspeed_estimate()` is deprecated. Use `ahrs:airspeed_EAS()` (returns EAS in m/s).

## Controlling Vehicle Movement

Movement commands only work in modes accepting external guidance (Guided, Auto with NAV_SCRIPT_TIME). Behavior tunable via `GUID_OPTIONS` parameter.

### Control Type Hierarchy

1. **Position Control** - Safest. Command target position/velocity; autopilot manages attitude. Cannot go inverted.
2. **Angle Control** - Command target attitude; autopilot maintains it. Cannot go inverted.
3. **Rate Control** - Most direct. Command rotational rates. Script has full control/responsibility. CAN go inverted. Auto-stops if no commands received within `GUID_TIMEOUT`.

### Position Control

| Function | Description |
|----------|-------------|
| `vehicle:set_target_location(Location_ud)` | Fly to specific geographic location |
| `vehicle:set_target_velocity_NED(Vector3f_ud)` | Fly at specific velocity (NED frame) |
| `vehicle:set_target_pos_NED(...)` | Fly to position relative to EKF origin |

### Angle Control

| Function | Description |
|----------|-------------|
| `vehicle:set_target_angle_and_climbrate(...)` | Set target roll, pitch, yaw angles + climb rate |

### Rate Control

| Function | Description |
|----------|-------------|
| `vehicle:set_target_rate_and_throttle(...)` | Set roll/pitch/yaw rates (deg/s) + throttle |

### Combined Control (Advanced)

| Function | Description |
|----------|-------------|
| `vehicle:set_target_angle_and_rate_and_throttle(...)` | Target angles + rates + throttle (for aerobatics) |
| `vehicle:set_target_velaccel_NED(...)` | Target velocity + feed-forward acceleration |
| `vehicle:set_target_posvel_NED(...)` | Target position + velocity (arrive with specific speed) |
| `vehicle:set_target_posvelaccel_NED(...)` | Target position + velocity + acceleration (full trajectory control) |

### Yaw Control

| Type | Description |
|------|-------------|
| **Set Point Yaw** | Command specific heading. `yaw_relative` flag: absolute vs relative to current |
| **Rate-Controlled Yaw** | Command turn rate (deg/s). Continues until new command |

### Common Actions

| Action | Method |
|--------|--------|
| **Brake/Hold Position** | `vehicle:set_target_velocity_NED(Vector3f())` (zero velocity) |
| **Land** | `vehicle:set_mode()` to LAND mode |
| **Takeoff** | `vehicle:start_takeoff(alt_m)` - altitude in meters |

### Querying Current Target

| Function | Description |
|----------|-------------|
| `vehicle:get_target_location()` | Current navigation target location |
| `vehicle:get_wp_distance_m()` | Distance to current waypoint (meters) |
| `vehicle:get_wp_bearing_deg()` | Bearing to current waypoint (degrees) |

## Controller Behavior

**Position Controllers** (`set_target_location`, `set_target_posvel_NED`):
- Goal: Achieve and maintain specific 3D point
- "Fire-and-forget" - no need to call repeatedly
- Actively fights disturbances (wind)

**Velocity Controller** (`set_target_velocity_NED`):
- Goal: Maintain specific velocity vector
- **Continuous command** - must call repeatedly in update()
- Does NOT correct position errors (will drift off course)

**Rate/Throttle Controllers** (`set_target_rate_and_throttle`, `set_target_angle_and_rate_and_throttle`):
- Goal: Maintain rotational rate/attitude with given throttle
- **Continuous command** - must call repeatedly
- Overrides all other controllers
- If commands stop: stops rotating, holds last attitude

## Controller Transitions

**From Rate to Position:**
1. Command stable attitude (level flight) with zero rates
2. Wait for vehicle to stabilize
3. Add short delay (~100ms) for residual acceleration to dissipate
4. Then issue position command

**Never mix controller types in same update() cycle.** Each state machine state should use only one control type.

## Control Handover Pattern

When transitioning from rate control back to position/velocity:
1. First restore attitude/heading
2. Then immediately restore 3D velocity vector
3. Autopilot's internal controllers handle the rest

**Wrong:** `set_target_location()` then `set_target_angle_and_climbrate()` in same cycle (first command ignored)

## Physics-Based Maneuvers

For aerobatic maneuvers with ballistic phases:

1. **Acknowledge model limitations** - simple physics (d = v*t + 0.5*a*t²) doesn't account for drag
2. **Use empirical tuning factors** - add multiplier parameters (e.g., `climb_multiplier`) for user tuning
3. **Verify state before acting** - don't assume commanded state achieved instantly; include verification states (e.g., `ACHIEVING_CLIMB`)

## Managing Autonomous Missions

Primary object: `mission`

| Function | Description |
|----------|-------------|
| `mission:num_commands()` | Total commands in mission |
| `mission:get_item(index)` | Get command at index |
| `mission:set_item(index, item)` | Set/update command at index |
| `mission:set_current_cmd(index)` | Jump to command at index |
| `mission:state()` | Mission status (Running, Complete, Stopped) |
| `mission:clear()` | Clear all mission commands |

## GCS Communication & Logging

Primary objects: `gcs`, `logger`

| Function | Description |
|----------|-------------|
| `gcs:send_text(severity, text)` | Send message to GCS console |
| `gcs:send_named_float(name, value)` | Send named value for GCS graphing |
| `logger:write(name, labels, format, ...)` | Write custom entry to dataflash log |

## Controlling Peripherals & I/O

Primary objects: `SRV_Channels`, `relay`, `gpio`

| Function | Description |
|----------|-------------|
| `SRV_Channels:set_output_pwm_chan(chan, pwm)` | Set raw PWM for servo channel |
| `SRV_Channels:set_output_scaled(function, value)` | Set normalized output (-1 to 1) |
| `relay:on(instance)` | Turn relay on |
| `relay:toggle(instance)` | Toggle relay state |
| `gpio:write(pin_number, value)` | Write to GPIO output (0 or 1) |
| `gpio:read(pin_number)` | Read GPIO input state |

## RC Input

Primary objects: `rc`, `RC_Channel_ud`, `param`

**Note:** Flight control channels are user-mapped. Read `RCMAP_ROLL`, `RCMAP_PITCH`, `RCMAP_THROTTLE`, `RCMAP_YAW` parameters to find correct channels.

| Function | Description |
|----------|-------------|
| `param:get("RCMAP_PITCH")` | Get channel number for pitch control |
| `rc:get_channel(chan_num)` | Get RC_Channel object for channel |
| `rc:has_valid_input()` | Check for valid RC signal (not in failsafe) |
| `RC_Channel_ud:get_pwm()` | Raw PWM value (typically 1000-2000) |
| `RC_Channel_ud:norm_input()` | Normalized input (-1 to 1), centered on trim |
| `RC_Channel_ud:norm_input_dz()` | Normalized input with deadzone (exactly 0 in deadzone) |
| `rc:find_channel_for_option(aux_fun)` | Find channel assigned to aux function |
| `RC_Channel_ud:get_aux_switch_pos()` | Switch position (0, 1, or 2) |

## GUID_OPTIONS Parameter

Bitmask to modify Guided mode behavior (combine by adding values):

| Bit | Value | Option | Description |
|-----|-------|--------|-------------|
| 0 | 1 | DoNotStabilizePositionXY | Disable position hold in velocity control (allows drift) |
| 1 | 2 | DoNotStabilizeVelocityXY | Disable velocity hold in acceleration control |
| 3 | 8 | WPNavUsedForPosControl | Use wp_nav instead of pos_control (smoother corners, slower update rate) |
