#!/usr/bin/env python3
"""Build dist/jarvus-watch.zip: the 24/7 watcher with only the files it needs. Run: python3 build_watch_bundle.py"""
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ["watch.py", "jarvus.py", "decide.py", "events.py", "ladder.py", "momentum.py", "volgate.py", "fetch_ohlcv.py",
           "indicators.py", "snapshot.py"]
ASSETS = ["volgate_model.json", "strategy_scoreboard.json"]
EXTRA = ["START-WINDOWS.bat", "SETUP-ALERTS-WINDOWS.bat", "start-mac-linux.sh", "README-WATCH.txt", "github-actions-jarvus-watch.yml"]

out = os.path.join(HERE, "dist", "jarvus-watch.zip")
os.makedirs(os.path.dirname(out), exist_ok=True)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for f in SCRIPTS:
        z.write(os.path.join(HERE, "scripts", f), f"jarvus-watch/scripts/{f}")
    for f in ASSETS:
        z.write(os.path.join(HERE, "assets", f), f"jarvus-watch/assets/{f}")
    for f in EXTRA:
        info = zipfile.ZipInfo(f"jarvus-watch/{f}")
        info.external_attr = (0o755 if f.endswith(".sh") else 0o644) << 16
        data = open(os.path.join(HERE, "watch", f), "rb").read()
        if f.endswith(".bat"):
            data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        z.writestr(info, data)
print(f"wrote {out} ({os.path.getsize(out):,} bytes)")
