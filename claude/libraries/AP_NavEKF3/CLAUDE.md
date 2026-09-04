# AP_NavEKF3 - CLAUDE.md

Reference guide for working with the EKF3 navigation filter in ArduPilot.

## Architecture

### State Vector (24 states)

From `AP_NavEKF3_core.h`:

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

### Directory Structure

- `AP_NavEKF3.h` - Main interface/frontend
- `AP_NavEKF3_core.h` - Core EKF state and structures
- `AP_NavEKF3_feature.h` - Feature flags/configuration
- `AP_NavEKF3_PosVelFusion.cpp` - Position/velocity fusion (baro, GPS, external nav)
- `AP_NavEKF3_OptFlowFusion.cpp` - Optical flow fusion
- `AP_NavEKF3_VehicleStatus.cpp` - Vehicle state detection (onGround, etc.)
- `LogStructure.h` - Log message definitions

## Data Abstraction Layer (DAL) and EKF Replay

### Why the DAL Exists

The EKF does NOT read sensors directly. All sensor data and external state enters the EKF through the DAL (`libraries/AP_DAL/`). When `LOG_REPLAY=1`, the DAL logs every input to the EKF into the onboard log. The Replay tool re-feeds this logged data to reproduce the exact EKF behavior.

**If the EKF reads anything that bypasses the DAL, replay will produce different results than the original flight.**

### What MUST Go Through the DAL

Any **runtime data** that influences EKF state estimation:

- **Sensor measurements**: gyro/accel deltas, GPS, baro, mag, rangefinder, optical flow, airspeed — all via `dal.ins()`, `dal.gps()`, `dal.baro()`, etc.
- **Per-instance sensor properties that vary at runtime**: e.g. `dal.ins().is_low_drift(instance)`, `dal.ins().get_accel_vrf_bias_z(instance)` — these are logged in the `RISI` struct per IMU
- **Vehicle state flags**: `dal.get_armed()`, `dal.get_takeoff_expected()`, `dal.get_touchdown_expected()`, `dal.get_fly_forward()`, `dal.get_hover_z_bias_enabled()` — logged in the `RFRN` struct
- **Any value set by vehicle code** that the EKF uses: if Copter sets a flag or value that changes EKF behavior, it must flow through the DAL (typically via AHRS → DAL RFRN bitfield)

### What Does NOT Need the DAL

- **Compile-time constants** (`#define`, `#if`): These are baked into the binary. Both the live flight and the Replay tool use the same binary, so `#if` branches evaluate identically. No logging needed.
- **EKF tuning parameters** (`AP_Param`): These are replayed via `PARM` log messages, not through the DAL sensor structs. The Replay tool can also override them with `--parm NAME=VALUE`.
- **EKF-internal state**: The state vector, covariance matrix, innovation sequences — these are computed, not inputs.

### How to Add New Data to the DAL

1. **Per-IMU instance data** → add to `log_RISI` struct in `AP_DAL/LogStructure.h`, populate in `AP_DAL_InertialSensor::start_frame()`, expose accessor on `AP_DAL_InertialSensor`
2. **Global flags/state** → add to `log_RFRN` struct, populate in `AP_DAL::start_frame()` from AHRS, expose accessor on `AP_DAL`
3. **Per-GPS instance data** → add to `log_RGPI`/`log_RGPJ` structs, similar pattern

### Common Mistakes

- **Calling `AP::ins()` from EKF code**: Use `dal.ins()` instead. Direct sensor access bypasses replay logging. The only exception is EKF code that runs before the DAL is initialized (rare).
- **Adding a vehicle-to-EKF flag without DAL**: If vehicle code (Copter, Plane) sets a bool/float on the EKF frontend that changes algorithm behavior, it must be logged. Route it through AHRS → DAL RFRN.
- **Assuming AP_Param values need DAL**: They don't — parameters are replayed via PARM log messages. But if you read a parameter value and cache it in a non-param member that the EKF reads, that cached value needs DAL treatment.

## Log Messages

| Message | Description |
|---------|-------------|
| **XKF1** | Main outputs: attitude (Roll/Pitch/Yaw), velocity NED, position NED, gyro bias |
| **XKF2** | Secondary outputs: accel bias, wind, magnetic field (earth & body), drag innovations |
| **XKF3** | Innovations: velocity, position, mag, yaw, airspeed + error metrics |
| **XKF4** | Variances/health: sqrt variances, tilt error, position resets, faults, timeouts |
| **XKF5** | Optical flow, rangefinder, HAGL, error magnitudes |
| **XKFD** | Body frame odometry innovations and variances |
| **XKFM** | On-ground-not-moving diagnostics (gyro/accel ratios) |
| **XKFS** | Sensor selection: mag/baro/GPS/airspeed indices, source set, fusion state. **Note:** MI field is magnetometer index, NOT IMU index |
| **XKQ** | Quaternion (Q1-Q4) |
| **XKT** | Timing: IMU/EKF sample intervals min/max |
| **XKTV** | Tilt error variance (symbolic vs difference method) |
| **XKV1** | State variances V00-V11 (quat, velocity, position, gyro bias) |
| **XKV2** | State variances V12-V23 (accel bias, earth mag, body mag, wind) |
| **XKY0** | Yaw estimator outputs and weights |
| **XKY1** | Yaw velocity innovations |

### XKF4 Status Fields

- **FS (Fault Status):** Bitmask of filter faults
- **TS (Timeout Status):** Bit 0=Position, Bit 1=Velocity, Bit 2=Height, Bit 3=Magnetometer, Bit 4=Airspeed, Bit 5=Drag
- **SS (Solution Status):** NavFilterStatusBit bitmask
- **PI:** Primary core index (which core is active for vehicle control)

### Log Analysis Tips

- All XK* messages have a `C` field for EKF core index (0 or 1 for dual-IMU). Always filter by core.
- TimeUS is microseconds since boot. Convert: `TimeUS / 1e6`
- XKF1 angles are centidegrees. GX/GY/GZ (gyro bias) are milliradians.
- XKV1/XKV2 are diagonal elements of covariance matrix P. Smaller = more confident. Watch for variance growth (filter divergence).

### Source Sets vs. Cores (common confusion)

**These are orthogonal concepts — do not conflate them:**

- **Core (lane)** — a complete EKF instance, typically one per IMU. `XKF*.C` identifies the core. "Lane switch" means the frontend picked a different core as primary; all cores still fuse the **same** sensors as configured by the currently-active source set.
- **Source set** — a runtime-switchable configuration bundle (`EK3_SRC1_*`, `EK3_SRC2_*`, `EK3_SRC3_*`) that selects *which* sensors to fuse for position/velocity/yaw. Only **one** source set is active at a time across **all** cores.

Source sets are switched **manually** — by the pilot via an RC option (`RC_OPTIONS`/auxiliary switch function `SOURCE_SET`), MAVLink, or Lua (`ahrs:set_posvelyaw_source_set()`). They do **not** provide automatic failover when a sensor glitches. If `SRC1_VELXY=3` (GPS) and GPS glitches, configuring `SRC2_VELXY=0` does *not* save you — nothing switches to SRC2 on its own.

