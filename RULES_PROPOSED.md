# Proposed architectural rules

Candidates for the playbooks, waiting for the user to confirm, edit or
reject them. This file is never installed: nothing here is a standard, and
no review holds a change against it. The process is in the root playbook,
"Subsystem Playbooks", under "Architectural rules".

- A **confirmed** rule moves to the playbook for the code it constrains,
  with the date, and the playbook version is bumped.
- A **rejected** rule moves to "Rejected" below with the user's reason, so
  the next session does not propose it again.
- A rule that holds only on a fork's own branches goes in that fork's
  repository, not here.

## What a rule looks like

A rule is a general principle that a maintainer would agree with on reading
it, with no knowledge of the incident that exposed it. The incident is its
example, not its subject. If the rule only makes sense with the incident
attached, it is a note for the analysis record, not a rule.

```
### ARCH-n: <the principle, in one plain sentence>

<Two or three sentences: what it asks of code, and why.>

Example: <one line - the incident or review that exposed it>
Check:   <what a reviewer looks at to see it is kept>
Status:  proposed <date>
```

## Proposed

The first batch mined from human review comments on andyp1per's 870
ArduPilot PRs (2026-10-14): 1000 principles extracted from rmackay9,
peterbarker, lthall and tridge (his AI-tool comments excluded), clustered,
and ranked by distinct PRs with Randy and Peter weighted highest. "Seen
in" counts distinct PRs.

### ARCH-3: Lower layers detect, higher layers decide

A library reports what it sees and the vehicle decides what to do about
it, since different vehicles need different responses. Callers go through
a layer's interface (AHRS rather than an EKF backend, AP_HAL rather than a
platform), never into its internals, and lower layers never call up.
Generic behaviour lives in a shared library, not one vehicle's directory.

