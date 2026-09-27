# PyInstaller spec for Jarvus Terminal.
#
# One file, no console suppression: the window is where the app explains itself,
# tells you the address, and shows an error instead of vanishing.
#
# The web folder is bundled read-only; everything the app writes goes beside the
# executable instead (see config.BASE_DIR), so the database survives a restart.

import os

block_cipher = None

# the bot platform and strategy library: beside this folder in the repository, or copied in for a build
MAB = os.path.abspath("market_analysis_bots") if os.path.isdir("market_analysis_bots") else os.path.abspath("../market_analysis_bots")
STRAT = os.path.abspath("strategies") if os.path.isdir("strategies") else os.path.abspath("../strategies")

datas = [
    (os.path.join(MAB, "mab", "dashboard.html"), "mab"),
    (os.path.join(MAB, "bots", "registry.json"), "market_analysis_bots/bots"),
    (os.path.join(MAB, "config", "fleet.example.json"), "market_analysis_bots/config"),
    (os.path.join(STRAT, "catalog.json"), "strategies"),
    (os.path.join(STRAT, "sources.json"), "strategies"),
    (os.path.join(STRAT, "data", "events.json"), "strategies/data"),
    ("web", "web"),
    ("engine/strategies/custom", "engine/strategies/custom"),
    # the Brain's trained weights and the measured results the Learn tab teaches from
    ("engine/brain_weights.json", "engine"),
    ("engine/research_book.json", "engine"),
]

# The engine imports several modules dynamically, so name them explicitly rather
# than relying on PyInstaller's static analysis to find them.
hiddenimports = [
    "config",
    "server",
    "engine", "engine.http", "engine.universe", "engine.marketdata", "engine.volgate",
    "engine.analysis", "engine.news", "engine.store", "engine.learn", "engine.scanner",
    "engine.indicators", "engine.swarm", "engine.backtest", "engine.research",
    "engine.portfolio", "engine.automation", "engine.broker", "engine.bots",
    "engine.brain", "engine.stocks", "engine.strategies.pro",
    "engine.strategies", "engine.strategies.builtin", "engine.fleet",
    "mab", "mab.account", "mab.backtest", "mab.broker", "mab.cli", "mab.clock", "mab.costs", "mab.dashboard",
    "mab.expr", "mab.frame", "mab.indicators", "mab.instruments", "mab.metrics", "mab.models", "mab.net",
    "mab.replay", "mab.risk", "mab.runtime", "mab.secrets_store", "mab.storage", "mab.strategy",
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
