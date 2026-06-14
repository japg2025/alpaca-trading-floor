"""Backtest bullish RSI divergence strategy on 15min bars.
Tickers: 7 magnificas + QQQ + SPY

Logic:
  - Detect bullish RSI divergence (price lower low + RSI higher low)
  - Enter: buy at next bar open
  - Exit: after N bars or when RSI crosses above 60 (momentum exhaustion)
  - Simulate with calls-like leverage (3x multiplier on returns)

Output: stats per ticker + aggregate
"""
import os
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

load_dotenv(dotenv_path="D:/Alpaca/.env")
api_key = os.environ["ALPACA_API_KEY"]
secret = os.environ["ALPACA_SECRET_KEY"]
client = StockHistoricalDataClient(api_key, secret)

# 7 Magnificas + QQQ + SPY
SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "QQQ", "SPY"]

RSI_PERIOD = 14
SWING_LOOKBACK = 3
EXIT_BARS = 8  # hold max 8 bars (2 hours)
RSI_EXIT = 60  # exit when RSI > 60 (momentum exhaustion)
LEVERAGE = 3.0  # simulate 3x returns (like 0-1 DTE calls)


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def find_swing_lows(series: pd.Series, lookback: int = 3) -> pd.Series:
    lows = pd.Series(False, index=series.index)
    for i in range(lookback, len(series) - lookback):
        window = series.iloc[i-lookback:i+lookback+1]
        if series.iloc[i] == window.min():
            lows.iloc[i] = True
    return lows


