---
name: log-analyze
description: "Analyze ArduPilot DataFlash .bin log files or MAVLink .tlog telemetry logs: extract flight parameters, plot altitude and attitude profiles, identify error events, diagnose vibration or EKF issues, and compare sensor data. Use when the user provides a .bin or .tlog log file path or asks to analyze flight log data."
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
