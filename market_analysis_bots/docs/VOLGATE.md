# Volatility gate: measured results

Generated 2026-09-29 06:11 UTC by `tools/train_volgate.py`. Chronological split: fit 60%, thresholds chosen on the next 20%, measured once on the last 20% (test). Thresholds are the lowest that reached 65% precision on validation.

## crypto (next 12 hours; 299,719 hourly rows, 2021-05-08 to 2026-09-28; model: gradient-boosted trees)

| Forecast | Test AUC | Baseline AUC (ATR ratio only) | Threshold | Share of hours flagged (test) | Right when flagged (test) | Base rate |
|---|---|---|---|---|---|---|
| LOUD | 0.686 | 0.620 | 0.58 | 5.8% (3,502) | 76.2% | 30.6% |
| QUIET | 0.700 | 0.606 | 0.51 | 20.7% (12,408) | 59.8% | 36.3% |

## stock (next 7 hours; 26,086 hourly rows, 2024-04-01 to 2026-09-28; model: logistic regression)

| Forecast | Test AUC | Baseline AUC (ATR ratio only) | Threshold | Share of hours flagged (test) | Right when flagged (test) | Base rate |
|---|---|---|---|---|---|---|
| LOUD | 0.637 | 0.637 | 0.65 | 1.7% (88) | 68.2% | 29.0% |
| QUIET | 0.647 | 0.639 | 0.50 | 5.4% (284) | 59.2% | 32.9% |

A LOUD or QUIET reading is about how much the market will move, never which way. Coin flip AUC = 0.500.
