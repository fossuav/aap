#!/bin/bash
#
# Install ArduPilot AI Playbooks for Claude Code
#
# Run this script from the root of an ArduPilot repository to install
# CLAUDE.md files that guide Claude Code when working with the codebase.
#
# Usage: curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/install-claude.sh | bash
#

set -e

REPO_URL="https://raw.githubusercontent.com/fossuav/aap/main/claude"

# Check if we're in an ArduPilot repository
if [[ ! -f "wscript" ]] || [[ ! -d "ArduCopter" ]] || [[ ! -d "libraries" ]]; then
    echo "Error: This script must be run from the root of an ArduPilot repository."
    echo ""
    echo "Usage:"
    echo "  cd /path/to/ardupilot"
    echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/install-claude.sh | bash"
    exit 1
fi

# Function to download a URL to a destination path
download_file() {
    local url="$1"
    local dest="$2"

    if command -v curl &> /dev/null; then
        curl -fsSL "$url" -o "$dest"
    elif command -v wget &> /dev/null; then
        wget -q "$url" -O "$dest"
    else
        echo "Error: curl or wget is required but not installed."
        exit 1
    fi
}

# Download a file and install it at the destination, skipping the backup +
# overwrite when the existing file already matches what we just downloaded.
install_file() {
    local url="$1"
    local dest="$2"
    local tmp
    tmp=$(mktemp)
    download_file "$url" "$tmp"

    if [[ -f "$dest" ]]; then
        if cmp -s "$tmp" "$dest"; then
            echo "  Unchanged: $dest"
            rm -f "$tmp"
            return
        fi
        cp "$dest" "${dest}.bak"
        echo "  Backed up existing $dest to ${dest}.bak"
    fi

    mv "$tmp" "$dest"
    echo "  Installed: $dest"
}

echo "Installing Claude Code playbooks to ArduPilot repository..."

# Install root CLAUDE.md
install_file "$REPO_URL/CLAUDE.md" "./CLAUDE.md"

# Install AP_Scripting CLAUDE files
mkdir -p libraries/AP_Scripting

for file in CLAUDE.md CLAUDE_CRSF_MENU.md CLAUDE_VEHICLE_CONTROL.md; do
    install_file "$REPO_URL/libraries/AP_Scripting/$file" "libraries/AP_Scripting/$file"
done

# Install AP_NavEKF3 CLAUDE file
mkdir -p libraries/AP_NavEKF3
install_file "$REPO_URL/libraries/AP_NavEKF3/CLAUDE.md" "libraries/AP_NavEKF3/CLAUDE.md"

# Install AP_HAL_ChibiOS hwdef CLAUDE file
mkdir -p libraries/AP_HAL_ChibiOS/hwdef
install_file "$REPO_URL/libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md" "libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md"

# Install ArduPlane CLAUDE file
mkdir -p ArduPlane
install_file "$REPO_URL/ArduPlane/CLAUDE.md" "ArduPlane/CLAUDE.md"

# Install Tools/autotest CLAUDE file
mkdir -p Tools/autotest
install_file "$REPO_URL/Tools/autotest/CLAUDE.md" "Tools/autotest/CLAUDE.md"

# Install Claude Code settings (project-level permissions + hooks). Never
# overwrite an existing settings.json - permissions are the user's call. When the
# playbook ships permission/hook changes, the user updates it deliberately:
# compare against the canonical copy and merge what they want.
mkdir -p .claude
dst=".claude/settings.json"
if [[ -f "$dst" ]]; then
    echo "  Note: .claude/settings.json already exists, not overwriting (permissions are user-managed)"
    echo "  To adopt playbook changes, diff it against $REPO_URL/settings.json and merge by hand"
else
    download_file "$REPO_URL/settings.json" "$dst"
    echo "  Installed: $dst"
fi

# Install Claude Code skills
echo ""
echo "Installing Claude Code skills..."

SKILLS_URL="$REPO_URL/skills"

