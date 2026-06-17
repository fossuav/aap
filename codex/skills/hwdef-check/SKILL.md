---
name: hwdef-check
description: Review an ArduPilot new-board hwdef PR. Stashes any local changes, checks the PR out as a branch in the current repo, runs DMA / board-ID / file-presence / commit-structure checks, layers the hwdef playbook on top, and (after confirmation) posts a review comment on the PR — then restores the original branch and pops the stash. Use when the user asks to review or pre-review an hwdef PR.
---

# Review an ArduPilot hwdef PR

This skill saves time on reviewing PRs that add a new ChibiOS board definition. It runs **in-place in the current ArduPilot checkout**: it stashes the user's tracked changes, checks the PR out as a temporary local branch (`hwdef-check-pr<N>`), runs the helper, lets you (the model) layer the playbook checks on top, drafts a review comment, posts it after the user confirms, and then restores the original branch and pops the stash. Using the current checkout (rather than a sibling worktree) reuses initialised submodules and build cache.

## Inputs

`$ARGUMENTS` is the PR URL (`https://github.com/ArduPilot/ardupilot/pull/12345`) or just the number (`12345`). Repository defaults to whatever `gh` picks for the current repo when the number is bare; honour any explicit owner/repo from a URL.

If `$ARGUMENTS` is empty, ask the user for the PR.

## Working directory assumption

Must be run from the root of an ArduPilot checkout (the current `.` should have `wscript` and `ArduCopter/`). The skill does **not** create a sibling worktree - everything happens here, so the current checkout's build cache and submodules apply naturally.

## Workflow

### Step 1 — Fetch PR metadata

```bash
gh pr view <PR> --repo <owner>/<repo> --json number,title,headRefName,baseRefName,url,author
```

Extract:
- `number` — the PR number (used in branch name and final comment)
- `baseRefName` — usually `master` for ArduPilot (the diff base)
- `url` — for the comment header

If the user gave just a number with no URL, omit `--repo` and let `gh` use the current repository's default. If they gave a full URL, parse `<owner>/<repo>` from it and pass `--repo`.

### Step 2 — Prepare the working tree in-place

Capture the original ardupilot checkout root before the helper changes branches:

```bash
ORIG="$PWD"
python3 .codex/skills/hwdef-check/hwdef_check.py prepare --pr <PR> [--repo <owner>/<repo>]
```

`prepare` will:

