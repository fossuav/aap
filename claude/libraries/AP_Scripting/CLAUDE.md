# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with Lua scripts in libraries/AP_Scripting.

**Additional guidance files:**
- `CLAUDE_VEHICLE_CONTROL.md` - Movement commands, controller behavior, state/telemetry, RC input
- `CLAUDE_CRSF_MENU.md` - CRSF (Crossfire) menu implementation with helper library

## Directory Structure

- `applets/` - Complete, ready-to-use scripts with `.md` documentation files
- `drivers/` - Hardware/protocol driver scripts
- `examples/` - Demonstration scripts for learning specific features
- `tests/` - Test scripts
- `docs/` - API documentation including `docs.lua` (the API source of truth)
- `modules/` - Reusable Lua modules:
  - `crsf_helper.lua` - CRSF menu abstraction (see `CLAUDE_CRSF_MENU.md`)
  - `pid.lua` - PID controller implementation
  - `mavport.lua` - MAVLink port access utilities
  - `mavlink_attitude.lua` - MAVLink attitude message helpers
  - `mavlink_wrappers.lua` - MAVLink message wrapper utilities
  - `NMEA_2000.lua` - NMEA 2000 protocol support

## API Reference

**The `docs/docs.lua` file is the absolute source of truth for all ArduPilot Lua API function signatures.** Never invent functions or assume API patterns. When uncertain, check `docs.lua`.

## Using Modules

Modules from `modules/` can be loaded with `require()`:
```lua
local pid = require('pid')
local controller = pid.new(1.0, 0.1, 0.01, 0.0, 100.0)  -- kP, kI, kD, min, max
local output = controller:run(target, actual, dt)
```

Modules are loaded from ROMFS and can be used across multiple scripts.

## Script Types and Structure

### Applets (Default Output)

Applets are complete, production-ready scripts. Every applet requires:
1. A `.lua` script file
2. A corresponding `.md` documentation file

**Required Applet Structure:**
```lua
-- Header comment describing the applet's purpose

local PARAM_TABLE_KEY = 101  -- Unique key (1-200, check existing scripts)
local PARAM_TABLE_PREFIX = "MYAPP_"
assert(param:add_table(PARAM_TABLE_KEY, PARAM_TABLE_PREFIX, 2), "Could not add param table")

-- Parameter binding helpers
local function bind_param(name)
   local p = Parameter()
   assert(p:init(name), string.format('could not find %s parameter', name))
   return p
end

local function bind_add_param(name, idx, default_value)
   assert(param:add_param(PARAM_TABLE_KEY, idx, name, default_value), string.format('could not add param %s', name))
   return bind_param(PARAM_TABLE_PREFIX .. name)
end

-- MAV_SEVERITY enum (mandatory for gcs:send_text)
local MAV_SEVERITY = {
    EMERGENCY = 0, ALERT = 1, CRITICAL = 2, ERROR = 3,
    WARNING = 4, NOTICE = 5, INFO = 6, DEBUG = 7
}

--[[
  // @Param: MYAPP_ENABLE
  // @DisplayName: My App Enable
  // @Description: Enables or disables the applet.
  // @Values: 0:Disabled,1:Enabled
  // @User: Standard
--]]
local MYAPP_ENABLE = bind_add_param("ENABLE", 1, 0)

-- RC activation (use aux function 300-307 for Scripting1-8)
local SCRIPTING_AUX_FUNC = 300

local function update()
    if MYAPP_ENABLE:get() == 0 then
        return update, 1000
    end

    local switch_pos = rc:get_aux_cached(SCRIPTING_AUX_FUNC)
    -- 0=low, 1=middle, 2=high

    -- Main logic here

    return update, 100
end

local function protected_wrapper()
    local success, err = pcall(update)
    if not success then
        gcs:send_text(MAV_SEVERITY.ERROR, "Internal Error: " .. err)
        return protected_wrapper, 1000
    end
    return protected_wrapper, 100
end

return protected_wrapper()
```

### Examples and Tests

Simpler structure, may omit headers, pcall wrappers, and documentation.

## Code Constraints

### Lua Version and Environment

- **Lua 5.3** compatibility required
- Scripts run in **isolated sandboxes** - no shared state between scripts
- **No threads** - single-threaded execution
- **Non-blocking** - each update() must complete within milliseconds
- Coordination between scripts must go through C++ API

### Required Patterns

**Update Loop:** Scripts must reschedule themselves:
```lua
local function update()
    -- logic
    return update, 100  -- reschedule in 100ms
end
return update()
```

**Protected Calls:** Applets must use pcall wrapper for error handling.

**Initial Condition Checks:** Use assert() for preconditions:
```lua
local my_param = assert(param:get('MYAPL_ENABLE'), 'MYAPL_ENABLE not set')
```

**Time Conversion:** `millis()` and `micros()` return userdata, not numbers:
```lua
-- Correct:
local time_ms = millis():tofloat()
-- Wrong:
local time_ms = tonumber(millis())
```

### Parameter System

