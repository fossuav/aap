---
name: hwdef-check
description: Review an ArduPilot new-board hwdef PR. Checks out the PR into a temporary git worktree, runs DMA / board-ID / file-presence / commit-structure checks, layers the hwdef playbook on top, and (after confirmation) posts a review comment on the PR. Use when the user asks to review or pre-review an hwdef PR.
argument-hint: "<PR url or number>"
disable-model-invocation: true
allowed-tools: Bash(gh pr view *), Bash(gh pr diff *), Bash(gh pr checkout *), Bash(gh pr comment *), Bash(git worktree *), Bash(git fetch *), Bash(git rev-parse *), Bash(git submodule *), Bash(./waf *), Bash(python3 *hwdef_check.py*), Bash(rm -f /tmp/*), Bash(cd *), Bash(mktemp *), Read, Grep, Write
---

# Review an ArduPilot hwdef PR

This skill saves time on reviewing PRs that add a new ChibiOS board definition. It takes the PR URL or number, checks the PR out in an isolated worktree, runs the checks the user does manually (DMA allocation, board ID uniqueness, commit split, build success, hwdef patterns), and applies the hwdef playbook (`libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md`) to flag style / redundancy / completeness issues. The output is a draft review comment; **do not post it until the user has seen it and approved.**

## Inputs

`$ARGUMENTS` is the PR URL (`https://github.com/ArduPilot/ardupilot/pull/12345`) or just the number (`12345`). Repository defaults to `ArduPilot/ardupilot` when given a bare number; honour any explicit owner/repo from a URL.

If `$ARGUMENTS` is empty, ask the user for the PR.

## Working directory assumption

This skill must be run from inside an ArduPilot checkout (the current `.` should have `wscript` and `ArduCopter/`). The worktree is created **alongside** it (sibling directory), so changes to the user's current branch are untouched.

## Workflow

### Step 1 — Fetch PR metadata

```bash
gh pr view <PR> --repo <owner>/<repo> --json number,title,headRefName,headRepository,headRepositoryOwner,baseRefName,url,author
```

Extract:
- `number` — the PR number (used in worktree path and final comment)
- `headRefName` — the branch name on the contributor's fork
- `headRepository.name` / `headRepositoryOwner.login` — the fork to fetch from
- `baseRefName` — usually `master` for ArduPilot
- `url` — for the comment header

### Step 2 — Create a temporary worktree and check the PR out

Pick a worktree path that won't collide:

```bash
WT="../ardupilot-hwdef-check-pr<PR>"
git fetch origin <baseRefName>
git worktree add --detach "$WT" "origin/<baseRefName>"
```

Switch into the worktree and check out the PR. `gh pr checkout` handles forks automatically:

```bash
cd "$WT"
gh pr checkout <PR> --repo <owner>/<repo>
```

If `gh pr checkout` fails (e.g. fork is private or PR closed), stop and report the failure to the user without proceeding.

### Step 3 — Run the deterministic helper

The helper is shipped beside this skill, so its absolute path depends on where the user installed the playbook. It lives at `<original-ardupilot-checkout>/.claude/skills/hwdef-check/hwdef_check.py`. Reference it via the original checkout path (which the skill captures before `cd`).

```bash
python3 "$ORIG/.claude/skills/hwdef-check/hwdef_check.py" all \
    --base "origin/<baseRefName>"
```

This:
- detects the new board(s) added in the PR
- checks required files (hwdef.dat, hwdef-bl.dat, README.md, bootloader bin+hex)
- checks `APJ_BOARD_ID` registration + uniqueness in `Tools/AP_Bootloader/board_types.txt`
- runs static hwdef.dat checks (32-bit system timer, redundant defines, SERIAL_ORDER natural order, CS/DRDY pin labels)
- runs `./waf configure --board <Board>` (this is the slow step — ~30-60s)
- parses `build/<Board>/hwdef.h` for `NO DMA` and `SHARED` annotations
- checks commit structure (expects separate `AP_Bootloader:`, `bootloaders:`, `AP_HAL_ChibiOS:` commits)

Capture the output as the **automated findings** block — you'll merge it with your playbook findings below.

If `./waf configure` fails, stop the workflow and report that to the user; downstream checks depend on the generated `hwdef.h`.

### Step 4 — Playbook review (you, not the helper)

Read the playbook and the modified files, then add findings the helper can't cover. Files to load:

- `libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md` — sections 6, 7, 12, 13 are the review checklist
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
- **Bootloader timer match** (§7.2): main hwdef and `hwdef-bl.dat` use the same 32-bit `STM32_ST_USE_TIMER`.

Don't enumerate every section of the playbook in the comment; only raise the issues you actually find.

### Step 5 — Compose the review comment

Build a markdown comment with this shape:

```markdown
Automated hwdef review (`/hwdef-check`)

Worktree: `<WT>`  ·  base: `origin/<baseRefName>`  ·  new board(s): `<list>`

## Build
- `./waf configure --board <Board>`: <pass | FAIL with tail>

## Must-fix
<items the PR cannot land with>

## Should-fix
<items the reviewer expects fixed before approval but won't block merge by themselves>

## Notes
<observations, alternatives considered, polite suggestions>

<sub>Generated by Claude via `/hwdef-check`. Not a substitute for a human review pass.</sub>
```

Apply the writing rules from the root `CLAUDE.md`:

- **Pithy** — one line per finding where possible; quote the offending file:line.
- **On the problem** — no preamble, no recap of what the PR does.
- **Address obvious-but-wrong alternatives** — if the helper flags something that has a known good reason, say so.
- **Claude attribution is allowed in PR comments**, so the trailing `Generated by Claude` line is fine. (Commits and PR descriptions are different — see root playbook.)

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

### Step 7 — Cleanup

Always remove the worktree, even on cancel:

```bash
cd "$ORIG"
git worktree remove --force "$WT"
```

Report the final state (posted / skipped) and the worktree removal.

## Defaults and edge cases

- **PR target is not `master`:** the helper uses `--base origin/<baseRefName>` from PR metadata; do not hard-code `origin/master`.
- **PR modifies an existing board** (no new hwdef.dat added): the helper's `detect` step returns empty and `all` prints a "nothing to check" message. In that case, ask the user whether they still want a review pass — and if so, run `hwdef`, `boardid`, `dma` against the specific board manually, then do the Step 4 playbook pass.
- **PR adds more than one board:** the helper handles this — it iterates each new board through the per-board checks. Compose one comment covering all of them.
- **Author requests Claude attribution off:** if the user says so, drop the trailing sub line; the rest of the rules in the root playbook still apply.
