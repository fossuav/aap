# CLAUDE_CRSF_MENU.md

This file provides guidance for Lua scripts implementing CRSF (Crossfire) menus. For general script structure, see CLAUDE.md.

## Architecture Overview

CRSF menu scripts use a **declarative, callback-driven approach** with a mandatory helper library. This abstracts the low-level binary packing/unpacking and provides safe multi-script coexistence via "Peek-and-Yield" pattern.

### Required Files

Every CRSF menu implementation requires TWO files:
1. **`crsf_helper.lua`** - Standard helper library (provided below)
2. **`my_menu.lua`** - Your menu script that `require()`s the helper

### Core Methodology

1. **Menu Definition:** Define menu structure in a declarative Lua table
2. **Initialization:** Call `helper.register_menu(menu_definition)`
3. **Menu Building:** Helper uses C++ API to build menu objects
4. **Event Handling:** Helper runs independent event loop using Peek-and-Yield pattern

### Peek-and-Yield Pattern

Multiple scripts can safely coexist:
1. Each script's event loop calls `crsf:peek_menu_event()` to view next event without removing it
2. Checks if event's `param_id` exists in its local `menu_items` table
3. If **matches**: process event, call callback, then `crsf:pop_menu_event()` to consume
4. If **no match**: immediately yield, leaving event for other scripts

## Menu Definition Syntax

### Top-Level Structure

```lua
local menu_definition = {
    name = "My Menu",      -- Root menu name on transmitter
    items = {              -- List of menu items
        -- item definitions here
    }
}
```

### Item Types and Properties

| Property | Type | Description | Used By |
|----------|------|-------------|---------|
| `type` | string | **Required.** `'MENU'`, `'NUMBER'`, `'SELECTION'`, `'COMMAND'`, `'INFO'` | All |
| `name` | string | **Required.** Display text | All |
| `callback` | function | **Required.** Handler for value changes | NUMBER, SELECTION, COMMAND |
| `items` | table | Sub-menu item definitions | MENU |
| `default` | number | Initial value. For SELECTION: 1-based index | NUMBER, SELECTION |
| `min`, `max` | number | Value range | NUMBER |
| `step` | number | Increment size (default: 1) | NUMBER |
| `dpoint` | number | Decimal places (default: 0) | NUMBER |
| `unit` | string | Unit label (e.g., "m", "s", "%") | NUMBER |
| `options` | table | List of choice strings | SELECTION |
| `info` | string | Read-only display text | INFO |

### Example Menu Definition

```lua
local crsf_helper = require('crsf_helper')

-- Callbacks receive the new value
local function on_mode_change(new_mode)
    gcs:send_text(6, "Mode: " .. new_mode)
end

local function on_speed_change(new_speed)
    gcs:send_text(6, "Speed: " .. tostring(new_speed))
end

local function on_calibrate(action)
    local STATUS = crsf_helper.CRSF_COMMAND_STATUS
    if action == STATUS.START then
        -- Begin calibration
        return STATUS.PROGRESS, "Working..."
    elseif action == STATUS.CONFIRM then
        -- Confirmed
        return STATUS.READY, "Done"
    elseif action == STATUS.CANCEL then
        return STATUS.READY, "Cancelled"
    end
    return STATUS.READY, "Execute"
end

local menu_definition = {
    name = "My Applet",
    items = {
        {
            type = 'SELECTION',
            name = "Mode",
            options = {"Off", "Low", "High"},
            default = 1,
            callback = on_mode_change
        },
        {
            type = 'NUMBER',
            name = "Speed",
            min = 0,
            max = 100,
            default = 50,
            step = 5,
            unit = "%",
            callback = on_speed_change
        },
        {
            type = 'MENU',
            name = "Advanced",
            items = {
                {
                    type = 'COMMAND',
                    name = "Calibrate",
                    info = "Execute",
                    callback = on_calibrate
                },
                {
                    type = 'INFO',
                    name = "Version",
                    info = "1.0.0"
                }
            }
        }
    }
}

return crsf_helper.register_menu(menu_definition)
```

