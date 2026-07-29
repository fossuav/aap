#!/usr/bin/env python3
"""
PreToolUse hook for ArduPilot - validates Bash commands against CLAUDE.md rules.

Enforces:
- No Claude/Anthropic co-author in commits
- Commit messages must have subsystem prefix
- No git clean without permission
- No force push to main/master
- No git push without explicit permission
- No git commit --amend without explicit permission
- No git rebase (squash) without explicit permission
- No bypassing the git pre-push hook (--no-verify / core.hooksPath tampering)
- No hiding a guarded command inside a script passed to an interpreter
"""
import os
import sys
import json
import re
import shlex
import subprocess
import time

TOKEN_BASENAME = "push-authorization"

# How the user unlocks a guarded operation, quoted in every refusal message.
_ASK = (
    "The user authorises this by typing:\n"
    "    /prepare-for-push <branch> [--allow %s]\n"
    "Ask them for it and wait - never mint the grant yourself."
)


def _grant():
    """Return the active authorisation token, or None.

    Mirrors .claude/githooks/pre-push. This layer only produces a friendlier,
    earlier refusal; the git hook remains the real enforcement for pushes.
    """
    try:
        # git prints --git-common-dir relative to the directory it ran in, so
        # resolve it against that same directory rather than our own cwd.
        base = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
        r = subprocess.run(["git", "rev-parse", "--git-common-dir"],
                           capture_output=True, text=True, cwd=base)
        if r.returncode != 0:
            return None
        common = os.path.join(base, r.stdout.strip())
        path = os.path.abspath(os.path.join(common, TOKEN_BASENAME))
        with open(path) as f:
            tok = json.load(f)
    except (OSError, ValueError):
        return None
    try:
        if time.time() > float(tok.get("expires_at", 0)):
            return None
    except (TypeError, ValueError):
        return None
    return tok


def _allows(op):
    """True when an unexpired grant covers this operation."""
    tok = _grant()
    if not tok:
        return False
    ops = tok.get("operations", ["push"])
    return op in ops or "*" in ops


def check_git_clean(command):
    """Block git clean commands."""
    if re.search(r'\bgit\s+clean\b', command):
        return (
            "BLOCKED: 'git clean' is prohibited by CLAUDE.md.\n"
            "This removes untracked files which may include important local work.\n"
            "Use 'git checkout' or 'git restore' to discard changes to tracked files."
        )
    return None


def check_push(command):
    """Block any git push not covered by an active user grant."""
    if not re.search(r'\bgit\s+push\b', command):
        return None
    if _allows("push"):
        return None
    return (
        "BLOCKED: git push requires explicit user permission.\n"
        "Rebasing a branch does NOT imply permission to push it.\n" + (_ASK % "push")
    )


def check_commit_amend(command):
    """Block git commit --amend without an active user grant."""
    if not re.search(r'\bgit\s+commit\b', command):
        return None
    if re.search(r'--amend\b', command) and not _allows("amend"):
        return (
            "BLOCKED: git commit --amend requires explicit user permission.\n"
            "Prefer creating a new commit — it is easier to review and revert.\n"
            + (_ASK % "amend")
        )
    return None


def check_rebase_or_squash(command):
    """Block git rebase and git reset without an active user grant."""
    if re.search(r'\bgit\s+rebase\b', command):
        # Allow driving an already-in-progress rebase (resolving conflicts);
        # only a fresh/interactive rebase carries the squash-loses-work risk.
        if re.search(r'\bgit\s+rebase\s+--(continue|skip|abort|quit|edit-todo)\b', command):
            return None
        if _allows("rebase"):
            return None
        return (
            "BLOCKED: git rebase requires explicit user permission.\n"
            "Prefer incremental new commits — squashing can lose work.\n"
            + (_ASK % "rebase")
        )
    if re.search(r'\bgit\s+reset\b', command):
        if _allows("reset"):
            return None
        return (
            "BLOCKED: git reset requires explicit user permission.\n"
            "This can discard commits and staged changes.\n" + (_ASK % "reset")
        )
    return None


