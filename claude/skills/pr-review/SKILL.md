---
name: pr-review
description: Review your own ArduPilot PR the way a maintainer will - before you open it, or after review feedback arrives - and then fix what the review finds. Runs the CI gates that bounce PRs mechanically, fans out parallel reviewers over the diff, cross-checks every finding with an independent Codex pass, and iterates fixes until the verdict is clean. Use when the user is about to open a PR, asks whether a branch is ready to submit, or wants to make a PR pass review.
argument-hint: "[PR number/url] [--fix] [--no-codex] [--base ref]"
allowed-tools: Bash(python3 *pr_review.py*), Bash(gh pr view:*), Bash(gh pr diff:*), Bash(gh pr checks:*), Bash(git diff:*), Bash(git log:*), Bash(git show:*), Bash(git rev-parse:*), Bash(git merge-base:*), Read, Grep, Edit, Task
---

# Review your own PR before a maintainer does

This is the ArduPilot review pipeline turned around: instead of reviewing other
people's PRs, it reviews **yours**, at the point where fixing something is still
free. It is adapted from Andrew Tridgell's `/reviewprs` dev-call workflow at
<https://github.com/tridge/junkcode/tree/master/AI/claude/reviewprs>, which sweeps
every PR carrying a label and cross-checks each one with a second AI reviewer. The
pipeline, the head-hash skip and most of the review rules below are his; the target
and the ending differ - one PR instead of a batch, and it ends in **fixes applied
to your tree** rather than comments posted to someone else's PR.

**Self-review is the anchored case.** You already believe the diff is correct - you
wrote it. Every mechanism below that costs extra effort exists because of that:
the Codex pass that never sees your findings, the requirement to reproduce numbers,
the rule that the mechanical gate runs before anyone forms an opinion. Skipping
them because "it's my own small change" removes exactly the parts that can
contradict you.

## Arguments

`$ARGUMENTS` is optional:

- *(nothing)* - review the current branch against its merge-base with upstream master. This is the pre-submission case: there may be no PR yet.
- `<number>` or `<url>` - review that PR. Use this when review feedback has arrived and you are making the PR pass.
- `--fix` - go straight into the fix loop after the review, instead of stopping to show findings first.
- `--no-codex` - skip the Codex cross-check (say so in the report; the verdict is single-sourced).
- `--base <ref>` - diff against something other than the auto-detected base.

Run from the root of an ArduPilot checkout.

## Step 0 - Scope the review

```bash
python3 .claude/skills/pr-review/pr_review.py scope [$ARGUMENTS]
```

Prints the branch, resolved base ref and merge-base, the open PR if there is one,
every commit with its subsystems, and the changed files. `--json` for the machine
form.

Read the output before going further. Three things in it change what you do:

- **Uncommitted changes are excluded.** The review covers committed work only. If the tree is dirty, say so up front - reviewing a diff the user is still editing produces findings about code that no longer exists.
- **The commit list is the review unit.** ArduPilot wants one subsystem per commit; the fan-out in step 3 follows those boundaries.
- **The base ref.** If it resolved to `origin/master` on a fork that is months stale, the diff includes everything master gained since. Pass `--base upstream/master` and rerun.

A `WARNING:` line at the top means the PR you named is at a different commit from
the checkout. The metadata would come from the PR while every finding came from
the local branch, so stop and `gh pr checkout <number>` first. The scope command
prints it rather than refusing, because reviewing a local branch that has drifted
ahead of its own PR is a legitimate thing to do - but only when you meant to.

## Step 1 - Mechanical gate

```bash
python3 .claude/skills/pr-review/pr_review.py checks [$ARGUMENTS]
```

Exit status 1 means at least one **must-fix**. These are the findings that get a PR
bounced without a human forming an opinion about the code at all, so they are
cheapest to clear first and they run in about two seconds:

| Check | What it catches |
|-------|-----------------|
| `whitespace` | `git diff --check` errors, grouped per file; vendored/generated files are downgraded to a note |
| `flake8` | changed `.py` files carrying the `AP_FLAKE8_CLEAN` marker that no longer pass flake8 - a real CI job |
| `astyle` | reformatting on lines you added, **only** within the paths `Tools/scripts/run_astyle.py` actually enforces |
| `non-ascii` | em-dashes, smart quotes, arrows and ellipses in added code - the clearest machine-written tell |
| `printf` | `printf()` in flight code (`gcs().send_text()`, or `hal.console->printf()` for debug) |
| `commits` | missing subsystem prefix, prefix that does not match the files, a commit spanning several subsystems, merge commits, Claude/AI attribution, non-ASCII in the message, over-long subjects |
| `params` | new `AP_GROUPINFO` entries with no `// @Param:` block, incomplete doc blocks, names over 16 characters |
| `new-file-license` | new source files with no licence or copyright header |
| `defensive-init` | zero-initialisers added to class members - redundant given BSS/`new`/`calloc`, and a reliable LLM-tell |
| `size` | total diff size, and any uncommitted tracked files excluded from the review |

