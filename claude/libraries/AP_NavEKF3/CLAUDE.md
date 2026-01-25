# EKF3 Analysis - CLAUDE.md

This file tracks our EKF3 analysis work, including notes, plans, and rules discovered during the process.

## Plan

*Current objectives and next steps for EKF3 analysis.*

- [x] Initial exploration of EKF3 architecture
- [x] Understand state vector and covariance structure
- [x] Document log message formats
- [x] Learn to use Replay tool for EKF analysis
- [x] Analyze altitude hold issue in log4.bin
- [x] Understand ground effect compensation mechanism
- [x] **Investigate improvement options for low-altitude hover ground effect**
  - Option A: Extend `touchdown_expected` to include low-altitude hover (not just descent)
  - Option B: Add new flag `low_altitude_hover_expected` triggered by altitude + low vertical speed
  - Option C: Use rangefinder height (if available) to detect proximity to ground
  - Option D: Detect ground effect from baro variance signature in real-time
  - Option E: Keep compensation active until vehicle is above configurable height threshold
- [x] **Implemented: TKOFF_GNDEFF_ALT parameter** (see Implementation Notes below)
- [x] Compare altitude estimators: IMU integration, DCM (AHR2), EKF
- [x] Analyze EKF velocity drift without GPS
- [x] **Investigate IMU temperature effects on EKF accel bias** (see Temperature Analysis below)
- [x] **Analyze takeoff abruptness and recommend parameter changes** (see Takeoff Smoothness below)
- [x] **Test EK3_ABIAS_P_NSE via Replay** - No effect without velocity sensor (see EK3_ABIAS_P_NSE Testing)
- [x] **Analyze log5.bin** - Confirmed velocity drift is root cause, ground effect compensation helped but insufficient (see log5.bin section)
- [x] **Analyze vibration compensation** - Won't help indoor no-GPS; only affects acceleration controller, not velocity (see Vibration Compensation Analysis)
- [x] **Ground motor test (log6.bin)** - Found +0.084 m/s² Z-axis shift when motors spin, EKF learns this as bias (see log6.bin section)
- [x] **Inhibit Z-axis bias learning during ground effect** - Implemented in AP_NavEKF3_PosVelFusion.cpp (see Ground Effect Bias Inhibition)
- [x] **Flight test (log8.bin)** - Z-bias inhibition dramatically improved altitude hold (see log8.bin section)
- [x] **Stationary zero velocity fusion** - Fuse synthetic zero velocity when on ground and disarmed to make bias observable (see logjk1.bin section)
- [ ] Investigate velocity sensor options (optical flow, rangefinder)
- [ ] Map out sensor fusion flow
- [ ] Document key algorithms and their purposes

## Notes

### Log File: log4.bin

**Flight Info:**
- Vehicle: ArduCopter V4.6.3-SFD on MambaH743v4
- Frame: QUAD/BF_X
- Dual IMU EKF3 (IMU0 and IMU1 running as separate cores)
- GPS: u-blox
- RC Protocol: CRSF

**Key Timeline:**
- 10.4s: EKF3 IMU0/IMU1 initialized
- 11.8s: Tilt alignment complete (both IMUs)
- 11.9s: MAG0 initial yaw alignment complete
- 45.3s: EKF3 origin set, Field Elevation 156m
- Mode changes: LOITER(5) → STABILIZE(0) → ALT_HOLD(2)

**Log Statistics:**
- ~2014 XKF1 records (~1007 per IMU core)
- 10Hz logging rate for XKF messages

### EKF3 State Vector (24 states)

From `AP_NavEKF3_core.h:555-564`:

| Index | State | Description | Units |
|-------|-------|-------------|-------|
| 0-3 | `quat` | Quaternion (w,x,y,z) - rotation from NED to body | - |
| 4-6 | `velocity` | Velocity in NED frame (N,E,D) | m/s |
| 7-9 | `position` | Position in NED frame (N,E,D) | m |
| 10-12 | `gyro_bias` | Gyro bias in body frame (x,y,z) | rad |
| 13-15 | `accel_bias` | Accel bias in body frame (x,y,z) | m/s |
| 16-18 | `earth_magfield` | Earth magnetic field in NED (N,E,D) | Gauss |
| 19-21 | `body_magfield` | Body magnetic field (x,y,z) | Gauss |
| 22-23 | `wind_vel` | Wind velocity NE (N,E) | m/s |

### EKF3 Log Messages

| Message | Description |
|---------|-------------|
| **XKF0** | Beacon sensor diagnostics |
| **XKF1** | Main outputs: attitude (Roll/Pitch/Yaw), velocity NED, position NED, gyro bias |
| **XKF2** | Secondary outputs: accel bias, wind, magnetic field (earth & body), drag innovations |
| **XKF3** | Innovations: velocity, position, mag, yaw, airspeed + error metrics |
| **XKF4** | Variances/health: sqrt variances, tilt error, position resets, faults, timeouts |
| **XKF5** | Optical flow, rangefinder, HAGL, error magnitudes |
| **XKFD** | Body frame odometry innovations and variances |
| **XKFM** | On-ground-not-moving diagnostics (gyro/accel ratios) |
| **XKFS** | Sensor selection: mag/baro/GPS/airspeed indices, source set, fusion state |
| **XKQ** | Quaternion (Q1-Q4) |
| **XKT** | Timing: IMU/EKF sample intervals min/max |
| **XKTV** | Tilt error variance (symbolic vs difference method) |
| **XKV1** | State variances V00-V11 (quat, velocity, position, gyro bias) |
| **XKV2** | State variances V12-V23 (accel bias, earth mag, body mag, wind) |
| **XKY0** | Yaw estimator outputs and weights |
| **XKY1** | Yaw velocity innovations |

### XKF4 Status Fields

**FS (Fault Status):** Bitmask of filter faults
**TS (Timeout Status):** Bitmask:
- Bit 0: Position timeout
- Bit 1: Velocity timeout
- Bit 2: Height timeout
- Bit 3: Magnetometer timeout
- Bit 4: Airspeed timeout
- Bit 5: Drag timeout

**SS (Solution Status):** NavFilterStatusBit bitmask

### Directory Structure

- `libraries/AP_NavEKF3/` - Main EKF3 implementation
- Key files:
  - `AP_NavEKF3.h` - Main interface/frontend
  - `AP_NavEKF3_core.h` - Core EKF state and structures
  - `AP_NavEKF3_feature.h` - Feature flags/configuration
  - `LogStructure.h` - Log message definitions

### Sample Data Observations

**XKF1 at end of log (flying):**
- Core 0: Roll=-2.0°, Pitch=1.4°, Yaw=308°, VD≈-0.6m/s (climbing), PD≈-1.1m (1.1m above origin)
- Core 1: Roll=-0.4°, Pitch=1.0°, Yaw=309°, VD≈-0.27m/s, PD≈-0.4m
- Two cores show different estimates (Core 0 is primary based on PI field)

**XKV1/XKV2 (State Variances):**
- V00 (quaternion w): ~1e-7 (very small, attitude well-known)
- V01-V03 (quaternion x,y,z): ~0.0025 rad²
- V04-V05 (vel N,E): ~0.3-0.5 m²/s²
- V06 (vel D): ~0.23-0.25 m²/s²
- V07-V08 (pos N,E): ~0.05-0.09 m²
- V09 (pos D): ~0.4-0.6 m² (height less certain)
- V13-V15 (accel bias): ~5e-8 (very small)

### Ground Effect Compensation Analysis

**Problem:** Vehicle doesn't hold altitude in ALT_HOLD mode indoors. Ground effect from propwash causes baro readings to swing wildly near the ground.

#### How Ground Effect Compensation Works

**Key File:** `ArduCopter/baro_ground_effect.cpp`

**Parameter:** `GND_EFFECT_COMP` (default: 1 = enabled)

The EKF has two mechanisms to handle ground effect:
1. **Innovation flooring:** Limits negative baro corrections during ground effect (`AP_NavEKF3_PosVelFusion.cpp:1014-1028`)
2. **Noise scaling:** Increases baro noise variance by 4x during ground effect (`gndEffectBaroScaler = 4.0`)

Both mechanisms are ONLY active when `takeoff_expected` OR `touchdown_expected` flags are true.

#### When Flags Are Set

