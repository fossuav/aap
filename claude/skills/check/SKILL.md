---
name: check
description: Build and run ArduPilot unit tests. Use when the user asks to run tests, check tests, or verify code changes with tests.
argument-hint: "[test_name]"
disable-model-invocation: true
allowed-tools: Bash(./waf *), Bash(./build/*), Read, Grep, Glob
---

# Run ArduPilot Unit Tests

Unit tests use Google Test framework. They require SITL board configuration.

## Workflow

### Step 1: Ensure SITL is configured

```bash
./waf configure --board sitl
```

### Step 2: Build and run tests

If `$ARGUMENTS` specifies a test name:

```bash
# Build specific test
./waf --targets tests/$ARGUMENTS

# Run it
./build/sitl/tests/$ARGUMENTS
```

If no arguments, run all changed tests:

```bash
./waf check
```

Or to run ALL tests:

```bash
./waf check-all
```

### Step 3: Report results

- Show pass/fail status for each test case
- For failures, show the assertion that failed with expected vs actual values
- Suggest relevant code locations to investigate failures

## Available tests

Tests are in `libraries/*/tests/`. Common ones:

| Test | Library | What it tests |
|------|---------|---------------|
| `test_math` | AP_Math | Vector, matrix, quaternion math |
| `test_rotation` | AP_Math | Rotation matrices and conversions |
| `test_polygon` | AP_Math | Polygon inclusion/exclusion |
| `test_euler` | AP_Math | Euler angle conversions |
| `test_filter` | Filter | Low-pass, notch filters |
| `test_bitmask` | AP_Common | Bitmask operations |
| `test_fence` | AC_Fence | Geofence logic |
| `test_mission` | AP_Mission | Mission item handling |

To list all available tests:

```bash
find libraries -name "test_*.cpp" -path "*/tests/*" | sed 's|.*/tests/||;s|\.cpp||' | sort
```

## Writing tests

Tests follow Google Test patterns:
```cpp
TEST(MathTest, VectorLength)
{
    Vector3f v(1, 0, 0);
    EXPECT_FLOAT_EQ(v.length(), 1.0f);
}
```

Test files go in `libraries/<LIB>/tests/test_<name>.cpp`.