Severity is advice, not a verdict: `must-fix` blocks, `should-fix` needs a reason
if you leave it, `note` is context. `--skip <check>,<check>` drops individual
checks when one is genuinely wrong for a PR - and if you skip one, say which and
why in the report.

**The commit-prefix check asks the repository before it complains.** When a prefix
is not the one the playbook prescribes, the helper looks at whether the base
branch's own history uses that prefix for those paths, and stays silent if it
does. This exists because the first version reported `hwdef:` as wrong on hwdef
commits - upstream has used it 667 times. Extend `PREFIX_ALIASES` rather than
teaching the user to ignore the check.

## Step 2 - Read the thread

If the PR exists, read it before writing a single finding:

```bash
python3 .claude/skills/pr-review/pr_review.py thread [<number>]
```

Every source is paginated (issue comments, reviews, review comments) because on an
active PR your own newest items are exactly the ones that fall off page one. The
output leads with per-source counts, so "nothing there" is visibly a fetched result
rather than a fetch that failed.

On your own PR the thread is not background - it *is* the specification for
"passes review":

- A maintainer objection outranks anything this pipeline finds. Address it first, and if you disagree, argue it on the merits in the thread rather than quietly not doing it.
- A review comment you already answered in code needs checking against the diff, not re-answering.
- A review comment you answered *in prose* and never fixed is the most common reason a PR stalls. Surface those explicitly.

## Step 3 - Primary review, fanned out

**Read the whole diff yourself. Fan out to do it, do not fan out to avoid it.**
Launch one subagent per commit (or per subsystem, when commits are small and
related) in a single message so they run concurrently. Each one gets its own slice
of the diff, reads the surrounding source in the checkout, and returns findings
marked **VERIFIED** or **UNCONFIRMED**.

Give each agent the angles that actually matter for what it is reviewing rather
than a generic "review this":

- **hwdef / board PRs** - pin labels, DMA sharing and conflicts, board ID registration and uniqueness, power rail defaults, bootloader/timer agreement. `/hwdef-check` already automates most of this; run it instead of re-deriving it.
- **Control, EKF, filters** - the maths, the mode dispatch, unit and frame agreement, what happens at the edges the design admits (zero, negative, saturated, NaN). Domain math (`sqrtf`, `logf`, `acosf`, division) gets every reaching value enumerated.
- **Drivers and HAL** - register sequences against the datasheet, timeouts, bus sharing, failure paths, what happens when the device is absent.
- **Anything embedded** - flash and RAM cost, stack depth, allocation in flight paths, and whether a new feature needs an `AP_*_ENABLED` guard so small boards can drop it.
- **Tooling and scripts** - the failure modes, not the happy path.

The standard every agent reviews against is the playbook itself: the C++ Development
Guidelines, Development Constraints, Comments and Documentation, the Surgical
Modification Principle, Commit Conventions, and Writing for Reviewers in the root
`CLAUDE.md`. That is the same document a maintainer's objections tend to reduce to.

Tell each agent explicitly that an admitted gap is worth more than a confident
wrong claim. These findings turn into edits to the user's code.

## Step 4 - Codex cross-check

Unless `--no-codex`, every finding gets an independent second opinion, and the
parts of the diff you *cleared* get a cold read. Both run as one detached pool:

```bash
SCRATCH=$(mktemp -d)/pr-review; mkdir -p "$SCRATCH/tasks"
# one task file per unit of work; name them so the log is identifiable
cat > "$SCRATCH/tasks/verify-<commit>.task" <<'EOF'
...findings for that commit, inline, plus how to fetch the diff...
EOF
cat > "$SCRATCH/tasks/cold-<commit>.task" <<'EOF'
...PR/commit identity only - no findings, no verdict...
EOF

python3 .claude/skills/pr-review/pr_review.py codex run --dir "$SCRATCH" --jobs 4
python3 .claude/skills/pr-review/pr_review.py codex status --dir "$SCRATCH"
```

`run` detaches and returns immediately; `status` exits **3** while the pool is
running, **0** when every task produced output, and **4** when a task came back
empty or non-zero. Poll `status` rather than the process table, and re-run
stragglers with `codex run --dir "$SCRATCH" --retry` - a missing log is a piece of
the diff that received no second opinion, and it is invisible unless you count.

Two kinds of task, kept strictly apart:

- **Verification** - give it one commit's findings inline and ask for **CONFIRM / REFUTE / ADJUST** per finding plus any **NEW** ones. Never point it at your report.
- **Cold** - give it the diff and nothing else: "review this and report anything wrong". This is the one that matters most on a self-review, because it is the only reader in the pipeline that is not anchored by your intent. Aim it at the parts you cleared, especially new hwdefs, state machines, concurrency, lifetime/ownership, and anything that newly depends on existing shared state.

`codex exec` logs interleave the tool transcript with prose and the final answer is
not reliably the tail, so extract findings by grepping for the markers you asked
for rather than slicing the end of the file.

## Step 5 - Reconcile

Codex is a second opinion, not an authority, and on your own PR you are the one
with the conflict of interest. Both directions get checked against the source:

