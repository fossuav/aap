---
name: log-analyze
description: Analyze ArduPilot DataFlash .bin log files or MAVLink .tlog telemetry logs. Use when the user provides a .bin or .tlog log file path or asks to analyze flight log data.
argument-hint: "<logfile> [focus area]"
allowed-tools: Bash(python3 *), Read, Grep, Glob
---

# ArduPilot Log Analysis

You have a log extraction tool at `.claude/skills/log-analyze/log_extract.py` that handles common analysis tasks without writing one-off scripts. It supports both DataFlash `.bin` logs and MAVLink `.tlog` telemetry logs.

## Standard Workflow

### Step 1: Overview (ALWAYS do this first)

```bash
python3 .claude/skills/log-analyze/log_extract.py overview <logfile>
```

This gives you: message types with counts and fields, key parameters (including tuning PID gains, notch filter config, motor settings), flight modes, arm/disarm events, and errors. Read the output carefully before proceeding.

**For .tlog files:** The overview also shows source systems (vehicle, GCS, peripherals), status text messages, and suggests the vehicle system ID. Use `--system <id>` to filter by source system:

```bash
# Show overview filtered to vehicle only (eliminates GCS noise)
python3 .claude/skills/log-analyze/log_extract.py overview <logfile.tlog> --system 5
```

### Step 2: Targeted Extraction

Based on what the overview reveals, extract specific data:

```bash
# EKF data for core 0
python3 .claude/skills/log-analyze/log_extract.py extract <logfile> \
    --types XKF1 --condition "XKF1.C==0"

# Multiple types, specific fields
python3 .claude/skills/log-analyze/log_extract.py extract <logfile> \
    --types BARO,RFND --fields Alt,Dist

# Time window
python3 .claude/skills/log-analyze/log_extract.py extract <logfile> \
    --types ATT --from-time 10.0 --to-time 30.0

# Reduce output for large datasets
python3 .claude/skills/log-analyze/log_extract.py extract <logfile> \
    --types IMU --decimate 10 --limit 0
```

### Step 3: Statistics

Compute min/max/mean/std/percentiles without custom scripts:

```bash
# Stats for specific sources
python3 .claude/skills/log-analyze/log_extract.py stats <logfile> \
    --sources "RATE.YDes,RATE.Y,RATE.YOut,PIDY.P,PIDY.D"

# Stats using types/fields syntax
python3 .claude/skills/log-analyze/log_extract.py stats <logfile> \
    --types RATE --fields YDes,Y,YOut --from-time 10 --to-time 30

# Stats with condition filter
python3 .claude/skills/log-analyze/log_extract.py stats <logfile> \
    --types XKF4 --fields SV,SP,SH --condition "XKF4.C==0"
```

Output includes: Count, Min, Max, Mean, Std, P5, P50, P95 for each field.

### Step 4: Multi-Source Comparison

Compare data from multiple sensors aligned to a common time grid:

```bash
# Altitude: BARO vs RFND vs EKF vs GPS vs CTUN
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe altitude

# Attitude: actual vs desired roll/pitch/yaw
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe attitude

# Vibration: raw accel + VIBE values
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe vibration

# EKF variances and health
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe ekf_health

# RC input vs output
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe rc

# PID components per axis
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe pid_yaw
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe pid_roll
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe pid_pitch

# Rate tracking per axis (desired vs actual vs output)
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe rate_yaw
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe rate_roll
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe rate_pitch
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe rate_all

# Motor outputs
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe motor_output

# Controller RMS values (oscillation indicator)
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> --recipe ctrl_rms

# Custom comparison (prefix with - to negate)
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> \
    --sources "BARO.Alt,RFND.Dist,-XKF1.PD"
```

### Step 5: Plot (when visual analysis helps)

```bash
# Plot a recipe
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --recipe altitude --output /tmp/altitude.png

# Plot PID components (great for oscillation diagnosis)
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --recipe pid_yaw --from-time 30 --to-time 35 --output /tmp/pid_yaw.png

# Plot rate tracking
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --recipe rate_yaw --output /tmp/rate_yaw.png

# Plot controller RMS
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --recipe ctrl_rms --output /tmp/ctrl_rms.png

# Plot custom sources (same syntax as compare --sources)
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --sources "RATE.YDes,RATE.Y" --output /tmp/yaw_tracking.png

# Plot specific fields from a message type
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --types XKF4 --fields SV,SP,SH --output /tmp/ekf_var.png

# Time-windowed plot
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --recipe altitude --from-time 10 --to-time 60 --output /tmp/takeoff.png
```

After generating a plot, read the image file to view it.

## Available Recipes

| Recipe | Description | Sources |
|--------|-------------|---------|
| `altitude` | Altitude comparison | BARO, RFND, EKF, CTUN/QTUN |
| `attitude` | Attitude actual vs desired | ATT Roll/Pitch/Yaw + Des |
| `vibration` | Vibration analysis | IMU AccXYZ, VIBE XYZ |
| `ekf_health` | EKF variances | XKF4 SV/SP/SH/SM/SVT |
| `rc` | RC input vs output | RCIN/RCOU C1-C4 |
| `pid_roll` | Roll PID components | PIDR P/I/D/FF |
| `pid_pitch` | Pitch PID components | PIDP P/I/D/FF |
| `pid_yaw` | Yaw PID components | PIDY P/I/D/FF |
| `rate_roll` | Roll rate tracking | RATE RDes/R/ROut |
| `rate_pitch` | Pitch rate tracking | RATE PDes/P/POut |
| `rate_yaw` | Yaw rate tracking | RATE YDes/Y/YOut |
| `rate_all` | All axes rate tracking | RATE Des/Act all axes |
| `motor_output` | Motor outputs | RCOU C1-C4 |
| `ctrl_rms` | Controller RMS values | CTRL RMSRollP/D, PitchP/D, Yaw |