def check_commit_coauthor(command):
    """Block commits that list Claude as co-author."""
    if not re.search(r'\bgit\s+commit\b', command):
        return None
    if re.search(
        r'Co-Authored-By\s*:.*(?:Claude|Anthropic|noreply@anthropic)',
        command, re.IGNORECASE
    ):
        return (
            "BLOCKED: Do not list Claude as co-author.\n"
            "CLAUDE.md rule: 'DO NOT list Claude as author or co-author'\n"
            "Remove the Co-Authored-By line and retry the commit."
        )
    return None


def check_commit_prefix(command):
    """Block commits without subsystem prefix in message."""
    if not re.search(r'\bgit\s+commit\b', command):
        return None
    # Skip if no message flag (interactive or --no-edit)
    if not re.search(r'\s-\w*m[\s"]', command):
        return None
    if re.search(r'--no-edit', command):
        return None

    # Extract first line of commit message
    msg = None

    # Try heredoc pattern: <<'EOF' or <<EOF
    heredoc_match = re.search(
        r"<<\s*'?EOF'?\s*\n(.*?)(?:\nEOF|\n\s*EOF)",
        command, re.DOTALL
    )
    if heredoc_match:
        lines = heredoc_match.group(1).strip().split('\n')
        msg = lines[0].strip() if lines else None
    else:
        # Try -m "message" or -m 'message' (handles -am, -cm, etc.)
        simple_match = re.search(r'-\w*m\s+"([^"]*)"', command)
        if not simple_match:
            simple_match = re.search(r"-\w*m\s+'([^']*)'", command)
        if simple_match:
            msg = simple_match.group(1).strip().split('\n')[0].strip()

    if msg:
        # Valid prefix: "Word:" or "Word_Word:" at start of message
        if not re.match(r'^[A-Za-z][A-Za-z0-9_]*:', msg):
            return (
                f"BLOCKED: Commit message must start with a subsystem prefix.\n"
                f"CLAUDE.md examples: 'AP_AHRS:', 'Copter:', 'autotest:', 'scripts:'\n"
                f"Got: '{msg[:70]}'\n"
                f"Fix the commit message to start with the appropriate subsystem prefix."
            )
    return None


