# Swing lab: what survives real costs

Generated 2026-09-29 21:54 UTC by `src/swing_lab.py`. Hourly data: 9 cryptos (Coinbase, up to 5.5 years) and 6 US stocks/ETFs (Yahoo, 3 years). Each setup was tried with 48 exit structures and entry types; the protocol and its preregistration are in the script's docstring. Test period = the volatility gate's untouched test period (crypto from 2025-12-23, stocks from 2026-03-30); validation from 2025-03-20 / 2025-09-26.

R = profit or loss in units of the risk taken (entry to stop). Net = after fees and slippage.

## Coinbase retail fees (0.60% maker / 1.20% taker)

### majors

| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | Test cost R | Test with vol gate | Holm | Survivor |
|---|---|---|---|---|---|---|---|---|---|
| breakout | 4.0xATR, 3.0R, 96h, maker | -0.371 (759) | -0.539 (174) | **-0.619** (159) | +0.097 | +0.716 | -0.640 (149) | no | no |
| rsi2_dip | 4.0xATR, 3.0R, 96h, maker | -0.327 (629) | -0.457 (133) | **-0.460** (126) | +0.149 | +0.609 | -0.466 (107) | no | no |
| pullback | 4.0xATR, 3.0R, 96h, maker | -0.396 (547) | -0.672 (113) | **-0.576** (108) | +0.096 | +0.672 | -0.418 (87) | no | no |
| retest | 4.0xATR, 3.0R, 96h, maker | -0.318 (550) | -0.451 (124) | **-0.724** (111) | -0.077 | +0.647 | -0.758 (105) | no | no |
| squeeze | 4.0xATR, 3.0R, 96h, maker | -0.683 (374) | -0.533 (86) | **-0.830** (97) | +0.098 | +0.928 | -0.866 (70) | no | no |
| momentum | 4.0xATR, 3.0R, 96h, maker | -0.272 (546) | -0.286 (110) | **-0.735** (122) | -0.030 | +0.705 | -0.644 (81) | no | no |
| orb | 4.0xATR, 3.0R, 96h, maker | -0.418 (1036) | -0.489 (218) | **-0.608** (196) | +0.018 | +0.626 | -0.630 (155) | no | no |
| every_bar | 4.0xATR, 3.0R, 96h, maker | -0.398 (1645) | -0.414 (314) | **-0.555** (334) | +0.056 | +0.611 | -0.576 (304) | no | no |

### memes

| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | Test cost R | Test with vol gate | Holm | Survivor |
|---|---|---|---|---|---|---|---|---|---|
| breakout | 4.0xATR, 2.0R, 96h, maker | -0.265 (606) | -0.206 (320) | **-0.313** (318) | +0.087 | +0.400 | -0.367 (312) | no | no |
| rsi2_dip | 4.0xATR, 3.0R, 96h, maker | -0.224 (423) | -0.358 (206) | **-0.448** (194) | -0.065 | +0.382 | -0.473 (168) | no | no |
| pullback | 4.0xATR, 3.0R, 96h, maker | -0.158 (384) | -0.413 (185) | **-0.613** (169) | -0.213 | +0.401 | -0.573 (144) | no | no |
| retest | 4.0xATR, 3.0R, 96h, maker | -0.171 (383) | -0.191 (208) | **-0.280** (172) | +0.113 | +0.394 | -0.336 (160) | no | no |
| squeeze | 4.0xATR, 3.0R, 96h, maker | -0.545 (274) | -0.248 (171) | **-0.626** (159) | -0.047 | +0.578 | -0.579 (127) | no | no |
| momentum | 4.0xATR, 2.0R, 96h, maker | -0.137 (352) | -0.336 (178) | **-0.402** (193) | -0.043 | +0.359 | -0.390 (142) | no | no |
| orb | 4.0xATR, 3.0R, 96h, maker | -0.386 (863) | -0.337 (465) | **-0.408** (395) | +0.006 | +0.414 | -0.399 (330) | no | no |
| every_bar | 4.0xATR, 3.0R, 96h, maker | -0.354 (1366) | -0.328 (664) | **-0.396** (675) | +0.004 | +0.400 | -0.417 (603) | no | no |

## Kraken retail fees (0.40% / 0.80%)

