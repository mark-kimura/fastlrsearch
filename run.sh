#!/bin/bash
# Run FastLRSearch

# Resolve symlinks to get the real script directory
SCRIPT_PATH="$(readlink -f "$0")"
cd "$(dirname "$SCRIPT_PATH")"

# Bind API to all interfaces for LAN access (e.g., Lightroom on VM)
export FASTLRSEARCH_API_HOST=0.0.0.0

/home/mkimura/miniconda3/envs/lrsearch/bin/python -m fastlrsearch.main "$@"
