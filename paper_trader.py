#!/usr/bin/env python3
"""
AI Trading Floor — Alpaca Paper Trading Executor
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

SCHEMA = ["Date", "Open", "High", "Low", "Close", "Volume"]

PORTFOLIO_LEGS = [
    {"ticker": "SPY",  "strategy": "rsi_bullish_divergence", "params": {"timeframe_minutes": 15}},
    {"ticker": "AAPL", "strategy": "rsi_bullish_divergence", "params": {"timeframe_minutes": 15}},
    {"ticker": "GOOGL","strategy": "rsi_bullish_divergence", "params": {"timeframe_minutes": 15}},
]


def get_alpaca_clients():
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import StockHistoricalDataClient

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        sys.exit("ERROR: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")

    base_url = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    trading = TradingClient(api_key, secret_key, paper=True)
    data_client = StockHistoricalDataClient(api_key, secret_key)
    return trading, data_client


def load_data(ticker: str, data_dir: str = "data", timeframe_minutes: int | None = None) -> pd.DataFrame:
    path = Path(data_dir) / f"{ticker}.parquet"
    if path.exists():
        df = pd.read_parquet(path)
    else:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        _, data_client = get_alpaca_clients()
        end = datetime.now()
        start = end - timedelta(days=120)

        if timeframe_minutes:
            tf = TimeFrame(timeframe_minutes, TimeFrameUnit.Minute)
        else:
            tf = TimeFrame.Day

        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=tf,
            start=start, end=end,
            feed="iex",
        )
        bars = data_client.get_stock_bars(req)
        df = bars.df.reset_index()
        rename_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "volume": "Volume",
        }
        df = df.rename(columns=rename_map)
        df["Date"] = pd.to_datetime(df["timestamp"])
        df = df[SCHEMA]
        for c in ["Open", "High", "Low", "Close", "Volume"]:
            df[c] = df[c].astype("float64")
        df = df.dropna(subset=SCHEMA).reset_index(drop=True)
    return df


def _get_toolkit_dir() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [
        here / "ai-trading-floor" / "ai-trading-floor" / "scripts",
        here / "ai-trading-floor" / "scripts",
        Path("/app") / "ai-trading-floor" / "ai-trading-floor" / "scripts",
        Path("/app") / "ai-trading-floor" / "scripts",
    ]
    for p in candidates:
        if (p / "backtest.py").exists():
            return p
    return candidates[0]

def compute_signal(ticker: str, strategy: str, params: dict) -> int:
    if strategy != "rsi_bullish_divergence":
        raise ValueError(f"Unknown strategy: {strategy}")

    timeframe_minutes = params.get("timeframe_minutes")
    df = load_data(ticker, timeframe_minutes=timeframe_minutes)
    df = df.sort_values("Date").reset_index(drop=True)

    if len(df) < 30:
        return 0

    closes = df["Close"]
    rsi_values = _rsi(closes)
    swing_lows = _find_swing_lows(closes)
    rsi_lows = _find_swing_lows(rsi_values)

    in_trade = False

    for i in range(4, len(df)):
        if pd.isna(rsi_values.iloc[i]):
            continue

        if in_trade:
            if rsi_values.iloc[i] > 60:
                in_trade = False
            continue

        if not swing_lows.iloc[i]:
            continue

        prev_idx = None
        for j in range(i - 1, 2, -1):
            if swing_lows.iloc[j]:
                prev_idx = j
                break

        if prev_idx is None:
            continue

        price_curr = closes.iloc[i]
        price_prev = closes.iloc[prev_idx]
        rsi_curr = rsi_values.iloc[i]
        rsi_prev = rsi_values.iloc[prev_idx]

        if price_curr < price_prev and rsi_curr > rsi_prev and rsi_curr < 45:
            return 1

    return 0


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


def _find_swing_lows(series: pd.Series, lookback: int = 3) -> pd.Series:
    lows = pd.Series(False, index=series.index)
    for i in range(lookback, len(series) - lookback):
        window = series.iloc[i - lookback : i + lookback + 1]
        if series.iloc[i] == window.min():
            lows.iloc[i] = True
    return lows


def get_account_summary(trading) -> dict:
    account = trading.get_account()
    return {
        "cash": float(account.cash),
        "portfolio_value": float(account.portfolio_value),
        "buying_power": float(account.buying_power),
        "status": str(account.status),
    }


def get_positions(trading) -> dict:
    positions = {}
    try:
        for p in trading.get_all_positions():
            positions[p.symbol] = {
                "qty": float(p.qty),
                "side": str(p.side),
                "market_value": float(p.market_value),
                "avg_entry_price": float(p.avg_entry_price),
            }
    except Exception as e:
        print(f"  Warning: could not fetch positions: {e}")
    return positions


def get_orders_today(trading) -> list:
    today = datetime.now().date()
    orders = []
    try:
        for o in trading.get_orders():
            o_time = pd.to_datetime(o.created_at).date()
            if o_time == today and o.status not in ("canceled", "expired"):
                orders.append({"id": o.id, "symbol": o.symbol, "side": str(o.side),
                               "qty": o.qty, "status": str(o.status)})
    except Exception as e:
        print(f"  Warning: could not fetch orders: {e}")
    return orders


def place_order(trading, ticker: str, side: str, qty: float,
                order_type: str = "market") -> dict:
    from alpaca.trading.requests import OrderRequest
    alpaca_mod = __import__("alpaca.trading.enums", fromlist=["OrderType"])
    from alpaca.trading.enums import OrderSide, TimeInForce

    order_args = {
        "symbol": ticker,
        "qty": str(round(qty, 6)),
        "side": OrderSide.BUY if side == "buy" else OrderSide.SELL,
        "type": getattr(alpaca_mod.OrderType, order_type.upper()),
        "time_in_force": TimeInForce.GTC,
    }
    req = OrderRequest(**order_args)
    order = trading.submit_order(req)
    return {
        "id": order.id,
        "symbol": order.symbol,
        "side": str(order.side),
        "qty": order.qty,
        "type": str(order.type),
        "status": str(order.status),
    }


def print_account(trading):
    summary = get_account_summary(trading)
    positions = get_positions(trading)

    print(f"\n{'='*50}")
    print(f"  PAPER TRADING ACCOUNT")
    print(f"{'='*50}")
    print(f"  Status:        {summary['status']}")
    print(f"  Cash:          ${summary['cash']:>12,.2f}")
    print(f"  Portfolio:     ${summary['portfolio_value']:>12,.2f}")
    print(f"  Buying Power:  ${summary['buying_power']:>12,.2f}")
    print(f"\n  Open Positions ({len(positions)}):")
    if positions:
        for sym, pos in positions.items():
            print(f"    {sym:6s}  {pos['side']:>4s}  {pos['qty']:>10.2f} shares  "
                  f"${pos['market_value']:>10,.2f}  @ ${pos['avg_entry_price']:.2f}")
    else:
        print(f"    (no open positions)")
    print()


def print_signals(signals: list, dry_run: bool = True):
    print(f"\n{'='*50}")
    tag = "[DRY RUN] " if dry_run else "[LIVE] "
    print(f"{tag}TRADING SIGNALS — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
    print(f"{'='*50}")

    for leg in signals:
        action = "HOLD" if leg["signal"] == 0 else ("LONG" if leg["signal"] == 1 else "FLAT")
        emoji = "  " if action == "HOLD" else ("🟢 " if action == "LONG" else "🔴 ")
        print(f"  {emoji}{leg['ticker']:6s}  {action:>4s}  {leg['strategy']:>22s}  "
              f"Sharpe(IS)={leg.get('sharpe', 0):.2f}  → target=${leg.get('target_value', 0):,.0f}")

    print()
    long_count = sum(1 for s in signals if s["signal"] == 1)
    flat_count = sum(1 for s in signals if s["signal"] == 0)
    print(f"  Summary: {long_count} long, {flat_count} flat")
    print()


def rebalance_portfolio(trading, signals: list, capital: float,
                        dry_run: bool = True) -> list:
    print(f"\n{'='*50}")
    if dry_run:
        print(f"  REBALANCE PLAN (dry run — no orders placed)")
    else:
        print(f"  EXECUTING ORDERS")
    print(f"{'='*50}")

    current_positions = get_positions(trading)
    orders_today = get_orders_today(trading)
    order_symbols_today = {o["symbol"] for o in orders_today}

    executed = []
    active_legs = [leg for leg in signals if leg["signal"] != 0]

    if not active_legs:
        print("  No active signals — no trades to place.")
        return executed

    per_leg = capital / max(len(active_legs), 1)

    for leg in active_legs:
        ticker = leg["ticker"]
        target_value = per_leg
        leg["target_value"] = target_value

        # Get latest price from cached data or Alpaca
        _, data_client = get_alpaca_clients()
        try:
            from alpaca.data.requests import LatestTradeRequest
            latest_req = LatestTradeRequest(symbol_or_symbols=ticker)
            latest = data_client.get_stock_latest_trade(latest_req)
            current_price = float(latest[ticker].price) if hasattr(latest, '__getitem__') else float(list(latest.values())[0].price)
        except Exception:
            df = load_data(ticker)
            current_price = float(df["Close"].iloc[-1])

        target_qty = target_value / current_price if current_price > 0 else 0
        leg["target_qty"] = target_qty

        current = current_positions.get(ticker, {})
        current_qty = float(current.get("qty", 0))
        current_side = current.get("side", "none")

        print(f"  {ticker:6s}  BUY   {target_qty:.2f} shares  "
              f"≈${target_value:,.0f}  @ ${current_price:.2f}")

        if not dry_run:
            if ticker in order_symbols_today:
                print(f"    → SKIPPED (already has order today)")
                continue
            try:
                result = place_order(trading, ticker, "buy", target_qty)
                print(f"    → Order placed: {result['id']} ({result['status']})")
                executed.append(result)
                order_symbols_today.add(ticker)
            except Exception as e:
                print(f"    → ERROR: {e}")

    return executed


def send_telegram_message(text: str):
    try:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        import urllib.request
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"  Warning: Telegram notification failed: {e}")
def main():
    parser = argparse.ArgumentParser(description="Alpaca Paper Trading")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show signals and orders without placing them")
    parser.add_argument("--capital", type=float, default=None,
                        help="Total capital to allocate (default: use account cash)")
    parser.add_argument("--scheme", default="equal_dollar",
                        help="Allocation scheme (equal_dollar or inverse_vol)")
    parser.add_argument("--tickers", default=None,
                        help="Comma-separated tickers (default: all portfolio legs)")
    parser.add_argument("--show-account", action="store_true",
                        help="Only show account status, no trading")
    args = parser.parse_args()

    load_dotenv()
    trading, data_client = get_alpaca_clients()

    print_account(trading)

    if args.show_account:
        return

    if args.tickers:
        selected = [t.strip().upper() for t in args.tickers.split(",")]
        legs = [leg for leg in PORTFOLIO_LEGS if leg["ticker"] in selected]
    else:
        legs = PORTFOLIO_LEGS

    if args.capital:
        capital = float(args.capital)
    else:
        capital = 1000.0  # Plan de ejecución: $1,000 base

    print(f"  Capital available: ${capital:,.2f}")
    print(f"  Allocation scheme: {args.scheme}")
    print(f"  Legs: {len(legs)} strategies")
    print()

    # Telegram: notificar señales generadas
    telegram_lines = [f"📡 *Señales generadas* — {datetime.now().strftime('%Y-%m-%d %H:%M ET')}\n"]
    signals = []
    print("Generating signals...")
    for leg in legs:
        print(f"  {leg['ticker']} / {leg['strategy']} ...", end=" ")
        try:
            signal = compute_signal(leg["ticker"], leg["strategy"], leg["params"])

            result_path = f"results/{leg['ticker']}_{leg['strategy']}.json"
            if os.path.exists(result_path):
                with open(result_path) as f:
                    d = json.load(f)
                sharpe = d.get("stats", {}).get("sharpe_daily", 0.0)
            else:
                sharpe = 0.0

            signals.append({
                "ticker": leg["ticker"],
                "strategy": leg["strategy"],
                "signal": signal,
                "sharpe": sharpe,
                "params": leg["params"],
            })
            action = "LONG" if signal == 1 else ("FLAT" if signal == 0 else "SHORT")
            print(f"→ {action} (Sharpe IS={sharpe:.2f})")
            telegram_lines.append(f"• {leg['ticker']}: {action} (Sharpe {sharpe:.2f})")
        except Exception as e:
            print(f"ERROR: {e}")
            telegram_lines.append(f"• {leg['ticker']}: ERROR ({e})")
            continue

    print_signals(signals, dry_run=args.dry_run)
    telegram_lines.append(f"\nPortfolio: {sum(1 for s in signals if s['signal'] == 1)} long, {sum(1 for s in signals if s['signal'] == 0)} flat")

    # Notificar señales iniciales
    send_telegram_message("\n".join(telegram_lines))

    # Ejecutar/rebalancear
    executed = rebalance_portfolio(trading, signals, capital, dry_run=args.dry_run)

    # Telegram: notificar ejecuciones y P&L estimado
    trade_lines = [f"💰 *{'DRY RUN' if args.dry_run else 'PAPER'} — Trades*\n"]
    if not executed:
        trade_lines.append("No se ejecutaron trades en esta corrida.")
    else:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M ET")
        for idx, order in enumerate(executed, 1):
            symbol = order.get("symbol", "?")
            side = order.get("side", "?")
            qty = float(order.get("qty", 0))
            status = order.get("status", "?")
            order_id = order.get("id", "?")
            entry_price = order.get("filled_avg_price") or order.get("limit_price") or "?"
            trade_lines.append(
                f"#{idx} {side} `{symbol}` {qty} @ {entry_price}\n"
                f"Apertura: {now_str} | Estado: {status}\n"
                f"ID: {order_id}\n"
            )

        # Estimación simple de P&L usando última posición conocida
        try:
            positions = get_positions(trading)
            for pos_symbol, pos in positions.items():
                market_value = float(pos.get("market_value", 0))
                avg_entry = float(pos.get("avg_entry_price", 0))
                current_qty = float(pos.get("qty", 0))
                side = pos.get("side", "long")
                if current_qty == 0 or avg_entry == 0:
                    continue
                current_price = market_value / current_qty if current_qty else 0
                pnl = (current_price - avg_entry) * current_qty
                pnl_pct = ((current_price - avg_entry) / avg_entry) * 100 if avg_entry else 0
                sign = "+" if pnl >= 0 else ""
                trade_lines.append(f"📊 `{pos_symbol}` P&L: {sign}{pnl:,.2f} ({sign}{pnl_pct:.2f}%)")
        except Exception as e:
            print(f"  Warning: could not fetch P&L: {e}")

    send_telegram_message("\n".join(trade_lines))

    mode = "DRY RUN" if args.dry_run else "PAPER TRADING"
    print(f"\n{'='*50}")
    print(f"  Done — {mode} mode")
    print(f"  Dashboard: https://app.alpaca.markets/paper/dashboard/overview")
    print(f"{'='*50}")


def build_daily_summary(trading) -> str | None:
    today = datetime.now().date()
    try:
        orders = list(trading.get_orders())
    except Exception as e:
        return f"⚠️ No se pudo obtener el resumen diario: {e}"

    today_orders = []
    for o in orders:
        try:
            o_date = pd.to_datetime(o.created_at).date()
        except Exception:
            continue
        if o_date == today and str(o.status) not in {"canceled", "expired"}:
            today_orders.append(o)

    if not today_orders:
        return None

    leg_winners = {"SPY": 0, "AAPL": 0, "GOOGL": 0}
    leg_count = {"SPY": 0, "AAPL": 0, "GOOGL": 0}
    for o in today_orders:
        symbol = getattr(o, "symbol", None) or getattr(o, "leg", {}).get("symbol")
        if symbol in leg_count:
            leg_count[symbol] += 1

    try:
        positions = get_positions(trading)
    except Exception:
        positions = {}

    lines = [f"🗓️ *Resumen diario* — {today.isoformat()}"]
    for symbol in ["SPY", "AAPL", "GOOGL"]:
        count = leg_count.get(symbol, 0)
        status = "Sin actividad"
        if count:
            status = f"{count} trade{'s' if count != 1 else ''} hoy"
        lines.append(f"• {symbol}: {status}")
        pos = positions.get(symbol)
        if pos:
            qty = float(pos.get("qty", 0))
            avg_entry = float(pos.get("avg_entry_price", 0))
            market_value = float(pos.get("market_value", 0))
            if qty and avg_entry:
                current_price = market_value / qty
                pnl = (current_price - avg_entry) * qty
                pnl_pct = ((current_price - avg_entry) / avg_entry) * 100
                sign = "+" if pnl >= 0 else ""
                lines.append(f"  📊 P&L: {sign}{pnl:,.2f} ({sign}{pnl_pct:.2f}%)")

    send_telegram_message("\n".join(lines))
    return "\n".join(lines)


if __name__ == "__main__":
    main()
