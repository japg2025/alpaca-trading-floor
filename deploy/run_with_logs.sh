#!/bin/bash
# Wrapper: runs paper trader and logs output with timestamps
cd /d/Alpaca || exit 1
source venv/Scripts/activate

LOG_DIR="logs"
mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/trader_$(date +%Y-%m-%d).log"
echo "=== Run at $(date -Iseconds) ===" >> "$LOG_FILE"

python paper_trader.py 2>&1 | tee -a "$LOG_FILE"

# Keep last 30 days of logs
find "$LOG_DIR" -name "trader_*.log" -mtime +30 -delete
