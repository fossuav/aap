#!/bin/bash
#
# Install ArduPilot AI Playbooks for Codex
#
# Run this script from the root of an ArduPilot repository to install
# AGENTS.override.md files that guide Codex when working with the codebase.
#
# Usage: curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/install-codex.sh | bash
#

set -e

REPO_URL="https://raw.githubusercontent.com/fossuav/aap/main/codex"

# Check if we're in an ArduPilot repository
if [[ ! -f "wscript" ]] || [[ ! -d "ArduCopter" ]] || [[ ! -d "libraries" ]]; then
    echo "Error: This script must be run from the root of an ArduPilot repository."
    echo ""
    echo "Usage:"
    echo "  cd /path/to/ardupilot"
    echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/install-codex.sh | bash"
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

echo "Installing Codex playbooks to ArduPilot repository..."

# Install root AGENTS.override.md
install_file "$REPO_URL/AGENTS.md" "./AGENTS.override.md"

# Install AP_Scripting playbooks
mkdir -p libraries/AP_Scripting

install_file "$REPO_URL/libraries/AP_Scripting/AGENTS.md" "libraries/AP_Scripting/AGENTS.override.md"
for file in CODEX_CRSF_MENU.md CODEX_VEHICLE_CONTROL.md; do
    install_file "$REPO_URL/libraries/AP_Scripting/$file" "libraries/AP_Scripting/$file"
done

# Install AP_NavEKF3 playbook
mkdir -p libraries/AP_NavEKF3
install_file "$REPO_URL/libraries/AP_NavEKF3/AGENTS.md" "libraries/AP_NavEKF3/AGENTS.override.md"

# Install AP_HAL_ChibiOS hwdef playbook
mkdir -p libraries/AP_HAL_ChibiOS/hwdef
install_file "$REPO_URL/libraries/AP_HAL_ChibiOS/hwdef/AGENTS.md" "libraries/AP_HAL_ChibiOS/hwdef/AGENTS.override.md"

# Install ArduPlane playbook
mkdir -p ArduPlane
install_file "$REPO_URL/ArduPlane/AGENTS.md" "ArduPlane/AGENTS.override.md"

# Install Tools/autotest playbook
mkdir -p Tools/autotest
install_file "$REPO_URL/Tools/autotest/AGENTS.md" "Tools/autotest/AGENTS.override.md"

# Install Codex skills
echo ""
echo "Installing Codex skills..."

SKILLS_URL="$REPO_URL/skills"

# Skills with only SKILL.md
for skill in boards find-code find-param build-options style-check hwdef-info explain build check sitl lua lua-crsf lua-vehicle aap-update; do
    mkdir -p ".codex/skills/$skill"
    install_file "$SKILLS_URL/$skill/SKILL.md" ".codex/skills/$skill/SKILL.md"
done

# hwdef-check skill (has additional Python tool)
mkdir -p .codex/skills/hwdef-check
for file in SKILL.md hwdef_check.py; do
    install_file "$SKILLS_URL/hwdef-check/$file" ".codex/skills/hwdef-check/$file"
done
chmod +x .codex/skills/hwdef-check/hwdef_check.py

# autotest skill (has additional Python tools: results parser + timed runner)
mkdir -p .codex/skills/autotest
for file in SKILL.md autotest_results.py run_autotest.py; do
    install_file "$SKILLS_URL/autotest/$file" ".codex/skills/autotest/$file"
done
chmod +x .codex/skills/autotest/autotest_results.py .codex/skills/autotest/run_autotest.py

# log-analyze skill (has additional Python tool)
mkdir -p .codex/skills/log-analyze
for file in SKILL.md log_extract.py; do
    install_file "$SKILLS_URL/log-analyze/$file" ".codex/skills/log-analyze/$file"
done
chmod +x .codex/skills/log-analyze/log_extract.py

# pr-checks skill (has additional Python tool)
mkdir -p .codex/skills/pr-checks
for file in SKILL.md ci_failures.py; do
    install_file "$SKILLS_URL/pr-checks/$file" ".codex/skills/pr-checks/$file"
done
chmod +x .codex/skills/pr-checks/ci_failures.py

echo ""
echo "Installation complete!"
echo ""
echo "The following files are now available for Codex:"
echo ""
echo "  Playbooks (AGENTS.override.md files):"
echo "  - AGENTS.override.md (root - build system, architecture, C++ guidelines)"
echo "  - libraries/AP_Scripting/AGENTS.override.md (Lua scripting patterns)"
echo "  - libraries/AP_Scripting/CODEX_CRSF_MENU.md (CRSF menu implementation)"
echo "  - libraries/AP_Scripting/CODEX_VEHICLE_CONTROL.md (vehicle control APIs)"
echo "  - libraries/AP_NavEKF3/AGENTS.override.md (EKF3 navigation filter reference)"
echo "  - libraries/AP_HAL_ChibiOS/hwdef/AGENTS.override.md (ChibiOS board porting)"
echo "  - ArduPlane/AGENTS.override.md (Plane log analysis, flight modes, QuadPlane)"
echo "  - Tools/autotest/AGENTS.override.md (autotest authoring conventions, Lua applet patterns)"
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
echo "  - /aap-update     - Check for and install playbook updates"
echo ""
echo "To uninstall, run:"
echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-codex.sh | bash"
