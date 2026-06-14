"""Enhanced dashboard: top 3 as combined portfolio recommendation."""
import json
from pathlib import Path

with open("results/divergence_backtest.json") as f:
    div_data = json.load(f)

div_results = div_data["results"]
valid = [s for s in div_results if s["trades"] >= 3 and s["sharpe_daily"] > 0]
valid.sort(key=lambda x: x["sharpe_daily"], reverse=True)

# Top 3 by Sharpe
top3 = valid[:3]
top3_symbols = [s["symbol"] for s in top3]

# Compute combined equity curve (equal weight across trades, interleaved by date)
# Build trade list per symbol with date and leveraged return
all_trades = []
for s in top3:
    for t in s.get("trades_detail", []):
        all_trades.append({
            "date": t["entry_date"][:10],
            "symbol": s["symbol"],
            "ret": t["return_leveraged"] / 100.0,
        })

# Sort by date
all_trades.sort(key=lambda x: x["date"])

# Equal-weight portfolio: each trade gets 1/3 of capital (rebalanced per trade)
# This is a simplified approximation (not perfect but directionally correct)
eq_port = [1000.0]
port_dates = ["start"]
active_positions = {sym: 0.0 for sym in top3_symbols}  # weight allocated
per_trade = 1.0 / len(top3_symbols)

for t in all_trades:
    sym = t["symbol"]
    ret = t["ret"]
    # Each trade represents 1/3 of portfolio; apply return to that slice
    current = eq_port[-1]
    # Realistic: each leg has its own capital portion, grow independently
    # Approximate by applying return to the whole portfolio weighted by participation
    # Simplified: compound each trade onto the total
    eq_port.append(current * (1 + ret * per_trade))
    port_dates.append(t["date"])

# Total return from combined curve
total_ret_port = (eq_port[-1] - 1000.0) / 1000.0 * 100
max_dd_port = min((eq_port[i] - max(eq_port[:i+1])) / max(eq_port[:i+1]) * 100 for i in range(1, len(eq_port)))

# Build per-symbol equity for top 3
charts = []
for s in top3:
    trades = s.get("trades_detail", [])
    if not trades:
        continue
    eq = [1000.0]
    dates = ["start"]
    for t in trades:
        eq.append(eq[-1] * (1 + t["return_leveraged"] / 100.0))
        dates.append(t["entry_date"][:10])
    charts.append({
        "symbol": s["symbol"],
        "dates": dates,
        "equity": [round(v, 2) for v in eq],
        "final": round(eq[-1], 2),
        "max": round(max(eq), 2),
        "min": round(min(eq), 2),
    })

# Combined chart
port_chart = {
    "symbol": "PORTFOLIO (SPY+AAPL+GOOGL)",
    "dates": port_dates,
    "equity": [round(v, 2) for v in eq_port],
    "final": round(eq_port[-1], 2),
    "max": round(max(eq_port), 2),
    "min": round(min(eq_port), 2),
}
charts.append(port_chart)

# Weights for recommendation
weights = {
    "SPY": 0.35,   # lower risk, high WR, lower return
    "AAPL": 0.35,  # high total return, low MDD
    "GOOGL": 0.30,  # balanced
}

# HTML build
html = []
html.append("<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'>")
html.append("<meta name='viewport' content='width=device-width, initial-scale=1.0'>")
html.append("<title>Divergences RSI 15min — Portfolio Recomendado $1k</title>")
html.append("<script src='https://cdn.jsdelivr.net/npm/chart.js'></script>")
html.append("<style>")
html.append("  * { box-sizing: border-box; font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; }")
html.append("  body { margin: 0; background: #0f172a; color: #e2e8f0; }")
html.append("  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }")
html.append("  h1 { font-size: 1.8em; margin-bottom: 4px; color: #f1f5f9; }")
html.append("  .subtitle { color: #94a3b8; margin-bottom: 24px; }")
html.append("  .badge { display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 0.75em; font-weight: 600; margin: 2px; }")
html.append("  .badge-green { background: #064e3b; color: #6ee7b7; }")
html.append("  .badge-blue { background: #1e3a5f; color: #93c5fd; }")
html.append("  .badge-purple { background: #3b0764; color: #d8b4fe; }")
html.append("  .section { background: #1e293b; border-radius: 12px; padding: 20px; margin-bottom: 20px; }")
html.append("  .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; }")
html.append("  .kpi { text-align: center; padding: 14px; border-radius: 8px; background: #0f172a; border: 1px solid #334155; }")
html.append("  .kpi-value { font-size: 1.7em; font-weight: 700; margin: 4px 0; }")
html.append("  .kpi-label { font-size: 0.75em; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; }")
html.append("  .positive { color: #34d399; } .negative { color: #f87171; } .warn { color: #fbbf24; }")
html.append("  table { width: 100%; border-collapse: collapse; font-size: 0.9em; }")
html.append("  th, td { padding: 10px 12px; text-align: right; border-bottom: 1px solid #334155; }")
html.append("  th { font-weight: 600; color: #cbd5e1; background: #0f172a; }")
html.append("  td:first-child, th:first-child { text-align: left; }")
html.append("  .highlight { background: #1e3a5f; padding: 2px 6px; border-radius: 4px; color: #93c5fd; }")
html.append("  .chart-box { background: #0f172a; border-radius: 8px; padding: 12px; margin-top: 12px; }")
html.append("  canvas { max-height: 300px; }")
html.append("</style></head><body><div class='container'>")

