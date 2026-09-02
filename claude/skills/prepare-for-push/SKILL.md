---
name: prepare-for-push
description: Authorise Claude to push specific branches to a remote. Pushes are blocked by a git pre-push hook until this grants a short-lived, branch-scoped token.
argument-hint: "<branch> [more branches...] [--force]"
disable-model-invocation: true
allowed-tools: Bash(python3 *grant_push.py*), Bash(git push *), Bash(git log *), Bash(git status *), Bash(git rev-list *), Bash(git diff *), Read
---

# Authorise a push

`.claude/githooks/pre-push` refuses every push unless an unexpired, branch-scoped
authorisation token exists. This skill mints that token. **The user types
`/prepare-for-push` - Claude must never invoke it** (hence
`disable-model-invocation: true`). Claude's job is to ask for it and wait.

## Argument parsing

`$ARGUMENTS` is a list of branch names plus optional flags:

- `/prepare-for-push pr-my-branch` - authorise a fast-forward push of one branch
- `/prepare-for-push pr-a pr-b --force` - two branches, force allowed (after a rebase)
- `/prepare-for-push pr-a --allow push,rebase` - also unlock local history rewriting
- `/prepare-for-push --status` - show the current authorisation
- `/prepare-for-push --revoke` - cancel it immediately

If no branch is named, default to the current branch and say so.

`--allow` takes any of `push`, `rebase`, `reset`, `amend` and defaults to `push`
alone. Squashing `/pr-review` fixes back into the commits that introduced them is
the common reason to need more than `push`, and it wants `--allow push,rebase,amend`. `pre_bash_check.py` blocks each of those operations until a grant covers
it, so a task that rebases a stack and then pushes it wants
`--allow push,rebase,amend`. Grant the narrowest set that does the job.

## Workflow

### Step 0: Has the branch been reviewed?

If the push would publish a branch that is about to become a PR - or update one
that is already under review - check whether `/pr-review` has run at this head:

```bash
python3 .claude/skills/pr-review/pr_review.py state diff
```

Exit 0 means the branch was reviewed at exactly this commit. Anything else means
it was not, and Claude should say so and offer to run `/pr-review` first. This is a
prompt, not a gate: the user may well be pushing work in progress, a checkpoint, or
a branch nobody is going to review, and none of those need a review pass. Mint the
token if they want it minted.

### Step 1: Show what the push would actually do

Before minting anything, put the change in front of the user:

```bash
git status -sb
git log --oneline <remote>/<branch>..<branch>
git rev-list --left-right --count <remote>/<branch>...<branch>
```

Call out explicitly when a push would be a **force** (non-fast-forward), which
branches are affected, and how many commits move. If the user named a branch
whose push would rewrite published history and they did not pass `--force`, say
so rather than quietly adding the flag.

If `--allow` includes `rebase` and the branch is already on the remote, the push
that follows the rebase will not be a fast-forward either. Say so and ask for
`--force` before minting, rather than discovering it when the push is refused.

### Step 2: Mint the token

```bash
python3 .claude/skills/prepare-for-push/grant_push.py <branch> [branch...] [--force] [--minutes N]
```

Defaults: remote `origin`, 15 minutes, force **not** allowed. The script prints a
per-branch summary of what pushing would do; relay anything surprising in it.

### Step 3: Push, then confirm

```bash
git push origin <branch>                      # fast-forward
git push --force-with-lease origin <branch>   # after a rebase
```

Always prefer `--force-with-lease` over `--force` so the push aborts if the remote
moved since your last fetch.

Afterwards, report the resulting remote SHA per branch, and revoke if more time is
left than the work needs:

```bash
python3 .claude/skills/prepare-for-push/grant_push.py --revoke
```

## What the token cannot do

- Force-pushing or deleting `master`/`main` is refused by the hook unconditionally.
  No token overrides it.
- The token is scoped to the branches named and to one remote. Pushing anything
  else needs a fresh grant.
- It expires. A grant for one push does not silently authorise later work.

## Your own pushes are not affected

The git hook only asks for a token when the push comes from inside a Claude Code
session. It works this out from the process tree - a push started by Claude is a
descendant of the `claude` process - falling back to the `CLAUDE*` environment
markers where `/proc` is unavailable. Pushing from your own terminal needs no
grant and never has.

The one thing the hook still questions for a human is a force-push or delete of
`master`/`main`, since that is rarely what anyone wants. Wave it through with
`git push --no-verify` if you do mean it. For Claude that same case is refused
outright and no token overrides it.

Note that a push you start in-session with the `!` prefix is a descendant of
`claude` too, so it is treated as a Claude push and wants a grant. Push from a
normal terminal to avoid that.

## Honest limits

This is a guardrail against unrequested and accidental pushes, not a security
boundary. `Bash(python3 *)` is granted in `settings.json`, so an agent that
decided to ignore the rules could run `grant_push.py` itself. Two things make that
visible rather than silent: the grant prints a loud audit block, and
`pre_bash_check.py` blocks `git push --no-verify` and refuses interpreter-invoked
scripts that contain guarded git commands.

If you want the grant to be unambiguously yours, run it yourself in the session
with the `!` prefix instead of letting Claude run it:

```
! python3 .claude/skills/prepare-for-push/grant_push.py pr-my-branch --force
```
