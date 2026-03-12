---
name: lua-crsf
description: Write ArduPilot CRSF (Crossfire) menu scripts using crsf_helper.lua. Use when the user asks to create or modify CRSF/ELRS transmitter menus.
argument-hint: "<menu description>"
allowed-tools: Read, Grep, Glob
---

# ArduPilot CRSF Menu Scripting

Before writing any CRSF menu code, read the full playbooks:

1. **Read the CRSF playbook:** `libraries/AP_Scripting/CLAUDE_CRSF_MENU.md` — complete reference for menu definition syntax, item types, command lifecycle, and the crsf_helper.lua library
2. **Read the general playbook:** `libraries/AP_Scripting/CLAUDE.md` — applet structure, parameter system, code constraints
3. **Read the API docs:** `libraries/AP_Scripting/docs/docs.lua` — verify all function signatures

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

### Critical Patterns
- **Peek-and-Yield** for multi-script coexistence — helper handles this automatically
- **Command lifecycle:** callback receives action, returns `(new_status, info_text)`
- **Delayed reboot:** schedule with timer, never call `vehicle:reboot()` in callback directly
- **GC protection:** helper's `crsf_objects` table prevents garbage collection crashes
