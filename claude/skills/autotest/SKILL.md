---
name: autotest
description: Run ArduPilot SITL autotests (integration/behavior tests) and inspect their results. Use when the user asks to run autotests, vehicle tests, specific test methods, or to examine why an autotest failed.
argument-hint: "<vehicle> [test_name]"
disable-model-invocation: true
allowed-tools: Bash(python3 *autotest*), Bash(python3 *autotest_results.py*), Bash(./waf *), Read, Grep
---

# Run ArduPilot Autotests

Autotests are Python-based integration tests that run vehicles in SITL simulation.

## Argument parsing

Parse `$ARGUMENTS` for vehicle and optional test name:
- `/autotest Copter` — build and run all Copter tests
- `/autotest Copter AltHold` — run specific Copter test
- `/autotest Plane QuadPlane` — run specific Plane test
- `/autotest --list Copter` — list available Copter tests

## Workflow

### Step 1: Build the vehicle first

**Always build separately using `/build` or `./waf` — do NOT use `build.<Vehicle>` in autotest.py:**

```bash
./waf configure --board sitl    # if not already configured
./waf copter                    # or plane, rover, sub, etc.
```

### Step 2: List available tests (optional)

```bash
python3 Tools/autotest/autotest.py --list-subtests-for-vehicle=<Vehicle>
```

Vehicle names: `Copter`, `Plane`, `Rover`, `Sub`, `Tracker`, `Helicopter`, `QuadPlane`, `BalanceBot`, `Sailboat`, `Blimp`

### Step 3: Run tests

```bash
# Run all tests for a vehicle
python3 Tools/autotest/autotest.py test.<Vehicle>

# Run a specific test method
python3 Tools/autotest/autotest.py test.<Vehicle>.<TestMethod>
```

### Useful options

```bash
# Show test timing info
python3 Tools/autotest/autotest.py --show-test-timings test.Copter.AltHold

# Run with debug build (build with --debug first via /build)
python3 Tools/autotest/autotest.py --debug test.Copter.AltHold
```

### Bounding a run that might hang

Use the runner script - it wraps `autotest.py` with a wall-clock timeout, streams
output, warns about a held lock, and isolates the run from other clones, all
under one pre-authorized script (so we grant the script, not a blanket
`timeout`/`python3`):

```bash
python3 .claude/skills/autotest/run_autotest.py test.Copter.<Test>
python3 .claude/skills/autotest/run_autotest.py --timeout 1200 test.Plane.QuadPlane
```

It exits 124 on timeout and kills the SITL children. Build first with `/build`.

### Running alongside another clone

The runner gives each clone its own `BUILDLOGS` (so its own harness lock and
its own log files) and one of four port slots, held for the life of the run.
Two clones can therefore run autotests at the same time; a third and fourth
can too, and the fifth is refused with exit 125 naming what holds each slot.
It prints the log directory and port range it chose - quote those when
reporting, since they are no longer the same for every clone.

Slot 0 is SITL instance 0, so a lone run uses exactly the ports it always did.
`--slot N` pins a slot, `--buildlogs DIR` overrides the log tree, and
`--no-isolate` restores the old shared-`../buildlogs` behaviour.

Moving the ports needs `autotest.py --sitl-instance`. A checkout without it
still gets its own log tree and lock, but has to use the default ports, so the
runner says so and pins the run to slot 0 - two such checkouts still wait for
each other.

Two caveats. A handful of tests bind literal ports the offset does not reach
(Rover `NetworkingWebServer` and `ManyMAVLinkConnections`, Copter
`MountTopotekNetwork` and `PeriphMultiUARTTunnel`'s MAVLink multicast bus,
`TestLogDownloadMAVProxyNetwork`, `TestLogDownloadMAVProxyCAN`, `IBus`). They
run at any instance but share those ports, so run them one clone at a time. And
concurrent runs compete for CPU: on a starved host SITL's sim clock crawls and
tests fail on wallclock timeouts that say nothing about the code.

Do NOT reach for `&` + `pkill`, `nohup`, launching `build/sitl/bin/arducopter`
directly, or an env-var prefix like `PYTHONUNBUFFERED=1 python3 ...`. They are the
wrong tools (drive SITL through `autotest.py` / `sim_vehicle.py`), and the env
prefix also changes the command's first token so it no longer matches the
pre-authorized script and prompts needlessly. If a previous run left a live lock,
clear the wedged process (with the user's ok) - don't work around it by hand.
Inspect results with `autotest_results.py` (below), not `tail`/`grep` over the logs.

## Test file locations

| Vehicle | Test file |
|---------|-----------|
| Copter | `Tools/autotest/arducopter.py` |
| Plane | `Tools/autotest/arduplane.py` |
| Rover | `Tools/autotest/rover.py` |
| Sub | `Tools/autotest/ardusub.py` |
| Helicopter | `Tools/autotest/helicopter.py` |
| Tracker | `Tools/autotest/antennatracker.py` |

## Report results

Use the `autotest_results.py` helper at `.claude/skills/autotest/autotest_results.py` to inspect results — do **not** grep / tail / head per-test files by hand. The helper parses the per-test buildlogs into structured output.

```bash
# Pass/fail summary across all tests in buildlogs
python3 .claude/skills/autotest/autotest_results.py summary

# Filter by vehicle
python3 .claude/skills/autotest/autotest_results.py summary --vehicle ArduCopter

# Show every failing test with reason + exception block
python3 .claude/skills/autotest/autotest_results.py failures

# Full failure context for one test (last N lines + exception)
python3 .claude/skills/autotest/autotest_results.py failure AltHold --lines 150

# List .BIN / .tlog logs produced by the run (feed these into /log-analyze)
python3 .claude/skills/autotest/autotest_results.py logs
```

Default `--buildlogs` is `$BUILDLOGS`, else this clone's own log tree - the same one `run_autotest.py` points the harness at. Override with `--buildlogs <dir>` if needed.

When reporting back to the user:

- Lead with the pass/fail counts.
- Quote the failure reason and exception line for each failing test (from `failures`).
- Mention any `.BIN` / `.tlog` logs available for further analysis with `/log-analyze`.
- Don't paste hundreds of lines of raw test output — extract the relevant signal.

## Common failure patterns

- **Timeout waiting for message** — vehicle didn't reach expected state in time
- **Altitude/position check failed** — vehicle didn't hit waypoint or target
- **Mode change rejected** — arming checks or pre-conditions not met
- **Build failure** — fix build first before running tests
