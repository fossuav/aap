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

Second batch (2026-10-16). ARCH-11 to ARCH-16 are the architecture themes
of the 2026-10-14 mining not used in the first batch, with the ones the
playbooks already cover left out (control and filter changes need evidence,
EKF changes need scrutiny, hwdef and scripting conventions, which belong to
their own playbooks). ARCH-17 and ARCH-18 come from this week's PR work.
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
Status:  proposed 2026-10-16

### ARCH-12: Memory is paid for only where it is used

An optional feature allocates its state at init or on first use, only when
the hardware or the feature is actually present, and never in a flight
path. Every allocation is checked: a failure is reported rather than
skipped in silence, and every path that uses the object copes with it
being absent. What an option stops using is freed and its pointer cleared,
and large buffers stay out of BSS, which on some boards shares a full first
memory block with the vehicle objects.

Example: tridge on #13923 (an object paid for on every board when there was
         no UART) and #11795 (what happens if this allocation fails?);
         peterbarker on #31521 (report the failure rather than rumble on).
Check:   for each new allocation - when it happens, what limits it to when
         it is needed, what happens when it fails, and what frees it.
Seen in: 15 PRs, tridge foremost, with peterbarker and rmackay9.
Status:  proposed 2026-10-16

### ARCH-13: A driver change holds for every variant and failure the driver can meet

A driver serves a family of chips and meets lost devices, bus glitches and
timeouts. A change is checked against the datasheet of every variant the
driver supports, takes the timeout path first so a lost sensor always
reaches no-data, does not trust a single sample, and behaves like its
sibling backends (pass on what the sensor reported; flag every kind of new
data). A risky change is limited to the variant that needs it.

Example: peterbarker on #28983 (an SPL06 change would write the wrong
         configuration into the SPA06) and #31155 (handle the timeout first,
         and behave like every other rangefinder backend); tridge on #32399
         (checked against all v3 variants' datasheets?).
Check:   the variants the driver supports and how each is covered; what the
         change does when the device stops answering; what the sibling
         backends do in the same case.
Seen in: 11 PRs, peterbarker, rmackay9, tridge.
Status:  proposed 2026-10-16

### ARCH-14: Do not add code before it is used, and remove what your change leaves unused

Code that nothing calls costs flash and review time, and rots. A PR adds
methods, members and options only when something uses them, and when its
new mechanism replaces an old one it removes the old one in the same PR.
This is what "required by the change" means in the Surgical Modification
Principle: what the change orphans goes with it, while dead code the change
did not touch is a separate PR.

Example: rmackay9 on #11795 ("a golden rule in AP that we don't add things
         before they are used") and #32396 (an unused method); peterbarker
         on #31919 (why keep any of the old calibration code?).
Check:   every new symbol has a caller in the PR; every symbol the PR stops
         calling is removed or has a caller elsewhere.
Seen in: 11 PRs, all four reviewers.
Status:  proposed 2026-10-16. If confirmed, the Surgical Modification
         Principle's "Never remove existing code ... unless directly
         required by the change" gets a pointer to it.

### ARCH-15: internal_error is for the impossible, not the unexpected

INTERNAL_ERROR marks a state the code believes cannot happen - "land now,
do not fly again until the bug is fixed" - so it reaches the logs and
watchdog dumps even without asserts, rather than the code crashing or
quietly misbehaving. Bad external input, protocol drift and harmless misuse
are handled, not raised, and a non-critical fault at startup is recorded
rather than leaving the board unbootable.

Example: peterbarker on #24196 (internal errors are for land-now conditions,
         not unrecognised input); tridge on #28828 (cork, cork, push is not
         dangerous) and #17029 (do not panic at startup).
Check:   for each new internal error - can anything outside the code (a
         sensor, a GCS, a parameter) cause it? Then it is input handling.
Seen in: 6 PRs, peterbarker and tridge.
Status:  proposed 2026-10-16

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

### ARCH-17: Behaviour that cannot apply to a vehicle type is compiled out of that build

Shared code does not branch at run time on which vehicle it runs in;
vehicle differences arrive through generic signals the vehicle sets. Where
a feature cannot apply to a vehicle type at all - a landing floor on a
Rover, which never lands - it is compiled out of that vehicle's build
(APM_BUILD_TYPE), as the EKF's FLOW_HGT_OVR range override already is.
Replay is its own build, so the PR says what Replay of that vehicle's logs
then does. The alternative, a runtime vehicle-class test, keeps Replay
faithful but puts vehicle knowledge into the library.

Example: #34292 (2026-10-16): a flow Rover fused zero flow while driving,
         because the landing floor read its range at the ground clearance as
         resting. Compiled out of Rover; AP-Review had proposed a runtime
         class test and cited assume_zero_sideslip() as precedent.
Check:   a new vehicle-type condition is APM_BUILD_TYPE, not
         get_vehicle_class(), and the PR says what Replay does.
Where:   refines the EKF3 playbook's "No vehicle-specific code in the EKF"
         and the root's "In the EKF that cannot be a vehicle-class test".
Status:  proposed 2026-10-16

### ARCH-18: Know which threads call a function before giving it state

A function reached from a driver's callback runs on that driver's bus
thread, alongside the main loop: writeOptFlowMeas() does for PX4Flow.
Before adding state that such a path reads and writes, list the threads
that can reach it; protect what they share (WITH_SEMAPHORE), or at least
order the stores so another thread never pairs a new flag with an old
value, and say which was done.

Example: #33484 (2026-10-16): the flow latch release read a run start that a
         PX4Flow sample on another core could pair with a newly set latch.
         AP-Review found it; a Codex read showed its first fix, clearing
         the start on disarm, did not close it, and ordering the stores did.
Check:   for each new member written on a sensor or MAVLink path, the
         threads that can reach it and how they are kept apart.
Where:   under ARCH-9 ("The main loop never waits"), which already says
         shared data is protected.
Status:  proposed 2026-10-16

## Confirmed

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
