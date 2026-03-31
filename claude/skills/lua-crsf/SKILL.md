---
name: lua-crsf
description: "Write ArduPilot CRSF (Crossfire/ELRS) transmitter menu scripts using crsf_helper.lua, including defining menu structures, parameter fields, and command handlers. Use when the user asks to create or modify CRSF, Crossfire, or ELRS transmitter menus."
argument-hint: "<menu description>"
allowed-tools: Read, Grep, Glob
---

# ArduPilot CRSF Menu Scripting

## Workflow

1. **Read playbooks** — load the references below before writing any code
2. **Create menu script** — define menu table with item types from the reference below
3. **Register menu** — `return crsf_helper.register_menu(menu_definition)`
4. **Validate** — verify all callback signatures, check two-file requirement, test on SITL if available

### Required Reading
1. **CRSF playbook:** `libraries/AP_Scripting/CLAUDE_CRSF_MENU.md` — menu definition syntax, item types, command lifecycle, crsf_helper.lua library
2. **General playbook:** `libraries/AP_Scripting/CLAUDE.md` — applet structure, parameter system, code constraints
3. **API docs:** `libraries/AP_Scripting/docs/docs.lua` — verify all function signatures

## Task: $ARGUMENTS

## Quick Reference

### Required Files
Every CRSF menu needs TWO files:
1. `crsf_helper.lua` — standard helper library (already in `modules/`)
2. Your menu script — `require('crsf_helper')`, define menu table, `return crsf_helper.register_menu(menu_definition)`

### Menu Item Types
| Type | Key Properties |
|------|---------------|
| `MENU` | `name`, `items` (sub-items) |
| `NUMBER` | `name`, `callback`, `min`, `max`, `default`, `step`, `dpoint`, `unit` |
| `SELECTION` | `name`, `callback`, `options` (string list), `default` (1-based index) |
| `COMMAND` | `name`, `callback`, `info` — multi-step lifecycle (START/CONFIRM/CANCEL) |
| `INFO` | `name`, `info` (read-only display text) |

### Minimal Working Example

```lua
local crsf = require('crsf_helper')

local function on_number_change(value)
  param:set('MY_PARAM', value)
end

local function on_command(action)
  if action == crsf.START then
    return crsf.CONFIRMED, "Done"
  end
  return crsf.IDLE, ""
end

local menu = {
  type = crsf.MENU, name = "My Menu", items = {
    { type = crsf.NUMBER, name = "Gain", callback = on_number_change,
      min = 0, max = 100, default = 50, step = 1, unit = "%" },
    { type = crsf.COMMAND, name = "Reset", callback = on_command, info = "Tap to reset" },
  }
}
return crsf.register_menu(menu)
```

### Critical Patterns
- **Peek-and-Yield** for multi-script coexistence — helper handles this automatically
- **Command lifecycle:** callback receives action, returns `(new_status, info_text)` — handle START, CONFIRM, and CANCEL actions
- **Delayed reboot:** schedule with timer, never call `vehicle:reboot()` in callback directly
- **GC protection:** helper's `crsf_objects` table prevents garbage collection crashes
