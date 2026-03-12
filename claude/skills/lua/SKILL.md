---
name: lua
description: Write or modify ArduPilot Lua applets. Use when the user asks to create, debug, or modify Lua scripts for AP_Scripting.
argument-hint: "<topic or task description>"
allowed-tools: Read, Grep, Glob
---

# ArduPilot Lua Scripting

Before writing or modifying any Lua code, read the full playbook and API reference:

1. **Read the playbook:** `libraries/AP_Scripting/CLAUDE.md`
2. **Read the API docs:** `libraries/AP_Scripting/docs/docs.lua` — this is the **absolute source of truth** for all function signatures. Never invent or assume API patterns.

For vehicle control tasks, also read: `libraries/AP_Scripting/CLAUDE_VEHICLE_CONTROL.md`
For CRSF menu tasks, also read: `libraries/AP_Scripting/CLAUDE_CRSF_MENU.md`

## Task: $ARGUMENTS

## Quick Reference

### Required Applet Structure
- Header comment, parameter table, `bind_param`/`bind_add_param` helpers
- `MAV_SEVERITY` enum, `ENABLE` parameter, RC activation
- `update()` function with reschedule return, `protected_wrapper()` with pcall
- Corresponding `.md` documentation file

### Key Constraints
- **Lua 5.3** — isolated sandbox, single-threaded, non-blocking
- **Always verify API** in `docs.lua` before calling any function
- `millis()` and `micros()` return userdata — use `:tofloat()` not `tonumber()`
- `Parameter()` constructor for existing params, `bind_add_param()` for script params
- Parameter names max 16 chars total (`PREFIX_NAME`)
- Unique `PARAM_TABLE_KEY` (1-200) — check existing scripts first

### Deliverables
1. `.lua` script (luacheck compliant, no trailing whitespace)
2. `.md` documentation (purpose, parameters, setup instructions)
3. Offer to generate SITL autotest
