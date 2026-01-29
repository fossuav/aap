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
