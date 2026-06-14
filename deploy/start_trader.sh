#!/bin/bash
# Start paper trader from correct directory
cd /d/Alpaca || exit 1
source venv/Scripts/activate
python paper_trader.py
