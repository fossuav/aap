# GEMINI.md

This file provides guidance to Google Antigravity (`agy`) when working with code in this repository.

**Playbook version:** 1.0.0

## Precedence and Repository-Local Rules

- **Supersedes conflicting upstream `AGENTS.md` rules:** Where upstream `AGENTS.md` conflicts with this playbook — notably AI-assistance disclosure or hidden emoji markers, commit/PR prose style, and fork workflows — follow this playbook. Never add AI-assistance disclosures, denials, or hidden markers to commits, PR descriptions, or comments.
- **Repository-local rules:** Before starting any task, look for `CLAUDE_local.md` or `AGENTS_local.md` at the repository root (read from the primary checkout if inside a worktree) and read it if present.
- **SmallFastDrone (`Tools/SFD/`):** If `Tools/SFD/` exists, read `Tools/SFD/README.md`, `Tools/SFD/ANALYSIS_REPOS.md`, `Tools/SFD/REFRESH_NOTES.md`, `Tools/SFD/PR_REVIEW_RULES.md`, and `Tools/SFD/ARCHITECTURE_RULES.md` before refresh, topup, review, or log-analysis work. Never cite private repo paths (`../analysis`, `../analysis-private`), filenames, vehicle owners, testers, or locations in public text, commit messages, PR comments, or `Tools/SFD/`.

## Antigravity Environment and Usage

- **Skills discovery:** Antigravity discovers skills in `.agents/skills/*/SKILL.md` (not `.claude/skills/` or `.codex/skills/`). Prefer installed skills and their Python scripts under `.agents/skills/<skill>/` over ad-hoc shell one-liners.
- **24 KB rule limit & references:** Standalone `GEMINI.md` rule files are capped at 24,000 bytes (and share a 20,000-token rules budget). Full unabridged documentation and oversized subsystem playbooks live in `.agents/references/` (`CORE_PLAYBOOK.md`, `AP_NavEKF3.md`, `hwdef.md`). Read the relevant reference with `read_file` before modifying or reviewing those areas.
- **Terminal sandbox & sibling repos:** `read_file` reads outside the workspace directly. `run_command` runs in a sandbox restricted to the workspace, `/tmp`, and `<appDataDir>/brain/` with no network access. Always try sandboxed first; run only the single outside-workspace or network command (`gh`, `curl`, `git -C ../...`, worktrees in `../`) with `BypassSandbox: true`.
- **Subagents & orchestration:** Use `invoke_subagent` (or `run_workflow` for multi-unit fan-out) for parallel commit reviews, cold reads, and codebase research. Use `update_steps` for multi-step tasks and `ask_question` for genuine design decisions.
- **Push & history safety:** Never run `git push`, `git rebase`, `git reset`, `git commit --amend`, or `git clean` without explicit user confirmation in the current session. Note that `.claude/githooks/pre-push` only checks for a `claude` process ancestor, so `agy` pushes are not auto-blocked by that hook unless you ask first. Never pass `--no-verify` or alter `core.hooksPath`.

## Available Skills (`.agents/skills/`)

| Skill | Use for |
|-------|---------|
| `/build <vehicle> [--board board]` | Configuring and building firmware |
| `/boards [search]` | Listing/searching available board targets |
| `/sitl <vehicle>` | Launching SITL simulator |
| `/autotest <vehicle> [test]` | Running SITL integration tests |
| `/check [test_name]` | Running Google Test unit tests |
| `/style-check [files]` | Checking code style before committing |
| `/find-code <feature>` | Finding where features, modes, or commands live |
| `/find-param <NAME>` | Finding parameter definitions in source |
| `/build-options [search]` | Searching compile-time feature flags |
| `/hwdef-info <board>` | Showing board hardware definitions |
| `/hwdef-check <PR>` | Reviewing an hwdef PR (DMA, board ID, files, commits, playbook) |
| `/explain <topic>` | Explaining code or architecture |
| `/swd-debug` | Flashing/debugging a board over SWD |
| `/lua <task>` | Writing or modifying Lua applets |
| `/lua-crsf <menu>` | Writing CRSF transmitter menu scripts |
| `/lua-vehicle <task>` | Lua vehicle control and movement commands |
| `/log-analyze <logfile>` | Analyzing DataFlash `.bin` flight logs |
| `/pr-checks [PR]` | Downloading a PR's failing CI checks and identifying errors |
| `/pr-review [PR]` | Reviewing your own PR (CI gates, parallel review, cold read, fix loop) |
| `/cleanup [--sweep]` | Surveying and removing scratch worktrees and branches safely |
| `/aap-update` | Checking local playbook version against GitHub and updating |

## Build System, SITL, and Autotest

Always run `./waf` from the repository root. **Never use `autotest.py build.*` for builds.**

