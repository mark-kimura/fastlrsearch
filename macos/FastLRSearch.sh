#!/bin/bash
# FastLRSearch.app launcher
# Finds the Python environment where fastlrsearch is installed and launches it.

# Try these Python paths in order:
#   1. Homebrew Python (Apple Silicon)
#   2. Homebrew Python (Intel)
#   3. pipx venv
#   4. System Python

CANDIDATES=(
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "$HOME/.local/pipx/venvs/fastlrsearch/bin/python3"
    "/usr/bin/python3"
)

PYTHON=""
for candidate in "${CANDIDATES[@]}"; do
    if [ -x "$candidate" ] && "$candidate" -c "import fastlrsearch" 2>/dev/null; then
        # Check Python version is 3.10+
        version=$("$candidate" -c 'import sys; print(sys.version_info.minor)')
        if [ "$version" -ge 10 ]; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    osascript -e 'display dialog "FastLRSearch is not installed or Python 3.10+ is required.\n\nTo install:\n  1. Install Python: brew install python@3.12\n  2. pip install fastlrsearch" with title "FastLRSearch" buttons {"OK"} default button "OK" with icon stop'
    exit 1
fi

# Launch the app
exec "$PYTHON" -m fastlrsearch.main
