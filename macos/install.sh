#!/bin/bash
# FastLRSearch macOS installer
#
# Usage (two steps — download first so interactive prompts work):
#   curl -fsSL https://raw.githubusercontent.com/mark-kimura/fastlrsearch/master/macos/install.sh -o /tmp/fastlrsearch-install.sh
#   bash /tmp/fastlrsearch-install.sh
#
# Or after cloning:
#   ./macos/install.sh
#
# What this does:
#   1. Installs Homebrew (if not installed)
#   2. Installs Python 3.12 and libraw (if needed)
#   3. Installs FastLRSearch in a virtual environment
#   4. Creates FastLRSearch.app in /Applications
#   5. Optionally installs the Lightroom plugin

set -e

APP_NAME="FastLRSearch"
INSTALL_DIR="$HOME/.local/share/fastlrsearch"
VENV_DIR="$INSTALL_DIR/venv"
REPO_URL="https://github.com/mark-kimura/fastlrsearch.git"
REPO_DIR="$INSTALL_DIR/repo"

echo "========================================"
echo "  $APP_NAME Installer"
echo "========================================"
echo ""

# ── Step 1: Find or install Homebrew ──────────────────────────────
# Check PATH first, then known install locations (in case user just
# installed Homebrew but hasn't restarted their terminal)
if command -v brew &>/dev/null; then
    BREW=brew
elif [ -x "/opt/homebrew/bin/brew" ]; then
    # Apple Silicon
    eval "$(/opt/homebrew/bin/brew shellenv)"
    BREW=/opt/homebrew/bin/brew
elif [ -x "/usr/local/bin/brew" ]; then
    # Intel Mac
    eval "$(/usr/local/bin/brew shellenv)"
    BREW=/usr/local/bin/brew
else
    echo "Homebrew is required but not installed."
    echo ""
    echo "To install Homebrew first, run:"
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo ""
    echo "Then re-run this installer:"
    echo "  bash /tmp/fastlrsearch-install.sh"
    echo ""
    echo "Note: Your macOS user account must be an Administrator to install Homebrew."
    echo "Check: System Settings > Users & Groups"
    exit 1
fi
echo "Using Homebrew: $($BREW --prefix)"

# ── Step 2: Python ────────────────────────────────────────────────
# Prefer Homebrew Python 3.12 over system Python. System Python (e.g. 3.14)
# may be too new for PySide6 and other dependencies.
PYTHON=""

# Check for Homebrew Python 3.12 or 3.13 first
for ver in 3.12 3.13; do
    brew_python="$($BREW --prefix python@$ver 2>/dev/null)/bin/python$ver"
    if [ -x "$brew_python" ]; then
        PYTHON="$brew_python"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "Installing Python 3.12..."
    $BREW install python@3.12
    PYTHON="$($BREW --prefix python@3.12)/bin/python3.12"
    echo ""
fi

echo "Using Python: $($PYTHON --version)"
echo ""

# ── Step 2b: libraw (for RAW photo support) ──────────────────────
if ! $BREW list libraw &>/dev/null; then
    echo "Installing libraw (for RAW photo support: CR2, DNG, NEF, ARW, etc.)..."
    $BREW install libraw
    echo ""
fi

# ── Step 3: Clone/update repo ────────────────────────────────────
mkdir -p "$INSTALL_DIR"

if [ -d "$REPO_DIR/.git" ]; then
    echo "Updating FastLRSearch..."
    git -C "$REPO_DIR" pull --ff-only 2>/dev/null || true
else
    echo "Downloading FastLRSearch..."
    git clone "$REPO_URL" "$REPO_DIR"
fi
echo ""

# ── Step 4: Virtual environment & install ─────────────────────────
echo "Setting up virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    $PYTHON -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/pip" install --upgrade pip --quiet
echo "Installing FastLRSearch (this may take a few minutes)..."
"$VENV_DIR/bin/pip" install "$REPO_DIR" --quiet
echo ""

# ── Step 5: Create .app bundle ────────────────────────────────────
echo "Creating $APP_NAME.app..."

APP_BUNDLE="/Applications/$APP_NAME.app"

