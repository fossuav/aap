# ArduPlane — CLAUDE.md

Reference guide for ArduPlane development and flight log analysis.

## Plane Flight Mode Numbers

**Critical**: Get these right when decoding MODE log messages.

| Number | Mode | Auto-throttle | TECS | Description |
|--------|------|---------------|------|-------------|
| 0 | MANUAL | No | No | Full manual control |
| 1 | CIRCLE | Yes | Yes | Circle around a point |
| 2 | STABILIZE | No | No | Stabilized manual flight |
| 3 | TRAINING | No | No | Training mode |
| 4 | ACRO | No | No | Aerobatic rate control |
| **5** | **FBWA** | **No** | **No** | **Pilot-direct pitch angle + throttle** |
| **6** | **FBWB** | **Yes** | **Yes** | **Auto-throttle, altitude hold** |
| 7 | CRUISE | Yes | Yes | Auto-throttle with heading hold |
| 8 | AUTOTUNE | Yes | Yes | Auto-tuning |
| 10 | AUTO | Yes | Yes | Mission waypoints |
| 11 | RTL | Yes | Yes | Return to launch |
| 12 | LOITER | Yes | Yes | Circle loiter |
| 15 | GUIDED | Yes | Yes | External guided control |
| 17 | QSTABILIZE | N/A | N/A | VTOL manual stabilize |
| 18 | QHOVER | N/A | N/A | VTOL attitude + altitude hold |
| 19 | QLOITER | N/A | N/A | VTOL position hold |
| 20 | QLAND | N/A | N/A | VTOL land |
| 21 | QRTL | Yes | Yes | VTOL return to launch |
| 22 | QAUTOTUNE | N/A | N/A | VTOL auto-tuning |
| 25 | THERMAL | Yes | Yes | Thermal soaring |

### FBWA vs FBWB — The Key Difference

**FBWA (mode 5)** — pilot has direct control:
- Pilot stick maps to pitch angle and roll angle within limits
- Pilot throttle stick controls throttle directly (`output_pilot_throttle()`)
- No TECS, no altitude target, no auto-throttle
- `does_auto_throttle()` returns false
- NTUN altitude fields are stale/irrelevant

**FBWB (mode 6)** — autopilot manages throttle and altitude:
- Pilot stick controls climb rate and roll angle
- TECS manages throttle and pitch to hold altitude + airspeed
- `does_auto_throttle()` returns true
- `set_target_altitude_current()` called on mode entry
- NTUN.TAT shows TECS altitude target relative to home

**Code**: `ArduPlane/mode_fbwa.cpp`, `ArduPlane/mode_fbwb.cpp`, `ArduPlane/mode.h`

## Plane Log Messages

### CTUN (Control/Throttle)

Plane's CTUN differs from Copter's. Key fields:

| Field | Description | Notes |
|-------|-------------|-------|
| NavRoll | Demanded nav roll | cdeg |
| Roll | Actual roll | cdeg |
| NavPitch | Demanded nav pitch | cdeg |
| Pitch | Actual pitch | cdeg |
| ThO | Throttle output | 0-1.0 (fraction). In FBWA = pilot stick. In FBWB/AUTO = TECS output. |
| RdrOut | Rudder output | |
| ThD | Throttle demand (TECS) | Only meaningful in auto-throttle modes |
| As | Airspeed | m/s |

**No Alt/BAlt fields** — unlike Copter CTUN, Plane CTUN does not contain altitude. Use NTUN or XKF1 for altitude.

### NTUN (Navigation Tuning)

| Field | Description | Notes |
|-------|-------------|-------|
| AltE | Altitude error | cm. `target_altitude.amsl_cm - current_loc.alt`. Only meaningful in auto-throttle modes. |
| TAW | Target altitude waypoint | AMSL cm. Stale/zero if no auto-throttle mode has set it. |
| TAT | Target altitude TECS | Relative to home, cm. `relative_target_altitude_cm()` output. Most useful for diagnosing TECS targeting. |
| Arsp | Target airspeed | m/s |
| XT | Crosstrack error | m |
| XTi | Crosstrack integrator | m |

**Caution**: In FBWA, NTUN fields are stale — FBWA does not set altitude targets or run navigation. Do not diagnose altitude issues from NTUN in FBWA.

### TECS (Total Energy Control System)

Only logged when TECS is running (auto-throttle modes). Zero messages in FBWA is expected.

| Field | Description | Notes |
|-------|-------------|-------|
| hin | Height input (demand) | m, relative to home |
| hout | Height output (estimated) | m |
| dh | Height rate demand | m/s |
| dhi | Height rate input | m/s |
| sp | Speed demand | m/s |
| spout | Speed output | m/s |
| pmin | Minimum pitch | rad |
| pmax | Maximum pitch | rad |
| th | Throttle demand | fraction |