## Command Item Lifecycle

Commands support multi-step lifecycle with status codes:

| Status | Value | Direction | Description |
|--------|-------|-----------|-------------|
| READY | 0 | feedback | Command ready to execute |
| START | 1 | input | User initiated command |
| PROGRESS | 2 | feedback | Command in progress |
| CONFIRMATION_NEEDED | 3 | feedback | Awaiting user confirmation |
| CONFIRM | 4 | input | User confirmed |
| CANCEL | 5 | input | User cancelled |
| POLL | 6 | input | Status poll request |

Command callbacks receive the action and return `(new_status, info_text)`:

```lua
local function on_command(action)
    local STATUS = crsf_helper.CRSF_COMMAND_STATUS
    if action == STATUS.START then
        start_long_operation()
        return STATUS.CONFIRMATION_NEEDED, "Confirm?"
    elseif action == STATUS.CONFIRM then
        complete_operation()
        return STATUS.READY, "Done"
    elseif action == STATUS.CANCEL then
        abort_operation()
        return STATUS.READY, "Cancelled"
    end
    return STATUS.READY, "Execute"
end
```

## The crsf_helper.lua Library

This library must be included alongside any CRSF menu script:

```lua
-- crsf_helper.lua
-- Reusable helper library for ArduPilot CRSF menus.
-- Abstracts binary packing/unpacking and event loop management.

local helper = {}

helper.MAV_SEVERITY = {INFO = 6, WARNING = 4, ERROR = 3, DEBUG = 7}
local MAV_SEVERITY = helper.MAV_SEVERITY

local CRSF_EVENT = {PARAMETER_READ = 1, PARAMETER_WRITE = 2}
local CRSF_PARAM_TYPE = {
    FLOAT = 8,
    TEXT_SELECTION = 9,
    FOLDER = 11,
    INFO = 12,
    COMMAND = 13,
}

helper.CRSF_COMMAND_STATUS = {
    READY = 0,
    START = 1,
    PROGRESS = 2,
    CONFIRMATION_NEEDED = 3,
    CONFIRM = 4,
    CANCEL = 5,
    POLL = 6
}
local CRSF_COMMAND_STATUS = helper.CRSF_COMMAND_STATUS

-- Local tables for this script's sandbox
local menu_items = {}
local crsf_objects = {}

-- Packing functions
local function create_selection_entry(name, options_table, current_idx)
    local options_str = table.concat(options_table, ";")
    local zero_based_idx = current_idx - 1
    local min_val = 0
    local max_val = #options_table - 1
    return string.pack(">BzzBBBBz", CRSF_PARAM_TYPE.TEXT_SELECTION, name, options_str, zero_based_idx, min_val, max_val, zero_based_idx, "%")
end

local function create_number_entry(name, value, min, max, default, dpoint, step, unit)
    local scale = 10^(dpoint or 0)
    local packed_value = math.floor(value * scale + 0.5)
    local packed_min = math.floor(min * scale + 0.5)
    local packed_max = math.floor(max * scale + 0.5)
    local packed_default = math.floor(default * scale + 0.5)
    local packed_step = math.floor(step * scale + 0.5)
    return string.pack(">BzllllBlz", CRSF_PARAM_TYPE.FLOAT, name, packed_value, packed_min, packed_max, packed_default, dpoint or 0, packed_step, unit or "")
end

local function create_info_entry(name, info)
    return string.pack(">Bzz", CRSF_PARAM_TYPE.INFO, name, info)
end

local function create_command_entry(name, status, info)
    status = status or CRSF_COMMAND_STATUS.READY
    info = info or "Execute"
    local timeout = 50
    return string.pack(">BzBBz", CRSF_PARAM_TYPE.COMMAND, name, status, timeout, info)
end

-- Menu parsing
local function parse_menu(menu_definition, parent_menu_obj)
    if not menu_definition.items or type(menu_definition.items) ~= "table" then
        return
    end

    for _, item_def in ipairs(menu_definition.items) do
        local param_obj = nil
        local packed_data = nil

        if item_def.type == 'MENU' then
            param_obj = parent_menu_obj:add_menu(item_def.name)
            if param_obj then
                parse_menu(item_def, param_obj)
            else
                gcs:send_text(MAV_SEVERITY.WARNING, "CRSF: Failed to create menu: " .. item_def.name)
            end

        elseif item_def.type == 'SELECTION' then
            item_def.current_idx = item_def.default
            packed_data = create_selection_entry(item_def.name, item_def.options, item_def.current_idx)
            param_obj = parent_menu_obj:add_parameter(packed_data)

        elseif item_def.type == 'NUMBER' then
            packed_data = create_number_entry(item_def.name, item_def.default, item_def.min, item_def.max, item_def.default, item_def.dpoint, item_def.step, item_def.unit)
            param_obj = parent_menu_obj:add_parameter(packed_data)

        elseif item_def.type == 'COMMAND' then
            item_def.status = CRSF_COMMAND_STATUS.READY
            item_def.info = item_def.info or "Execute"
            packed_data = create_command_entry(item_def.name, item_def.status, item_def.info)
            param_obj = parent_menu_obj:add_parameter(packed_data)

        elseif item_def.type == 'INFO' then
            packed_data = create_info_entry(item_def.name, item_def.info)
            param_obj = parent_menu_obj:add_parameter(packed_data)
        end

        if param_obj then
            table.insert(crsf_objects, param_obj)
            menu_items[param_obj:id()] = item_def
        elseif not param_obj and item_def.type ~= 'MENU' then
            gcs:send_text(MAV_SEVERITY.WARNING, "CRSF: Failed to create param: " .. item_def.name)
        end
    end
end

-- Event loop with Peek-and-Yield
local function event_loop()
    local IDLE_DELAY
    local ACTIVE_DELAY

    if arming:is_armed() then
        IDLE_DELAY = 500
        ACTIVE_DELAY = 100
    else
        IDLE_DELAY = 200
        ACTIVE_DELAY = 20
    end

    local count, param_id, payload, events = crsf:peek_menu_event()

    if count == 0 then
        return event_loop, IDLE_DELAY
    end

    local item_def = menu_items[param_id]
    if not item_def then
        return event_loop, IDLE_DELAY
    end

    crsf:pop_menu_event()

    if (events & CRSF_EVENT.PARAMETER_READ) ~= 0 then
        if item_def.type == 'SELECTION' then
            local packed_data = create_selection_entry(item_def.name, item_def.options, item_def.current_idx)
            crsf:send_write_response(packed_data)
        elseif item_def.type == 'COMMAND' then
            local packed_data = create_command_entry(item_def.name, item_def.status, item_def.info)
            crsf:send_write_response(packed_data)
        elseif item_def.type == 'INFO' then
            local packed_data = create_info_entry(item_def.name, item_def.info)
            crsf:send_write_response(packed_data)
        else
            crsf:send_response()
        end
    end

    if (events & CRSF_EVENT.PARAMETER_WRITE) ~= 0 then
        if not item_def.callback then
            return event_loop, ACTIVE_DELAY
        end

        local new_value = nil

        if item_def.type == 'SELECTION' then
            local selected_index_zero_based = string.unpack(">B", payload)
            item_def.current_idx = selected_index_zero_based + 1
            new_value = item_def.options[item_def.current_idx]
        elseif item_def.type == 'NUMBER' then
            local raw_value = string.unpack(">l", payload)
            local scale = 10^(item_def.dpoint or 0)
            new_value = raw_value / scale
        elseif item_def.type == 'COMMAND' then
            local command_action = string.unpack(">B", payload)
            if command_action == CRSF_COMMAND_STATUS.START or
               command_action == CRSF_COMMAND_STATUS.CONFIRM or
               command_action == CRSF_COMMAND_STATUS.CANCEL then
                new_value = command_action
            end
        end

        if new_value ~= nil then
            local success, ret1, ret2 = pcall(item_def.callback, new_value)

            if not success then
                gcs:send_text(MAV_SEVERITY.ERROR, "CRSF Callback Err: " .. tostring(ret1))
                if item_def.type == 'COMMAND' then
                    item_def.status = CRSF_COMMAND_STATUS.READY
                    item_def.info = "Error"
                end
            else
                if item_def.type == 'COMMAND' then
                    item_def.status = ret1 or CRSF_COMMAND_STATUS.READY
                    item_def.info = ret2 or "Execute"
                end
            end
        end

        if item_def.type == 'COMMAND' and new_value then
            local packed_data = create_command_entry(item_def.name, item_def.status, item_def.info)
            crsf:send_write_response(packed_data)
        elseif item_def.type == 'SELECTION' then
            local packed_data = create_selection_entry(item_def.name, item_def.options, item_def.current_idx)
            crsf:send_write_response(packed_data)
        end
    end

    return event_loop, ACTIVE_DELAY
end

function helper.register_menu(menu_definition)
    if not (menu_definition and menu_definition.name and menu_definition.items) then
        gcs:send_text(MAV_SEVERITY.ERROR, "CRSF: Invalid menu definition passed to helper.register_menu().")
        return
    end

    local top_level_menu_obj = crsf:add_menu(menu_definition.name)
    if top_level_menu_obj then
        parse_menu(menu_definition, top_level_menu_obj)
        gcs:send_text(MAV_SEVERITY.INFO, "CRSF: Loaded menu '" .. menu_definition.name .. "'")
    else
        gcs:send_text(MAV_SEVERITY.WARNING, "CRSF: Failed to create top-level menu for '" .. menu_definition.name .. "'")
        return
    end

    return event_loop, 2000
end

return helper
```

