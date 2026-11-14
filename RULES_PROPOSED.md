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
  marker; `rules/generate.py` learns the prefix with the first one.

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

Each waits for the user to confirm its wording; ARCH-11 is parked.

### ARCH-11: A pre-arm check catches what would silently go wrong, says what, and changes nothing

A configuration that would misbehave silently fails pre-arm, in the
library that owns the setting, with a message naming the cause. The check
asks what the vehicle actually uses, so a vehicle without the sensor can
still arm, and it only reads: anything done at arming belongs in arm().

Example: rmackay9 and peterbarker on #31177: ask the AHRS whether GPS is
         in use, and change state in arm().
Check:   what silently fails without each new check, and whether it
         writes anything.
Seen in: 12 PRs, all four reviewers.
Status:  parked 2026-10-16: no clear consensus yet; lthall and tridge
         differ on checks for settings and on option bits to disable them.

### ARCH-3a: A layer reports the structure its users configure

Callers still go through the layer (ARCH-3), but where a configuration
makes a backend's structure visible to the user, the layer reports it in
the user's terms rather than hiding it behind one generic answer.

Example: #34543's OSD shows the standby source set's estimate before a
         switch, with one EKF core per source set (`EK3_SRC_OPTIONS` bit 3).
Check:   anything backend-specific the layer exposes matches something the
         user configures, and is named in those terms.
Status:  proposed 2026-10-16 from the user's position on #34543, against
         peterbarker's on #34630: "Our abstraction is AHRS."

### ARCH-20: A flag a mode holds true must still be true when the mode ends

While a mode holds a validity flag true, the evidence the flag otherwise
needs goes stale, so the flag drops the moment the mode ends. Keep the
evidence current while the mode runs, or refresh it as the mode ends.

Example: SFD-O4 log54. `gndOffsetValid` is "ground measured within 5 s, or
         range finder is the height source"; after a low hover the
         measurement was 55 s old, and the switch to baro at touchdown
         dropped the flow lane and raised the EKF failsafe. Confirmed by
         Replay.
Check:   for each `evidence || mode` validity, what the evidence reads when
         the mode ends.
Status:  proposed 2026-10-22 from log54.

### ARCH-21: A state kept out of a filter update keeps its covariance consistent

`P = P - K*H*P` is only right for the optimal gain. Zeroing a state's gain
without a matching covariance update can leave P not positive definite,
and the filter then skips fusions in silence while reporting healthy.
Update a masked state in Joseph form, or decorrelate it before the gain is
computed.

Example: SFD TD25, #33498's flow Z gyro bias mask: EKF3 refused 222 of 225
         baro fusions and VALT climbed; a Joseph-consistent update kept
         every fusion in Replay.
Check:   for every mask on a Kalman gain, how the masked state's covariance
         is updated.
Status:  proposed 2026-10-29 from TD25.

### ARCH-25: A feed-forward term models the vehicle, not a setting that shapes the command

Each feed-forward term comes from an estimate of the vehicle, never from a
parameter that shapes the command (a speed limit, a time constant, an
expo). Whatever the two disagree by is left to an integrator, which
carries it through every transient.

Example: #33318. Loiter's drag model, built from LOIT_ANG_MAX and
         LOIT_SPEED_MS, stood for airframe drag in master's feed-forward;
         in SITL master braked early, #33318 ran 0.5 m past, and feeding
         the airframe's own drag stopped within 0.14 m.
Check:   the physical effect each feed-forward term compensates, and where
         its value comes from.
Status:  proposed 2026-11-06 from #33318.

### ARCH-26: An estimate fused into another filter is not an independent measurement

A filter's errors persist from step to step, so fusing its output every
step as if independent makes the receiving filter overconfident and shuts
out the sensors that could correct it. Fuse at the rate new information
enters, or inflate the noise for the correlation.

Example: SFD-O4 log81, #33478: fusing the AGL KF's vertical velocity every
         step cut the flow core's height std from 0.233 m to 0.084 m, the
         baro barely corrected it, and the vehicle climbed 0.5 m in 37 s;
         0.04 m with the fusion off in Replay.
Check:   whether the receiving filter's variance matches its error against
         an independent reference.
Status:  proposed 2026-11-06 from log81.

### Style batch (2026-11-14)

Every style theme from the 2026-10-14 mining, by weighted score. "Seen in"
counts distinct PRs in `ardupilot-pr-analysis/rules-mining/data/ranked.txt`.

### STYLE-1: A name says what the thing is or does

A name holds on every path, failure included. Name a boolean for the
positive condition, use the term the codebase already has for a concept,
and make siblings say how they differ. A rename is its own commit. Method
names never start with an underscore.

Example: rmackay9 on #33498: "Instead of a double negative why don't we
         rename it to yawFusedRecently()".
