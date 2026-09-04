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
- `assert_receive_message('TYPE', condition=...)` for catching a single MAVLink message (raises if none arrives in time) — **always prefer this to `self.mav.recv_match(...)` + a manual `if m is None` check**. The helper raises with a useful timeout message; the open-coded version is two extra lines that a reviewer (Peter) will rewrite for you.
- `wait_location(loc, minimum_duration=N)` for position-hold verification — confirms the vehicle stayed near `loc` for `N` seconds rather than a one-shot distance check after a sleep. Use this whenever a test wants to assert "the controller held station here after event X"; pair with `accuracy=` for the radius and `height_accuracy=None` if you don't care about altitude.
- `wait_message_field_values('TYPE', {'field': value, ...})` for waiting until a MAVLink message's fields hit specific values

The full set of `wait_*` helpers lives on the `TestSuite` base class in `Tools/autotest/vehicle_test_suite.py` — grep there before adding a sleep.

**Only fall back to a fixed delay when there is genuinely no observable event** (e.g., a known sensor warm-up that emits nothing). When you do, leave a comment explaining why no event-based wait is possible — this pre-empts the obvious review comment.

**Never use `time.sleep()` directly in autotests** — use `self.delay_sim_time(N, "why")` if a delay is unavoidable, so it scales with SITL speedup. The `reason` string is a required positional argument: a call without it raises `TypeError` at runtime, after SITL has booted and the test is under way, so a throwaway harness that never runs under CI fails on its first flight.

### Measuring a transient across an event

