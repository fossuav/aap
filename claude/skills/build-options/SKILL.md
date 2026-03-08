---
name: build-options
description: Search ArduPilot compile-time build options (feature flags). Use when the user asks about feature enables, build defines, HAL_*_ENABLED macros, or what can be compiled in/out.
argument-hint: "[search term]"
allowed-tools: Grep, Read, Bash(python3 *)
---

# Search ArduPilot Build Options

Build options are defined in `Tools/scripts/build_options.py`. There are 400+ options organized by category.

## Search

If `$ARGUMENTS` is provided, search for matching options:

```bash
python3 -c "
import sys
sys.path.insert(0, 'Tools/scripts')
from build_options import BUILD_OPTIONS
term = '$ARGUMENTS'.lower()
for opt in BUILD_OPTIONS:
    if term in opt.label.lower() or term in opt.define.lower() or term in opt.description.lower() or term in opt.category.lower():
        dep = opt.dependency or 'None'
        default = 'ON' if opt.default else 'OFF'
        print(f'{opt.category:15s} {opt.label:30s} {opt.define:40s} default={default}  deps={dep}')
        print(f'                {opt.description}')
        print()
"
```

If no arguments, list all categories and counts:

```bash
python3 -c "
import sys
sys.path.insert(0, 'Tools/scripts')
from build_options import BUILD_OPTIONS
cats = {}
for opt in BUILD_OPTIONS:
    cats[opt.category] = cats.get(opt.category, 0) + 1
for cat in sorted(cats.keys()):
    print(f'  {cat:20s} {cats[cat]:4d} options')
print(f'  {\"TOTAL\":20s} {len(BUILD_OPTIONS):4d} options')
"
```

## Each option has

| Field | Description |
|-------|-------------|
| `category` | Group (AHRS, Safety, Telemetry, Copter, Plane, etc.) |
| `label` | Unique identifier (max 30 chars), used in `--enable-<label>` |
| `define` | C++ preprocessor macro (e.g., `AP_AIRSPEED_ENABLED`) |
| `description` | Human-readable description |
| `default` | 1=enabled, 0=disabled by default |
| `dependency` | Comma-separated labels this feature depends on |

## How options are used

- **In code:** `#if AP_FEATURE_ENABLED` / `#endif` guards
- **In hwdef.dat:** `define AP_FEATURE_ENABLED 1` to force enable/disable
- **In waf configure:** `./waf configure --board sitl --enable-LABEL`
- **In custom builds:** Used by the ArduPilot custom firmware builder

## Common categories

AHRS, Safety, Telemetry, Sensors, RC, CAN, AP_Periph, Copter, Plane, Rover, Sub, Compass, GPS, Logging, Mission, Notify