Check:   each new or renamed name against every path that reaches it.
Seen in: 30 PRs, all four reviewers.
Open:    underscores on members. lthall (#11795) for, rmackay9 (#32472)
         against; about a third of header members have one. Proposed:
         follow the file.
Status:  proposed 2026-11-14.

### STYLE-2: A comment stays true, and says what the code cannot

A change that makes a comment wrong fixes it. Comment what a reader cannot
recover from the code: a precondition, a sentinel return, units and allowed
values, a reserved value, a workaround someone would otherwise undo. Each
member in a header gets a short comment.

Example: peterbarker on #24064: "This deserves a comment. Otherwise we'll
         be bouncing PRs to turn this back into a bool".
Check:   every comment beside the diff still reads true after it.
Seen in: 28 PRs, all four reviewers.
Status:  proposed 2026-11-14. Adds to the playbook's Comments section.

### STYLE-3: A type fits the values it holds

Use fixed-width integers sized for every value the feature and real
hardware produce, negatives included. Pass an enum rather than a raw
integer, and write a size with `sizeof` and a named constant, not a
literal explained in a comment.

Example: tridge on #16725: "make it a float, we do have ESCs that go over
         320A, and some can go negative".
Check:   each new type against the largest and smallest value it takes.
Seen in: 17 PRs, peterbarker, rmackay9, tridge.
Open:    deg/s. The playbook says `_dps`; peterbarker (#25814) asks for
         `_degs`, and the code has 345 `_degs` to 172 `_dps`. Proposed:
         `_degs`.
Status:  proposed 2026-11-14.

### STYLE-4: A feature macro is always defined and tested with #if

A macro defined on one build path and not another gives a class a
different shape in different files. Define feature and debug macros to 0
or 1 and test them with `#if`; `#ifdef` is for compiler and platform
macros. A constant one file uses is a `static constexpr` beside its use,
not a `#define` in a shared header.

Example: peterbarker on #31521: "I've seen autopilots crash because
         something was defined in one path and wasn't defined in another".
Check:   every `#ifdef` in the diff names a compiler or platform macro.
Seen in: 11 PRs, peterbarker, tridge.
Status:  proposed 2026-11-14. `-Werror=undef` already rejects an undefined
         macro in `#if`.

### STYLE-5: A switch over an enum lists every value and has no default

Without `default:`, a new enum value fails the build (`-Werror=switch`)
wherever it is not handled. List values that need nothing as empty cases.
A value cast from a parameter or the wire can match no case, so the code
after the switch must cope (ARCH-10).

Example: peterbarker on #14257: "Adding default: means the compiler won't
         cause them pain until they conform".
Check:   no `default:` in a new switch over an enum.
Seen in: 8 PRs, peterbarker only.
Status:  proposed 2026-11-14.

### STYLE-6: Code does not spend flash on constructs that buy nothing

Bitfields and packed structs cost more flash than the RAM they save; use
them only where a wire or storage format needs the layout. No `virtual`
without an override, no destructor for an object never deleted, no error
return from a call that cannot fail.

Example: tridge on #21038: "we did this to save ram, but it costs flash,
         not worth it".
Check:   what each new bitfield, `PACKED`, `virtual`, destructor and error
         path buys.
Seen in: 9 PRs, peterbarker, rmackay9, tridge.
Status:  proposed 2026-11-14.

### STYLE-7: A member's default goes at its declaration, and a zero default not at all

ArduPilot zeroes class memory, so a zero initialiser only costs flash. A
non-zero default goes at the declaration, not in the constructor body. A
class declared on the stack is the exception.

Example: tridge on #13741: "init of vars to false (zero) just uses flash
         space for no reason".
Check:   every new member initialiser is non-zero.
Seen in: 7 PRs, peterbarker, rmackay9, tridge.
Open:    could be one line in the playbook's Memory section instead.
Status:  proposed 2026-11-14.

### STYLE-8: An interface is as narrow as its callers need

Members are private unless a caller needs them, and then it gets an
accessor. A method that changes nothing is `const`, an input that cannot be
null is a reference, and a method returns a value only if a caller can act
on it.

Example: peterbarker on #32202: "What can the caller sensibly do with this
         return value?"
Check:   which caller needs each new public member and return value.
Seen in: 6 PRs, peterbarker only.
Status:  proposed 2026-11-14.

### STYLE-9: Time is compared as time elapsed since a stored start

`now - start > period` survives the 32-bit wrap of `millis()` and
`micros()`; `start + period < now` does not. Store when something
happened, not when it should next happen.

Example: peterbarker on #31521: "adding timestamps and comparing against
         now - this is a frequent source of bugs at uint32_t wrap time".
Check:   no duration is added to a timestamp before a comparison.
Seen in: 7 PRs, peterbarker, tridge.
Status:  proposed 2026-11-14.

### STYLE-10: Guard conditions return early, one reason each

Early returns show which condition decides and how the conditions
interact; nesting hides both.

Example: peterbarker on #32393: "reformulating like this makes it quite
         clear that disabling the RPM check also disables the CPU check".
Check:   each return in new code has one reason.
Seen in: 5 PRs, lthall, peterbarker, rmackay9.
Status:  proposed 2026-11-14.

### STYLE-11: A repeated or tricky condition becomes a named predicate

A test made in more than one place, or easy to get wrong, becomes a
`const` bool method named for what it decides, so a fix lands once.

Example: peterbarker on #34209: "a bool is_xy_bias_observable() const
         {...} with this logic would probably make things clearer".
Check:   no compound condition appears twice.
Seen in: 3 PRs, peterbarker, tridge.
Open:    could fold into STYLE-10.
Status:  proposed 2026-11-14.

### STYLE-12: No default argument for a single caller, or for a choice every caller should make

A single caller can pass the value, and a choice with consequences is made
by each caller, so a new one cannot inherit it by accident.

Example: rmackay9 on #28825: "it might be safer to remove the default from
         the argument and force the caller to make a choice".
Check:   who relies on each new default argument.
Seen in: 2 PRs, peterbarker, rmackay9.
Open:    could fold into STYLE-8.
Status:  proposed 2026-11-14.

## Confirmed

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
