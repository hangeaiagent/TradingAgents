#!/bin/bash
# Wrapper script that activates venv and runs analyze.py
# Used by OpenClaw SKILL.md commands

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Auto-install if venv doesn't exist
if [ ! -d "$BASE_DIR/.venv" ]; then
    echo "First run detected. Installing dependencies..."
    bash "$SCRIPT_DIR/install.sh"
fi

# Activate venv and run
source "$BASE_DIR/.venv/bin/activate"
exec python3 "$SCRIPT_DIR/analyze.py" "$@"
