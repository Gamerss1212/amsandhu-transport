# Knowledge base: Bitcoin, crypto markets, on-chain, derivatives, cycles, Canada

One entry per `### `. Facts here are stable background; anything that changes (fees, listings, rules, ETF flows)
must be checked live before it is quoted. `More:` points to the long reference.

### Bitcoin basics
aka: bitcoin, btc, what is bitcoin, satoshi, 21 million, supply cap, blockchain
What: the first cryptocurrency (Satoshi Nakamoto, 2009). Fixed supply cap of 21 million BTC; new coins come from mining; a block about every 10 minutes; 1 BTC = 100,000,000 satoshis.
Market: the most liquid crypto; it leads the rest. Alts and memes move as leveraged BTC.

### Bitcoin halving
aka: halving, halvening, block reward, 2024 halving, 2028 halving
What: every 210,000 blocks (about 4 years) the mining reward halves. April 2024: 6.25 → 3.125 BTC per block; the next is expected around 2028.
Trap: past halvings preceded big bull runs, but with 4 data points this is a story, not a statistic. Supply cuts are known in advance.

### Four-year cycle
aka: crypto cycle, bitcoin cycle, 4 year cycle, bull market, bear market, cycle top, cycle bottom
What: past BTC cycles (2013, 2017, 2021) peaked roughly 12–18 months after a halving, then fell 75–85%. Too few cycles to rely on; ETFs and macro liquidity may change the pattern.
More: regimes-and-cycles.md §5.

### Mining, hashrate and difficulty
aka: mining, miners, hashrate, hash rate, difficulty, difficulty adjustment, miner capitulation, hash ribbons, puell multiple
What: miners secure the network; hashrate = total computing power; difficulty adjusts every 2,016 blocks to keep 10-minute blocks. Hash ribbons (30- vs 60-day hashrate averages) flag miner capitulation; Puell multiple = daily issuance value ÷ its 1-year average. Slow, cycle-scale signals; useless for day trading.

### Ethereum
aka: ethereum, eth, ether, the merge, proof of stake, eip-1559, gas, smart contracts
What: the main smart-contract chain. Proof of stake since The Merge (Sept 2022); EIP-1559 (2021) burns part of every fee. Gas = the fee for computation. ETH/BTC is the standard gauge of risk appetite beyond Bitcoin.

### Solana
aka: solana, sol
What: a fast, low-fee chain and the home of most memecoin trading (pump.fun, Raydium, Jupiter). Had several network outages in 2021–2023. SOL is high-beta to BTC.

### Altcoins
aka: altcoin, alts, alt season, altseason, total2, total3, alt rotation
What: everything except BTC. Usually 1.5–3× BTC's moves (memes 4–10×). "Alt season" = alts outperforming BTC, typically late in a bull run when BTC dominance falls. TOTAL2/TOTAL3 = crypto market cap excluding BTC (and ETH).
More: altcoins-and-memecoins.md.

### Bitcoin dominance
aka: btc dominance, btc.d, dominance, eth btc ratio, ethbtc
What: BTC's share of total crypto market cap. Rising = money hiding in BTC (risk-off within crypto); falling with rising prices = alt rotation.

### Stablecoins
aka: stablecoin, usdt, tether, usdc, circle, dai, stablecoin supply, depeg
What: tokens pegged to $1. Growing stablecoin supply = dry powder entering crypto. Depegs happen (UST collapsed in May 2022; USDC briefly depegged in March 2023).
Canada: some stablecoins (notably USDT) are restricted on Canadian-registered platforms; check what yours lists.

### Spot vs perpetual futures
aka: spot, perps, perpetual, perpetual swap, futures, derivatives, leverage, margin
What: spot = you own the coin. Perps = leveraged contracts with no expiry, kept near spot by funding payments. Leverage multiplies gains and losses and adds liquidation.
Jarvus: spot only, no leverage; offshore perps are not available to Canadian retail. Perps data is used as information.
More: execution-and-order-types.md §5.