### majors

| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | Test cost R | Test with vol gate | Holm | Survivor |
|---|---|---|---|---|---|---|---|---|---|
| breakout | 4.0xATR, 2.0R, 96h, maker | -0.175 (819) | -0.358 (187) | **-0.319** (174) | +0.136 | +0.455 | -0.309 (162) | no | no |
| rsi2_dip | 4.0xATR, 3.0R, 96h, maker | -0.171 (629) | -0.264 (133) | **-0.259** (126) | +0.149 | +0.408 | -0.276 (107) | no | no |
| pullback | 4.0xATR, 3.0R, 96h, maker | -0.235 (547) | -0.481 (113) | **-0.354** (108) | +0.096 | +0.450 | -0.217 (87) | no | no |
| retest | 4.0xATR, 3.0R, 96h, maker | -0.166 (550) | -0.260 (124) | **-0.511** (111) | -0.077 | +0.433 | -0.545 (105) | no | no |
| squeeze | 4.0xATR, 3.0R, 96h, maker | -0.455 (374) | -0.275 (86) | **-0.523** (97) | +0.098 | +0.622 | -0.563 (70) | no | no |
| momentum | 4.0xATR, 3.0R, 96h, maker | -0.122 (546) | -0.105 (110) | **-0.502** (122) | -0.030 | +0.472 | -0.440 (81) | no | no |
| orb | 4.0xATR, 3.0R, 96h, maker | -0.268 (1036) | -0.320 (218) | **-0.402** (196) | +0.018 | +0.419 | -0.431 (155) | no | no |
| every_bar | 4.0xATR, 3.0R, 96h, maker | -0.249 (1645) | -0.246 (314) | **-0.353** (334) | +0.056 | +0.409 | -0.378 (304) | no | no |

### memes

| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | Test cost R | Test with vol gate | Holm | Survivor |
|---|---|---|---|---|---|---|---|---|---|
| breakout | 4.0xATR, 2.0R, 96h, maker | -0.160 (606) | -0.109 (320) | **-0.185** (318) | +0.087 | +0.272 | -0.236 (312) | no | no |
| rsi2_dip | 4.0xATR, 3.0R, 96h, maker | -0.126 (423) | -0.262 (206) | **-0.326** (194) | -0.065 | +0.261 | -0.356 (168) | no | no |
| pullback | 4.0xATR, 3.0R, 96h, maker | -0.057 (384) | -0.315 (185) | **-0.486** (169) | -0.213 | +0.274 | -0.450 (144) | no | no |
| retest | 4.0xATR, 3.0R, 96h, maker | -0.069 (383) | -0.092 (208) | **-0.155** (172) | +0.113 | +0.268 | -0.209 (160) | no | no |
| squeeze | 4.0xATR, 3.0R, 96h, maker | -0.388 (274) | -0.119 (171) | **-0.442** (159) | -0.047 | +0.394 | -0.397 (127) | no | no |
| momentum | 4.0xATR, 2.0R, 96h, maker | -0.051 (352) | -0.252 (178) | **-0.288** (193) | -0.043 | +0.245 | -0.282 (142) | no | no |
| orb | 4.0xATR, 2.0R, 96h, maker | -0.252 (906) | -0.271 (497) | **-0.219** (423) | +0.047 | +0.266 | -0.222 (355) | no | no |
| every_bar | 4.0xATR, 3.0R, 96h, maker | -0.252 (1366) | -0.235 (664) | **-0.269** (675) | +0.004 | +0.273 | -0.292 (603) | no | no |

## NDAX-level fees (0.20% / 0.20%)

### majors

| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | Test cost R | Test with vol gate | Holm | Survivor |
|---|---|---|---|---|---|---|---|---|---|
| breakout | 4.0xATR, 2.0R, 96h, maker | +0.021 (819) | -0.124 (187) | **-0.036** (174) | +0.136 | +0.172 | -0.029 (162) | no | no |
| rsi2_dip | 4.0xATR, 3.0R, 96h, maker | +0.032 (629) | -0.015 (133) | **+0.000** (126) | +0.149 | +0.149 | -0.030 (107) | no | no |
| pullback | 4.0xATR, 3.0R, 96h, taker | -0.020 (554) | -0.189 (116) | **-0.160** (111) | +0.017 | +0.177 | -0.057 (90) | no | no |
| retest | 4.0xATR, 3.0R, 96h, maker | +0.032 (550) | -0.016 (124) | **-0.233** (111) | -0.077 | +0.156 | -0.268 (105) | no | no |
| squeeze | 4.0xATR, 3.0R, 96h, maker | -0.159 (374) | +0.053 (86) | **-0.129** (97) | +0.098 | +0.227 | -0.169 (70) | no | no |
| momentum | 4.0xATR, 3.0R, 96h, maker | +0.073 (546) | +0.130 (110) | **-0.199** (122) | -0.030 | +0.169 | -0.172 (81) | no | no |
| orb | 4.0xATR, 3.0R, 96h, maker | -0.074 (1036) | -0.099 (218) | **-0.130** (196) | +0.018 | +0.148 | -0.168 (155) | no | no |
| every_bar | 4.0xATR, 3.0R, 96h, maker | -0.055 (1645) | -0.028 (314) | **-0.091** (334) | +0.056 | +0.147 | -0.120 (304) | no | no |

### memes

| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | Test cost R | Test with vol gate | Holm | Survivor |
|---|---|---|---|---|---|---|---|---|---|
| breakout | 4.0xATR, 2.0R, 96h, maker | -0.028 (606) | +0.011 (320) | **-0.025** (318) | +0.087 | +0.112 | -0.071 (312) | no | no |
| rsi2_dip | 4.0xATR, 2.0R, 96h, maker | +0.003 (447) | -0.156 (220) | **-0.170** (202) | -0.070 | +0.099 | -0.179 (177) | no | no |
| pullback | 4.0xATR, 3.0R, 96h, maker | +0.074 (384) | -0.189 (185) | **-0.320** (169) | -0.213 | +0.107 | -0.289 (144) | no | no |
| retest | 4.0xATR, 3.0R, 96h, maker | +0.064 (383) | +0.034 (208) | **+0.006** (172) | +0.113 | +0.108 | -0.046 (160) | no | **yes** |
| squeeze | 4.0xATR, 3.0R, 96h, maker | -0.187 (274) | +0.045 (171) | **-0.205** (159) | -0.047 | +0.157 | -0.163 (127) | no | no |
| momentum | 4.0xATR, 2.0R, 96h, maker | +0.056 (352) | -0.145 (178) | **-0.142** (193) | -0.043 | +0.099 | -0.145 (142) | no | no |
| orb | 4.0xATR, 2.0R, 96h, maker | -0.127 (906) | -0.151 (497) | **-0.061** (423) | +0.047 | +0.108 | -0.067 (355) | no | no |
| every_bar | 4.0xATR, 3.0R, 96h, maker | -0.119 (1366) | -0.113 (664) | **-0.104** (675) | +0.004 | +0.108 | -0.130 (603) | no | no |

## Low-fee exchange (0.08% / 0.10%)

### majors

| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | Test cost R | Test with vol gate | Holm | Survivor |
|---|---|---|---|---|---|---|---|---|---|
| breakout | 4.0xATR, 2.0R, 96h, maker | +0.086 (819) | -0.048 (187) | **+0.058** (174) | +0.136 | +0.078 | +0.063 (162) | no | no |
| rsi2_dip | 4.0xATR, 3.0R, 96h, maker | +0.093 (629) | +0.063 (133) | **+0.081** (126) | +0.149 | +0.069 | +0.044 (107) | no | **yes** |
| pullback | 4.0xATR, 3.0R, 96h, taker | +0.038 (554) | -0.120 (116) | **-0.077** (111) | +0.017 | +0.095 | +0.019 (90) | no | no |
| retest | 4.0xATR, 3.0R, 96h, maker | +0.091 (550) | +0.061 (124) | **-0.150** (111) | -0.077 | +0.073 | -0.184 (105) | no | no |
| squeeze | 4.0xATR, 3.0R, 96h, maker | -0.069 (374) | +0.158 (86) | **-0.007** (97) | +0.098 | +0.105 | -0.051 (70) | no | no |
| momentum | 4.0xATR, 3.0R, 96h, maker | +0.131 (546) | +0.201 (110) | **-0.109** (122) | -0.030 | +0.079 | -0.094 (81) | no | no |
| orb | 4.0xATR, 3.0R, 96h, maker | -0.016 (1036) | -0.035 (218) | **-0.052** (196) | +0.018 | +0.070 | -0.092 (155) | no | no |
| every_bar | 4.0xATR, 3.0R, 96h, maker | +0.003 (1645) | +0.038 (314) | **-0.012** (334) | +0.056 | +0.069 | -0.044 (304) | no | no |

