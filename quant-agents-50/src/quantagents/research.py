"""Research grid runner (A43 + A44 + A39): many backtests, judged as one honest experiment.

    python -m quantagents research --universe multi_asset=data/multi_asset.csv \\
        --universe sectors=data/sectors.csv --noise 20 --jobs 4

For every universe it runs:
1. every grid variant on the real data at the config's costs, and again at 2x costs;
2. every grid variant on ``noise`` block-bootstrap panels of the same data (real days reshuffled
   in month-long blocks, so no trend longer than a month exists): how good does the best of
   the grid look when there is nothing real to find?

Then it judges the grid as a whole, so trying many variants cannot manufacture a winner:
- PBO (CSCV) across all variants: does picking the in-sample best tend to pick a loser?
- Hansen SPA against cash and against buy-and-hold of the same universe;
- Benjamini-Hochberg FDR (q from the config) on every variant's excess return over
  buy-and-hold (Newey-West t, one-sided);
- walk-forward: pick the best variant on 3 years, score it on the next year, roll; compare with
  buy-and-hold on the same years;
- noise control: the real best-minus-benchmark Sharpe against the same statistic on every noise
  panel (empirical p-value);
- the Deflated Sharpe Ratio of the best variant, charged with every real-data variant run.

The best variant of each universe (highest full-sample Sharpe, excluding the benchmark) is the
finalist. It gets the full A44 report, the A39 red team and an event-driven re-test. It passes
only if every pre-registered check passes (docs/research/grid-preregistration.md).
"""

from __future__ import annotations

import csv
import math
import multiprocessing
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from statistics import NormalDist

import numpy as np

from quantagents.backtest.engine import Backtester
from quantagents.backtest.event import EventBacktester, EventCosts
from quantagents.backtest.grid import BENCHMARK, Variant, research_grid
from quantagents.config import AppConfig
from quantagents.data.store import data_labels
from quantagents.data.synthetic import block_bootstrap_market
from quantagents.market import FloatArray, MarketData, load_csv, periods_per_year
from quantagents.validation import stats as S
from quantagents.validation.leakage import RedTeamAuditor, RedTeamReport
from quantagents.validation.trials import Trial, append_trials, data_id

WARMUP = 260
NOISE_ALPHA = 0.05
EVENT_SHARPE_GAP = 0.10
_NORMAL = NormalDist()


@dataclass(frozen=True)
class Task:
    universe: str
    path: str
    variant: str
    cost: float
    seed: int  # 0 = the real data; k > 0 = noise panel k


# ---------------------------------------------------------------- worker side (one per process)

_GRID: dict[str, Variant] = {}
_MARKETS: dict[tuple[str, int], MarketData] = {}


def _market(path: str, seed: int) -> MarketData:
    key = (path, seed)
    if key not in _MARKETS:
        real = _MARKETS.get((path, 0)) or load_csv(path)
        _MARKETS.clear()  # keep memory flat: tasks arrive grouped by (universe, panel)
        _MARKETS[(path, 0)] = real
        _MARKETS[key] = real if seed == 0 else block_bootstrap_market(real, seed=seed)
    return _MARKETS[key]


def _run(task: Task) -> tuple[Task, FloatArray, dict[str, float]]:
    if not _GRID:
        _GRID.update({v.name: v for v in research_grid()})
    market = _market(task.path, task.seed)
    variant = _GRID[task.variant]
    result = Backtester(task.cost).run(
        market, variant.factory(market), warmup=WARMUP, name=variant.name
    )
    return task, result.returns, result.metrics


# ---------------------------------------------------------------- results


@dataclass
class VariantResult:
    family: str
    name: str
    sharpe: float
    sharpe_2x: float
    cagr: float
    ann_vol: float
    max_drawdown: float
    turnover: float
    excess_t: float
    excess_p: float
    discovery: bool = False


@dataclass
class FinalistReport:
    name: str
    validation: S.ValidationReport
    red_team: RedTeamReport
    vector_sharpe: float
    event_sharpe: float
    event_cagr: float
    checks: list[tuple[str, bool, str]]

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)


