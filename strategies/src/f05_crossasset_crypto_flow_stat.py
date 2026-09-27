"""Families: cross-asset & relative value; crypto derivatives & venue structure; order flow & microstructure;
statistical & regime; machine learning; market making & arbitrage; named multi-screen systems."""
from lib import BOTH, CRYPTO, STOCK, st, variant

X = "cross_asset"
st("relative_strength_vs_index", "Intraday relative strength vs the index", X, "relative strength", mech="stocks leading the market on the day attract flows",
   logic="continuation", anchor="return since open minus SPY's",
   hyp="A stock up at least 1% more than SPY since the open, holding above VWAP, keeps outperforming into the afternoon.",
   markets=STOCK, tf="5m", params={"bench": "SPY"},
   entry={"long": "close / session().open - sym($bench, close / session().open) > 0.01 and close > vwap() and minutes_since_open() >= 60",
          "short": "close / session().open - sym($bench, close / session().open) < -0.01 and close < vwap() and minutes_since_open() >= 60"},
   stop={"type": "level", "long": "vwap()", "short": "vwap()", "buffer_atr": 0.3, "n": 14}, mtd=1, research="hypothesis")
st("residual_reversion", "Beta-adjusted residual reversion", X, "statistical arbitrage", mech="idiosyncratic deviations from the market revert",
   logic="reversal", anchor="z-score of the 60-bar beta-adjusted spread vs SPY",
   hyp="When a stock's log price minus beta times SPY's falls two standard deviations below its 60-bar mean, it reverts.",
   markets=STOCK, tf="5m", params={"bench": "SPY"},
   entry={"long": "spread_z(close, sym($bench, close), 60) < -2", "short": "spread_z(close, sym($bench, close), 60) > 2"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, exit={"long": "spread_z(close, sym($bench, close), 60) > 0", "short": "spread_z(close, sym($bench, close), 60) < 0"},
   max_bars=24, ev=[("SRC-020", "direct", "daily residual mean reversion with ETF factors; intraday single-leg adaptation")],
   research="incompletely sourced", fail=["single leg: carries market risk that the paper hedged"])
variant("etf_pair_spread", "residual_reversion", "QQQ/SPY spread reversion (one leg)", "pair of ETFs instead of stock vs index", ev=[("SRC-021", "mechanism", "")])
st("crypto_pair_ratio_reversion", "ETH/BTC ratio reversion", X, "pairs", mech="relative mispricing between close substitutes reverts",
   logic="reversal", anchor="z-score of log ETH-BTC price",
   hyp="Trade the ETH-BTC product when its log price is more than 2 standard deviations from its 200-bar mean.",
   markets=CRYPTO, tf="15m", instruments=["ETH-BTC"],
   entry={"long": "zscore(log(close), 200) < -2", "short": "zscore(log(close), 200) > 2"},
   stop={"type": "atr", "mult": 2.5, "n": 14}, exit={"long": "zscore(log(close), 200) > 0", "short": "zscore(log(close), 200) < 0"},
   ev=[("SRC-021", "mechanism", "distance-method pairs trading in stocks")], research="incompletely sourced",
   notes="Spot ETH-BTC cannot be shorted on spot venues; only the long side trades unless a margin venue is used.")
st("lead_lag_catch_up", "Leader-to-laggard catch-up", X, "lead-lag", mech="information reaches the leading asset first and diffuses slowly",
   logic="continuation", anchor="leader's 15-minute return vs follower's", params={"lead": "BTC-USD"},
   hyp="When the leader (BTC) rises more than 1% in 15 minutes and the follower has moved less than half as much, buy the follower.",
   markets=CRYPTO, tf="5m",
   entry={"long": "sym($lead, pct(close,3)) > 0.01 and pct(close,3) < 0.5*sym($lead, pct(close,3))",
          "short": "sym($lead, pct(close,3)) < -0.01 and pct(close,3) > 0.5*sym($lead, pct(close,3))"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, max_bars=6, ev=[("SRC-015", "mechanism", "big-to-small lead-lag within industries (weekly)")],
   research="hypothesis")
variant("btc_leads_coin", "lead_lag_catch_up", "BTC leads COIN/MSTR", "follower: US crypto stocks")
variant("spy_leads_iwm", "lead_lag_catch_up", "SPY leads IWM", "leader SPY, follower small caps", ev=[("SRC-015", "mechanism", "")])
st("vix_spike_reversion", "VIX-spike capitulation buy", X, "volatility index", mech="fear spikes overshoot",
   logic="reversal", anchor="VIX change vs prior close + SPY below VWAP band",
   hyp="When VIX is up more than 10% on the day and SPY closes back inside its lower 2-sd VWAP band, buy SPY for a rebound.",
   markets=STOCK, tf="5m", instruments=["SPY", "QQQ"],
   entry={"long": "sym(\"^VIX\", close) / sym(\"^VIX\", session().prev_close) - 1 > 0.10 and cross_above(close, vwap().lower2)"},
   stop={"type": "level", "long": "session().low", "buffer_atr": 0.2, "n": 14}, target={"type": "level", "long": "vwap()"}, mtd=1,
   research="hypothesis", notes="Uses Yahoo's ^VIX index series.")

D = "crypto_structure"
st("perp_basis_reversion", "Perpetual-spot basis reversion", D, "basis", mech="perpetual prices are tied to spot by funding; extreme basis mean-reverts",
   logic="reversal", anchor="z-score of OKX BTC perp / spot - 1",
   hyp="Short the perpetual when its premium over spot is more than 2.5 standard deviations above its 1-day mean; long when below.",
   markets=CRYPTO, tf="5m", instruments=["BTC-USDT-SWAP"],
   entry={"long": "zscore(close / sym(\"okx:BTC-USDT\", close) - 1, 288) < -2.5", "short": "zscore(close / sym(\"okx:BTC-USDT\", close) - 1, 288) > 2.5"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, exit={"long": "zscore(close / sym(\"okx:BTC-USDT\", close) - 1, 288) > 0",
                                                    "short": "zscore(close / sym(\"okx:BTC-USDT\", close) - 1, 288) < 0"},
   ev=[("SRC-035", "mechanism", "perp-spot deviations and no-arbitrage bounds")], research="incompletely sourced",
   notes="Runs on the OKX BTC-USDT perpetual (shortable). OKX availability to Canadian residents was not checked.")
st("coinbase_premium", "US-venue premium momentum", D, "cross-venue premium", mech="US demand shows up first as a Coinbase premium",
   logic="continuation", anchor="Coinbase BTC-USD / OKX BTC-USDT - 1",
   hyp="When the Coinbase premium over OKX rises above +2 standard deviations of its 1-day history, buy BTC on Coinbase.",
   markets=CRYPTO, tf="5m", instruments=["BTC-USD"], direction="long",
   entry={"long": "zscore(close / sym(\"okx:BTC-USDT\", close) - 1, 288) > 2"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, max_bars=24, ev=[("SRC-034", "mechanism", "cross-exchange premia widen during appreciation")],
   research="incompletely sourced", notes="Premium includes USDT/USD drift; stablecoin de-pegs distort it.")
variant("usdt_premium", "coinbase_premium", "Stablecoin premium signal", "USDT-USD deviation instead of cross-venue premium")
st("cme_gap_fill", "Weekend (CME-hours) gap fill", D, "weekend structure", mech="price tends to revisit the level where the regulated futures market closed on Friday",
   logic="reversal", anchor="spot at Friday 21:00 UTC vs Sunday 23:00 UTC",
   hyp="If bitcoin re-opens the week more than 1% away from Friday's 21:00 UTC price, trade back toward that level during Monday (UTC).",
   markets=CRYPTO, tf="15m", instruments=["BTC-USD"],
   entry={"short": "dow() == 0 and weekend(21,23).gap > 0.01 and close > weekend(21,23).fri_close and close < open",
          "long": "dow() == 0 and weekend(21,23).gap < -0.01 and close < weekend(21,23).fri_close and close > open"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "level", "long": "weekend(21,23).fri_close", "short": "weekend(21,23).fri_close"},
   mtd=1, research="hypothesis", notes="21:00/23:00 UTC approximate CME hours in summer; one hour later in winter.")
st("weekend_range_breakout", "Monday breakout of the weekend range", D, "weekend structure", mech="thin weekend ranges are broken when institutional flow returns",
   logic="breakout", anchor="Saturday-Sunday high/low",
   hyp="On Monday (UTC), a close beyond the weekend's range continues.",
   markets=CRYPTO, tf="15m",
   entry={"long": "dow() == 0 and cross_above(close, weekend(21,23).high)", "short": "dow() == 0 and cross_below(close, weekend(21,23).low)"},
   stop={"type": "level", "long": "(weekend(21,23).high + weekend(21,23).low)/2", "short": "(weekend(21,23).high + weekend(21,23).low)/2"},
   target={"type": "r", "r": 2.0}, mtd=1, research="hypothesis")
st("stablecoin_peg_reversion", "Stablecoin peg reversion", D, "peg", mech="redemption arbitrage pulls fully-backed stablecoins back to $1",
   logic="reversal", anchor="USDT-USD / USDC price vs 1.00",
   hyp="Buy a major stablecoin trading below 0.998 USD; sell at 0.9995 or the session end.",
   markets=CRYPTO, tf="5m", instruments=["USDT-USD"], direction="long",
   entry={"long": "close < 0.998"}, stop={"type": "pct", "pct": 1.0}, target={"type": "level", "long": "0.9995"}, mtd=2,
   research="hypothesis", fail=["a real de-peg does not revert", "fees exceed the spread captured at retail tiers"])
st("perp_volume_lead", "Derivatives-led volume spike fade", D, "venue volume", mech="moves driven by leveraged perp volume without spot volume are fragile",
   logic="reversal", anchor="perp/spot volume ratio",
   hyp="When perpetual volume exceeds 5x its usual ratio to spot volume during a sharp move, fade the move.",
   markets=CRYPTO, tf="5m", instruments=["BTC-USDT"],
   entry={"short": "zscore(sym(\"okx:BTC-USDT-SWAP\", volume) / max(volume, 1e-9), 288) > 3 and pct(close,3) > 0.005",
          "long": "zscore(sym(\"okx:BTC-USDT-SWAP\", volume) / max(volume, 1e-9), 288) > 3 and pct(close,3) < -0.005"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, max_bars=6, research="hypothesis",
   notes="Perp volume is in contracts and spot in coins, so only the z-score (not the level) is meaningful.")
st("funding_extreme_contrarian", "Funding-rate extreme contrarian", D, "funding", mech="crowded leveraged positioning (extreme funding) unwinds",
   logic="reversal", anchor="OKX funding rate",
   hyp="When the latest funding rate is above +0.05% per 8h, fade intraday strength in the perpetual; below -0.03%, buy weakness.",
   markets=CRYPTO, tf="15m", data=("bars", "funding"), blocked="funding-rate series is fetched by the adapter but not yet wired into the live hub as a rule input",
   ev=[("SRC-035", "mechanism", "funding ties perp to spot")], research="hypothesis",
   spec="entry short: funding > 0.0005 and close < vwap(); entry long: funding < -0.0003 and close > vwap(); stop 2 ATR; flat by 23:55 UTC")
st("funding_settlement_drift", "Pre-funding-settlement drift", D, "funding", mech="positions are adjusted ahead of 8-hourly funding settlements",
   logic="event bias", anchor="00:00/08:00/16:00 UTC", markets=CRYPTO, tf="5m", data=("bars", "funding"),
   hyp="In the hour before a settlement with extreme funding, the paying side reduces positions, pushing price against it.",
   blocked="needs the funding series wired into the hub", research="hypothesis",
   spec="in the 60 minutes before 00:00/08:00/16:00 UTC: if funding > 0.03% short, if < -0.03% long; exit at settlement")
st("oi_breakout_confirmation", "Open-interest-confirmed breakout", D, "open interest", mech="breakouts with rising open interest reflect new positions, not short covering",
   logic="breakout", anchor="OKX open interest", markets=CRYPTO, tf="5m", data=("bars", "oi"),
   hyp="Only take 20-bar breakouts when open interest rose over the same bars.",
   blocked="historical open interest at 5-minute resolution is not available from the free endpoints used", research="hypothesis",
   spec="long: close > donchian(20).upper[1] and oi change over 20 bars > 1%")
st("liquidation_cascade_reversal", "Liquidation-cascade reversal", D, "liquidations", mech="forced liquidations overshoot",
   logic="reversal", anchor="exchange liquidation prints", markets=CRYPTO, tf="1m", data=("bars", "liquidations"),
   hyp="After a burst of long liquidations with a >2% drop in 5 minutes, buy the first higher close.",
   blocked="liquidation feeds are recent-only on free endpoints; no history for testing and not wired live", research="hypothesis",
   spec="long: liquidation notional over 5 min > 99th pct and pct(close,5) < -0.02 and close > open; stop below the low; target VWAP")
st("dvol_spike_fade", "Implied-volatility spike fade (Deribit DVOL)", D, "implied volatility", mech="implied-volatility spikes mark panic extremes",
   logic="reversal", anchor="Deribit DVOL", markets=CRYPTO, tf="1h", data=("bars", "dvol"),
   hyp="When DVOL jumps more than 15% in a day and price is at a 24-hour low, buy for a rebound.",
   blocked="DVOL adapter exists in research scripts only; not wired into the hub", research="hypothesis",
   spec="long: dvol / dvol[24] - 1 > 0.15 and close <= lowest(low,24) and close > open")
st("options_expiry_max_pain", "Deribit expiry max-pain drift", D, "options expiry", mech="option-writer hedging pulls price toward the max-pain strike into Friday 08:00 UTC expiry",
   logic="event bias", anchor="max-pain strike", markets=CRYPTO, tf="1h", data=("bars", "options_oi"),
   hyp="On expiry Thursday/Friday, price drifts toward the strike that minimises option-holder payoff.",
   blocked="needs per-strike open interest history (not collected)", research="hypothesis",
   spec="compute max-pain from Deribit open interest by strike; trade toward it from Thursday 12:00 UTC; exit 08:00 UTC Friday")
st("kimchi_premium", "Korean-premium sentiment signal", D, "cross-country premium", mech="retail demand in Korea shows as a premium over US prices",
   logic="continuation", anchor="Upbit KRW price / (USD price x KRW rate)", markets=CRYPTO, tf="15m", data=("bars", "upbit", "fx"),
   hyp="A rising Korean premium precedes further gains in global prices.", blocked="no Upbit adapter built",
   ev=[("SRC-034", "mechanism", "country premia co-move with BTC appreciation")], research="incompletely sourced",
   spec="long when premium z-score (1 day) > 2; exit when it falls below 0")
st("listing_announcement", "Exchange listing announcement momentum", D, "listings", mech="new listings on large venues attract buyers",
   logic="event bias", anchor="listing announcements", markets=CRYPTO, tf="1m", data=("bars", "announcements"),
   hyp="Buy a token on another venue immediately after a major-exchange listing announcement.",
   blocked="no machine-readable announcement feed; also front-running risk and very high slippage", research="hypothesis",
   spec="on announcement: buy within 1 minute on a venue already listing it; exit after 60 minutes or +20%")

O = "order_flow"
st("book_imbalance_momentum", "Order-book imbalance momentum", O, "book depth", mech="depth imbalance at the best levels predicts short-term price changes",
   logic="continuation", anchor="top-10 depth imbalance at bar close",
   hyp="When bid depth exceeds ask depth by 30% and aggressive buying dominates the bar, price drifts up over the next few bars.",
   markets=CRYPTO, tf="1m", data=("bars", "trades", "book"),
   entry={"long": "book().imbalance > 0.3 and orderflow().imbalance > 0.2", "short": "book().imbalance < -0.3 and orderflow().imbalance < -0.2"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, max_bars=3, mtd=20,
   ev=[("SRC-017", "mechanism", "order-flow imbalance drives contemporaneous price changes (NYSE)")], research="incompletely sourced",
   notes="Live only: needs recorded trades and books; history is not available for backtests.")
st("trade_imbalance_persistence", "Aggressor-flow persistence", O, "trade flow", mech="lagged order imbalance predicts 5-minute returns",
   logic="continuation", anchor="aggressor volume imbalance over 3 bars",
   hyp="When buyer-initiated volume exceeds seller-initiated volume by 25% over three 5-minute bars, the next bar tends to rise.",
   markets=CRYPTO, tf="5m", data=("bars", "trades"),
   entry={"long": "sum(orderflow().delta, 3) / sum(volume, 3) > 0.25", "short": "sum(orderflow().delta, 3) / sum(volume, 3) < -0.25"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, max_bars=2, mtd=20,
   ev=[("SRC-016", "mechanism", "lagged imbalance predicts 5-minute NYSE returns")], research="incompletely sourced")
st("cvd_divergence", "Cumulative-delta divergence", O, "trade flow", mech="new price highs without new buying pressure are fragile",
   logic="reversal", anchor="session CVD vs price",
   hyp="A new 20-bar price high while cumulative delta is below its 20-bar high is unsupported; short on the next down close.",
   markets=CRYPTO, tf="5m", data=("bars", "trades"),
   entry={"short": "high >= highest(high,20) and orderflow().cvd < highest(orderflow().cvd,20)[1] and close < open",
          "long": "low <= lowest(low,20) and orderflow().cvd > lowest(orderflow().cvd,20)[1] and close > open"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 1.5}, research="hypothesis")
st("absorption", "Absorption of aggressive selling", O, "trade flow", mech="passive buyers absorbing aggressive sells hold price",
   logic="reversal", anchor="delta vs close location",
   hyp="A bar with strongly negative delta that still closes in its top 30% shows passive buyers absorbing supply.",
   markets=CRYPTO, tf="5m", data=("bars", "trades"),
   entry={"long": "orderflow().imbalance < -0.4 and close > high - 0.3*(high - low)", "short": "orderflow().imbalance > 0.4 and close < low + 0.3*(high - low)"},
   stop={"type": "level", "long": "low", "short": "high", "buffer_atr": 0.1, "n": 14}, target={"type": "r", "r": 1.5}, max_bars=6,
   research="hypothesis")
st("large_print_following", "Large-print following", O, "trade size", mech="unusually large aggressive trades come from informed participants",
   logic="continuation", anchor="trades above the 99.9th size percentile", markets=CRYPTO, tf="1m", data=("bars", "trades"),
   hyp="Follow the direction of clusters of very large aggressive prints.", blocked="per-trade size distribution is not aggregated by the hub",
   research="hypothesis", spec="long when buy volume from trades > 99.9th size percentile exceeds sell volume by 3x within a minute; hold 5 minutes")
st("vpin_toxicity_breakout", "Flow-toxicity (VPIN) regime", O, "toxicity", mech="rising order-flow toxicity precedes volatility",
   logic="volatility regime", anchor="VPIN on volume buckets", markets=CRYPTO, tf="1m", data=("bars", "trades"),
   hyp="When VPIN is above its 90th percentile, trade breakouts of the 15-minute range; otherwise stand aside.",
   blocked="volume-bucket VPIN is not implemented in the indicator engine", ev=[("SRC-018", "origin", "VPIN definition")],
   research="incompletely sourced", spec="VPIN over 50 volume buckets of 1/50 daily volume; breakout rule as orb_breakout")
st("stock_tape_reading", "US stock tape and level-2 reading", O, "stocks order flow", mech="large resting orders and aggressive prints reveal intent",
   logic="continuation", anchor="level-2 book + time and sales", markets=STOCK, tf="1m", data=("bars", "quotes", "trades"),
   hyp="Buy when large bids stack and prints hit the offer repeatedly at a level.",
   blocked="no free real-time US quotes, book or trade prints (Yahoo provides bars only)", research="hypothesis",
   spec="requires consolidated quotes/trades (paid feed); rules as book_imbalance_momentum")
st("closing_imbalance", "NYSE closing-auction imbalance", O, "auction imbalance", mech="published closing imbalances move prices into the close",
   logic="event flow", anchor="NYSE imbalance messages from 15:50 ET", markets=STOCK, tf="1m", data=("bars", "imbalance_feed"),
   hyp="Trade in the direction of large published buy/sell imbalances at 15:50.", blocked="imbalance feed is not free; platform also flattens 5 minutes before the close",
   research="hypothesis", spec="long when buy imbalance > 10% of ADV at 15:50; exit in the closing auction")
st("iceberg_detection", "Iceberg-order detection", O, "hidden liquidity", mech="repeated refills at one price reveal a hidden large order",
   logic="support/resistance", anchor="level-3 refills", markets=BOTH, tf="1m", data=("bars", "l3"),
   hyp="Trade off a price level that keeps refilling after being hit.", blocked="needs level-3 / full order-event data",
   research="hypothesis", spec="detect > 5 refills at the same price within 60 s; buy above it with a stop just below")
st("microprice_queue", "Microprice / queue-imbalance scalping", O, "tick microstructure", mech="queue imbalance predicts the next mid-price move",
   logic="scalp", anchor="best-level sizes", markets=BOTH, tf="tick", data=("ticks", "book"),
   hyp="Take the side favoured by the microprice when queue imbalance exceeds 0.7.", blocked="tick-level data and queue-position simulation are not available",
   ev=[("SRC-017", "mechanism", "")], research="incompletely sourced", spec="enter at touch when imbalance > 0.7; exit on next mid change")

Q = "statistical"
st("variance_ratio_regime", "Variance-ratio regime switch", Q, "regime", mech="markets alternate between trending (VR>1) and mean-reverting (VR<1) states",
   logic="regime-dependent", anchor="variance ratio(120,5)",
   hyp="When the 5-bar variance ratio exceeds 1.2 trade 20-bar breakouts; when below 0.8 fade Bollinger band excursions.",
   entry={"long": "(variance_ratio(120,5) > 1.2 and close > donchian(20).upper[1]) or (variance_ratio(120,5) < 0.8 and cross_above(close, bb(close,20,2).lower))",
          "short": "(variance_ratio(120,5) > 1.2 and close < donchian(20).lower[1]) or (variance_ratio(120,5) < 0.8 and cross_below(close, bb(close,20,2).upper))"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "r", "r": 1.5}, max_bars=24,
   ev=[("SRC-046", "origin", "variance-ratio test")], research="hypothesis")
variant("hurst_regime", "variance_ratio_regime", "Hurst-exponent regime switch", "Hurst exponent instead of variance ratio")
st("autocorrelation_follow", "Autocorrelation-signed follow/fade", Q, "serial dependence", mech="the sign of recent return autocorrelation persists",
   logic="regime-dependent", anchor="60-bar lag-1 autocorrelation",
   hyp="If lag-1 autocorrelation over 60 bars is above +0.1, follow the last bar; if below -0.1, fade it; hold 2 bars.",
   entry={"long": "(autocorr(60,1) > 0.1 and close > close[1]) or (autocorr(60,1) < -0.1 and close < close[1])",
          "short": "(autocorr(60,1) > 0.1 and close < close[1]) or (autocorr(60,1) < -0.1 and close > close[1])"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, max_bars=2, mtd=10, ev=[("SRC-046", "mechanism", "serial correlation")], research="hypothesis")
st("ou_halflife_reversion", "Ornstein-Uhlenbeck reversion with half-life filter", Q, "mean reversion model", mech="fast-mean-reverting deviations revert within their half-life",
   logic="reversal", anchor="AR(1) of price deviations from the 100-bar mean",
   hyp="Only fade 2-sigma deviations when the fitted AR(1) coefficient implies a half-life under 20 bars.",
   entry={"long": "zscore(close,100) < -2 and beta(close - mean(close,100), close[1] - mean(close,100)[1], 100) < 0.966",
          "short": "zscore(close,100) > 2 and beta(close - mean(close,100), close[1] - mean(close,100)[1], 100) < 0.966"},
   stop={"type": "atr", "mult": 2.0, "n": 14}, target={"type": "level", "long": "mean(close,100)", "short": "mean(close,100)"}, max_bars=20,
   research="hypothesis", notes="0.966 = exp(-ln2/20): an AR(1) coefficient below it means a half-life under 20 bars.")
st("kalman_trend", "Kalman local-trend filter", Q, "state space", mech="a local-linear-trend filter separates slope from noise",
   logic="continuation", anchor="Kalman slope", markets=BOTH, tf="5m",
   hyp="Trade in the direction of the filtered slope when it exceeds two of its standard errors.",
   blocked="Kalman filter indicator not implemented", research="hypothesis", spec="local linear trend model; long when slope/se > 2; exit when < 0")
st("hmm_regime", "Hidden-Markov regime model", Q, "regime", mech="latent volatility/trend regimes", logic="regime-dependent", anchor="2-state HMM",
   hyp="Trade trend rules in the high-persistence state and reversion rules in the other.", markets=BOTH, tf="15m",
   blocked="no HMM fitting in the platform (would need numpy/hmmlearn)", research="hypothesis",
   spec="fit 2-state Gaussian HMM on returns walk-forward; map states to rule sets")

ML = "machine_learning"
MLB = "no model-training runtime in the bot platform yet (the separate Jarvus Brain trains models offline)"
st("ml_logistic_direction", "Walk-forward logistic regression direction model", ML, "supervised", mech="combining weak predictors",
   logic="prediction", anchor="features: returns 1/3/6/12 bars, RSI14, rvol, VWAP distance, time of day", markets=BOTH, tf="5m",
   hyp="A logistic model re-fit daily on the last 30 days predicts the sign of the next 6-bar return; trade when p > 0.6.",
   blocked=MLB, ev=[("SRC-064", "context", "purged CV and embargo for financial ML")], research="hypothesis",
   spec="label: sign of 6-bar forward return; purge 6 bars and embargo 1 day between train and test; trade top decile of p")
st("ml_triple_barrier_gbm", "Gradient boosting on triple-barrier labels", ML, "supervised", mech="non-linear feature interactions",
   logic="prediction", anchor="triple-barrier labels", markets=BOTH, tf="5m", hyp="Boosted trees classify which barrier (target, stop, time) is hit first.",
   blocked=MLB, ev=[("SRC-064", "origin", "triple-barrier method")], research="incompletely sourced",
   spec="barriers at +/-1.5 ATR and 12 bars; features as ml_logistic_direction; purged k-fold CV")
st("ml_meta_labeling", "Meta-labelling filter on rule signals", ML, "meta-labelling", mech="a second model learns when a primary rule's signals work",
   logic="filter", anchor="primary: orb_breakout signals", markets=BOTH, tf="5m",
   hyp="A classifier trained on the context of past ORB signals skips the ones likely to fail.", blocked=MLB,
   ev=[("SRC-064", "origin", "meta-labelling")], research="incompletely sourced", spec="primary signals from orb_breakout; secondary model predicts win/loss; size by probability")
st("ml_knn_analog", "Nearest-neighbour analog forecasting", ML, "instance-based", mech="similar recent patterns lead to similar outcomes",
   logic="prediction", anchor="z-scored last 20 returns", markets=BOTH, tf="15m", hyp="Average the outcomes of the 20 most similar historical windows.",
   blocked=MLB, research="hypothesis", spec="k=20 Euclidean on normalised 20-bar return vectors; trade if mean outcome > costs")
st("ml_sequence_model", "Recurrent/sequence neural network", ML, "deep learning", mech="non-linear temporal dependencies", logic="prediction",
   anchor="raw bar sequences", markets=BOTH, tf="5m", hyp="An LSTM/Transformer on bar sequences predicts next-hour direction.",
   blocked=MLB + "; very high overfitting risk at retail data sizes", research="hypothesis", spec="walk-forward train monthly; purged validation; compare against a no-skill baseline")
st("ml_reinforcement_agent", "Reinforcement-learning trading agent", ML, "reinforcement learning", mech="policy learned from simulated rewards",
   logic="policy", anchor="simulated environment", markets=BOTH, tf="5m", hyp="An agent trained in the paper simulator learns entry/exit timing.",
   blocked=MLB + "; simulator-exploitation risk", research="hypothesis", spec="PPO on the platform's backtester with costs; evaluate only on untouched data")

A = "market_making_arbitrage"
st("avellaneda_stoikov_mm", "Inventory-aware market making", A, "market making", mech="earn the spread while skewing quotes against inventory",
   logic="liquidity provision", anchor="reservation price", markets=CRYPTO, tf="tick", data=("ticks", "book"),
   hyp="Quote both sides around an inventory-adjusted reservation price.", blocked="needs tick data and a queue-position fill model; maker fills cannot be simulated honestly from bars",
   ev=[("SRC-019", "origin", "the model")], research="incompletely sourced", spec="reservation r = s - q*gamma*sigma^2*(T-t); spread from the paper's formula")
st("grid_trading", "Intraday grid", A, "grid", mech="harvest oscillation inside a range", logic="liquidity provision", anchor="fixed price grid",
   markets=CRYPTO, tf="1m", hyp="Buy every 0.5% down and sell every 0.5% up inside the day's expected range.",
   blocked="the trade manager holds one position per bot; multi-order grids are not supported", research="hypothesis",
   spec="10 levels, 0.5% apart around the session open; flat by 23:55 UTC", fail=["trends run through every level", "maker fees"])
st("triangular_arbitrage", "Triangular arbitrage (BTC-USD / ETH-USD / ETH-BTC)", A, "arbitrage", mech="cross rates must be consistent",
   logic="arbitrage", anchor="three books", markets=CRYPTO, tf="tick", data=("ticks", "book"),
   hyp="Trade the three legs when the implied cross rate deviates by more than total fees.",
   blocked="needs simultaneous multi-leg execution and tick data; fees at retail tiers exceed typical deviations", research="hypothesis",
   spec="deviation = (ETH-USD / BTC-USD) / ETH-BTC - 1; act when |dev| > 3 x taker fee")
st("cross_exchange_arbitrage", "Cross-exchange arbitrage", A, "arbitrage", mech="the same coin trades at different prices on different venues",
   logic="arbitrage", anchor="Coinbase vs Kraken", markets=CRYPTO, tf="1s", data=("book",),
   hyp="Buy on the cheaper venue and sell on the dearer one.", blocked="needs funded accounts on both venues and real transfers (real money)",
   ev=[("SRC-034", "mechanism", "")], research="incompletely sourced", spec="act when price gap > both taker fees + withdrawal cost")
st("statarb_pca_portfolio", "PCA statistical-arbitrage portfolio", A, "stat arb", mech="residual mean reversion across many stocks",
   logic="reversal", anchor="PCA residuals", markets=STOCK, tf="15m", data=("bars", "universe"),
   hyp="Hold many small long/short positions in stocks whose PCA residual is stretched.",
   blocked="needs simultaneous positions in dozens of stocks and shorting; one-instrument bots cannot express it",
   ev=[("SRC-020", "direct", "")], research="sourced", spec="15 PCA factors on 60-day returns; s-score entry +/-1.25, exit +/-0.5 (as in the paper, daily)")
st("funding_carry", "Funding-rate carry (spot long / perp short)", A, "carry", mech="collect funding paid by leveraged longs",
   logic="carry", anchor="funding", markets=CRYPTO, tf="8h", data=("funding",),
   hyp="Hold spot long and perp short while funding is positive.", blocked="not day trading: the position is held across funding settlements; also needs two venues",
   ev=[("SRC-035", "mechanism", "")], research="incompletely sourced", spec="enter when 7-day average funding > 0.01% per 8h; exit when negative")

N = "named_systems"
st("elder_triple_screen", "Triple Screen (Elder)", N, "multi-timeframe", mech="trade the higher-timeframe tide, enter on lower-timeframe waves",
   logic="continuation (pullback)", anchor="1h MACD-histogram slope + 5m force index",
   hyp="When the hourly MACD histogram is rising, buy 5-minute pullbacks (2-period force index below zero) with a buy stop above the prior bar.",
   tf="5m",
   entry={"long": "tf(\"1h\", macd(close,12,26,9).hist > macd(close,12,26,9).hist[1]) == 1 and force(2) < 0",
          "short": "tf(\"1h\", macd(close,12,26,9).hist < macd(close,12,26,9).hist[1]) == 1 and force(2) > 0"},
   order={"type": "stop", "long": "high", "short": "low", "ttl_bars": 2},
   stop={"type": "level", "long": "lowest(low,3)", "short": "highest(high,3)"}, target={"type": "r", "r": 2.0},
   ev=[("SRC-076", "origin", "Triple Screen (book)")], research="incompletely sourced")
st("holy_grail", "Holy Grail (Raschke)", N, "ADX pullback", mech="first pullback to the 20-EMA in a strong trend",
   logic="continuation (pullback)", anchor="ADX(14) > 30, EMA(20)",
   hyp="When ADX is above 30 and rising, a pullback to the 20-EMA is bought with a stop order above the pullback bar's high.",
   entry={"long": "adx(14).adx > 30 and adx(14).adx > adx(14).adx[1] and adx(14).plus_di > adx(14).minus_di and low <= ema(close,20)",
          "short": "adx(14).adx > 30 and adx(14).adx > adx(14).adx[1] and adx(14).minus_di > adx(14).plus_di and high >= ema(close,20)"},
   order={"type": "stop", "long": "high", "short": "low", "ttl_bars": 3},
   stop={"type": "level", "long": "low", "short": "high", "buffer_atr": 0.1, "n": 14}, target={"type": "r", "r": 2.0},
   ev=[("SRC-071", "origin", "Holy Grail (book)")], research="incompletely sourced")
st("the_anti", "The Anti (Raschke)", N, "stochastic hook", mech="a counter-move against a slow stochastic trend that fails",
   logic="continuation", anchor="Stochastic(7,10,10)",
   hyp="With slow %D rising, a pullback in %K that hooks back up signals the trend resuming.",
   entry={"long": "stoch(7,10,10).d > stoch(7,10,10).d[1] and stoch(7,10,10).k[1] < stoch(7,10,10).k[2] and stoch(7,10,10).k > stoch(7,10,10).k[1]",
          "short": "stoch(7,10,10).d < stoch(7,10,10).d[1] and stoch(7,10,10).k[1] > stoch(7,10,10).k[2] and stoch(7,10,10).k < stoch(7,10,10).k[1]"},
   stop={"type": "atr", "mult": 1.5, "n": 14}, target={"type": "r", "r": 1.5}, max_bars=12,
   ev=[("SRC-071", "origin", "The Anti (book)")], research="incompletely sourced")
st("eighty_twenty", "80-20s (Raschke)", N, "bar-reversal", mech="a bar that opened at its top and closed at its bottom often reverses the next bar",
   logic="reversal", anchor="prior bar open/close location",
   hyp="If the prior bar opened in the top 20% and closed in the bottom 20% of its range, buy when price trades below its low then back above it.",
   entry={"long": "open[1] > low[1] + 0.8*(high[1] - low[1]) and close[1] < low[1] + 0.2*(high[1] - low[1]) and low < low[1] and close > low[1]",
          "short": "open[1] < low[1] + 0.2*(high[1] - low[1]) and close[1] > low[1] + 0.8*(high[1] - low[1]) and high > high[1] and close < high[1]"},
   stop={"type": "level", "long": "low", "short": "high"}, target={"type": "r", "r": 1.5}, max_bars=12,
   ev=[("SRC-071", "origin", "80-20s (book, daily bars)")], research="incompletely sourced")
st("wolfe_wave", "Wolfe waves", N, "geometric pattern", mech="five-wave channel geometry projects a target line",
   logic="reversal", anchor="five swing points", markets=BOTH, tf="15m",
   hyp="A completed five-point Wolfe wave reverses toward the 1-4 line.", blocked="five-swing geometric pattern not implemented (engine tracks three swings)",
   ev=[("SRC-071", "origin", "Wolfe Waves (book)")], research="incompletely sourced", spec="points 1-5 alternating swings; 5 beyond the 1-3 line; target line through 1 and 4")
st("harmonic_patterns", "Harmonic (Gartley/Bat) patterns", N, "geometric pattern", mech="Fibonacci ratio relationships between swings",
   logic="reversal", anchor="XABCD swings", markets=BOTH, tf="15m", hyp="Price reverses at the D point of an XABCD pattern meeting ratio tolerances.",
   blocked="five-swing pattern matching not implemented", research="hypothesis",
   spec="Gartley: AB=0.618 XA, BC 0.382-0.886 AB, CD 1.27-1.618 BC, D at 0.786 XA; enter at D with stop beyond X")
