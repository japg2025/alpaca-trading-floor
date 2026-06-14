import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv(dotenv_path="D:/Alpaca/.env")
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

api_key = os.environ["ALPACA_API_KEY"]
secret = os.environ["ALPACA_SECRET_KEY"]
client = StockHistoricalDataClient(api_key, secret)

now = datetime.now()
for sym in ["QQQ", "SPY", "AAPL", "/NQ", "MNQ"]:
    for days in [30, 7]:
        start = now - timedelta(days=days)
        req = StockBarsRequest(
            symbol_or_symbols=sym,
            timeframe=TimeFrame(15, TimeFrameUnit.Minute),
            start=start,
            end=now,
        )
        try:
            bars = client.get_stock_bars(req)
            df = bars.df
            if len(df):
                ts0 = df.index.get_level_values("timestamp")[0]
                ts1 = df.index.get_level_values("timestamp")[-1]
                print(f"{sym} 15m last {days}d -> {len(df)} bars [{ts0} -> {ts1}]")
            else:
                print(f"{sym} 15m last {days}d -> 0 bars (empty)")
        except Exception as e:
            print(f"{sym} 15m last {days}d -> ERROR: {type(e).__name__}: {e}")
