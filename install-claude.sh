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

# Install Claude Code settings (project-level, shared permissions)
mkdir -p .claude
dst=".claude/settings.json"
if [[ -f "$dst" ]]; then
    echo "  Note: .claude/settings.json already exists, not overwriting"
    echo "  To update, remove it first and re-run this script"
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

# autotest skill (has additional Python tool for parsing results)
mkdir -p .claude/skills/autotest
for file in SKILL.md autotest_results.py; do
    install_file "$SKILLS_URL/autotest/$file" ".claude/skills/autotest/$file"
done
chmod +x .claude/skills/autotest/autotest_results.py

# log-analyze skill (has additional Python tool)
mkdir -p .claude/skills/log-analyze
for file in SKILL.md log_extract.py; do
    install_file "$SKILLS_URL/log-analyze/$file" ".claude/skills/log-analyze/$file"
done
chmod +x .claude/skills/log-analyze/log_extract.py

# Install Claude Code hooks (rule enforcement)
echo ""
echo "Installing Claude Code hooks..."

HOOKS_URL="$REPO_URL/hooks"
mkdir -p .claude/hooks

for hook in pre_bash_check.py post_edit_check.py; do
    install_file "$HOOKS_URL/$hook" ".claude/hooks/$hook"
    chmod +x ".claude/hooks/$hook"
done

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
echo "  - /explain        - Explain ArduPilot code and architecture"
echo "  - /build          - Configure and build firmware"
echo "  - /check          - Build and run unit tests"
echo "  - /autotest       - Run SITL integration tests"
echo "  - /sitl           - Launch SITL simulator"
echo "  - /lua             - Write or modify Lua applets"
echo "  - /lua-crsf        - Write CRSF transmitter menu scripts"
echo "  - /lua-vehicle     - Lua vehicle control and movement commands"
echo "  - /log-analyze    - Analyze DataFlash .bin log files"
echo "  - /aap-update     - Check for and install playbook updates"
echo ""
echo "  Hooks (rule enforcement):"
echo "  - pre_bash_check  - Blocks git clean, force push, bad commit messages"
echo "  - post_edit_check - Warns about printf() in C++ code"
echo ""
echo "NOTE: Each skill will ask for approval on first use. Select"
echo "  'Yes, and don't ask again' to permanently approve it."
echo ""
echo "To uninstall, run:"
echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-claude.sh | bash"