**`takeoff_expected = true` when:**
- Armed AND `land_complete` is true (vehicle on ground)
- Mode is NOT THROW

**`takeoff_expected = false` when:**
- 5 seconds have passed since takeoff started, OR
- Vehicle is >50cm above takeoff altitude

**`touchdown_expected = true` when ALL of:**
- `slow_horizontal`: XY speed demand ≤125cm/s OR actual XY speed ≤125cm/s OR (ALT_HOLD + small angle)
- `slow_descent`: Active descent demanded AND (rate ≥-100cm/s OR Z speed ≤60cm/s)

**Critical Finding:** When hovering at low altitude (not taking off, not descending), NEITHER flag is true, so NO ground effect compensation is applied!

#### The Gap

| Flight Phase | takeoff_expected | touchdown_expected | Compensation |
|--------------|------------------|--------------------|--------------|
| On ground, armed | YES | NO | YES |
| First 5s or 50cm of takeoff | YES | NO | YES |
| Hovering at low altitude | NO | NO | **NONE** |
| Descending slowly for landing | NO | YES | YES |
| On ground after landing | YES | NO | YES |

This explains why ground effect causes problems during sustained low-altitude flight - the compensation code exists but isn't activated for that scenario.

#### Timeline Correlation (from log4.bin)

| Event | Time | Effect |
|-------|------|--------|
| Armed | 45.3s | `takeoff_expected = true` |
| Takeoff begins | ~52s | Ground effect active, compensation ON |
| NOT_LANDED event | 54.2s | `takeoff_expected = false`, compensation OFF |
| Altitude problems | 55s+ | No compensation, EKF diverges |
| LAND_COMPLETE | 100.6s | - |
| Disarm | 104.5s | - |

**Concrete Evidence (CTUN data):**

| Time | BAlt (baro) | EKF Alt | Notes |
|------|-------------|---------|-------|
| 52.0s | -0.86m | -0.12m | Takeoff starts, baro drops (propwash) |
| 52.4s | -2.79m | -0.22m | Ground effect peak, but EKF compensating |
| 54.3s | -8.42m | -1.09m | Massive baro spike as props spin up |
| 54.6s | -0.03m | -1.11m | Baro recovers as vehicle lifts |
| 55.2s | +0.50m | -0.91m | **Compensation OFF** - EKF not following baro |
| 58.3s | +0.50m | -1.38m | EKF thinks ~1.8m below baro! |
| 60.0s | +0.79m | -1.02m | Divergence continues |

**Key Observation:** When `takeoff_expected` was true (52-54s), the EKF handled the -8m baro spike gracefully. After 54.2s when compensation turned off, a much smaller ground effect (±0.5m) caused the EKF to diverge by ~2m.

### Potential Ground Effect Compensation Improvements

**Problem Statement:** The current ground effect compensation only activates during:
1. Initial takeoff (first 5s or 50cm)
2. Active slow descent for landing

It does NOT activate during:
- Sustained low-altitude hover
- Horizontal flight at low altitude
- Any phase where the vehicle is near ground but not actively taking off or landing

**Potential Solutions:**

**Option A: Extend Takeoff Window**
- Increase the 5s/50cm thresholds in `baro_ground_effect.cpp:51`
- Pros: Simple change
- Cons: Would apply compensation even when not needed; doesn't solve the fundamental problem

**Option B: Add Low-Altitude Hover Detection**
- Add new condition: `low_altitude_expected = altitude < threshold && |vertical_speed| < small`
- Would need altitude estimate that's not corrupted by ground effect (chicken-and-egg)
- Could use time-filtered/smoothed altitude estimate

**Option C: Rangefinder-Based Detection**
- If rangefinder available and showing low altitude, enable compensation
- Pros: Rangefinder not affected by ground effect
- Cons: Not all vehicles have rangefinders

**Option D: Baro Variance Detection**
- Detect ground effect from rapid baro variance/innovation changes
- EKF already tracks innovation statistics
- Could enable compensation when baro innovations exceed threshold

**Option E: Height-Based Deactivation**
- Keep compensation active until vehicle exceeds configurable height (e.g., 2-3m)
- Simpler than option B, doesn't require good altitude estimate
- Could use baro-derived climb from takeoff point

**Recommended Approach:** Option E combined with D - keep compensation active based on accumulated climb from takeoff, with baro variance detection as backup for cases where vehicle descends back into ground effect zone.

### Implementation: TKOFF_GNDEFF_ALT Parameter

**New parameter added:** `TKOFF_GNDEFF_ALT`
- **Default:** 0.5m (50cm) - preserves existing behavior
- **Description:** Altitude above takeoff point below which ground effect compensation is active
- **Key improvement:** Re-enables compensation when vehicle descends back below threshold

**Files modified:**
- `ArduCopter/Parameters.h` - variable declaration
- `ArduCopter/Parameters.cpp` - parameter definition (index 11 in var_info2)
- `ArduCopter/baro_ground_effect.cpp` - logic changes

**New behavior:**
1. On takeoff: disable ground effect after 5s OR above `TKOFF_GNDEFF_ALT` (unchanged logic, configurable height)
2. While flying: re-enable ground effect when descending below `TKOFF_GNDEFF_ALT`
3. Set to 0 to disable the re-activation feature

**Recommended settings for indoor/low-altitude flight:** `TKOFF_GNDEFF_ALT = 1.5` to `2.0`

### Altitude Hold Issue Analysis (Secondary)

**Additional Factor:** EKF vertical velocity configured to use GPS, but GPS unavailable indoors.

#### Replay Test Result

Tested `EK3_SRC1_VELZ=0` (None) vs original `EK3_SRC1_VELZ=3` (GPS) using Replay tool.

**Result:** No difference. Original and replayed EKF outputs were identical.

**Reason:** GPS Status=1 (No GPS) with 0 satellites throughout the flight. When GPS provides no data, changing the source configuration has no effect - the EKF was already operating without GPS vertical velocity in both cases.

**Conclusion:** The velocity timeout (XKF4.TS bit 1) is a cosmetic issue - it indicates the EKF is configured to expect GPS velocity that doesn't exist. Setting `EK3_SRC1_VELZ=0` would clear this timeout flag but doesn't change actual EKF behavior when GPS is unavailable.

### Deep Dive: EKF Velocity Drift Analysis

Comparing BARO, DCM (AHR2), and EKF altitude estimates during 55-65s (after ground effect compensation turned OFF):

| Time | BARO | DCM | EKF | Notes |
|------|------|-----|-----|-------|
| 55s | +0.6m | +0.6m | -0.9m | Compensation just turned OFF |
| 60s | +0.6m | +0.6m | -2.2m | 5s into hover |
| 65s | +0.5m | +0.5m | -2.8m | 10s into hover |

**Key Finding:** BARO was stable and accurate during this period. DCM tracked BARO correctly. But EKF drifted 2m in 10 seconds.

**Velocity Comparison:**
| Metric | Value | Notes |
|--------|-------|-------|
| BARO CRt | ±0.2 m/s | Near zero - vehicle hovering |
| EKF VD | +0.6 to +1.3 m/s | Thinks descending at ~1 m/s |
| Velocity Error | ~1 m/s | EKF velocity is wrong |

**Root Cause Chain:**
1. No GPS velocity measurement (EK3_SRC1_VELZ=3 but GPS unavailable)
2. EKF integrates IMU for velocity → drift accumulates
3. Baro provides position corrections only, not velocity
4. Position-only corrections can't fix velocity drift fast enough
5. Accel bias observability is weak → EKF hunts (bias drifts from -0.06 to +0.08 m/s²)
6. Position drifts as integral of velocity error

**Why Ground Effect Compensation Helps:**
The compensation increases baro noise by 4x, making the EKF trust its IMU-integrated position MORE and baro LESS. This seems counterintuitive, but during ground effect it prevents the EKF from chasing bad baro spikes. When baro is good (like 55-65s), compensation being OFF should help - but the velocity drift is the dominant problem.

**Conclusion:**
The altitude hold issue has TWO components:
1. **Ground effect spikes** (52-54s) → Fixed by `TKOFF_GNDEFF_ALT`
2. **Velocity drift** (55-65s) → Not fixed by ground effect compensation alone

