#!/usr/bin/env python3
"""Mint a short-lived push authorisation for .claude/githooks/pre-push.

The pre-push hook refuses every push unless this token exists, is unexpired, and
covers the branch and remote being pushed. Running this script is the act of
authorisation, so it is meant to be reached by the user typing
/prepare-for-push - never by Claude on its own initiative.

    python3 .claude/skills/prepare-for-push/grant_push.py <branch> [branch...]
        [--force] [--minutes N] [--remote NAME] [--revoke] [--status]

--force allows non-fast-forward pushes (needed after a rebase). Force-pushing or
deleting master/main is refused by the hook regardless of what is granted here.
"""
import argparse
import json
import os
import subprocess
import sys
import time

TOKEN_BASENAME = "push-authorization"
DEFAULT_MINUTES = 15


def git(*args):
    try:
        r = subprocess.run(["git"] + list(args), capture_output=True, text=True)
    except OSError:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def token_path():
    d = git("rev-parse", "--git-common-dir") or ".git"
    return os.path.abspath(os.path.join(d, TOKEN_BASENAME))


def describe(branch, remote):
    """One line on what pushing this branch would actually do."""
    if not git("rev-parse", "--verify", "--quiet", branch):
        return "  %-32s ERROR: no such local branch" % branch
    rb = "%s/%s" % (remote, branch)
    if not git("rev-parse", "--verify", "--quiet", rb):
        n = git("rev-list", "--count", branch) or "?"
        return "  %-32s NEW branch on %s (%s commits)" % (branch, remote, n)
    counts = git("rev-list", "--left-right", "--count", "%s...%s" % (rb, branch))
    behind, ahead = (counts.split() + ["?", "?"])[:2]
    ff = subprocess.run(["git", "merge-base", "--is-ancestor", rb, branch],
                        capture_output=True).returncode == 0
    kind = "fast-forward" if ff else "FORCE (rewrites remote history)"
    return "  %-32s +%s/-%s vs %s  %s" % (branch, ahead, behind, rb, kind)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("branches", nargs="*")
    ap.add_argument("--force", action="store_true",
                    help="permit non-fast-forward pushes (after a rebase)")
    ap.add_argument("--allow", default="push",
                    help="comma-separated operations to unlock: push, rebase, "
                         "reset, amend (default: push)")
    ap.add_argument("--minutes", type=int, default=DEFAULT_MINUTES)
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--revoke", action="store_true", help="delete any existing token")
    ap.add_argument("--status", action="store_true", help="show the current token")
    args = ap.parse_args()

    path = token_path()

    if args.revoke:
        if os.path.exists(path):
            os.unlink(path)
            print("push authorisation revoked (%s)" % path)
        else:
            print("no push authorisation was present")
        return 0

    if args.status:
        if not os.path.exists(path):
            print("no push authorisation present - pushes are blocked")
            return 0
        with open(path) as f:
            tok = json.load(f)
        left = int(tok.get("expires_at", 0) - time.time())
        state = "%ds remaining" % left if left > 0 else "EXPIRED %ds ago" % -left
        print("remote:     %s" % tok.get("remote"))
        print("branches:   %s" % ", ".join(tok.get("branches", [])))
        print("operations: %s" % ", ".join(tok.get("operations", ["push"])))
        print("force:      %s" % ("allowed" if tok.get("allow_force") else "not allowed"))
        print("status:     %s" % state)
        return 0

    if not args.branches:
        print("error: name at least one branch to authorise (or --status/--revoke)",
              file=sys.stderr)
        return 2

    if args.minutes < 1 or args.minutes > 120:
        print("error: --minutes must be between 1 and 120", file=sys.stderr)
        return 2

    unknown = [b for b in args.branches
               if b != "*" and not git("rev-parse", "--verify", "--quiet", b)]
    if unknown:
        print("error: no such local branch: %s" % ", ".join(unknown), file=sys.stderr)
        return 2

    known_ops = {"push", "rebase", "reset", "amend"}
    ops = [o.strip() for o in args.allow.split(",") if o.strip()]
    bad = sorted(set(ops) - known_ops - {"*"})
    if bad:
        print("error: unknown operation(s): %s (known: %s)"
              % (", ".join(bad), ", ".join(sorted(known_ops))), file=sys.stderr)
        return 2

    token = {
        "expires_at": time.time() + args.minutes * 60,
        "remote": args.remote,
        "branches": args.branches,
        "operations": ops,
        "allow_force": args.force,
        "granted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(path, "w") as f:
        json.dump(token, f, indent=2)
    os.chmod(path, 0o600)

    print("GIT OPERATIONS AUTHORISED for %d minute(s)" % args.minutes)
    print("  operations: %s" % ", ".join(ops))
    print("  remote:     %s" % args.remote)
    print("  force:      %s" % ("ALLOWED" if args.force else "not allowed"))
    print("  token:      %s" % path)
    print("what pushing these branches would do:")
    for b in args.branches:
        print(describe(b, args.remote))
    print("revoke early with: python3 .claude/skills/prepare-for-push/grant_push.py --revoke")
    return 0


if __name__ == "__main__":
    sys.exit(main())
