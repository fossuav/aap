---
name: cleanup
description: Clean up what agent sessions leave behind - scratch git worktrees with their build trees, submodule clones and autotest log trees, and local branches nothing needs - after saving anything that removing them would lose. Use at the end of a session that made worktrees or branches, or when the user says the disk is filling up or asks to clean up worktrees or branches.
---

# Clean up after a session

A scratch worktree costs far more than its checkout. It has its own build
tree, `run_autotest.py` gives it a `../buildlogs-<name>` log tree, and the main
repository keeps a clone of every submodule for it under
`.git/worktrees/<name>/modules` (about 0.2 GB on ArduPilot), which nothing
removes until the worktree is removed properly. On 2026-11-14 one machine had
207 forgotten scratch worktrees holding 280 GB, and the main repository's
`.git` had grown to 40 GB around a 1 GB object pack.

The helper is `.codex/skills/cleanup/cleanup.py`. `survey` and `branches`
only read, and write a plan. `apply` carries a plan out, and is the only part
that deletes anything.

## Rules

- **Nothing is deleted without the user's go-ahead**, given in this conversation
  after they have seen the list. The go-ahead covers the list they saw. A
  later survey that finds more needs its own.
- **Never lose the only copy of anything.** `apply` saves before it removes:
  - uncommitted changes as `<name>.patch` and `<name>.status`;
  - untracked files that are not build output or installed playbooks as `<name>-untracked.tgz`;
  - commits on no branch, remote or tag as a `wt-backup/<name>` branch.

  It deletes a branch only when every commit on it sits under a branch head that
  exists on a remote now. That is checked with `ls-remote`, because local
  remote-tracking refs go stale after a force-push.
- **Leave alone anything in use.** That means the primary checkout and any
  worktree that is locked, has a process running inside it, or was touched
  within `--keep-days` (default 2). Another session may be working there.
  For branches, it means any branch that is checked out anywhere, updated
  within `--keep-days`, the head of one of your open PRs, or a protected name.
- **`apply` re-checks every entry against the tree as it is now** and skips
  anything that changed since the survey. A plan more than a day old is
  refused.
- Never use `git clean`, never edit the primary checkout's files, and never
  delete a branch by its short name. `apply` deletes by full ref, because a
  local branch called `origin/x` is displayed as `heads/origin/x`.

## Two scopes

- **This session (default):** the worktrees and branches this session made. You
  know them from the conversation: the `git worktree add` and `git branch` or
  `switch -c` calls you ran. Pass their names with `--only`.
- **Sweep (`--sweep`):** every worktree of every checkout beside this one, the
  same directory the playbooks' sibling worktrees go in. Use it when the user
  asks about disk space or old clutter, not at the end of an ordinary session.

## Workflow

### Step 1: Survey

```bash
python3 .codex/skills/cleanup/cleanup.py survey --only wt-a,wt-b --plan <tmp>/cleanup-worktrees.json
python3 .codex/skills/cleanup/cleanup.py survey --sweep --plan <tmp>/cleanup-worktrees.json
```

Each worktree comes out as one of these:

- **`remove`:** says what would be saved first, or "nothing to save".
- **`prune`:** the directory is already gone and only the registration is left.
- **`review`:** it has more than 100 MB of untracked files to save. Look at them with the user rather than archiving them blind.
- **`keep`:** with the reason.

For a dirty worktree, look at what the change is before calling it scratch.
`git -C <path> diff --stat` is usually enough. An A/B probe or an
instrumentation edit is scratch; a half-finished fix may not be.

### Step 2: Branches

```bash
python3 .codex/skills/cleanup/cleanup.py branches --only name-a,name-b --plan <tmp>/cleanup-branches.json
python3 .codex/skills/cleanup/cleanup.py branches --sweep --protect '^release-' --plan <tmp>/cleanup-branches.json
```

The candidates are branches whose deletion loses nothing. That is not the same as
branches nobody wants. Split them before presenting them:

- Branches a session made can go: dated, prefixed or rebase and squash scratch
  such as `sq/1234`, `r1030/...`, `tmp-...`, or a PR branch's own pre-rebase copy.
- Branches a person named, such as `loiter-backup` or `VTOL-4.6-beta`, stay
  unless the user says otherwise. Losing nothing is not the same as nobody
  wanting them.

When `gh` cannot list your open PRs, each candidate is flagged "PR status
unknown". Check those by hand.

A branch this session made that still has commits on no remote is kept by the
helper. If you know it was superseded, for example squashed into a branch that
was then pushed, show that with `git cherry -v <pushed-branch> <scratch-branch>`
(`-` marks a commit already there). Delete it only with the user's explicit
go-ahead for that branch, after recording its name and sha in the backup
directory.

### Step 3: Present the list and ask

Give the totals first: how much is freed, how many worktrees and branches. Then:

- what is removed outright;
- what is saved first, and how;
- what is kept, and why. Name the in-use ones, so the user knows another session may be running.

Put the long per-entry list in a file and give its path rather than pasting
hundreds of rows. Then ask for the go-ahead, and wait for it.

### Step 4: Apply

Run a dry run first, then the real run:

```bash
python3 .codex/skills/cleanup/cleanup.py apply --plan <tmp>/cleanup-worktrees.json --dry-run
python3 .codex/skills/cleanup/cleanup.py apply --plan <tmp>/cleanup-worktrees.json
python3 .codex/skills/cleanup/cleanup.py apply --plan <tmp>/cleanup-branches.json
```

Remove the worktrees before the branches. A branch stops being checked out
only once its worktree has gone, so survey the branches again after removing
the worktrees.

The backups go to `../cleanup-backups-<date>/`, or wherever `--backup-dir`
points. Each line of output says what happened to one entry: `REMOVED`,
`DELETED`, `PRUNE`, or `SKIP` with the reason. `STOP` means a backup could not
be verified and nothing was removed. `WARN` means something was left behind.

### Step 5: Report

Report:

- what was freed;
- what was kept and why;
- where the backups are, and how to restore one (below).

Also delete the large files this session left in its own temporary
directories: build outputs, ELFs and logs that the conversation has already
used.

On WSL the virtual disk does not shrink by itself. Tell the user to compact
`ext4.vhdx` from Windows after `wsl --shutdown`, using `Optimize-VHD` or
diskpart's `compact vdisk`.

## Restoring

- **A worktree:** `git worktree add ../<name> <branch or sha>` using the line
  from `removed_worktrees.tsv`. Then run `git apply <backup>/<name>.patch` and
  `tar -xzf <backup>/<name>-untracked.tgz` inside it.
- **A branch:** `git branch <name> <sha>` using the line from
  `deleted_branches.tsv`. Its commits are on a remote, and stay in the local
  object store until the next `git gc`.
- **Commits on no branch:** the `wt-backup/<name>` branch keeps them.