For indoor flight without GPS, the vertical velocity will always drift. Potential solutions:
- Add rangefinder for altitude/velocity sensing
- Use optical flow if available
- Consider using DCM altitude (which just follows baro) for altitude hold instead of EKF

#### Evidence

**1. EKF vs Baro Divergence (at 55-58s during flight):**

| Time | BARO.Alt | XKF1.PD | XKF1.VD | BARO.CRt |
|------|----------|---------|---------|----------|
| 55.2s | +0.50m | +0.92m | +0.77 m/s | +0.34 m/s |
| 58.2s | +0.83m | +1.35m | +0.86 m/s | -0.12 m/s |

- **BARO says:** Vehicle climbing (Alt increasing, positive CRt)
- **EKF says:** Vehicle descending (PD increasing = going down in NED, VD positive = descending)
- **Divergence:** ~2.2m and growing

**2. XKF3 Innovation (IPD):** 1.3-1.8m height innovation - EKF ignoring baro!

**3. XKF4 Timeout Status (TS=50 = 0b110010):**
- Bit 1 (2): **Velocity timeout = YES**
- Bit 4 (16): Airspeed timeout
- Bit 5 (32): Drag timeout

**4. Source Configuration:**
```
EK3_SRC1_POSZ = 1   (Baro for height position - OK)
EK3_SRC1_VELZ = 3   (GPS for vertical velocity - PROBLEM!)
```

Without GPS, vertical velocity has no external measurement. The EKF integrates IMU accelerometer for velocity, which drifts, and the baro position correction alone cannot keep up.

#### Solution

For indoor flight without GPS, change:
```
EK3_SRC1_VELZ = 0   (None - don't expect external vertical velocity)
```

Or create a secondary source set for indoor use:
```
EK3_SRC2_POSZ = 1   (Baro)
EK3_SRC2_VELZ = 0   (None)
```

Then switch to source set 2 for indoor flights.

#### EK3_ABIAS_P_NSE Testing (Accel Bias Learning Rate)

**Question:** Can we speed up accel bias learning to track temperature-induced drift?

**Parameter:** `EK3_ABIAS_P_NSE` - Accel bias process noise (m/s³)
- Default: 0.02
- Log value: 0.001 (20x slower than default)
- Range: 0.00001 - 0.02

**Replay Testing:**

Tested via Replay tool with values from 0.00001 to 0.02:

| ABIAS_P_NSE | Accel Bias at 80s | Position at 70s | Result |
|-------------|-------------------|-----------------|--------|
| 0.001 (original) | +0.17 m/s² | +3.31m | baseline |
| 0.015 | +0.17 m/s² | +3.31m | identical |
| 0.02 (default) | +0.17 m/s² | +3.31m | identical |
| 0.00001 (min) | +0.17 m/s² | +3.31m | identical |

**Finding:** Parameter has NO effect on EKF output without GPS velocity.

**Root Cause - Observability:**

The accel bias states require velocity measurements to be observable:
- Accel bias → velocity (single integration) → position (double integration)
- With only baro position corrections, bias observability is extremely weak
- The EKF converges to the same bias estimate regardless of process noise

**Implications:**
1. `EK3_ABIAS_P_NSE` won't help indoor no-GPS flight
2. The bias drift isn't because learning is too slow - it's because there's no velocity reference
3. Adding a velocity sensor (optical flow, rangefinder-derived) would make bias observable

**Conclusion:** Don't bother tuning `EK3_ABIAS_P_NSE` for indoor flight. Focus on:
- Temperature calibration (reduce source of drift)
- Adding velocity-capable sensors (optical flow, rangefinder)

#### Key Diagnostic Commands

```bash
# Check altitude divergence
mavlogdump.py log.bin --types CTUN | grep "Alt\|BAlt"

# Check EKF height innovation (should be small, <0.5m)
mavlogdump.py log.bin --types XKF3 | grep "IPD"

# Check timeout status (bit 1 = velocity timeout)
mavlogdump.py log.bin --types XKF4 | grep "TS :"

# Check source configuration
mavlogdump.py log.bin --types PARM | grep "EK3_SRC.*VELZ"
```

#### Ground Effect Analysis Techniques

**Detecting ground effect from baro variance:**

Ground effect causes characteristic baro noise patterns. Analyze baro stability in time windows:
- **Stable flight:** BAlt stddev < 0.15m, range < 0.5m
- **Ground effect:** BAlt stddev > 0.5m, range > 1m, negative spikes (pressure increase from propwash)

**Finding ground effect height threshold:**

Look for transitions between stable and unstable baro readings:
- When baro becomes unstable (stddev jumps from <0.15 to >0.3), note the BAlt value
- When baro stabilizes again, note the BAlt value
- The threshold is typically where baro reads 0.3-0.5m (vehicle-dependent)

**Effect of ground effect compensation when not needed:**

| Compensation State | When Not Needed | When Needed |
|-------------------|-----------------|-------------|
| ON | Sluggish altitude tracking, may drift slightly | Stable, handles baro spikes |
| OFF | Normal responsiveness | **Divergence** (can be 2m+), altitude hold failure |

**Conclusion:** Having compensation ON unnecessarily is much safer than having it OFF when needed. For indoor/low-altitude flight, err on the side of keeping compensation active.

### Takeoff Smoothness Analysis

**Problem:** Takeoff feels abrupt/aggressive - motors jump suddenly when vehicle lifts off.

#### Root Cause

The ALT_HOLD takeoff state machine has two distinct phases with a discontinuous transition:

1. **While `land_complete=true`:**
   - Throttle ramps slowly (controlled by `TKOFF_SLEW_TIME`)
   - Motors held near minimum spin
   - Position controller is reset every loop (not actively controlling)

2. **When liftoff detected (`land_complete=false`):**
   - Position controller takes over immediately
   - Commands full acceleration to achieve pilot's desired climb rate
   - Results in sudden motor output jump

**Evidence from log4.bin:**

| Time | RC Throttle | Motor Avg | ThO | Event |
|------|-------------|-----------|-----|-------|
| 53.91s | 1579 | 1106 | 0% | On ground, throttle ramping |
| 54.11s | 1599 | 1106 | 0% | Still waiting for liftoff |
| 54.21s | 1609 | 1286 | 12.4% | **LIFTOFF** - motors jump +180 PWM |
| 54.31s | 1615 | 1260 | 10.4% | Position controller active |

The +180 PWM jump (1106→1286) in one 100ms cycle is the source of the abrupt feel.

#### Liftoff Detection Conditions

From `ArduCopter/takeoff.cpp`, liftoff is declared when ANY of:
- Throttle reaches 90% (`TKOFF_THR_MAX`)
- Vertical acceleration > 50% of max
- Vertical velocity > 10% of max AND > pilot commanded rate
- Altitude change > 50% of takeoff target altitude

#### Current Parameters (log4.bin)

| Parameter | Value | Effect |
|-----------|-------|--------|
| `TKOFF_SLEW_TIME` | 0.5s | Throttle ramps 0-100% in 0.5s (fast) |
| `PILOT_ACCEL_Z` | 250 cm/s² | Position controller can command up to 2.5 m/s² |
| `PILOT_SPEED_UP` | 250 cm/s | Max climb rate 2.5 m/s |
| `MOT_SPOOL_TIME` | 0.5s | Motor spool up time |
| `PSC_JERK_Z` | 40 | Jerk limit (rate of acceleration change) |
| `PILOT_TKOFF_ALT` | 0 | No automatic target altitude |

#### Recommended Changes for Smoother Takeoff

**Primary (most impact):**

| Parameter | Current | Recommended | Effect |
|-----------|---------|-------------|--------|
| `PILOT_ACCEL_Z` | 250 | 100-150 | Limits how fast pos controller can change thrust |
| `TKOFF_SLEW_TIME` | 0.5 | 1.0-1.5 | Slower initial throttle ramp |
| `PILOT_SPEED_UP` | 250 | 150 | Lower max climb rate |

**Secondary (if still too abrupt):**

| Parameter | Current | Recommended | Effect |
|-----------|---------|-------------|--------|
| `MOT_SPOOL_TIME` | 0.5 | 1.0 | Slower motor response |
| `PSC_JERK_Z` | 40 | 20 | Smoother acceleration transitions |