**Unique Table Keys:** Do not reuse these reserved keys:
- 7-16, 31, 36-49, 52, 70-76, 78-93, 102, 104, 106, 108-111, 117, 123, 136, 138-139, 142, 170-176, 193
- Check `applets/` and `drivers/` for current usage before choosing a key.

**Naming Rules:**
- Prefix: short uppercase string without trailing underscore (e.g., `MYAPL`)
- Full parameter name = `PREFIX_NAME` (e.g., `MYAPL_ENABLE`)
- Total length must not exceed 16 characters

**Parameter Documentation:** Every parameter needs a documentation block:
```lua
--[[
  // @Param: MYAPP_SPEED
  // @DisplayName: Speed Setting
  // @Description: Target speed for maneuver.
  // @Units: m/s
  // @Range: 1 50
  // @User: Standard
--]]
local MYAPP_SPEED = bind_add_param('SPEED', 2, 10)
```

### Applet Requirements

1. **All configurable values must be parameters** - no hardcoded tuning values
2. **RC switch activation by default** using `rc:get_aux_cached(SCRIPTING_AUX_FUNC)`
3. **GCS feedback** via `gcs:send_text()` for state changes
4. **Use enums** instead of magic numbers

## Custom Flight Mode Pattern

For scripts implementing new flight modes:

```lua
local MODE_NUM = 100  -- Custom mode number
local g_cruise_mode_state = nil
local g_last_mode_number = nil
local g_state = {}

local function script_init()
    g_cruise_mode_state = assert(vehicle:register_custom_mode(MODE_NUM, "NAME", "SHORT"), "Failed to register")
    g_state.mode_id = MODE_NUM
end

local function allow_enter_function()
    return arming:is_armed() and ahrs:healthy()
end

local function mode_init()
    gcs:send_text(MAV_SEVERITY.INFO, "Custom Mode: ACTIVATED")
end

local function mode_run()
    -- Core control logic
end

local function mode_exit()
    gcs:send_text(MAV_SEVERITY.INFO, "Custom Mode: Deactivated")
end

local function update()
    g_cruise_mode_state:allow_entry(allow_enter_function())
    local mode = vehicle:get_mode()

    if mode == g_state.mode_id and g_last_mode_number ~= g_state.mode_id then
        mode_init()
    elseif mode == g_state.mode_id then
        mode_run()
    elseif g_last_mode_number == g_state.mode_id then
        mode_exit()
    end

    g_last_mode_number = mode
    return update, 20
end

script_init()
return update()
```

## Shared Resource Handling

When multiple scripts access shared C++ resources (event queues, hardware):
1. Use non-destructive `peek` to check resource state
2. Verify if the resource/event belongs to current script
3. If yes, process and `pop` to consume
4. If no, yield quickly to allow other scripts to process

## Safety Constraints

- Check flight mode before executing position/movement commands
- Always verify `arming:is_armed()` before motor-related commands
- Never interfere with failsafe mechanisms
- Pilot RC input has highest priority - relinquish control on stick input
- Restore modified parameters when script completes

## Code Quality

- **luacheck compliant** - no errors or warnings
- **No trailing whitespace**
- **Comments explain "why"** not "what" - no changelog-style comments
- **Function comments** for every function declaration

## Surgical Modification

When modifying existing scripts:
- Limit changes to the explicit request scope
- No unrelated reformatting, renaming, or refactoring
- Preserve existing code style and structure
- Smallest possible diff

## Testing

### SITL Autotest Structure

Tests are added as methods to vehicle test suites in `Tools/autotest/` (e.g., `arducopter.py`).

```python
def test_my_applet(self):
    '''Tests my_applet.lua'''
    with self.install_applet_script_context("my_applet.lua"):
        # Stage 1: Enable scripting
        self.set_parameters({"SCR_ENABLE": 1})
        self.reboot_sitl()

        # Stage 2: Configure script parameters
        self.set_parameters({
            "MYAPL_ENABLE": 1,
            "RC9_OPTION": 300,
        })
        self.reboot_sitl()

        # Test logic
        self.wait_ready_to_arm()
        self.arm_vehicle()
        self.change_mode("LOITER")
        self.user_takeoff(alt_min=20)

        self.context_collect('STATUSTEXT')
        self.set_rc(9, 2000)  # Trigger script
        self.wait_statustext("Expected message", check_context=True, timeout=10)

        self.disarm_vehicle()
```

## Commit Conventions

- **Atomic commits** - one logical change per commit
- **Prefix format:**
  - Script changes: `AP_Scripting: Add terrain brake applet`
  - Autotest changes: `Tools: Add autotest for terrain brake applet`

## Deliverable Checklist

For complete applet delivery:

1. **Lua Script (.lua)**
   - Header comment describing purpose
   - Precondition assert() checks
   - GCS feedback for state changes
   - luacheck compliant

2. **Documentation (.md)**
   - Purpose explanation
   - All parameters documented
   - Setup instructions including RCx_OPTION

3. **Autotest Offer**
   - Offer to generate SITL autotest
   - Test added to appropriate vehicle test suite