@dataclass
class UniverseReport:
    name: str
    path: str
    data: str
    start: date
    end: date
    days: int
    periods: int
    variants: list[VariantResult]
    pbo: float
    spa_cash: S.SpaResult
    spa_bh: S.SpaResult
    folds: list[S.WalkForwardFold]
    bh_fold_sharpes: list[float]
    noise_best: list[float]
    noise_excess: list[float]
    noise_p: float
    noise_excess_p: float
    best: str
    dsr_universe: float
    dsr_all: float
    labels: list[str] = field(default_factory=list)
    finalist: FinalistReport | None = None

    def get(self, name: str) -> VariantResult:
        return next(v for v in self.variants if v.name == name)

    @property
    def benchmark(self) -> VariantResult:
        return self.get(BENCHMARK)


@dataclass
class ResearchReport:
    run_date: date
    cost_rate: float
    noise_panels: int
    backtests: int
    real_trials: int
    universes: list[UniverseReport] = field(default_factory=list)


# ---------------------------------------------------------------- the run


def _execute(
    tasks: list[Task], jobs: int, progress: Callable[[str], None]
) -> dict[Task, tuple[FloatArray, dict[str, float]]]:
    out: dict[Task, tuple[FloatArray, dict[str, float]]] = {}
    step = max(1, len(tasks) // 20)
    results: Iterable[tuple[Task, FloatArray, dict[str, float]]]
    if jobs <= 1:
        results = (_run(t) for t in tasks)
        for i, (task, rets, metrics) in enumerate(results, 1):
            out[task] = (rets, metrics)
            if i % step == 0 or i == len(tasks):
                progress(f"  {i}/{len(tasks)} backtests done")
        return out
    with multiprocessing.Pool(jobs) as pool:
        chunk = max(1, min(32, len(tasks) // (jobs * 8) or 1))
        for i, (task, rets, metrics) in enumerate(pool.imap_unordered(_run, tasks, chunk), 1):
            out[task] = (rets, metrics)
            if i % step == 0 or i == len(tasks):
                progress(f"  {i}/{len(tasks)} backtests done")
    return out


def run_research(
    universes: Mapping[str, str],
    *,
    cfg: AppConfig,
    noise: int = 20,
    jobs: int = 1,
    families: Iterable[str] | None = None,
    run_date: date,
    trials_path: Path,
    progress: Callable[[str], None] = print,
) -> ResearchReport:
    grid = research_grid()
    wanted = set(families) if families else None
    if wanted is not None:
        grid = [v for v in grid if v.family in wanted or v.name == BENCHMARK]
    names = [v.name for v in grid]
    by_name = {v.name: v for v in grid}
    cost = cfg.costs.one_way_cost
    tasks: list[Task] = []
    for u, path in universes.items():
        tasks += [Task(u, path, n, cost, 0) for n in names]
        tasks += [Task(u, path, n, 2 * cost, 0) for n in names]
        for seed in range(1, noise + 1):
            tasks += [Task(u, path, n, cost, seed) for n in names]
    progress(
        f"Running {len(tasks)} backtests: {len(names)} variants x {len(universes)} universe(s) "
        f"x (1x costs, 2x costs, {noise} noise panels) on {jobs} process(es)"
    )
    done = _execute(tasks, jobs, progress)
    real_trials = len(names) * len(universes)
    report = ResearchReport(run_date, cost, noise, len(tasks), real_trials)
    for u, path in universes.items():
        progress(f"Judging {u} ...")
        report.universes.append(
            _judge(u, path, names, by_name, done, cfg=cfg, noise=noise, real_trials=real_trials)
        )
    report.backtests += 3 * len(report.universes)  # each finalist: event run + 2 time-shift runs
    _log_trials(report, by_name, trials_path)
    return report


def _judge(
    universe: str,
    path: str,
    names: list[str],
    by_name: Mapping[str, Variant],
    done: Mapping[Task, tuple[FloatArray, dict[str, float]]],
    *,
    cfg: AppConfig,
    noise: int,
    real_trials: int,
) -> UniverseReport:
    cost = cfg.costs.one_way_cost
    market = load_csv(path)
    ppy = periods_per_year(market.dates[WARMUP:])
    v = cfg.validation

    def col(name: str, c: float, seed: int) -> FloatArray:
        return done[Task(universe, path, name, c, seed)][0]

    real = np.column_stack([col(n, cost, 0) for n in names])
    stressed = np.column_stack([col(n, 2 * cost, 0) for n in names])
    bh_i = names.index(BENCHMARK)
    bh = real[:, bh_i]
    others = [i for i in range(len(names)) if i != bh_i]

    results: list[VariantResult] = []
    for i, n in enumerate(names):
        metrics = done[Task(universe, path, n, cost, 0)][1]
        t = S.newey_west_tstat(real[:, i] - bh) if i != bh_i else 0.0
        results.append(
            VariantResult(
                family=by_name[n].family,
                name=n,
                sharpe=S.sharpe_ratio(real[:, i], ppy),
                sharpe_2x=S.sharpe_ratio(stressed[:, i], ppy),
                cagr=metrics["cagr"],
                ann_vol=metrics["ann_vol"],
                max_drawdown=metrics["max_drawdown"],
                turnover=metrics["avg_daily_turnover"],
                excess_t=t,
                excess_p=1.0 - _NORMAL.cdf(t) if i != bh_i else 1.0,
            )
        )
    flags = S.benjamini_hochberg([results[i].excess_p for i in others], q=v.fdr_q)
    for i, flag in zip(others, flags, strict=True):
        results[i].discovery = flag

    pbo = S.pbo_cscv(real) if len(names) >= 2 and len(real) >= 32 else math.nan
    spa_cash = S.spa_test(real, samples=v.bootstrap_samples, mean_block=v.bootstrap_mean_block)
    excess = real[:, others] - bh[:, None] if others else real
    spa_bh = S.spa_test(excess, samples=v.bootstrap_samples, mean_block=v.bootstrap_mean_block)
    folds = S.walk_forward_selection(real, names, train=3 * ppy, test=ppy)
    bh_folds = [S.sharpe_ratio(bh[f.test_start : f.test_end], ppy) for f in folds]

    best_i = max(others, key=lambda i: results[i].sharpe) if others else bh_i
    best = names[best_i]
    real_excess = results[best_i].sharpe - results[bh_i].sharpe
    noise_best: list[float] = []
    noise_excess: list[float] = []
    for seed in range(1, noise + 1):
        sharpes = [S.sharpe_ratio(col(n, cost, seed), ppy) for n in names]
        top = max(sharpes[i] for i in others) if others else sharpes[bh_i]
        noise_best.append(top)
        noise_excess.append(top - sharpes[bh_i])
    noise_p = (1 + sum(x >= results[best_i].sharpe for x in noise_best)) / (1 + noise)
    noise_excess_p = (1 + sum(x >= real_excess for x in noise_excess)) / (1 + noise)

    report = UniverseReport(
        name=universe,
        path=path,
        data=data_id(path, 0),
        start=market.dates[WARMUP],
        end=market.dates[-1],
        days=len(real),
        periods=ppy,
        variants=results,
        pbo=pbo,
        spa_cash=spa_cash,
        spa_bh=spa_bh,
        folds=folds,
        bh_fold_sharpes=bh_folds,
        noise_best=noise_best,
        noise_excess=noise_excess,
        noise_p=noise_p,
        noise_excess_p=noise_excess_p,
        best=best,
        dsr_universe=S.deflated_sharpe_ratio(real[:, best_i], len(names)),
        dsr_all=S.deflated_sharpe_ratio(real[:, best_i], real_trials),
        labels=data_labels(path),
    )
    if best != BENCHMARK:
        report.finalist = _finalist(
            report, by_name[best], market, real, stressed, names, bh, cfg, real_trials
        )
    return report


def _finalist(
    report: UniverseReport,
    variant: Variant,
    market: MarketData,
    real: FloatArray,
    stressed: FloatArray,
    names: list[str],
    bh: FloatArray,
    cfg: AppConfig,
    real_trials: int,
) -> FinalistReport:
    i = names.index(variant.name)
    validation = S.StatisticalValidator(cfg.validation).validate(
        real[:, i],
        strategy=variant.name,
        n_trials=real_trials,
        trial_matrix=real,
        stressed_returns=stressed[:, i],
        trial_names=names,
        market_returns=bh,
        periods_per_year=report.periods,
        seed=cfg.system.seed,
        notes=[f"Grid finalist on {report.name}: best of {len(names)} variants by Sharpe."],
    )
    red_team = RedTeamAuditor(max_gross=cfg.risk.max_gross_exposure_pct / 100.0).audit(
        variant.factory, market, name=variant.name, warmup=WARMUP
    )
    event = EventBacktester(EventCosts.from_config(cfg), cfg.system.capital).run(
        market, variant.factory(market), warmup=WARMUP, name=variant.name
    )
    vector_sharpe = report.get(variant.name).sharpe
    event_sharpe = S.sharpe_ratio(event.returns, report.periods)
    failed = [c.name for c in validation.checks if not c.passed]
    v = report.get(variant.name)
    checks = [
        (
            "A44 validation",
            validation.passed,
            "all checks pass" if not failed else "failed: " + ", ".join(failed),
        ),
        (
            "beats buy-and-hold (Hansen SPA)",
            report.spa_bh.p_value <= cfg.validation.max_spa_p,
            f"p = {report.spa_bh.p_value:.3f} (need <= {cfg.validation.max_spa_p:g})",
        ),
        (
            "FDR discovery vs buy-and-hold",
            v.discovery,
            f"excess t = {v.excess_t:.2f}, p = {v.excess_p:.4f} (BH at q = {cfg.validation.fdr_q:g})",
        ),
        (
            "noise control",
            report.noise_excess_p <= NOISE_ALPHA,
            f"p = {report.noise_excess_p:.3f} over {len(report.noise_excess)} panels (need <= {NOISE_ALPHA:g})",
        ),
        ("A39 red team", red_team.passed, f"{len(red_team.findings)} finding(s)"),
        (
            "event-driven re-test agrees",
            event_sharpe > 0 and abs(event_sharpe - vector_sharpe) <= EVENT_SHARPE_GAP,
            f"Sharpe {event_sharpe:.2f} event vs {vector_sharpe:.2f} vectorized "
            f"(need > 0 and within {EVENT_SHARPE_GAP:g})",
        ),
    ]
    return FinalistReport(
        name=variant.name,
        validation=validation,
        red_team=red_team,
        vector_sharpe=vector_sharpe,
        event_sharpe=event_sharpe,
        event_cagr=event.metrics["cagr"],
        checks=checks,
    )


def _log_trials(report: ResearchReport, by_name: Mapping[str, Variant], path: Path) -> None:
    rows: list[Trial] = []
    detail = f"grid {report.run_date.isoformat()}, vectorized, {report.cost_rate:.2%} one way"
    for u in report.universes:
        for v in u.variants:
            if v.name == BENCHMARK:
                verdict = "benchmark"
            elif u.finalist is not None and v.name == u.finalist.name:
                verdict = ("PASS" if u.finalist.passed else "FAIL") + " (grid finalist)"
            else:
                verdict = "grid variant (counted)"
            rows.append(
                Trial(
                    report.run_date,
                    by_name[v.name].family,
                    f"{v.name}@{u.name}",
                    f"{detail}; 2x costs Sharpe {v.sharpe_2x:.2f}",
                    u.data,
                    v.sharpe,
                    verdict,
                )
            )
        if u.noise_best:
            q95 = float(np.quantile(u.noise_best, 0.95))
            rows.append(
                Trial(
                    report.run_date,
                    "noise_control",
                    f"grid@{u.name}",
                    f"{len(u.noise_best)} block-bootstrap panels x {len(u.variants)} variants",
                    f"synthetic (bootstrap of {u.data})",
                    float(np.median(u.noise_best)),
                    f"best-of-grid Sharpe on noise: median {np.median(u.noise_best):.2f}, "
                    f"95th percentile {q95:.2f}",
                )
            )
    append_trials(rows, path)


# ---------------------------------------------------------------- report


def _pct(x: float) -> str:
    return f"{x:+.1%}" if math.isfinite(x) else "n/a"


def format_report(report: ResearchReport) -> str:
    lines = [
        f"# Research grid: {report.run_date.isoformat()}",
        "",
        "Generated by `quantagents research`. Pre-registered in "
        "`docs/research/grid-preregistration.md`.",
        "",
        f"- Backtests run: **{report.backtests:,}**. That is "
        f"{report.real_trials} real-data variants at 1x costs, the same at 2x costs, "
        f"{report.noise_panels} noise panels per universe, and the finalists' event-driven and "
        "time-shift runs.",
        f"- Costs: {report.cost_rate:.2%} one way. Fills at the next open. Holdings drift with "
        "prices.",
        f"- Trials charged to the DSR: {report.real_trials} (every real-data variant on every "
        "universe).",
        "- Data caveats: "
        + "; ".join(sorted({label for u in report.universes for label in u.labels}))
        + ".",
        "",
        "## Verdict by universe",
        "",
        "| Universe | Days | Best variant | Sharpe | Buy-and-hold Sharpe | Finalist verdict |",
        "|---|---|---|---|---|---|",
    ]
    for u in report.universes:
        best = u.get(u.best)
        verdict = "n/a" if u.finalist is None else ("PASS" if u.finalist.passed else "FAIL")
        lines.append(
            f"| {u.name} | {u.days} ({u.start} to {u.end}) | {u.best} | {best.sharpe:.2f} | "
            f"{u.benchmark.sharpe:.2f} | **{verdict}** |"
        )
    for u in report.universes:
        lines += _universe_section(u)
    return "\n".join(lines) + "\n"


def _universe_section(u: UniverseReport) -> list[str]:
    bh = u.benchmark
    ranked = sorted(u.variants, key=lambda v: -v.sharpe)
    discoveries = [v.name for v in u.variants if v.discovery]
    oos = [f.out_sample_sharpe for f in u.folds]
    lines = [
        "",
        f"## {u.name}",
        "",
        f"Data `{u.data}`, {u.days} trading days from {u.start} to {u.end}, "
        f"{u.periods} periods a year, {len(u.variants)} variants.",
        "",
        "### Is anything in the grid real?",
        "",
        f"- **PBO** (chance that picking the in-sample best picks an out-of-sample loser): "
        f"{u.pbo:.2f}.",
        f"- **Hansen SPA vs cash:** p = {u.spa_cash.p_value:.3f}. **vs buy-and-hold:** "
        f"p = {u.spa_bh.p_value:.3f}. A small p means at least one variant beats it beyond luck.",
        f"- **FDR (Benjamini-Hochberg) on excess over buy-and-hold:** {len(discoveries)} "
        f"discoveries of {len(u.variants) - 1}"
        + (f": {', '.join(discoveries)}." if discoveries else "."),
        f"- **Walk-forward** (best of the grid on 3 years, scored on the next): {len(u.folds)} "
        f"folds. Mean out-of-sample Sharpe {np.mean(oos):.2f} against "
        f"{np.mean(u.bh_fold_sharpes):.2f} for buy-and-hold in the same years."
        if u.folds
        else "- **Walk-forward:** not enough data for a fold.",
        f"- **Noise control** ({len(u.noise_best)} panels with no trend longer than a month): "
        f"best-of-grid Sharpe on noise median {np.median(u.noise_best):.2f}, 95th percentile "
        f"{np.quantile(u.noise_best, 0.95):.2f}; real best {u.get(u.best).sharpe:.2f} "
        f"(p = {u.noise_p:.3f}). Best minus buy-and-hold: real "
        f"{u.get(u.best).sharpe - bh.sharpe:+.2f}, noise median {np.median(u.noise_excess):+.2f} "
        f"(p = {u.noise_excess_p:.3f})."
        if u.noise_best
        else "- **Noise control:** not run.",
        f"- **Deflated Sharpe of the best:** {u.dsr_universe:.3f} charged with this universe's "
        f"variants; {u.dsr_all:.3f} charged with every real-data variant (need 0.95).",
        "",
        "### Top 10 variants by Sharpe (and the benchmark)",
        "",
        "| Variant | Family | Sharpe | at 2x costs | CAGR | Volatility | Max drawdown | Excess t vs B&H | FDR |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    rows = ranked[:10] + ([bh] if bh not in ranked[:10] else [])
    for v in rows:
        lines.append(
            f"| {v.name} | {v.family} | {v.sharpe:.2f} | {v.sharpe_2x:.2f} | {_pct(v.cagr)} | "
            f"{v.ann_vol:.1%} | {v.max_drawdown:.1%} | "
            + ("benchmark" if v.name == BENCHMARK else f"{v.excess_t:.2f}")
            + f" | {'yes' if v.discovery else '-'} |"
        )
    lines += [
        "",
        "### Best variant of each family",
        "",
        "| Family | Variants | Best | Sharpe | Max drawdown | Median Sharpe of the family |",
        "|---|---|---|---|---|---|",
    ]
    families: dict[str, list[VariantResult]] = {}
    for v in u.variants:
        families.setdefault(v.family, []).append(v)
    for fam, vs in sorted(families.items(), key=lambda kv: -max(v.sharpe for v in kv[1])):
        top = max(vs, key=lambda v: v.sharpe)
        lines.append(
            f"| {fam} | {len(vs)} | {top.name} | {top.sharpe:.2f} | {top.max_drawdown:.1%} | "
            f"{float(np.median([v.sharpe for v in vs])):.2f} |"
        )
    if u.folds:
        lines += [
            "",
            "### Walk-forward folds",
            "",
            "| Test days | Chosen | In-sample Sharpe | Out-of-sample Sharpe | Buy-and-hold |",
            "|---|---|---|---|---|",
        ]
        for f, b in zip(u.folds, u.bh_fold_sharpes, strict=True):
            lines.append(
                f"| {f.test_start}-{f.test_end - 1} | {f.chosen} | {f.in_sample_sharpe:.2f} | "
                f"{f.out_sample_sharpe:.2f} | {b:.2f} |"
            )
    if u.finalist is not None:
        fin = u.finalist
        lines += [
            "",
            f"### Finalist: {fin.name} -> **{'PASS' if fin.passed else 'FAIL'}**",
            "",
            "| Check | Result | Detail |",
            "|---|---|---|",
        ]
        lines += [
            f"| {name} | {'PASS' if ok else 'FAIL'} | {detail} |" for name, ok, detail in fin.checks
        ]
        lines += ["", "A44 detail:", ""]
        lines += [
            f"- [{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}"
            for c in fin.validation.checks
        ]
        lines.append(
            f"- Event-driven re-test: CAGR {_pct(fin.event_cagr)}, Sharpe {fin.event_sharpe:.2f}."
        )
    return lines


def write_variants_csv(report: ResearchReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "universe", "family", "variant", "sharpe", "sharpe_2x_costs", "cagr", "ann_vol",
                "max_drawdown", "avg_daily_turnover", "excess_t_vs_buy_and_hold", "excess_p",
                "fdr_discovery",
            ]
        )  # fmt: skip
        for u in report.universes:
            for v in u.variants:
                writer.writerow(
                    [
                        u.name, v.family, v.name, f"{v.sharpe:.4f}", f"{v.sharpe_2x:.4f}",
                        f"{v.cagr:.6f}", f"{v.ann_vol:.6f}", f"{v.max_drawdown:.6f}",
                        f"{v.turnover:.6f}", f"{v.excess_t:.4f}", f"{v.excess_p:.6f}",
                        int(v.discovery),
                    ]
                )  # fmt: skip
