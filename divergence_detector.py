"""Detect bullish RSI divergences on 15min timeframe.
Saves alerts to alerts/divergences.json
"""
import json, os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

load_dotenv(dotenv_path="D:/Alpaca/.env")
api_key = os.environ["ALPACA_API_KEY"]
secret = os.environ["ALPACA_SECRET_KEY"]
client = StockHistoricalDataClient(api_key, secret)

SYMBOLS = ["QQQ", "SPY", "AAPL"]
RSI_PERIOD = 14
SWING_LOOKBACK = 3  # bars on each side for swing detection


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def find_swing_lows(series: pd.Series, lookback: int = 3) -> pd.Series:
    """Return series of bool: True where value is a local minimum."""
    lows = pd.Series(False, index=series.index)
    for i in range(lookback, len(series) - lookback):
        window = series.iloc[i-lookback:i+lookback+1]
        if series.iloc[i] == window.min():
            lows.iloc[i] = True
    return lows


def detect_bullish_divergence(df: pd.DataFrame, symbol: str) -> list:
    """Detect bullish RSI divergences in the last N bars."""
    closes = df["Close"]
    rsi_vals = rsi(closes, RSI_PERIOD)
    price_lows = find_swing_lows(closes, SWING_LOOKBACK)
    rsi_lows = find_swing_lows(rsi_vals, SWING_LOOKBACK)

    divergences = []
    # Collect recent swing lows (last 50 bars)
    recent_price_lows = price_lows[price_lows].index[-20:]
    recent_rsi_lows = rsi_lows[rsi_lows].index[-20:]

    # Compare pairs of swing lows
    price_low_points = [(idx, float(closes.loc[idx]), float(rsi_vals.loc[idx])) for idx in recent_price_lows]
    rsi_low_points = [(idx, float(closes.loc[idx]), float(rsi_vals.loc[idx])) for idx in recent_rsi_lows]

    # Find pairs: price lower low + rsi higher low
    for i in range(1, len(price_low_points)):
        idx_prev, price_prev, rsi_prev = price_low_points[i-1]
        idx_curr, price_curr, rsi_curr = price_low_points[i]
        if price_curr < price_prev and rsi_curr > rsi_prev:
            # Also check RSI is coming from oversold (< 40)
            if rsi_curr < 45:
                divergences.append({
                    "symbol": symbol,
                    "detected_at": datetime.now().isoformat(),
                    "price_low_1": {"index": str(idx_prev), "price": round(price_prev, 2), "rsi": round(rsi_prev, 1)},
                    "price_low_2": {"index": str(idx_curr), "price": round(price_curr, 2), "rsi": round(rsi_curr, 1)},
                    "current_price": round(float(closes.iloc[-1]), 2),
                    "current_rsi": round(float(rsi_vals.dropna().iloc[-1]), 1),
                    "signal": "BULLISH DIVERGENCE DETECTED",
                })
    return divergences


def main():
    now = datetime.now()
    start = now - timedelta(days=30)

    all_alerts = []
    for sym in SYMBOLS:
        req = StockBarsRequest(
            symbol_or_symbols=sym,
            timeframe=TimeFrame(15, TimeFrameUnit.Minute),
            start=start,
            end=now,
        )
        bars = client.get_stock_bars(req)
        df = bars.df.reset_index()
        if len(df) == 0:
            print(f"{sym}: no data")
            continue

        # Normalize columns
        rename = {"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume", "timestamp": "Date"}
        df = df.rename(columns=rename)
        df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
        df = df.sort_values("Date").reset_index(drop=True)

        alerts = detect_bullish_divergence(df, sym)
        if alerts:
            all_alerts.extend(alerts)
            a = alerts[-1]
            print(f"🚨 {sym} BULLISH DIVERGENCE on 15min!")
            print(f"   Swing 1: price={a['price_low_1']['price']}  rsi={a['price_low_1']['rsi']}")
            print(f"   Swing 2: price={a['price_low_2']['price']}  rsi={a['price_low_2']['rsi']}")
            print(f"   Now:      price={a['current_price']}  rsi={a['current_rsi']}")
        else:
            print(f"{sym}: no divergence detected")

    # Save alerts
    Path("alerts").mkdir(exist_ok=True)
    out = Path("alerts/divergences.json")
    payload = {
        "checked_at": now.isoformat(),
        "timeframe": "15min",
        "symbols": SYMBOLS,
        "alerts": all_alerts,
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nSaved {len(all_alerts)} alert(s) to {out}")


if __name__ == "__main__":
    main()
