---
name: log-analyze
description: Analyze ArduPilot DataFlash .bin log files. Use when the user provides a .bin log file path or asks to analyze flight log data.
argument-hint: "<logfile.bin> [focus area]"
allowed-tools: Bash(python3 *), Read, Grep, Glob
---

# ArduPilot Log Analysis

You have a log extraction tool at `.claude/skills/log-analyze/log_extract.py` that handles common analysis tasks without writing one-off scripts.

## Standard Workflow

### Step 1: Overview (ALWAYS do this first)

```bash
python3 .claude/skills/log-analyze/log_extract.py overview <logfile>
```

This gives you: message types with counts and fields, key parameters, flight modes, arm/disarm events, and errors. Read the output carefully before proceeding.

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

### Step 3: Multi-Source Comparison

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

# Custom comparison (prefix with - to negate)
python3 .claude/skills/log-analyze/log_extract.py compare <logfile> \
    --sources "BARO.Alt,RFND.Dist,-XKF1.PD"
```

### Step 4: Plot (when visual analysis helps)

```bash
# Plot a recipe
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --recipe altitude --output /tmp/altitude.png

# Plot specific fields
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --types XKF4 --fields SV,SP,SH --output /tmp/ekf_var.png

# Time-windowed plot
python3 .claude/skills/log-analyze/log_extract.py plot <logfile> \
    --recipe altitude --from-time 10 --to-time 60 --output /tmp/takeoff.png
```

After generating a plot, read the image file to view it.

## Analysis Methodology

1. **Extract data first, theorize second.** Always run `overview` then targeted extractions before forming hypotheses.
2. **Cross-check multiple sensors.** Never trust a single source. Compare EKF estimate against raw sensors (baro, rangefinder, GPS).
3. **Check the events timeline.** ARM/DISARM, mode changes, and errors give crucial context.
4. **Filter EKF by core.** XKF* messages have a `C` field for core index. Use `--condition "XKF1.C==0"` to isolate one core.
5. **Mind the units.** XKF1 angles are in centidegrees. PD is positive-down (NED). BARO.Alt is meters above origin. RFND.Dist is meters.

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
