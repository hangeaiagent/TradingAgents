#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Installing TradingAgents skill..."
cd "$BASE_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Installing dependencies..."
source .venv/bin/activate
pip install -e . --quiet

# Check for .env file
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo ""
        echo "Created .env from .env.example."
        echo "Please edit .env and add your API keys."
    else
        echo ""
        echo "No .env file found. Create one with your API keys:"
        echo "  OPENAI_API_KEY=sk-..."
    fi
else
    echo ".env file already exists."
fi

echo ""
echo "Installation complete!"
echo "Test with: ${BASE_DIR}/scripts/run.sh --ticker AAPL --depth quick"
