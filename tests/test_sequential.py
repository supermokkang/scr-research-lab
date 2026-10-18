import pandas as pd
from engine import Params,signals

def frame(S,C,R):
    return pd.DataFrame({'S':S,'C':C,'R':R},index=pd.date_range('2025-01-01',periods=len(S)))

def test_order_rsi_stoch_cci_then_sell():
    d=frame([10,10,30,40,40,85,85,75,70,60],[-150,-150,-150,-80,-70,120,120,120,80,75],[20,35,40,45,50,75,75,75,65,60])
    out=signals(d,Params(),mode='sequential',window=26)
    assert list(out.index[out.Buy])==[d.index[3]]
    assert list(out.index[out.Sell])==[d.index[8]]

def test_last_indicator_only_triggers_and_time_limit():
    d=frame([10,30,40,40,40,40],[-130,-130,-130,-130,-90,-70],[20,20,35,50,50,50])
    out=signals(d,Params(),mode='sequential',window=26)
    assert list(out.index[out.Buy])==[d.index[4]]
    old=signals(d,Params(),mode='sequential',window=2)
    assert not old.Buy.any()
