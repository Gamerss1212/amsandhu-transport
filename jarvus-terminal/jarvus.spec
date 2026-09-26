# PyInstaller spec for Jarvus Terminal.
#
# One file, no console suppression: the window is where the app explains itself,
# tells you the address, and shows an error instead of vanishing.
#
# The web folder is bundled read-only; everything the app writes goes beside the
# executable instead (see config.BASE_DIR), so the database survives a restart.

import os

block_cipher = None

datas = [
    ("web", "web"),
    ("engine/strategies/custom", "engine/strategies/custom"),
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
    "engine.strategies", "engine.strategies.builtin",
]

a = Analysis(
    ["desktop.py"],
    pathex=[os.path.abspath(".")],
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
