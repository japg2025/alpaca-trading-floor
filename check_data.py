"""Check Alpaca intradía data availability for backtest."""
import json
from datetime import datetime, timedelta

try:
    from dotenv import load_dotenv
    import os
    load_dotenv(dotenv_path="D:/Alpaca/.env")
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    print("Alpaca data imports OK")
except Exception as e:
    print(f"Import error: {e}")
    raise SystemExit(1)

api_key = os.environ.get("ALPACA_API_KEY")
secret = os.environ.get("ALPACA_SECRET_KEY")
if not api_key or not secret:
    print("Missing ALPACA_API_KEY / ALPACA_SECRET_KEY in .env")
    raise SystemExit(1)

client = StockHistoricalDataClient(api_key, secret)

# Test QQQ 15-min bars: try last 60 days, 30 days, 7 days
now = datetime.now()
for days in [60, 30, 7, 1]:
    start = now - timedelta(days=days)
    req = StockBarsRequest(
        symbol_or_symbols="QQQ",
        timeframe=TimeFrame.FifteenMinute,
        start=start,
        end=now,
        adjustment="split",
    )
    try:
        bars = client.get_stock_bars(req)
        df = bars.df
        print(f"QQQ 15m last {days}d -> {len(df)} bars")
        if len(df):
            print(f"   range: {df.index.get_level_values('timestamp')[0]} to {df.index.get_level_values('timestamp')[-1]}")
    except Exception as e:
        print(f"QQQ 15m last {days}d -> ERROR: {e}")

# Try NQ futures? Usually need different symbols on Alpaca. Test /NQ or MNQ
for sym in ["MNQ", "/NQ", "NQ"]:
    for days in [30]:
        start = now - timedelta(days=days)
        req = StockBarsRequest(
            symbol_or_symbols=sym,
            timeframe=TimeFrame.FifteenMinute,
            start=start,
            end=now,
        )
        try:
            bars = client.get_stock_bars(req)
            df = bars.df
            print(f"{sym} 15m last {days}d -> {len(df)} bars")
        except Exception as e:
            print(f"{sym} 15m last {days}d -> ERROR: {type(e).__name__}: {e}")