```bash
./waf configure --board sitl        # or --debug, --board CubeOrange, --consistent-builds
./waf copter                        # build vehicles in SEPARATE ./waf calls (copter, plane, heli, sub, rover, AP_Periph)
./waf --targets tests/test_math     # single unit test
./waf check                         # run changed unit tests
Tools/autotest/sim_vehicle.py -v ArduCopter
Tools/autotest/autotest.py test.Copter.<TestMethod>
```

- Build vehicles in separate `./waf` invocations (`./waf plane heli sub` in one call can link the wrong library set).
- **Never pass `--uds`** to `autotest.py` or `sim_vehicle.py` (changes UART outqueue limit from 1024 to 65536 bytes).
- On stacked branches (like SFD), run `Tools/SFD/check_param_tables.py` after code changes and before any SITL run.

## Architecture and Subsystem Playbooks

- Vehicles (`ArduCopter/`, `ArduPlane/`, `Rover/`, `ArduSub/`, `AntennaTracker/`, `Blimp/`) inherit `AP_Vehicle` and own flight modes (`mode_*.cpp`) and responses.
- `Tools/AP_Periph/` is CAN peripheral firmware; `libraries/` holds shared libraries (`AP_HAL*`, `AP_NavEKF3/`, `AP_AHRS/`, `AP_DAL/`, `AP_Scripting/`, `GCS_MAVLink/`, `SITL/`, etc.).
- **Read subsystem guidance before touching its code** (if in a worktree without untracked files, read from the primary checkout):
  - `libraries/AP_NavEKF3/GEMINI.md` + `.agents/references/AP_NavEKF3.md`
  - `libraries/AP_HAL_ChibiOS/hwdef/GEMINI.md` + `.agents/references/hwdef.md`
  - `Tools/autotest/GEMINI.md`
  - `libraries/AP_Scripting/GEMINI.md` (`GEMINI_CRSF_MENU.md`, `GEMINI_VEHICLE_CONTROL.md`)
  - `ArduPlane/GEMINI.md`
- **Confirmed architectural rules** live in this playbook and any tracked `*ARCHITECTURE_RULES.md` (`git ls-files '*ARCHITECTURE_RULES.md'`). Candidates in `RULES_PROPOSED.md` are not standards until confirmed by the user.

## C++ Development Guidelines

Full rationale and examples are in `.agents/references/CORE_PLAYBOOK.md`.

### Architectural Rules (`ARCH-1` to `ARCH-26`)