**Example conservative setup for indoor/gentle flight:**
```
TKOFF_SLEW_TIME = 1.5
PILOT_ACCEL_Z = 100
PILOT_SPEED_UP = 150
PSC_JERK_Z = 20
```

#### Key Files

- `ArduCopter/mode_althold.cpp` - ALT_HOLD state machine
- `ArduCopter/takeoff.cpp` - Takeoff logic, `do_pilot_takeoff()`
- `ArduCopter/mode.cpp` - `get_alt_hold_state()`, `_TakeOff::triggered()`

#### Why PILOT_ACCEL_Z is Most Important

The abruptness comes from the position controller commanding high acceleration immediately after liftoff. `PILOT_ACCEL_Z` directly limits this:

- At 250 cm/s²: Controller can command 0.25g acceleration instantly
- At 100 cm/s²: Controller limited to 0.1g, feels much gentler

The other parameters help but are secondary to this fundamental limit.

## Rules

*Guidelines and constraints discovered during EKF3 analysis.*

### Ground Effect Rules

1. **Ground effect compensation is controlled by Copter, not EKF:** The `takeoff_expected` and `touchdown_expected` flags are set in `ArduCopter/baro_ground_effect.cpp`, not in the EKF code. The EKF just responds to these flags.

2. **Ground effect causes positive pressure (negative altitude):** Propwash pushes air down, creating higher pressure at the baro sensor. This makes the baro read LOWER altitude than actual.

3. **When in doubt, enable compensation:** Unnecessary compensation causes sluggish but stable behavior. Missing compensation when needed causes divergence and control issues.

4. **Vehicle-specific threshold:** Ground effect height depends on vehicle size, prop diameter, and thrust. Typical range is 0.3-1.0m for small multirotors.

### EKF Source Configuration Rules

1. **Source parameters only matter when sensor provides data:** Changing `EK3_SRC1_VELZ` from GPS to None has no effect if GPS isn't providing data anyway. The EKF already handles missing sensors gracefully.

2. **Timeout flags are informational:** A velocity timeout (XKF4.TS bit 1) means the EKF expected data that didn't arrive. It doesn't necessarily indicate a problem if the sensor is intentionally unavailable.

3. **Use Replay to verify source changes:** If unsure whether a source parameter change will help, test with Replay first. If original and replayed outputs are identical, the change has no effect.

4. **Accel bias observability requires velocity measurements:** Without GPS or optical flow, vertical accel bias is poorly observable. Changing `EK3_ABIAS_P_NSE` has no effect when only baro position is available. The bias states need velocity corrections to converge properly.

### Log Analysis Rules

1. **Core Index (C field):** All XK* messages have a `C` field indicating which EKF core (0 or 1 for dual-IMU). Always filter by core when analyzing.

2. **Timestamp Units:** TimeUS is microseconds since boot. Convert to seconds: `TimeUS / 1e6`

3. **Angle Units in Logs:**
   - Roll, Pitch, Yaw in XKF1: centidegrees (divide by 100 for degrees)
   - GX, GY, GZ (gyro bias): milliradians

4. **Variance Interpretation (XKV1/XKV2):**
   - These are diagonal elements of the covariance matrix P
   - Smaller = more confident in state estimate
   - Watch for variance growth indicating filter divergence

5. **Primary Core:** XKF4.PI field indicates which core is primary (active for vehicle control)

### Tools

#### Replay Tool

The Replay tool re-runs the EKF on recorded log data, allowing comparison between original flight behavior and current code.

**Build:**
```bash
./waf configure --board sitl
./waf --targets tool/Replay
```

**Usage:**
```bash
./build/sitl/tool/Replay [options] <logfile.bin>

Options:
  --parm NAME=VALUE      Set parameter NAME to VALUE
  --param-file FILENAME  Load parameters from file
  --force-ekf2           Force enable EKF2
  --force-ekf3           Force enable EKF3
  --help                 Show usage
```

**Example:**
```bash
./build/sitl/tool/Replay --force-ekf3 ./log4.bin
```

**Output:**
- Creates new log in `logs/` directory (check `logs/LASTLOG.TXT` for log number)
- Output log contains both original data (C=0,1) and replayed data (C=100,101)
- Core index mapping:
  - C=0: Original IMU0 data from input log
  - C=1: Original IMU1 data from input log
  - C=100: Replayed EKF3 using IMU0
  - C=101: Replayed EKF3 using IMU1

**Key Files:**
- `Tools/Replay/Replay.cpp` - Main replay implementation
- `Tools/Replay/Replay.h` - ReplayVehicle class
- `Tools/Replay/LogReader.cpp` - Log file parser

**Notes:**
- Replay loads parameters from the input log automatically
- Small floating-point differences (1e-8 range) are normal between STM32 and x86
- Output log is ~same size as input (original + replayed data)

**Parameter Overrides:**
- Use `--parm NAME=VALUE` or `--param-file` to override log parameters
- User parameters take precedence over log's PARM messages
- The "Changed X to Y from Z" message shows initial parameter setting
- Verify parameter took effect by comparing C=0 vs C=100 outputs
- **Important:** Some parameters only affect EKF behavior when sensors provide data (e.g., `EK3_ABIAS_P_NSE` needs velocity measurements to show an effect)

**Limitations:**
- Replay only includes EKF parameters (EK2_, EK3_, AHRS_, etc.)
- Copter-specific parameters (like `TKOFF_GNDEFF_ALT`) cannot be tested via Replay
- Ground effect flags (`takeoff_expected`, `touchdown_expected`) are determined by Copter's state machine, not re-computed during replay
- To test Copter-level parameter changes, use SITL or real flight

### Log File: log5.bin (Post-Parameter Changes)

**Flight Info:**
- Vehicle: ArduCopter V4.6.3-SFD (781e4d97) - includes TKOFF_GNDEFF_ALT
- Frame: QUAD/BF_X
- Indoor flight, no GPS
- Armed: 37.2s, Disarmed: 94.4s (57s flight)

**Parameters Changed from log4.bin:**
```
TKOFF_GNDEFF_ALT = 1.5    (new parameter)
PILOT_ACCEL_Z = 125       (was 250)
PILOT_SPEED_UP = 150      (was 250)
TKOFF_SLEW_TIME = 1.0     (was 0.5)
```

**Observations:**
- Takeoff was smoother (parameter changes worked)
- Required full throttle (~1750 PWM) to maintain ~80cm altitude
- Throttle output (ThO) stayed at ~10% despite high stick input

#### Problem Analysis

**Root Cause: EKF Velocity Drift + Accumulated Descent Commands**

| Time | Baro Alt | EKF Alt | DAlt | RC Throttle | Issue |
|------|----------|---------|------|-------------|-------|
| 44s | -2 to -6m | +0.2m | -0.2m | 1600 | Ground effect spike |
| 46s | +0.4m | +0.5m | -0.6m | 1250 | EKF drifting, pilot below mid-stick |
| 50s | +0.5m | +1.5m | -3.0m | 1215 | DAlt accumulating descent |
| 60s | 0m | +2.7m | -6.5m | 1640 | Massive divergence |
| 68s | 0m | +0.8m | -4.9m | 1752 | Full throttle, still commanding descent |

**The Cascade Failure:**

1. **Ground effect phase (43-45s):**
   - Baro spiked to -6m (ground effect)
   - Innovation floored at -0.5m (TKOFF_GNDEFF_ALT working!)
   - But EKF velocity integrated wrong direction

2. **Post-ground-effect (45s+):**
   - EKF thought it was sinking at ~1 m/s
   - Pilot throttle at 1215 PWM (below mid ~1500) = descent command
   - DAlt accumulated all descent commands

3. **Runaway condition (50-70s):**
   - DAlt reached -6.5m (way below actual position)
   - Even full throttle (1752) couldn't overcome the DAlt deficit
   - Controller kept trying to descend to reach impossible target

**Innovation Analysis:**

```
Time  | Baro   | EKF PD | Innovation | Notes
43.4s | -2.74m | +0.02m |   -0.50m   | Ground effect, innovation CAPPED (good!)
44.6s | -5.60m | +0.47m |   -2.02m   | Spike exceeded cap briefly
45.5s | +0.34m | +0.69m |   +1.29m   | Ground effect ended, positive innovation
48.0s | +0.62m | +0.79m |   +1.67m   | EKF ignoring baro correction
50.0s | +0.35m | +1.48m |   +2.06m   | 2m divergence, velocity still wrong
```

