#!/bin/bash
#
# Uninstall ArduPilot AI Playbooks for Claude Code
#
# Run this script from the root of an ArduPilot repository to remove
# CLAUDE.md files installed by install-claude.sh
#
# Usage: /path/to/aap/uninstall-claude.sh
#

set -e

# Check if we're in an ArduPilot repository
if [[ ! -f "wscript" ]] || [[ ! -d "ArduCopter" ]] || [[ ! -d "libraries" ]]; then
    echo "Error: This script must be run from the root of an ArduPilot repository."
    echo "Usage: cd /path/to/ardupilot && /path/to/aap/uninstall-claude.sh"
    exit 1
fi

echo "Removing Claude Code playbooks from ArduPilot repository..."

# Remove root CLAUDE.md
if [[ -f "CLAUDE.md" ]]; then
    rm CLAUDE.md
    echo "  Removed: CLAUDE.md"
fi

# Remove AP_Scripting CLAUDE files
for file in CLAUDE.md CLAUDE_CRSF_MENU.md CLAUDE_VEHICLE_CONTROL.md; do
    dst="libraries/AP_Scripting/$file"
    if [[ -f "$dst" ]]; then
        rm "$dst"
        echo "  Removed: $dst"
    fi
done

# Remove backup files if user wants
if [[ -f "CLAUDE.md.bak" ]] || [[ -f "libraries/AP_Scripting/CLAUDE.md.bak" ]]; then
    echo ""
    read -p "Remove backup files (.bak) as well? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -f CLAUDE.md.bak
        rm -f libraries/AP_Scripting/CLAUDE.md.bak
        rm -f libraries/AP_Scripting/CLAUDE_CRSF_MENU.md.bak
        rm -f libraries/AP_Scripting/CLAUDE_VEHICLE_CONTROL.md.bak
        echo "  Removed backup files"
    fi
fi

echo ""
echo "Uninstallation complete!"
