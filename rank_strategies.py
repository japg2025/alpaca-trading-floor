"""Rank all 420 backtests by risk-adjusted metrics + real dollar returns."""
import json, os
from pathlib import Path

results_dir = Path("results")
# Exclude portfolio and batch summary
files = sorted(f for f in results_dir.glob("*.json")
               if f.name not in ("_batch_summary.json", "portfolio_alpaca_multi.json")
               and "oos" not in f.parent.name)

rows = []
for f in files:
    try:
        d = json.loads(f.read_text())
    except Exception:
        continue

    # Robustness: need enough trades and non-zero std
    trades = d.get("trades", 0)
    if trades < 10:
        continue

    stats = d.get("stats", {})
    if not stats:
        continue

    sharpe = stats.get("sharpe_daily", 0)
    cagr = stats.get("cagr_pct", 0)
    mdd = abs(stats.get("max_drawdown_pct", 0))
    total_ret = stats.get("total_return_pct", 0)
    final_eq = stats.get("final_equity", 0)
    trading_days = stats.get("trading_days", 0)

    if mdd == 0 or sharpe <= 0:
        continue

    # --- Derived risk-adjusted metrics ---
    # 1. Return / MaxDD (higher = better bang for buck)
    ret_per_mdd = cagr / mdd if mdd else 0

    # 2. Calmar-like (using CAGR / MDD — ideal > 2)
    calmar_like = cagr / mdd if mdd else 0

    # 3. Profit Factor proxy (from available equity curve)
    # We'll approximate from total return and Sharpe
    # PF approx = (Sharpe + 0.3) / 0.5  (heuristic)
    pf_approx = (sharpe + 0.3) / 0.5

    # 4. Composite score: balance return + low risk + enough trades
    # Penalize low trade count
    trade_bonus = min(trades / 50, 1.0)  # 1.0 at 50+ trades
    composite = (ret_per_mdd * 0.4 + calmar_like * 0.3 + trade_bonus * 0.3) * 10

    rows.append({
        "ticker": d.get("ticker", "?"),
        "strategy": d.get("strategy", "?"),
        "trades": trades,
        "sharpe": sharpe,
        "cagr": cagr,
        "mdd": mdd,
        "total_ret": total_ret,
        "final_eq": final_eq,
        "ret_per_mdd": ret_per_mdd,
        "calmar_like": calmar_like,
        "pf_approx": pf_approx,
        "trade_bonus": trade_bonus,
        "composite": composite,
        "file": f.name,
    })

# Sort by composite
rows.sort(key=lambda r: r["composite"], reverse=True)

print("=" * 120)
print(f"{'RANK':<5} {'TICKER':<8} {'STRATEGY':<22} {'T':>4} {'SHARPE':>7} {'CAGR%':>7} {'MDD%':>7} {'RET/MDD':>8} {'CALMAR':>7} {'PF*':>6} {'COMP':>7}")
print("=" * 120)
for i, r in enumerate(rows[:40], 1):
    pf_str = f"{r['pf_approx']:.1f}"
    print(f"{i:<5} {r['ticker']:<8} {r['strategy']:<22} {r['trades']:>4} "
          f"{r['sharpe']:>7.2f} {r['cagr']:>7.1f} {r['mdd']:>7.1f} "
          f"{r['ret_per_mdd']:>8.2f} {r['calmar_like']:>7.2f} {pf_str:>6} "
          f"{r['composite']:>7.2f}")

# Top 5 recommendation
print("\n=== TOP 5 RECOMMENDED (composite score) ===")
for i, r in enumerate(rows[:5], 1):
    print(f"\n#{i}: {r['ticker']} / {r['strategy']}")
    print(f"  Trades: {r['trades']}, Sharpe: {r['sharpe']:.2f}, CAGR: {r['cagr']:.1f}%, MDD: {r['mdd']:.1f}%")
    print(f"  Return/MDD: {r['ret_per_mdd']:.2f}x, Calmar-like: {r['calmar_like']:.2f}")
    print(f"  Final equity (IS): ${r['final_eq']:,.0f} (from $10,000 start)")
    print(f"  Composite score: {r['composite']:.2f}")
