#!/bin/bash
# Creates FastLRSearch.app bundle in /Applications
#
# Usage:
#   ./macos/create_app.sh           # Install to /Applications
#   ./macos/create_app.sh ~/Desktop # Install to custom location
#
# This creates a lightweight .app wrapper that launches the pip/Homebrew-installed
# fastlrsearch Python package. No code signing needed — it's a local script.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${1:-/Applications}"
APP_NAME="FastLRSearch"
APP_BUNDLE="$INSTALL_DIR/$APP_NAME.app"

# Check Python version
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
if [ -z "$PYTHON_VERSION" ]; then
    echo "Error: Python 3 not found."
    echo "Install with: brew install python@3.12"
    exit 1
fi

PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "Error: Python 3.10+ required (found $PYTHON_VERSION)"
    echo "Install with: brew install python@3.12"
    exit 1
fi

echo "Creating $APP_NAME.app in $INSTALL_DIR ..."

# Clean previous install
if [ -d "$APP_BUNDLE" ]; then
    echo "  Removing existing $APP_NAME.app ..."
    rm -rf "$APP_BUNDLE"
fi

# Create bundle structure
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Copy Info.plist
cp "$SCRIPT_DIR/Info.plist" "$APP_BUNDLE/Contents/"

# Copy launcher script
cp "$SCRIPT_DIR/FastLRSearch.sh" "$APP_BUNDLE/Contents/MacOS/$APP_NAME"
chmod +x "$APP_BUNDLE/Contents/MacOS/$APP_NAME"

# Copy icon if it exists
if [ -f "$SCRIPT_DIR/AppIcon.icns" ]; then
    cp "$SCRIPT_DIR/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/"
else
    echo "  Note: No AppIcon.icns found. App will use default icon."
    echo "  Place an .icns file at macos/AppIcon.icns and re-run."
fi

# Remove quarantine attribute (prevents Gatekeeper warning for locally-created apps)
xattr -dr com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true

echo ""
echo "Done! $APP_NAME.app installed to $INSTALL_DIR"
echo ""
echo "You can now:"
echo "  - Find '$APP_NAME' in Spotlight (Cmd+Space)"
echo "  - Open from Applications folder"
echo "  - Drag to Dock to pin it"
