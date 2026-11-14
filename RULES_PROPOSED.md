# Proposed architectural rules

Candidates for the playbooks, waiting for the user to confirm, edit or
reject them. This file is never installed: nothing here is a standard, and
no review holds a change against it. The process is in the root playbook,
"Subsystem Playbooks", under "Architectural rules".

- A **confirmed** rule moves to the playbook for the code it constrains,
  with the date, and the playbook version is bumped. Then
  `python3 rules/generate.py` writes its page under `rules/` and its row
  in the README index; it finds the rule by its
  `(ARCH-n, confirmed <date>):` marker, so keep that form. Re-run it after
  editing a confirmed rule too: `--check` reports a page that has fallen
  behind the playbook.
- A **rejected** rule moves to "Rejected" below with the user's reason, so
  the next session does not propose it again.
- A rule that holds only on a fork's own branches goes in that fork's
  repository, not here.
- Style rules are numbered STYLE-n and, once confirmed, go in the root
  playbook's Code Style section with a `(STYLE-n, confirmed <date>):`
  marker, without their example; `rules/generate.py` finds both prefixes.

## What a rule looks like

A rule is a general principle that a maintainer would agree with on reading
it, with no knowledge of the incident that exposed it. The incident is its
example, not its subject. If the rule only makes sense with the incident
attached, it is a note for the analysis record, not a rule. Keep it to the
length of the confirmed rules, 25 to 60 words; the detail of the incident
belongs in the analysis record too.

```
### ARCH-n: <the principle, in one plain sentence>

<Two or three sentences: what it asks of code, and why.>

Example: <one line - the incident or review that exposed it>
Check:   <what a reviewer looks at to see it is kept>
Status:  proposed <date>
```

## Proposed

### Logging and GCS batch (2026-11-14)

Every logging_gcs theme of the review mining, rescanned 2026-11-14. The
prefix LOG-n is a proposal; ARCH-n would do as well, since a log format is
a contract with its readers. Once confirmed they would form a "Logging and
GCS Messages" section of the root playbook. "Seen in" counts distinct PRs
in `ardupilot-pr-analysis/rules-mining/data/ranked.txt`.

### LOG-1: A log message's layout is a contract with every tool that reads it

New fields and messages go at the end, so existing logs and Replay keep
working. Names are short and stable, an encoding does not vary with
configuration, and every new message is documented. A new field or message
covers a use the existing ones do not: no near-duplicate of a message, no
value that never changes.

Example: tridge on #34292: "please add to end of list, not middle, to
         preserve existing replay logs".
Check:   where each new field or message goes, its documentation, and
         which existing message already carries the data.
Seen in: 13 PRs, all four reviewers.
Status:  proposed 2026-11-14. Extends ARCH-6's log consumers.

### LOG-2: GCS text is rare, rate-limited, and tells the user what to do

A message goes through `GCS_SEND_TEXT`, at most once per interval, and
says what to do about it. Nothing repeats while the user deliberately
holds against a limit or duplicates what the GCS already shows from
telemetry, and a condition critical enough to warn about may belong in a
pre-arm check instead.

Example: rmackay9 on #28737: "It should probably be a warning and only be
         sent at most every 30sec."
Check:   how often each new message can fire in flight, and what the user
         does on seeing it.
Seen in: 11 PRs, all four reviewers.
Status:  proposed 2026-11-14.

### LOG-3: A library logs its own data, under its own log bit

A controller or sensor library writes the messages that describe it, with
its own enable bit and rate, rather than leaving the vehicle or another
library to log it.

Example: peterbarker on #30841: "My preference would be for a logging
         interval as a parameter in the library and leave the vehicles out
         of it entirely."
Check:   which library owns the data each new message logs, and whether
         vehicle code takes part.
Seen in: 6 PRs, lthall, peterbarker, tridge.
Status:  proposed 2026-11-14. The rate is the library's, not necessarily a
         new parameter (ARCH-23).

### LOG-4: Logging costs bandwidth, and a change says how much it adds

Log bandwidth and card space do not grow. A change that adds or enlarges
messages states the increase, and logs only what is in use: nothing for
cores or lanes that are not running the feature.

Example: peterbarker on #34363: "Log bandwidth is something that doesn't
         grow."
Check:   bytes per second added at the default log settings.
Seen in: 4 PRs, peterbarker only.
Open:    could fold into LOG-1.
Status:  proposed 2026-11-14.

### LOG-5: Log time never goes backwards, and data sampled earlier says when

TimeUS is when the message was written and stays monotonic, so messages
can be compared. Data sampled at another time carries its own sample-time
field, so analysis and Replay can line it up.

Example: peterbarker on #28005: "it allowed time to go backwards in logs,
         and *that* was painful when you were trying to compare messages".
Check:   for each new message, what TimeUS means and whether the data
         needs its own sample time.
