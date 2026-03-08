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

# Function to download a file
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

echo "Installing Claude Code playbooks to ArduPilot repository..."

# Install root CLAUDE.md
if [[ -f "CLAUDE.md" ]]; then
    echo "  Backing up existing CLAUDE.md to CLAUDE.md.bak"
    cp CLAUDE.md CLAUDE.md.bak
fi
download_file "$REPO_URL/CLAUDE.md" "./CLAUDE.md"
echo "  Installed: CLAUDE.md"

# Install AP_Scripting CLAUDE files
mkdir -p libraries/AP_Scripting

for file in CLAUDE.md CLAUDE_CRSF_MENU.md CLAUDE_VEHICLE_CONTROL.md; do
    dst="libraries/AP_Scripting/$file"
    if [[ -f "$dst" ]]; then
        echo "  Backing up existing $dst to ${dst}.bak"
        cp "$dst" "${dst}.bak"
    fi
    download_file "$REPO_URL/libraries/AP_Scripting/$file" "$dst"
    echo "  Installed: $dst"
done

# Install AP_NavEKF3 CLAUDE file
mkdir -p libraries/AP_NavEKF3

dst="libraries/AP_NavEKF3/CLAUDE.md"
if [[ -f "$dst" ]]; then
    echo "  Backing up existing $dst to ${dst}.bak"
    cp "$dst" "${dst}.bak"
fi
download_file "$REPO_URL/libraries/AP_NavEKF3/CLAUDE.md" "$dst"
echo "  Installed: $dst"

# Install AP_HAL_ChibiOS hwdef CLAUDE file
mkdir -p libraries/AP_HAL_ChibiOS/hwdef

dst="libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md"
if [[ -f "$dst" ]]; then
    echo "  Backing up existing $dst to ${dst}.bak"
    cp "$dst" "${dst}.bak"
fi
download_file "$REPO_URL/libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md" "$dst"
echo "  Installed: $dst"

# Install ArduPlane CLAUDE file
mkdir -p ArduPlane

dst="ArduPlane/CLAUDE.md"
if [[ -f "$dst" ]]; then
    echo "  Backing up existing $dst to ${dst}.bak"
    cp "$dst" "${dst}.bak"
fi
download_file "$REPO_URL/ArduPlane/CLAUDE.md" "$dst"
echo "  Installed: $dst"

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
for skill in boards find-param build-options style-check hwdef-info explain build check autotest sitl; do
    mkdir -p ".claude/skills/$skill"
    dst=".claude/skills/$skill/SKILL.md"
    download_file "$SKILLS_URL/$skill/SKILL.md" "$dst"
    echo "  Installed: $dst"
done

# log-analyze skill (has additional Python tool)
mkdir -p .claude/skills/log-analyze
for file in SKILL.md log_extract.py; do
    dst=".claude/skills/log-analyze/$file"
    download_file "$SKILLS_URL/log-analyze/$file" "$dst"
    echo "  Installed: $dst"
done
chmod +x .claude/skills/log-analyze/log_extract.py

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
echo "  - /log-analyze    - Analyze DataFlash .bin log files"
echo ""
echo "To uninstall, run:"
echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-claude.sh | bash"