If TECS messages are absent during FBWB/CRUISE/AUTO, check LOG_BITMASK.

### ARSP (Airspeed)

| Field | Description | Notes |
|-------|-------------|-------|
| Airspeed | Measured airspeed | m/s |
| DiffPress | Differential pressure | Pa |
| Temp | Temperature | degC |
| RawPress | Raw pressure | Pa |
| Offset | Zero-wind offset | Pa |
| **U** | **Use flag** | 1 = sensor being used for flight control. **Not `Use`** |
| **H** | **Healthy flag** | 1 = sensor healthy. **Not `Healthy`** |
| **Hp** | **Health probability** | 0.0-1.0. Filtered consistency check result. |
| Pri | Primary flag | 1 = primary sensor |

**Common mistake**: The field names are single letters (`U`, `H`, `Hp`), not full words. Always check `m._fieldnames` in pymavlink.

#### Airspeed Hp (Health Probability)

`ARSP.Hp` tracks a filtered consistency metric between measured airspeed and EKF-estimated airspeed (from wind + groundspeed). When divergence exceeds `ARSPD_WIND_GATE`, Hp decays. Below threshold (~0.1), the sensor is disabled.

- **Gradual Hp drift** (over minutes) = divergence between measured and EKF-estimated airspeed. Often caused by:
  - `ARSPD_RATIO` calibration error (error scales with V^2)
  - `ARSPD_WIND_GATE` too tight (default 5 m/s may be insufficient)
  - EKF wind estimate divergence during unstable flight paths
- **Sudden Hp drop** = transient event (pitot blockage, turbulence, hardware glitch)
- **GPS-denied impact**: EKF dead reckoning requires `hasAirspeed`. Hp failure terminates DR immediately.

### QTUN (QuadPlane Tuning)

| Field | Description | Notes |
|-------|-------------|-------|
| Alt | Current altitude | m AGL (above home) |
| DAlt | Desired altitude | m AGL |
| TAlt | Target altitude | m AGL (may differ from DAlt during transitions) |
| CRt | Climb rate | m/s |
| DCRt | Desired climb rate | m/s |
| TMix | Transition mixing | 0-1.0 (1.0 = full VTOL, 0 = full FW) |
| Trn | Transition state | 0=AIRSPEED_WAIT, 1=TIMER, 2=DONE |
| Ast | VTOL assist active | boolean |

### MODE

| Field | Description |
|-------|-------------|
| Mode | Mode number (see table above) |
| ModeNum | Same as Mode |
| Rsn | Reason for mode change |

## QuadPlane Forward Transition

### Transition Phases

| Phase | QTUN.Trn | Description | Ends When |
|-------|----------|-------------|-----------|
| AIRSPEED_WAIT | 0 | Building airspeed, motors tilting (tiltrotor) or pitching down (SLT) | Airspeed >= AIRSPEED_MIN |
| TIMER | 1 | Timer countdown (Q_TRANSITION_MS), continuing acceleration | Timer expires |
| DONE | 2 | Pure FW flight, VTOL motors off | Mode change |

### Key Parameters

| Parameter | Description |
|-----------|-------------|
| Q_TRANSITION_MS | Timer phase duration (ms) |
| Q_TRAN_PIT_MAX | Max pitch-up during transition (deg) — limits copter pitch authority |
| AIRSPEED_MIN | Airspeed threshold for AIRSPEED_WAIT→TIMER |
| Q_ASSIST_SPEED | Airspeed below which VTOL assist activates in FW modes |

### Tiltrotor vs SLT Transition

**Tiltrotor** (Q_TILT_TYPE > 0): Motors physically tilt forward. Acceleration comes from redirected thrust. Less dependent on vehicle pitch angle. QTUN.TMix ramps during transition.

**SLT** (Standard/Lifting Tail): Must pitch the whole vehicle down to accelerate. Copter pitch authority during transition is critical. See `forward_transition_climb.md` topic for pitch authority gap analysis.

## QuadPlane Hover Modes — GPS-Denied

### QLOITER — Unsuitable Without GPS

QLOITER runs `AC_Loiter` position controller which depends on EKF velocity estimates for braking and position hold. In GPS-denied `const_pos_mode`, EKF velocity is IMU-only integration that drifts immediately. The position controller sees phantom velocity and fights pilot input.

### QHOVER — Recommended for GPS-Denied