## Analysis Methodology

1. **Extract data first, theorize second.** Always run `overview` then targeted extractions before forming hypotheses.
2. **Cross-check multiple sensors.** Never trust a single source. Compare EKF estimate against raw sensors (baro, rangefinder, GPS).
3. **Check the events timeline.** ARM/DISARM, mode changes, and errors give crucial context.
4. **Filter EKF by core.** XKF* messages have a `C` field for core index. Use `--condition "XKF1.C==0"` to isolate one core.
5. **Mind the units.** XKF1 angles are in centidegrees. PD is positive-down (NED). BARO.Alt is meters above origin. RFND.Dist is meters.
6. **Use stats for quantitative comparison.** When comparing axes or checking for oscillation, `stats` gives instant min/max/mean/std without custom scripts.
7. **Verify servo/motor mapping before naming motors.** See "Vehicle Identification Reconnaissance" below. Do not assume `ESC.Instance==N` is "Motor N" — check `SERVO*_FUNCTION` values in the log and translate.
8. **Separate physical vehicles even when the build spec is identical.** Logs from before and after a crash/rebuild are from different hardware. See "Multi-Log and Cross-Flight Analysis" below.
9. **`BAT.Curr` is pack-level, not per-motor.** `ESC.Curr` is often zero on DShot bidir — verify before relying on it.
10. **Aerodynamic body effects pollute in-flight calibration measurements.** On airframes with meaningful body lift, control fins, or significant drag, any in-flight attempt to characterise the thrust curve, hover throttle, or PID plant above low airspeed (~5–10 m/s) is contaminated by speed-dependent non-rotor contributions. Clean measurements for these quantities need static/bench conditions or stable-hover segments at minimal forward speed.
11. **Two-instance sensor analysis: focus on what was the *same* on both instances, not what differed.** When a sensor has two instances (compass, GPS, IMU, baro), the failing instance is rarely the diagnostic target — both instances usually see the same external event with different sensitivity, and the one that drops is just the one with less margin. Pull both, then ask "what was the same on both around the event?" That answer is the root cause; the asymmetric response is downstream of it. Ignoring this leads to "GPS2 is broken, replace it" recommendations when GPS2 is fine and a passing jammer was the cause.
12. **Verify the user's theory rather than inheriting it.** Customer reports often correctly identify the *time and direction* of a failure but mis-name the *cause*. Common substitutions: "GPS glitch" when actually compass; "multipath" when actually interference; "motor failure" when actually mixer saturation. Restate the user's theory as your first step, then build the diagnosis to confirm or disconfirm it explicitly. Do not assume the theory is right and look for confirming evidence — that is the standard route to a wrong fix.

## Vehicle Identification Reconnaissance

Before analysing per-motor data, **always verify the servo-to-motor mapping from the log itself**:

```bash
python3 .claude/skills/log-analyze/log_extract.py extract <logfile> \
    --types PARM --condition "PARM.Name=='SERVO1_FUNCTION' or PARM.Name=='SERVO2_FUNCTION' or PARM.Name=='SERVO3_FUNCTION' or PARM.Name=='SERVO4_FUNCTION'"
```

**The trap:** `ESC.Instance==N` corresponds to the `SERVO(N+1)` output channel, **not** to ArduPilot's motor number. On a vehicle with non-standard `SERVO*_FUNCTION` assignments, `ESC.Instance==3` can be Motor 2 rather than Motor 4 — or any other mapping. The motor roles are the `SERVO_*_FUNCTION` values (33-36 for quad motors 1-4, with higher values for hexa/octa), not the channel index or the ESC instance.

| Log field | What it identifies |
|---|---|
| `ESC.Instance` | Zero-indexed ESC order (0-3 for a quad) |
| `RCOU.CN` | PWM output channel N (1-indexed) — same as SERVO*N* |
| `SERVO_N_FUNCTION` | The motor role assigned to that output channel |

**Consequence of getting it wrong:** you blame a motor that's actually the healthiest while the actual weak channel goes uninvestigated. The symptom is often "the motor I flagged doesn't match what the pilot reports as having felt off."

Hexa, octa, and coax mappings are even easier to misread. On any non-standard build or any diagnosis that names a specific physical motor, make the mapping table explicit in your analysis output.

### Pack Current vs Per-Motor Current

`BAT.Curr` is total pack current. It is **not** per-motor current. Three common errors from conflating them:

1. **Estimating per-motor thermal load during aggressive manoeuvres.** The mixer creates asymmetry under roll/pitch correction — one motor can be at 90% throttle while another is at minimum spin. During such events a single motor may be drawing 35-40% of pack current, not 25%. Worst-case per-motor share is roughly `pack / 3`, not `pack / 4`.
2. **Reasoning about `MOT_BAT_CURR_MAX` as a per-motor limit.** It is a pack-level limit. The mixer cannot enforce per-motor current caps.
3. **Assuming `ESC.Curr` is populated.** On many DShot300/600 bidir setups `ESC.Curr` is zero — the telemetry frame does not include current, only RPM (and sometimes temperature). Verify the stats are non-zero before relying on it; if zero, you only have pack-level current.

