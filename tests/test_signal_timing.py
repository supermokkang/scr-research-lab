import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from engine import Params,indicators,signals

def test_sequential_buy_last_cci_and_sequential_sell():
    d=pd.DataFrame({'S':[15,25,25,25,25,90,75,75],
                    'C':[-120,-120,-120,0,0,120,120,80],
                    'R':[20,20,40,40,40,80,80,60]},index=pd.date_range('2025-01-01',periods=8))
    a=signals(d,Params())
    assert a.Buy.sum()==1 and a.Buy.iloc[3]
    assert a.loc[a.index[3],'Last_escaped']=='C'
    assert a.loc[a.index[3],'R_escape_at']==a.index[2]
    assert a.loc[a.index[3],'S_escape_at']==a.index[1]
    assert a.Sell.sum()==1 and a.Sell.iloc[7]

def test_fast_k_used_for_threshold_and_smoothed_d_for_display():
    price=[50,52,53,55,56,57,58,59,61,62,61,60,59,58,57,56,55,54,53,52,51,50,52,53,54,55,57,59,61,62,64,65]
    frame=pd.DataFrame({'Open':price,'Close':price,'High':np.array(price)+1,'Low':np.array(price)-1},index=pd.date_range('2025-01-01',periods=len(price)))
    d=indicators(frame,Params())
    assert np.isclose(d['S'].iloc[-1], d['S_main'].iloc[-1])
    assert not np.isclose(d['S'].iloc[-1],d['S_signal'].iloc[-1])
