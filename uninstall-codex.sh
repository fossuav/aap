#!/bin/bash
#
# Uninstall ArduPilot AI Playbooks for Codex
#
# Run this script from the root of an ArduPilot repository to remove
# AGENTS.override.md files installed by install-codex.sh
#
# Usage: curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-codex.sh | bash
#

set -e

# Check if we're in an ArduPilot repository
if [[ ! -f "wscript" ]] || [[ ! -d "ArduCopter" ]] || [[ ! -d "libraries" ]]; then
    echo "Error: This script must be run from the root of an ArduPilot repository."
    echo ""
    echo "Usage:"
    echo "  cd /path/to/ardupilot"
    echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-codex.sh | bash"
    exit 1
fi

echo "Removing Codex playbooks from ArduPilot repository..."

# Remove root AGENTS.override.md
if [[ -f "AGENTS.override.md" ]]; then
    rm AGENTS.override.md
    echo "  Removed: AGENTS.override.md"
fi

# Remove AP_Scripting playbooks
for file in AGENTS.override.md CODEX_CRSF_MENU.md CODEX_VEHICLE_CONTROL.md; do
    dst="libraries/AP_Scripting/$file"
    if [[ -f "$dst" ]]; then
        rm "$dst"
        echo "  Removed: $dst"
    fi
done

# Remove AP_NavEKF3 playbook
if [[ -f "libraries/AP_NavEKF3/AGENTS.override.md" ]]; then
    rm "libraries/AP_NavEKF3/AGENTS.override.md"
    echo "  Removed: libraries/AP_NavEKF3/AGENTS.override.md"
fi

# Remove AP_HAL_ChibiOS hwdef playbook
if [[ -f "libraries/AP_HAL_ChibiOS/hwdef/AGENTS.override.md" ]]; then
    rm "libraries/AP_HAL_ChibiOS/hwdef/AGENTS.override.md"
    echo "  Removed: libraries/AP_HAL_ChibiOS/hwdef/AGENTS.override.md"
fi

# Remove ArduPlane playbook
if [[ -f "ArduPlane/AGENTS.override.md" ]]; then
    rm "ArduPlane/AGENTS.override.md"
    echo "  Removed: ArduPlane/AGENTS.override.md"
fi

# Remove Tools/autotest playbook
if [[ -f "Tools/autotest/AGENTS.override.md" ]]; then
    rm "Tools/autotest/AGENTS.override.md"
    echo "  Removed: Tools/autotest/AGENTS.override.md"
fi

# Clean up backup files
for bak in AGENTS.override.md.bak \
           libraries/AP_Scripting/AGENTS.override.md.bak \
           libraries/AP_Scripting/CODEX_CRSF_MENU.md.bak \
           libraries/AP_Scripting/CODEX_VEHICLE_CONTROL.md.bak \
           libraries/AP_NavEKF3/AGENTS.override.md.bak \
           libraries/AP_HAL_ChibiOS/hwdef/AGENTS.override.md.bak \
           ArduPlane/AGENTS.override.md.bak \
           Tools/autotest/AGENTS.override.md.bak; do
    if [[ -f "$bak" ]]; then
        rm "$bak"
        echo "  Removed: $bak"
    fi
done

# Remove Codex skills
for skill in boards find-code find-param build-options style-check hwdef-info hwdef-check explain build check autotest sitl lua lua-crsf lua-vehicle log-analyze pr-checks aap-update; do
    if [[ -d ".codex/skills/$skill" ]]; then
        rm -rf ".codex/skills/$skill"
        echo "  Removed: .codex/skills/$skill/"
    fi
done
# Clean up empty skills directory
if [[ -d ".codex/skills" ]] && [[ -z "$(ls -A .codex/skills 2>/dev/null)" ]]; then
    rmdir .codex/skills
fi

echo ""
echo "Uninstallation complete!"
