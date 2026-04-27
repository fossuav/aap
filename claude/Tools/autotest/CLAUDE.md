# Tools/autotest playbook

This file covers conventions, patterns, and lessons learned when **authoring or iterating** ArduPilot vehicle behavior tests under `Tools/autotest/`. For test *execution*, use the `/autotest` skill.

Tests are Python scripts inheriting from `TestSuite` in `Tools/autotest/vehicle_test_suite.py`. Each vehicle has its own file (`arducopter.py`, `arduplane.py`, `rover.py`, `ardusub.py`, `helicopter.py`, `antennatracker.py`). Add new tests as methods on the appropriate test class and register them by adding the method reference to one of the `tests1a` / `tests1b` / `tests1c` / ... list-returning methods (see "Test method registration" below).

## Conventions

### Prefer event waits over arbitrary delays

Reviewer feedback (Peter Barker) is that `time.sleep(N)`, `self.delay_sim_time(N)`, and similar fixed-duration sleeps should be replaced by waiting on an actual observable event whenever one exists. Sleeps are flaky under varying SITL speedups and hide the real condition the test depends on. Look first for an event-based equivalent:

- `wait_altitude(min_m, max_m)` instead of sleeping while climbing/descending
- `wait_heading(deg)` instead of sleeping during a turn
- `wait_groundspeed(min, max)` / `wait_airspeed(min, max)` instead of sleeping while accelerating
- `wait_mode(mode)` after a mode change
- `wait_armed()` / `wait_disarmed()` after arming changes
- `wait_statustext(text, check_context=True)` for script messages, GCS notifications, EKF events
- `wait_distance_to_location(loc, min_m, max_m)` for navigation progress
- `wait_servo_channel_value(ch, value)` for output verification
- `assert_receive_message('TYPE', condition=...)` for catching a single MAVLink message (raises if none arrives in time)
- `wait_message_field_values('TYPE', {'field': value, ...})` for waiting until a MAVLink message's fields hit specific values

The full set of `wait_*` helpers lives on the `TestSuite` base class in `Tools/autotest/vehicle_test_suite.py` — grep there before adding a sleep.

**Only fall back to a fixed delay when there is genuinely no observable event** (e.g., a known sensor warm-up that emits nothing). When you do, leave a comment explaining why no event-based wait is possible — this pre-empts the obvious review comment.

**Never use `time.sleep()` directly in autotests** — use `self.delay_sim_time(N)` if a delay is unavoidable, so it scales with SITL speedup.

### Reuse helpers; avoid copy-paste

The `TestSuite` base class in `Tools/autotest/vehicle_test_suite.py` is the shared helper library for every vehicle's test suite. Before writing new test plumbing, grep `vehicle_test_suite.py` for an existing helper that does the same thing — `arm_vehicle`, `takeoff`, `fly_to_location`, `wait_*`, `set_parameters`, `context_*`, `change_mode`, etc. Reusing helpers keeps tests short, consistent, and easy for reviewers to scan.

If you find yourself copying the same multi-line setup or check sequence between tests (or between vehicles), that's a signal to factor it out into a helper instead of pasting it again. Be open to adding new helpers to `vehicle_test_suite.py` when the logic is generically useful — a new helper is justified when:

- the same logic would otherwise live in two or more tests, or
- the logic encapsulates an awkward multi-step sequence worth giving a name.

Vehicle-specific helpers (e.g. tied to a single mode in `mode_*.cpp`) belong in that vehicle's test file rather than the shared base class.

### Don't add `context_push` / `context_pop` manually

Each test method already runs inside an automatically-managed context — the framework calls `context_push()` at the start of the test and `context_pop()` at the end. **Do not** add `self.context_push()` / `self.context_pop()` calls at the top and bottom of a test body; they are redundant, clutter the diff, and will draw a review comment.

Only introduce a nested `context_push()` / `context_pop()` pair when you genuinely need to scope something mid-test that must be unwound before the rest of the test continues — e.g. parameter overrides for a single phase that should be restored before the next phase, or a temporary message subscription. When you do, pair every push with a matching pop and add a brief comment naming what the inner scope is for.

### Never run autotests in parallel

The autotest harness uses a lock file to prevent concurrent runs — launching two `autotest.py` invocations at once (or a single `test.<Vehicle>.<A>` and `test.<Vehicle>.<B>` in two shells) will fail or interfere with each other. Always run tests serially: complete one invocation before starting the next, even when iterating on multiple test methods. If you need to exercise several tests in one go, pass them as multiple arguments to a single `autotest.py` invocation rather than spawning separate processes.

### Test method registration

Each vehicle test class has several list-returning methods (`tests1a`, `tests1b`, `tests1c`, …) that the harness combines into the full test list. The split is purely for runtime balancing — there is **no** topical "tests_scripting" or per-feature list. To register a new test, append the method reference to one of these lists:

```python
def tests1c(self):
    '''return list of all tests'''
    ret = ([
        # ... existing tests ...
        self.ScriptMyNewTest,
    ])
    return ret
```

If you add a test method but forget to register it on one of the `tests1*` lists, it will silently never run. Pick a list with capacity to keep runtimes balanced; if all are saturated, add a new `tests1<letter>` method and reference it from the class's `tests()` aggregator.

### SITL speedup considerations

Tests run at high speedup (commonly ~10–100x), so time-based logic in scripts and tests completes very fast in wall-clock terms. Two consequences:

- Data collection that expects "real flight time" may get insufficient samples — relax requirements or use sample counts rather than time durations (e.g. `total_samples >= 50`).
- Use `self.delay_sim_time(N)` rather than wall-clock sleeps so timeouts scale with the speedup.

## Lua Applet Autotest Patterns

These patterns apply when writing autotests that exercise a Lua applet (typically in `Tools/autotest/arducopter.py`).

### Script installation sequence

```python
# 1. Enable scripting first
self.set_parameters({"SCR_ENABLE": 1})
self.reboot_sitl()

# 2. Install script (creates parameters on next boot)
self.install_applet_script_context('my_script.lua')
self.reboot_sitl()

# 3. Wait for script initialization message BEFORE setting script params
self.wait_statustext("Script loaded message", check_context=True, timeout=30)

# 4. NOW set script-specific parameters (they exist after the script has run)
self.set_parameters({"SCRIPT_PARAM": value})
```

Setting script-specific parameters before the script has booted and registered them will fail silently or raise.

### Context collection timing

- Call `self.context_collect('STATUSTEXT')` early in the test, **before** any reboots or actions that might generate messages you want to catch.
- You do **not** need to call `context_push()` first — the framework already did that when the test started (see "Don't add `context_push` / `context_pop` manually" above).

### Multiple test phases

When running multiple test phases, `check_context=True` matches **all** messages ever collected. For subsequent phases needing fresh messages, either:

- use `check_context=False` (waits for new messages only),
- clear context between phases, or
- use unique message strings per phase.

Timing can be tricky — a message may arrive before `wait_statustext` starts listening.

### Protected wrapper pattern (Lua side)

When using `pcall(update)` in Lua, capture **all** return values:

```lua
local success, result, interval = pcall(update)
return protected_wrapper, interval or 100  -- Don't lose the interval!
```

Dropping the interval falls back to a default and silently breaks scripts that rely on a custom rate.

### Mode transitions

Scripts that change flight modes (e.g. to `LOITER` on completion) affect subsequent test phases. Explicitly set the required mode before each test phase:

```python
self.change_mode('GUIDED')  # Ensure correct mode before next test
```

