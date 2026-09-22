#!/usr/bin/env bash
set -euo pipefail

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev,needle]'
mkdir -p models
needle download needle3 --out models

echo "Brainbox OS + Needle 3 is ready. Model: models/needle3.cact"