- refuse if a rebase/merge/cherry-pick/revert/bisect is in progress (the user should resolve that first);
- refuse if a previous `hwdef-check` session was not torn down (state file at `.git/hwdef-check-state.json` — instruct the user to run `restore` first);
- record the current branch (or HEAD SHA if detached) and whether the tree was dirty;
- stash *tracked* changes only (not `--include-untracked`, so the user's `.codex/` directory is left alone);
- run `gh pr checkout <PR> --branch hwdef-check-pr<PR>` to fetch the PR ref and switch to a local branch with a predictable name;
- write a sidecar `.git/hwdef-check-state.json` describing how to undo all of the above.

If `prepare` exits non-zero, stop the workflow and surface its message verbatim — it has already rolled the stash back.

### Step 3 — Run the deterministic helper

```bash
python3 .codex/skills/hwdef-check/hwdef_check.py all \
    --base "origin/<baseRefName>"
```

If the user's `origin` doesn't point at the PR's target repo (typical when `origin` is their fork and `upstream` is `ArduPilot/ardupilot`), pass `--base "upstream/<baseRefName>"` instead. Use `git remote -v` output already in the conversation to pick the right one, or check with `git rev-parse --verify upstream/<baseRefName>`.

`all` runs the full sequence:
- detects the new board(s) added in the PR
- checks required files (hwdef.dat, hwdef-bl.dat, README.md, bootloader bin+hex)
- checks `APJ_BOARD_ID` registration + uniqueness in `Tools/AP_Bootloader/board_types.txt`
- runs static hwdef.dat checks (32-bit system timer, default-vs-PWM conflict, bootloader timer match, redundant defines, SERIAL_ORDER natural order, CS/DRDY pin labels)
- runs `./waf configure --board <Board>` (slow — ~30-60s; submodules are already in place from the parent checkout)
- parses `build/<Board>/hwdef.h` for `NO DMA` and `SHARED` annotations
- checks commit structure (expects separate `AP_Bootloader:`, `bootloaders:`, `AP_HAL_ChibiOS:` commits)

Capture the helper's output verbatim — it goes into the comment under "Must-fix / Should-fix" as needed.

If `./waf configure` fails, **do not** abort the workflow — note the failure in the comment but continue. Cleanup (Step 7) still has to run.

### Step 4 — Playbook review (you, not the helper)

Read the playbook and the modified files, then add findings the helper can't cover. Files to load:

- `libraries/AP_HAL_ChibiOS/hwdef/AGENTS.override.md` — sections 6, 7, 12, 13 are the review checklist
- `libraries/AP_HAL_ChibiOS/hwdef/<NewBoard>/hwdef.dat`
- `libraries/AP_HAL_ChibiOS/hwdef/<NewBoard>/hwdef-bl.dat`
- `libraries/AP_HAL_ChibiOS/hwdef/<NewBoard>/README.md`
- `libraries/AP_HAL_ChibiOS/hwdef/<NewBoard>/defaults.parm` (if present)

Apply, at minimum:

- **README completeness** (§6.3): are all features in hwdef.dat documented in README.md? Especially second battery, analog RSSI/airspeed, CAN, VTX power, camera switch, LED strip, flow control, pinout images.
- **Cross-references** (§6.4): IMU names match, UART count matches `SERIAL_ORDER`, OSD chip matches, battery scales match, default protocols match the README's "this port is for X" claims.
- **Style** (§10): section dividers, peripheral context comments, DMA-disable rationale.
- **defaults.parm scope** (§7.6): only hardware-output assignments, no user preferences (no `MOT_PWM_TYPE`, `FRAME_CLASS`, `RC_OPTIONS`, etc.).
- **BIDIR rules** (§3.5): no `BIDIR` on `TIM4_CH4`; BIDIR pairs handled correctly.

The helper covers the system-timer rules (§7.2) including the F4/F7-default-TIM2 vs H7-default-TIM5 distinction, so don't second-guess it on that axis.

Don't enumerate every section of the playbook in the comment; only raise the issues you actually find.

### Step 5 — Compose the review comment

Build a markdown comment with this shape:

```markdown
Automated hwdef review (`/hwdef-check`)

PR <N> · base `origin/<baseRefName>` · new board(s) `<list>`

## Build
- `./waf configure --board <Board>`: <pass | FAIL with tail>

## Must-fix
<items the PR cannot land with>

## Should-fix
<items the reviewer expects fixed before approval but won't block merge by themselves>

## Notes
<observations, alternatives considered, polite suggestions>

<sub>Generated by Codex via `/hwdef-check`. Not a substitute for a human review pass.</sub>
```

Apply the writing rules from the root `AGENTS.override.md`:

- **Pithy** — one line per finding where possible; quote the offending file:line.
- **On the problem** — no preamble, no recap of what the PR does.
- **Address obvious-but-wrong alternatives** — if the helper flags something that has a known good reason, say so.
- **Codex attribution is allowed in PR comments**, so the trailing `Generated by Codex` line is fine. (Commits and PR descriptions are different — see root playbook.)

Skip empty sections. If there is **nothing** to flag, write a short "Nothing blocking — LGTM pending human review" comment.

### Step 6 — Show the user, ask before posting

Print the comment in full, then ask:

> Post this as a comment on PR #\<N\> ? (yes / edit / cancel)

- **yes** → write the comment to a tempfile and post:

  ```bash
  TMP=$(mktemp --suffix=.md)
  # ... write comment body to $TMP ...
  gh pr comment <PR> --repo <owner>/<repo> --body-file "$TMP"
  rm -f "$TMP"
  ```

- **edit** → ask the user what to change, redraft, ask again.
- **cancel** → skip the post and proceed to cleanup.

### Step 7 — Always restore the working tree

This step runs whether the workflow succeeded, the user cancelled, the build failed, or you hit an error in any earlier step. Do not skip it:

```bash
python3 .codex/skills/hwdef-check/hwdef_check.py restore
```

`restore` reads `.git/hwdef-check-state.json` and undoes `prepare`:

- `git checkout <original ref>` — back to the user's branch (or detached SHA)
- `git branch -D hwdef-check-pr<PR>` — drop the temporary local branch
- `git stash pop` — only if `prepare` made an auto-stash

If `restore` exits non-zero (e.g. the original ref can't be checked out because the build dropped new tracked files, or the stash pop hits a conflict), surface the message verbatim. The sidecar file is intentionally **kept** in that case so the user can re-run `restore` once they've resolved the issue.

Tell the user one of: "restored to `<branch>`", or "restored to `<branch>`, but stash pop conflicted — run `git stash list` / resolve by hand", or "could not switch back — sidecar at `.git/hwdef-check-state.json` will let you retry once you fix the working tree".

## Defaults and edge cases

- **PR target is not `master`:** the helper uses `--base origin/<baseRefName>` from PR metadata; do not hard-code `origin/master`. Switch to `upstream/<baseRefName>` if `origin` is the user's fork.
- **PR modifies an existing board** (no new hwdef.dat added): the helper's `detect` step returns empty and `all` prints a "nothing to check" message. In that case, ask the user whether they still want a review pass — and if so, run `hwdef`, `boardid`, `dma` against the specific board manually, then do the Step 4 playbook pass.
- **PR adds more than one board:** the helper handles this — it iterates each new board through the per-board checks. Compose one comment covering all of them.
- **User had stashed changes blocking the checkout:** `prepare` rolls the stash back before exiting so the user is left exactly where they started. Just report the gh error and stop.
- **Author requests Codex attribution off:** if the user says so, drop the trailing sub line; the rest of the rules in the root playbook still apply.
