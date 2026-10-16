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

Second batch (2026-10-16). ARCH-11, 14 and 16 are the architecture themes
of the 2026-10-14 mining not used in the first batch, with the ones the
playbooks already cover left out (control and filter changes need evidence,
EKF changes need scrutiny, hwdef and scripting conventions, which belong to
their own playbooks). ARCH-17 and ARCH-18 come from this week's PR work, and ARCH-19 (confirmed)
from the user.
"Seen in" counts distinct PRs in the mining.

### ARCH-11: A pre-arm check catches what would silently go wrong, says exactly what, and changes nothing

A configuration that would misbehave without telling anyone - a failsafe
whose data source is missing, an output used by two functions - fails
pre-arm, in the library that owns the setting, with a message that names
the cause rather than "unhealthy". The check asks what the vehicle actually
uses (the AHRS's sources, not whether a GPS is configured), so it never
locks out a vehicle that has no such sensor, and it only reads: anything
that must happen at arming belongs in arm(). A setting that is merely
unusual is not a pre-arm failure; each check costs flash and support time
and needs evidence that it catches something real.

Example: tridge on #20856 (fail arming when the RPM failsafe's ESC telemetry
         is missing); rmackay9 and peterbarker on #31177 (ask the AHRS
         whether GPS is in use; the state change belongs in arm()); lthall
         on #27068 (no pre-arm checks for sensible settings).
Check:   for each new check - what silently fails without it, where its
         setting lives, whether a vehicle without the sensor can still arm,
         and whether the check writes anything.
Seen in: 12 PRs, all four reviewers.
Status:  parked 2026-10-16. The user is not sure what there is good consensus
         on for pre-arm checks yet (Leonard and Tridge pull in different
         directions on checks for settings and on option bits to disable them).

### ARCH-16: Home, EKF origin and position are different things

Home is where the vehicle returns to; the EKF origin is the frame its
position is measured in; neither is where it is now. Code says which it
means (above home is home-relative, not origin-relative), does not move the
origin once a position estimate exists, does not change the altitude
reference the vehicle measures against from one flight to the next, and
allows for each vehicle setting home its own way.

Example: peterbarker on #31619 ("home is not the same as origin");
         rmackay9 on #32505 (the origin must not move once there is a
         position, which the position controller relies on) and on #32768
         (resetting the altitude above origin at arming breaks AMSL mission
         altitudes across flights).
Check:   every home or origin read or write names which it is and why;
         nothing moves the origin after the EKF has a position.
Seen in: 4 PRs, peterbarker, rmackay9, tridge.
Status:  proposed 2026-10-16. Note: #32768 is one of andyp1per's own open
         PRs, and rmackay9's comment there is one of the objections this
         rule records.

## Confirmed

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