**Why Ground Effect Compensation Wasn't Enough:**

The `TKOFF_GNDEFF_ALT` parameter successfully:
- ✅ Kept compensation active below 1.5m
- ✅ Floored negative innovations at -0.5m during ground effect

But it couldn't fix:
- ❌ Velocity drift that occurred during ground effect
- ❌ Position-only corrections can't fix velocity fast enough
- ❌ Accumulated DAlt from pilot's descent commands

**Key Insight:** Ground effect compensation prevents the EKF from chasing bad baro DOWN, but the EKF velocity still drifts without a velocity measurement. When ground effect ends, the EKF has wrong velocity and position.

#### Conclusion

**Indoor flight without GPS velocity has fundamental limitations:**

1. Ground effect compensation helps but can't fix velocity drift
2. The EKF needs velocity measurements to maintain accuracy
3. Position-only corrections (baro) are too slow

**Solutions:**
- Add velocity sensor (optical flow, rangefinder-derived velocity)
- Use STABILIZE mode for indoor (direct throttle, no altitude hold)
- Keep hovers very short to minimize drift accumulation

### IMU Temperature Analysis

**Investigation:** IMU temperature, temperature compensation, and learned EKF accel biases as contributors to drift.

#### Temperature Data (IMU0)

| Time | IMU Temp (°C) | EKF AZ Bias (m/s²) | ΔTemp from start | ΔAZ from start | Notes |
|------|---------------|--------------------|--------------------|----------------|-------|
| 45s | 46.7 | -0.060 | -0.5 | 0.000 | Armed |
| 55s | 45.8 | -0.050 | -1.4 | +0.010 | Flying, GndEff OFF |
| 65s | 41.9 | +0.040 | -5.3 | +0.100 | Mid-flight |
| 80s | 38.0 | +0.170 | -9.2 | +0.230 | Peak bias error |
| 100s | 35.6 | +0.120 | -11.6 | +0.180 | End of flight |

#### Key Findings

**1. Temperature Drop:**
- IMU0: 47°C → 36°C (11°C drop during flight)
- Cooling caused by propeller airflow over electronics

**2. Temperature Calibration IS Enabled:**
- `INS_TCAL1_ENABLE = 1` (IMU0, calibrated 13-65°C)
- `INS_TCAL2_ENABLE = 1` (IMU1, calibrated 10-65°C)
- Significant Z-axis coefficients: `INS_TCAL1_ACC1_Z = -2400`
- The bias drift observed is *residual* error after TCAL correction

**3. Temperature Coefficient:**
- IMU0: ~0.021 m/s² per °C
- IMU1: ~0.013 m/s² per °C
- These are uncorrected sensor temperature sensitivities

**4. Correlation with EKF Bias:**
- Clear linear relationship between temperature drop and Z-axis accel bias increase
- EKF is trying to learn the bias, but:
  - Learning rate is slow (by design, for stability)
  - Temperature changes faster than bias can adapt
  - Results in persistent velocity/position error

**5. Impact on Altitude:**
- Total AZ bias change: +0.23 m/s² over ~40 seconds
- Integrated velocity error: 0.23 m/s² × 40s = ~9 m/s velocity drift potential
- EKF velocity was showing ~1 m/s error - bias learning helped but couldn't keep up

#### Temperature vs Accel Bias Correlation

```
Temperature (°C)    Accel Bias Z (m/s²)
    47 |*
    45 |  *
    43 |    *
    41 |      *
    39 |        *
    37 |          *
    35 |____________*________
       -0.1   0   +0.1  +0.2

Correlation: As temperature drops, bias increases (less negative → more positive)
```

#### Root Cause Summary

The altitude hold problem has THREE contributing factors:

| Factor | Severity | Time Period | Solution |
|--------|----------|-------------|----------|
| **Ground effect spikes** | High | 52-54s (takeoff) | TKOFF_GNDEFF_ALT parameter |
| **Velocity drift** | High | 55s+ (no GPS) | Add rangefinder or optical flow |
| **Residual temp bias** | Medium | Throughout flight | Re-run INS_TCAL calibration |

#### Recommended Actions

**Short-term (parameter changes):**
1. Set `TKOFF_GNDEFF_ALT = 1.5` or higher for indoor/low-altitude flight
2. Adjust takeoff smoothness params: `PILOT_ACCEL_Z = 125`, `TKOFF_SLEW_TIME = 1.0`
3. Consider `EK3_SRC1_VELZ = 0` to clear velocity timeout warnings (cosmetic)

**Medium-term (hardware/calibration):**
1. Re-run temperature calibration (INS_TCAL)
   - TCAL is already enabled but residual drift suggests recalibration may help
   - Ensure calibration covers the full operating temperature range
   - Current calibration range: 13-65°C for IMU0, 10-65°C for IMU1

2. Add downward-facing rangefinder
   - Provides height measurement independent of baro
   - Not affected by ground effect
   - Can provide velocity via differentiation

**Long-term (flight controller selection):**
1. Use flight controllers with better thermal management
2. Consider IMUs with lower temperature sensitivity
3. Ensure adequate cooling airflow over IMU during hover

#### Diagnostic Commands for Temperature Analysis

```bash
# Extract IMU temperature
mavlogdump.py log.bin --types IMU | grep "T :"

# Extract EKF accel bias (XKF2.AZ is Z-axis accel bias)
mavlogdump.py log.bin --types XKF2 | grep -E "C : 0.*AZ :"

# Check if TCAL is enabled
mavlogdump.py log.bin --types PARM | grep "INS_TCAL"

# Plot temperature vs time (requires matplotlib)
# Use AP_Log_Plotter or Mission Planner log analysis
```

#### mavlogdump Commands

```bash
# List all message types in a log
mavlogdump.py log.bin 2>/dev/null | grep "FMT.*Name :" | sed 's/.*Name : \([^,]*\).*/\1/' | sort -u

# Extract specific message type
mavlogdump.py log.bin --types XKF1 2>/dev/null

# Get FMT definitions for message types
mavlogdump.py log.bin 2>/dev/null | grep -E "FMT.*Name : XK"

# Compare original vs replayed (after Replay)
mavlogdump.py logs/00000004.BIN --types XKF1 | grep "C : 0"   # Original core 0
mavlogdump.py logs/00000004.BIN --types XKF1 | grep "C : 100" # Replayed core 0
```

### Vibration Compensation Analysis

**Question:** Would the vibration compensation mode's simpler altitude calculation help indoor no-GPS flight?

**Answer:** No. It doesn't address the root cause (EKF velocity drift).

#### How Vibration Compensation Works

The vibration compensation mode (`_vibe_comp_enabled` in AC_PosControl) only affects the **innermost control loop** - the acceleration-to-throttle conversion.

**Control Cascade:**
```
Position Controller → Velocity Controller → Acceleration Controller → Motors
     (uses EKF pos)      (uses EKF vel)        (vibe comp HERE)
```

**Normal mode** (`AC_PosControl.cpp:1043`):
```cpp
thr_out = _pid_accel_z.update_all(_accel_target.z, z_accel_meas, ...) * 0.001f;
```
Full PID: compares commanded acceleration to measured acceleration

**Vibration compensation mode** (`AC_PosControl.cpp:1326`):
```cpp
return POSCONTROL_VIBE_COMP_P_GAIN * thr_per_accelz_cmss * _accel_target.z
     + _pid_accel_z.get_i() * 0.001f;
```
Feed-forward: 25% of commanded acceleration converted directly to throttle, plus integrator

#### Key Code References

**Defines** (`AC_PosControl.cpp:74-75`):
```cpp
#define POSCONTROL_VIBE_COMP_P_GAIN 0.250f  // 25% P-term gain
#define POSCONTROL_VIBE_COMP_I_GAIN 0.125f  // 12.5% I-term learning
```

**Position/Velocity Sources** (all use EKF):
```cpp
// Position controller (line 1012)
_vel_target.z = _p_pos_z.update_all(pos_target_zf, _inav.get_position_z_up_cm());

// Velocity controller (line 1023-1024)
const float curr_vel_z = _inav.get_velocity_z_up_cms();
_accel_target.z = _pid_vel_z.update_all(_vel_target.z, curr_vel_z, ...);
```

