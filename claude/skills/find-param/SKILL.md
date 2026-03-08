---
name: find-param
description: Find ArduPilot parameter definitions in C++ source code. Use when the user asks about a parameter's definition, range, units, default value, or where it's declared.
argument-hint: "<PARAM_NAME>"
allowed-tools: Grep, Glob, Read
---

# Find ArduPilot Parameter Definition

Search for the parameter `$ARGUMENTS` in the ArduPilot codebase.

## Search Strategy

### 1. Find the parameter documentation block

ArduPilot parameters have documentation blocks like:
```cpp
// @Param: RTL_ALT
// @DisplayName: RTL Altitude
// @Description: The altitude the vehicle will return at.
// @User: Standard
// @Units: cm
// @Range: 200 8000
```

Search for the `@Param:` line:

```
Grep for: @Param:\s*$ARGUMENTS
```

### 2. Find the AP_Param declaration

Parameters are declared as class members:
```cpp
AP_Int16 rtl_alt;
AP_Float alt_hold_p;
AP_Int8 some_flag;
```

The parameter table binds name to variable:
```cpp
// @Param: RTL_ALT
AP_GROUPINFO("RTL_ALT", 1, Mode, _rtl_alt, 1500),
```

Search for the `AP_GROUPINFO` or `AP_SUBGROUPINFO` line:

```
Grep for: AP_GROUPINFO.*"$ARGUMENTS"
```

### 3. Find where it's used

Search for the variable name in code to understand its effect.

## Key information to extract

When you find the parameter, report:
- **Full name** (e.g., `RTL_ALT`)
- **Display name** and **description**
- **Type** (Int8, Int16, Int32, Float)
- **Units** (cm, m, cdeg, etc.)
- **Range** or **Values** (enumeration)
- **Default value** (from AP_GROUPINFO)
- **File location** where it's defined
- **Which vehicle(s)** use it

## Common parameter table patterns

```cpp
// Simple parameter
AP_GROUPINFO("NAME", index, ClassName, member_var, default_value),

// Flags variant (e.g., read-only)
AP_GROUPINFO_FLAGS("NAME", index, ClassName, member_var, default_value, AP_PARAM_FLAG_ENABLE),

// Nested group
AP_SUBGROUPINFO(member, "PREFIX_", index, ClassName, SubClass),

// Parameter from another class
AP_SUBGROUPPTR(pointer, "PREFIX_", index, ClassName, SubClass),
```

## Parameter naming convention

- Uppercase with underscores: `RTL_ALT_MIN`
- Most important word first: `RTL_ALT` not `ALT_RTL`
- Prefixed by subsystem in parameter tables