Seen in: 3 PRs, lthall, peterbarker, rmackay9.
Open:    lthall on #28005 would rather TimeUS be the time the data was
         valid; this draft keeps TimeUS monotonic and adds the sample time
         as a field, as peterbarker asked on #33585.
Status:  proposed 2026-11-14.

### LOG-6: A failure the user must act on reaches them where they will see it

A configured backend that fails to start says so rather than failing
silently. An error before the GCS is up cannot use STATUSTEXT, and one
that stops the boot looks like a bricked board, so the channel suits when
it fires. Nothing alarming is reported for a feature the user has not
configured.

Example: tridge on #20856: "need to ensure we don't log scary errors if
         the user has not configured ESC telemetry".
Check:   trigger each new error path and look at what a ground station
         user sees.
Seen in: 5 PRs, peterbarker, rmackay9, tridge.
Status:  proposed 2026-11-14. Shares ARCH-15's line on startup faults.

## Confirmed

- **ARCH-11, ARCH-20, ARCH-21, ARCH-25 and ARCH-26**, with ARCH-3a as a
  refinement of ARCH-3 - confirmed 2026-11-14 from the user, without their
  examples (1.7.69). ARCH-11 came off the shelf on its shorter wording,
  which leaves out the checks for unusual settings that lthall and tridge
  disagree on. ARCH-20, 11 and 25 are in the root playbook after ARCH-2,
  ARCH-5 and ARCH-24; ARCH-21 and 26 open the EKF3 playbook's Filter
  Rules; ARCH-3a is ARCH-3's third bullet.

- **STYLE-1 to STYLE-12**, the style batch from the review mining -
  confirmed 2026-11-14 from the user, in the root playbook's Code Style
  section before Style Verification, without their examples (1.7.67). The
  open points: members follow the file's underscore convention, and
  STYLE-7, 11 and 12 stay rules of their own. deg/s stays `_dps`, against
  the proposal: `_degs` reads as degrees (the user), and the code bears
  that out, with `yaw_rate_degs` a rate but `roll_degs` an angle. At the
  user's request STYLE-9 points to `AP_HAL::timeout_expired()` and
  `timeout_remaining()`.

- **ARCH-24** "A threshold in flight code has a reason a reviewer can
  check" - confirmed 2026-11-05 from the user, with log evidence across
  scenarios accepted as a reason, parameters last, and every surviving
  threshold a named constant, in the root playbook after ARCH-8, whose
  reuse it applies to constants (1.7.60). Prompted by peterbarker's "0.25?"
  and "0.3?" on #34457's AGL KF coast stop and floor hold.

- **ARCH-23** "A new parameter has to earn its flash, and a feature costing
  1 KB or more sits behind its own define" - confirmed 2026-11-02 from the
  user, with 1 KB on a 1 MB board as the threshold, in the root playbook
  after ARCH-4, which it extends (1.7.59). Prompted by #34543's EKF lane OSD
  items (1,036 bytes on JHEM_JHEF405 with optical flow), now behind
  `AP_OSD_EKF_LANES_ENABLED`, off upstream and on in SFD.

- **ARCH-22** "A parameter index any released build used is never given to
  another parameter" - confirmed 2026-10-31 from SFD-O4 log66, in the root
  playbook after ARCH-6, with the project conventions' `AP_GROUPINFO` line
  pointing to it (1.7.58). The fork's own fix put VALT_POS_EXPO back on its
  June index, var_info2 30, moved TKOFF_CPU_AVG/PEAK to 41/42, and marked
  29 and 31.

- **ARCH-17 refined** 2026-10-18 from the user: Replay, built as its own
  vehicle type, may follow the logged vehicle class (`dal.get_vehicle_class()`,
  compiled only under `APM_BUILD_Replay`) so that code compiled out of a
  vehicle's build replays that vehicle's logs as it ran them. Prompted by
  AP-Review on #34292: Replay built the focus floor and fused zero flow on
  Rover logs; with the Replay-only gate SITL Rover logs replay exactly (worst
  speed difference 0.000 m/s, from 0.48 m/s). The bot's suggested runtime
  class test in the vehicle build stays ruled out (1.7.48).
- **ARCH-16** "Use the weakest spatial reference the job needs, and name
  the one you use" - confirmed 2026-10-16 on its second draft (the user's
  Copter/Plane and position/location points, checked against the code),
  in the root playbook before the Coordinate System Convention (1.7.47).
  The user: #32768 works towards making the origin fully immutable; the
  altitude re-referencing the rule describes is the current behaviour.
- **ARCH-14** "Do not add code before it is used, and remove what your
  change leaves unused" - confirmed 2026-10-16, in the root playbook after
  ARCH-8, with the Surgical Modification Principle's "never remove existing
  code" line pointing to it (1.7.46). User-visible removals stay under
  ARCH-6; untouched dead code is a separate PR; a helper first used by a
  later PR belongs in it or the later PR stacks.
