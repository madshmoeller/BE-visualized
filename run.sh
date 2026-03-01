#!/usr/bin/env bash
set -e

# CRISPR Library Viewer (Dash) - Startup Script
# Prerequisites: Python 3.8+ must be installed
# Usage: bash run.sh  (from inside the viewer_dash/ folder)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "=== CRISPR Library Viewer (Dash) ==="
echo ""

# Find Python
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python not found. Please install Python 3.8 or later."
    exit 1
fi

echo "Using Python: $($PYTHON --version)"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment (first run only)..."
    "$PYTHON" -m venv "$VENV_DIR"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install dependencies
echo "Checking dependencies..."
pip install -q -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "Starting server..."
echo "Open http://localhost:5002 in your browser"
echo "Press Ctrl+C to stop"
echo ""

# Run from the viewer_dash directory
cd "$SCRIPT_DIR"
python app.py
