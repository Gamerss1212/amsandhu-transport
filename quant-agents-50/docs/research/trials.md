# Trial log

Every backtest variant ever run counts as a trial (spec section 63). Add one row per run.

| Date | Family | Variant and parameters | Data (file + hash) | Sharpe | Verdict |
|------|--------|------------------------|--------------------|--------|---------|
| 2026-10-06 | tsmom | tsmom_126 (126-day lookback, long-only, equal weight), vectorized A43, 15 bp one way | us.csv (SPY+QQQ Yahoo adjusted 2000-01-03..2026-10-05) c0766dd69b6b | 0.72 | Engine check only, not validated (no A44 run). CAGR +8.71%, max DD 24.1%. Survivorship-biased: upper bound only |
| 2026-10-06 | tsmom | tsmom_126 same, event-driven A43 (10 bp fee, 5 bp slippage, sqrt impact, 1% ADV cap, whole shares, 10,000 CAD) | same c0766dd69b6b | 0.72 | Engine check only, not validated. CAGR +8.66%: within 0.05%/yr of the vectorized run |
