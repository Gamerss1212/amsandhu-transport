"""The pre-registered research grid (2026-10-06): 87 variants of 11 published strategy families.

Written and committed before any run of the grid (see docs/research/grid-preregistration.md).
Every variant counts as a trial on every universe it is run on (spec section 63). Parameter
ranges are the ones the original papers and common practice use; none were picked after
looking at results.

| Family | Source (spec Appendix A) | Variants |
|---|---|---|
| tsmom | Moskowitz-Ooi-Pedersen time-series momentum | 6 lookbacks |
| tsmom_blend | Hurst-Ooi-Pedersen multi-horizon blend | 4 lookback sets x 3 volatility settings |
| sma | price above its moving average | 5 windows |
| sma_cross | golden cross | 4 fast/slow pairs |
| faber | Faber month-end moving-average timing | 4 lengths |
| xs_mom | Jegadeesh-Titman cross-sectional momentum | 2 lookbacks x 2 skips x 3 sizes x crash filter on/off |
| dual_mom | Antonacci dual momentum | 2 lookbacks x top 1/2/3 |
| rsi2 | Connors RSI(2) reversion | 3 entries x 2 exits x 2 trend filters |
| vol_target | volatility targeting (on buy-and-hold, and on the trend blend) | 4 targets x 2 windows + 2 |
| donchian | Turtle channel breakout | 3 entry/exit pairs |
| buy_and_hold | the benchmark | 1 |
"""

from __future__ import annotations

from dataclasses import dataclass

from quantagents.backtest import library
from quantagents.backtest.engine import StrategyFactory
from quantagents.backtest.strategies import buy_and_hold, sma_filter, tsmom

BENCHMARK = "buy_and_hold"
BLEND_SETS: dict[str, tuple[int, ...]] = {
    "1-3-12": (21, 63, 252),
    "3-6-12": (63, 126, 252),
    "1-3-6": (21, 63, 126),
    "2-6-12": (42, 126, 252),
}


@dataclass(frozen=True)
class Variant:
    family: str
    name: str
    factory: StrategyFactory


def research_grid() -> list[Variant]:
    out: list[Variant] = []

    def add(family: str, name: str, factory: StrategyFactory) -> None:
        out.append(Variant(family, name, factory))

    for lookback in (21, 42, 63, 126, 189, 252):
        add("tsmom", f"tsmom_{lookback}", tsmom(lookback))
    for label, lookbacks in BLEND_SETS.items():
        for target, tag in ((None, "raw"), (0.10, "vt10"), (0.15, "vt15")):
            add("tsmom_blend", f"tsmom_blend_{label}_{tag}", library.tsmom_blend(lookbacks, target))
    for window in (50, 100, 150, 200, 250):
        add("sma", f"sma_{window}", sma_filter(window))
    for fast, slow in ((20, 100), (50, 150), (50, 200), (100, 200)):
        add("sma_cross", f"sma_cross_{fast}_{slow}", library.sma_cross(fast, slow))
    for months in (6, 8, 10, 12):
        add("faber", f"faber_{months}m", library.faber(months))
    for lookback in (126, 252):
        for skip in (0, 21):
            for frac, tag in ((0.25, "quarter"), (1 / 3, "third"), (0.5, "half")):
                for trend in (False, True):
                    name = f"xsmom_{lookback}_{skip}_{tag}" + ("_trend" if trend else "")
                    add("xs_mom", name, library.xs_momentum(lookback, skip, frac, trend))
    for lookback in (126, 252):
        for k in (1, 2, 3):
            add("dual_mom", f"dual_mom_{lookback}_top{k}", library.dual_momentum(lookback, k))
    for entry in (5.0, 10.0, 15.0):
        for exit_sma in (5, 10):
            for trend_sma in (100, 200):
                name = f"rsi2_{entry:g}_{exit_sma}_{trend_sma}"
                add("rsi2", name, library.rsi2(entry, exit_sma, trend_sma))
    for target in (0.08, 0.10, 0.12, 0.15):
        for window in (21, 63):
            name = f"vt{round(target * 100)}_{window}_hold"
            add("vol_target", name, library.vol_target(buy_and_hold(), target, window))
    for target in (0.10, 0.15):
        base = library.tsmom_blend(target_vol=None)
        add("vol_target", f"vt{round(target * 100)}_tsmom_blend", library.vol_target(base, target))
    for entry, exit_ in ((20, 10), (55, 20), (100, 50)):
        add("donchian", f"donchian_{entry}_{exit_}", library.donchian(entry, exit_))
    add("buy_and_hold", BENCHMARK, buy_and_hold())
    return out