QHOVER provides attitude + altitude hold only:
- Pilot sticks map directly to attitude angles (no position controller)
- Z controller runs on baro (works without GPS)
- No horizontal velocity feedback dependency
- Weathervane still works (uses attitude lean, not GPS velocity)

### QSTABILIZE — Emergency Fallback

Fully manual (no altitude hold). Most GPS-independent but hardest to fly.

## EKF Log Analysis for Plane

### Key EKF Log Messages

| Message | Key Fields | Use For |
|---------|-----------|---------|
| XKF1 | Roll, Pitch, Yaw, VN/VE/VD, PN/PE/PD | Attitude, velocity, position (NED, meters) |
| XKF2 | AX/AY/AZ (accel bias), WN/WE (wind), MN/ME/MD (earth mag) | Wind estimates, accel bias monitoring |
| XKF3 | IVN/IVE/IVD, IPN/IPE/IPD, IMX/IMY/IMZ | Innovations (residuals) — large values = sensor disagreement |
| XKF4 | SV/SP/SH/SM (sqrt variances), FS/TS/SS, PI | Health, faults, solution status, primary core |
| XKFS | MI, BI, GI, AI, SS, Source | Sensor selection indices, source set |

All XK* messages have a `C` field for core index (0 or 1). Always filter by core.

### XKF4 Status Fields

**SS (Solution Status)** — NavFilterStatusBit bitmask. Key bits:

| Bit | Value | Name | Meaning |
|-----|-------|------|---------|
| 0 | 1 | attitude | Attitude estimate valid |
| 1 | 2 | horiz_vel | Horizontal velocity valid |
| 2 | 4 | vert_vel | Vertical velocity valid |
| 3 | 8 | horiz_pos_rel | Relative horizontal position valid |
| 4 | 16 | horiz_pos_abs | Absolute horizontal position valid |
| 5 | 32 | vert_pos | Vertical position valid |
| 6 | 64 | terrain_alt | Terrain altitude estimate valid |
| 7 | 128 | const_pos_mode | **No horizontal aiding — position frozen** |
| 16 | 65536 | dead_reckoning | Dead reckoning (no position updates) |
| 17 | 131072 | pred_horiz_pos_rel | Predicted horizontal position relative |
| 18 | 262144 | using_air_dead_reckoning | **Active airspeed-based DR** |

Common GPS-denied SS values:
- **65703** = const_pos_mode + dead_reckoning (hover, no aiding)
- **327983** = horiz_pos_rel + using_air_dead_reckoning + pred_horiz_pos_rel (FW flight with DR)

**FS (Fault Status)**: 0 = no faults. Non-zero = EKF problem.

**TS (Timeout Status)**: Bit 0=Position, 1=Velocity, 2=Height, 3=Mag, 4=Airspeed, 5=Drag.
- TS=48 (airspeed+drag) pre-transition is normal
- TS=32 (drag only) during FW flight is normal

### EKF Air Dead Reckoning

Activated when `readyToUseAirData()` returns true. Requires:
1. `fly_forward = true` (set by `update_fly_forward()` when in FW mode or forward transition)
2. `hasAirspeed = true` (airspeed sensor healthy)
3. No GPS/external position aiding configured (or GPS lost)

DR estimates velocity from airspeed + heading + zero-sideslip assumption. Position integrates from velocity. **Wind estimates stay at zero without GPS velocity reference** — DR position drifts at wind speed.

On transition back to hover: DR stops (airspeed drops below threshold), EKF reverts to const_pos_mode, position resets to origin (0,0).

### EKF State Vector (24 states)

| Index | State | Description | Units |
|-------|-------|-------------|-------|
| 0-3 | quat | Quaternion (w,x,y,z) | - |
| 4-6 | velocity | NED velocity | m/s |
| 7-9 | position | NED position | m |
| 10-12 | gyro_bias | Body frame gyro bias | rad |
| 13-15 | accel_bias | Body frame accel bias | m/s |
| 16-18 | earth_magfield | NED magnetic field | Gauss |
| 19-21 | body_magfield | Body magnetic field | Gauss |
| 22-23 | wind_vel | Wind NE | m/s |

### Analysis Methodology

**Rule 1: No theories without data.** Do not speculate about EKF behavior from code alone. Theories MUST be validated against actual log data.

**Rule 2: Cross-check multiple sources.** For altitude: compare XKF1.PD, BARO.Alt, GPS.Alt, RFND.Dist. For airspeed: compare ARSP.Airspeed with wind+groundspeed. If your theory contradicts a physical sensor, your theory is wrong.

**Rule 3: Extract data first, theorize second.** Extract relevant messages, align timestamps, identify anomalies in the DATA, then form hypotheses that explain ALL observations.

