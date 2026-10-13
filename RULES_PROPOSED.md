# Proposed architectural rules

Candidates for the playbooks, waiting for the user to confirm, edit or
reject them. This file is never installed: nothing here is a standard, and
no review holds a change against it. The process is in the root playbook,
"Subsystem Playbooks", under "Architectural rules".

- A **confirmed** rule moves to the playbook for the code it constrains,
  with the date and who holds it, and the playbook version is bumped.
- A **rejected** rule moves to "Rejected" below with the user's reason, so
  the next session does not propose it again.
- A rule that holds only on a fork's own branches goes in that fork's
  repository, not here.

## Format

```
### ARCH-n: <the rule as a claim, one line>
Rule:   What code must do or must not assume.
Why:    The failure it prevents: the incident, PR or maintainer comment,
        with the numbers.
Scope:  Vehicles, libraries, branches.
Check:  What a reviewer greps, runs or asks to see it is kept.
Holder: Whose rule it is - the user, or a maintainer with a link to where
        they said it.
Status: proposed <date>
```

## Proposed

### ARCH-1: A change to what a shared signal means names every reader of it

Rule:   A PR that changes when a shared flag or predicate is true (a
        failsafe flag, `position_ok()`, `land_complete`, an EKF status
        bit) lists every reader of it in the description and says, for
        each, why the new meaning is still safe there.
Why:    #32514 made Copter's EKF failsafe clear without a position on a
        source set with no horizontal source. #34696, written against the
        old meaning, restored Loiter when the failsafe cleared. Neither PR
        was wrong alone; a branch carrying both had the restore refused in
        6 of 13 failsafes on a flown flow quad (2026-10-13), fixed in
        #34696's `0a4ae24f1e` (`../ardupilot-pr-analysis/34696/`).
Scope:  All vehicles and libraries.
Check:  For each signal whose meaning the diff changes, grep its readers;
        the description names them.
Holder: the user (pending)
Status: proposed 2026-10-13

## Rejected

None yet.