# Clean previous install
rm -rf "$APP_BUNDLE"

mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Info.plist
cp "$REPO_DIR/macos/Info.plist" "$APP_BUNDLE/Contents/"

# Launcher — directly uses our venv Python (no searching needed)
# Logs errors to ~/Library/Logs/FastLRSearch.log for debugging
cat > "$APP_BUNDLE/Contents/MacOS/$APP_NAME" << 'LAUNCHER'
#!/bin/bash
LOGFILE="$HOME/Library/Logs/FastLRSearch.log"
VENV_PYTHON="$HOME/.local/share/fastlrsearch/venv/bin/python3"

echo "$(date): Launching FastLRSearch..." >> "$LOGFILE"

if [ ! -x "$VENV_PYTHON" ]; then
    echo "$(date): ERROR: venv Python not found at $VENV_PYTHON" >> "$LOGFILE"
    osascript -e 'display dialog "FastLRSearch needs to be reinstalled.\n\nRun:\n  ~/.local/share/fastlrsearch/repo/macos/install.sh" with title "FastLRSearch" buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi

echo "$(date): Using Python: $($VENV_PYTHON --version 2>&1)" >> "$LOGFILE"
echo "$(date): Arch: $(uname -m)" >> "$LOGFILE"

# On Apple Silicon, ensure we run natively (not under Rosetta).
# macOS may launch .app shell scripts under x86_64 by default,
# causing arm64 Python packages to fail with architecture mismatch.
if [ "$(sysctl -n hw.optional.arm64 2>/dev/null)" = "1" ] && [ "$(uname -m)" = "x86_64" ]; then
    echo "$(date): Rosetta detected, re-launching as arm64..." >> "$LOGFILE"
    exec arch -arm64 "$VENV_PYTHON" -m fastlrsearch.main >> "$LOGFILE" 2>&1
fi

exec "$VENV_PYTHON" -m fastlrsearch.main >> "$LOGFILE" 2>&1
LAUNCHER
chmod +x "$APP_BUNDLE/Contents/MacOS/$APP_NAME"

# Icon
if [ -f "$REPO_DIR/macos/AppIcon.icns" ]; then
    cp "$REPO_DIR/macos/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/"
fi

# Remove quarantine
xattr -dr com.apple.quarantine "$APP_BUNDLE" 2>/dev/null || true

echo ""

# ── Step 6: CLI command ───────────────────────────────────────────
# Create a 'fastlrsearch' command that uses our venv, not system Python
echo "Setting up command-line tool..."
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/fastlrsearch" << 'CLISCRIPT'
#!/bin/bash
exec "$HOME/.local/share/fastlrsearch/venv/bin/fastlrsearch" "$@"
CLISCRIPT
chmod +x "$HOME/.local/bin/fastlrsearch"

# Ensure ~/.local/bin is on PATH (for zsh)
if ! echo "$PATH" | grep -q "$HOME/.local/bin"; then
    echo ""
    echo "Adding ~/.local/bin to your PATH..."
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zprofile"
    export PATH="$HOME/.local/bin:$PATH"
fi
echo ""

# ── Step 7: Lightroom plugin (optional) ──────────────────────────
read -p "Install Lightroom Classic plugin? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    LR_MODULES="$HOME/Library/Application Support/Adobe/Lightroom/Modules"
    mkdir -p "$LR_MODULES"
    rm -rf "$LR_MODULES/fastlrsearch.lrplugin"
    cp -r "$REPO_DIR/fastlrsearch.lrplugin" "$LR_MODULES/fastlrsearch.lrplugin"
    echo "Lightroom plugin installed!"
    echo ""
fi

# ── Done ──────────────────────────────────────────────────────────
echo "========================================"
echo "  Installation complete!"
echo "========================================"
echo ""
echo "Launch: Cmd+Space → type '$APP_NAME'"
echo "   or: open /Applications/$APP_NAME.app"
echo ""
echo "First launch will download the AI model (~1.5 GB)."
echo ""
echo "To update later:"
echo "  ~/.local/share/fastlrsearch/repo/macos/install.sh"
