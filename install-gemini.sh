#!/bin/bash
#
# Install ArduPilot AI Playbooks for Gemini
#
# Run this script from the root of an ArduPilot repository to install
# GEMINI.md files that guide Gemini when working with the codebase.
#
# Usage: curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/install-gemini.sh | bash
#

set -e

REPO_URL="https://raw.githubusercontent.com/fossuav/aap/main/gemini"

# Check if we're in an ArduPilot repository
if [[ ! -f "wscript" ]] || [[ ! -d "ArduCopter" ]] || [[ ! -d "libraries" ]]; then
    echo "Error: This script must be run from the root of an ArduPilot repository."
    echo ""
    echo "Usage:"
    echo "  cd /path/to/ardupilot"
    echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/install-gemini.sh | bash"
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

echo "Installing Gemini playbooks to ArduPilot repository..."

# Install root GEMINI.md
if [[ -f "GEMINI.md" ]]; then
    echo "  Backing up existing GEMINI.md to GEMINI.md.bak"
    cp GEMINI.md GEMINI.md.bak
fi
download_file "$REPO_URL/GEMINI.md" "./GEMINI.md"
echo "  Installed: GEMINI.md"

# Install AP_Scripting GEMINI files
mkdir -p libraries/AP_Scripting

for file in GEMINI.md GEMINI_CRSF_MENU.md GEMINI_VEHICLE_CONTROL.md; do
    dst="libraries/AP_Scripting/$file"
    if [[ -f "$dst" ]]; then
        echo "  Backing up existing $dst to ${dst}.bak"
        cp "$dst" "${dst}.bak"
    fi
    download_file "$REPO_URL/libraries/AP_Scripting/$file" "$dst"
    echo "  Installed: $dst"
done

echo ""
echo "Installation complete!"
echo ""
echo "The following files are now available for Gemini:"
echo "  - GEMINI.md (root - build system, architecture, C++ guidelines)"
echo "  - libraries/AP_Scripting/GEMINI.md (Lua scripting patterns)"
echo "  - libraries/AP_Scripting/GEMINI_CRSF_MENU.md (CRSF menu implementation)"
echo "  - libraries/AP_Scripting/GEMINI_VEHICLE_CONTROL.md (vehicle control APIs)"
echo ""
echo "To uninstall, run:"
echo "  curl -fsSL https://raw.githubusercontent.com/fossuav/aap/main/uninstall-gemini.sh | bash"
