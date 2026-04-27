---
name: aap-update
description: Check the local ArduPilot AI Playbook version against the upstream GitHub version and update if newer. Use when the user asks to update the playbooks, check for playbook updates, or wants to know which version is installed.
disable-model-invocation: true
allowed-tools: Bash(grep:*), Bash(curl:*), Bash(wget:*), Bash(sort:*), Bash(test:*), Bash(bash:*), Read
---

# Update ArduPilot AI Playbooks

Compares the `**Playbook version:**` line in the local `CLAUDE.md` against the same line in the upstream `claude/CLAUDE.md` on GitHub, and re-runs `install-claude.sh` if the upstream is newer.

## Workflow

### Step 1: Read the local version

The root playbook lives at `./CLAUDE.md` in an ArduPilot checkout.

```bash
LOCAL=$(grep -m1 '^\*\*Playbook version:\*\*' ./CLAUDE.md | sed 's/^\*\*Playbook version:\*\* *//')
echo "Local: ${LOCAL:-<not found>}"
```

If `LOCAL` is empty, the installed playbook predates versioning. Treat that as "older than any tagged version" and recommend updating.

### Step 2: Fetch the upstream version

```bash
REMOTE=$(curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/claude/CLAUDE.md \
    | grep -m1 '^\*\*Playbook version:\*\*' \
    | sed 's/^\*\*Playbook version:\*\* *//')
echo "Remote: ${REMOTE:-<not found>}"
```

If the fetch fails, report the error and stop — do not attempt to update.

### Step 3: Compare and report

- If `LOCAL` equals `REMOTE`: report "Playbooks up to date (version $LOCAL)" and stop.
- If they differ: use `sort -V` to determine ordering:
  ```bash
  NEWER=$(printf '%s\n%s\n' "$LOCAL" "$REMOTE" | sort -V | tail -n1)
  ```
  - If `NEWER` equals `REMOTE` and `LOCAL` != `REMOTE`: upstream is ahead — proceed to step 4.
  - Otherwise (local is ahead, or versions are unorderable): report both versions and ask the user how to proceed. Do not auto-update.

### Step 4: Confirm and run the installer

Show the user the version delta (`$LOCAL → $REMOTE`) and confirm before running:

```bash
curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/install-claude.sh | bash
```

The installer downloads each file, diffs against the existing copy, and only writes a `.bak` and replaces the file when the contents actually changed. Files that are unchanged upstream are left alone.

### Step 5: Verify

After the installer finishes, re-read `./CLAUDE.md` and confirm the version line now matches the upstream version.

## Notes

- This skill must be run from the root of an ArduPilot checkout (the same directory layout `install-claude.sh` requires).
- The version line format is exactly `**Playbook version:** X.Y.Z` near the top of `claude/CLAUDE.md` upstream and `CLAUDE.md` locally.
- The skill never touches `.claude/settings.json` — the installer leaves that file alone if it already exists.
