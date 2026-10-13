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

### ARCH-1: Changing what a shared flag means changes every reader of it

A flag or check that several parts of the code read is an agreement between
them. A change to when it is true has to be checked against every reader,
not only the one that prompted the change, and the PR should say which
readers it checked.

Example: #32514 let Copter's EKF failsafe clear without a position; #34696
restores Loiter when it clears, and on a branch carrying both the restore
was refused.
Check:   For each shared flag or check whose meaning the diff changes, its
         readers are listed and each is accounted for.
Status:  proposed 2026-10-13

### ARCH-2: Test for what you need, not for something that usually comes with it

Code that needs a capability - a position, a healthy sensor, a link -
should test for that capability directly, not for a proxy such as a
failsafe having cleared. A proxy holds only until someone changes what it
means.

Example: #34696's restore needed a position and waited for the EKF failsafe
to clear; once the failsafe could clear without a position, the restore was
refused.
Check:   Where code acts on a proxy, ask what it actually needs and whether
         there is a direct test for it.
Status:  proposed 2026-10-13

## Rejected

- **First drafts of ARCH-1 and SFD-1** (2026-10-13): too specific. They
  named the signals and the incident instead of the principle; SFD-1's
  title quoted a GCS message, which read as if code acted on message text.
  Rewritten as ARCH-1 and ARCH-2 above.
