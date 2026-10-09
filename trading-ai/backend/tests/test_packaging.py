"""Every data file the app reads at run time must be bundled into the Windows build (packaging/trading_ai.spec);
a missing one only shows up as an error inside the built exe."""

import os
import re

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(BACKEND, "..", "packaging", "trading_ai.spec")


def test_every_package_data_file_is_in_the_pyinstaller_spec():
    text = open(SPEC).read()
    bundled = [os.path.join("tradingai", *re.findall(r'"([^"]+)"', m))
               for m in re.findall(r"os\.path\.join\(PKG, ([^)]*)\)", text)]
    missing = []
    for root, dirs, files in os.walk(os.path.join(BACKEND, "tradingai")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith((".json", ".csv", ".txt", ".parquet")):
                rel = os.path.relpath(os.path.join(root, f), BACKEND)
                if not any(rel == b or rel.startswith(b + os.sep) for b in bundled):
                    missing.append(rel)
    assert not missing, f"add these to datas in packaging/trading_ai.spec: {missing}"
