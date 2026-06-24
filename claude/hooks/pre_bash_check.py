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
"""
import sys
import json
import re


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
    """Block any git push without explicit permission."""
    if re.search(r'\bgit\s+push\b', command):
        return (
            "BLOCKED: git push requires explicit user permission.\n"
            "Prefer incremental new commits — they are easier to review and revert.\n"
            "Ask the user before pushing."
        )
    return None


def check_commit_amend(command):
    """Block git commit --amend without explicit permission."""
    if not re.search(r'\bgit\s+commit\b', command):
        return None
    if re.search(r'--amend\b', command):
        return (
            "BLOCKED: git commit --amend requires explicit user permission.\n"
            "Prefer creating a new commit — it is easier to review and revert.\n"
            "Ask the user before amending."
        )
    return None


def check_rebase_or_squash(command):
    """Block git rebase and git reset used for squashing."""
    if re.search(r'\bgit\s+rebase\b', command):
        # Allow driving an already-in-progress rebase (resolving conflicts);
        # only a fresh/interactive rebase carries the squash-loses-work risk.
        if re.search(r'\bgit\s+rebase\s+--(continue|skip|abort|quit|edit-todo)\b', command):
            return None
        return (
            "BLOCKED: git rebase requires explicit user permission.\n"
            "Prefer incremental new commits — squashing can lose work.\n"
            "Ask the user before rebasing."
        )
    if re.search(r'\bgit\s+reset\b', command):
        return (
            "BLOCKED: git reset requires explicit user permission.\n"
            "This can discard commits and staged changes.\n"
            "Ask the user before resetting."
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


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")

    if not command:
        sys.exit(0)

    # Run checks in priority order
    for check in [
        check_git_clean,
        check_push,
        check_commit_amend,
        check_rebase_or_squash,
        check_commit_coauthor,
        check_commit_prefix,
    ]:
        error = check(command)
        if error:
            print(error, file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