- **ARCH-1 (Shared state is a contract):** Changing what shared state means or when it is set updates every reader; report which readers were checked. Publish via `const` accessors.
- **ARCH-2 (Test for what you need, not a proxy):** Test directly for position, healthy sensor, or link rather than proxies like a cleared failsafe.
- **ARCH-3 (Lower layers detect, higher layers decide):** Shared libraries report observations and never reach up; vehicles decide responses. Generic behaviour belongs in shared libraries.
- **ARCH-4 (Optional features cost nothing when off):** Non-universal features get an `AP_<NAME>_ENABLED` define in `*_config.h` and `Tools/scripts/build_options.py`, defaulted off on tight flash, guarding whole functions/`case`s. Report flash cost on a small board.
- **ARCH-5 (Safety logic is judged by what it does when wrong):** Trigger failsafes on lost flight dependencies, separate trigger from action, never weaken existing failsafes, and design disarm/land/mode-change logic for false positives.
- **ARCH-6 (Do not break what users already have):** Keep existing configs, GCS, logs, and scripts working; state, migrate, and release-note user-visible changes.
- **ARCH-7 (Simplest design that does the job):** Avoid speculative queues, flags, or mirrored state; keep one source of truth.
- **ARCH-8 (Reuse before you write):** Extend existing base classes or shared libraries rather than duplicating.
- **ARCH-9 (The main loop never waits):** Never block, busy-wait, or sleep on the main thread; protect cross-thread data with `WITH_SEMAPHORE`.
- **ARCH-10 (Nothing from outside is trusted):** Bound loops/buffers, validate parameters/sensor/wire inputs, never index arrays from user-set parameters.
- **ARCH-11 (Pre-arm checks catch silent misbehaviour):** Check in the owning library for what the vehicle actually uses, name the cause, and only read (arm-time actions belong in `arm()`).
- **ARCH-12 (Memory is paid for only where used):** Allocate optional state at init/first use only when present, check allocations, free when unused, keep large buffers out of BSS.
- **ARCH-13 (Drivers hold for every variant and failure):** Check every variant datasheet, take timeout path first to no-data, do not trust one sample, keep risky fixes scoped.
- **ARCH-14 (No unused code; remove what you orphan):** Add helpers/members/params only when used in the same PR; remove code your change leaves dead.
- **ARCH-15 (`INTERNAL_ERROR` is for the impossible):** Never raise for bad sensor/GCS/parameter inputs or harmless misuse.
- **ARCH-16 (Use the weakest spatial reference needed):** Position (NED from EKF origin) vs Location (lat/lon/alt) vs Home (movable) vs Origin (fixed horizontally).
- **ARCH-17 (Libraries carry no vehicle-specific code):** Never test vehicle class at runtime in a library; vehicle moderates via setters/options/generic signals (`APM_BUILD_TYPE` only where strictly necessary; Replay follows `dal.get_vehicle_class()`).
- **ARCH-18 (Driver-thread data crosses only at frontend copy):** Bus timer callbacks accumulate under backend `_sem`; `update()` copies to frontend on main thread.
- **ARCH-19 (New behaviour is opt-in, structure before behaviour):** Refactoring/plumbing commits first (ideally binary-identical), small behaviour commit last behind a param/option/define unless fixing a clear bug.
- **ARCH-20 (Flags held true by a mode stay valid on exit):** Keep underlying evidence current or refresh it when the mode ends.
- **ARCH-21 (Masked filter state keeps consistent covariance):** Update masked states in Joseph form or decorrelate before computing gain.
- **ARCH-22 (Never reuse a released parameter index):** `AP_Param` keys by table, index, and type. Mark removed/moved indices `// N was NAME` against every released build (including fork betas).
- **ARCH-23 (Parameters earn their flash; >=1 KB sits behind a define):** Prefer constants, auto defaults, or `_OPTIONS` bits before adding a parameter; state flash cost and added params in the PR.
- **ARCH-24 (Flight thresholds have a checkable reason):** Derive from sensor noise/filter variance/existing named constant, or justify with multi-airframe logs; never bare magic numbers — use `static constexpr` with unit suffix and comment.
- **ARCH-25 (Feed-forward models the vehicle, not command limits):** Derive feed-forward from vehicle estimates, never command-shaping parameters.
- **ARCH-26 (Filter outputs are not independent measurements):** Do not fuse another filter's correlated output every step without rate-limiting or inflated noise.
- **Flight-state flags (`onGround`, `inFlight`, `takeOffDetected`, `land_complete`, `is_flying()`):** Per-vehicle opinions that can read wrong in flight; check every vehicle class and require a second independent signal before fabricating zero-velocity/zero-flow/height observations.

### Style, Memory, Logging, and Replay Rules

- **Formatting (`Tools/CodeStyle/astylerc`):** 4 spaces (no tabs), LF endings, `#pragma once`, function `{` on new line, control `{` on same line, always brace single-line blocks, `if (cond)`, `foo(a, 10)`, format **only** modified lines (`astyle --options=Tools/CodeStyle/astylerc --dry-run <file>`).
- **STYLE-1..12:**
  1. Name says what it is/does on every path; positive booleans; no leading `_` on methods.
  2. Comments stay true and state preconditions, sentinels, units, workarounds — not "what" or process history; one-line purpose in `.h`, full inputs/units/edge cases/"why" above definition in `.cpp`; short member comments in headers; **ASCII only** (`-`, `->`, `"`, `...`; never em-dashes, smart quotes, Unicode arrows).
  3. Fixed-width types sized for all values (including negatives); enums over raw ints; `sizeof` + named constants.
  4. Feature/debug macros always defined as `0` or `1` and tested with `#if` (`-Werror=undef`), `#ifdef` only for compiler/platform; file-local constants as `static constexpr`.
  5. Switch over enum lists every value with no `default:` (`-Werror=switch`), and handle out-of-range cast values after the switch.
  6. Avoid bitfields/packed structs unless wire/storage requires them; no unneeded `virtual`, destructors, or error returns that cannot fail.
  7. Put non-zero member defaults at declaration; omit zero defaults (`{0}`, `= 0`, `{}`) on class members (BSS/`new` zeroes them; redundant zero-init is an LLM tell).
  8. Narrowest interface: private members, `const` methods, references for non-null inputs, return values only when callers act.
  9. Compare elapsed time with `AP_HAL::timeout_expired(start, now, timeout)` or `AP_HAL::timeout_remaining()`; store start timestamps, never `now + duration`.
  10. Guard conditions return early, one reason per check.
  11. Extract repeated or tricky boolean conditions into `const` named predicates.
  12. No default arguments for a single caller or consequential choices.
