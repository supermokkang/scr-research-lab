"""Run authorized SCR issue requests using strict argument validation."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf8"))
    issue = event["issue"]
    title = issue.get("title", "")
    match = re.fullmatch(r"SCR BT: ([A-Za-z0-9.^,=\-]{1,200}) (1y|2y|5y|10y|max) ([DWM])", title)
    if not match:
        raise SystemExit(f"Invalid request title: {title!r}")
    symbols, period, timeframe = match.groups()
    cmd = [sys.executable, "-m", "scripts.scr_runner", "--symbols", symbols, "--period", period,
           "--timeframe", timeframe, "--output", "reports"]
    print("Validated SCR issue request:", symbols, period, timeframe, flush=True)
    subprocess.run(cmd, check=True)

if __name__ == "__main__":
    main()
