#!/bin/bash
#
# Install ArduPilot AI Playbooks for Claude Code
#
# Run this script from the root of an ArduPilot repository to install
# CLAUDE.md files that guide Claude Code when working with the codebase.
#
# Usage: /path/to/aap/install-claude.sh
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$SCRIPT_DIR/claude"

# Check if we're in an ArduPilot repository
if [[ ! -f "wscript" ]] || [[ ! -d "ArduCopter" ]] || [[ ! -d "libraries" ]]; then
    echo "Error: This script must be run from the root of an ArduPilot repository."
    echo "Usage: cd /path/to/ardupilot && /path/to/aap/install-claude.sh"
    exit 1
fi

# Check if source files exist
if [[ ! -d "$CLAUDE_DIR" ]]; then
    echo "Error: Claude playbook directory not found at $CLAUDE_DIR"
    exit 1
fi

echo "Installing Claude Code playbooks to ArduPilot repository..."

# Install root CLAUDE.md
if [[ -f "CLAUDE.md" ]]; then
    echo "  Backing up existing CLAUDE.md to CLAUDE.md.bak"
    cp CLAUDE.md CLAUDE.md.bak
fi
cp "$CLAUDE_DIR/CLAUDE.md" ./CLAUDE.md
echo "  Installed: CLAUDE.md"

# Install AP_Scripting CLAUDE files
mkdir -p libraries/AP_Scripting

for file in CLAUDE.md CLAUDE_CRSF_MENU.md CLAUDE_VEHICLE_CONTROL.md; do
    src="$CLAUDE_DIR/libraries/AP_Scripting/$file"
    dst="libraries/AP_Scripting/$file"
    if [[ -f "$src" ]]; then
        if [[ -f "$dst" ]]; then
            echo "  Backing up existing $dst to ${dst}.bak"
            cp "$dst" "${dst}.bak"
        fi
        cp "$src" "$dst"
        echo "  Installed: $dst"
    fi
done

echo ""
echo "Installation complete!"
echo ""
echo "The following files are now available for Claude Code:"
echo "  - CLAUDE.md (root - build system, architecture, C++ guidelines)"
echo "  - libraries/AP_Scripting/CLAUDE.md (Lua scripting patterns)"
echo "  - libraries/AP_Scripting/CLAUDE_CRSF_MENU.md (CRSF menu implementation)"
echo "  - libraries/AP_Scripting/CLAUDE_VEHICLE_CONTROL.md (vehicle control APIs)"
echo ""
echo "Note: These files are in .gitignore and won't be committed to ArduPilot."
echo "To remove them, run: /path/to/aap/uninstall-claude.sh"
