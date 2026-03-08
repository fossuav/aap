---
name: style-check
description: Check code style of modified files using astyle and whitespace checks. Use when the user wants to verify formatting before committing.
argument-hint: "[file paths]"
allowed-tools: Bash(astyle *), Bash(git diff *), Bash(git status *), Read
---

# ArduPilot Code Style Check

Check formatting of modified files against ArduPilot's coding standards.

## Workflow

### Step 1: Find modified files

If `$ARGUMENTS` specifies files, check those. Otherwise check all modified files:

```bash
git diff --name-only HEAD
```

Filter to only `.cpp` and `.h` files.

### Step 2: Check trailing whitespace

```bash
git diff --check HEAD
```

This reports any trailing whitespace or space-before-tab issues.

### Step 3: Run astyle dry-run

For each modified C++ file, run astyle in dry-run mode to see what would change:

```bash
astyle --options=Tools/CodeStyle/astylerc --dry-run <file>
```

If astyle reports "Formatted" the file needs changes. "Unchanged" means it passes.

To see the actual formatting diff:

```bash
astyle --options=Tools/CodeStyle/astylerc < <file> | diff <file> -
```

### Step 4: Report results

For each file, report:
- PASS or FAIL for whitespace
- PASS or FAIL for astyle formatting
- Show the specific diffs for any failures

## ArduPilot style rules (summary)

- 4-space indentation (spaces, not tabs)
- LF line endings
- Braces on their own lines
- Spaces after `if`, `for`, `while`, `switch` — not after function names
- No trailing whitespace

## Important

- Only check files that were actually modified, never run astyle on entire unmodified files
- The `--dry-run` flag ensures no files are modified by this check
- If fixes are needed, ask the user before applying them
