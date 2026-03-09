#!/bin/bash
# Install FastLRSearch Lightroom Classic plugin
#
# Usage:
#   ./macos/install_lrplugin.sh
#
# Copies the .lrplugin to Lightroom's Modules directory.
# After running, open Lightroom → File → Plug-in Manager to verify.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLUGIN_SRC="$PROJECT_DIR/fastlrsearch.lrplugin"

# Lightroom plugin directories (check in order)
LR_MODULES_DIRS=(
    "$HOME/Library/Application Support/Adobe/Lightroom/Modules"
    "$HOME/Library/Application Support/Adobe/CameraRaw/Lightroom/Modules"
)

if [ ! -d "$PLUGIN_SRC" ]; then
    echo "Error: Plugin source not found at $PLUGIN_SRC"
    exit 1
fi

# Find the right Lightroom Modules directory
DEST=""
for dir in "${LR_MODULES_DIRS[@]}"; do
    parent="$(dirname "$dir")"
    if [ -d "$parent" ]; then
        DEST="$dir"
        break
    fi
done

if [ -z "$DEST" ]; then
    # Default to the standard location
    DEST="${LR_MODULES_DIRS[0]}"
fi

echo "Installing FastLRSearch Lightroom plugin..."
echo "  Source: $PLUGIN_SRC"
echo "  Destination: $DEST"
echo ""

# Create Modules directory if needed
mkdir -p "$DEST"

# Remove old version if present
if [ -d "$DEST/fastlrsearch.lrplugin" ]; then
    echo "  Removing previous version..."
    rm -rf "$DEST/fastlrsearch.lrplugin"
fi

# Copy plugin
cp -r "$PLUGIN_SRC" "$DEST/fastlrsearch.lrplugin"

echo "Done!"
echo ""
echo "Next steps:"
echo "  1. Open Lightroom Classic"
echo "  2. Go to File → Plug-in Manager"
echo "  3. FastLRSearch should appear in the list"
echo "  4. Make sure FastLRSearch desktop app is running (for the API server)"
echo ""
echo "Usage in Lightroom:"
echo "  - Library → Plug-in Extras → Search Photos..."
echo "  - Library → Plug-in Extras → Find Similar to Selected"
