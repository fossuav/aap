---
name: sitl
description: Launch ArduPilot SITL simulator. Use when the user asks to start SITL, run the simulator, or test a vehicle interactively.
argument-hint: "<vehicle> [options]"
disable-model-invocation: true
allowed-tools: Bash(python3 *sim_vehicle*), Bash(./waf *), Read
---

# Launch ArduPilot SITL Simulator

Start an interactive SITL simulation session.

## Argument parsing

Parse `$ARGUMENTS` for vehicle type and options:
- `/sitl copter` — start Copter SITL
- `/sitl plane` — start Plane SITL
- `/sitl rover` — start Rover SITL
- `/sitl copter --debug` — start with GDB attached
- `/sitl copter -I 1` — second instance (different ports)

## Vehicle name mapping

| Argument | sim_vehicle.py -v value |
|----------|------------------------|
| `copter` | `ArduCopter` |
| `plane` | `ArduPlane` |
| `rover` | `Rover` |
| `sub` | `ArduSub` |
| `tracker` | `AntennaTracker` |
| `heli` | `ArduCopter` (with `--frame heli` ) |
| `blimp` | `Blimp` |

## Launch command

```bash
python3 Tools/autotest/sim_vehicle.py -v <Vehicle> [options]
```

### Common options

| Option | Purpose |
|--------|---------|
| `--debug` | Build with debug symbols and launch under GDB |
| `-I <n>` | Instance number (0-based, for multi-vehicle) |
| `--frame <frame>` | Vehicle frame (e.g., `hexa`, `octa`, `heli`, `quadplane`) |
| `-L <location>` | Start location (e.g., `CMAC`, `AVC2013`) |
| `--map` | Show map window |
| `--console` | Show console window |
| `--no-mavproxy` | Don't start MAVProxy (just the simulator) |
| `--speedup <n>` | Simulation speed multiplier |
| `-A "<args>"` | Extra arguments passed to the SITL binary |
| `--add-param-file <file>` | Load additional parameter file |

## Examples

```bash
# Basic copter SITL with map
python3 Tools/autotest/sim_vehicle.py -v ArduCopter --map --console

# QuadPlane
python3 Tools/autotest/sim_vehicle.py -v ArduPlane --frame quadplane

# Hexacopter at specific location
python3 Tools/autotest/sim_vehicle.py -v ArduCopter --frame hexa -L CMAC

# Multi-instance for swarm testing
python3 Tools/autotest/sim_vehicle.py -v ArduCopter -I 0 &
python3 Tools/autotest/sim_vehicle.py -v ArduCopter -I 1 &
```

## Notes

- SITL requires `sitl` board to be configured (`./waf configure --board sitl`)
- sim_vehicle.py handles configure and build automatically if needed
- MAVProxy connects on port 14550 (instance 0) or 14560+ (higher instances)
- SITL runs interactively — it will keep running until stopped
- Use Ctrl+C to stop, or `quit` in the MAVProxy console