## Multi-Log and Cross-Flight Analysis

### Vehicle Identity

**Before correlating observations across multiple logs, establish that the logs are from the same physical vehicle.** Same firmware, same `FRAME_CLASS`, same param file, and even same pilot does not guarantee same hardware. A rebuilt airframe after a crash is a different vehicle regardless of how much of the spec is preserved. Motor/ESC/prop health observations do not transfer across a rebuild.

Heuristics for establishing continuity:

- `STAT_BOOTCNT` and `STAT_FLTTIME` should monotonically increase across logs from the same airframe
- Large gaps in time with `STAT_FLTTIME` reset or dropping indicate a new vehicle (or a flight-time reset, which is itself a reason to double-check)
- A crash event in one log followed by subsequent logs should be treated as a different vehicle until explicitly confirmed otherwise

**Do not** carry forward "Motor X is weak" findings across a rebuild. The *failure mode* may recur (same airframe type under similar maneuvres will have similar failure modes) but the *specific weak channel* is a property of the current physical hardware.

### Chronological Per-Motor Diagnostics

When you have multiple logs from a single confirmed-same vehicle spanning hours or days, per-motor patterns become visible that don't show up in any individual log:

**Per-ESC error-rate sweep.** `ESC.Err` (DShot bidir error rate %) per `ESC.Instance` across a day of flights reveals motor-channel degradation:

```bash
for log in log1.bin log2.bin ... ; do
    for inst in 0 1 2 3; do
        python3 .claude/skills/log-analyze/log_extract.py stats "$log" \
            --sources "ESC.Err" --condition "ESC.Instance==$inst and ESC.RPM>1000"
    done
done
```

Patterns to look for:

- **Baseline outlier:** one instance with `max` error rate 10-100× its peers during a flight where everything else is clean. This is the earliest fingerprint of a weakening channel and often appears in flights the pilot reports as "fine."
- **Single-flight transient > 30%:** a "ground the vehicle" event. Even if nothing catastrophic happened in that flight, a DShot error rate spike that high indicates the ESC-motor link is intermittently losing frames; the next aggressive flight is where it fails. Treat log37-class events (one big spike before a crash) as preventable warnings.
- **Across-flight climb:** per-motor error rate climbing steadily across a day is predictive of imminent desync/burnout.

These patterns require same-vehicle continuity to read correctly — see "Vehicle Identity" above.

**Operating-envelope thresholds.** On a specific vehicle, the pack-current level at which DShot errors begin to cross 1% is an empirical electrical-stress threshold for that combination of motor + ESC + pack + cooling. Cross-reference `BAT.Curr` with `ESC.Err` in the same time window to find it:

```bash
# Pack current trajectory and error rates during a high-stress segment
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> \
    --sources "BAT.Curr,ESC.Err" --interval 0.25 --from-time <peak_start> --to-time <peak_end>
```

This threshold is a **hardware-specific** measurement that drifts down as batteries age and motor runtime accumulates. It is a useful per-vehicle health signal but does **not** transfer across vehicles even of the same build.

## Parameter-Change Safety Rules

These are general rules for when recommending parameter changes from log evidence is or is not appropriate. The underlying principle: a PID or filter value that came out of autotune, a calibration run, or bench measurement represents actual airframe dynamics; overriding it without new measurement evidence replaces data with opinion.

Before recommending any tuning change, ask: *what would I measure in the log to show this specific parameter is the problem, and have I actually measured that?* If the answer is "I'm interpolating from general rules," do not recommend it.

### Rate-Loop Gains Post-Autotune

**Recommend a change when:**
- Rate-tracking data shows sustained error with large I-term accumulation that doesn't decay during the manoeuvre
- `CTRL.RMS` values show sustained oscillation on a specific axis in normal flight
- PID component stats show a specific term saturating at its IMAX/PDMX limit

**Do not recommend a change when:**
- The apparent tracking error is at a flight condition autotune never tested (forward speed, attitude extremes, near-vertical attitude where body-frame rate axes are kinematically coupled). These are often physics, not gain.
- The mean error is small and only the peaks are large — autotune's output already handles the mean correctly, and peaks come from transient disturbances the PID loop is actually doing the right thing about.
- The "error" at peak speed is really the rate loop delivering less output than demanded because **motor authority is saturated**. Raising P does not create thrust headroom.

### ATC_RAT_*_SMAX

**Never recommend setting this on a copter rate PID.** The slew-rate modifier (`Dmod` in `libraries/AC_PID/AC_PID.cpp:263-267`) scales only the rate-loop P and D outputs:

```cpp
_pid_info.Dmod = _slew_limiter.modifier((_pid_info.P + _pid_info.D) * _slew_limit_scale, dt);
P_out *= _pid_info.Dmod;
D_out *= _pid_info.Dmod;
```

The upstream angle P gain (`ATC_ANG_*_P`) is not scaled. When SMAX engages, the angle loop continues commanding full-authority rate demands while the rate loop's ability to follow them has been cut. The loop mismatch can drive oscillation and outright instability, especially on airframes with above-default angle P gains.

**Use `IMAX` for integrator runaway protection and `PDMX` for P-output capping.** Both act honestly in the rate loop without hiding their effect from the angle loop.

### ATC_RAT_YAW_D

Yaw D is a narrow parameter in ArduCopter — typical values are 0.000–0.005. Many airframes converge at `AUTOTUNE_MIN_D` (default 0.0003) during yaw tuning.

