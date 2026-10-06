# Phase 1: Data and backtester (5 agents)

**Agents:** A01, A02, A03, A43, A46 (all exist in starter form).
**Goal:** real point-in-time data and a backtester the owner can trust.
**Spec sections to read:** 24, 56, 57, 58, 59, 73, 74, 75, Appendix B.

## Already in the kit

- A01: synthetic data, CSV import, snapshot hashes.
- A02: data-health score that blocks bad symbols.
- A03: 17 causal features with reference and causality tests.
- A43: vectorized next-open backtester with an exact buy-and-hold identity test.
- A46: the 15-step decision cycle.

## Build

1. **Data store (A01):** append-only DuckDB + Parquet. Every row keeps `ingested_at`; history is never overwritten (vintages). Add `duckdb` and `pyarrow` to a `[data]` extra with pinned versions.
2. **Adapters (A01):**
   - daily stock/ETF bars from a CSV the owner downloads (start here; free)
   - crypto daily bars through CCXT public endpoints (no API key), for example Kraken BTC/USD
   Network code lives only in `src/quantagents/data/`. Tests use small recorded files, never the network.
3. **Corporate actions (A02):** flag split-like jumps (price ratio near 2, 3 or 1/2 that peers do not share). Prefer adjusted data.
4. **Survivorship (A01):** keep delisted symbols when the source has them. Otherwise label results "survivorship-biased: upper bound only".
5. **Event-driven mode (A43):** orders, next-open fills, partial fills, fees, slippage, square-root impact, a 1%-of-ADV cap. Keep the vectorized engine for screening.
   Option: evaluate NautilusTrader instead of building this. Show the owner the trade-off first.
6. **Benchmark:** reproduce buy-and-hold total return for SPY (or XIC or VFV) within 0.1% a year from the same data.
7. **Leakage tests:** time-shift test (shifting features forward must not help) and duplicate timestamps. The future-perturbation test already exists in A39.

## Owner does

- Picks and downloads a data source. Paid data needs the owner's approval.

## Acceptance (spec section 83)

- [ ] Benchmark reproduced within 0.1% a year
- [ ] Leakage tests pass
- [ ] Data store is append-only with ingest timestamps
- [ ] `/verify` is green
