"""Research query endpoint; accepts validated JSON in owner-created GitHub issue body."""
import json
import os
import re
from dataclasses import replace
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
from engine import Params, indicators, signals, run_backtest
from scripts.scr_runner import load_prices, completed_frames, validate_symbol, iso_date, sane_num

ALLOWED = {"stoch_n": (2, 60, int), "stoch_smooth": (1, 60, int),
           "cci_n": (2, 100, int), "rsi_n": (2, 100, int),
           "stoch_os": (1, 49, float), "stoch_ob": (51, 99, float),
           "cci_os": (-400, -1, float), "cci_ob": (1, 400, float),
           "rsi_os": (1, 49, float), "rsi_ob": (51, 99, float),
           "commission": (0, 3, float)}
def validate(req):
    if not isinstance(req, dict) or set(req) - {"symbol","period","timeframe","start","end","params"}:
        raise ValueError("Unexpected request fields")
    symbol = validate_symbol(req["symbol"])
    if req.get("period", "10y") not in ("1y","2y","5y","10y","max"):
        raise ValueError("Invalid period")
    if req.get("timeframe", "W") not in ("D","W","M"):
        raise ValueError("Invalid timeframe")
    kw = req.get("params", {})
    if not isinstance(kw,dict) or set(kw)-set(ALLOWED):
        raise ValueError("Unsupported indicator parameters")
    parsed = {}
    for k,v in kw.items():
        lo,hi,typ = ALLOWED[k]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not lo <= v <= hi:
            raise ValueError("Invalid value for "+k)
        parsed[k]=typ(v)
    for k in ("start","end"):
        if k in req:
            if not isinstance(req[k],str) or not re.fullmatch(r"20\d\d-\d\d-\d\d",req[k]):
                raise ValueError("Invalid date for "+k)
            pd.Timestamp(req[k])
    return symbol, replace(Params(), **parsed)

def run(req):
    symbol,p = validate(req)
    period=req.get("period","10y")
    timeframe=req.get("timeframe","W")
    daily=load_prices(symbol,period)
    frame=completed_frames(daily,timeframe)
    hist=signals(indicators(frame,p),p)
    if len(hist)<40:
        raise ValueError("Too few completed bars")
    equity,trades,metrics=run_backtest(hist,p)
    selection=hist
    if "start" in req: selection=selection.loc[req["start"]:]
    if "end" in req: selection=selection.loc[:req["end"]]
    bars=[]
    for date,row in selection.iterrows():
        bars.append({"date":iso_date(date),**{k:sane_num(row[k]) for k in
                    ("Open","High","Low","Close","S","C","R","S_signal","C_signal","R_signal")},
                     "buy":bool(row["Buy"]),"sell":bool(row["Sell"])})
    entries=[]
    for date,row in hist.loc[hist["Buy"]|hist["Sell"]].iterrows():
        entries.append({"date":iso_date(date),"side":"buy" if row["Buy"] else "sell",
                         "S_escape":iso_date(row["S_escape_at"]),
                         "C_escape":iso_date(row["C_escape_at"]),
                         "R_escape":iso_date(row["R_escape_at"])})
    tx=[]
    for _,row in trades.iterrows():
        tx.append({"buy_signal":iso_date(row["Buy signal"]),
                   "sell_signal":iso_date(row["Sell signal"]),
                   "entry":iso_date(row["Entry"]),"exit":iso_date(row["Exit"]),
                   "return_pct":sane_num(row["Return %"])})
    result={"query":req,"symbol":symbol,"period":period,"timeframe":timeframe,
            "source":"Yahoo Finance adjusted OHLC via yfinance",
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "bar_count":len(hist),"metrics":{k:sane_num(v) if isinstance(v,(int,float)) and not isinstance(v,bool) else v for k,v in metrics.items()},
            "bars":bars,"signals":entries,"trades":tx,
            "note":"Bar close confirmation, next-bar-open fills. Monthly/weekly incomplete bars excluded; SCR formula remains research hypothesis."}
    Path("reports").mkdir(exist_ok=True)
    Path("reports/chart_query.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False,default=str),encoding="utf8")
    print("QUERY OK",symbol,timeframe,"bars",len(bars),"signals",len(entries),flush=True)

if __name__=="__main__":
    event=json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf8"))
    req=json.loads(event["issue"].get("body",""))
    run(req)