**Rule 4: Check field names.** Use `m._fieldnames` in pymavlink to verify actual field names. Common mistakes:
- ARSP: fields are `U`, `H`, `Hp` (not `Use`, `Healthy`, `HealthProb`)
- CTUN: Plane has no `Alt`/`BAlt` fields (use NTUN or XKF1 for altitude)
- XKF1: Roll/Pitch/Yaw are auto-converted from centidegrees by pymavlink; PD/VN/VE/VD are floats in meters/m/s (do not apply 0.01 scaling)

## GPS-Denied Flight — Key Lessons

### What Works
- Forward transition completes identically to GPS-enabled (tiltrotor: 4.5s)
- EKF air dead reckoning activates automatically in FW flight
- Baro-based altitude hold is reliable in VTOL modes
- Weathervane works (uses attitude lean, not GPS)
- FBWA gives pilot full direct control without any GPS dependency

### What Doesn't Work
- QLOITER — position controller needs EKF velocity (use QHOVER)
- EKF wind estimation — stays at zero, DR position drifts at wind speed
- Position-based modes after DR stops — EKF resets position to origin

### Pre-Flight Checklist
- AHRS_ORIGIN params must match test site (lat, lon, alt within ~100m)
- Airspeed sensor must be reliable (no Hp drift). Set ARSPD_WIND_GATE to 8-10.
- Use QHOVER (not QLOITER) for all hover phases
- Keep FW segments short initially until airspeed reliability is confirmed
- Enable TECS logging before testing FBWB/CRUISE modes

## pymavlink Tips for Plane Logs

### Basic Extraction Pattern

```python
from pymavlink import mavutil

log = mavutil.mavlink_connection('logfile.bin')

while True:
    m = log.recv_match(type=['MODE', 'ARSP', 'XKF4'], blocking=False)
    if m is None:
        break

    t = m._timestamp - log._start_time  # seconds since boot

    if m.get_type() == 'MODE':
        print(f"{t:.1f}s Mode {m.Mode}")  # Use mode number table above
    elif m.get_type() == 'ARSP':
        print(f"{t:.1f}s ARSP Hp={m.Hp:.2f} U={m.U} H={m.H}")
    elif m.get_type() == 'XKF4' and m.C == 0:  # Core 0 only
        print(f"{t:.1f}s SS={m.SS} FS={m.FS} TS={m.TS}")
```

### Plane Mode Number Decode

```python
PLANE_MODES = {
    0: 'MANUAL', 1: 'CIRCLE', 2: 'STABILIZE', 3: 'TRAINING',
    4: 'ACRO', 5: 'FBWA', 6: 'FBWB', 7: 'CRUISE',
    8: 'AUTOTUNE', 10: 'AUTO', 11: 'RTL', 12: 'LOITER',
    13: 'TAKEOFF', 14: 'AVOID_ADSB', 15: 'GUIDED',
    17: 'QSTABILIZE', 18: 'QHOVER', 19: 'QLOITER',
    20: 'QLAND', 21: 'QRTL', 22: 'QAUTOTUNE',
    24: 'QACRO', 25: 'THERMAL',
}
```

### Check Field Names Before Accessing

```python
m = log.recv_match(type='ARSP', blocking=False)
if m:
    print(m._fieldnames)  # ('Airspeed', 'DiffPress', 'Temp', 'RawPress', 'Offset', 'U', 'H', 'Hp', 'Pri')
```

### XKF4 SS Bitmask Decode

```python
def decode_ss(ss):
    bits = []
    names = {
        0: 'attitude', 1: 'horiz_vel', 2: 'vert_vel', 3: 'horiz_pos_rel',
        4: 'horiz_pos_abs', 5: 'vert_pos', 6: 'terrain_alt', 7: 'const_pos_mode',
        16: 'dead_reckoning', 17: 'pred_horiz_pos_rel', 18: 'using_air_dead_reckoning',
    }
    for bit, name in names.items():
        if ss & (1 << bit):
            bits.append(name)
    return bits
```

## Diagnostic Commands

```bash
# Extract parameters
mavlogdump.py log.bin --types PARM --format csv > params.csv

# Check flight modes
mavlogdump.py log.bin --types MODE

# Extract status text messages
mavlogdump.py log.bin --types MSG

# Check EKF health (core 0)
mavlogdump.py log.bin --types XKF4 --condition "XKF4.C==0"

# Check airspeed health
mavlogdump.py log.bin --types ARSP

# List all message types in a log
mavlogdump.py log.bin --format csv 2>/dev/null | grep "^FMT" | awk -F, '{print $4}' | sort -u
```