html.append("<h1>📊 Divergencias RSI 15min — Portfolio Recomendado</h1>")
html.append("<div class='subtitle'>")
html.append("  Estrategia: RSI bullish divergence 15min &nbsp;|&nbsp;")
html.append("  <span class='badge badge-green'>Portfolio: SPY + AAPL + GOOGL</span> &nbsp;|&nbsp;")
html.append("  <span class='badge badge-blue'>Capital base: $1,000</span> &nbsp;|&nbsp;")
html.append("  <span class='badge badge-blue'>60 días (15min)</span>")
html.append("</div>")

# Portfolio recommendation section
html.append("<div class='section'><h2>💼 Portafolio Recomendado (Top 3)</h2>")
html.append("<div class='kpi-grid'>")
for s in top3:
    w = weights[s["symbol"]]
    final_1k = 1000 * (1 + s["total_leveraged_return_pct"]/100)
    html.append(f"<div class='kpi'>")
    html.append(f"<div class='kpi-label'>{s['symbol']} ({w:.0%})</div>")
    html.append(f"<div class='kpi-value positive'>${final_1k:.2f}</div>")
    html.append(f"<div class='kpi-label'>Final $1k</div>")
    html.append(f"<div style='margin-top:6px; font-size:0.8em;'>Sharpe {s['sharpe_daily']:.1f} | WR {s['win_rate_pct']:.1f}%</div>")
    html.append(f"</div>")
# Combined portfolio KPI
html.append(f"<div class='kpi' style='border-color:#3b82f6;'>")
html.append(f"<div class='kpi-label' style='color:#93c5fd;'>COMBINADO</div>")
html.append(f"<div class='kpi-value positive'>${port_chart['final']:.2f}</div>")
html.append(f"<div class='kpi-label'>Final $1k</div>")
html.append(f"<div style='margin-top:6px; font-size:0.8em;'>+{total_ret_port:.1f}% | MaxDD {max_dd_port:.1f}%</div>")
html.append(f"</div>")
html.append("</div></div>")

# Weights table
html.append("<div class='section'><h2>⚖️ Asignación Sugerida</h2>")
html.append("<table><tr><th>Ticker</th><th>Peso</th><th>Monto ($1,000)</th><th>Sharpe IS</th><th>Win Rate</th><th>Max DD</th><th>Total Lev</th></tr>")
for s in top3:
    w = weights[s["symbol"]]
    monto = 1000 * w
    final_1k = 1000 * (1 + s["total_leveraged_return_pct"]/100)
    final_alloc = final_1k * w
    html.append(f"<tr><td><strong class='highlight'>{s['symbol']}</strong></td><td>{w:.0%}</td><td>${monto:.2f}</td><td>{s['sharpe_daily']:.1f}</td><td>{s['win_rate_pct']:.1f}%</td><td>{s['max_drawdown_pct']:.1f}%</td><td class='positive'>+{s['total_leveraged_return_pct']:.1f}%</td></tr>")
html.append(f"<tr style='background:#1e3a5f;'><td><strong>TOTAL</strong></td><td>100%</td><td>$1,000.00</td><td>—</td><td>—</td><td>{max_dd_port:.1f}%</td><td class='positive'>+{total_ret_port:.1f}%</td></tr>")
html.append("</table></div>")