**Autotune converging at `MIN_D` is a signal, not an artefact.** Autotune scans D upward looking for damping improvement and stops at the lowest value where the test metric either stops improving or starts oscillating. Landing at the floor means the airframe does not tolerate more yaw D.

**Raising yaw D above autotune's output** puts D-term output into the same order of magnitude as P-term output under buffet or noise. On a quad, yaw torque comes from differential thrust — every unit of yaw D output drives repeated asymmetric motor loading. This is a documented cause of motor/ESC thermal failure on high-TWR quads.

**Recommend raising yaw D only with specific evidence:**
- `PIDY.Dmod`-limited events in hover (indicates the rate loop is actively damping something)
- Sustained yaw-rate oscillation that P-gain changes alone can't explain
- Bench or flight data showing a specific damping deficit

Do not recommend raising it on "it's at the minimum, we have room" reasoning.

### ATC_INPUT_TC

**This is a pilot-feel parameter, not a log-derivable parameter.** `ATC_INPUT_TC` controls the time constant of the angle target's response to stick input in angle modes (STABILIZE, ALT_HOLD, LOITER). Its "right" value is subjective.

**Recommend a change only on pilot report:**
- Pilot reports perceived lag or sluggishness → consider lowering
- Pilot reports overshoot or twitchy feel → consider raising
- If the pilot hasn't complained, don't touch it.

