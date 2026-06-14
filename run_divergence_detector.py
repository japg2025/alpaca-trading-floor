import pandas as pd
import numpy as np
import os

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)

def find_swing_lows(series, lookback=3):
    lows = pd.Series(False, index=series.index)
    for i in range(lookback, len(series) - lookback):
        window = series.iloc[i-lookback:i+lookback+1]
        if series.iloc[i] == window.min():
            lows.iloc[i] = True
    return lows

def detect_bullish_divergence(df):
    df = df.sort_values('Date').reset_index(drop=True)
    r = rsi(df['Close'])
    price_lows = find_swing_lows(df['Close'])
    rsi_lows = find_swing_lows(r)
    divergence = None
    for i in range(len(df)-1, len(df)-30, -1):
        if price_lows.iloc[i] and rsi_lows.iloc[i]:
            j = i-1
            while j >= 0 and not price_lows.iloc[j]:
                j -= 1
            if j < 0:
                continue
            price_now = df['Close'].iloc[i]
            price_prev = df['Close'].iloc[j]
            rsi_now = r.iloc[i]
            rsi_prev = r.iloc[j]
            if price_now < price_prev and rsi_now > rsi_prev and rsi_now < 45:
                divergence = {
                    'symbol': df['symbol'].iloc[0],
                    'entry_date': str(df['Date'].iloc[i+1]),
                    'entry_price': round(df['Open'].iloc[i+1], 2),
                    'exit_date': str(df['Date'].iloc[min(i+1+8, len(df)-1)]),
                    'exit_price': round(df['Open'].iloc[min(i+1+8, len(df)-1)], 2),
                    'rsi_entry': round(rsi_now, 1),
                    'rsi_exit': round(r.iloc[min(i+1+8, len(df)-1)], 1),
                    'return_pct': round((df['Open'].iloc[min(i+1+8, len(df)-1)] - df['Open'].iloc[i+1]) / df['Open'].iloc[i+1] * 100, 2),
                }
                break
    return divergence

symbols = ['QQQ', 'SPY', 'AAPL']
results = []
for sym in symbols:
    path = f'data/{sym}.parquet'
    if not os.path.exists(path):
        results.append({'symbol': sym, 'error': 'no data'})
        continue
    df = pd.read_parquet(path)
    if 'Date' not in df.columns:
        results.append({'symbol': sym, 'error': 'bad columns'})
        continue
    div = detect_bullish_divergence(df)
    if div:
        results.append(div)
    else:
        results.append({'symbol': sym, 'error': 'no divergence'})

best = sorted([r for r in results if 'error' not in r], key=lambda x: abs(x['return_pct']), reverse=True)
print(json.dumps({'best': best[:3], 'all': results}, indent=2))