### Funding rate
aka: funding, funding rate, negative funding, positive funding, funding flip
What: periodic payment between perp longs and shorts (commonly every 8 hours; some venues hourly). Positive = longs pay (crowded long); negative = shorts pay (crowded short). Extreme funding warns of a squeeze against the crowd.
More: crypto-market-data.md §1.

### Open interest
aka: open interest, oi, oi spike, rising oi
What: total open derivative contracts. Price up + OI up = new longs (fuel for both continuation and liquidation); price up + OI down = shorts covering. Big OI with flat price = a coiled spring.
More: crypto-market-data.md §2.

### Liquidations
aka: liquidation, liquidations, liquidation cascade, long squeeze, short squeeze, liquidation map, liquidation heatmap, rekt
What: forced closing of leveraged positions. Cascades create the long wicks crypto is known for. Heatmaps estimate where liquidations cluster (estimates, not facts).
More: crypto-market-data.md §3.

### Basis and the futures premium
aka: basis, futures premium, contango, backwardation, cash and carry, annualized basis
What: futures price − spot price. High positive basis = leveraged bullish demand; negative = fear. Cash-and-carry traders capture it market-neutral.

### Long/short ratio
aka: long short ratio, l/s ratio, top trader ratio
What: share of accounts (or positions) long vs short on a venue. A crowding gauge, not a direction signal; it differs by venue and by account vs position.

### Options and implied volatility
aka: options, crypto options, deribit, implied volatility, iv, dvol, max pain, put call ratio, skew, options expiry
What: Deribit dominates crypto options. DVOL = BTC implied volatility index. Big monthly/quarterly expiries (last Friday, 08:00 UTC) can pin or release price. "Max pain" is a popular but weak idea.

### Bitcoin ETFs
aka: etf, bitcoin etf, spot etf, etf flows, ibit, gbtc, ethereum etf
What: US spot Bitcoin ETFs began trading in January 2024, spot Ether ETFs in July 2024 (Canada had spot BTC ETFs from 2021). Daily net flows are watched as institutional demand; they report after the US close, so they describe yesterday.

### CME futures and gaps
aka: cme, cme futures, cme gap, cme bitcoin futures
What: regulated BTC/ETH futures in Chicago, historically closed on weekends, so their charts show weekend "gaps". Check current trading hours; "every gap fills" is folklore.

### Coinbase premium and regional premiums
aka: coinbase premium, kimchi premium, premium index, us premium
What: BTC price on Coinbase (US buyers) minus Binance (global), or Korean exchanges minus global (kimchi premium). A positive Coinbase premium = US demand. Information only.

### On-chain metrics
aka: on chain, onchain, mvrv, mvrv z score, sopr, nupl, realized price, realized cap, exchange flows, exchange netflow, exchange reserves, whale wallets, long term holders, lth, sth, glassnode, cryptoquant
What: blockchain-derived data. MVRV = market cap ÷ realized cap (high = holders in big profit, cycle-top territory); SOPR = profit ratio of coins moved; NUPL = unrealized profit; realized price = average cost basis; exchange inflows = potential selling.
Use: cycle-scale context (weeks to months). Too slow and too revised for intraday trading.

### Cycle-top and bottom indicators
aka: pi cycle top, pi cycle, 200 week moving average, rainbow chart, stock to flow, s2f, golden ratio multiplier, mayer multiple
What: Pi Cycle (111-day MA vs 2× 350-day MA), 200-week MA (historically near cycle lows), Mayer multiple (price ÷ 200-day MA), the Rainbow chart (a meme), stock-to-flow (its 2021 predictions failed badly). Few cycles = heavy curve-fitting risk.

### Macro drivers
aka: macro, fed, fomc, interest rates, cpi, inflation, nfp, jobs report, dxy, dollar, liquidity, m2, rate cuts, nasdaq correlation
What: crypto trades as a risk asset: easier money (rate cuts, rising liquidity, weaker dollar) tends to help, tightening hurts. CPI, FOMC and jobs reports move it within minutes.
Jarvus: no new trade 30 minutes either side of a tier-1 event (`scripts/events.py`).
More: crypto-market-data.md §8–9.