# Skills with only SKILL.md
for skill in boards find-code find-param build-options style-check hwdef-info explain build check sitl lua lua-crsf lua-vehicle aap-update; do
    mkdir -p ".claude/skills/$skill"
    install_file "$SKILLS_URL/$skill/SKILL.md" ".claude/skills/$skill/SKILL.md"
done

# hwdef-check skill (has additional Python tool)
mkdir -p .claude/skills/hwdef-check
for file in SKILL.md hwdef_check.py; do
    install_file "$SKILLS_URL/hwdef-check/$file" ".claude/skills/hwdef-check/$file"
done
chmod +x .claude/skills/hwdef-check/hwdef_check.py

# autotest skill (has additional Python tools: results parser + timed runner)
mkdir -p .claude/skills/autotest
for file in SKILL.md autotest_results.py run_autotest.py; do
    install_file "$SKILLS_URL/autotest/$file" ".claude/skills/autotest/$file"
done
chmod +x .claude/skills/autotest/autotest_results.py .claude/skills/autotest/run_autotest.py

# log-analyze skill (has additional Python tools)
mkdir -p .claude/skills/log-analyze
for file in SKILL.md log_extract.py flow_cal_check.py log_health.py thrust_check.py \
            gyro_fft.py rate_response.py filter_phase.py baro_thst_cal.py rate_band.py batch_fft.py; do
    install_file "$SKILLS_URL/log-analyze/$file" ".claude/skills/log-analyze/$file"
done
chmod +x .claude/skills/log-analyze/log_extract.py .claude/skills/log-analyze/flow_cal_check.py \
    .claude/skills/log-analyze/log_health.py .claude/skills/log-analyze/thrust_check.py \
    .claude/skills/log-analyze/gyro_fft.py .claude/skills/log-analyze/rate_response.py \
    .claude/skills/log-analyze/filter_phase.py .claude/skills/log-analyze/baro_thst_cal.py \
    .claude/skills/log-analyze/rate_band.py .claude/skills/log-analyze/batch_fft.py

# pr-checks skill (has additional Python tool)
mkdir -p .claude/skills/pr-checks
for file in SKILL.md ci_failures.py; do
    install_file "$SKILLS_URL/pr-checks/$file" ".claude/skills/pr-checks/$file"
done
chmod +x .claude/skills/pr-checks/ci_failures.py

# pr-review skill (has the scope/checks/codex-pool helper)
mkdir -p .claude/skills/pr-review
for file in SKILL.md pr_review.py; do
    install_file "$SKILLS_URL/pr-review/$file" ".claude/skills/pr-review/$file"
done
chmod +x .claude/skills/pr-review/pr_review.py

# prepare-for-push skill (has the authorisation minter used by the git pre-push hook)
mkdir -p .claude/skills/prepare-for-push
for file in SKILL.md grant_push.py; do
    install_file "$SKILLS_URL/prepare-for-push/$file" ".claude/skills/prepare-for-push/$file"
done
chmod +x .claude/skills/prepare-for-push/grant_push.py

# Install Claude Code hooks (rule enforcement)
echo ""
echo "Installing Claude Code hooks..."

HOOKS_URL="$REPO_URL/hooks"
mkdir -p .claude/hooks

for hook in pre_bash_check.py post_edit_check.py; do
    install_file "$HOOKS_URL/$hook" ".claude/hooks/$hook"
    chmod +x ".claude/hooks/$hook"
done

# Install the git-level pre-push hook. A Claude Code PreToolUse hook only sees the
# command string, so wrapping "git push" in a script defeats it; git runs this one
# itself, so it cannot be sidestepped that way. It refuses every push until the
# user authorises one with /prepare-for-push.
echo ""
echo "Installing git pre-push hook..."

mkdir -p .claude/githooks
install_file "$REPO_URL/githooks/pre-push" ".claude/githooks/pre-push"
chmod +x .claude/githooks/pre-push

