# PyInstaller spec: one folder = START_TRADING_AI.exe + _internal/ (Python, libraries, dashboard, data files).
# Build with packaging/build_windows.sh (runs PyInstaller with Windows Python under Wine, or natively on Windows).
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
BACKEND = os.path.join(ROOT, "backend")
PKG = os.path.join(BACKEND, "tradingai")

datas = [
    (os.path.join(ROOT, "frontend", "dist"), os.path.join("frontend", "dist")),
    (os.path.join(PKG, "market", "data", "contract_specs.json"), os.path.join("tradingai", "market", "data")),
    (os.path.join(PKG, "strategies", "library_cache.json"), os.path.join("tradingai", "strategies")),
    # the owner's 80-template catalog and its source register
    (os.path.join(PKG, "strategies", "data"), os.path.join("tradingai", "strategies", "data")),
]
datas += collect_data_files("tzdata")                      # Windows has no time-zone database of its own

hidden = (collect_submodules("tradingai") + collect_submodules("uvicorn") + collect_submodules("websockets")
          + ["tzdata"])

a = Analysis(
    [os.path.join(SPECPATH, "start_trading_ai.py")],
    pathex=[BACKEND],
    datas=datas,
    hiddenimports=hidden,
    excludes=["tkinter", "matplotlib", "pandas", "scipy", "IPython", "pytest", "PIL", "pyarrow"],
    # keep the .py sources of the app next to the bytecode so the strategy-library cache can verify its fingerprint
    module_collection_mode={"tradingai": "pyz+py"},
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="START_TRADING_AI",
    console=True,                                          # the small window that says the local server is running
    icon=os.path.join(SPECPATH, "trading_ai.ico") if os.path.exists(os.path.join(SPECPATH, "trading_ai.ico")) else None,
    version=os.path.join(SPECPATH, "version_info.txt"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="TradingAI", upx=False)