### Trading sessions and the crypto clock
aka: sessions, asia session, london session, new york session, ny open, us open, weekend, daily close, weekly close, monday
What: crypto runs 24/7 but volume follows Asia → London → New York; the London–New York overlap (about 7:30–10:00 AM MT) is busiest. Weekends are thinner; the daily close is 00:00 UTC (6 PM MDT / 5 PM MST).
Jarvus: no new majors trades on weekends (measured zero edge).

### Tokenomics, unlocks and FDV
aka: tokenomics, token unlock, unlock, vesting, fdv, fully diluted valuation, circulating supply, emissions, inflation, market cap
What: market cap = price × circulating supply; FDV = price × total supply. Big unlocks add supply (team/VC tokens) and often weigh on price around the date.
Jarvus: no alt trade with an unlock inside 72 hours.

### DeFi, DEXes and AMMs
aka: defi, dex, amm, uniswap, raydium, jupiter, liquidity pool, lp, impermanent loss, yield farming, staking, liquid staking, restaking
What: on-chain exchanges where trades price against a pool (x·y = k). Liquidity providers earn fees but suffer impermanent loss when prices move. Staking earns protocol rewards with lock-up and slashing risk.
Risk: smart-contract bugs, hacks, oracle attacks, bridge exploits.

### MEV and sandwich attacks
aka: mev, sandwich, sandwich attack, frontrun, front running, jito, priority fee
What: bots reorder or wrap your DEX trade to take value from it (buy before you, sell after). Defence: tight slippage limits, MEV-protected routes/RPCs, smaller orders in thin pools.

### Wallets and self-custody
aka: wallet, hot wallet, cold wallet, hardware wallet, seed phrase, private key, phantom, metamask, ledger, not your keys
What: a wallet holds keys, not coins. Seed phrase = the master key: never type it into a website, chat or bot. Hardware wallets keep keys offline. Exchange balances are an IOU (FTX, Nov 2022).
Jarvus: never asks for keys or seed phrases.

### Exchange risk and proof of reserves
aka: exchange risk, counterparty risk, ftx, proof of reserves, por, exchange hack, withdrawals paused
What: a centralized exchange can freeze, fail or be hacked. Proof-of-reserves reports show assets, often not full liabilities. Keep only trading money on an exchange.

### Canada: platforms, rules and tax
aka: canada, canadian, ndax, kraken canada, coinbase canada, wealthsimple, shakepay, newton, csa, ciro, cra, crypto tax canada, capital gains
What: use a platform registered with Canadian securities regulators (the CSA publishes the list). Fees differ a lot: NDAX 0.20%/side; Kraken Pro's entry tier 0.40% maker / 0.80% taker (Sept 2026); Coinbase Advanced higher.
Tax: trading gains are taxable (capital gains, or business income if trading is a business); losses have rules too. Keep records; ask an accountant. Jarvus does not give tax advice.

### Crypto security and scams
aka: scam, phishing, drainer, wallet drainer, approval, revoke, fake airdrop, pig butchering, impersonation, support scam, giveaway scam
What: fake sites and airdrops that ask you to "connect" and sign approvals that drain wallets; DMs from "support"; doubling giveaways; romance/investment scams. Rule: no one legitimate needs your seed phrase; revoke unused token approvals.

### Crypto data sources
aka: data sources, tradingview, coinglass, coingecko, coinmarketcap, dexscreener, birdeye, glassnode, cryptoquant, defillama, laevitas, velo
What: charts (TradingView, exchange UIs), derivatives (Coinglass, Velo, Laevitas), prices/market caps (CoinGecko), DEX pairs (DexScreener, Birdeye), on-chain (Glassnode, CryptoQuant), DeFi (DefiLlama). Free tiers are delayed or limited; quote a source's numbers only when actually seen.
More: crypto-market-data.md §10–11.
