#!/usr/bin/env bash
# One-time setup (Linux / macOS): creates .venv and installs the package. Run from the agents/ folder.
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e .
echo
echo "Done. Try it:  . .venv/bin/activate && python -m sphinx1 --task \"find the red bottle\""
