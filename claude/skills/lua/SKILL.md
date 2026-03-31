---
name: lua
description: "Write or modify ArduPilot Lua applets for AP_Scripting, including binding parameters, registering update callbacks, and interacting with vehicle state and MAVLink messages. Use when the user asks to create, debug, or modify Lua scripts, .lua applets, or AP_Scripting code."
argument-hint: "<topic or task description>"
allowed-tools: Read, Grep, Glob
---

# ArduPilot Lua Scripting

## Workflow

1. **Read playbook and API docs** — load references below before writing code
2. **Check PARAM_TABLE_KEY** — grep existing scripts to ensure uniqueness: `Grep pattern: "PARAM_TABLE_KEY" glob: "*.lua" path: libraries/AP_Scripting/applets/`
3. **Write applet** — follow required structure below
4. **Validate** — run `luacheck` on the script, verify API signatures in `docs.lua`, test in SITL

### Required Reading
1. **Playbook:** `libraries/AP_Scripting/CLAUDE.md`
2. **API docs:** `libraries/AP_Scripting/docs/docs.lua` — **absolute source of truth** for all function signatures. Never invent or assume API patterns.
3. For vehicle control: `libraries/AP_Scripting/CLAUDE_VEHICLE_CONTROL.md`
4. For CRSF menus: `libraries/AP_Scripting/CLAUDE_CRSF_MENU.md`

## Task: $ARGUMENTS

## Quick Reference

### Minimal Applet Template

```lua
-- MyApplet: brief description
-- luacheck: only allow defined globals

local PARAM_TABLE_KEY = <unique 1-200>
local PARAM_TABLE_PREFIX = "MY_"

assert(param:add_table(PARAM_TABLE_KEY, PARAM_TABLE_PREFIX, 2), "could not add param table")
assert(param:add_param(PARAM_TABLE_KEY, 1, "ENABLE", 1), "could not add ENABLE param")

local function update()
  if param:get("MY_ENABLE") == 0 then return update, 5000 end
  -- main logic here
  return update, 100
end

local function protected_wrapper()
  local success, err = pcall(update)
  if not success then
    gcs:send_text(0, "MyApplet: " .. tostring(err))
  end
  return protected_wrapper, 1000
end

return protected_wrapper, 1000
```

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