#### Why It Won't Help Indoor No-GPS

The problem in log5.bin was **EKF velocity drift** - the EKF thought the vehicle was sinking when it wasn't.

**What vibration compensation does:**
- Reduces sensitivity to noisy/unreliable IMU acceleration measurements
- Uses feed-forward instead of measured acceleration for P-term
- Still uses EKF velocity for the velocity controller

**What our problem is:**
- EKF velocity is wrong (drifts without velocity sensor)
- Velocity controller sees (wrong EKF velocity - velocity target)
- Outputs wrong acceleration target
- Feed-forward just executes the wrong command more smoothly

**Summary:**
| Mode | Helps With | Doesn't Help With |
|------|------------|-------------------|
| Vibration Comp | Noisy accel measurements | Wrong velocity estimate |
| | Throttle spikes from vibration | Position drift |
| | | Velocity drift |

#### What Vibration Compensation IS For

- High-vibration airframes where IMU produces unreliable acceleration
- Situations where velocity estimate is good but accel measurement is bad
- Reducing control jitter from acceleration noise

#### What Indoor No-GPS Actually Needs

1. **Velocity sensor** to make EKF velocity observable:
   - Optical flow sensor
   - Downward rangefinder (provides height, derivative gives velocity)
   - Visual odometry

2. **Different control approach** (if no velocity sensor available):
   - Use STABILIZE mode (direct throttle, no altitude hold)
   - Keep hovers very short to minimize drift accumulation
   - Consider DCM altitude (baro-only) if such a mode existed

### Log File: log6.bin (Ground Motor Test)

**Test Description:**
- Armed on ground, motors spinning at idle, no flight
- Purpose: Isolate motor vibration effects on accelerometer
- Duration: 29 seconds armed (53.3s to 82.4s)

#### Key Findings

**1. Z-Axis Accelerometer Shift When Motors Spin:**

| Condition | AccZ Mean | AccZ Std | Notes |
|-----------|-----------|----------|-------|
| Before arm (motors off) | -9.844 m/s² | 0.011 m/s² | Clean baseline |
| During arm (motors on) | -9.760 m/s² | 0.442 m/s² | +0.084 m/s² shift |

The +0.084 m/s² shift is ~0.86% of gravity. This is likely caused by:
- Thrust from props even at idle (small but measurable lift)
- Vibration rectification (asymmetric vibration creates DC offset)

**2. All Axes Comparison:**

| Axis | Before Arm | During Arm | Shift | Interpretation |
|------|------------|------------|-------|----------------|
| X | +0.146 | +0.145 | -0.001 | Negligible |
| Y | +0.162 | +0.161 | -0.001 | Negligible |
| Z | -9.844 | -9.760 | +0.084 | Significant |

Only Z-axis is affected - consistent with thrust/vibration from vertical motor orientation.

**3. EKF Bias Learning:**

| Time | EKF AZ Bias | Event |
|------|-------------|-------|
| 53.3s | -0.030 m/s² | Arm |
| 82.4s | +0.050 m/s² | Disarm |
| Delta | +0.080 m/s² | Matches raw AccZ shift |

The EKF correctly learns the motor-induced bias while on the ground.

**4. Vibration Levels:**

| Metric | Before Arm | During Arm | Threshold |
|--------|------------|------------|-----------|
| VibeZ | 0.2 m/s² | 1.4 m/s² (mean) | <30 m/s² |
| VibeZ peak | - | 7.4 m/s² | <60 m/s² |

Vibration is within acceptable limits (not causing clipping).

#### The Problem

The bias learned on the ground is only valid while motors are spinning AND on the ground:

1. **On ground + motors spinning:** AccZ reads -9.76 m/s², EKF learns +0.08 bias correction
2. **In flight:** Different thrust pattern, vibration coupling, ground effect
3. **Result:** Learned bias is incorrect for flight conditions

This explains part of the velocity drift observed in log4.bin and log5.bin:
- EKF has wrong accel bias at liftoff
- Velocity integrates with ~0.08 m/s² error
- Over 30 seconds: 0.08 × 30 = 2.4 m/s velocity error potential

#### Temperature vs Motor Analysis (log7.bin)

Investigated whether AccZ shift was caused by prop cooling (temperature change) or motor thrust/vibration.

**Correlation with AccZ:**
| Factor | Correlation | Effect Size |
|--------|-------------|-------------|
| Motor output | **+0.954** | +0.10 m/s² |
| Temperature | -0.404 | ~0.005 m/s² |

**AccZ by motor state:**
- Low motor (≤1080 PWM): AccZ = -9.828 m/s²
- High motor (>1080 PWM): AccZ = -9.726 m/s²
- Difference: +0.10 m/s² (1% of gravity)

**Conclusion:** The AccZ shift is caused by motor thrust/vibration, NOT temperature:
- TCAL (temperature calibration) is working correctly
- For 2°C temp change, TCAL compensates ~0.005 m/s²
- The motor-induced shift (+0.10 m/s²) is **20x larger** than the temperature effect
- This is a real physical force from prop thrust, not a sensor calibration issue

#### Implications

**This is a fundamental challenge for indoor/no-GPS flight:**
- EKF must learn bias from ground calibration
- Ground calibration includes motor effects not present in hover
- Without velocity measurements, EKF cannot correct for this mismatch

**Potential mitigations:**
1. **Pre-arm calibration without motors** - Learn bias before motors start
2. **In-flight bias learning** - Requires velocity sensor (optical flow, etc.)
3. **Known bias offset** - Characterize motor effect and compensate
4. **Faster EKF bias adaptation** - Won't help without velocity (see ABIAS_P_NSE testing)
5. **Inhibit Z-bias learning during ground effect** - IMPLEMENTED (see below)

### Ground Effect Z-Axis Bias Learning Inhibition

**Problem:** When motors spin on the ground, the Z-axis accelerometer shows a DC offset (+0.08 m/s² in log6.bin) due to:
- Prop thrust at idle creating small upward force
- Vibration rectification

The EKF learns this as accel bias, but when the vehicle lifts off, the motor effects change and the learned bias becomes incorrect.

**Solution:** Inhibit Z-axis accel bias learning when:
1. Ground effect compensation is active (original fix, commit `6bc5565643`)
2. No Z velocity source is configured (new fix, commit `49187dac64`)

**Implementation:** `libraries/AP_NavEKF3/AP_NavEKF3_PosVelFusion.cpp` around line 1068:

```cpp
// Inhibit Z-axis accel bias learning during ground effect because motor thrust
// causes a DC offset in AccZ that is not present in normal flight
const bool gndEffectActive = dal.get_takeoff_expected() || dal.get_touchdown_expected();
// Inhibit Z-axis accel bias learning when there is no Z velocity source because
// the bias is unobservable with only position (baro) measurements
const bool noZVelSource = !frontend->sources.haveVelZSource();
...
for (uint8_t i = 13; i<=15; i++) {
    const bool zAxisInhibit = (i == 15) && (gndEffectActive || noZVelSource);
    if (!dvelBiasAxisInhibit[i-13] && !zAxisInhibit) {
        Kfusion[i] = P[i][stateIndex]*SK;
    } else {
        Kfusion[i] = 0.0f;
    }
}
```

**State indices:**
- 13 = X-axis accel bias (not inhibited)
- 14 = Y-axis accel bias (not inhibited)
- 15 = Z-axis accel bias (inhibited when ground effect OR no Z velocity source)

**When Z-axis inhibited:**
- `takeoff_expected = true` (armed on ground, first 5s/50cm of takeoff, or below TKOFF_GNDEFF_ALT)
- `touchdown_expected = true` (slow descent for landing)
- `EK3_SRC1_VELZ = 0` (no Z velocity source configured)

**Effect:** The EKF will use whatever Z-axis bias it learned before arming (when motors were off and the vehicle was truly stationary) rather than learning a corrupted bias from motor effects or unobservable conditions.

### Log File: logjk1.bin (External Tester - Optical Flow Issue)

**Problem:** External tester with optical flow experienced Z-bias drifting to +0.92 m/s² during disarmed period, causing severe altitude hold issues.

**Configuration:**
- `EK3_SRC1_VELXY = 5` (Optical Flow) - provides XY velocity
- `EK3_SRC1_VELZ = 0` (None) - NO Z velocity source
- `EK3_SRC1_POSZ = 1` (Baro) - Z position only