To show that an estimate is continuous across an arm, a mode change or a reset, sample it at a known rate on both sides of the event instead of reading it once afterwards. Raise the stream rate for the message you need (`self.set_message_rate_hz('LOCAL_POSITION_NED', 20)`; Copter's default is 5 Hz), capture the pre-event sample with a `condition=` so the test waits for the state it wants (`condition='LOCAL_POSITION_NED.vz > 5'` for "already falling"), fire the event, then loop for a short `get_sim_time_cached()` window collecting the min and max. Assert on the step the failure would produce (a velocity that drops toward zero, a position that jumps by the whole height) with a bound the physics of the window cannot reach on its own: a copter in free fall covers 20-30 m in a second, so a 20 m bound on position fails a correct build. `HeightDatumKeptOnMidairRearm` in `arducopter.py` is the pattern.

### Reuse helpers; avoid copy-paste

The `TestSuite` base class in `Tools/autotest/vehicle_test_suite.py` is the shared helper library for every vehicle's test suite. Before writing new test plumbing, grep `vehicle_test_suite.py` for an existing helper that does the same thing — `arm_vehicle`, `takeoff`, `fly_to_location`, `wait_*`, `set_parameters`, `context_*`, `change_mode`, etc. Reusing helpers keeps tests short, consistent, and easy for reviewers to scan.

If you find yourself copying the same multi-line setup or check sequence between tests (or between vehicles), that's a signal to factor it out into a helper instead of pasting it again. Be open to adding new helpers to `vehicle_test_suite.py` when the logic is generically useful — a new helper is justified when:

- the same logic would otherwise live in two or more tests, or
- the logic encapsulates an awkward multi-step sequence worth giving a name.

Vehicle-specific helpers (e.g. tied to a single mode in `mode_*.cpp`) belong in that vehicle's test file rather than the shared base class.

**Don't open-code the takeoff sequence on Copter.** Reviewer feedback (Peter Barker): the canonical way to get a Copter test airborne is `self.takeoff(alt, mode='GUIDED')` (defined in `arducopter.py`). That helper already handles `change_mode`, `wait_ready_to_arm`, `arm_vehicle`, `user_takeoff`, and `wait_altitude` with the right `minimum_duration`. Writing those four calls out by hand will draw a `suggestion: self.takeoff(...)` block on review. Match what surrounding tests do.

### Match the test to the code's intent, not its surface

A test must encode the **invariant the code is meant to enforce**, not just exercise the code path. Reviewer feedback (Peter Barker) flags tests that go through the motions of triggering a feature but assert the wrong property — e.g. a "guarded action" check that calls the action and confirms it ran, when the whole point of the guard is to prevent the action under certain conditions. That test would pass even if the guard were deleted.

Before writing assertions, state the rule the code enforces in one sentence (e.g. "EKF reset is allowed only when disarmed"), then build the test around proving *both halves* of that rule:

- the **allowed** case behaves as advertised (reset happened, side effects observable), and
- the **disallowed** case is refused (no side effect, or a refusal STATUSTEXT, or both).

A single-phase test that covers only the allowed case is a regression hazard: the guard can rot and the test still passes. If you cannot reach the disallowed case (e.g. it requires hardware state SITL can't reproduce), say so in the test comment so a reader knows the coverage gap is deliberate.

### A green test is not coverage

Citing an existing test as covering a path needs a trace, not a pass count. Read the test's setup for anything that steers around the branch, then confirm from the run that it went through: an EV event or STATUSTEXT the branch emits, or a log field only it writes. Three Copter traps:

- `self.set_home()` sends `DO_SET_HOME`, which the GCS handler applies with `lock=true`. Every `!ahrs.home_is_locked()` branch in the arming code is then skipped, so `RudderDisarmMidair` passed 3/3 without ever reaching the arm-time datum reset it was cited for (PR #32768). A test of the unlocked-home path must let home auto-set at the first arm and never call `set_home()`.
- Copter believes it is landed after any disarm. `disarm()` forces `land_complete` true and the land detector keeps it true while disarmed, so ALT_HOLD on a re-armed vehicle sits in `Landed_Pre_Takeoff` with the throttle relaxed until the stick asks for a climb. `hover()` after a mid-air re-arm free-falls to the ground at terminal velocity; demand a climb first (`set_rc(3, 1700)`, `wait_climbrate(0.5, 20)`) to bring the controller in, then hover.
- `GLOBAL_POSITION_INT.relative_alt` is not the EKF height. `AP_AHRS::get_relative_position_D_home()` falls back to `-AP::baro().get_altitude()` whenever the EKF vertical position is unhealthy, and an unhealthy vertical position is exactly what a height-failure test sets up, so the assertion quietly reads the raw baro instead of the estimate. The first cut of `BaroGroundEffectResetSuppression` (PR #32972) asserted on it and passed identically with the change compiled out, reading the baro through that fallback and calling it a height reset. Use `LOCAL_POSITION_NED.z`: `send_local_position()` withholds the message when `get_relative_position_NED_origin_float()` fails rather than substituting another source.

The same trace run backwards is what qualifies a *new* test: compile the guard out, re-run, and confirm the test fails. A new test that still passes without the code it was written for is measuring something else, which is how the `relative_alt` trap above was found.

### Don't add `context_push` / `context_pop` manually

Each test method already runs inside an automatically-managed context — the framework calls `context_push()` at the start of the test and `context_pop()` at the end. **Do not** add `self.context_push()` / `self.context_pop()` calls at the top and bottom of a test body; they are redundant, clutter the diff, and will draw a review comment.

Only introduce a nested `context_push()` / `context_pop()` pair when you genuinely need to scope something mid-test that must be unwound before the rest of the test continues — e.g. parameter overrides for a single phase that should be restored before the next phase, or a temporary message subscription. When you do, pair every push with a matching pop and add a brief comment naming what the inner scope is for.

### Never run autotests in parallel

The autotest harness uses a lock file to prevent concurrent runs — launching two `autotest.py` invocations at once (or a single `test.<Vehicle>.<A>` and `test.<Vehicle>.<B>` in two shells) will fail or interfere with each other. Always run tests serially: complete one invocation before starting the next, even when iterating on multiple test methods. If you need to exercise several tests in one go, pass them as multiple arguments to a single `autotest.py` invocation rather than spawning separate processes.

### The lock file is shared across sibling clones (BUILDLOGS)

The lock lives at `buildlogs_path('autotest.lck')`, which resolves to `os.getenv("BUILDLOGS", reltopdir("../buildlogs"))` (`Tools/autotest/autotest.py`). The default `../buildlogs` is **one level above the repo root**, so two sibling checkouts (e.g. `~/github/ardupilot-dist` and `~/github/smallfastdrone`) both resolve to the *same* `~/github/buildlogs/autotest.lck` and share one lock and one log output tree.

Consequences:

- A present `autotest.lck` is not necessarily stale — it may be a live lock held by an autotest running in a **different** sibling clone. Never `rm` it to "clear a stale lock" without first confirming no `autotest.py`/`arducopter` process is running (`ps aux | grep -E "autotest|arducopter"`). Deleting a live lock lets two runs collide and corrupt each other.
- To isolate a repo's autotests (own lock, own log files), set a repo-local `BUILDLOGS`, e.g. `export BUILDLOGS=$PWD/buildlogs`.
- Isolating `BUILDLOGS` removes the *lock* contention but **not** the network contention: every SITL autotest binds the same default TCP ports (5760/5762/5763), so two concurrent runs still collide with an `EOF`/connection error mid-test. The shared lock exists precisely to serialise that. Repo-local `BUILDLOGS` is for keeping logs and locks separate across clones, not for running two autotests at the same time — still run them serially, or give one a port offset.

### Host stalls look like telemetry timeouts

`NotAchievedException('Did not get GLOBAL_POSITION_INT after 1.1 seconds')` on a test unrelated to the change is usually the host, not SITL. The `assert_receive_message` timeout is wallclock; on a WSL2 VM starved by the Windows host SITL's sim clock crawls (1.8 s of sim in 66 s of wallclock on 2026-09-02) while SITL stays alive and keeps logging, and guest load average shows nothing. Before reading anything into it: copy `logs/*.BIN` aside, because the next run wipes them; confirm in the .BIN that SITL logged the harness's later disarm and reboot commands; then rerun the test alone. Two such stalls in five sessions hit different tests at different points and every test passed on rerun. Do not cite one as evidence about the change, and do not run builds alongside an autotest on that host.

### Landing at the end of a test

`land_and_disarm(timeout=N)` cannot be given a longer disarm wait. `wait_landed_and_disarmed()` spends N on its `wait_altitude` and then calls `wait_disarmed()` with no argument, so the disarm wait is always the class default. It also skips the altitude wait entirely when `GLOBAL_POSITION_INT.relative_alt` is already below `min_alt` (6 m), which is true whenever home sits above the vehicle. When a landing times out, shorten the descent rather than reaching for the timeout argument.

### Arming in the air moves home up to the vehicle

`AP_Arming_Copter::arm()` re-sets home to the current location whenever home is not locked, so a test that disarms mid-air and re-arms leaves home at flight altitude: 584 m to 721 m in `HeightDatumKeptOnMidairRearm` on 2026-09-02. Everything measured above home is then wrong for the rest of that test. `relative_alt` goes negative, and LAND reads its own height above ground as negative, so `Mode::land_run_vertical_control()` clamps the descent to `LAND_SPEED` (0.5 m/s) the whole way down instead of using the fast rate above `LAND_ALT_LOW`; a 95 m descent takes about 190 s and outlasts the disarm wait above. Fly down in GUIDED to a low absolute altitude before landing. `Location` altitudes are frame-tagged and there is deliberately no `.alt` attribute, so use `get_alt_m(AltFrame.ABSOLUTE)`; a frameless read raises rather than silently picking a frame.

### Long convergence and fixed-window assertions

`assert_dataflash_message_field_level_at` (and `delay_sim_time(N)` before a check) assert that a value is reached within a fixed window. EKF state that converges slowly — accel-bias learning via zero-velocity fusion, wind, mag — can take longer than the window, so a change that merely *slows* convergence fails such a test identically to one that *breaks* it. Before concluding "X broke Y" from a fixed-window failure, plot the actual trajectory over a longer disarmed window (a throwaway probe test that injects the stimulus and `delay_sim_time`s well past the assertion window) to tell "slower" apart from "broken". Note `wait_ready_to_arm()` itself can burn ~40 s of sim time for GPS/EKF lock, so re-zero such plots at the moment the stimulus is actually applied (e.g. the `PARM` step in the log), not at boot.

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
- Use `self.delay_sim_time(N, "why")` rather than wall-clock sleeps so timeouts scale with the speedup.

### Before/after A/B runs with a throwaway harness

When a change alters runtime behaviour, the root playbook asks for a measured A/B, not an argument. The cheapest reliable shape:

1. Build the baseline in a scratch worktree so the working tree stays on the branch: `git worktree add --detach <scratch>/base <merge-base>`, then `git submodule update --init --recursive`, `./waf configure --board sitl` and `./waf --targets bin/arducopter` in it. Copy the binary aside as `arducopter.base`.
2. Write the harness as a test method in the **worktree's** `Tools/autotest/arducopter.py`, registered on a `tests1*` list there, never in the real tree. Start from the nearest existing test for the configuration (`LoiterNoCompassYaw` for optical flow without a yaw source) and add the provocation the change keys on: a flow scale error via `FLOW_FXSCALER`/`FLOW_FYSCALER` (the SITL flow backend applies it), a real gyro bias via `SIM_GYR1_BIAS_Z` with `INS_GYR_CAL=0`, and so on. Fly a pattern with `set_rc` in Loiter long enough for slow states to move; wrap it in `try/finally` around `land_and_disarm()` so a failed run still lands and logs.
3. Run the same harness twice from the worktree, swapping `build/sitl/bin/arducopter` between the baseline and the branch binary. Set `BUILDLOGS` per run.
4. **The autotest deletes the SITL `logs/` directory at the start of every run** (`vehicle_test_suite.py` calls `shutil.rmtree` on it), so the first run's dataflash logs are gone once the second starts. Move `logs/` aside after each run; `BUILDLOGS` only holds the text transcript. The flight is the largest `.BIN` in the set; boot and reboot produce small ones.
5. Extract the compared fields with `/log-analyze` or a scratch `pymavlink` script and re-zero time at the ARM event, not at boot. Measure drift before landing: the disarm-time yaw and position resets put a step at the end of every run that swamps a "final value" metric.
6. Keep `arducopter.base`, the harness diff (`git -C <worktree> diff`) and the plots in the scratch area, then `git worktree remove --force` so the real repository is not left with a registered worktree.

A result that shows no difference is a result: it means the provocation is too weak or the mechanism is not what was claimed, and either way the PR text must not claim more than the plot shows.

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