**Implication for GPS-glitch failsafe recommendations:** Do not recommend "set SRC2 to baro as a fallback" expecting automatic redundancy — that's wrong. Real redundancy comes from:
- Multiple GPS units + blending (`GPS_AUTO_SWITCH`)
- EKF's built-in GPS glitch detection (`EK3_GLITCH_RADIUS`, variance-based failsafe `FS_EKF_THRESH`/`FS_EKF_ACTION`)
- Redundant sensors *within* the active source set (e.g. baro is always fused for height when `SRCn_POSZ=3 GPS` via the EKF's height-source hierarchy)
- A scripted / RC-triggered source-set switch for planned regime changes (e.g. indoor ↔ outdoor), not glitch response

## EKF Analysis Methodology

**Rule 1: No theories without data.** Do not speculate about EKF behavior based on code reading alone. The EKF is a complex dynamic system where multiple states interact. Theories MUST be validated against actual log data before being presented as explanations.

**Rule 2: Always cross-check with multiple sensors.** When analyzing altitude/position issues, compare ALL available sources:
- EKF estimate (XKF1 PD/VD)
- Barometer (BARO.Alt)
- Rangefinder (RFND.Dist)
- GPS altitude (GPS.Alt)
- Raw IMU (IMU.AccZ)

If your theory predicts the vehicle is at 2.5m but the rangefinder shows 17cm, your theory is wrong. The rangefinder is measuring physical reality.

**Rule 3: Extract data first, theorize second.** Before forming hypotheses:
1. Extract the relevant log messages (XKF1, XKF2, XKF4, CTUN, BARO, RFND, IMU, etc.)
2. Align timestamps and create comparison tables
3. Identify anomalies in the DATA, not in your mental model
4. Only then form hypotheses that explain ALL the observations

**Rule 4: Use Replay for controlled experiments.** To test whether a specific parameter or code change affects EKF behavior:
1. Run the original log through Replay to establish baseline
2. Modify the parameter/code
3. Run Replay again and compare XKF outputs
4. The difference (or lack thereof) is objective evidence

**Rule 5: Check ground truth.** When something looks wrong in the EKF:
- What does the rangefinder say? (direct distance measurement)
- What does the pilot report? (actual vehicle behavior)
- What does video show? (if available)
- Does the CTUN throttle output make sense for the claimed altitude?

**Sensor trust hierarchy for altitude (in ground effect):** Rangefinder > GPS > Baro. The rangefinder measures physical distance; baro is severely affected by prop wash on small drones.

**Log analysis checklist:**
- [ ] Extract PARM values for relevant parameters
- [ ] Extract ARM/DISARM events and flight mode changes
- [ ] Extract multiple altitude sources (BARO, RFND, XKF1.PD, GPS if available)
- [ ] Extract XKF4 status flags (takeoff_expected, touchdown_expected)
- [ ] Cross-check all sources before forming theories
- [ ] Identify which sensor is likely correct based on trust hierarchy

## Ground Effect Compensation

### How It Works

The EKF has two mechanisms for ground effect, both controlled by flags set in `libraries/AP_GroundEffect/AP_GroundEffect.cpp` (`ArduCopter/baro_ground_effect.cpp` is only the thin wrapper that feeds it):

1. **Innovation flooring:** Limits negative baro corrections during ground effect (`AP_NavEKF3_PosVelFusion.cpp`)
2. **Noise scaling:** Increases baro noise variance by 4x (`gndEffectBaroScaler = 4.0`)

Both are ONLY active when `takeoff_expected` OR `touchdown_expected` flags are true.

### When Flags Are Set

**`takeoff_expected = true`:** Armed AND `land_complete` is true AND mode is not THROW
**`takeoff_expected = false`:** 5s passed since takeoff OR vehicle above `GNDEFF_ALT`

**`touchdown_expected = true`:** Slow horizontal (XY speed demand ≤125cm/s OR actual ≤125cm/s) AND slow descent demanded

### The Gap

Hovering at low altitude (not taking off, not descending) has NEITHER flag true, so NO compensation. The `GNDEFF_ALT` parameter addresses this by re-enabling compensation when below the threshold.

| Flight Phase | takeoff_expected | touchdown_expected | Compensation |
|--------------|------------------|--------------------|--------------|
| On ground, armed | YES | NO | YES |
| First 5s or below GNDEFF_ALT | YES | NO | YES |
| Hovering above GNDEFF_ALT | NO | NO | NONE |
| Descending slowly for landing | NO | YES | YES |

### GNDEFF_ALT Tuning

Set **below** your typical hover altitude to avoid unnecessary compensation during stable hover:

| Hover Altitude | Recommended GNDEFF_ALT |
|----------------|------------------------------|
| ~0.5m | 0.3m |
| ~1.0m | 0.5-0.7m |
| ~1.5m | 1.0m |
| ~2.0m+ | 1.5m |

**If set too high:** Compensation stays active during stable hover, innovation gets clamped, EKF altitude drifts from baro.
**If set too low:** Ground effect spikes at low altitude corrupt the EKF estimate.

Ground effect causes **positive pressure (negative altitude)** — propwash pushes air down, baro reads lower than actual. Having compensation ON unnecessarily is safer than having it OFF when needed.

### GNDEFF_TMO Parameter

Requires BOTH a time delay AND the altitude threshold before ground effect compensation is disabled.

**Problem it solves:** On vehicles with severe baro ground effect (motor-induced pressure noise), the EKF altitude can falsely cross the GNDEFF_ALT threshold due to baro noise, prematurely disabling ground effect protection. This causes the EKF to trust garbage baro data, leading to altitude estimate runaway and inability to take off in AltHold.

**Logic:**
- `GNDEFF_TMO = 0`: only the altitude check is applied - clear when (altitude > threshold) OR (5s elapsed)
- `GNDEFF_TMO > 0` (default 2): Clear when (timeout AND altitude > threshold) OR (5s max elapsed)

**Recommended settings for vehicles with severe baro ground effect:**
```
GNDEFF_TMO = 2    # or 3 for more protection (seconds); this is the default
GNDEFF_ALT = 0.8  # adjust based on hover altitude (meters); default 0.5
```

This ensures the vehicle must be above the altitude threshold AND have been flying for the specified time before ground effect protection is removed. The 5s maximum timeout is always preserved.

## Z-Axis Accel Bias Learning Inhibition

**Branch-specific.** The ground-effect `zAxisInhibit` gate below, the hover Z-bias learning section after it and their parameters (`ACC_ZBIAS_LEARN`, `INS_ACC_VRFB_Z`) live on the SmallFastDrone-4.6 branches (`origin/pr-vrf-core`, `origin/pr-acro-bias-inhibit`), not on upstream master. On master the only accel-bias inhibition is the tilt/ground `dvelBiasAxisInhibit` gate in `AP_NavEKF3_core.cpp` (set around line 1176-1198, covariance row and column zeroed around 1794-1803); the stationary zero-velocity fusion is on master. Before a commit message, PR body or code comment cites any mechanism from this file, confirm the symbol exists on the base branch (`git grep zAxisInhibit upstream/master`). The self-review of PR #33498 caught a commit that claimed to "mirror the accel-Z bias inhibition under optical flow" on the strength of this section, plus two `setAccelBiasZ` / `accelBiasLearningInhibited` declarations that had leaked from the same branch.

### Problem

Without Z velocity measurements (no GPS indoors), the Z-axis accelerometer bias is poorly observable. Motor thrust/vibration creates a DC offset in AccZ (~+0.08-0.15 m/s²) that the EKF would incorrectly learn as bias. Multiple scenarios cause problems:

1. Motor thrust on ground creates AccZ offset
2. Optical flow provides only XY velocity, leaving Z-bias unobservable
3. When disarmed with optical flow, bias drifts unchecked
4. GPS configured but unavailable (indoors) — code must check actual data availability, not just configuration. The same rule applies to yaw sources; see "Gyro Bias Observability Without a Yaw Reference" below

### How Inhibition Works

In `AP_NavEKF3_PosVelFusion.cpp`, the Kalman gain for state index 15 (Z-axis accel bias) is set to zero when conditions make it unobservable:

```cpp
const bool gndEffectActive = dal.get_takeoff_expected() || dal.get_touchdown_expected();
// ...
const bool zAxisInhibit = (i == 15) && gndEffectActive;
if (!dvelBiasAxisInhibit[i-13] && !zAxisInhibit) {
    Kfusion[i] = P[i][stateIndex]*SK;
} else {
    Kfusion[i] = 0.0f;
}
```

State indices: 13=X accel bias, 14=Y accel bias, 15=Z accel bias (inhibited during ground effect).

### Stationary Zero Velocity Fusion

When on ground and disarmed (`onGround && !motorsArmed`), the EKF fuses synthetic zero velocity to make bias observable. This works in all aiding modes (AID_NONE, AID_RELATIVE, AID_ABSOLUTE). Key member: `fusingStationaryZeroVel`.

This is critical for optical flow configurations where `PV_AidingMode == AID_RELATIVE` but no velocity data is available when stationary.

### When Z-Bias Learning is Inhibited

| Scenario | Z-bias Learning | Reason |
|----------|-----------------|--------|
| Stationary on ground, disarmed | **Enabled** via zero velocity fusion | Bias IS observable |
| Armed on ground (motors spinning) | **Inhibited** | Ground effect flag prevents learning motor thrust offset |
| Takeoff (below GNDEFF_ALT) | **Inhibited** | Ground effect flag |
| Hover (above GNDEFF_ALT) | **Enabled** | Weakly observable from baro |
| Flying with GPS Z velocity | **Enabled** | Strongly observable |
| Flying with optical flow only | **Enabled** | Weakly observable from baro |
| Landing (slow descent) | **Inhibited** | Ground effect flag |

### Important: `dvelBiasAxisInhibit` vs Ground Effect Inhibition

The existing `dvelBiasAxisInhibit` mechanism (`AP_NavEKF3_core.cpp`) only handles **geometric** observability — once airborne, all axes are considered observable. It does NOT account for **measurement** observability (whether we have sensors that can observe the bias). The ground effect inhibition handles the measurement case.

## Hover Z-Bias Learning (Vibration Rectification Compensation)

**Branch-specific** (see the note at the top of the previous section): none of the symbols, parameters or files listed here exist on upstream master.

### What It Does

Captures the EKF's learned accel Z-bias during stable hover and saves it for subsequent flights. Compensates for **vibration rectification** — a DC offset in AccZ caused by motor vibration that only exists when motors are running.

### How It Works — Frozen Correction Approach

The system uses a "frozen correction" to avoid feedback instability:

1. **At boot**: INS parameter values loaded into Copter's `_hover_bias_learning[]`; frozen into EKF's `_accelBiasHoverZ_correction[imu]` once EKF3 is active (deferred via `one_hz_loop()`)
2. **When armed**: Each EKF core applies its IMU's frozen correction at the IMU level in `correctDeltaVelocity()`
3. **During hover**: Copter's `update_hover_bias_learning()` captures TOTAL bias = EKF_residual + frozen_correction per IMU with 2s time constant filter
4. **On disarm**: Copter's `save_hover_bias_learning()` saves total bias per IMU to INS parameters

Key properties:
- **EKF reset immunity**: IMU-level correction is applied before EKF processing
- **Feedback stability**: The frozen value doesn't change during flight
- If the frozen correction perfectly matches vibration rectification, the EKF residual will be ~0

```cpp
// Frozen correction applied at IMU level (in correctDeltaVelocity)
if (motorsArmed) {
    delVel.z -= frontend->_accelBiasHoverZ_correction[accel_index] * delVelDT;
}

// Learning captures TOTAL bias per IMU (in Copter::update_hover_bias_learning)
for (uint8_t imu = 0; imu < INS_MAX_INSTANCES; imu++) {
    float currentBiasZ;
    if (!ahrs.get_accel_bias_z_for_imu(imu, currentBiasZ)) continue;
    const float frozenCorrection = ahrs.get_hover_z_bias_correction(imu);
    const float totalBias = currentBiasZ + frozenCorrection;
    _hover_bias_learning[imu] += alpha * (totalBias - _hover_bias_learning[imu]);
    AP::ins().set_accel_vrf_bias_z(imu, _hover_bias_learning[imu]);
}
```

### Boot Loading (Deferred Initialization)

EKF3 is not active when `startup_INS_ground()` runs, so initialization is split:

1. `Copter::init_hover_bias_correction()` — loads INS params into `_hover_bias_learning[]` (called from `startup_INS_ground()`)
2. `Copter::set_hover_z_bias_correction()` — sets frozen correction in EKF via `ahrs.set_hover_z_bias_correction()` (called from `one_hz_loop()` while disarmed, keeps trying until values match)

The AHRS and EKF3 setter functions return `bool` for success/failure. The caller compares saved vs current values with `is_equal()` to stop retrying.

### Parameters

| Parameter | Description |
|-----------|-------------|
| `INS_ACC_VRFB_Z` | Learned hover Z-axis accel bias for IMU0 (m/s^2) |
| `INS_ACC2_VRFB_Z` | Learned hover Z-axis accel bias for IMU1 (m/s^2) |
| `INS_ACC3_VRFB_Z` | Learned hover Z-axis accel bias for IMU2 (m/s^2) |
| `ACC_ZBIAS_LEARN` | Learning mode: 0=Disabled, 1=Learn, 2=Learn+Save (Copter parameter) |
| `GNDEFF_ALT` | Altitude threshold for ground effect (controls when learning is allowed) |

Safety: frozen correction clamped to +/-0.3 m/s^2. If `ACC_ZBIAS_LEARN=0`, correction is set to 0.

### Key Files

**ArduCopter (learning lifecycle):**
- `ArduCopter/Attitude.cpp` — `init_hover_bias_correction()`, `set_hover_z_bias_correction()`, `update_hover_bias_learning()`, `save_hover_bias_learning()`
- `ArduCopter/Copter.h` — `_hover_bias_learning[INS_MAX_INSTANCES]` array and method declarations
- `ArduCopter/Copter.cpp` — Calls `set_hover_z_bias_correction()` from `one_hz_loop()` while disarmed
- `ArduCopter/system.cpp` — Calls `init_hover_bias_correction()` from `startup_INS_ground()`
- `ArduCopter/AP_Arming.cpp` — Calls `save_hover_bias_learning()` on disarm

**AP_AHRS (abstraction layer):**
- `AP_AHRS.h/cpp` — `get_hover_z_bias_correction()`, `set_hover_z_bias_correction()` (returns bool), `get_accel_bias_z_for_imu()` — delegates to EKF3, returns safe defaults if not available

**AP_NavEKF3 (frozen correction storage and application):**
- `AP_NavEKF3.cpp` — `InitialiseFilter()` freezes correction per IMU; `getHoverZBiasCorrection()`, `setHoverZBiasCorrection()` (returns bool)
- `AP_NavEKF3_core.cpp` — `correctDeltaVelocity()` applies per-IMU frozen correction when armed
- `AP_NavEKF3.h` — `_accelBiasHoverZ_correction[INS_MAX_INSTANCES]` array

**AP_InertialSensor (parameter storage):**
- `AP_InertialSensor.cpp` — Parameter definitions: `INS_ACC_VRFB_Z`, `INS_ACC2_VRFB_Z`, etc.
- `AP_InertialSensor.h` — `_accel_vrf_bias_z[INS_MAX_INSTANCES]` array and accessors

## Gyro Bias Observability Without a Yaw Reference

State 12 (Z gyro bias) is only observable through something that observes heading. Optical flow gives body-frame velocity, so with flow as the only horizontal aiding source and no usable yaw reference, a flow-velocity error (scale, misalignment) can be reconciled either by rotating yaw or by moving the Z gyro bias, and the filter does some of each. The phantom bias then integrates into a continuous yaw drift that walks the dead-reckoned position.

### "No usable yaw reference" is a question about fusion, not configuration

`yaw_source_last` is the parameter setting (`EK3_SRC*_YAW`, remapped only for compass calibration). A test on it says what the user asked for, not what the filter is getting. `checkGyroCalStatus()` and `SelectMagFusion()` share this predicate for "no yaw sensor of any type":

```cpp
// AP_NavEKF3_Control.cpp checkGyroCalStatus(), AP_NavEKF3_MagFusion.cpp SelectMagFusion()
!use_compass() &&
yaw_source_last != AP_NavEKF_Source::SourceYaw::GPS &&
yaw_source_last != AP_NavEKF_Source::SourceYaw::GPS_COMPASS_FALLBACK &&
yaw_source_last != AP_NavEKF_Source::SourceYaw::EXTNAV
```

It is availability-aware on exactly one leg. `use_compass()` is false for every yaw source other than COMPASS / GPS_COMPASS_FALLBACK, and for those two when `use_for_yaw()` is false or all mags have failed. The GPS and EXTNAV legs are bare enum compares. With GPS yaw configured, aligned on the ground and then lost in flight, the GPS branch of `SelectMagFusion()` fuses nothing and returns with no fallback, yet the predicate still reports a yaw reference. Same for external nav yaw. This is the yaw-source instance of the accel-bias rule above: GPS configured but unavailable, so check actual data availability, not just configuration.

The fusion-freshness signals are members, and the review of PR #33498 missed them because this file said "reuse the predicate":

| Source | Yaw is being fused if |
|--------|-----------------------|
| GPS, GPS_COMPASS_FALLBACK | `recentGpsYawFusion()`: `last_gps_yaw_fuse_ms != 0 && imuSampleTime_ms - last_gps_yaw_fuse_ms < 5000`. Only a successful `fuseEulerYaw(GPS)` or `alignYawAngle()` refreshes it; a geometrically rejected measurement does not |
| COMPASS | `use_compass() && !magTimeout`. `magTimeout` is set once the compass has failed its innovation checks for `magFailTimeLimit_ms` (10 s) and cleared by the next healthy fusion; `use_compass()` alone only drops when every mag has failed |
| GPS_COMPASS_FALLBACK after GPS yaw loss | `gps_yaw_mag_fallback_active && use_compass() && !magTimeout`. The fallback engages 10 s after loss, in flight only, and only if the compass agreed with GPS yaw while it was fused |
| EXTNAV | `last_extnav_yaw_fuse_ms != 0 && imuSampleTime_ms - last_extnav_yaw_fuse_ms < 5000`. Not `last_extnav_yaw_fusion_ms`, despite the name: that one is refreshed whenever a sample arrives, including one the innovation gate rejects, and feeds `using_extnav_for_yaw()` |
| NONE, GSF | never. GSF fuses yaw only once GPS velocity has converged it, and then GPS velocity observes state 12 through `FuseVelPosNED` anyway |

`flowYawGyroBiasInhibited()` (PR #33498) is built from these. `using_noncompass_for_yaw()` is not usable for the purpose: the synthetic PREDICTED / STATIC fusion refreshes `lastSynthYawTime_ms`, so it returns true with no yaw source at all.

When a mask has to err, err towards inhibiting. Any real yaw fusion learns state 12 through its own unmasked gains, so masking the flow contribution while a reference exists costs a little convergence speed; leaving it unmasked with no reference is the phantom-bias failure the mask exists for.

### What still learns state 12 in that configuration

- On the ground and not moving, `SelectMagFusion()` fuses a STATIC synthetic yaw (`fuseEulerYaw(yawFusionMethod::STATIC)`, unmasked gains), which legitimately calibrates the Z bias because the true heading is constant. This is why the bias can be "frozen at its ground-learned value" in flight.
- In flight, PREDICTED zero-innovation yaw fusion runs only when on ground, in AID_NONE, or when the attitude variance sum exceeds 0.01; it bounds P[12][12] without moving the state.
- Zero-velocity fusion, baro and rangefinder do not observe it (their H has no heading component for a level, stationary vehicle).
- `FuseVelPosNED` already masks the Kalman gain of a gyro bias axis within 45 deg of vertical when `PV_AidingMode == AID_NONE` (the `poorObservability` block in `AP_NavEKF3_PosVelFusion.cpp`). That K-only mask is the precedent for masking state 12 in `FuseOptFlow` (PR #33498, `flowYawGyroBiasInhibited()`).

### K-only mask vs full inhibition

A K-only mask (zero `Kfusion[12]`) leaves P[12][12] and its cross-covariances alive. `FinishFusion()` averages `P - KHP` with its transpose, so the masked state's cross-covariances are reduced by half the full amount; this is second order and is how the existing AID_NONE mask already behaves. It is not the wind-truth case of commit e004e792ff, where a variance forced to zero with live cross-covariances lost positive-definiteness. Full inhibition in the style of `dvelBiasAxisInhibit` (zero row and column in `CovariancePrediction`, restore the diagonal) would be wrong here because the on-ground STATIC yaw fusion must still be able to learn the state.

Process noise on state 12 is negligible: with `EK3_GBIAS_P_NSE` at its 1e-3 default and dt 12 ms the variance grows about 1.7e-12 per second against an initial 2.7e-7 (2.5 deg/s IMU default) and a cap of 4.4e-6, so an unobserved bias state does not run its variance up within a flight.

### checkGyroCalStatus and tilt

`checkGyroCalStatus()` gates `readyToUseOptFlow()` through `delAngBiasLearned`. In the no-yaw-reference branch it rotates the vector of the three bias variances by `prevTnb` and tests only the horizontal components, but rotating variances as a vector leaks P[12][12] into the horizontal terms at first order in tilt (`Tnb.a.z = -sin(pitch)`), not the second order a proper R P R^T would give. Against a threshold of `sq(radians(0.15 * dtEkfAvg))` this only passes because the STATIC yaw fusion has already shrunk P[12][12] on the ground; if something stops that learning, flow aiding will refuse to engage on any vehicle more than about a degree off level.

### Measured effect (SITL, PR #33498)

Flow-only Loiter box pattern, no yaw source, 20 percent flow scale error, four laps: the merge-base learns a 0.34 deg/s phantom Z bias from a bias-free simulated gyro and the branch holds zero; with a real 1 deg/s gyro bias and `INS_GYR_CAL=0` the merge-base overshoots to 1.38 deg/s and the branch holds the 0.93 deg/s learned on the ground. Yaw drift at 240 s fell from 57 to 39 deg and 68 to 46 deg. The remaining drift is the direct yaw correction from the flow innovation and is inherent to having no yaw reference; the phantom bias is roughly a third of the drift, not all of it, so do not describe the mask as curing yaw drift.

GPS yaw configured (moving baseline, `copter-gps-for-yaw.parm`), aligned on the ground, both receivers dropped 5 s after takeoff, then eight flow-only laps with the same flow scale error: the merge-base and the config-only guard of the PR's first head (629b5959e9) both learn a 0.55 to 0.66 deg/s phantom Z bias and yaw drifts through 150 deg by 420 s, at which point Loiter can no longer hold position and one run failed to land; the fusion-aware guard holds the bias at 0.01 deg/s and the drift at 40 deg. Dropping GPS after a full lap instead barely moves the bias on any arm (0.06 deg/s at 240 s): the extra 50 s of GPS yaw fusion collapses P[12][12] to 6e-11, 400 times below its takeoff value with no yaw source, and the flow gain into state 12 scales with it. A provocation for this mask has to remove the yaw reference while the bias variance is still large, or it measures nothing.

## Vibration Rectification

A known phenomenon in MEMS accelerometers where high-frequency vibration causes the **mean** reading to shift due to nonlinear spring stiffness, sensor asymmetries, and anti-aliasing filter effects. The shift is consistent (always less negative AccZ with more vibration).

**Typical magnitude:** +0.08-0.15 m/s^2 shift in AccZ between motors-off and hover. This is ~1% of gravity.

**Impact without velocity sensor:** The EKF interprets the shift as real acceleration. Without velocity measurements to correct it, velocity integrates at ~0.1 m/s per second, causing altitude drift.

**The hover Z-bias learning system compensates for this** by learning the total bias during hover and applying it as a frozen correction on subsequent flights. With the correction applied, the EKF residual converges to near-zero.

## Indoor No-GPS Flight Limitations

Without Z velocity measurements, the EKF has fundamental limitations:

1. **Velocity drift**: EKF integrates IMU for velocity, which drifts without external correction. Baro provides position-only corrections with weak velocity observability.
2. **Accel bias poorly observable**: `EK3_ABIAS_P_NSE` has no effect without velocity data — bias states need velocity corrections to converge.
3. **Vibration rectification**: Motor vibration causes AccZ DC offset not present on ground. Without velocity sensor, can't be fully compensated in real-time.
4. **Temperature effects**: IMU cooling from prop airflow causes residual bias drift even with TCAL enabled.

**Source configuration note:** Setting `EK3_SRC1_VELZ` from GPS to None has no effect if GPS isn't providing data — the EKF already handles missing sensors. Timeout flags (XKF4.TS bit 1) are informational only.

**Recommended solutions:**
1. Add velocity sensor (optical flow, rangefinder-derived velocity)
2. Use STABILIZE mode for indoor flight (direct throttle, no altitude hold)
3. Keep hovers short to minimize drift accumulation

## GPS Innovation Handling at High Dynamics (EK3_GLITCH_RAD)

`EK3_GLITCH_RAD` is not a monotonic "aggressiveness of GPS glitch rejection" setting. It selects between two fundamentally different code paths in `AP_NavEKF3_PosVelFusion.cpp`. Understanding which path fits a specific vehicle's operational envelope matters — the wrong path can create flyaways on high-speed platforms.

### The Two Paths

**Path 1 — `EK3_GLITCH_RAD > 0` (default 25 m)**

Standard behaviour. Innovation tests compare the difference between EKF-predicted position and incoming GPS position against a variance-scaled threshold. On a failed innovation test:

- If position covariance has grown beyond `sq(_gpsGlitchRadiusMax)`, the EKF triggers `ResetPosition()` to the GPS fix and resets position variances (see `AP_NavEKF3_PosVelFusion.cpp:837-850`)
- Otherwise, the sample is rejected (`fusePosData = false`) and the EKF continues on IMU propagation until a later sample passes

This is appropriate for **hover-class and slow-cruise copters**: any 25 m innovation is almost certainly a bad GPS fix, and snapping the state to the GPS is the right recovery.

**Path 2 — `EK3_GLITCH_RAD <= 0` (special case)**

A distinct branch in the same code (at `AP_NavEKF3_PosVelFusion.cpp:819-829`, with matching branches at `:894-905` for velocity and `:942-951` for height):

```cpp
} else if ((frontend->_gpsGlitchRadiusMax <= 0) && (PV_AidingMode != AID_NONE)) {
    // Handle the special case where the glitch radius parameter has been set to a non-positive number.
    // The innovation variance is increased to limit the state update to an amount corresponding
    // to a test ratio of 1.
    posCheckPassed = true;
    varInnovVelPos[3] *= posTestRatio;
    varInnovVelPos[4] *= posTestRatio;
}
```

When the innovation test fails, the sample is **not** rejected and **not** used for a position reset. Instead, the innovation variance is multiplied by the failed test ratio, which bounds the Kalman update to what a test ratio of 1.0 would have produced. The state gradually converges toward GPS over multiple samples rather than snapping.

### Which Path Fits Which Vehicle

- **Hover-class, slow-cruise, or static-position multirotors:** use the default `25` (or larger for rough-GPS environments). Glitch rejection protects against real bad fixes.
- **High-speed vehicles with sustained flight at 30-50+ m/s or aggressive acro:** use `0`. GPS processing latency of ~100 ms is already 5 m of apparent position error at 50 m/s and 10 m at 100 m/s. These are *legitimate* innovations, not glitches. Combined with covariance growth from the high dynamics, Path 1's `ResetPosition()` at the covariance threshold would snap the EKF state to where the (lagged) GPS *thinks* the vehicle is, several metres behind the IMU-propagated state. On a vehicle moving at 100 m/s, that position snap is a flyaway — the controller then drives toward the next waypoint from the wrong start point.

Path 2 keeps the IMU-propagated position, applies a bounded correction toward the GPS, and lets the filter converge naturally as later GPS samples arrive. This is the correct behaviour when IMU propagation is more accurate than the current GPS sample, which is typical at high dynamics.

### Log Diagnostics

`STATUSTEXT` / `MSG` string `"GPS Glitch or Compass error"` during high-speed flight is the innovation test firing. **This message alone does not indicate the EKF accepted a bad fix.** It indicates the innovation test flagged a sample that exceeded the variance-scaled threshold. What happens next depends on `EK3_GLITCH_RAD`:

- With `GLITCH_RAD > 0`: the message is often followed by `EKF lane switch` and state discontinuities from `ResetPosition()` — these **are** a symptom, and in a high-speed context they are the wrong response to a legitimate large innovation.
- With `GLITCH_RAD <= 0`: the message still appears (the innovation test still flags) but the special path handles the sample via bounded variance scaling. No reset, no lane switch consequence.

### Do Not Recommend "Restore Default"

On any vehicle where sustained cruise regularly puts the airframe into a flight regime where GPS processing lag creates metres-scale apparent position error against IMU propagation, **the default `25` is the wrong value**. Seeing `"GPS Glitch"` messages in such a log is not evidence that glitch rejection is needed — it is evidence that the innovation test is doing what it should, and the question is whether you want the reset-to-GPS or bounded-variance path to handle the update. For high-speed platforms, bounded-variance (`<= 0`) is the right answer.

## Flight-State Flags: onGround, inFlight, takeOffDetected

`detectFlight()` in `AP_NavEKF3_VehicleStatus.cpp` has two branches. Fly-forward vehicles infer ground state from ground speed, height change and airspeed. Everything else gets this:

```cpp
// Non fly forward vehicle, so can only use height and motor arm status
if (motorsArmed) {
    onGround = false;
} else {
    inFlight = false;
    onGround = true;
}
```

On a copter `onGround` is `!motorsArmed` and nothing more. One EKF cycle after a mid-air disarm the filter reports on-ground, so a guard of the form `if (!onGround) return` gives no in-flight protection to anything that runs at re-arm. Copter's own `ap.land_complete` is no substitute: `AP_Arming_Copter::disarm()` forces it true and the land detector holds it true while disarmed. Only the vehicle knows it was flying, so code that must not run in flight after a disarm needs the vehicle to record that at disarm time. PR #32768 adds `ap.disarmed_in_air` for the arm-time height datum reset (branch-specific until it merges; `resetHeightDatum()` zeroes `velocity.z`, and a re-arm while falling at 15.6 m/s reported 0.4 m/s one sample later).

### `inFlight` is not a portable airborne test

The fly-forward branch of `detectFlight()` sets `inFlight` only when GPS ground speed exceeds 5 m/s (plus the reported speed accuracy) and one of `takeoff_expected`, airspeed over 10 m/s, or 10 m of height change:

```cpp
if (motorsArmed) {
    onGround = false;
    if (highGndSpd && (dal.get_takeoff_expected() || highAirSpd || largeHgtChange)) {
        inFlight = true;
    }
}
```

`highGndSpd` is computed from `gpsDataNew.vel`, so on a GPS-denied or GPS-jammed plane `inFlight` never becomes true for the whole flight. The height-change, rangefinder and `get_time_flying_ms() > 5000` sources that make `inFlight` dependable belong to the non fly-forward branch only. A Copter-only autotest cannot see the difference - both flags behave on Copter, and the code still ships broken on Plane.

Once set it latches until disarm, and `inFlight` implies `!onGround` (the two are never both true), so `!onGround` is always the weaker and more permissive of the pair.

### `takeOffDetected` is optical flow state, not a flight-state flag

`takeOffDetected` is written in exactly one function, `detectOptFlowTakeoff()`, which is called from exactly one place, `writeOptFlowMeas()`:

```cpp
// by definition if this function is called, then flow measurements have been provided so we
// need to run the optical flow takeoff detection
detectOptFlowTakeoff();
```

No flow sensor means no call, so the flag holds its initialised false for the whole flight, and it is compiled out entirely under `#if !EK3_FEATURE_OPTFLOW_FUSION`. A condition of the form `takeOffDetected && <something>` is therefore dead on every vehicle without optical flow, and whatever the `<something>` selects between becomes unreachable with it. Its declared meaning is "takeoff for optical flow navigation has been detected", not "airborne".

### Which flag to use for an observability gate

For "is this bias observable now", follow what `CovariancePrediction()` already does for the delta velocity bias axes:

```cpp
const bool is_bias_observable = (fabsF(prevTnb[index][2]) > 0.8f && onGroundNotMoving) || !onGround;
```

`onGroundNotMoving` for the stationary case, `!onGround` for the airborne case. `!onGround` is only armed-state on Copter, but it is the one term that means the same thing on every vehicle, and reusing the established idiom keeps a new gate consistent with the axis inhibit running next to it.

Measured (SITL, #32473): a Z accel-bias gate written as `onGroundNotMoving || (takeOffDetected && heightRefGood)` collapsed to `onGroundNotMoving` on a baro/GPS copter, and the bias learned 0.000097 against a 0.15 injected offset. With `!onGround` it learned 0.178. The subtest that learns on the ground before takeoff passed in both cases, so only a subtest that inhibits ground learning exercises the air path at all.

Review rule: before crediting an `onGround`, `inFlight`, `takeOffDetected` or `land_complete` test as protection, read how that flag is set for the vehicle type the code runs on, and check it can be set at all with the sensors that vehicle has. A gate that reads as a clean observability test can quietly reduce to a constant.

## Known Issues

### Motor-Induced Baro Noise

On small drones, motor operation can cause severe baro pressure noise (3-10x worse than motors-off). This is NOT a broken sensor — it's motor-induced pressure effects at the baro static port (prop wash, acoustic resonance, airframe vibration).

**Diagnosis:** Compare baro std dev with motors on vs off. If motors-on noise is significantly higher, this is the issue.

**Mitigations:**
1. **Hardware:** Relocate baro away from prop wash, add foam isolation
2. **BARO_FLTR_RNG:** Enable baro filtering
3. **GNDEFF_ALT:** Increase threshold to keep ground effect protection longer
4. **GNDEFF_TMO:** Require time delay before ground effect clears

### Baro Thrust Compensation (BARO1_THST_SCALE)

`BARO1_THST_SCALE` subtracts a thrust-proportional pressure offset: `correction = mot_scale * throttle`

**Key insight:** Ground effect protection ignores baro during takeoff transient, so BARO_THST_SCALE only needs to work during stable flight where the thrust-pressure relationship is linear.

**How to calculate:**
1. Fly to stable hover with rangefinder (or known altitude reference)
2. Record: hover throttle, baro altitude, true altitude (RFND or known)
3. Calculate error: `error_m = baro_alt - true_alt`
4. Calculate scale: `BARO1_THST_SCALE = -(error_m × 12) / throttle` (Pa)

**Example:** Baro shows +7m, rangefinder shows +2m, throttle=0.39
```
error = 7 - 2 = +5m
BARO1_THST_SCALE = -(5 × 12) / 0.39 = -154 Pa
```

**Properties:**
- Works well during stable flight (thrust-pressure is approximately linear)
- Does NOT help during takeoff/landing (chaotic airflow, protected by ground effect anyway)
- Vehicle-specific — depends on prop size, baro location, airframe geometry
- Negative values correct for propwash-induced low pressure (most common)

**Alternative approach:** Use rangefinder for height fusion instead:
- `EK3_RNG_USE_HGT = 70` (use rangefinder below 70% of max range)
- `GNDEFF_TMO = 3` (keep ground effect active during takeoff transient)
- EKF will trust rangefinder over corrupted baro, converging to correct altitude

### Baro Thrust Filter (BARO1_THST_FILT)

`BARO1_THST_FILT` applies a low-pass filter to the throttle input before computing thrust compensation.

**Problem it solves:** During rapid throttle changes (takeoff, aggressive maneuvers), the instantaneous thrust compensation can cause step changes in corrected baro altitude. This creates altitude transients that can cause controller instability, especially indoors near surfaces.

**Parameters:**
```
BARO1_THST_FILT = 1.0   # Default: 1Hz cutoff
BARO1_THST_FILT = 0.5   # More filtering, more lag
BARO1_THST_FILT = 0     # Disable filter (original behavior)
```

**Trade-off:** More filtering = smoother altitude during throttle transients, but slower response to legitimate altitude changes. For indoor flight where stability matters more than responsiveness, use 0.5-1.0 Hz.

### Ground Effect Flags Clearing Prematurely

The ground effect threshold check uses EKF altitude. If baro noise corrupts EKF altitude, it can falsely cross the threshold, disabling protection too early. This creates a feedback loop: bad baro → wrong altitude → ground effect clears → EKF trusts bad baro.

**Solution:** Use `GNDEFF_TMO` to require BOTH time delay AND altitude threshold.

### Frozen Correction + Ground Effect Conflict

The hover Z-bias frozen correction applies at arm, but ground effect inhibits Z-bias learning. If correction is wrong for ground conditions, the EKF cannot compensate.

**Proposed fix:** Gate frozen correction on ground effect state in `correctDeltaVelocity()`.

### EK3_RNG_USE_HGT Feedback Loop (BUG)

**Problem:** The rangefinder height switch threshold uses EKF-estimated altitude, creating a feedback loop where bad baro can lock out the rangefinder.

**Code location:** `AP_NavEKF3_PosVelFusion.cpp:1283-1320`, function `selectHeightForFusion()`

**The threshold check (lines 1285-1287):**
```cpp
ftype rangeMaxUse = 1e-4 * _rng->max_distance_cm_orient(...) * frontend->_useRngSwHgt;
bool aboveUpperSwHgt = (terrainState - stateStruct.position.z) > rangeMaxUse;
bool belowLowerSwHgt = ((terrainState - stateStruct.position.z) < 0.7f * rangeMaxUse)
                       && (imuSampleTime_ms - gndHgtValidTime_ms < 1000);
```

**The feedback loop:**
1. Bad baro → EKF altitude corrupted (e.g., thinks 7m when actually 2m)
2. `(terrainState - stateStruct.position.z)` = EKF-estimated height = 7m
3. If `rangeMaxUse = 4.9m` (70% of 7m max range): `aboveUpperSwHgt = true`
4. Rangefinder gets disabled (line 1310)
5. Without rangefinder, EKF only has bad baro → can't correct
6. **Stuck in wrong state permanently!**

**Additional gate makes it worse:** The `belowLowerSwHgt` check requires `(imuSampleTime_ms - gndHgtValidTime_ms < 1000)`. `gndHgtValidTime_ms` is only updated when rangefinder fusion succeeds (line 157 in OptFlowFusion.cpp). Once rangefinder is disabled for >1 second, this gate fails, making re-enabling even harder.

**Real-world scenario (from logtd1.bin analysis):**
- Vehicle at 2m actual altitude (per rangefinder)
- Bad baro shows 7m due to propwash
- EKF trusts baro, thinks it's at 7m
- EK3_RNG_USE_HGT=70 with 7m max range → threshold is 4.9m
- 7m > 4.9m → rangefinder disabled
- Rangefinder that could provide correct altitude is locked out!

**Implemented fix (AP_NavEKF3_PosVelFusion.cpp:~1285 and ~1321):**

The fix has two parts:

**Part 1 (~line 1285):** Force rangefinder as height source during ground effect when:
1. Ground effect is active (`takeoff_expected` or `touchdown_expected`)
2. Current height source is BARO (not already rangefinder or GPS)
3. Raw rangefinder reading is within usable range

```cpp
// During ground effect with baro as height source, use raw rangefinder reading for threshold check
// to prevent bad baro from corrupting EKF altitude and locking out the rangefinder
const bool gndEffectActive = dal.get_takeoff_expected() || dal.get_touchdown_expected();
if (gndEffectActive &&
    activeHgtSource == AP_NavEKF_Source::SourceZ::BARO &&
    rangeDataDelayed.rng < rangeMaxUse)
{
    activeHgtSource = AP_NavEKF_Source::SourceZ::RANGEFINDER;
}
```

**Part 2 (~line 1321):** Prevent switch-back during ground effect:

The existing code at line 1321 switches from rangefinder back to baro when `aboveUpperSwHgt || dontTrustTerrain`. But `aboveUpperSwHgt` uses the corrupted EKF altitude, which would immediately undo Part 1. Fix: add `&& !gndEffectActive` to prevent switching back during ground effect:

```cpp
if ((aboveUpperSwHgt || dontTrustTerrain) && (activeHgtSource == AP_NavEKF_Source::SourceZ::RANGEFINDER) && !gndEffectActive) {
    // cannot trust terrain or range finder so stop using range finder height
    // Note: don't switch back during ground effect - the aboveUpperSwHgt check uses EKF altitude which may be corrupted
```

**Why conditional on BARO source:** If already using rangefinder, no need to force. If using GPS, don't override user's configuration choice. Only when baro is the current source do we need this protection.

**Why use raw rangefinder reading:** `rangeDataDelayed.rng` is the actual sensor measurement, immune to EKF altitude corruption. This breaks the feedback loop — even if baro corrupts EKF altitude during ground effect, the rangefinder enables itself based on what it actually measures.

**When ground effect ends:** Once `gndEffectActive` becomes false, the normal switching logic resumes. The EKF altitude should have recovered by then (thanks to rangefinder fusion during ground effect), so the threshold checks work correctly again.

### Indoor Flight Considerations

**Rangefinder is critical for indoor flight** — baro alone is unreliable due to propwash and surface reflections.

**Pre-flight checks:**
- Verify rangefinder returns valid data (`Stat=4`), not `Stat=1` (NoData) or `Stat=2` (OutOfRangeLow)
- BARO1_THST_FILT can reduce transient issues but doesn't solve fundamental baro unreliability
- Consider `EK3_SRC1_POSZ=2` (rangefinder primary) for indoor flights

**Recommended indoor settings:**
```
EK3_RNG_USE_HGT = -1          # Disable rangefinder height switching (avoids feedback loop)
BARO1_THST_SCALE = -147       # Calibrated thrust compensation (vehicle-specific)
BARO1_THST_FILT = 1.0         # Filter throttle transients
INS_ACC_VRFB_Z = 0            # Reset if previously corrupted
GNDEFF_ALT = 5          # Keep ground effect protection to 5m
```

### Post-Landing EKF Divergence

After landing with ground effect, the EKF accumulates position/velocity errors that cause drift after disarm:

1. Ground effect protection correctly prevents EKF from chasing bad baro during landing
2. But this accumulates an error (EKF position diverges from baro by ~2m)
3. At disarm, protection removed — EKF sees huge innovation
4. Zero velocity fusion IS happening, but large height innovation corrupts velocity state

**Potential solutions:**
- Gradual innovation limit release after touchdown_detected clears
- Position reset on landing
- Stronger zero velocity fusion when stationary
- Extended ground effect protection after landing

**Key code:** `AP_NavEKF3_VehicleStatus.cpp` (onGround detection), `AP_NavEKF3_PosVelFusion.cpp` (zero velocity fusion, innovation flooring), `libraries/AP_GroundEffect/AP_GroundEffect.cpp` (flag control)

## Magnetometer Fusion Mode Selection (EK3_MAG_CAL)

### Two Models, Very Different Observability

`magFusionSel` (logged as `XKFS.MAG_FUSION`) picks between:

| Mode | Name | States estimated |
|------|------|------------------|
| 0 | not fusing | — |
| 1 | simple heading fusion | yaw only, taken directly from the compass |
| 2 | 3-axis fusion | yaw **plus** 3-axis earth field (`XKF2.MN/ME/MD`) **plus** 3-axis body-field bias (`XKF2.MX/MY/MZ`) |

Mode 2 is the more capable model and the more dangerous one. Yaw and body-field bias are **not independently observable without motion**: rotating the yaw estimate and rotating the learned body bias by the compensating amount produce identical predicted measurements. On a stationary or non-manoeuvring vehicle the filter has no information to split them, so the yaw state wanders freely along that null direction while the bias state absorbs the difference. The residual then lands in the gyro bias states, giving a `XKF1.GZ` that the hardware does not have.

### The On-Ground Guard, and What Removes It

`NavEKF3_core::setAidingMode()` in `AP_NavEKF3_Control.cpp` (~lines 115-128) builds `magCalRequested` and `magCalDenied`. The denial line is the important one:

```cpp
bool magCalDenied = !use_compass() || (effectiveMagCal == MagCal::NEVER) ||
    (onGround && effectiveMagCal != MagCal::ALWAYS && effectiveMagCal != MagCal::GROUND_AND_INFLIGHT);
```

Every `EK3_MAG_CAL` value blocks field-state learning on the ground **except**:

- `4` (`ALWAYS`) — upstream ArduPilot
- `7` (`GROUND_AND_INFLIGHT`) — SmallFastDrone-fork only, added so a battery's magnetic signature can be learned before takeoff

With either, mode 2 runs while disarmed and motionless, and the degeneracy above has free rein. Measured on a MatekH743 octaquad with `EK3_MAG_CAL=7`: 73° of yaw error and a 239 mGauss learned body bias (roughly half the Earth field) accumulated over 35 s on the ground, with the raw compass flat at 530 mGauss and the gyro registering std 0.001 rad/s. The vehicle took off already 73° wrong.

`3` (`AFTER_FIRST_CLIMB`, the copter default) is the safe choice: simple heading fusion on the ground pins yaw to the compass, and mode 2 only starts once the first in-air yaw and field reset has given the filter enough motion to separate the states.

### EK3_MAG_MASK Cannot Mask Core 0

`NavEKF3_core::effective_magCal()` (`AP_NavEKF3_Control.cpp:45`) tests:

```cpp
if (frontend->_magMask & core_index) {
    return MagCal::NEVER;
}
```

That is `& core_index`, not `& (1 << core_index)`. Core 0 has `core_index == 0`, so the test is always false and **core 0 can never be forced to simple heading fusion**. Do not recommend `EK3_MAG_MASK` as a way to make the primary lane use heading-only fusion; change `EK3_MAG_CAL` instead.

### Diagnosing It From a Log

The tell is `XKF2.MX/MY/MZ` magnitude growing to a large fraction of the measured `MAG` field magnitude while the measured field itself is steady — the filter is explaining a rotation as a bias. Cross-check yaw against two compass-independent references (a tilt-compensated heading recomputed from `MAG` + `ATT`, and `XKY0.YC` from the GSF) before concluding anything about the compass. Full workflow in the `/log-analyze` skill under "EKF3 Yaw inconsistent N deg".

## Lane Switching

### How It Works

EKF3 runs one core per IMU (controlled by `EK3_IMU_MASK`). When armed, each core computes an `errorScore()` based on sensor innovation ratios (`AP_NavEKF3_Outputs.cpp:62`). The primary core switches to an alternative if:
- Primary error score > 1.0, OR
- Primary is unhealthy, OR
- Alternative has a substantially lower accumulated relative error

Decision logic is in `NavEKF3::UpdateFilter()` (`AP_NavEKF3.cpp:932-998`). On stock ArduPilot there is no parameter to disable lane switching — it always runs when armed.

**Fork exception:** SmallFastDrone adds `EK3_OPTIONS` bit 1 (`Option::ManualLaneSwitch`), checked in `NavEKF3::UpdateFilter()` and `NavEKF3::checkLaneSwitch()`. When set, automatic lane switching **and the lane health checks** are both disabled; the primary only moves via `EK3_PRIMARY`. A core whose yaw or bias states have diverged will then be flown to the ground with nothing to escape to. Before blaming a diverged lane for a flight outcome, check whether this bit was set — and when reading `XKF4.PI` pinned at one value, do not read that as "no lane ever went unhealthy".

### Key Parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| `EK3_IMU_MASK` | 7 (3 IMUs) | Number of lanes. Use 3 (2 lanes) or 1 (1 lane) to reduce switching |
| `EK3_ERR_THRESH` | 0.2 | Relative error sensitivity. Higher = less sensitive to lane differences |
| `EK3_AFFINITY` | 0 | Bitmask: bit 0=GPS, bit 1=Baro, bit 2=Compass, bit 3=Airspeed. Pins sensor instances to lanes |
| `EK3_PRIMARY` | 0 | Preferred core when disarmed |

### GPS Affinity (EK3_AFFINITY bit 0)

When enabled, each core prefers the GPS instance matching its `core_index` (`AP_NavEKF3_Measurements.cpp:1153`):
- Core 0 → GPS1, Core 1 → GPS2, etc.
- Falls back to `gps.primary_sensor()` if preferred GPS has no 3D fix
- Each core reads exclusively from `gps.location(selected_gps)` — full data isolation between lanes

**Critical for GPS-jammed operations with external nav:** Pin the hardware GPS (jammed/spoofed) to one lane and the external nav to another. If the hardware GPS produces spoofed data, only its lane is corrupted. Lane switching moves to the clean external nav lane.

Recommended config for dual-GPS with one potentially unreliable:
```
EK3_AFFINITY = 1       # GPS affinity
EK3_IMU_MASK = 3       # 2 lanes (one per GPS)
GPS_PRIMARY = 1        # Reliable GPS as default fallback
```

### When Lane Switching Hurts

All lanes share the same GPS input by default (`EK3_AFFINITY=0`). If the GPS is spoofed, all lanes get corrupted simultaneously → rapid lane switching between equally bad solutions → each switch causes attitude/position discontinuities that compound flight controller instability.

**Mitigations:**
- `EK3_AFFINITY=1` with a clean GPS2 — isolates bad GPS to one lane
- `EK3_IMU_MASK=1` — single lane, no switching possible (loses IMU redundancy)
- `ARSPD_USE=1` — gives each lane a velocity cross-check to reject impossible GPS velocities

## AHRS DCM Fallback (Plane)

### How `_active_EKF_type()` Decides (AP_AHRS.cpp)

For Plane (FIXED_WING), the decision flow:

1. `ret = fallback_active_EKF_type()` → always returns DCM when DCM compiled in
2. `case THREE:` — sets `ret = THREE` only if `EKF3.healthy()` (Plane doesn't set `FLAG_ALWAYS_USE_EKF`)
3. Fixed-wing fallback section checks `can_use_ekf = attitude && vert_vel && vert_pos`:
   - `!can_use_ekf` → returns DCM ("No choice") — **bypasses DISABLE_DCM_FALLBACK**
   - `disable_dcm_fallback` check — only reached when `can_use_ekf` is true
   - Further checks: GPS fix loss, const_pos_mode, no horiz_vel → return DCM (gated by disable check)

### The DISABLE_DCM_FALLBACK Limitation

AHRS_OPTIONS bits 0+1 (`DISABLE_DCM_FALLBACK_FW` / `_VTOL`) prevent DCM fallback for the GPS fix loss, const_pos_mode, and no horiz_vel paths. But the `!can_use_ekf` path returns DCM **unconditionally**, bypassing the disable bits.

When the EKF loses attitude (e.g., from GPS spoofing corrupting the state covariance), this creates DCM↔EKF toggling that amplifies instability. Each toggle produces an attitude discontinuity for the flight controller.

### `EKF3.healthy()` vs `getFilterFaults()`

- `EKF3.healthy()` checks initialization, innovations, variances — returns false during GPS spoofing (high innovations)
- `getFilterFaults()` checks sensor-specific faults (bad mag, bad airspeed, etc.) — returns 0 during GPS spoofing (GPS corruption isn't a sensor fault)

This distinction matters because the `always_use_EKF()` path uses `ekf3_faults == 0` (keeps EKF), while the normal Plane path uses `EKF3.healthy()` (drops to DCM). Copter always uses the faults path; Plane only does if `FLAG_ALWAYS_USE_EKF` is set (which it isn't by default).

## GPS-Denied / GPS-Jammed Operations

### Airspeed as Velocity Cross-Check

`ARSPD_USE=1` fuses airspeed into the EKF velocity estimate. This provides the **only** independent velocity cross-check when GPS is unreliable. Without it, the EKF has no way to reject impossible GPS velocities (e.g., 230 m/s from spoofed GPS when actual airspeed is 22 m/s).

Airspeed fusion also enables dead reckoning via `readyToUseAirData()` when GPS is lost — requires `hasAirspeed` (ARSPD_USE=1) AND `assume_zero_sideslip()` (fly_forward=true).

### EK3_OPTIONS bit 0 (JammingExpected)

When set, the EKF requires preflight GPS quality checks to pass before resuming GPS fusion after a >2 second GPS outage. This prevents the EKF from immediately accepting a potentially spoofed GPS fix after jamming.

### `_force_disable_gps` (RC_OPTION 65)

`GPS_DISABLE` sets `_force_disable_gps` which makes ALL GPS instances report `NO_FIX` regardless of actual status (`AP_GPS.h`). This is a blanket disable — it affects hardware GPS AND external nav (e.g., MAVLink GPS backend) simultaneously. There is no per-instance GPS disable.

**Implication:** You cannot selectively disable a jammed hardware GPS while keeping external nav active. With GPS affinity, the better approach is to leave GPS enabled and let affinity isolate the bad GPS to its own lane.

### GPS Spoofing Failure Pattern

When a jammed GPS produces spoofed 3D fixes with valid satellite counts:

1. Spoofed position/altitude injected into EKF → position jumps hundreds of meters, velocity estimates physically impossible
2. All EKF lanes corrupted simultaneously (without affinity) → rapid lane switching amplifies discontinuities
3. EKF collapse → attitude flag lost → DCM fallback (bypasses DISABLE_DCM_FALLBACK bits)
4. EKF partial recovery → back to EKF3 → next spoofed update → collapse again
5. DCM↔EKF toggling + lane switching = compound instability

**Configuration to contain GPS spoofing:**
- `ARSPD_USE=1` — reject impossible velocity via airspeed cross-check
- `EK3_AFFINITY=1` — isolate spoofed GPS to one lane
- `EK3_IMU_MASK=3` — 2 lanes matching 2 GPS instances
- `EK3_OPTIONS=1` — JammingExpected
- `GPS_PRIMARY=1` — external nav as default
- Do not re-enable GPS hardware in jammed areas

## Tools

### Replay Tool

Re-runs the EKF on recorded log data for comparison. Requires `LOG_REPLAY=1` during the original flight to capture DAL data.

```bash
./waf configure --board sitl && ./waf --targets tool/Replay
./build/sitl/tool/Replay --force-ekf3 ./logfile.bin
# Override params: --parm NAME=VALUE
```

Output log in `logs/` has both original (C=0,1) and replayed (C=100,101) data. Use `Tools/Replay/check_replay.py` to verify outputs match.

**What Replay can test:** Any EKF behavior driven by DAL-logged sensor data and EKF parameters. This includes tuning parameter changes (`--parm EK3_VELNE_M_NSE=0.5`).

**What Replay cannot test:** Vehicle-specific behavior not captured in DAL logs — e.g. Copter flight mode logic, ground effect flag timing from `AP_GroundEffect.cpp`, hover bias learning lifecycle. For these, use SITL autotest or real flight.

**Replay and the DAL:** Replay feeds the EKF exclusively through the DAL. If EKF code reads data that bypasses the DAL (e.g. direct `AP::ins()` calls), replay will use stale or default values instead of the flight's actual data. Always access sensor data via `dal.ins()`, `dal.gps()`, etc. See the DAL section above.

### Diagnostic Commands

```bash
# Check altitude divergence
mavlogdump.py log.bin --types CTUN | grep "Alt\|BAlt"

# Check EKF height innovation (should be small, <0.5m)
mavlogdump.py log.bin --types XKF3 | grep "IPD"

# Check timeout status
mavlogdump.py log.bin --types XKF4 | grep "TS :"

# Check source configuration
mavlogdump.py log.bin --types PARM | grep "EK3_SRC.*VELZ"

# Extract EKF accel bias
mavlogdump.py log.bin --types XKF2 | grep -E "C : 0.*AZ :"

# Extract IMU temperature
mavlogdump.py log.bin --types IMU | grep "T :"

# List all message types
mavlogdump.py log.bin 2>/dev/null | grep "FMT.*Name :" | sed 's/.*Name : \([^,]*\).*/\1/' | sort -u
```

### Z-Bias Analysis Script

```bash
python3 libraries/AP_NavEKF3/tools/ekf_bias_analysis.py <logfile.bin>
python3 libraries/AP_NavEKF3/tools/ekf_bias_analysis.py <logfile.bin> --plot
python3 libraries/AP_NavEKF3/tools/ekf_bias_analysis.py <logfile.bin> --csv output.csv
```