def backtest_symbol(df: pd.DataFrame, symbol: str) -> dict:
    """Run divergence backtest on one symbol."""
    df = df.sort_values("Date").reset_index(drop=True)
    closes = df["Close"]
    rsi_vals = rsi(closes, RSI_PERIOD)
    price_lows = find_swing_lows(closes, SWING_LOOKBACK)
    rsi_lows = find_swing_lows(rsi_vals, SWING_LOOKBACK)

    trades = []
    in_trade = False
    entry_idx = None
    entry_price = None
    entry_rsi = None
    bars_held = 0

    for i in range(SWING_LOOKBACK * 2, len(df)):
        # Check exit first
        if in_trade:
            bars_held += 1
            current_rsi = rsi_vals.iloc[i]
            if bars_held >= EXIT_BARS or current_rsi > RSI_EXIT:
                # Exit at next bar open (realistic fill)
                if i + 1 < len(df):
                    exit_price = df["Open"].iloc[i + 1]
                    ret_pct = (exit_price - entry_price) / entry_price
                    ret_leveraged = ret_pct * LEVERAGE
                    trades.append({
                        "entry_idx": int(entry_idx),
                        "exit_idx": int(i + 1),
                        "entry_date": str(df["Date"].iloc[int(entry_idx)]),
                        "exit_date": str(df["Date"].iloc[i + 1]),
                        "entry_price": round(entry_price, 2),
                        "exit_price": round(exit_price, 2),
                        "bars_held": bars_held,
                        "rsi_at_entry": round(entry_rsi, 1),
                        "rsi_at_exit": round(current_rsi, 1),
                        "return_pct": round(ret_pct * 100, 2),
                        "return_leveraged": round(ret_leveraged * 100, 2),
                    })
                in_trade = False
                continue

        # Check entry
        if not in_trade and not pd.isna(rsi_vals.iloc[i]):
            # Look for bullish divergence on last 2 swing lows
            if price_lows.iloc[i] and i >= 2:
                price_curr = closes.iloc[i]
                rsi_curr = rsi_vals.iloc[i]
                # Find previous swing low
                prev_price_low_idx = None
                for j in range(i - 1, SWING_LOOKBACK - 1, -1):
                    if price_lows.iloc[j]:
                        prev_price_low_idx = j
                        break
                if prev_price_low_idx is not None:
                    price_prev = closes.iloc[prev_price_low_idx]
                    rsi_prev = rsi_vals.iloc[prev_price_low_idx]
                    # Bullish divergence: price lower low + RSI higher low
                    if price_curr < price_prev and rsi_curr > rsi_prev:
                        # Extra filter: RSI near oversold (< 45)
                        if rsi_curr < 45:
                            # Enter at next bar open
                            if i + 1 < len(df):
                                in_trade = True
                                entry_idx = i + 1
                                entry_price = df["Open"].iloc[i + 1]
                                entry_rsi = rsi_vals.iloc[i]
                                bars_held = 0

    # Compute stats
    if not trades:
        return {
            "symbol": symbol,
            "trades": 0,
            "win_rate_pct": 0,
            "avg_return_pct": 0,
            "avg_leveraged_return_pct": 0,
            "total_return_pct": 0,
            "total_leveraged_return_pct": 0,
            "max_drawdown_pct": 0,
            "sharpe_daily": 0,
            "profit_factor": 0,
            "bars_held_avg": 0,
        }

    returns = [t["return_pct"] / 100 for t in trades]
    lev_returns = [t["return_leveraged"] / 100 for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]
    lev_wins = [r for r in lev_returns if r > 0]
    lev_losses = [r for r in lev_returns if r <= 0]

    win_rate = len(wins) / len(returns) * 100
    avg_ret = np.mean(returns) * 100
    avg_lev = np.mean(lev_returns) * 100
    total_ret = (np.prod([1 + r for r in returns]) - 1) * 100
    total_lev = (np.prod([1 + r for r in lev_returns]) - 1) * 100

    # Max drawdown from equity curve
    equity = 10000 * np.cumprod([1 + r for r in lev_returns])
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak
    max_dd = dd.min() * 100

    # Sharpe (daily-ish: each bar is 15min, ~26 bars/day)
    bars_per_day = 26
    if len(lev_returns) > 1:
        sharpe = np.mean(lev_returns) / max(np.std(lev_returns, ddof=1), 1e-9) * np.sqrt(bars_per_day * 252)
    else:
        sharpe = 0

    # Profit factor
    gross_profit = sum(lev_wins) if lev_wins else 0
    gross_loss = abs(sum(lev_losses)) if lev_losses else 0
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0

    return {
        "symbol": symbol,
        "trades": len(trades),
        "win_rate_pct": round(win_rate, 1),
        "avg_return_pct": round(avg_ret, 2),
        "avg_leveraged_return_pct": round(avg_lev, 2),
        "total_return_pct": round(total_ret, 2),
        "total_leveraged_return_pct": round(total_lev, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_daily": round(sharpe, 3),
        "profit_factor": round(pf, 2),
        "bars_held_avg": round(np.mean([t["bars_held"] for t in trades]), 1),
        "trades_detail": trades[:20],  # keep first 20 for inspection
    }


def main():
    end = datetime.now()
    start = end - timedelta(days=60)  # 60 days of 15min

    all_stats = []
    for sym in SYMBOLS:
        req = StockBarsRequest(
            symbol_or_symbols=sym,
            timeframe=TimeFrame(15, TimeFrameUnit.Minute),
            start=start,
            end=end,
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

        print(f"\n{sym}: {len(df)} 15min bars ({df['Date'].iloc[0]} -> {df['Date'].iloc[-1]})")
        stats = backtest_symbol(df, sym)
        all_stats.append(stats)

        print(f"  Trades: {stats['trades']}  Win rate: {stats['win_rate_pct']}%  "
              f"Avg ret: {stats['avg_return_pct']}%  Avg lev: {stats['avg_leveraged_return_pct']}%")
        print(f"  Total: {stats['total_return_pct']}% (spot) / {stats['total_leveraged_return_pct']}% (3x leverage)")
        print(f"  MaxDD: {stats['max_drawdown_pct']}%  Sharpe: {stats['sharpe_daily']}  "
              f"PF: {stats['profit_factor']}  Avg bars: {stats['bars_held_avg']}")

    # Summary table
    print("\n\n=== SUMMARY: RSI BULLISH DIVERGENCE 15min (3x leverage) ===")
    print(f"{'Symbol':<8} {'Trades':>6} {'Win%':>6} {'AvgRet%':>8} {'AvgLev%':>9} {'TotalLev%':>10} {'MaxDD%':>8} {'Sharpe':>7} {'PF':>6} {'AvgBars':>8}")
    print("-" * 90)
    for s in all_stats:
        print(f"{s['symbol']:<8} {s['trades']:>6} {s['win_rate_pct']:>6.1f} {s['avg_return_pct']:>8.2f} "
              f"{s['avg_leveraged_return_pct']:>9.2f} {s['total_leveraged_return_pct']:>10.1f} "
              f"{s['max_drawdown_pct']:>8.1f} {s['sharpe_daily']:>7.2f} {s['profit_factor']:>6.2f} {s['bars_held_avg']:>8.1f}")

    # Find top performers
    valid = [s for s in all_stats if s["trades"] >= 3 and s["sharpe_daily"] > 0]
    valid.sort(key=lambda x: x["sharpe_daily"], reverse=True)
    print("\n=== TOP 3 by Sharpe (min 3 trades) ===")
    for i, s in enumerate(valid[:3], 1):
        print(f"#{i}: {s['symbol']} — Sharpe={s['sharpe_daily']:.2f}, Trades={s['trades']}, "
              f"WinRate={s['win_rate_pct']}%, TotalLev={s['total_leveraged_return_pct']:.1f}%, MaxDD={s['max_drawdown_pct']:.1f}%")

    # Save results
    Path("results").mkdir(exist_ok=True)
    out = {
        "strategy": "rsi_bullish_divergence_15min",
        "timeframe": "15Min",
        "period": f"{start.date()} to {end.date()}",
        "params": {
            "rsi_period": RSI_PERIOD,
            "swing_lookback": SWING_LOOKBACK,
            "exit_bars": EXIT_BARS,
            "rsi_exit": RSI_EXIT,
            "leverage": LEVERAGE,
        },
        "results": all_stats,
    }
    Path("results/divergence_backtest.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved to results/divergence_backtest.json")


if __name__ == "__main__":
    main()