### memes

| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | Test cost R | Test with vol gate | Holm | Survivor |
|---|---|---|---|---|---|---|---|---|---|
| breakout | 4.0xATR, 2.0R, 96h, maker | +0.015 (606) | +0.052 (320) | **+0.029** (318) | +0.087 | +0.058 | -0.016 (312) | no | **yes** |
| rsi2_dip | 4.0xATR, 2.0R, 96h, maker | +0.041 (447) | -0.118 (220) | **-0.123** (202) | -0.070 | +0.053 | -0.134 (177) | no | no |
| pullback | 4.0xATR, 3.0R, 96h, maker | +0.114 (384) | -0.150 (185) | **-0.271** (169) | -0.213 | +0.059 | -0.241 (144) | no | no |
| retest | 4.0xATR, 3.0R, 96h, maker | +0.105 (383) | +0.074 (208) | **+0.056** (172) | +0.113 | +0.057 | +0.005 (160) | no | **yes** |
| squeeze | 1.5xATR, 2.0R, 96h, maker | -0.047 (371) | -0.022 (228) | **-0.187** (218) | +0.024 | +0.211 | -0.150 (177) | no | no |
| momentum | 4.0xATR, 2.0R, 96h, maker | +0.092 (352) | -0.111 (178) | **-0.095** (193) | -0.043 | +0.052 | -0.101 (142) | no | no |
| orb | 4.0xATR, 2.0R, 96h, maker | -0.087 (906) | -0.113 (497) | **-0.009** (423) | +0.047 | +0.056 | -0.016 (355) | no | no |
| every_bar | 4.0xATR, 3.0R, 96h, maker | -0.079 (1366) | -0.077 (664) | **-0.054** (675) | +0.004 | +0.058 | -0.081 (603) | no | no |

## Stocks, commission-free broker (spread and regulatory fees only)

### stocks

| Setup | Chosen on train (stop, target, hold, entry) | Train R (n) | Validation R (n) | Test R (n) | Test gross R | Test cost R | Test with vol gate | Holm | Survivor |
|---|---|---|---|---|---|---|---|---|---|
| breakout | 4.0xATR, 3.0R, 96h, maker | +0.350 (173) | -0.441 (47) | **+0.126** (51) | +0.134 | +0.008 | +0.086 (51) | no | no |
| rsi2_dip | 4.0xATR, 3.0R, 96h, maker | +0.340 (158) | -0.413 (44) | **+0.212** (41) | +0.221 | +0.009 | +0.269 (40) | no | no |
| pullback | 4.0xATR, 3.0R, 96h, taker | +0.338 (134) | -0.639 (33) | **+0.140** (37) | +0.158 | +0.018 | +0.140 (37) | no | no |
| retest | 2.0xATR, 2.0R, 24h, maker | +0.186 (240) | -0.363 (49) | **+0.083** (70) | +0.098 | +0.016 | +0.038 (67) | no | no |
| squeeze | 3.0xATR, 3.0R, 96h, taker | +0.108 (86) | -0.750 (14) | **+0.344** (26) | +0.366 | +0.022 | +0.422 (25) | no | no |
| momentum | 4.0xATR, 3.0R, 96h, maker | +0.306 (191) | -0.327 (52) | **+0.126** (58) | +0.135 | +0.009 | +0.091 (43) | no | no |
| orb | 4.0xATR, 3.0R, 96h, taker | +0.308 (262) | -0.264 (72) | **+0.556** (63) | +0.571 | +0.015 | +0.494 (58) | no | no |
| every_bar | 4.0xATR, 3.0R, 24h, maker | +0.122 (854) | -0.061 (242) | **+0.129** (220) | +0.139 | +0.010 | +0.117 (212) | no | no |
