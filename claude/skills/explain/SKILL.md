---
name: explain
description: Explain ArduPilot code, architecture, or subsystems in context. Use when the user asks how something works, what a file does, or wants to understand a code path.
argument-hint: "<file, function, or subsystem>"
allowed-tools: Read, Grep, Glob
---

# Explain ArduPilot Code

Explain `$ARGUMENTS` in the context of ArduPilot's architecture.

## Approach

1. **Find the code** — locate the relevant files, classes, and functions
2. **Read the code** — read the actual implementation, don't guess
3. **Trace the call chain** — understand how it's invoked (scheduler, main loop, interrupt)
4. **Identify the subsystem** — where it fits in ArduPilot's architecture
5. **Explain clearly** — use plain language, reference specific line numbers

## ArduPilot architecture context

### Execution model
- Main loop runs in `AP_Vehicle::loop()` calling the scheduler
- `AP_Scheduler` runs tasks at defined rates (400Hz, 50Hz, 10Hz, 1Hz, etc.)
- Each library's `update()` is called from scheduler tasks
- SITL runs the same code path as real hardware via HAL abstraction

### Key singletons
- `AP::ahrs()` — attitude/heading (wraps EKF)
- `AP::gps()` — GPS data
- `AP::baro()` — barometer
- `AP::ins()` — inertial sensors (IMU)
- `AP::logger()` — DataFlash logging
- `AP::vehicle()` — current vehicle instance
- `gcs()` — MAVLink GCS communication

### Data flow patterns
- **Sensors → EKF → AHRS → Controllers → Actuators**
- Sensor drivers read hardware via HAL, publish to frontend
- EKF fuses sensor data into state estimate
- Vehicle mode code reads AHRS, commands controllers
- Controllers output to motors/servos via HAL

### Common patterns to explain
- **Frontend/Backend split:** Public API (frontend) delegates to driver (backend)
- **Parameter system:** `AP_Param` with `AP_GROUPINFO` tables
- **Scheduler tasks:** Registered in vehicle's `scheduler_tasks[]` array
- **MAVLink handlers:** `GCS_MAVLINK::handle_message()` dispatch
- **Flight modes:** `Mode` base class with `run()` called each loop iteration
- **Logging:** `AP_Logger::Write()` with format strings matching `LogStructure.h`

## When explaining, always

- Reference specific file paths and line numbers
- Show the actual code, don't paraphrase
- Trace the execution path from entry point
- Note any compile-time guards (`#if FEATURE_ENABLED`)
- Identify the coordinate frame (NED, body, etc.) for navigation code
- Mention relevant parameters that control behavior
