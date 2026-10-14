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

### ARCH-5: Safety logic is judged by what it does when it is wrong

A failsafe triggers when the vehicle loses something its current flight
depends on, and what it then does is a separate, configurable decision.
Improve an existing failsafe rather than adding an overlapping one, and
never let one feature disable or bypass another's protection. Anything
that can disarm, land or change mode in flight is designed for the case
where it fires wrongly as much as for the case where it is right.

Example: rmackay9 on #34210, improve the existing failsafe instead of
adding another
(https://github.com/ArduPilot/ardupilot/pull/34210#issuecomment-5471845867);
on #20929, landing detector false positives disarm vehicles in flight.
Check:   What does it do when its own input is wrong in flight, and does it
         remove or bypass any existing protection?
Seen in: 18 PRs (rmackay9 8, peterbarker 6, tridge 5, lthall 2)
Status:  proposed 2026-10-14 (second draft). Open: "something its current
         flight depends on" agrees with #32514, where a source set with no
         horizontal source expects no position. rmackay9 on #32514 held
         the stricter view, that the EKF failsafe should trigger without a
         good position whatever sources are in use
         (https://github.com/ArduPilot/ardupilot/pull/32514#issuecomment-4124383538);
         adopting that wording would put #32514's design against the rule.

## Confirmed

- **ARCH-3** "Lower layers detect, higher layers decide", **ARCH-6** "Do not
  break what users already have", **ARCH-7** "Prefer the simplest design
  that does the job", **ARCH-8** "Reuse before you write" and **ARCH-10**
  "Nothing from outside is trusted" - confirmed 2026-10-14 from the first
  mined batch, in the root playbook under Architectural Principles
  (1.7.38).
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

- **ARCH-5 first draft** (2026-10-14), "Safety logic fails safe, and
  stays one mechanism": needed refinement (the user); its trigger wording
  was Randy's #32514 view unscoped.
- **First drafts of ARCH-1 and SFD-1** (2026-10-13): too specific. They
  named the signals and the incident instead of the principle; SFD-1's
  title quoted a GCS message, which read as if code acted on message text.
  Rewritten as ARCH-1 and ARCH-2 above.
