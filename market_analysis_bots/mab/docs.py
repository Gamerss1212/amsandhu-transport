"""Write docs/INDICATORS.md from the indicator and function registries (python -m mab.docs)."""
import os

from mab import expr, indicators as I

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    L = ["# Indicators and rule functions\n",
         "Generated from the code registry (`python -m mab.docs`), so it always matches the engine.\n",
         "All indicators update once per **completed** bar and use only that bar and earlier ones. Tests check this for every "
         "indicator (values computed on a truncated history must equal the full-history values). Order-flow indicators use only "
         "recorded venue data and are never estimated silently; `est_delta` is an explicitly labelled estimate.\n",
         "Warm-up: *first* = bars before the first value; *stable* = bars after which the value no longer depends on where the "
         "history started (recursive smoothers). Session-based indicators need whole sessions (column *sessions*).\n",
         "| Indicator | Category | Parameters (defaults) | Outputs | Inputs | Formula | Warm-up first / stable | Sessions | Missing data |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in I.catalog():
        p = ", ".join(f"{k}={v}" for k, v in r["params"].items()) or "-"
        L.append(f"| `{r['name']}` | {r['category']} | {p} | {', '.join(r['outputs'])} | {r['inputs']} | {r['formula']} | "
                 f"{r['warmup_first']} / {r['warmup_stable']} | {'-' if r['sessions_needed'] is None else r['sessions_needed']} | "
                 f"{r['missing']}{' ' + r['notes'] if r['notes'] else ''} |")
    L.append("\n## Rule functions\n\n| Function | Meaning |\n|---|---|")
    for k, f in sorted(expr.FUNCS.items()):
        L.append(f"| `{k}` | {getattr(f, 'doc', '')} |")
    L.append("\n## Rule language\n\n" + expr.__doc__.strip())
    os.makedirs(os.path.join(HERE, "docs"), exist_ok=True)
    with open(os.path.join(HERE, "docs", "INDICATORS.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"{len(I.REGISTRY)} indicators, {len(expr.FUNCS)} functions")


if __name__ == "__main__":
    main()