def check_hook_bypass(command):
    """Block attempts to defeat the git pre-push hook.

    Each pattern is scoped so that merely *mentioning* a flag or filename - in a
    grep pattern, a heredoc, or a message to the user - is not itself an offence.
    """
    # --no-verify only matters as an argument to the git command that would skip
    # a hook, so require it in the same simple command as git push/commit.
    if re.search(r'\bgit\s+(?:push|commit)\b[^|;&]*?\s--no-verify\b', command):
        return (
            "BLOCKED: --no-verify skips the git pre-push authorisation hook.\n"
            + (_ASK % "push")
        )
    # Only writes that would disable the guard matter. Reading the value back is
    # how you verify the wiring, and pointing it AT .claude/githooks is what the
    # installer does to switch the guard on.
    if re.search(r'\bgit\s+config\b[^|;&]*\bcore\.hooksPath\b', command):
        for part in re.split(r'[|;&]', command):
            if 'core.hooksPath' not in part or 'git' not in part:
                continue
            if re.search(r'--(get|get-all|get-regexp|list)\b', part):
                continue
            if re.search(r'\bcore\.hooksPath\s+["\']?\.claude/githooks["\']?\s*$', part):
                continue
            return (
                "BLOCKED: redirecting or unsetting core.hooksPath disables the git\n"
                "pre-push hook. Ask the user before touching the hook configuration.\n"
                "(Reading it, or setting it to .claude/githooks, is fine.)"
            )
    # The pre-push hook uses these markers to tell a Claude-originated push from
    # a human one, so that the user is never asked for a token in their own
    # terminal. Process ancestry is the primary signal and cannot be forged from
    # a shell, but scrubbing the environment is plainly an attempt to pass as
    # the user. Merely reading the variables stays fine.
    if (re.search(r'\benv\b[^|;&]*\s-u\s+CLAUDE\w*', command)
            or re.search(r'\bunset\s+(?:[A-Za-z_]\w*\s+)*CLAUDE\w*', command)
            or re.search(r'\bCLAUDE(?:CODE|_PID|_CODE_[A-Z_]+)='
                         r'(?:""|\'\')?(?=\s|$)', command)):
        return (
            "BLOCKED: clearing the CLAUDE* environment markers would make a push\n"
            "look like it came from the user rather than from Claude.\n"
            + (_ASK % "push")
        )
    # The token is what the pre-push hook trusts; only grant_push.py may write it.
    # Flag it only alongside something that actually writes, so that reading or
    # naming the token stays fine.
    if (re.search(r'push-authorization', command)
            and 'grant_push.py' not in command
            and re.search(r'(>|>>|\btee\b|\bcp\b|\bmv\b|\bln\b|\btouch\b|\bdd\b'
                          r'|open\s*\([^)]*[\'"]w|\bwrite_text\b|\bjson\.dump\b)',
                          command)):
        return (
            "BLOCKED: the push authorisation token may only be written by\n"
            ".claude/skills/prepare-for-push/grant_push.py, via the user typing\n"
            "/prepare-for-push. Do not create, edit, or copy it directly."
        )
    return None


# Interpreters that take a script path and run whatever is inside it. Wrapping a
# guarded command in such a file used to defeat every check above, because the
# hook only ever saw the wrapper's path.
_INTERPRETERS = {
    "bash", "sh", "zsh", "dash", "ksh", "python", "python3", "perl", "ruby",
}

_SCRIPT_CHECKS = None  # set in main() to avoid a forward reference


def check_script_contents(command):
    """Recurse into a script file passed to an interpreter and check its text.

    Only reads small, local, existing files; anything unreadable is ignored so a
    normal invocation is never blocked by a false positive.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None

    for i, tok in enumerate(tokens):
        base = os.path.basename(tok)
        if base not in _INTERPRETERS:
            continue
        for candidate in tokens[i + 1:]:
            if candidate.startswith("-"):
                continue
            if not os.path.isfile(candidate):
                break
            try:
                if os.path.getsize(candidate) > 256 * 1024:
                    break
                with open(candidate, "r", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                break
            # Check line by line. Scanning the file as one blob would let a guarded
            # word on one line pair up with an exemption (or a bare "git") from an
            # unrelated line, which produced false positives in both directions.
            for n, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                for check in _SCRIPT_CHECKS:
                    error = check(line)
                    if error:
                        return (
                            "BLOCKED: %s line %d contains a command that requires\n"
                            "explicit user permission, and running it via an interpreter\n"
                            "does not bypass that requirement.\n\n  %s\n\n%s"
                            % (candidate, n, line[:120], error)
                        )
            break  # only the first non-flag argument is the script
    return None


def main():
    global _SCRIPT_CHECKS

    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        sys.exit(0)

    # Checks that are meaningful when applied to a script's text as well as to a
    # command line. check_commit_prefix is excluded: it only parses -m arguments.
    _SCRIPT_CHECKS = [
        check_git_clean,
        check_push,
        check_commit_amend,
        check_rebase_or_squash,
        check_commit_coauthor,
        check_hook_bypass,
    ]

    # Run checks in priority order
    for check in [
        check_git_clean,
        check_push,
        check_commit_amend,
        check_rebase_or_squash,
        check_commit_coauthor,
        check_commit_prefix,
        check_hook_bypass,
        check_script_contents,
    ]:
        error = check(command)
        if error:
            print(error, file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