# core.hooksPath is local git config, so it is per-clone and not carried by a
# clone or a fresh worktree - point it at the playbook's hooks directory here.
if git rev-parse --git-dir > /dev/null 2>&1; then
    existing=$(git config --get core.hooksPath || true)
    if [[ -z "$existing" ]]; then
        git config core.hooksPath .claude/githooks
        echo "  Set core.hooksPath = .claude/githooks"
    elif [[ "$existing" == ".claude/githooks" ]]; then
        echo "  core.hooksPath already set to .claude/githooks"
    else
        echo "  WARNING: core.hooksPath is already set to '$existing', leaving it alone."
        echo "           The pre-push guard will NOT run until you either move"
        echo "           .claude/githooks/pre-push into '$existing', or run:"
        echo "               git config core.hooksPath .claude/githooks"
    fi
else
    echo "  Note: not a git repository, skipping core.hooksPath setup"
fi

echo ""
echo "Installation complete!"
echo ""
echo "The following files are now available for Claude Code:"
echo ""
echo "  Playbooks (CLAUDE.md files):"
echo "  - CLAUDE.md (root - build system, architecture, C++ guidelines)"
echo "  - libraries/AP_Scripting/CLAUDE.md (Lua scripting patterns)"
echo "  - libraries/AP_Scripting/CLAUDE_CRSF_MENU.md (CRSF menu implementation)"
echo "  - libraries/AP_Scripting/CLAUDE_VEHICLE_CONTROL.md (vehicle control APIs)"
echo "  - libraries/AP_NavEKF3/CLAUDE.md (EKF3 navigation filter reference)"
echo "  - libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md (ChibiOS board porting)"
echo "  - ArduPlane/CLAUDE.md (Plane log analysis, flight modes, QuadPlane)"
echo "  - Tools/autotest/CLAUDE.md (autotest authoring conventions, Lua applet patterns)"
echo ""
echo "  Skills (slash commands):"
echo "  - /boards         - List and search available board targets"
echo "  - /find-param     - Find parameter definitions in source code"
echo "  - /build-options  - Search compile-time feature flags"
echo "  - /style-check    - Check code style of modified files"
echo "  - /hwdef-info     - Show board hardware definitions"
echo "  - /hwdef-check    - Review an hwdef PR (DMA, board ID, files, commits, playbook)"
echo "  - /explain        - Explain ArduPilot code and architecture"
echo "  - /build          - Configure and build firmware"
echo "  - /check          - Build and run unit tests"
echo "  - /autotest       - Run SITL integration tests"
echo "  - /sitl           - Launch SITL simulator"
echo "  - /lua             - Write or modify Lua applets"
echo "  - /lua-crsf        - Write CRSF transmitter menu scripts"
echo "  - /lua-vehicle     - Lua vehicle control and movement commands"
echo "  - /log-analyze    - Analyze DataFlash .bin log files"
echo "  - /pr-checks      - Download a PR's failing CI checks and identify failing tests"
echo "  - /pr-review      - Review your own PR before a maintainer does, and fix it"
echo "  - /aap-update     - Check for and install playbook updates"
echo "  - /prepare-for-push - Authorise Claude to push named branches (you invoke this)"
echo ""
echo "  Hooks (rule enforcement):"
echo "  - pre_bash_check  - Blocks git clean, bad commit messages, and unauthorised"
echo "                      push/rebase/reset/amend, including inside helper scripts"
echo "  - post_edit_check - Warns about printf() in C++ code"
echo "  - githooks/pre-push - Git-level guard: refuses any push without a grant from"
echo "                      /prepare-for-push, and always refuses force-push to master"
echo ""
echo "Pushes are now blocked by default. When Claude needs to push, it will ask you"
echo "to run:  /prepare-for-push <branch> [--force]"
echo ""
echo "NOTE: Each skill will ask for approval on first use. Select"
echo "  'Yes, and don't ask again' to permanently approve it."
echo ""
echo "To uninstall, run:"
echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-claude.sh | bash"