**Do not recommend a change based on:**
- Rate-demand peak data alone (the peaks scale with any TC change, so there's no baseline to compare against)
- Cross-vehicle comparison or "typical for this airframe class"

**Cost of lowering:** halving TC roughly doubles the peak rate demand for the same stick input. On a vehicle already saturating the rate loop or motor output at peak throttle, lowering TC moves more load into the saturation regime. Verify headroom before recommending a decrease.

### MOT_SPIN_MAX vs MOT_BAT_CURR_MAX (Motor Thermal Protection)

When the goal is to protect motors or ESCs from thermal burnout (over-volted motors, marginal continuous current rating, cooling problems), **use `MOT_BAT_CURR_MAX` with a value from component specifications**, not `MOT_SPIN_MAX`.

**Why `MOT_SPIN_MAX` is the wrong tool for thermal protection:**

`MOT_SPIN_MAX` clips at the actuator stage (`libraries/AP_Motors/AP_MotorsMulticopter.cpp:468`) *after* the mixer has computed per-motor thrust contributions assuming the full [0, 1] range was available. When `spin_max < 1.0`, the mixer silently commands more than it gets. The rate loop absorbs the mismatch via attitude error. Invisible on benign flights; growing under saturation.

**Why `MOT_BAT_CURR_MAX` is the right tool:**

`MOT_BAT_CURR_MAX` modulates `_throttle_thrust_max` (`libraries/AP_Motors/AP_MotorsMulticopter.cpp:348-385`), which the mixer uses as its input ceiling at `libraries/AP_Motors/AP_MotorsMatrix.cpp:234-244`. The mixer sees the reduced ceiling and plans around it. No loop mismatch. `ATC_THR_MIX_MAN/MAX` still applies — when the mixer saturates against the reduced ceiling, attitude is still prioritised over throttle.

The mechanism: when measured current exceeds the limit, `_throttle_limit` decreases (smoothed by `MOT_BAT_CURR_TC`, default 5 s), and max throttle is pulled down to `throttle_hover + (1 − throttle_hover) * _throttle_limit`. The floor is `throttle_hover`, so the vehicle can always hover.

**Time-scale caveat:** `MOT_BAT_CURR_MAX` protects against **sustained** over-current (seconds-scale, matching motor thermal failure modes). It does **not** protect against millisecond-scale ESC desync under abrupt PWM step commands — that's ESC firmware territory, not tuning.

**Picking a value:** should come from the *lower* of:

1. Battery continuous C-rating × capacity
2. ESC continuous current rating × motor count (with margin for mixer asymmetry — worst case is pack/3 on one motor, not pack/4)
3. Motor continuous current rating (thermally derated for the actual operating voltage)
4. Empirical operating-envelope threshold from logs, if available

If component specs are unknown, the operating envelope (where DShot errors begin to cross 1% in existing logs) is a data-driven starting point. Always pick the lower of the envelope and the spec.

### MOT_THST_EXPO

**`MOT_THST_EXPO` should be measured on a thrust stand, not derived from flight logs.** It is ArduCopter's inverse of the empirical thrust curve `thrust = (1 − expo) * actuator + expo * actuator²`. A wrong value means every commanded thrust becomes a wrong actuator command, and the PID loop fit *depends on the assumed curve being close to the real one*.

**Recommend a change in direction when:**
- Physics of the prop suggests default doesn't apply. High-pitch props, large-diameter props, or props with notably high static torque draw (heavy drag at low RPM) typically need higher expo than default (0.65). Low-pitch racer props typically match default.
- `ESC.RPM` vs commanded actuator in log data is notably shallower than `RPM ∝ √throttle` would predict — the signature of a drag-loaded prop-motor system where the default curve doesn't fit.

**Do not recommend a specific numerical value from log data alone:**
- In-flight thrust measurements are corrupted by aerodynamic body lift above low airspeeds (~5–10 m/s)
- Vehicles rarely sit in clean stable hover long enough for accurate curve fitting
- Without known mass or a direct thrust measurement, accel integration can't be converted to thrust
- `MOT_THST_HOVER` may be frozen (`MOT_HOVER_LEARN=0`) and unreliable as a cross-check if the curve is wrong

**Required follow-up after any `MOT_THST_EXPO` change:** re-run `AUTOTUNE`. The existing tune was measured against the old thrust model. Changing the model shifts the plant the PID loops see, invalidating the fit. Do not fly aggressive envelopes on pre-change gains.

**Bench procedure (canonical):**
1. Mount one motor+prop+ESC on a thrust stand at the actual operating voltage
2. Sweep actuator from `MOT_SPIN_MIN` to `MOT_SPIN_MAX` in ~20 steps, holding each 2-3 s
3. Record actuator, thrust, RPM, current, voltage
4. Fit to `thrust = (1 − expo) * a + expo * a²` and read off `expo`
5. Apply, re-run `AUTOTUNE`, validate with stable hover across three battery-voltage states before aggressive flight

### EK3_GLITCH_RAD — Two Modes

`EK3_GLITCH_RAD` is not a simple "how aggressive is GPS glitch rejection" knob — it selects between two different code paths in `libraries/AP_NavEKF3/AP_NavEKF3_PosVelFusion.cpp` (branches at lines `819-829`, `894-905`, `942-951`).

- **`EK3_GLITCH_RAD > 0` (default 25):** innovation tests that fail trigger `ResetPosition()` to the GPS fix when position variance grows beyond `GLITCH_RAD²`. Appropriate for hover-class copters where a 25 m innovation is almost certainly a bad GPS fix.
- **`EK3_GLITCH_RAD <= 0` (special case):** innovation variance is scaled by the failed test ratio, bounding the state update without triggering a reset. The EKF stays on its IMU prediction and corrects toward GPS gradually.

**Which to use depends on the vehicle's operational envelope:**

- **Hover-class / slow cruise copters (typical multirotors):** default 25 is correct. Glitch rejection protects against real bad fixes.
- **High-speed vehicles (sustained >30-50 m/s cruise or aggressive acro):** set to **0**. GPS processing latency of ~100 ms is already 5 m of apparent position error at 50 m/s and 10 m at 100 m/s. Combined with covariance growth from high dynamics, the `> 0` path triggers `ResetPosition()` to the *lagged* GPS fix, snapping the state to where the GPS *thinks* the vehicle is. This is a flyaway mechanism at high speed. The `<= 0` path handles the same large innovations bounded-variance style.

**Log diagnostic:** `"GPS Glitch or Compass error"` in `MSG`/`STATUSTEXT` during aggressive flight is the innovation test firing. With `GLITCH_RAD <= 0` the special path handles the update safely and no reset occurs. With `GLITCH_RAD > 0` the same message is followed by position snaps and often `EKF lane switch` events that may look like EKF health failures but are actually the reset mechanism misfiring.

**Do not** recommend "set `GLITCH_RAD` back to 25" on a high-speed platform as a fix for EKF messages during peak-speed flight. On those vehicles, **the default value is the wrong one**, and the messages are a normal consequence of the innovation test at high dynamics — they are not evidence of a bad GPS fix.

## Compass Yaw Sanity Check (180° / 90° Heading Errors)

A compass that reports yaw 90° or 180° wrong is one of the most dangerous and most-missed pre-flight failure modes — pre-arm cannot catch it because the vehicle is stationary and GPS course is undefined. The vehicle arms cleanly, then flies sideways or backwards into the ground at the first commanded position move.

**In-flight signature** (in this order):

1. Position controller commands sustained forward pitch/roll for a position move; vehicle accelerates in the *wrong* direction.
2. EKF GPS innovations (`XKF3.IVN`, `IVE`, `IPN`, `IPE`) ramp continuously and pin at the gate value as the position controller pushes harder.
3. `EKF3 lane switch` events as cores disagree about the right answer.
4. Status text: `"GPS Glitch or Compass error"` — this message is generic and can mean either; the log tells you which.
5. `EKF3 IMU0 emergency yaw reset` (and IMU1) — yaw snaps by ~90° or 180° in one sample as the EKF gives up and aligns to GPS.
6. After disarm: `"PreArm: AHRS: EKF3 Yaw inconsistent N deg. Wait"` where `N` is close to 90 or 180 — direct numerical confirmation of the heading error.

**Diagnostic — compare EKF yaw to GPS ground course during forward flight:**

```bash
python3 .claude/skills/log-analyze/log_extract.py plot <log> \
    --sources "ATT.Yaw,GPS.GCrs" --from-time <move_start> --to-time <move_end>
```

During steady forward flight at >2 m/s, `ATT.Yaw` and `GPS.GCrs` should agree to within ~10° (the residual is wind drift). A flat persistent offset of ~90°, ~180°, or ~270° across the entire moving segment is a compass orientation/calibration error. Stationary segments are not informative — `GCrs` is undefined at zero speed.

**Disambiguating "GPS Glitch or Compass error":**

The EKF cannot distinguish a wrong heading from a wrong GPS fix from inside the filter — both produce GPS innovations the same way. The message names both because either could be the cause; the log tells you which:

| Evidence | Cause |
|---|---|
| `GPS.NSats` stable, `GPS.HDop` stable, both GPS instances agree on position | **Compass** |
| `GPS.NSats` drops, `GPS.HDop` spikes, or two GPS instances disagree on position | **GPS** |
| `ATT.Yaw` differs from `GPS.GCrs` by ~90°/180°/270° during forward flight | **Compass** |
| Post-event `"EKF Yaw inconsistent N deg"` with N near 90 or 180 | **Compass** (N is the actual error) |
| uBlox `MON-HW` `agcCnt` drops at the same instant | **GPS** (interference — see uBlox section below) |

**Pre-arm limitation:** the GPS-course/compass consistency check requires forward motion. A stationary vehicle cannot trigger it. Catching this on the ground requires either an external reference (sun compass, known landmark bearing) or a brief taxi/walk-forward step before takeoff to confirm `XKF1.Yaw` matches `GPS.GCrs`.

## GPS Receiver Health Diagnostics (uBlox MON-HW / MON-HW2)

uBlox-based GPS units (`GPS_TYPE=2`) emit per-instance hardware-monitor messages that distinguish **interference** from **multipath** from **antenna fault** from **constellation outage**. The fields are routinely under-used because the field interpretations are non-obvious — and several of them are counter-intuitive.

**Message names** (logged once every ~5 s per instance):

| Message | Source | Content |
|---|---|---|
| `UBX1` | GPS instance 0 | MON-HW: `noisePerMS`, `jamInd`, `aPower`, `agcCnt` |
| `UBX2` | GPS instance 0 | MON-HW2: `ofsI`, `magI`, `ofsQ`, `magQ` |
| `UBY1` | GPS instance 1 | MON-HW (same fields as UBX1) |
| `UBY2` | GPS instance 1 | MON-HW2 (same fields as UBX2) |

**Field interpretations — the intuitive readings are wrong; read carefully:**

| Field | Healthy | Meaning |
|---|---|---|
| `agcCnt` | 4000–5000 | AGC count. **Lower = strong incoming RF forcing AGC to back off.** The receiver is reducing front-end gain because something is too loud. **The most reliable interference indicator.** |
| `noisePerMS` | 65–95 | Receiver-measured noise. Counter-intuitively *drops* during strong narrowband interference — AGC clamp suppresses everything, including the noise-floor measurement. Do not interpret a drop as "improvement". |
| `jamInd` | 0–30 | Jamming indicator. **Unreliable on its own.** It is calibrated against initial conditions and tends to under-report sustained narrowband interference. Don't trust `jamInd` to decide whether interference is happening — use `agcCnt`. |
| `aPower` | 1 | Antenna power state. 0 = open or short feedline. **Decisive when present** — points at hardware fault, not interference. |
| `magI`, `magQ` | 100–170 | I/Q channel signal magnitudes. **Drop below ~50 = front-end saturated/compressed.** Second most reliable interference indicator after `agcCnt`. |
| `ofsI`, `ofsQ` | -10 to 25 | I/Q DC offsets. Persistent large values point to receiver hardware issues, not interference. |

**Interference vs multipath signature comparison:**

| | Multipath | Interference | Antenna fault |
|---|---|---|---|
| `agcCnt` | unchanged | drops sharply | rises (toward max) |
| `magI` / `magQ` | unchanged | drop sharply (often <50) | drop |
| `noisePerMS` | unchanged or slight rise | drops with AGC clamp | rises |
| `aPower` | 1 | 1 | **0** |
| `NSats` | gradual decrease | full loss possible | progressive loss |
| `HAcc` while fix held | inflated to several metres | stays at cm-level on unaffected receiver | N/A (loss of fix) |
| Affected sky region | low-elevation satellites | whole sky | whole sky |
| Both instances affected? | typically yes, similar magnitude | yes, often *asymmetric* (whichever antenna sees the source more) | typically only the one with the broken cable |
| Recurrence | site-specific | source-of-RF-specific | deterministic, every flight |

**Workflow when a GPS dropout is suspected:**

1. Confirm dropout: extract `GPS.Status`, `GPS.NSats`, `GPS.HDop` (and `GPS2.*` if present). A dropout shows `Status=1`, `NSats=0`, `HDop=99.99`.
2. Plot the hardware monitor data on both receivers across the dropout window:
   ```bash
   python3 .claude/skills/log-analyze/log_extract.py plot <log> \
       --sources "UBX1.agcCnt,UBY1.agcCnt,UBX1.noisePerMS,UBY1.noisePerMS"
   python3 .claude/skills/log-analyze/log_extract.py plot <log> \
       --sources "UBX2.magI,UBX2.magQ,UBY2.magI,UBY2.magQ"
   ```
3. Match the pattern: AGC drop + magI/magQ collapse → interference. Sat count drift but stable AGC → multipath/sky obstruction. `aPower=0` → hardware fault.
4. Check EKF response: `NKF4.GPS` (or `XKF4.GPS`) shows which instance the EKF is using. If the working instance was already primary, the vehicle should be unaffected.
5. Asymmetry between instances (one drops, the other holds) usually means **antenna/feedline placement** difference, not module difference — the two receivers are configured the same and saw the same external event with different physical coupling.

## Before Recommending a Fix — Verification Checklist

Do NOT send a diagnosis or recommendation to the user until you have independently verified it against every corroborating data stream in the log. A plausible-sounding theory is not evidence.

**For every hypothesis, walk through this list before reporting:**

| Claim type | Data you MUST also pull before concluding |
|------------|-------------------------------------------|
| "Sensor X is wrong" | The *other* instance of the same sensor (IMU 0 vs 1, BARO 0 vs 1, GPS 1 vs 2) and the EKF innovation for that sensor. If both instances agree, it is not a sensor fault. |
| "Motor / frame asymmetry" | `RCOU.C1…Cn` at stable hover AND during the event; `ESC[i].RPM` if available. Quantify the diagonal-pair imbalance. |
| "Motor saturation limits authority" | RCOU values vs `MOT_SPIN_MIN` / `MOT_SPIN_MAX` / `MOT_PWM_MIN` / `MOT_PWM_MAX`. A motor pegged at the floor during a climb overshoot is proof, not speculation. |
| "EKF is falsely reporting climb/descent" | XKF3 innovations (IVD, IPD), both IMUs' raw AccZ, and BARO.Alt. All three should disagree with the EKF before you blame the filter. |
| "GPS glitch caused failsafe" | GPS.Spd and GPS.Alt at the instant of the ERR, plus GPS.NSats and HDop to show it wasn't a coverage issue. Show the innovation spike (XKF3.IVE/IVN/IPE/IPN), not just the ERR message. |
| "GPS receiver dropped fix / RTK lost" | uBlox `MON-HW` `agcCnt` and `MON-HW2` `magI`/`magQ` on **both** receivers during the dropout window; the *other* GPS instance's status; the EKF's `NKF4.GPS` (or `XKF4.GPS`) source field; and `aPower`. Distinguish interference (AGC drops) from multipath (no AGC drop) from antenna fault (`aPower=0`) before recommending action. See "GPS Receiver Health Diagnostics" above. |
| "Compass / heading is wrong" | `ATT.Yaw` vs `GPS.GCrs` during steady forward flight at >2 m/s — must agree to ~10°. A flat persistent ~90°/180°/270° offset is direct evidence; "EKF Yaw inconsistent N deg" post-event is the numerical confirmation. Innovation spikes alone are not enough — they only show that *something* disagrees with GPS, not that compass is the wrong something. See "Compass Yaw Sanity Check" above. |
| "Source-set / failover recommendation" | See EKF source-set playbook note in `libraries/AP_NavEKF3/CLAUDE.md` — source sets are manually switched, not automatic failover. Do not recommend `EK3_SRC2_*` as a "fallback" for glitch response. |
| "Fence action caused the crash" | MODE changes AND fence ERR codes AND aircraft state (alt/speed) at fence breach time. |

**Rule of thumb:** If a reviewer asked "how do you know?", you should be able to cite a specific row from the log. If the answer is "it's consistent with the symptom", you have not finished verifying.

### Worked example — "climbs when moving left" misdiagnosis

Initial plausible-but-unverified theory: *"accelerometer misalignment during hard left roll creates a false climb signal in the EKF"*. Evidence that seemed to support it: XKF3.IVD positive (GPS disagrees with EKF), both baro and EKF show climb.

What actually showed up on full verification:
- IMU 0 and IMU 1 AccZ traces were within 0.1 m/s² through the whole event → **not** an IMU fault.
- `RCOU.C1..C4` at hover: `1455, 1475, 1186, 1277` — a ~250 PWM diagonal asymmetry. Motor 3 sat near `MOT_SPIN_MIN` before anything went wrong.
- During left-roll events, the roll mixer drives M3 below its floor; `CTUN.ThO` hits 0.00 but M3 stays pinned at 1150 → the vehicle physically cannot descend.
- On right-roll events M1/M4 are decreased instead, both have headroom, no symptom.

The root cause was a **frame/yaw build asymmetry** leaving M3 at saturation. Recommending EKF parameter changes would have been a dead end. The verification table above is exactly what flushed this out.

## Oscillation Diagnosis Workflow

When investigating oscillation or tuning issues:

1. **Overview** — check ATC_RAT_* gains, SMAX, filter cutoffs, notch config
2. **Stats** — `--sources "CTRL.RMSRollD,CTRL.RMSPitchD,CTRL.RMSYaw"` to identify which axis
3. **PID plot** — `--recipe pid_yaw` (or roll/pitch) to see P/I/D/FF components
4. **Rate tracking** — `--recipe rate_yaw` to check desired vs actual tracking quality
5. **Zoom in** — use `--from-time`/`--to-time` on plots to examine specific maneuvers

## Common Message Types

### Navigation
| Type | Key Fields | Notes |
|------|-----------|-------|
| XKF1 | Roll,Pitch,Yaw,VN,VE,VD,PN,PE,PD | EKF primary output. PD is positive-down. |
| XKF2 | AX,AY,AZ,VWN,VWE | Accel bias, wind estimate |
| XKF3 | IVN,IVE,IVD,IPN,IPE,IPD | Innovations (should be small) |
| XKF4 | SV,SP,SH,SM,SVT,FS,TS,SS | Variances, faults, timeouts |
| ATT | Roll,Pitch,Yaw,DesRoll,DesPitch,DesYaw | Attitude actual vs desired |
| CTUN | Alt,BAlt,DAlt,TAlt,CRt | Alt controller: actual, baro, desired, target, climb rate |

### Sensors
| Type | Key Fields | Notes |
|------|-----------|-------|
| BARO | Alt,Press,Temp | Barometer |
| GPS | Lat,Lng,Alt,Spd,NSats,HDop | GPS fix data |
| RFND | Dist,Stat,Orient | Rangefinder (Stat: 0=NoData, 4=Good) |
| IMU | AccX,AccY,AccZ,GyrX,GyrY,GyrZ | Raw IMU |
| MAG | MagX,MagY,MagZ | Magnetometer |

### Control
| Type | Key Fields | Notes |
|------|-----------|-------|
| RCIN | C1-C16 | RC input channels (PWM) |
| RCOU | C1-C14 | Servo/motor outputs (PWM) |
| RATE | RDes,R,ROut,PDes,P,POut,YDes,Y,YOut | PID rate controller |
| PIDR/PIDP/PIDY | Tar,Act,Err,P,I,D,FF,Dmod,SRate,Limit | PID components per axis |
| CTRL | RMSRollP,RMSRollD,RMSPitchP,RMSPitchD,RMSYaw | Controller RMS values |

### System
| Type | Key Fields | Notes |
|------|-----------|-------|
| MODE | Mode,ModeNum | Flight mode changes |
| EV | Id | Events (10=ARM, 11=DISARM, 18=LAND_COMPLETE, etc.) |
| ERR | Subsys,ECode | Errors (16=EKFCHECK, 12=CRASH_CHECK, etc.) |
| PARM | Name,Value | Parameter changes |
| BAT | Volt,Curr,CurrTot | Battery |
| POWR | Vcc,VServo | Power board |

## XKF4 Status Field Reference

- **FS (Fault Status):** Bitmask of filter faults
- **TS (Timeout Status):** Bit 0=Pos, 1=Vel, 2=Hgt, 3=Mag, 4=Airspeed, 5=Drag
- **SS (Solution Status):** NavFilterStatusBit bitmask
- **PI:** Primary core index

## Tips

- Default output limit is 5000 rows. Use `--limit 0` for all data, `--decimate N` to thin.
- The `compare` command aligns data to a 0.1s grid by default. Use `--interval 0.02` for higher resolution.
- For EKF altitude, use the `altitude` recipe which automatically negates XKF1.PD for you.
- `--condition` uses pymavlink syntax: `"MSG.Field==value"`, `"MSG.Field>value"`, supports `and`/`or`.
- Use `--sources` with both `compare` and `plot` for ad-hoc cross-message-type analysis.
- The `stats` command supports both `--sources "TYPE.Field,..."` and `--types TYPE --fields F1,F2` syntax.
- **Producing a customer-facing PDF report:** write the analysis as a markdown file with adjacent PNG plots referenced as `![](plotname.png)`, then convert with `pandoc <file>.md -o <file>.pdf --pdf-engine=xelatex -V geometry:margin=2cm -V mainfont="DejaVu Serif" -V monofont="DejaVu Sans Mono"`. The DejaVu fonts cover Unicode characters (≈, °, arrows) that the default LaTeX font misses; without them xelatex emits "Missing character" warnings and the symbols vanish from the PDF.

## Telemetry Log (.tlog) Support

The tool supports MAVLink `.tlog` files with the same commands as `.bin` files. Key differences:

- **Message names differ:** tlog uses MAVLink names (e.g., `VFR_HUD`, `GLOBAL_POSITION_INT`, `GPS_RAW_INT`, `EKF_STATUS_REPORT`, `ATTITUDE`) rather than DataFlash names (e.g., `CTUN`, `GPS`, `XKF4`, `ATT`).
- **Field names differ:** tlog uses MAVLink field names (e.g., `alt`, `climb`, `airspeed`) rather than DataFlash names (e.g., `Alt`, `CRt`, `Aspd`). Run `overview` first to see available types and fields.
- **Multiple source systems:** tlog contains messages from vehicle, GCS, and peripherals interleaved. Use `--system <id>` to filter to the vehicle only. The overview command identifies the vehicle system ID.
- **Status text:** tlog overview shows all STATUSTEXT messages with severity and timestamp — often the most useful data for crash investigation.
- **No EV/ERR messages:** tlog doesn't have DataFlash event/error messages. Use STATUSTEXT for equivalent information.
- **Recipes may not work directly:** The built-in recipes use DataFlash message/field names. For tlog, use `--sources` or `--types`/`--fields` with MAVLink names instead.

### Common tlog message types for crash investigation

```bash
# Altitude, speed, heading
python3 .claude/skills/log-analyze/log_extract.py extract <tlog> --types VFR_HUD \
    --fields alt,climb,airspeed,groundspeed,heading --system 5

# Position (lat/lon/alt)
python3 .claude/skills/log-analyze/log_extract.py extract <tlog> --types GLOBAL_POSITION_INT \
    --fields lat,lon,alt,relative_alt,vx,vy,vz --system 5

# GPS fix status
python3 .claude/skills/log-analyze/log_extract.py extract <tlog> --types GPS_RAW_INT \
    --fields fix_type,lat,lon,alt,satellites_visible --system 5

# EKF health
python3 .claude/skills/log-analyze/log_extract.py extract <tlog> --types EKF_STATUS_REPORT \
    --fields flags,velocity_variance,pos_horiz_variance,pos_vert_variance,compass_variance --system 5

# Nav controller
python3 .claude/skills/log-analyze/log_extract.py extract <tlog> --types NAV_CONTROLLER_OUTPUT \
    --fields nav_roll,nav_pitch,alt_error,aspd_error,wp_dist --system 5

# Attitude
python3 .claude/skills/log-analyze/log_extract.py extract <tlog> --types ATTITUDE \
    --fields roll,pitch,yaw --system 5

# Plot altitude with custom sources
python3 .claude/skills/log-analyze/log_extract.py plot <tlog> \
    --sources "VFR_HUD.alt,VFR_HUD.climb" --output /tmp/alt.png --system 5
```
