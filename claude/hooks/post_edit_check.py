#!/usr/bin/env python3
"""
PostToolUse hook for ArduPilot - validates C++ edits against CLAUDE.md rules.

Provides feedback to Claude about:
- printf() usage in flight code (should use gcs().send_text())
"""
import sys
import json


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
