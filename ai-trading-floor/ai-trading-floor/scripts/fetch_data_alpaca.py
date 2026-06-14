#!/usr/bin/env python3
"""Fetch OHLCV bars from Alpaca Market Data API into the kit's parquet schema.

This replaces fetch_data.py (yfinance) with Alpaca as the data source.
Alpaca provides 7+ years of historical data for stocks, and also supports
crypto and intraday bars.

Output matches DATA_CONTRACT.md exactly:
  columns [Date, Open, High, Low, Close, Volume], plain RangeIndex,
  timezone-naive datetime64[ms] (Eastern Time for intraday), OHLCV float64.

Usage examples:
    # 3 years of daily AAPL
    python fetch_data_alpaca.py --tickers AAPL --start 2022-01-01 --end 2025-01-01

    # Multiple tickers
    python fetch_data_alpaca.py --tickers AAPL,MSFT,NVDA --start 2021-01-01

    # 15-minute intraday (Alpaca free tier: limited history for intraday)
    python fetch_data_alpaca.py --tickers AAPL --interval 15min --start 2025-05-01

    # Max history (~7 years)
    python fetch_data_alpaca.py --tickers SPY --start 2018-01-01
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

SCHEMA_COLUMNS = ["Date", "Open", "High", "Low", "Close", "Volume"]
PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]

# Map user-friendly interval names to Alpaca TimeFrame
INTERVAL_MAP = {
    "1min": "1Min", "1m": "1Min",
    "5min": "5Min", "5m": "5Min",
    "15min": "15Min", "15m": "15Min",
    "30min": "30Min", "30m": "30Min",
    "1h": "1Hour", "1hour": "1Hour", "60min": "1Hour",
    "1d": "1Day", "1day": "1Day", "day": "1Day", "daily": "1Day",
}

INTRADAY_INTERVALS = {"1Min", "5Min", "15Min", "30Min", "1Hour"}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Alpaca bars into the kit's parquet schema (writes to ./data).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tickers", default="AAPL",
                        help="Comma-separated ticker symbols.")
    parser.add_argument("--start", default=None,
                        help="Start date YYYY-MM-DD (default: 3 years ago).")
    parser.add_argument("--end", default=None,
                        help="End date YYYY-MM-DD (default: today).")
    parser.add_argument("--interval", default="1d",
                        help="Bar interval: 1d, 15min, 5min, 1h, etc.")
    parser.add_argument("--outdir", default="data",
                        help="Output directory (relative to CWD).")
    return parser.parse_args(argv)


def get_timeframe(interval: str):
    """Convert user interval string to Alpaca TimeFrame object."""
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    key = interval.lower()
    mapped = INTERVAL_MAP.get(key, key)

    tf_map = {
        "1Min": TimeFrame.Minute,
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "30Min": TimeFrame(30, TimeFrameUnit.Minute),
        "1Hour": TimeFrame.Hour,
        "1Day": TimeFrame.Day,
    }
    tf = tf_map.get(mapped)
    if tf is None:
        sys.exit(f"ERROR: unsupported interval '{interval}'. "
                 f"Supported: {list(INTERVAL_MAP.keys())}")
    return tf, mapped


def normalize_to_schema(df: pd.DataFrame, alpaca_interval: str) -> pd.DataFrame:
    """Coerce Alpaca bar DataFrame into the exact kit schema."""
    out = df.copy()

    # Alpaca returns a MultiIndex (symbol, timestamp) — flatten
    if isinstance(out.index, pd.MultiIndex):
        out = out.reset_index()
    elif out.index.name == "timestamp" or out.index.name:
        out = out.reset_index()

    # Find the timestamp column
    ts_col = None
    for candidate in ["timestamp", "Timestamp", "Date", "date"]:
        if candidate in out.columns:
            ts_col = candidate
            break
    if ts_col is None:
        # Try first column if it's datetime-like
        if pd.api.types.is_datetime64_any_dtype(out.iloc[:, 0]):
            ts_col = out.columns[0]
        else:
            raise ValueError(f"Cannot find timestamp column in: {list(out.columns)}")

    out = out.rename(columns={ts_col: "Date"})

    # Rename OHLCV columns (alpaca returns lowercase)
    rename_map = {
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
        "trade_count": "_drop_tc", "vwap": "_drop_vwap",
        "symbol": "_drop_sym",
    }
    out = out.rename(columns=rename_map)

    # Keep only schema columns
    missing = [c for c in SCHEMA_COLUMNS if c not in out.columns]
    if missing:
        raise ValueError(f"Alpaca frame missing expected columns: {missing}. "
                         f"Available: {list(out.columns)}")
    out = out[SCHEMA_COLUMNS]

    # Timezone: convert to naive Eastern Time
    out["Date"] = pd.to_datetime(out["Date"])
    if getattr(out["Date"].dt, "tz", None) is not None:
        if alpaca_interval in INTRADAY_INTERVALS:
            out["Date"] = out["Date"].dt.tz_convert("America/New_York").dt.tz_localize(None)
        else:
            out["Date"] = out["Date"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    out["Date"] = out["Date"].astype("datetime64[ms]")

    # Ensure float64
    for col in PRICE_COLUMNS:
        out[col] = out[col].astype("float64")

    out = out.dropna(subset=PRICE_COLUMNS).reset_index(drop=True)
    return out


def output_path(ticker: str, alpaca_interval: str, outdir: Path) -> Path:
    if alpaca_interval in INTRADAY_INTERVALS:
        interval_label = alpaca_interval.lower().replace("min", "min").replace("hour", "h")
        return outdir / "intraday" / f"{ticker}_{interval_label}.parquet"
    return outdir / f"{ticker}.parquet"


def download_one(ticker: str, start: datetime, end: datetime,
                 timeframe, alpaca_interval: str) -> pd.DataFrame:
    """Download bars for one ticker from Alpaca."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        sys.exit("ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set. "
                 "Put them in a .env file or export them.")

    client = StockHistoricalDataClient(api_key, secret_key)

    request = StockBarsRequest(
        symbol_or_symbols=ticker,
        timeframe=timeframe,
        start=start,
        end=end,
    )

    bars = client.get_stock_bars(request)
    return bars.df


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    args = parse_args(argv)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if not tickers:
        sys.exit("ERROR: --tickers produced an empty list.")

    timeframe, alpaca_interval = get_timeframe(args.interval)

    # Default date range: 3 years ago to today
    end = datetime.strptime(args.end, "%Y-%m-%d") if args.end else datetime.now()
    start = datetime.strptime(args.start, "%Y-%m-%d") if args.start else (end - timedelta(days=3*365))

    outdir = Path(args.outdir)
    written = 0

    for ticker in tickers:
        print(f"Fetching {ticker} ({args.interval}) from Alpaca ...")
        try:
            raw = download_one(ticker, start, end, timeframe, alpaca_interval)
        except Exception as e:
            print(f"  ERROR fetching {ticker}: {e}")
            continue

        if raw is None or raw.empty:
            print(f"  WARNING: no data returned for {ticker}. Skipping.")
            continue

        df = normalize_to_schema(raw, alpaca_interval)
        if df.empty:
            print(f"  WARNING: {ticker} had no usable rows after cleaning. Skipping.")
            continue

        out = output_path(ticker, alpaca_interval, outdir)
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        written += 1

        d_start, d_end = df["Date"].min(), df["Date"].max()
        print(f"  Saved {len(df)} rows to {out}")
        print(f"  Date range: {d_start} -> {d_end}")
        print(f"  Columns: {list(df.columns)}")
        print("  Head:")
        print(df.head().to_string(index=False))
        print()

    if written == 0:
        print("No files written. Check your tickers / date range / interval.")
        return 1

    print(f"Done! {written} file(s) written to ./{outdir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
