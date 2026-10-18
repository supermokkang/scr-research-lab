import numpy as np
import pandas as pd
from engine import Params, indicators, signals, run_backtest, resample_ohlc

def sample(n=150):
    idx = pd.bdate_range('2020-01-01',periods=n)
    c = pd.Series(100 + 10*np.sin(np.arange(n)/7) + np.arange(n)*.04, index=idx)
    return pd.DataFrame({'Open':c.shift(1).fillna(c.iloc[0]),'High':c+2,'Low':c-2,'Close':c,'Volume':100},index=idx)

def test_indicators_signal_backtest():
    d = sample()
    p = Params()
    i = indicators(d,p)
    assert i[['S','C','R']].iloc[-1].notna().all()
    assert i['R'].dropna().between(0,100).all()
    s=signals(i,p)
    eq,trades,m=run_backtest(s,p)
    assert len(eq)==len(d)
    assert (eq.Equity>0).all()
    assert m['MDD %']<=0
    assert np.isfinite(m['Return %'])

def test_next_bar_fill_no_lookahead():
    d = sample(6)
    d['Buy']=[False, True,False,False,False,False]
    d['Sell']=[False, False, False, True,False,False]
    eq,tr,m=run_backtest(d,Params(commission=0))
    assert len(tr)==1
    assert tr.iloc[0]['Entry']==d.index[2]
    assert tr.iloc[0]['Exit']==d.index[4]
    assert np.isclose(tr.iloc[0]['Entry price'],d.Open.iloc[2])
    assert np.isclose(tr.iloc[0]['Exit price'],d.Open.iloc[4])

def test_last_bar_signal_not_filled():
    d=sample(5)
    d['Buy']=[False]*4+[True]
    d['Sell']=[False]*5
    eq,tr,m=run_backtest(d,Params())
    assert len(tr)==0 and not m['Open position'] and m['Unfilled final signal']

def test_resample_last_observation():
    d=sample(70)
    w=resample_ohlc(d,'W')
    m=resample_ohlc(d,'M')
    assert w.index[-1]==d.index[-1]
    assert m.index[-1]==d.index[-1]
    assert (w.High>=w.Low).all()

def test_signal_counts_and_trade_dates():
    d = sample(6)
    d['Buy'] = [False, True, False, False, False, False]
    d['Sell'] = [False, False, False, True, False, False]
    _, tr, m = run_backtest(d, Params(commission=0))
    assert m['Buy signals'] == 1 and m['Sell signals'] == 1
    assert m['Trades'] == 1
    assert tr.iloc[0]['Buy signal'] == d.index[1]
    assert tr.iloc[0]['Sell signal'] == d.index[3]
    assert tr.iloc[0]['Entry'] == d.index[2]
    assert tr.iloc[0]['Exit'] == d.index[4]
