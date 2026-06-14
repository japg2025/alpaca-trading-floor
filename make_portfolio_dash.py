"""
Generate a clean, single-file dashboard for the alpaca_multi portfolio.
Outputs: D:\Alpaca\reports\portfolio_dashboard.html
"""
import json
from pathlib import Path

# Load portfolio data
with open("results/portfolio_alpaca_multi.json") as f:
    data = json.load(f)

stats = data["stats"]
per = data["per_strategy"]
corr = data["correlation_matrix"]
labels = data["corr_labels"]
matrix = data["corr_matrix"]
weights = data["weights"]
oos = data.get("oos_stats")

# Asset class mapping
ASSET_CLASS = {
    'GLD':'Commodity','SLV':'Commodity',
    'XLI':'Sector','IWM':'Equity Index',
    'AAPL':'Stock','MSFT':'Stock',
}

html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portfolio Dashboard — alpaca_multi</title>
<style>
  * {{ box-sizing: border-box; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }}
  body {{ margin: 0; background: #f5f6fa; color: #222; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 1.8em; margin-bottom: 4px; }}
  .subtitle {{ color: #666; margin-bottom: 24px; }}
  .badge {{ display: inline-block; padding: 4px 10px; border-radius: 12px; font-size: 0.75em; font-weight: 600; }}
  .badge-active {{ background: #d1fae5; color: #065f46; }}
  .badge-warn {{ background: #fef3c7; color: #92400e; }}
  .section {{ background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
  .section h2 {{ margin-top: 0; font-size: 1.2em; border-bottom: 1px solid #eee; padding-bottom: 8px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 16px; }}
  .kpi {{ text-align: center; padding: 12px; border-radius: 8px; background: #f8f9fb; }}
  .kpi-value {{ font-size: 1.6em; font-weight: 700; margin: 4px 0; }}
  .kpi-label {{ font-size: 0.75em; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }}
  .positive {{ color: #059669; }}
  .negative {{ color: #dc2626; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9em; }}
  th, td {{ padding: 10px 12px; text-align: right; border-bottom: 1px solid #f0f0f0; }}
  th {{ font-weight: 600; color: #555; }}
  td:first-child, th:first-child {{ text-align: left; }}
  tr:hover td {{ background: #fafafa; }}
  .methodology {{ line-height: 1.6; color: #333; }}
  .methodology h3 {{ font-size: 1em; margin-top: 16px; color: #444; }}
  .methodology ul {{ padding-left: 20px; }}
  .corr-cell {{ font-variant-numeric: tabular-nums; font-size: 0.85em; }}
  .corr-low {{ color: #059669; font-weight: 600; }}
  .corr-mid {{ color: #d97706; }}
  .corr-high {{ color: #dc2626; font-weight: 600; }}
</style>
</head>
<body>
<div class="container">

  <h1>📊 Portfolio <strong>alpaca_multi</strong></h1>
  <div class="subtitle">
    Paper trading &nbsp;|&nbsp;
    <span class="badge badge-active">6 legs activas</span> &nbsp;|&nbsp;
    Equal-dollar allocation &nbsp;|&nbsp;
    Creado: 2026-06-14
  </div>

  <!-- KPIs -->
  <div class="section">
    <h2>Performance (In-Sample: 2020–2025)</h2>
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-label">Sharpe</div>
        <div class="kpi-value">{stats['sharpe_daily']:.3f}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">CAGR</div>
        <div class="kpi-value {'positive' if stats['cagr_pct'] > 0 else 'negative'}">{stats['cagr_pct']:.1f}%</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Retorno total</div>
        <div class="kpi-value {'positive' if stats['total_return_pct'] > 0 else 'negative'}">+{stats['total_return_pct']:.0f}%</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Max Drawdown</div>
        <div class="kpi-value negative">{stats['max_drawdown_pct']:.1f}%</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Equity final</div>
        <div class="kpi-value">${stats['final_equity']:,.0f}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Días traded</div>
        <div class="kpi-value">{stats['trading_days']}</div>
      </div>
    </div>
  </div>

  <!-- Legs -->
  <div class="section">
    <h2>Legs del portfolio</h2>
    <p style="color:#666; font-size:0.9em; margin-top:-8px; margin-bottom:12px;">
      Cada estrategia opera sobre un activo distinto. Asignación igualitaria: ~$16,667 por estrategia activa.
    </p>
    <table>
      <tr>
        <th>Ticker</th>
        <th>Estrategia</th>
        <th>Asset class</th>
        <th>Sharpe IS</th>
        <th>CAGR</th>
        <th>Trades</th>
        <th>Max DD</th>
        <th>Peso avg</th>
      </tr>
"""

for label in labels:
    ticker = label.split("_")[0]
    strat = label.replace(ticker + "_", "")
    ac = ASSET_CLASS.get(ticker, "?")
    p = per[label]
    w = weights.get(label, 0)
    html += f"""
      <tr>
        <td><strong>{ticker}</strong></td>
        <td>{strat}</td>
        <td>{ac}</td>
        <td>{p['sharpe_daily']:.3f}</td>
        <td class="{'positive' if p['cagr_pct'] > 0 else 'negative'}">{p['cagr_pct']:.1f}%</td>
        <td>{p.get('trades', '?')}</td>
        <td class="negative">{p['max_drawdown_pct']:.1f}%</td>
        <td>{w:.1%}</td>
      </tr>
"""

html += """    </table>
  </div>

  <!-- Correlación -->
  <div class="section">
    <h2>Matriz de correlación (diversificación)</h2>
    <p style="color:#666; font-size:0.9em; margin-top:-8px; margin-bottom:12px;">
      Correlaciones cercanas a 0 = diversificación real entre activos.
    </p>
    <table>
      <tr><th>#</th>
"""

for lbl in labels:
    short = lbl.split("_")[0]
    html += f"       <th>{short}</th>\n"

html += "      </tr>\n"

for i, lbl1 in enumerate(labels):
    s1 = lbl1.split("_")[0]
    html += f"      <tr><td><strong>{s1}</strong></td>\n"
    for j, lbl2 in enumerate(labels):
        val = matrix[i][j]
        if i == j:
            css = "corr-cell"
        elif val < 0.2:
            css = "corr-cell corr-low"
        elif val < 0.6:
            css = "corr-cell corr-mid"
        else:
            css = "corr-cell corr-high"
        html += f"        <td class='{css}'>{val:.2f}</td>\n"
    html += "      </tr>\n"

oos_section = ""
if oos:
    eff = oos.get("efficiency", 0)
    eff_val = f"{eff:.1%}"
    eff_css = "positive" if eff > 0.5 else ("negative" if eff < 0 else "")
    oos_section = f"""
  <div class="section">
    <h2>Validación Out-of-Sample (2026)</h2>
    <div class="kpi-grid">
      <div class="kpi">
        <div class="kpi-label">Sharpe OOS</div>
        <div class="kpi-value">{oos['sharpe_daily']:.3f}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">CAGR OOS</div>
        <div class="kpi-value {'positive' if oos['cagr_pct'] > 0 else 'negative'}">{oos['cagr_pct']:.1f}%</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Max DD OOS</div>
        <div class="kpi-value negative">{oos['max_drawdown_pct']:.1f}%</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Efficiency (OOS/IS)</div>
        <div class="kpi-value {eff_css}">{eff_val}</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">Final equity OOS</div>
        <div class="kpi-value">${oos['final_equity']:,.0f}</div>
      </div>
    </div>
    <p style="color:#888; font-size:0.85em; margin-top:8px;">
      Nota: OOS efficiency &lt; 0.5 significa que el rendimiento fuera de muestra fue menor al in-sample.
      Esto es normal; una efficiency &gt; 0.7 sugeriría robustez extrema.
    </p>
  </div>
"""

html += f"""  </div>{oos_section}

  <!-- Metodología -->
  <div class="section">
    <h2>Cómo se construyó este portfolio</h2>
    <div class="methodology">
      <h3>1. Universo</h3>
      <ul>
        <li>30 activos: 15 ETFs (SPY, QQQ, TLT, GLD…) + 15 blue-chips (AAPL, MSFT, NVDA…)</li>
        <li>Datos: 5 años (2020–2025) + ventana OOS 2026 via Alpaca</li>
      </ul>

      <h3>2. Backtesting</h3>
      <ul>
        <li>7 estrategias por activo: sma_crossover, rsi_reversion, breakout, bollinger_meanrev,
            donchian_trend, vol_gate_trend, anchored_vwap_trend</li>
        <li>420 combinaciones corridas con anti-look-ahead (shift 1 día)</li>
        <li>Las señales son booleanas: True = en posición, False = fuera</li>
      </ul>

      <h3>3. Selección</h3>
      <ul>
        <li>Se descartaron estrategias con &lt; 5 trades (ruido estadístico)</li>
        <li>Se priorizó baja correlación < 0.3 entre legs</li>
        <li>Se eligieron 6 estrategias activas de distintos asset classes:
            <strong>commodities (GLD, SLV), sector (XLI), equity index (IWM), y stocks (AAPL, MSFT)</strong>
        </li>
      </ul>

      <h3>3. Combinación</h3>
      <ul>
        <li>Esquema: equal-dollar (1/6 del capital por cada estrategia activa)</li>
        <li>Rebalanceo diario basado en señales booleanas</li>
        <li>Sin apalancamiento, sin short (solo long/flat)</li>
        <li>Corredor: Alpaca Paper Trading ($100,000 capital inicial)</li>
      </ul>

      <h3>4. Limitaciones honestas</h3>
      <ul>
        <li>El Sharpe OOS es menor que el IS — todavía hay que confirmar robustez con más datos</li>
        <li>Este portfolio NO es una recomendación de inversión; es una演示 del sistema</li>
        <li>No hay stop-loss hard definido (solo los implícitos de cada estrategia)</li>
      </ul>
    </div>
  </div>

  <div style="text-align:center; color:#aaa; font-size:0.8em; padding: 16px;">
    Generated by AI Trading Floor · {data['shared_window']['start']} a {data['shared_window']['end']} · {data['shared_window']['days']} días
  </div>

</div>
</body>
</html>
"""

out = Path("reports/portfolio_dashboard.html")
out.write_text(html, encoding="utf-8")
print(f"Wrote {out} ({len(html):,} bytes)")
