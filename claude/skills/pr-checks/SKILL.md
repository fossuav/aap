---
name: pr-checks
description: Download a pull request's failing CI checks and identify the failing tests or build errors. Use when the user asks why a PR's CI is red, which tests failed, or to triage GitHub Actions failures on a PR.
argument-hint: "[PR number/url/branch] [--repo OWNER/REPO]"
allowed-tools: Bash(python3 *), Bash(gh pr:*), Bash(gh run:*), Bash(gh api:*), Read, Grep
---

# Triage PR CI Failures

ArduPilot PRs run a large CI matrix (build + autotest across many boards). When CI
is red, this skill pulls only the failed jobs' logs and extracts the failing tests
and build errors, so you don't page through the GitHub Actions UI or run dozens of
`gh` commands by hand.

## Why the helper exists

`gh run view --log-failed` returns nothing for this repo. The helper at
`.claude/skills/pr-checks/ci_failures.py` works around that by downloading each
failed job's log through the REST API (`gh api .../actions/jobs/<id>/logs`). It
wraps every `gh` call in one process, so the whole triage runs under a single
`python3` permission instead of prompting per `gh` invocation. Always use the
helper - do not hand-roll `gh run view` / `gh api` loops.

## Workflow

### Step 1: Run the helper

```bash
# Current branch's PR
python3 .claude/skills/pr-checks/ci_failures.py

# A specific PR (number, URL, or branch). For a fork PR to upstream, name the repo:
python3 .claude/skills/pr-checks/ci_failures.py 33312 --repo ArduPilot/ardupilot
```

Output is a header (pass/fail/pending counts) followed by one block per failing
check with the curated failure lines:

```
- test copter / autotest (sitltest-copter-tests2b)
    AT-2083.2: FAILED: "GuidedWeatherVane (...)": AutoTestTimeoutException('Failed to attain Heading want 90.0, reached 84') (see /tmp/buildlogs/ArduCopter-GuidedWeatherVane.txt)
    >>>> FAILED STEP: test.CopterTests2b
    FAILED 1 tests: ['test.CopterTests2b']
```

The helper recognises:
- autotest failures - the per-test `FAILED: "<name>": <Exception>(<reason>)` line, the `>>>> FAILED STEP:` and the `FAILED N tests:` summary,
- build failures - the `file:line:col: error:` compiler line, `Build failed`, and the waf `-> task in '...' failed` line,
- `##[error]` problem-matcher annotations generally.

### Step 2: Dig into one job if needed

If a check shows "no recognised failure markers" (some jobs - e.g. colcon/ROS2 -
use a format the helper doesn't pattern-match), or you want the full error context:

```bash
# Dump the raw ##[error]/summary lines for jobs whose name matches the substring
python3 .claude/skills/pr-checks/ci_failures.py 33312 --repo ArduPilot/ardupilot --raw quadplane
```

For the complete log, open the printed `detailsUrl`.

### Step 3: Reproduce locally

Map the failing CI job to a local command:
- `test.CopterTests2b` / `sitltest-copter-tests<N>` -> the failing individual test is the `FAILED: "<Name>"` - run it with `/autotest Copter <Name>` (e.g. `/autotest Copter GuidedWeatherVane`).
- A build error -> reproduce with `/build <vehicle> --board <board>` for the board named in the check (e.g. `build (chibios, MatekF405)` -> `--board MatekF405`).

## Reporting back

- Lead with the counts (e.g. "4 failing, 68 passing, 0 pending").
- For each failure, name the test or the compiler error and its one-line reason.
- Note whether the failures look related to the PR's change or are pre-existing/flaky (e.g. the same test failing on unrelated PRs - cross-check with the test's history if unsure).
- Don't paste whole logs; the helper already extracts the signal.

## Notes

- Re-run the helper later if checks are still pending - it reports the pending count and exits cleanly.
- External checks (Azure, Semaphore, ROS2 colcon) that aren't GitHub Actions jobs are listed with their link rather than parsed.
- The helper needs `gh` authenticated (`gh auth status`) and read access to the repo running the checks (ArduPilot/ardupilot for upstream PRs).
