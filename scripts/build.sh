#!/bin/bash
# Build FastLRSearch with PyInstaller
#
# Usage:
#   ./scripts/build.sh [--clean]
#
# Options:
#   --clean  Remove previous build artifacts before building

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Parse arguments
CLEAN=false
for arg in "$@"; do
    case $arg in
        --clean)
            CLEAN=true
            ;;
    esac
done

echo "========================================"
echo "FastLRSearch Build"
echo "========================================"
echo "Project directory: $PROJECT_DIR"
echo ""

# Clean if requested
if [ "$CLEAN" = true ]; then
    echo "Cleaning previous build..."
    rm -rf build/ dist/ *.spec.bak
    echo ""
fi

# Check for required tools
if ! command -v pyinstaller &> /dev/null; then
    echo "Error: pyinstaller not found"
    echo "Install with: pip install pyinstaller"
    exit 1
fi

# Build with PyInstaller
echo "Building with PyInstaller..."
echo ""

pyinstaller \
    --noconfirm \
    --collect-all torch \
    --collect-all transformers \
    --collect-all qdrant_client \
    --collect-all PySide6 \
    --collect-all PIL \
    --hidden-import=rawpy \
    --hidden-import=imagehash \
    --hidden-import=xxhash \
    --hidden-import=exifread \
    --hidden-import=fastapi \
    --hidden-import=uvicorn \
    --hidden-import=pydantic \
    --hidden-import=pydantic_settings \
    --hidden-import=tqdm \
    --name fastlrsearch \
    --windowed \
    src/fastlrsearch/main.py

echo ""
echo "========================================"
echo "Build complete!"
echo "========================================"
echo ""
echo "Output: dist/fastlrsearch/"
echo ""

# Show size
if [ -d "dist/fastlrsearch" ]; then
    SIZE=$(du -sh dist/fastlrsearch | cut -f1)
    echo "Size: $SIZE"
fi

echo ""
echo "To run:"
echo "  ./dist/fastlrsearch/fastlrsearch"
