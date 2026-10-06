# Trial log

Every backtest variant ever run counts as a trial (spec section 63). Add one row per run.

| Date | Family | Variant and parameters | Data (file + hash) | Sharpe | Verdict |
|------|--------|------------------------|--------------------|--------|---------|
| 2026-10-06 | tsmom | tsmom_126 (126-day lookback, long-only, equal weight), vectorized A43, 15 bp one way | us.csv (SPY+QQQ Yahoo adjusted 2000-01-03..2026-10-05) c0766dd69b6b | 0.72 | Engine check only, not validated (no A44 run). CAGR +8.71%, max DD 24.1%. Survivorship-biased: upper bound only |
| 2026-10-06 | tsmom | tsmom_126 same, event-driven A43 (10 bp fee, 5 bp slippage, sqrt impact, 1% ADV cap, whole shares, 10,000 CAD) | same c0766dd69b6b | 0.72 | Engine check only, not validated. CAGR +8.66%: within 0.05%/yr of the vectorized run |
| 2026-10-06 | tsmom_blend | tsmom_blend_vt10 (validate, vectorized, 0.15% one way) | multi_asset.csv 19e95947f2a0 | 0.64 | FAIL (A44 + A39, reported variant) |
| 2026-10-06 | tsmom_blend | tsmom_blend_raw (validate, vectorized, 0.15% one way) | multi_asset.csv 19e95947f2a0 | 0.64 | variant (counted) |
| 2026-10-06 | faber | faber_10m (validate, vectorized, 0.15% one way) | multi_asset.csv 19e95947f2a0 | 0.64 | FAIL (A44 + A39, reported variant) |
| 2026-10-06 | faber | faber_8m (validate, vectorized, 0.15% one way) | multi_asset.csv 19e95947f2a0 | 0.67 | variant (counted) |
| 2026-10-06 | faber | faber_12m (validate, vectorized, 0.15% one way) | multi_asset.csv 19e95947f2a0 | 0.66 | variant (counted) |
| 2026-10-06 | vol_target | vt10_hold (validate, vectorized, 0.15% one way) | multi_asset.csv 19e95947f2a0 | 0.57 | FAIL (A44 + A39, reported variant) |
| 2026-10-06 | vol_target | vt15_hold (validate, vectorized, 0.15% one way) | multi_asset.csv 19e95947f2a0 | 0.60 | variant (counted) |
| 2026-10-06 | xs_mom | xsmom_12_1 (validate, vectorized, 0.15% one way) | sectors.csv 96aa159115e7 | 0.60 | FAIL (A44 + A39, reported variant) |
| 2026-10-06 | xs_mom | xsmom_12_1_trend (validate, vectorized, 0.15% one way) | sectors.csv 96aa159115e7 | 0.62 | variant (counted) |
| 2026-10-06 | rsi2 | rsi2_10 (validate, vectorized, 0.15% one way) | us_index.csv 3f82863350f9 | 0.20 | FAIL (A44 + A39, reported variant) |
| 2026-10-06 | rsi2 | rsi2_5 (validate, vectorized, 0.15% one way) | us_index.csv 3f82863350f9 | 0.19 | variant (counted) |
| 2026-10-06 | buy_and_hold | buy_and_hold (equal weight, benchmark for context (pre-registered), vectorized, 0.15% one way) | multi_asset.csv 19e95947f2a0 | 0.58 | benchmark: CAGR +6.69%, vol 12.6%, max DD 37.2% (2007-02-20..2026-10-05) |
| 2026-10-06 | buy_and_hold | buy_and_hold (equal weight, benchmark for context (pre-registered), vectorized, 0.15% one way) | sectors.csv 96aa159115e7 | 0.58 | benchmark: CAGR +9.33%, vol 18.2%, max DD 52.2% (2000-01-04..2026-10-05) |
| 2026-10-06 | buy_and_hold | buy_and_hold (equal weight, benchmark for context (pre-registered), vectorized, 0.15% one way) | us_index.csv 3f82863350f9 | 0.58 | benchmark: CAGR +9.99%, vol 20.0%, max DD 54.0% (2001-06-08..2026-10-05) |