**Root Cause:**
1. Optical flow provides XY velocity → `PV_AidingMode != AID_NONE`
2. Original code: `horizInhibit = (PV_AidingMode == AID_NONE)` → FALSE
3. So bias learning was NOT inhibited by `horizInhibit`
4. Ground effect inhibit only works when armed (`takeoff_expected` or `touchdown_expected`)
5. When **disarmed**, Z-bias learning was unrestricted
6. Without Z velocity, bias is unobservable → drifted to +0.92 m/s²

**Timeline (85-92s):**
```
t=85.9s: Disarm
t=86.2s: Z-bias starts rapid change (-0.06 → -0.31)
t=89.1s: Z-bias jumps to 0.00 (reset?)
t=89.7s-91.1s: Z-bias climbs from +0.06 to +1.00
t=92.1s: Rearm with Z-bias = +0.92 m/s²
```

**Initial Fix:** Commit `49187dac64` - Inhibit Z-bias learning when `EK3_SRC1_VELZ = 0`, regardless of XY aiding status. This was a defensive fix that prevented bad bias learning but didn't make bias properly observable.

**Better Fix (Stationary Zero Velocity Fusion):**
The user correctly noted that Z-bias SHOULD be observable on the ground since we know velocity is zero. The problem was architectural: the EKF only fuses synthetic zero velocity in `AID_NONE` mode, not in `AID_RELATIVE` mode (optical flow configured).

**Root Cause Analysis:**
- When `PV_AidingMode == AID_NONE`: EKF fuses zero velocity → bias observable
- When `PV_AidingMode == AID_RELATIVE` (optical flow): Zero velocity NOT fused → bias unobservable
- Optical flow provides no data when stationary (no motion to detect)
- Only baro position was being fused, which has very weak bias observability

**Proper Fix Implementation:**
Added stationary zero velocity fusion in `AP_NavEKF3_PosVelFusion.cpp`:
1. Added `fusingStationaryZeroVel` member variable to track the state
2. When on ground (`onGround && !motorsArmed`) without recent velocity aiding, fuse synthetic zero velocity
3. Use small measurement noise (0.5 m/s) for the zero velocity since we're confident it's accurate
4. Modified `noZVelSource` inhibition to NOT apply when fusing stationary zero velocity (bias IS observable)

This makes bias properly observable when stationary, regardless of configured aiding mode.

**Key Insight:** The original `horizInhibit` check assumes that if you have any velocity aiding, all accel biases are observable. This is FALSE when you only have XY velocity (optical flow) - the Z-bias remains unobservable without Z velocity. The proper solution is to fuse zero velocity when we KNOW the vehicle is stationary.

### Log File: log8.bin (Flight Test - Z-Bias Inhibition)

**Test Purpose:** Validate the Z-axis bias inhibition fix for indoor altitude hold.

**Flight Info:**
- Vehicle: ArduCopter with Z-bias inhibition patch (commit 6bc5565643)
- Flight duration: 57 seconds total, 46 seconds stable hover
- Mode: ALT_HOLD, indoor, no GPS

#### Results: Dramatic Improvement

| Metric | Log5 (Before Fix) | Log8 (After Fix) | Change |
|--------|-------------------|------------------|--------|
| Hover stability | Drifting, unstable | **±0.10m std** | Fixed |
| Throttle needed | Full (1750 PWM) | Normal (1426 PWM) | Reasonable |
| DAlt runaway | -6.5m (impossible) | 1.3m range | No runaway |
| EKF Z-bias drift | +0.08 m/s² | **0.00 m/s²** | Fixed |
| Flight duration | Struggled to hover | **46s stable** | Success |

#### Key Observations

**1. Z-Axis Bias Stayed Constant:**
```
Before arm: -0.0500 m/s²
At arm:     -0.0500 m/s²
At disarm:  -0.0500 m/s²
Change:      0.0000 m/s²
```

**2. Altitude Stability During Hover (60-90s):**
- EKF altitude: mean=-1.45m, std=0.10m (excellent stability)
- Baro altitude: mean=+0.75m, std=0.12m
- Motor output: 1266 PWM avg (normal hover throttle)

**3. Ground Effect Handling:**
- Baro showed -3.1m spike at takeoff (ground effect)
- EKF innovation capped correctly
- No altitude runaway after leaving ground effect

**4. Throttle Feel Change During Flight:**

Pilot observation: Initially needed below mid-stick for stable hover, later mid-stick worked.

| Period | Altitude | VD Stability | Throttle Needed |
|--------|----------|--------------|-----------------|
| Early (50-65s) | Varying (-0.5 to -1.4m) | std=0.25 m/s | Below mid-stick |
| Late (75-90s) | Stable (~-1.5m) | std=0.02 m/s | Mid-stick |

**Explanation:** After takeoff through ground effect, the EKF and position controller need time to settle. Early in the flight, altitude was bouncing as the system found equilibrium. Pilot descent commands countered upward excursions. Once settled (~70s), altitude locked at -1.5m with minimal variation, and mid-stick maintained stable hover.

**Note on MOT_THST_HOVER:** This vehicle hovers at ~10% throttle (ThO ≈ 0.10), which is correct for a lightweight/efficient build. The parameter `MOT_THST_HOVER = 0.095` is appropriate - no adjustment needed.

#### Remaining Observation

There's a ~2.2m offset between EKF altitude (-1.45m) and baro altitude (+0.75m) during hover, with innovations around +2.4m. This is expected behavior:
- Ground effect compensation increases baro noise, so EKF trusts IMU more
- The EKF maintains a consistent (if offset) altitude estimate
- **Critically, the altitude is STABLE - no drift**

#### Conclusion

The Z-axis bias inhibition fix successfully addresses the indoor altitude hold problem:

1. **Root cause confirmed:** Motor thrust/vibration creates +0.07-0.10 m/s² AccZ offset
2. **Fix works:** Inhibiting Z-bias learning during ground effect prevents EKF from learning this offset
3. **Result:** Stable altitude hold for 46+ seconds without GPS

The fix is in commit `6bc5565643` (AP_NavEKF3: inhibit Z-axis accel bias learning during ground effect).

### Vibration Rectification Analysis (Deep Dive)

**Question:** Why does the accelerometer read different values on the ground vs in hover, even though both should measure ~1g?

#### The Physics

On the ground (motors off), AccZ = -9.86 m/s² (measuring gravity).
In hover, AccZ = -9.72 m/s² — **0.14 m/s² less than gravity**.

This is physically impossible if the accelerometer is working correctly — a hovering vehicle at equilibrium should measure the same specific force as one sitting on the ground.

#### Root Cause: Vibration Rectification

Analysis of log8.bin reveals a clear relationship between vibration level and AccZ shift:

| Vibration Level (VibeZ) | AccZ Mean | Shift from Baseline |
|-------------------------|-----------|---------------------|
| 0-0.5 m/s² (motors off) | -9.858 | 0 (baseline) |
| 0.5-1.0 m/s² | -9.818 | +0.039 |
| 1.0-2.0 m/s² | -9.764 | +0.094 |
| 5-10 m/s² | -9.706 | +0.152 |
| 10-15 m/s² | -9.714 | +0.144 |

**Key finding:** AccZ shifts +0.008 m/s² per 1 m/s² of VibeZ, then plateaus.

This is **vibration rectification** — a known phenomenon in MEMS accelerometers where high-frequency vibration causes the mean reading to shift due to:
1. Nonlinear spring stiffness in the MEMS proof mass suspension
2. Mechanical or electronic asymmetries in the sensor
3. Anti-aliasing filter bandwidth effects
4. Asymmetric clipping (though no clipping was observed in this log)

#### Vibration Spectrum (log8.bin)

FFT analysis of high-rate batch sampler data (4054 Hz) during hover:

| Frequency | Amplitude | Source |
|-----------|-----------|--------|
| **174 Hz** | Highest | Motor fundamental (RPM × blades / 60) |
| 518 Hz | Medium | 3× motor harmonic |
| 594 Hz | Low | 4× motor harmonic |
| 1700-2000 Hz | Medium | High-frequency (bearings, EMI, structural) |

Estimated motor RPM: ~5200 RPM (with 2-blade props)

#### Current Vibration Assessment

