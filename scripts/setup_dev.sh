#!/usr/bin/env bash
set -euo pipefail

# Create a local virtualenv in .venv and install dev dependencies.
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
echo "Dev environment ready (.venv). To activate: source .venv/bin/activate"
