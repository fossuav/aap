#!/usr/bin/env python3
"""
PostToolUse hook for ArduPilot - validates C++ edits against CLAUDE.md rules.

Provides feedback to Claude about:
- printf() usage in flight code (should use gcs().send_text())
- Non-ASCII "smart" punctuation in code (em-dashes, arrows, smart quotes, ...)
  which marks code as machine-written and is rejected by reviewers
"""
import sys
import json


# Decorative Unicode punctuation that has a plain-ASCII equivalent. These do not
# belong in C++ source: identifiers cannot use them, and in comments/strings they
# are a reliable signal that code was machine-generated. Map each to the ASCII
# form the author should have typed.
BANNED_CHARS = {
    "—": "-- or -",        # em dash
    "–": "-",             # en dash
    "‘": "'",             # left single quote
    "’": "'",             # right single quote
    "“": '"',             # left double quote
    "”": '"',             # right double quote
    "…": "...",           # horizontal ellipsis
    "→": "->",            # rightwards arrow
    "←": "<-",            # leftwards arrow
    "↔": "<->",           # left-right arrow
    "⇒": "=>",            # rightwards double arrow
    "•": "* or -",        # bullet
    " ": "a normal space",  # non-breaking space
}


def check_non_ascii(content):
    """Return [(line_number, line_text, [offending_chars])] for banned chars."""
    findings = []
    for i, line in enumerate(content.split("\n"), start=1):
        hits = sorted({ch for ch in line if ch in BANNED_CHARS})
        if hits:
            findings.append((i, line, hits))
    return findings


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {})

    file_path = tool_input.get("file_path", "")

    # Only check C++ files
    if not file_path.endswith(('.cpp', '.h', '.cc')):
        sys.exit(0)

    # Get the new content
    if tool_name == "Edit":
        content = tool_input.get("new_string", "")
    elif tool_name == "Write":
        content = tool_input.get("content", "")
    else:
        sys.exit(0)

    # Check for non-ASCII smart punctuation (em-dash, arrows, smart quotes, ...)
    findings = check_non_ascii(content)
    if findings:
        msg = [
            "WARNING: non-ASCII punctuation detected in C++ code.",
            "CLAUDE.md rule: ASCII only - these characters mark code as machine-written.",
            "Replace each with its plain-ASCII form:",
        ]
        for line_no, text, hits in findings:
            repls = ", ".join("'%s' -> %s" % (ch, BANNED_CHARS[ch]) for ch in hits)
            msg.append("  line %d: %s" % (line_no, repls))
            msg.append("    %s" % text.strip())
        print("\n".join(msg), file=sys.stderr)
        sys.exit(2)

    # Check for printf usage (allow hal.console->printf and comments)
    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('/*'):
            continue
        if 'printf(' in stripped:
            # hal.console->printf is acceptable for debug code
            if 'console->printf' in stripped:
                continue
            print(
                "WARNING: printf() detected in C++ code.\n"
                "CLAUDE.md rule: No printf - use gcs().send_text() for GCS messages.\n"
                "hal.console->printf() is acceptable for debug code compiled out by default.\n"
                "Please replace printf() with the appropriate alternative.",
                file=sys.stderr
            )
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
