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

The EKF has two mechanisms for ground effect, both controlled by flags set in `ArduCopter/baro_ground_effect.cpp`:

1. **Innovation flooring:** Limits negative baro corrections during ground effect (`AP_NavEKF3_PosVelFusion.cpp`)
2. **Noise scaling:** Increases baro noise variance by 4x (`gndEffectBaroScaler = 4.0`)

Both are ONLY active when `takeoff_expected` OR `touchdown_expected` flags are true.

### When Flags Are Set

**`takeoff_expected = true`:** Armed AND `land_complete` is true AND mode is not THROW
**`takeoff_expected = false`:** 5s passed since takeoff OR vehicle above `TKOFF_GNDEFF_ALT`

**`touchdown_expected = true`:** Slow horizontal (XY speed demand ≤125cm/s OR actual ≤125cm/s) AND slow descent demanded

### The Gap

Hovering at low altitude (not taking off, not descending) has NEITHER flag true, so NO compensation. The `TKOFF_GNDEFF_ALT` parameter addresses this by re-enabling compensation when below the threshold.

| Flight Phase | takeoff_expected | touchdown_expected | Compensation |
|--------------|------------------|--------------------|--------------|
| On ground, armed | YES | NO | YES |
| First 5s or below TKOFF_GNDEFF_ALT | YES | NO | YES |
| Hovering above TKOFF_GNDEFF_ALT | NO | NO | NONE |
| Descending slowly for landing | NO | YES | YES |

### TKOFF_GNDEFF_ALT Tuning

Set **below** your typical hover altitude to avoid unnecessary compensation during stable hover:

| Hover Altitude | Recommended TKOFF_GNDEFF_ALT |
|----------------|------------------------------|
| ~0.5m | 0.3m |
| ~1.0m | 0.5-0.7m |
| ~1.5m | 1.0m |
| ~2.0m+ | 1.5m |

**If set too high:** Compensation stays active during stable hover, innovation gets clamped, EKF altitude drifts from baro.
**If set too low:** Ground effect spikes at low altitude corrupt the EKF estimate.

Ground effect causes **positive pressure (negative altitude)** — propwash pushes air down, baro reads lower than actual. Having compensation ON unnecessarily is safer than having it OFF when needed.

### TKOFF_GNDEFF_TMO Parameter

**New parameter** that requires BOTH a time delay AND altitude threshold before ground effect compensation is disabled.

**Problem it solves:** On vehicles with severe baro ground effect (motor-induced pressure noise), the EKF altitude can falsely cross the TKOFF_GNDEFF_ALT threshold due to baro noise, prematurely disabling ground effect protection. This causes the EKF to trust garbage baro data, leading to altitude estimate runaway and inability to take off in AltHold.

**Logic:**
- `TKOFF_GNDEFF_TMO = 0` (default): Original behavior — clear when (altitude > threshold) OR (5s elapsed)
- `TKOFF_GNDEFF_TMO > 0`: Clear when (timeout AND altitude > threshold) OR (5s max elapsed)

**Recommended settings for vehicles with severe baro ground effect:**
```
TKOFF_GNDEFF_TMO = 2    # or 3 for more protection (seconds)
TKOFF_GNDEFF_ALT = 0.8  # adjust based on hover altitude (meters)
```

This ensures the vehicle must be above the altitude threshold AND have been flying for the specified time before ground effect protection is removed. The 5s maximum timeout is always preserved.

## Z-Axis Accel Bias Learning Inhibition

### Problem

Without Z velocity measurements (no GPS indoors), the Z-axis accelerometer bias is poorly observable. Motor thrust/vibration creates a DC offset in AccZ (~+0.08-0.15 m/s²) that the EKF would incorrectly learn as bias. Multiple scenarios cause problems:

1. Motor thrust on ground creates AccZ offset
2. Optical flow provides only XY velocity, leaving Z-bias unobservable
3. When disarmed with optical flow, bias drifts unchecked
4. GPS configured but unavailable (indoors) — code must check actual data availability, not just configuration

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
| Takeoff (below TKOFF_GNDEFF_ALT) | **Inhibited** | Ground effect flag |
| Hover (above TKOFF_GNDEFF_ALT) | **Enabled** | Weakly observable from baro |
| Flying with GPS Z velocity | **Enabled** | Strongly observable |
| Flying with optical flow only | **Enabled** | Weakly observable from baro |
| Landing (slow descent) | **Inhibited** | Ground effect flag |

### Important: `dvelBiasAxisInhibit` vs Ground Effect Inhibition

The existing `dvelBiasAxisInhibit` mechanism (`AP_NavEKF3_core.cpp`) only handles **geometric** observability — once airborne, all axes are considered observable. It does NOT account for **measurement** observability (whether we have sensors that can observe the bias). The ground effect inhibition handles the measurement case.

## Hover Z-Bias Learning (Vibration Rectification Compensation)

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
| `TKOFF_GNDEFF_ALT` | Altitude threshold for ground effect (controls when learning is allowed) |

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

## Known Issues

### Motor-Induced Baro Noise

On small drones, motor operation can cause severe baro pressure noise (3-10x worse than motors-off). This is NOT a broken sensor — it's motor-induced pressure effects at the baro static port (prop wash, acoustic resonance, airframe vibration).

**Diagnosis:** Compare baro std dev with motors on vs off. If motors-on noise is significantly higher, this is the issue.

**Mitigations:**
1. **Hardware:** Relocate baro away from prop wash, add foam isolation
2. **BARO_FLTR_RNG:** Enable baro filtering
3. **TKOFF_GNDEFF_ALT:** Increase threshold to keep ground effect protection longer
4. **TKOFF_GNDEFF_TMO:** Require time delay before ground effect clears

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
- `TKOFF_GNDEFF_TMO = 3` (keep ground effect active during takeoff transient)
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

**Solution:** Use `TKOFF_GNDEFF_TMO` to require BOTH time delay AND altitude threshold.

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
TKOFF_GNDEFF_ALT = 5          # Keep ground effect protection to 5m
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

**Key code:** `AP_NavEKF3_VehicleStatus.cpp` (onGround detection), `AP_NavEKF3_PosVelFusion.cpp` (zero velocity fusion, innovation flooring), `ArduCopter/baro_ground_effect.cpp` (flag control)

## Tools

### Replay Tool

Re-runs the EKF on recorded log data for comparison.

```bash
./waf configure --board sitl && ./waf --targets tool/Replay
./build/sitl/tool/Replay --force-ekf3 ./logfile.bin
# Override params: --parm NAME=VALUE
```

Output log in `logs/` has both original (C=0,1) and replayed (C=100,101) data.

**Limitations:** Only includes EKF parameters. Copter-specific parameters (`TKOFF_GNDEFF_ALT`) and ground effect flags cannot be tested via Replay — use SITL or real flight.

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
