# Knowledge base: meme coins

One entry per `### `. Jarvus's backtested meme rules are in SKILL.md; the hard-fail screening list is in
`assets/memecoin-screening-rules.json`; the deep reference is `handbook-memecoins.md`.

### What a memecoin is
aka: memecoin, meme coin, memes, meme token, shitcoin, degen
What: a token whose value is attention and community, with no cash flows. Two worlds: listed memes on big exchanges (DOGE, SHIB, PEPE, BONK, WIF, FLOKI) and fresh on-chain launches (minutes to days old).
Odds: most launches go to near zero; a few go up 100×. Survivorship makes the winners look common.

### Jarvus's meme rules
aka: meme rules, can i trade memes, meme risk
What: listed memes only through the scripts: BTC above its 200-day average and BTC's 4h trend up; volatility gate LOUD (or NORMAL when P7 4h momentum fired, risk 0.5%); not 7 PM–midnight MT; risk 0.3% per trade; at most 2 open. Backtested 2021–2026 at NDAX fees: v6.1 +0.19R per trade, v7 (with P7) +0.33R; P7 was picked from the same history, so treat it as promising, not proven.
Fresh launches: the hard-fail list must pass first (`python3 scripts/know.py "meme sleeve" --full`).

### Meme coin lifecycle
aka: launch phases, meme lifecycle, how memecoins pump, pump and dump
What: launch → snipers and insiders buy first → early buyers and callers push it → peak attention (often within hours or days) → insiders sell into late buyers → slow bleed. The few survivors build a community and list on exchanges.
Trap: by the time it trends on X or DexScreener, the early sellers are selling to you.

### Pump.fun and bonding curves
aka: pump.fun, pumpfun, bonding curve, graduation, migration, king of the hill, pumpswap, letsbonk, launchpad
What: launchpads where a token starts on a bonding curve (price rises as people buy from the curve). When the curve fills, liquidity migrates to a DEX pool ("graduates"); historically around $69K market cap to Raydium, since 2025 to pump.fun's own PumpSwap. The rules change; check them.
Odds: only a small fraction of launches ever graduate.

### Liquidity and LP burn/lock
aka: liquidity, lp, lp burned, lp locked, liquidity pool, rug pull liquidity, pulled liquidity
What: the pool you sell into. If the creator can withdraw it (LP not burned/locked), they can rug. Thin liquidity means your own sell moves the price a lot.
Rule: market cap means nothing if liquidity is tiny; size by the liquidity you can exit into.

### Mint and freeze authority
aka: mint authority, freeze authority, revoke authority, renounced, ownership renounced, can mint
What: on Solana, an un-revoked mint authority can print more tokens; a freeze authority can freeze your tokens. On EVM chains the equivalent is an owner who can change the contract.
Rule: either still active = hard fail.

### Honeypots and taxes
aka: honeypot, cant sell, sell tax, buy tax, transfer tax, blacklist, max wallet, trading disabled
What: contracts that let you buy but not sell, charge huge sell taxes, blacklist wallets or can switch trading off. Mostly EVM tokens. A tiny test sell before sizing up is the only real proof.

### Holder concentration and bundles
aka: holders, top holders, top 10 holders, holder distribution, bundle, bundled, bundlers, snipers, insiders, dev wallet, dev sold, bubble maps, bubblemaps, clusters
What: if a few wallets (often the same person, "bundled" at launch) hold a big share, they can dump on you. Bubble Maps-style tools cluster linked wallets. Addresses are not people: 1,000 holders can be 10 people.
Rule: unresolved clustering or a top-10 share that dominates supply = fail.

### Rug pulls
aka: rug, rug pull, rugged, hard rug, soft rug, slow rug, exit scam
What: hard rug = liquidity pulled or unlimited mint; soft rug = team/insiders sell everything; slow rug = continuous selling while promoting. Hard rugs end in seconds; there is no stop-loss for them.

### Volume and attention can be faked
aka: fake volume, wash trading, volume bots, dexscreener trending, boosts, paid trending, kol, influencer, callers, shill, telegram calls, x calls
What: bots trade with themselves to fake volume; trending spots and "boosts" are paid; callers/KOLs often hold before they post. Social hype is data about attention, never a reason to buy.

### Community takeover (CTO)
aka: cto, community takeover, dead coin revival
What: the community re-launches marketing after the original developer abandons a token. Some revive; most do not. Same hard-fail checks apply.

### Slippage and price impact
aka: slippage, price impact, slippage tolerance, high slippage
What: price impact = how much your order moves a thin pool; slippage tolerance = the worst price you accept. Wide tolerance invites sandwich bots. In tiny pools, a round trip can cost 5–20%.

### Trading bots on Telegram and web
aka: telegram bot, trading bot, photon, bullx, trojan, maestro, banana gun, axiom, gmgn, sniper bot, copy trading wallets
What: fast-execution tools for memes. Many hold your private key (custodial risk) and have been exploited. Never import your main wallet; Jarvus never asks for keys.

### Copy trading wallets
aka: copy trade, smart money wallets, wallet tracking, alpha wallets, follow wallets
What: following "smart" wallets. You buy after them (worse price), they may be decoys or bots, and past winners are survivors. Treat as attention data, not a strategy.

### Narratives and metas
aka: narrative, meta, ai memes, cat coins, dog coins, political memes, celebrity tokens, rotation
What: memes move in themes (dogs, cats, AI agents, political/celebrity tokens). Themes rotate fast; the first and biggest name in a theme usually holds best. Celebrity and political tokens have been notably extractive for late buyers.

### Listed memes vs new launches
aka: doge, dogecoin, shib, shiba inu, pepe, bonk, wif, dogwifhat, floki, trump coin, fartcoin, popcat, mog
What: listed memes trade on regulated exchanges with real liquidity and can be backtested; Jarvus's meme results come from these (DOGE, SHIB, PEPE, BONK, WIF, FLOKI). New launches have none of that history and an exit that can vanish.

### Meme position sizing
aka: meme size, how much to put in memes, meme bankroll, lottery ticket
What: size for a total loss. Jarvus: 0.3% risk per listed-meme trade with a stop, at most 2 open; fresh launches only from a separate "can lose it all" amount, and only after the hard-fail list passes.