Example: rmackay9 on #20856, motor failure detection belongs in AP_Motors
but the response in the vehicle
(https://github.com/ArduPilot/ardupilot/pull/20856#issuecomment-1139224611);
peterbarker on #31177, asking the EKF where its data comes from is a
layering violation
(https://github.com/ArduPilot/ardupilot/pull/31177#discussion_r2531445509).
Check:   Does the change make a library act on vehicle policy, reach past
         an interface into a backend, or put generic code in a vehicle?
Seen in: 44 PRs (peterbarker 20, tridge 14, rmackay9 13, lthall 3)
Status:  proposed 2026-10-14

### ARCH-4: A feature costs nothing to the users who do not use it

Anything not every vehicle needs has its own enable define, defaulted in
the library's config header and listed in build_options.py, is off where
flash is tight, and compiles out completely, guards around whole
functions and cases rather than inside them. The PR states the cost.

Example: peterbarker on #12810 and #30913, gate optional features behind
their own define
(https://github.com/ArduPilot/ardupilot/pull/30913#discussion_r2393816099);
on #12990, stripping features wholesale is not the way to find flash
(https://github.com/ArduPilot/ardupilot/pull/12990#issuecomment-562374010).
Check:   Build with the feature off: is the size back to master's? Does the
         PR quote the cost on a small board?
Seen in: 52 PRs (peterbarker 31, tridge 25, rmackay9 5). Extends the
         existing "Compile-Time Dependency Analysis" principle.
Status:  proposed 2026-10-14

### ARCH-5: Safety logic fails safe, and stays one mechanism

A failsafe triggers on the loss of what it protects; whether it acts is a
separate decision. Improve an existing failsafe rather than adding an
overlapping check, and never let one feature disable or bypass another's
protection. Anything that can disarm or change mode in flight is judged
by what happens when it fires wrongly.

Example: rmackay9 on #32514, the EKF failsafe should trigger without a
good position whatever sources are in use
(https://github.com/ArduPilot/ardupilot/pull/32514#issuecomment-4124383538);
on #34210, improve the existing failsafe instead of adding another
(https://github.com/ArduPilot/ardupilot/pull/34210#issuecomment-5471845867);
on #20929, landing detector false positives disarm vehicles in flight.
Check:   What does it do when its own input is wrong in flight, and does it
         remove or bypass any existing protection?
Seen in: 18 PRs (rmackay9 8, peterbarker 6, tridge 5, lthall 2)
Status:  proposed 2026-10-14

### ARCH-6: Do not break what users already have

Existing configurations, ground stations, log consumers and scripts keep
working across an update. A change to user-visible behaviour, a default
or a parameter's meaning is stated, migrated and released with notes, and
old tools stay supported until they are deprecated.

Example: peterbarker on #14299, changed log numbering broke QGC
(https://github.com/ArduPilot/ardupilot/pull/14299#pullrequestreview-406242495);
on #13272, keep support for boxes people still use.
Check:   What changes for a user who upgrades with their old parameters,
         ground station and scripts?
Seen in: 15 PRs (tridge 9, peterbarker 4, lthall 1, rmackay9 1)
Status:  proposed 2026-10-14

### ARCH-7: Prefer the simplest design that does the job

Do not add a queue, an option, a state flag or a mechanism for a small or
hypothetical gain. Use the constructs the codebase already uses, and keep
one source of truth rather than mirroring it in new state.

Example: peterbarker on #12810, does it need a queue at all
(https://github.com/ArduPilot/ardupilot/pull/12810#discussion_r352309194);
rmackay9 on #34208, an unusual construct needs a significant advantage
(https://github.com/ArduPilot/ardupilot/pull/34208#discussion_r4190252261).
Check:   For each new option, flag or mechanism: what fails without it?
Seen in: 23 PRs (rmackay9 8, tridge 8, peterbarker 7, lthall 3)
Status:  proposed 2026-10-14

### ARCH-8: Reuse before you write

Extend or factor the existing implementation, through a common base class
or shared library, rather than copying it or adding a second one.

Example: peterbarker on #31521, a common base class rather than an RC
protocol backend
(https://github.com/ArduPilot/ardupilot/pull/31521#discussion_r2590778353);
on #31918, no second implementation; on #11422, duplicated code from the
batch sampler.
Check:   Does similar code already exist that this copies or parallels?
Seen in: 21 PRs (peterbarker 10, tridge 7, lthall 3, rmackay9 2)
Status:  proposed 2026-10-14

### ARCH-9: The main loop never waits

Flight code does not block, busy-wait or sleep on the main thread: slow
or waiting work runs as a state machine across calls or on another
thread, periodic work goes in the scheduler at a rate set by its measured
cost, and data shared between threads is protected.

Example: peterbarker on #12810, delays must be asynchronous
(https://github.com/ArduPilot/ardupilot/pull/12810#discussion_r352307975);
on #31919, calibrate inside update() rather than in a blocking init.
Check:   Can any path in the change wait on a bus, a timer or another
         thread from the main loop?
Seen in: 36 PRs (tridge 23, peterbarker 10, rmackay9 3). Overlaps the
         existing "Scheduler Integration" principle.
Status:  proposed 2026-10-14

### ARCH-10: Nothing from outside is trusted

Bound every loop and buffer, check every index and length before use,
validate values from parameters, sensors and the wire, and treat an
impossible state as an internal error rather than a crash.

Example: peterbarker on #26887, never index an array from a user-set
parameter
(https://github.com/ArduPilot/ardupilot/pull/26887#discussion_r1857543241);
on #29368, check the index before writing into a payload.
Check:   Where does each index, length and loop bound in the change come
         from?
Seen in: 19 PRs (tridge 9, peterbarker 8, rmackay9 2)
Status:  proposed 2026-10-14

## Confirmed

- **ARCH-1**, "Shared state is a contract between subsystems" - confirmed
  2026-10-13 after three drafts (the scope from the user: vehicle state is
  read directly, libraries and AP_Vehicle use accessors, the contract holds
  everywhere), in the root playbook under Architectural Principles (1.7.37).
- **ARCH-2**, "Test for what you need, not for something that usually comes
  with it" - confirmed 2026-10-13, in the root playbook under Architectural
  Principles (1.7.36).

## Rejected

- **First drafts of ARCH-1 and SFD-1** (2026-10-13): too specific. They
  named the signals and the incident instead of the principle; SFD-1's
  title quoted a GCS message, which read as if code acted on message text.
  Rewritten as ARCH-1 and ARCH-2 above.
