#!/bin/bash
#
# Uninstall ArduPilot AI Playbooks for Gemini
#
# Run this script from the root of an ArduPilot repository to remove
# GEMINI.md files installed by install-gemini.sh
#
# Usage: curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-gemini.sh | bash
#

set -e

# Check if we're in an ArduPilot repository
if [[ ! -f "wscript" ]] || [[ ! -d "ArduCopter" ]] || [[ ! -d "libraries" ]]; then
    echo "Error: This script must be run from the root of an ArduPilot repository."
    echo ""
    echo "Usage:"
    echo "  cd /path/to/ardupilot"
    echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-gemini.sh | bash"
    exit 1
fi

echo "Removing Gemini playbooks from ArduPilot repository..."

# Remove root GEMINI.md
if [[ -f "GEMINI.md" ]]; then
    rm GEMINI.md
    echo "  Removed: GEMINI.md"
fi

# Remove AP_Scripting GEMINI files
for file in GEMINI.md GEMINI_CRSF_MENU.md GEMINI_VEHICLE_CONTROL.md; do
    dst="libraries/AP_Scripting/$file"
    if [[ -f "$dst" ]]; then
        rm "$dst"
        echo "  Removed: $dst"
    fi
done

# Clean up backup files
for bak in GEMINI.md.bak libraries/AP_Scripting/GEMINI.md.bak libraries/AP_Scripting/GEMINI_CRSF_MENU.md.bak libraries/AP_Scripting/GEMINI_VEHICLE_CONTROL.md.bak; do
    if [[ -f "$bak" ]]; then
        rm "$bak"
        echo "  Removed: $bak"
    fi
done

echo ""
echo "Uninstallation complete!"