# Individual curves + combined
html.append("<div class='section'><h2>💹 Curva de Equity: Activos + Portafolio Combinado</h2>")
html.append("<p style='color:#94a3b8; font-size:0.9em;'>Cada punto = capital después de cada trade cerrado (apalancamiento 3x simulado). Última línea = equity del portfolio combinado.</p>")
for c in charts:
    color = "#60a5fa" if c["symbol"].startswith("PORT") else "#34d399"
    fill = "rgba(96,165,250,0.2)" if c["symbol"].startswith("PORT") else "rgba(52,211,153,0.1)"
    html.append(f"<div class='chart-box'><strong>{c['symbol']}</strong>: {c['dates'][0]} → {c['dates'][-1]} | Final: ${c['final']:.2f} | Max: ${c['max']:.2f} | Min: ${c['min']:.2f}")
    html.append(f"<canvas id='chart_{c['symbol'].replace(' ','_')}' width='400' height='180'></canvas></div>")
    html.append("<script>")
    html.append(f"(function(){{")
    html.append(f"  const ctx = document.getElementById('chart_{c['symbol'].replace(' ','_')}').getContext('2d');")
    labels_json = json.dumps(c["dates"])
    data_json = json.dumps(c["equity"])
    html.append(f"  new Chart(ctx, {{")
    html.append(f"    type: 'line',")
    html.append(f"    data: {{")
    html.append(f"      labels: {labels_json},")
    html.append(f"      datasets: [{{")
    html.append(f"        label: '{c['symbol']}',")
    html.append(f"        data: {data_json},")
    html.append(f"        borderColor: '{color}',")
    html.append(f"        backgroundColor: '{fill}',")
    html.append(f"        fill: true,")
    html.append(f"        tension: 0.2,")
    html.append(f"        pointRadius: 2,")
    html.append(f"      }}]")
    html.append(f"    }},")
    html.append(f"    options: {{")
    html.append(f"      responsive: true,")
    html.append(f"      plugins: {{ legend: {{ labels: {{ color: '#e2e8f0' }} }} }},")
    html.append(f"      scales: {{")
    html.append(f"        x: {{ ticks: {{ color: '#94a3b8', maxTicksLimit: 6 }}, grid: {{ color: '#334155' }} }},")
    html.append(f"        y: {{ ticks: {{ color: '#94a3b8' }}, grid: {{ color: '#334155' }} }}")
    html.append(f"      }}")
    html.append(f"    }}")
    html.append(f"  }});")
    html.append(f"}})();")
    html.append("</script>")

html.append("</div>")

# Recommendation / plan
html.append("<div class='section'><h2>🎯 Plan de Ejecución con $1,000</h2><div style='line-height:1.7;'>")
html.append("<h3>Asignación y reglas</h3><ul>")
for s in top3:
    w = weights[s["symbol"]]
    monto = 1000 * w
    html.append(f"<li><strong>{s['symbol']}</strong>: ${monto:.0f} ({w:.0%}) — calls OTM 0-1DTE cuando la divergencia dispare</li>")
html.append(f"<li><strong>Riesgo máximo por trade:</strong> 5% del capital total = $50</li>")
html.append(f"<li><strong>Stop-loss portfolio:</strong> -10% ($100) → pausa total 1 semana</li>")
html.append("<li><strong>Frecuencia máxima:</strong> 1 trade por activo por día (no sobreexponer)</li>")
html.append("</ul>")
html.append("<h3>Fases</h3><ul>")
html.append("<li><strong>Fase 1 (próximas 2 semanas):</strong> Paper trading — registrar cada señal, fill y P&L real</li>")
html.append("<li><strong>Fase 2 (si WR real ≥ 65%):</strong> Live con los 3 activos en calls fraccionales, monto inicial $300–$500</li>")
html.append("<li><strong>Fase 3 (1 mes):</strong> Agregar QQQ como 4to leg si la cartera mantiene drawdown < -8%</li>")
html.append("</ul>")
html.append("<h3>Limitaciones honestas</h3><ul>")
html.append("<li>Backtest de solo 60 días — validación insuficiente para live</li>")
html.append("<li>Calls 0-1DTE tienen theta alta; la ventana de 2h es ajustada</li>")
html.append("<li>El portafolio combinado usa equal-weight simple; no es inverse-vol ni risk-parity</li>")
html.append("<li>Resultados pasados no garantizan performance futura</li>")
html.append("</ul></div></div>")

html.append("<div style='text-align:center; color:#64748b; font-size:0.8em; padding: 16px;'>")
html.append(f"Generated por AI Trading Floor · {div_data['period']} · {div_data['timeframe']} bars<br>")
html.append("Paper Trading: $100,000 · Live objetivo: $1,000")
html.append("</div>")

html.append("</div></body></html>")

Path("reports").mkdir(exist_ok=True)
Path("reports/dashboard.html").write_text("".join(html), encoding="utf-8")
print("Done:", len("".join(html)), "bytes")
print("Top3:", top3_symbols)
print("Portfolio final:", round(eq_port[-1], 2), "Return:", round(total_ret_port, 2), "%")