- **ARCH-18** "Data crosses from a driver's thread to the main loop only at
  the frontend's copy" - confirmed 2026-10-16 on its second draft (the
  user's backend/frontend point, checked against AP_Baro, AP_Compass,
  AP_InertialSensor, AP_RangeFinder, AP_Airspeed and AP_OpticalFlow), in
  the root playbook after ARCH-13 (1.7.44). PX4Flow, which breaks the
  pattern, gets its own fix PR.
  Corrected the same day (1.7.45): the confirmed text named Pixart and the
  range finders as keeping the pattern. A review of the PX4Flow fix found
  Pixart reads the AHRS gyro in its callback, PulsedLightLRF writes the
  frontend's state from its, and the compass publishes its raw field from
  the bus thread. The examples are now BMP280, VL53L1X and HereFlow, with
  those named as not following it yet.
- **ARCH-19** "New behaviour is opt-in, and lands as the last and smallest
  commits of a PR" - confirmed 2026-10-16 from the user, with the user's
  addition that a maintainer can agree to a change being on by default. In
  the root playbook after ARCH-6, with a "Structure before behaviour" line
  in Commit Conventions (1.7.43).
- **ARCH-17** "Libraries carry no vehicle-specific code; the vehicle
  moderates them" - confirmed 2026-10-16 on its second draft, in the root
  playbook under Architectural Principles after ARCH-15, with the EKF3
  playbook's "No vehicle-specific code in the EKF" and the root's
  flight-state flags line pointing to it (1.7.42).
- **ARCH-12** "Memory is paid for only where it is used", **ARCH-13** "A
  driver change holds for every variant and failure it can meet" and
  **ARCH-15** "internal_error is for the impossible, not the unexpected" -
  confirmed 2026-10-16 from the second batch: ARCH-12 as a bullet in the
  root playbook's Memory section, ARCH-13 and ARCH-15 under Architectural
  Principles after ARCH-10 (1.7.41).
- **ARCH-3** "Lower layers detect, higher layers decide", **ARCH-6** "Do not
  break what users already have", **ARCH-7** "Prefer the simplest design
  that does the job", **ARCH-8** "Reuse before you write" and **ARCH-10**
  "Nothing from outside is trusted" - confirmed 2026-10-14 from the first
  mined batch, in the root playbook under Architectural Principles
  (1.7.38).
- **ARCH-5** "Safety logic is judged by what it does when it is wrong" -
  confirmed 2026-10-14 with the second draft's wording, in the root
  playbook under Architectural Principles (1.7.39).
- **ARCH-4** "A feature costs nothing to the users who do not use it" and
  **ARCH-9** "The main loop never waits" - confirmed 2026-10-14 and merged
  into the existing "Compile-Time Dependency Analysis" and "Scheduler
  Integration" entries (1.7.38).
- **ARCH-1**, "Shared state is a contract between subsystems" - confirmed
  2026-10-13 after three drafts (the scope from the user: vehicle state is
  read directly, libraries and AP_Vehicle use accessors, the contract holds
  everywhere), in the root playbook under Architectural Principles (1.7.37).
- **ARCH-2**, "Test for what you need, not for something that usually comes
  with it" - confirmed 2026-10-13, in the root playbook under Architectural
  Principles (1.7.36).

## Rejected

- **ARCH-17, first draft** "Behaviour that cannot apply to a vehicle type
  is compiled out of that build" (2026-10-16). Too permissive about
  compiling out, and it framed the choice as compile-time against a runtime
  class test. The user: vehicle-specific code in libraries is to be avoided
  in general - it slows multi-vehicle builds, and the library may be used by
  that vehicle in future - so compiling out is only for something that makes
  no sense for the vehicle and could never be used, and only if strictly
  necessary; runtime vehicle checks in libraries are universally bad, and
  belong in vehicle code with a mechanism for the vehicle to moderate the
  library.
- **ARCH-5 with rmackay9's #32514 trigger** (2026-10-14), "the EKF
  failsafe should trigger without a good position whatever sources are in
  use": rejected by the user, who holds that this view of #32514 is not
  correct. A failsafe triggers on the loss of what the current flight
  depends on, and a source set with no horizontal source does not depend
  on a position.
- **ARCH-5 first draft** (2026-10-14), "Safety logic fails safe, and
  stays one mechanism": needed refinement (the user); its trigger wording
  was Randy's #32514 view unscoped.
- **First drafts of ARCH-1 and SFD-1** (2026-10-13): too specific. They
  named the signals and the incident instead of the principle; SFD-1's
  title quoted a GCS message, which read as if code acted on message text.
  Rewritten as ARCH-1 and ARCH-2 above.
