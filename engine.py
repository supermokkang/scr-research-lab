"""SCR weekly/daily/monthly indicator & next-bar-open backtester.
This is a research hypothesis, not a verified reproduction of the author's rules.
"""
from dataclasses import dataclass
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class Params:
    stoch_n: int = 5
    stoch_smooth: int = 3
    cci_n: int = 20
    rsi_n: int = 14
    stoch_os: float = 20
    stoch_ob: float = 80
    cci_os: float = -100
    cci_ob: float = 100
    rsi_os: float = 30
    rsi_ob: float = 70
    commission: float = 0.1  # percent per side
    initial: float = 10000


def indicators(ohlc: pd.DataFrame, p: Params) -> pd.DataFrame:
    d = ohlc.copy().sort_index()
    lo = d['Low'].rolling(p.stoch_n, min_periods=p.stoch_n).min()
    hi = d['High'].rolling(p.stoch_n, min_periods=p.stoch_n).max()
    raw = 100 * (d['Close'] - lo) / (hi - lo).replace(0, np.nan)
    d['S'] = raw.rolling(p.stoch_smooth, min_periods=p.stoch_smooth).mean()
    typical = (d['High'] + d['Low'] + d['Close']) / 3
    sma = typical.rolling(p.cci_n, min_periods=p.cci_n).mean()
    mean_dev = typical.rolling(p.cci_n, min_periods=p.cci_n).apply(lambda x: np.mean(np.abs(x - np.mean(x))), raw=True)
    d['C'] = (typical - sma) / (0.015 * mean_dev.replace(0, np.nan))
    delta = d['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    # Wilder RSI, SMA-seeded initial calculation (not an EWM seeded at the first observation).
    avg_gain = np.full(len(d), np.nan)
    avg_loss = np.full(len(d), np.nan)
    if len(d) > p.rsi_n:
        avg_gain[p.rsi_n] = gain.iloc[1:p.rsi_n+1].mean()
        avg_loss[p.rsi_n] = loss.iloc[1:p.rsi_n+1].mean()
        for i in range(p.rsi_n+1, len(d)):
            avg_gain[i] = (avg_gain[i-1]*(p.rsi_n-1) + gain.iloc[i])/p.rsi_n
            avg_loss[i] = (avg_loss[i-1]*(p.rsi_n-1) + loss.iloc[i])/p.rsi_n
    ag = pd.Series(avg_gain, index=d.index)
    al = pd.Series(avg_loss, index=d.index)
    rs = ag / al.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi[(al == 0) & (ag > 0)] = 100
    rsi[(al == 0) & (ag == 0)] = 50
    d['R'] = rsi
    return d


def signals(d: pd.DataFrame, p: Params, mode: str = 'strict', window: int = 8) -> pd.DataFrame:
    """Two explicitly distinct SCR interpretations, evaluated at completed bar close.

    strict: ALL 3 indicators cross their own threshold on the SAME bar.
            Thus all 3 must be beyond their thresholds on the preceding bar.
    staged: each indicator visited its extreme within the previous `window` bars,
            and on the signal bar all have recovered together, with at least
            one genuinely crossing on the current bar. State is not perpetual.
    Buy/sell alternate. These are interpretations, not a verified original formula.
    """
    if mode not in ('strict', 'staged'):
        raise ValueError('Unknown SCR mode')
    if window < 1:
        raise ValueError('window must be >= 1')
    d = d.copy()
    buy = np.zeros(len(d), dtype=bool)
    sell = np.zeros(len(d), dtype=bool)
    v = d[['S', 'C', 'R']].to_numpy(dtype=float)
    low = np.array([p.stoch_os, p.cci_os, p.rsi_os])
    high = np.array([p.stoch_ob, p.cci_ob, p.rsi_ob])
    phase = 'entry'
    for i in range(1, len(d)):
        current, previous = v[i], v[i-1]
        if not (np.isfinite(current).all() and np.isfinite(previous).all()):
            continue
        threshold = low if phase == 'entry' else high
        if phase == 'entry':
            crossing = (previous <= low) & (current > low)
            above = current > low
            extreme = v[max(0, i-window):i] <= low
        else:
            crossing = (previous >= high) & (current < high)
            above = current < high
            extreme = v[max(0, i-window):i] >= high
        if mode == 'strict':
            triggered = bool(crossing.all())
        else:
            triggered = bool(above.all() and crossing.any() and extreme.any(axis=0).all())
        if triggered:
            if phase == 'entry':
                buy[i] = True
                phase = 'exit'
            else:
                sell[i] = True
                phase = 'entry'
    d['Buy'] = buy
    d['Sell'] = sell
    return d

def run_backtest(d: pd.DataFrame, p: Params) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Long-only, all-in, full shares fractional permitted, commissions paid per side.
    Cash earns zero. Trade triggered at close t fills open t+1. No terminal forced sale.
    """
    d = d.copy()
    if d.empty:
        raise ValueError('Empty price data')
    cash = float(p.initial)
    units = 0.0
    entry_date, entry_price, entry_equity, entry_signal_date = None, None, None, None
    equity_rows = []
    trades = []
    for i, (date, row) in enumerate(d.iterrows()):
        op = float(row['Open'])
        cl = float(row['Close'])
        if not np.isfinite([op, cl]).all() or op <= 0 or cl <= 0:
            raise ValueError('Price contains missing or nonpositive values')
        if i > 0 and d['Buy'].iloc[i-1] and units == 0:
            entry_equity = cash
            units = cash / (op * (1 + p.commission/100))
            cash = 0.0
            entry_date, entry_price = date, op
            entry_signal_date = d.index[i-1]
        elif i > 0 and d['Sell'].iloc[i-1] and units > 0:
            cash = units * op * (1 - p.commission/100)
            trades.append({'Buy signal': entry_signal_date, 'Sell signal': d.index[i-1],
                           'Entry': entry_date, 'Exit': date, 'Entry price': entry_price,
                           'Exit price': op, 'Return %': (cash/entry_equity-1)*100})
            units = 0
            entry_date, entry_price, entry_equity, entry_signal_date = None, None, None, None
        equity_rows.append((date, cash + units * cl))
    equity = pd.DataFrame(equity_rows, columns=['Date', 'Equity']).set_index('Date')
    equity['Buy & hold'] = p.initial * d['Close'] / float(d['Open'].iloc[0])
    equity['Buy & hold'] *= (1 - p.commission/100)  # initial entry commission approximation
    drawdown = equity['Equity'] / equity['Equity'].cummax() - 1
    td = pd.DataFrame(trades, columns=['Buy signal', 'Sell signal', 'Entry', 'Exit', 'Entry price', 'Exit price', 'Return %'])
    years = max((d.index[-1] - d.index[0]).days / 365.25, 1/365.25)
    final_eq = float(equity['Equity'].iloc[-1])
    metrics = {
        'Return %': (final_eq/p.initial-1)*100,
        'CAGR %': ((final_eq/p.initial)**(1/years)-1)*100,
        'MDD %': drawdown.min()*100,
        'B&H return %': (float(equity['Buy & hold'].iloc[-1])/p.initial-1)*100,
        'Trades': len(td),
        'Buy signals': int(d['Buy'].sum()),
        'Sell signals': int(d['Sell'].sum()),
        'Win rate %': (td['Return %'] > 0).mean()*100 if len(td) else np.nan,
        'Open position': bool(units > 0),
        'Unfilled final signal': bool(d['Buy'].iloc[-1] or d['Sell'].iloc[-1]),
    }
    return equity, td, metrics


def resample_ohlc(d: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Timestamp completed periods at the date of their LAST actual observation."""
    if freq == 'D':
        return d.copy()
    rule = {'W': 'W-FRI', 'M': 'ME'}[freq]
    grouped = d.groupby(pd.Grouper(freq=rule))
    rows = []
    for _, g in grouped:
        if not g.empty:
            rows.append((g.index[-1], g['Open'].iloc[0], g['High'].max(), g['Low'].min(), g['Close'].iloc[-1], g['Volume'].sum()))
    return pd.DataFrame(rows, columns=['Date','Open','High','Low','Close','Volume']).set_index('Date')