## Common Pitfalls

### Garbage Collection Crashes

**Problem:** CRSF objects get garbage collected, causing UI corruption or crashes.

**Solution:** The helper's `crsf_objects` table maintains references to all created objects. Never bypass this mechanism.

### Selection Reverts After Change

**Problem:** User changes selection, but it reverts to previous value.

**Cause:** Script doesn't respond to `PARAMETER_READ` requests after write.

**Solution:** Helper handles both READ and WRITE events, sending `send_write_response()` for stateful items.

### Menu Hangs / Items Don't Appear

**Causes:**
- Missing response handler for item type in PARAMETER_READ block
- Not calling `pop_menu_event()` before `send_write_response()`
- Event loop not yielding properly

**Debug:** Look for repeated PARAMETER_READ requests for same ID (retry storm).

### Watchdog Crashes

**Problem:** Script uses too much CPU time.

**Solution:** Helper uses balanced delays:
- Idle: 200ms (disarmed) / 500ms (armed)
- Active: 20ms (disarmed) / 100ms (armed)

## CRSF Protocol Notes

- **NUMBER type:** Transmitted as 32-bit signed integers with decimal point indicator
- **SELECTION type:** Options transmitted as semicolon-separated string
- **String lengths:** Keep names short for small transmitter screens

## Checklist

1. **[ ] Two Files:** Both `crsf_helper.lua` and main script present
2. **[ ] Require Helper:** Script starts with `require('crsf_helper')`
3. **[ ] Declarative Table:** Menu defined as nested Lua table
4. **[ ] Callbacks Defined:** All interactive items have callback functions
5. **[ ] Return register_menu:** Script ends with `return crsf_helper.register_menu(menu_definition)`
6. **[ ] Correct Properties:** Item types use exact property names from syntax table
7. **[ ] No Manual Event Loop:** Script does not contain `crsf:get_menu_event` loop
