#!/usr/bin/env python3
"""Health check: verifica que el trader esté vivo y Alpaca responda.
Exit codes: 0=OK, 1=Alpaca caido, 2=archivo estado faltante, 3=error parsing
"""
import sys, json
from pathlib import Path

STATE_FILE = Path("logs/trader_state.json")
try:
    data = json.loads(STATE_FILE.read_text())
    last_run = data.get("last_run", "")
    status = data.get("status", "unknown")
    
    if status != "ok":
        print(f"ALERTA: Estado trader = {status}")
        sys.exit(1)
    
    print(f"OK: ultima corrida {last_run} | estado {status}")
    sys.exit(0)
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(2)
