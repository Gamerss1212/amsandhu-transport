"""`quantagents data ...`: fill the append-only store, list it, export it, benchmark it (Phase 1).

    quantagents data fetch --yahoo SPY QQQ --ccxt kraken:BTC/USD --start 2000-01-01
    quantagents data import --csv my_prices.csv
    quantagents data list
    quantagents data benchmark --symbol SPY
    quantagents data export --out data/prices.csv --symbols SPY QQQ

Free sources only, no API keys. Every download is a new snapshot; nothing is overwritten.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path

from quantagents.data import sources
from quantagents.data.benchmark import annual_gaps, buy_and_hold_benchmark
from quantagents.data.store import BarStore, export_csv

DEFAULT_STORE = Path("data/store")
DEFAULT_START = date(2000, 1, 1)


def _when(text: str | None) -> datetime | None:
    if not text:
        return None
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _day(text: str | None) -> date | None:
    return date.fromisoformat(text) if text else None


def _summary(raw: sources.RawDaily) -> str:
    return (
        f"{len(raw)} days {raw.dates[0]} to {raw.dates[-1]}, "
        f"{len(raw.dividends)} dividends, {len(raw.splits)} splits"
    )


def cmd_fetch(args: argparse.Namespace) -> int:
    store = BarStore(args.store)
    start = _day(args.start) or DEFAULT_START
    end = _day(args.end) or datetime.now(UTC).date()
    failed: list[str] = []
    for symbol in args.yahoo or []:
        try:
            raw = sources.fetch_yahoo(symbol, start, end)
            store.append(raw, sources.YAHOO_INFO)
            print(f"{symbol}: stored {_summary(raw)} (yahoo)")
        except Exception as exc:  # one bad symbol must not stop the rest
            failed.append(symbol)
            print(f"{symbol}: FAILED ({exc})")
    for spec in args.ccxt or []:
        exchange, _, pair = spec.partition(":")
        if not pair:
            failed.append(spec)
            print(f"{spec}: FAILED (write it as exchange:PAIR, e.g. kraken:BTC/USD)")
            continue
        try:
            raw = sources.fetch_ccxt(exchange, pair, start, end)
            store.append(raw, sources.ccxt_info(exchange))
            print(f"{raw.symbol}: stored {_summary(raw)} ({exchange})")
        except Exception as exc:
            failed.append(spec)
            print(f"{spec}: FAILED ({exc})")
    if not (args.yahoo or args.ccxt):
        print("Nothing to fetch: add --yahoo SYMBOLS and/or --ccxt exchange:PAIR")
        return 2
    print(f"\nStore: {store.root}  ({len(store.symbols())} symbols)")
    print(f"Caveat: {sources.SURVIVORSHIP_LABEL} (free sources keep only today's survivors)")
    return 1 if failed else 0


def cmd_import(args: argparse.Namespace) -> int:
    store = BarStore(args.store)
    raws, adjusted = sources.read_long_csv(args.csv)
    info = sources.csv_info(args.csv, adjusted=adjusted)
    for raw in raws.values():
        store.append(raw, info)
        print(f"{raw.symbol}: stored {_summary(raw)} ({info.name})")
    if not adjusted:
        print("No adj_close column: dividends are missing and splits must already be adjusted.")
    print(f"Caveat: {info.label}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    store = BarStore(args.store)
    rows = store.vintages()
    if not rows:
        print(f"The store at {store.root} is empty. Run `quantagents data fetch` first.")
        return 0
    print(f"{'symbol':<12} {'ingested (UTC)':<27} {'days':>6}")
    for symbol, when, n in rows:
        print(f"{symbol:<12} {when.isoformat():<27} {n:>6}")
    print(f"\n{len(store.symbols())} symbols, {len(rows)} snapshots (append-only; newest wins)")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    store = BarStore(args.store)
    meta = export_csv(
        store,
        args.out,
        args.symbols,
        as_of_ingest=_when(args.as_of_ingest),
        start=_day(args.start),
        end=_day(args.end),
    )
    print(
        f"Wrote {args.out}: {len(meta['symbols'])} symbols, {meta['first_date']} to "
        f"{meta['last_date']} (adjusted prices)"
    )
    for label in meta["labels"]:
        print(f"Caveat: {label}")
    if meta["missing_days"]:
        gaps = ", ".join(f"{s} {n}" for s, n in meta["missing_days"].items())
        print(
            f"Missing days: {gaps}. A02 blocks a symbol with gaps in its window; "
            "export stocks and crypto to separate files (crypto trades on weekends)."
        )
    return 0


def cmd_benchmark(args: argparse.Namespace) -> int:
    store = BarStore(args.store)
    raw, info = store.raw(args.symbol, as_of_ingest=_when(args.as_of_ingest))
    report = buy_and_hold_benchmark(raw)
    years = report.n_days / 252
    print(
        f"Buy-and-hold benchmark: {report.symbol} {report.start} to {report.end} "
        f"({report.n_days} days, about {years:.1f} years, {report.dividends} dividends)"
    )
    print(f"Source: {info.name} ({info.label})\n")
    print(f"  1. source adjusted close      total {report.adjusted_total:+.2%}")
    print(
        f"  2. raw close + dividends      total {report.rebuilt_total:+.2%}   "
        f"gap {report.cagr_gap_rebuilt * 1e4:+.2f} bp/yr"
    )
    print(
        f"  3. A43 backtester (from open) total {report.backtester_total:+.2%}   "
        f"gap {report.cagr_gap_backtester * 1e4:+.2f} bp/yr "
        f"(vs adjusted {report.adjusted_from_open_total:+.2%})"
    )
    worst = max(annual_gaps(raw), key=lambda g: abs(g[1]), default=None)
    if worst is not None:
        print(f"\n  Worst single year (2 vs 1): {worst[0]} {worst[1] * 1e4:+.1f} bp")
    tol = report.tolerance * 1e4
    verdict = "PASS" if report.passed else "FAIL"
    print(
        f"\n{verdict}: every route within {tol:.0f} bp (0.1%) a year"
        if report.passed
        else f"\n{verdict}: a route is more than {tol:.0f} bp (0.1%) a year away"
    )
    return 0 if report.passed else 1


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    data = sub.add_parser("data", help="real daily data: fetch, import, list, export, benchmark")
    data.add_argument(
        "--store", default=str(DEFAULT_STORE), help="store folder (default data/store)"
    )
    dsub = data.add_subparsers(dest="data_command", required=True)

    p = dsub.add_parser("fetch", help="download free daily bars into the store (no API keys)")
    p.add_argument("--yahoo", nargs="+", metavar="SYMBOL", help="stocks/ETFs, e.g. SPY XIC.TO")
    p.add_argument("--ccxt", nargs="+", metavar="EXCHANGE:PAIR", help="crypto, e.g. kraken:BTC/USD")
    p.add_argument("--start", help=f"first day (default {DEFAULT_START})")
    p.add_argument("--end", help="last day (default today; unfinished bars are dropped)")
    p.set_defaults(func=cmd_fetch)

    p = dsub.add_parser("import", help="store a CSV you downloaded (date,symbol,OHLCV[,adj_close])")
    p.add_argument("--csv", required=True)
    p.set_defaults(func=cmd_import)

    p = dsub.add_parser("list", help="every snapshot in the store")
    p.set_defaults(func=cmd_list)

    p = dsub.add_parser("export", help="write adjusted prices to a CSV for cycle/backtest/validate")
    p.add_argument("--out", default="data/prices.csv")
    p.add_argument("--symbols", nargs="+", help="default: every stored symbol")
    p.add_argument("--start")
    p.add_argument("--end")
    p.add_argument("--as-of-ingest", help="use the data as it was known then (ISO time, UTC)")
    p.set_defaults(func=cmd_export)

    p = dsub.add_parser("benchmark", help="Phase 1 check: buy-and-hold three ways within 0.1%/yr")
    p.add_argument("--symbol", default="SPY")
    p.add_argument("--as-of-ingest", help="use the data as it was known then (ISO time, UTC)")
    p.set_defaults(func=cmd_benchmark)
