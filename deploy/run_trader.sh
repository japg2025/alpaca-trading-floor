#!/usr/bin/env bash
set -euo pipefail
cd /app
python -m venv .venv
source .venv/bin/activate
pip install -r deploy/requirements.txt >/tmp/railway-pip.log 2>&1
python paper_trader.py
