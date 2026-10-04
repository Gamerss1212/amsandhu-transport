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
# the ULTRON councils (trained models + their numpy code), beside this folder in the repository
ULTRON = os.path.abspath("ultron") if os.path.isdir("ultron") else os.path.abspath("../ultron")
JSCRIPTS = os.path.abspath("jarvus/scripts") if os.path.isdir("jarvus/scripts") else os.path.abspath("../jarvus/scripts")

datas = [
    ("web", "web"),
    (os.path.join(MAB, "mab", "dashboard.html"), "mab"),
    (os.path.join(MAB, "mab", "models", "volgate.json"), "mab/models"),                    # the volatility gate
    (os.path.join(MAB, "bots", "registry.json"), "market_analysis_bots/bots"),
    (os.path.join(MAB, "config", "fleet.example.json"), "market_analysis_bots/config"),
    (os.path.join(MAB, "results", "system_backtest_summary.json"), "market_analysis_bots/results"),
    (os.path.join(MAB, "results", "system_backtest_profiles.json"), "market_analysis_bots/results"),   # the same system at each fee level
    (os.path.join(MAB, "results", "projection_inputs.json"), "market_analysis_bots/results"),          # goal calculator input
    (os.path.join(STRAT, "catalog.json"), "strategies"),
    (os.path.join(STRAT, "sources.json"), "strategies"),
    (os.path.join(STRAT, "data", "events.json"), "strategies/data"),
    (os.path.join(STRAT, "results", "evaluation_summary.json.gz"), "strategies/results"),   # the brain's starting knowledge
    (os.path.join(STRAT, "results", "swing_eval.json"), "strategies/results"),              # ... for the swing strategies
    (os.path.join(STRAT, "results", "swing_lab.json.gz"), "strategies/results"),
    (os.path.join(ULTRON, "assets", "councils"), "ultron_councils"),                        # the ULTRON councils
    (os.path.join(MAB, "results", "ultron_priors.json"), "results"),                       # ... and their measured evidence
]

# named explicitly: the bot engines and research workers run in spawned processes and import modules by name
from PyInstaller.utils.hooks import collect_submodules


def _modules(root, pkg):
    out = []
    for dirpath, _, files in os.walk(os.path.join(root, pkg)):
        if "__pycache__" in dirpath:
            continue
        rel = os.path.relpath(dirpath, root).replace(os.sep, ".")
        for f in files:
            if f.endswith(".py"):
                out.append(rel if f == "__init__.py" else f"{rel}.{f[:-3]}")
    return sorted(out)


hiddenimports = ["config", "server", "selftest", "engine", "engine.auth", "engine.supervisor", "engine.library"] \
    + _modules(MAB, "mab") + ["council", "pine_gate", "signals", "events", "numpy"]
try:                                   # the AI research assistant (optional: the app runs without it)
    hiddenimports += collect_submodules("anthropic")
except Exception:                      # noqa: BLE001
    pass

a = Analysis(
    ["desktop.py"],
    pathex=[os.path.abspath("."), MAB, os.path.join(ULTRON, "core"), os.path.join(ULTRON, "tv"), JSCRIPTS],
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