- **Math, Types & Memory:** NED frame (`X`=N, `Y`=E, `Z`=Down); unit suffixes (`_m`, `_cm`, `_rad`, `_deg`, `_rads`, `_dps`, `_ms`, `_mss`, `_ms`/`_us`); float literals `1.0f`; multiply instead of divide; `is_zero()`, `is_positive()`, `is_negative()`, `is_equal()`; `static_cast` before bitwise/mixed-width ops; verify exact signatures in headers before calling any API; enumerate domain-math inputs (`sqrt`, `log`, `acos`, `asin`, `/`); no `malloc`/`new` in flight code; prefer embedded objects or `calloc`/`free` over `new[]`/`delete[]`.
- **Parameters:** `@Param`, `@DisplayName`, `@Description`, `@Values`/`@Bitmask`, `@Range`, `@Units`, `@Increment`, `@User`, `@RebootRequired`, `@Vehicles`; full name <= 16 chars; never change an existing `AP_GROUPINFO` index.
- **LOG-1..6:** (1) Append log fields at end; short stable names; doc every new message. (2) `GCS_SEND_TEXT()` only (never `printf`), rare, rate-limited, actionable. (3) Libraries log their own state under their own log bit. (4) State bandwidth cost; do not log unused lanes/features. (5) Monotonic `TimeUS`; older samples carry their own sample timestamp. (6) Report configured backend startup failures without flooding unconfigured features or blocking boot.
- **REPLAY-1..4:** (1) Extend existing DAL messages at end with explicit alignment padding and zero=old-behaviour. (2) Keep retired DAL fields as `unused`, never reuse. (3) Everything EKF reads at runtime enters through `AP_DAL`. (4) Infrequently changing config gets its own DAL message written on change and log start.
- **Surgical Modification:** Smallest diff strictly in scope; never tidy sibling code, normalize adjacent whitespace, or add `{0}`/`= 0` to existing members; keep `AP_<FEATURE>_ENABLED` guards; never modify `modules/`.

## Commit Conventions and Git Safety

- **Atomic per-subsystem commits:** One subsystem/directory per commit, every commit compiles. Prefix subject line with exact subsystem (`AP_AHRS:`, `Copter:`, `Plane:`, `Tools:`, `autotest:`, `scripts:`, `hwdef:`, `AP_Bootloader:`, `bootloaders:`). Check with `python3 Tools/scripts/check_branch_conventions.py --base-branch upstream/master`.
- **Flown commits:** Never squash an unflown behaviour change into a commit that has already flown (flight evidence requires logs exercising that exact path); place unflown behaviour fixes on top as separate commits until flown.
- **No AI attribution:** Never add `Co-Authored-By`, "Generated with...", or AI trailers/markers.
- **Git hygiene:**
  - **Never** run `git clean` without explicit user permission.
  - **Never** run `git add -A` or `git add .` (they sweep untracked playbooks/notes into commits, which later checkouts delete). Always stage explicit file paths (`git add path/a path/b`) or `git add -u` for tracked edits.
  - Remove scratch worktrees with `git worktree remove` (or `/cleanup`), never `rm -rf`.
  - After rebasing/squashing, verify content with `git diff <orig> <rebased>` and `git range-diff`.

## Pull Requests, Writing for Reviewers, and Diagnosing from Logs

- **Before PR / Push:** Run `/pr-review` before opening a PR (`--quick` for targeted review fixes); follow `.github/PULL_REQUEST_TEMPLATE.md` (trim irrelevant checklist items); list parameter changes and flash cost; check CI (`Tools/scripts/check_branch_conventions.py`). Use `gh api -X PATCH repos/ArduPilot/ardupilot/pulls/<N>` instead of `gh pr edit` (fails on classic-projects deprecation).
- **Writing for Reviewers (commit bodies, PR descriptions, comments):**
  - Open with what the user does, what goes wrong, and what the change does (no internal identifiers in opening paragraph; second person for the failure, third person elsewhere; no first-person chat style).
  - Keep above-the-fold PR prose around 200-400 words (500 max); put secondary tables, rejected alternatives, and untouched-state enumerations under the Description detail heading.
  - Replies to reviewers: 1-3 sentences answering directly with evidence/numbers; no bot-style tables.
  - **No LLM tells:** no bold mini-headlines (`**Thing.** ...`), sparse backticks, ASCII punctuation only, vary sentence structure, no filler/hype, **do not hard-wrap PR descriptions or comments** (soft-wrap markdown; wrap commit bodies and in-repo `README.md` at ~75 cols).
- **Diagnosing & Verification:**
  - A mechanism inferred from one log is a **hypothesis**, not a diagnosis — test and measure it.
  - Any behaviour/control/EKF change gets a SITL A/B (`.agents/skills/log-analyze/` + `Tools/autotest/GEMINI.md`).
  - Interrogate measurements for angle wrap, dead parameter names, clipped sensors (`VIBE.Clip`), degenerate fits, and sim-only artifacts.
  - **Coverage is a trace, not a green run:** verify a cited test actually enters the changed branch (and fails with the fix reverted).
  - **A claim marked checked is a hypothesis:** re-derive claims from source when touching them; correct wrong records loudly.
