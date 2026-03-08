---
name: build
description: Configure and build ArduPilot firmware. Use when the user asks to compile, build, or configure for a board/vehicle.
argument-hint: "<vehicle> [--board <board>]"
disable-model-invocation: true
allowed-tools: Bash(./waf *), Read
---

# Build ArduPilot Firmware

Build the requested vehicle/target. Parse `$ARGUMENTS` for the vehicle and optional board.

## Argument parsing

Common patterns:
- `/build copter` — build ArduCopter for current board config
- `/build plane --board sitl` — configure for SITL then build Plane
- `/build copter --board CubeOrange` — configure and build for CubeOrange
- `/build sitl` — shorthand for configure sitl + build the last vehicle
- `/build check` — build and run changed unit tests
- `/build --board sitl --debug copter` — debug build

## Workflow

### Step 1: Configure (if board specified or not yet configured)

```bash
./waf configure --board <board>
```

Add `--debug` if requested.

Skip if no board specified and waf is already configured (check if `build/` exists for current board).

### Step 2: Build

Map vehicle names to waf targets:

| Argument | Command |
|----------|---------|
| `copter` | `./waf copter` |
| `plane` | `./waf plane` |
| `rover` | `./waf rover` |
| `sub` | `./waf sub` |
| `heli` | `./waf heli` |
| `tracker` | `./waf antennatracker` |
| `blimp` | `./waf blimp` |
| `periph` | `./waf AP_Periph` |
| `check` | `./waf check` |
| `check-all` | `./waf check-all` |
| `tests` | `./waf tests` |
| `clean` | `./waf clean` |

For specific targets:
```bash
./waf --targets bin/arducopter
./waf --targets tests/test_math
```

### Step 3: Report results

- Report success/failure
- Show binary size if successful
- Show first few errors if build fails
- Suggest fixes for common errors (missing dependencies, wrong board, etc.)

## Common issues

- **"The project was not configured"** — need to run `./waf configure --board <board>` first
- **Flash overflow** — binary too large for target board, need to disable features
- **Missing submodules** — run `git submodule update --init --recursive`
