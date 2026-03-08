#!/bin/bash
#
# Uninstall ArduPilot AI Playbooks for Claude Code
#
# Run this script from the root of an ArduPilot repository to remove
# CLAUDE.md files installed by install-claude.sh
#
# Usage: curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-claude.sh | bash
#

set -e

# Check if we're in an ArduPilot repository
if [[ ! -f "wscript" ]] || [[ ! -d "ArduCopter" ]] || [[ ! -d "libraries" ]]; then
    echo "Error: This script must be run from the root of an ArduPilot repository."
    echo ""
    echo "Usage:"
    echo "  cd /path/to/ardupilot"
    echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-claude.sh | bash"
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

# Remove AP_NavEKF3 CLAUDE file
if [[ -f "libraries/AP_NavEKF3/CLAUDE.md" ]]; then
    rm "libraries/AP_NavEKF3/CLAUDE.md"
    echo "  Removed: libraries/AP_NavEKF3/CLAUDE.md"
fi

# Remove AP_HAL_ChibiOS hwdef CLAUDE file
if [[ -f "libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md" ]]; then
    rm "libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md"
    echo "  Removed: libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md"
fi

# Remove ArduPlane CLAUDE file
if [[ -f "ArduPlane/CLAUDE.md" ]]; then
    rm "ArduPlane/CLAUDE.md"
    echo "  Removed: ArduPlane/CLAUDE.md"
fi

# Clean up backup files
for bak in CLAUDE.md.bak \
           libraries/AP_Scripting/CLAUDE.md.bak \
           libraries/AP_Scripting/CLAUDE_CRSF_MENU.md.bak \
           libraries/AP_Scripting/CLAUDE_VEHICLE_CONTROL.md.bak \
           libraries/AP_NavEKF3/CLAUDE.md.bak \
           libraries/AP_HAL_ChibiOS/hwdef/CLAUDE.md.bak \
           ArduPlane/CLAUDE.md.bak; do
    if [[ -f "$bak" ]]; then
        rm "$bak"
        echo "  Removed: $bak"
    fi
done

# Remove Claude Code skills
for skill in boards find-param build-options style-check hwdef-info explain build check autotest sitl log-analyze; do
    if [[ -d ".claude/skills/$skill" ]]; then
        rm -rf ".claude/skills/$skill"
        echo "  Removed: .claude/skills/$skill/"
    fi
done
# Clean up empty skills directory
if [[ -d ".claude/skills" ]] && [[ -z "$(ls -A .claude/skills 2>/dev/null)" ]]; then
    rmdir .claude/skills
fi

echo ""
echo "Uninstallation complete!"
