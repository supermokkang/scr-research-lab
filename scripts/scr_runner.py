"""Produce reusable machine-readable SCR reports using the existing engine.py.

Run in GitHub Actions (with internet) or locally. Never fake results when data fails.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
from engine import Params, indicators, signals, run_backtest, resample_ohlc

MARKETS = {
    '.KS': 'Asia/Seoul', '.KQ': 'Asia/Seoul', '.T': 'Asia/Tokyo'
}

def validate_symbol(s):
    s = s.strip().upper()
    if not re.fullmatch(r'[A-Z0-9.^=\-]{1,24}', s):
        raise ValueError('Invalid symbol: ' + repr(s))
    return s

def venue_timezone(s):
    return next((zone for suffix, zone in MARKETS.items() if s.endswith(suffix)), 'America/New_York')

def load_prices(symbol, period):
    raw = yf.Ticker(symbol).history(period=period, interval='1d', auto_adjust=True)
    if raw is None or raw.empty:
        raise RuntimeError(f'No price history from Yahoo Finance: {symbol}')
    raw.index = pd.to_datetime(raw.index)
    if raw.index.tz is not None:
        raw.index = raw.index.tz_localize(None)
    raw.index = raw.index.normalize()
    raw = raw[['Open', 'High', 'Low', 'Close', 'Volume']].dropna(subset=['Open','High','Low','Close'])
    raw = raw[(raw[['Open','High','Low','Close']] > 0).all(axis=1)].sort_index()
    raw = raw[~raw.index.duplicated(keep='last')]
    # Conservatively exclude today's possibly incomplete daily bar.
    today = datetime.now(ZoneInfo(venue_timezone(symbol))).date()
    raw = raw.loc[raw.index.date < today]
    if len(raw) < 40:
        raise RuntimeError(f'Insufficient closed daily bars for {symbol}: {len(raw)}')
    return raw

def completed_frames(daily, timeframe):
    out = resample_ohlc(daily, timeframe)
    if timeframe == 'W':
        # exclude currently forming trading week, including Friday close ambiguity
        start_this_week = pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
        start_this_week -= pd.Timedelta(days=start_this_week.weekday())
        out = out.loc[out.index < start_this_week]
    elif timeframe == 'M':
        start_this_month = pd.Timestamp.now(tz='UTC').tz_localize(None).replace(day=1).normalize()
        out = out.loc[out.index < start_this_month]
    return out

def iso_date(x):
    return pd.Timestamp(x).date().isoformat() if not pd.isna(x) else None

def sane_num(v):
    try:
        f = float(v)
        return round(f, 6) if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None

def build_report(symbol, period='10y', timeframe='W', commission=.1):
    symbol = validate_symbol(symbol)
    daily = load_prices(symbol, period)
    frame = completed_frames(daily, timeframe)
    p = Params(commission=commission)
    if len(frame) <= max(p.cci_n,p.rsi_n,p.stoch_n) + 5:
        raise RuntimeError('Not enough completed bars after aggregation')
    history = signals(indicators(frame,p),p)
    equity, trades, metrics = run_backtest(history,p)
    signals_list=[]
    for dt,row in history.loc[history['Buy'] | history['Sell']].iterrows():
        signals_list.append({
            'date': iso_date(dt), 'side': 'buy' if row['Buy'] else 'sell',
            'close': sane_num(row['Close']), 'stochastic': sane_num(row['S']),
            'cci': sane_num(row['C']), 'rsi': sane_num(row['R']),
            'stochastic_escape': iso_date(row['S_escape_at']),
            'cci_escape': iso_date(row['C_escape_at']),
            'rsi_escape': iso_date(row['R_escape_at'])
        })
    trades_list=[]
    for _,r in trades.iterrows():
        trades_list.append({
            'buy_signal':iso_date(r['Buy signal']), 'sell_signal':iso_date(r['Sell signal']),
            'entry_date':iso_date(r['Entry']), 'exit_date':iso_date(r['Exit']),
            'entry_price':sane_num(r['Entry price']), 'exit_price':sane_num(r['Exit price']),
            'return_pct':sane_num(r['Return %'])
        })
    diagnostic_2023 = []
    for dt, row in history.loc["2023-09-01":"2023-12-15"].iterrows():
        diagnostic_2023.append({
            "date": iso_date(dt), "close": sane_num(row["Close"]),
            "S": sane_num(row["S"]), "C": sane_num(row["C"]), "R": sane_num(row["R"]),
            "S_oversold": bool(row["S"] <= p.stoch_os),
            "C_oversold": bool(row["C"] <= p.cci_os),
            "R_oversold": bool(row["R"] <= p.rsi_os),
            "buy": bool(row["Buy"]), "sell": bool(row["Sell"])
        })
    return {
        'diagnostic_2023': diagnostic_2023,
        'symbol':symbol, 'period':period, 'timeframe':timeframe,
        'generated_at_utc':datetime.now(timezone.utc).isoformat(),
        'first_completed_bar':iso_date(history.index[0]),
        'last_completed_bar':iso_date(history.index[-1]),
        'bars':len(history), 'source':'Yahoo Finance via yfinance; auto_adjust=True',
        'rule':'All S/C/R enter oversold then individually escape above thresholds; last escape at closed bar triggers buy. Reverse for sell.',
        'fill':'next completed bar open; commission each side; no forced terminal liquidation',
        'indicators':{'Stochastic':'Fast %K(5), oversold 20, overbought 80', 'CCI':'CCI(20), -100/+100','RSI':'Wilder RSI(14), 30/70'},
        'commission_percent_each_side':commission,
        'metrics':{k:sane_num(v) if isinstance(v,(float,int,np.floating,np.integer)) and not isinstance(v,bool) else v for k,v in metrics.items()},
        'signals':signals_list, 'trades':trades_list,
        'equity_last':sane_num(equity['Equity'].iloc[-1])
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--symbols',required=True,help='comma-separated tickers e.g. VOO,005930.KS,7203.T')
    ap.add_argument('--period',choices=['1y','2y','5y','10y','max'],default='10y')
    ap.add_argument('--timeframe',choices=['D','W','M'],default='W')
    ap.add_argument('--output',default='reports')
    args=ap.parse_args()
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    symbols=[validate_symbol(s) for s in args.symbols.split(',') if s.strip()]
    if len(symbols)>30:
        raise SystemExit('Maximum 30 symbols per run')
    failures=[]
    summary=[]
    for sym in symbols:
        try:
            report=build_report(sym,args.period,args.timeframe)
            outfile=root / f'{sym.replace("^","_")}_{args.timeframe}_{args.period}.json'
            outfile.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
            summary.append({'symbol':sym,'path':str(outfile),'metrics':report['metrics']})
            print('OK',sym,report['metrics'])
        except Exception as exc:
            failures.append({'symbol':sym,'error':f'{type(exc).__name__}: {exc}'})
            print('ERROR',sym,str(exc))
    (root/'last_run.json').write_text(json.dumps({'successes':summary,'failures':failures},ensure_ascii=False,indent=2),encoding='utf8')
    if failures:
        raise SystemExit(f'{len(failures)} ticker(s) failed; see reports/last_run.json')
if __name__=='__main__': main()
