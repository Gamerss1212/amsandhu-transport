# The whole system at each exchange's fees

Same bots, same windows, same brain; only the crypto fees change (stocks are commission-free in every row). Each row is a full-system backtest (`tools/system_backtest.py --fee-profile NAME`); mean return per window and share of windows that made money.

| Crypto fees | Runs | No brain | Gates only | Full brain | Brain windows positive | Brain trades per window | Brain avg R |
|---|---|---|---|---|---|---|---|
| each bot's own exchange (Coinbase 1.20%, Kraken 0.80%, OKX 0.10% taker) | 1,000 | -12.124% | -0.107% | **-0.018%** | 13% | 5 | -0.007 |
| Kraken Pro, entry tier (0.40% / 0.80%) | 1,000 | -11.421% | -0.098% | **-0.010%** | 16% | 6 | -0.024 |
| NDAX (0.20% flat) | 1,000 | -5.487% | -0.140% | **+0.002%** | 19% | 10 | -0.252 |
| a low-fee exchange (0.08% / 0.10%) | 1,000 | -3.387% | -0.227% | **+0.007%** | 22% | 14 | -0.265 |

Windows are drawn after the training segment of each dataset; the brain starts from the training segment only. A fee level with more trades and a higher brain return is one where the bots' edges survive costs more often; it is not a forecast.
