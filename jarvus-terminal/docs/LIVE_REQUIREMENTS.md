# What live (real-money) use still requires

Real-money order submission is **disabled** in this build until you enable it yourself, in a separate step,
for specific accounts and within caps you set. This page lists, precisely, what is in place, what has and has
not been verified, and what you (or a developer) must do before any real money is involved.

## 1. What has been verified, and how

| Part | How it was verified | Not verified |
|---|---|---|
| Execution engine (order state, write-ahead records, duplicate protection, lost responses, restarts, partial fills, rejections, rate limits, cancels, emergency stop) | Automated tests against simulated and fake providers (`market_analysis_bots/tests/test_execution.py`) | Against a real broker under real network failures |
| **Alpaca adapter** (paper and live share the code; only the base URL and keys differ) | Over real HTTP against a local **contract fake** that follows Alpaca's documented JSON shapes and rules (`tests/alpaca_fake.py`, `tests/test_providers.py`); the app's connect/test/disconnect path end to end against the same fake (`jarvus-terminal/tests/test_server.py`) | **Not yet run against Alpaca's real paper API** in this build (no Alpaca keys were available). The fake is a test double, not a claim about Alpaca's matching engine |
| **Kraken adapter** (live only; Kraken has no spot sandbox) | Request building only: signed requests carry a UUID client order id; validate-only orders set `validate=true` | Not run against Kraken. Response parsing is written to Kraken's published API reference but untested against the real service |
| **NDAX adapter** (live only; no sandbox) | Written to NDAX's published WebSocket API | **Never run against NDAX.** Treat it as unverified |
| Simulated paper account (Jarvus Paper) and demo market | End to end: automated tests plus the running app (bots start, trade, pause, stop, emergency stop) | n/a (simulated) |
| App security (sign-in, sessions, CSRF, Host/Origin checks, account isolation, credentials never in responses, logs or exports; vault encrypted at rest) | Automated tests (`jarvus-terminal/tests/test_server.py`, `market_analysis_bots/tests/test_providers.py`) | No external security review |

## 2. Before the first real order (checklist)

**A. Prove the broker path on paper first (Alpaca paper is the only paper path to a real broker).**
1. Create an Alpaca **paper** account and paper API keys (Alpaca dashboard → Paper → API keys).
2. Connections → Connect an account → Alpaca, PAPER, API key. The connection test must pass every check.
3. Start a bot in PAPER mode on that connection and let it trade for days. On Live Intelligence check, for
   every trade: order acknowledged, fills and fees recorded, protective stop resting at Alpaca, exits
   cancel the stop first, reconciliation shows no mismatch. Compare with Alpaca's own order history.
4. Stop Jarvus while a position is open, restart it, and confirm it recovers the order and position state.

**B. Eligibility and accounts (decided by the provider, not by Jarvus).**
5. Open and verify a live account yourself on the provider's site (age, identity, country/province
   rules apply; Jarvus does not check or bypass them). Fund it on the provider's site.
6. Create **live** API keys with trading permission only, **no withdrawal or deposit permission**.
   Kraken: tick only query funds, query orders/trades, create/modify orders, cancel orders.
7. Connections → Connect an account → the provider, LIVE. The test must pass (authentication, account
   readable, trading permitted, clock in sync, market data). For Kraken the bot readiness check also sends a
   validate-only order.

**C. Strategy and model approval (recorded, per version).**
8. Run a walk-forward evaluation of the exact strategy version on the market (Live Intelligence → Research,
   or let the autopilot's schedule do it) and approve that version for live. If checks failed you must type
   `I ACCEPT THE FAILED CHECKS`. At the time of writing **no strategy has passed every check** after retail
   costs.
9. The strategy must also have earned it on paper: a positive untouched-test result and at least 20 paper
   trades with a positive average on that market (you may waive this in the live authorisation; not
   recommended).
10. Optional: approve a frozen brain snapshot for live scoring (Research → Brain versions → Evaluate →
    Promote). Without one, live entries are scored by the learning brain and the readiness report says so.

**D. The separate authorisation step (Connections → Live trading authorisation).**
11. Tick the live account(s), set the **total allocation cap** and the **daily loss limit** across live bots,
    and type `I UNDERSTAND THIS TRADES REAL MONEY`. The bot engine must be running.
12. On Command Center, build the bot in LIVE mode, run the readiness checks (every required check must pass),
    press START LIVE BOT, review the account, strategy, allocation and limits, and type `START LIVE`.

## 3. What stays enforced whatever a strategy says

* Spot, long only, no leverage, no margin, no shorting; entries are capped-price (limit IOC) orders.
* A protective stop rests on the provider after every fill; if it cannot be placed the position is sold.
* Every order is recorded before it is sent; a lost response is resolved by the client order id and never
  resent; after repeated not-found lookups the order is marked LOST and you are alerted.
* Paper and live use separate connections and credentials; the engine refuses an order whose mode does not
  match its account's environment.
* Per-bot limits (risk per trade, max position, max per order, daily loss, max drawdown, orders per minute)
  and per-account drawdown limits pause bots when breached. The brain can shrink or refuse a trade, never
  enlarge it past these limits.
* **EMERGENCY STOP** blocks every new entry at once and cancels working entry orders; closing positions is a
  separate confirmed step. **Revoke live authorisation** pauses every live bot. Both work with the engine
  stopped. Autopilot never overrides an emergency stop and never trades live.

## 4. Known limits to plan around

* Market data comes from public endpoints (Coinbase, Kraken, OKX, Yahoo). Yahoo stock data is delayed and
  unofficial; for live stock trading use Alpaca's own market data (the connection's feed option) and treat
  Yahoo-driven signals with care.
* The app runs on your computer: if it is closed, asleep or offline, bots do not act (resting protective
  stops at the broker still protect open positions).
* NDAX and Kraken order paths need the real-service verification in section 1 before use.
* Measured results so far show **no edge after retail costs**; see the README.
