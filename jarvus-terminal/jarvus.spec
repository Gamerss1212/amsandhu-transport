# PyInstaller spec for Jarvus.
#
# One file, console kept: the window is where the app explains itself, tells you the address and
# shows an error instead of vanishing. The web folder and the models are bundled read-only;
# everything the app writes goes beside the executable (see config.BASE_DIR).

import os

block_cipher = None

# the bot platform and the strategy library: beside this folder in the repository, or copied in for a build
MAB = os.path.abspath("market_analysis_bots") if os.path.isdir("market_analysis_bots") else os.path.abspath("../market_analysis_bots")
STRAT = os.path.abspath("strategies") if os.path.isdir("strategies") else os.path.abspath("../strategies")

datas = [
    ("web", "web"),
    (os.path.join(MAB, "mab", "dashboard.html"), "mab"),
    (os.path.join(MAB, "mab", "models", "volgate.json"), "mab/models"),                    # the volatility gate
    (os.path.join(MAB, "bots", "registry.json"), "market_analysis_bots/bots"),
    (os.path.join(MAB, "config", "fleet.example.json"), "market_analysis_bots/config"),
    (os.path.join(MAB, "results", "system_backtest_summary.json"), "market_analysis_bots/results"),
    (os.path.join(STRAT, "catalog.json"), "strategies"),
    (os.path.join(STRAT, "sources.json"), "strategies"),
    (os.path.join(STRAT, "data", "events.json"), "strategies/data"),
    (os.path.join(STRAT, "results", "evaluation_summary.json.gz"), "strategies/results"),   # the brain's starting knowledge
]

# named explicitly: the fleet runs in a spawned process and imports some modules by name
hiddenimports = [
    "config", "server", "engine", "engine.fleet",
    "mab", "mab.account", "mab.backtest", "mab.brain", "mab.broker", "mab.broker_setup", "mab.cli", "mab.clock",
    "mab.costs", "mab.dashboard", "mab.expr", "mab.frame", "mab.indicators", "mab.instruments", "mab.live",
    "mab.metrics", "mab.models", "mab.net", "mab.replay", "mab.risk", "mab.runtime", "mab.secrets_store",
    "mab.storage", "mab.strategy", "mab.sysbacktest", "mab.volgate",
    "mab.brokers", "mab.brokers.base", "mab.brokers.kraken", "mab.brokers.ndax", "mab.brokers.alpaca",
    "mab.data", "mab.data.adapters", "mab.data.hub", "mab.data.quality",
]

a = Analysis(
    ["desktop.py"],
    pathex=[os.path.abspath("."), MAB],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "test", "unittest", "pydoc_data", "lib2to3"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name="JarvusTerminal",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                 # UPX compression is a common antivirus false-positive trigger
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
