"""Dispatch authorized issue requests to fixed, validated scripts."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

def main():
    event=json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf8"))
    issue=event["issue"]
    title=issue.get("title","")
    if title.startswith("SCR LAB: "):
        print("Run interactive research query",flush=True)
        subprocess.run([sys.executable,"-m","scripts.chart_query"],check=True)
        return
    match=re.fullmatch(r"SCR BT: ([A-Za-z0-9.^,=\-]{1,200}) (1y|2y|5y|10y|max) ([DWM])",title)
    if not match:
        raise SystemExit("Unsupported SCR request")
    symbols,period,timeframe=match.groups()
    subprocess.run([sys.executable,"-m","scripts.scr_runner","--symbols",symbols,
                    "--period",period,"--timeframe",timeframe,"--output","reports"],check=True)

if __name__=="__main__":
    main()