- **Reproduce every numeric claim** - a magnitude, a timing, a size, a count - before it drives a fix. A ten-line script settles it. In tridge's runs this method confirmed a 57.3x timeout error and refuted a claimed 101 degree phase error that measured 0.06.
- **Check the diff's own comments before accepting a finding.** A second opinion will happily report a bug in code you changed deliberately with a comment saying why. Acting on one such report has reintroduced the bug it was meant to fix.
- **Codex skews to REQUEST CHANGES.** Re-derive the verdict from the findings that survive; never copy its label across.
- **Know the project's practice before calling something a process violation.** A submodule pointer moving to an unmerged commit is normal in ArduPilot as long as the submodule PR is linked in the description. Verify against the repo, the way the prefix check does, rather than asserting a rule.
- **Do not accept a refutation of your own finding just because it is convenient.** That is the direction self-review fails in.

## Step 6 - Verdict

State one, in the maintainer's vocabulary, so it is comparable with what will
happen next:

- **APPROVE** - would merge as-is. Say what you actually verified, not "looks good": the paths traced, the callers audited, whether a cold pass ran and what it looked for. A clean verdict with no evidence behind it is worth less than nothing on your own PR.
- **COMMENT** - merges, but with noted issues.
- **REQUEST CHANGES** - has defects that must be fixed first.

Record it so a re-run can skip unchanged work:

```bash
python3 .claude/skills/pr-review/pr_review.py state save --verdict REQUEST_CHANGES --findings 7
```

## Step 7 - The fix loop

**Show the findings and get agreement before editing**, unless the user passed
`--fix` or already said to go ahead. Then work down the list:

1. **Must-fix first**, then should-fix. Leave notes alone unless asked.
2. **Fix the cause, never the check.** Adding a `# noqa`, widening a `--skip`, or reformatting a vendored file to silence the gate is not a fix.
3. **Keep the diff surgical.** The Surgical Modification Principle applies to review fixes as much as to the original change - do not tidy sibling code while you are in there. A fix that grows the diff gives the reviewer more to read, not less.
4. **Put each fix in the commit that introduced the problem**, not in a trailing "address review comments" commit. ArduPilot reviews history, so a whitespace fix belongs squashed into the commit that added the whitespace. That needs a rebase or an amend, both of which are blocked until the user runs `/prepare-for-push <branch> --allow rebase,amend` (and `push` if the branch is already published). **Ask; never run `/prepare-for-push` yourself.** Where a rebase is not wanted, say so plainly and use fixup commits instead.
5. **Re-run the mechanical gate after every round.** It is two seconds and it catches fixes that introduced new problems.
6. **Build what you touched.** `/build <vehicle>` for the affected target, `/check` when libraries with unit tests changed. A review fix that does not compile is worse than the finding.

## Step 8 - Re-review what moved

```bash
python3 .claude/skills/pr-review/pr_review.py state diff
```

Exit **0** means the head is unchanged since the recorded review - nothing to
re-review. Exit **2** prints a diff of what changed since, and only that needs a
fresh pass.

After a rebase or an amend the recorded commit normally still exists locally, so
this prints a **content** diff between the old head and the new one rather than a
list of rewritten commits. That is the useful comparison: an empty diff means the
rebase moved the branch without changing what it does, which is exactly the check
the playbook asks for before a force push. Only when the old object has actually
gone does it say so and start the review over.

Iterate steps 7-8 until the mechanical gate is clean and no must-fix findings
survive, or until three rounds have passed without converging - at which point stop
and tell the user what is not converging rather than churning their tree.

Once CI has run on a pushed branch, `/pr-checks` triages the failures; those are
findings too, and they belong in the same loop.

## Reporting back

- Lead with the verdict and the counts: `REQUEST CHANGES - 3 must-fix, 4 should-fix, 2 notes (Claude + Codex, 1 refuted)`.
- Say which reviewers ran. If `--no-codex` was used, or a Codex task came back empty and was not re-run, say the verdict is single-sourced. Do not present it as cross-checked when it was not.
- Group findings by severity with `file:line`, and name the ones that came from the cold pass - those are the ones your own read missed.
- After a fix round, report what changed, what was left and why, and the new verdict.
- Name what you did **not** cover: unbuilt targets, untested behaviour, hardware you cannot exercise. On a self-review the unexamined part is the part most likely to fail review.

## What this skill does not do

- **It does not post anything to GitHub.** No comments, no reviews, no PR body edits. It reads the PR and writes to your working tree. Posting is a separate, explicit request.
- **It does not push.** Every push, rebase and amend stays behind the `/prepare-for-push` grant and the git pre-push hook. The skill asks; the user authorises.
- **It does not create the PR.** Drafting the PR body is ordinary work under the Pull Requests section of `CLAUDE.md` (follow `.github/PULL_REQUEST_TEMPLATE.md`, trim the checklist, no Claude attribution).
- **It is not a substitute for review.** It is a way to arrive at review having already fixed what a maintainer would have spent their time on.