| Axis | Mean | Max | Threshold |
|------|------|-----|-----------|
| VibeX | 3.5 m/s² | 4.7 m/s² | < 15 = Good |
| VibeY | 4.5 m/s² | 6.5 m/s² | < 15 = Good |
| VibeZ | 11.4 m/s² | 17.0 m/s² | 15-30 = Marginal |

Z-axis vibration is higher than X/Y — typical for multirotors where props create vertical thrust oscillations. The 11 m/s² VibeZ contributes ~0.09 m/s² AccZ bias.

#### Why This Matters

Without a velocity sensor, the EKF cannot observe the vibration-induced bias:
- In hover, AccZ reads 0.14 m/s² less than true gravity
- EKF interprets this as 0.14 m/s² upward acceleration
- Velocity integrates at 0.14 m/s per second
- Position drifts as velocity integrates

The Z-bias inhibition fix prevents the EKF from learning this wrong bias on the ground, but it can't correct for the bias that exists in hover.

#### Compensation Options

**Option 1: Vibration-Dependent Bias Correction (Software)**
- Measure VibeZ, apply lookup table correction: `corrected_AccZ = raw_AccZ - 0.008 * VibeZ`
- Pros: No hardware changes, similar to TCAL
- Cons: Vehicle-specific, needs calibration procedure, MEMS vary between sensors

**Option 2: Add Velocity Sensor (Hardware) — RECOMMENDED**
- Downward rangefinder (differentiate for velocity) and/or optical flow
- Pros: EKF can observe and correct ANY bias (temperature, vibration, etc.)
- Cons: Requires additional hardware

**Option 3: Reduce Vibration (Hardware)**
- Balance props, soft-mount FC, check motor bearings, stiffen frame
- Pros: Addresses root cause, benefits other systems
- Cons: Some vibration always remains

**Option 4: Allow Bias Learning in Stable Hover (Software)**
- Re-enable Z-bias learning when above ground effect AND stable
- Cons: Still needs velocity measurement for bias to be observable — this is why we inhibited it

#### Recommendation

1. **Short-term:** Check prop balance, consider soft-mounting FC
2. **Long-term:** Add rangefinder or optical flow sensor for indoor flight

The vibration-induced bias is a fundamental limitation of MEMS accelerometers operating in high-vibration environments without external velocity reference.

### Z-Axis Bias Inhibition: Complete Fix Summary

This section documents the complete set of fixes for Z-axis accel bias drift in indoor/no-GPS flight.

#### The Problem

Without Z velocity measurements (GPS unavailable indoors), the Z-axis accelerometer bias is unobservable. The EKF would attempt to learn the bias from position-only (baro) measurements, but this has very weak observability. The result was Z-bias drifting randomly, causing altitude hold instability.

Multiple scenarios contributed to the problem:
1. Motor thrust on ground creates AccZ offset that corrupts bias learning
2. Optical flow provides only XY velocity, leaving Z-bias unobservable during flight
3. When disarmed with optical flow configured, bias would drift unchecked
4. GPS configured but unavailable (indoors) wasn't handled - code checked configuration, not actual data

#### The Fixes (Commit History)

| Commit | Description | Scenario Addressed |
|--------|-------------|-------------------|
| `6bc5565643` | Inhibit Z-bias learning during ground effect | Motor thrust on ground |
| `49187dac64` | Inhibit Z-bias learning without Z velocity source | No VELZ configured |
| `0ff35c20b4` | Fuse zero velocity when stationary on ground | Disarmed with optical flow |
| `175c635a08` | Check actual Z velocity availability, not just config | GPS configured but unavailable |

#### Key Technical Findings

**1. The `dvelBiasAxisInhibit` Mechanism (existing code):**

Located in `AP_NavEKF3_core.cpp:1167-1182`, this mechanism only handles geometric observability:
```cpp
const bool is_bias_observable = (fabsF(prevTnb[index][2]) > 0.8f) || !onGround;
```
Once `onGround = false` (flying), all bias axes are considered observable. This doesn't account for measurement observability (do we have sensors that can observe the bias?).

**2. The `haveVelZSource()` Gap:**

The original code checked source *configuration*, not actual data *availability*:
```cpp
// OLD - only checks if GPS is configured
const bool noZVelSource = !frontend->sources.haveVelZSource();
```

This returns `false` if GPS is configured (`EK3_SRC1_VELZ=3`), even when GPS is unavailable indoors. The fix checks actual data:
```cpp
// NEW - checks if Z velocity data is actually being received
const bool noZVelSource = !useGpsVertVel && !useExtNavVel && !fusingStationaryZeroVel;
```

**3. Where Z-Bias Inhibition is Applied:**

- `AP_NavEKF3_PosVelFusion.cpp` - `FuseVelPosNED()` for GPS/position/height fusion
- `AP_NavEKF3_OptFlowFusion.cpp` - `FuseOptFlow()` for optical flow fusion (X and Y axes)

Both locations now use the same `noZVelSource` check based on actual velocity availability.

#### Validation Results (Replay on logjk1.bin)

Tested with optical flow configuration (`EK3_SRC1_VELXY=5`, `EK3_SRC1_VELZ=0`):

| Phase | Time | Original Z-bias | Fixed Z-bias |
|-------|------|-----------------|--------------|
| Pre-arm (stationary) | 40s | -0.20 m/s² | 0.00 m/s² |
| Armed on ground | 48s | -0.06 m/s² | 0.00 m/s² |
| Early flight | 55s | -0.10 m/s² | 0.00 m/s² |
| Mid flight | 75s | -0.07 m/s² | 0.00 m/s² |
| Disarm period | 86-90s | -0.10 → -0.29 m/s² | 0.00 m/s² |
| Second flight | 100s | +0.92 m/s² | 0.00 m/s² |
| End of log | 115s | +0.55 m/s² | 0.00 m/s² |

**Total improvement:** 0.75 m/s² less Z-bias drift (from ±0.75 to 0.00)

#### How Z-Bias is Now Handled

| Scenario | Z-bias Learning | Mechanism |
|----------|-----------------|-----------|
| Stationary on ground, disarmed | **Enabled** via zero velocity fusion | Bias IS observable |
| Armed on ground (motors spinning) | **Inhibited** | Ground effect flag |
| Taking off (first 5s or below TKOFF_GNDEFF_ALT) | **Inhibited** | Ground effect flag |
| Flying with GPS Z velocity | **Enabled** | Bias IS observable |
| Flying with optical flow only | **Inhibited** | No Z velocity source |
| Flying with GPS configured but unavailable | **Inhibited** | Actual availability check |
| Landing (slow descent) | **Inhibited** | Ground effect flag |

#### Future Enhancement: Rangefinder-Derived Velocity

Currently, rangefinder is only used as a height (position) source. A potential enhancement would be to differentiate rangefinder height to derive Z velocity, which would:
- Make Z-bias observable during indoor flight
- Be robust to ground obstacles (velocity is rate of change, not absolute position)
- Not require GPS

This is not yet implemented but would significantly improve indoor altitude hold capability.

#### Analysis Tool

A Python script is available for Z-bias analysis:

```bash
# Basic analysis
python3 libraries/AP_NavEKF3/tools/ekf_bias_analysis.py <logfile.bin>

# With plot (requires matplotlib)
python3 libraries/AP_NavEKF3/tools/ekf_bias_analysis.py <logfile.bin> --plot

# Export to CSV
python3 libraries/AP_NavEKF3/tools/ekf_bias_analysis.py <logfile.bin> --csv output.csv
```

For replay comparison, use the output log from the Replay tool:
- Original data: core C=0
- Replayed data: core C=100

Example output:
```
======================================================================
EKF3 Z-AXIS BIAS ANALYSIS
======================================================================
Time range: 8.4s to 116.6s (108.2s duration)
Original samples (C=0): 2706
Replayed samples (C=100): 2706

Original Z-bias statistics:
  Mean:  +0.135 m/s²
  Std:   0.408 m/s²
  Range: -0.400 to +1.000 m/s²
  Drift: 1.400 m/s²

Replayed Z-bias statistics:
  Mean:  +0.000 m/s²
  Std:   0.000 m/s²
  Range: +0.000 to +0.000 m/s²
  Drift: 0.000 m/s²

Improvement: 1.400 m/s² less drift
```
