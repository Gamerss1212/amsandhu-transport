# Real money (Phase 8): how it works and how to switch it on

Real money is **off** when you unzip QuantAgents. It stays off until you do every step below
yourself. Nothing in the program, and no Claude session, can switch it on for you.

## Read this first

- **No strategy has passed the tests.** The research so far says "no edge found", so expect the
  real account to do about as well as the paper account, minus extra fees, or worse. You can
  lose the money you put in.
- **The real-money part was tested against a fake exchange, not a real account.** There are 23
  automated tests, but no real Kraken account was used to build it, because no keys were ever
  shared. So the first steps are tiny on purpose: a preview, then a test order, then a small
  budget.
- **Crypto only, on Kraken.** Write symbols like `BTC-CAD.KRAKEN`. Stocks and ETFs cannot trade
  for real here:
  - Interactive Brokers blocks API orders on Canadian-listed products.
  - Questrade's API gives retail accounts data only.
- **Paper first.** Run the crypto folder on paper for 30 clean days before you start (Phase 3).
  Phase 8 then asks for 60 days and 50 trades at a tiny size, with zero risk-limit breaches,
  before any bigger amount.
- Not financial advice. The decision to use real money is yours.

## How it works

The paper account still decides everything:
1. The agents vote.
2. A49 (the risk governor) sizes and limits every order.
3. The paper account records the result.

The **real-money mirror** then copies the paper portfolio onto Kraken, as percentages of your
budget.

**Example:** the paper account holds 12% in BTC, and your budget (`live.budget`) is 200 CAD.
The mirror then buys about 24 CAD of BTC. When the paper account sells, the mirror sells too.

It runs inside the daily run, after the paper cycle and the watchdog. If any step before it
failed, it does not run.

### Its safety rules (in code; each one can only shrink, skip or cancel an order)

- **Checks first.** Before anything else, it compares its own ledger with your Kraken balances.
  If Kraken holds less than the ledger says, the kill switch engages.
- **Sells before it buys.** It sells only coins the mirror bought itself, so coins you already
  own are never touched. It never shorts and never borrows.
- **Limit orders only.**
  - A buy is priced at most 0.5% above the ask; a sell at most 0.5% below the bid.
  - Each order is at most `live.max_order_value`.
  - Whatever has not filled after 60 seconds is cancelled.
- **Checks before each buy.** A buy needs free cash, and the Kraken price within 5% of the
  paper price.
- **Errors stop everything.** Any error engages the kill switch and sends you an alert, if
  Telegram is set up.
- **One run at a time.** If you click "Run today" while the scheduled run is going, the
  second one does nothing, so it can never buy twice.
- **It never moves money off Kraken.** There is no withdraw or transfer call anywhere in the
  program (a test checks this).
- **Keys stay secret.** They are read only from your `.env` file and are hidden from every
  message and log.

### What it does not do

- **No stop orders on Kraken.** It follows the paper account's stops at the next daily run,
  so an exit can come up to a day late.
- **No trading during the day.** It runs once a day.
- **Different prices from paper.** Paper fills at the next day's open; the mirror trades right
  after the cycle at Kraken's price, so results will differ.
- **Very small budgets do little.** Positions smaller than Kraken's minimum order, or smaller
  than `live.min_order_value` (10), are skipped. Under about 100 CAD, most of them will be.

### What to expect

- **Long stretches in cash.** With only two coins (BTC and ETH), two agent teams rarely agree,
  so the paper account often holds nothing. Then the mirror holds nothing too.
  - Example, on live Kraken data on 2026-10-06: the trend agent leaned long on both coins, but
    the second team needed for a GO did not agree, so there was no trade.
- **The dashboard shows what matters:** the scoreboard compares the paper account with simply
  holding the same coins. If paper stays behind, real money copying it will too.

## Switch it on: 5 steps, all done by you, all on the QuantAgents page

1. **A crypto folder on paper.**
   - Unzip a second copy of QuantAgents, for example to `C:\QuantAgents-Crypto`, and
     double-click its `QuantAgents.bat`.
   - In **Your symbols**, press **Use: Crypto on Kraken, in CAD**.
   - Press **Turn ON** for the automatic daily run, and let it paper-trade for 30 days.
2. **A Kraken account.**
   - Get it verified and turn on two-factor login.
   - Deposit a small amount of CAD.
3. **A trade-only API key.** On Kraken, go to Settings, then API, then create a key.
   - **Turn on only:**
     - Query Funds
     - Query Open Orders & Trades
     - Query Closed Orders & Trades
     - Create & Modify Orders
     - Cancel/Close Orders
   - **Leave everything else off, above all Withdraw Funds.**
   - If Kraken names these differently, the rule is the same: read balances and orders, place
     and cancel orders, nothing else.
   - Add your IP address to the key's allow-list if you can.
4. **Real money box, step 1: Save keys.**
   - Paste the API key and the private key into the two boxes, and press **Save keys**.
   - They go into the `.env` file in that folder and are never shown again.
   - Never paste keys into a chat, an email or a screenshot.
5. **Real money box, step 2: switch it on.** Type:
   - a **budget**: the most it may invest (at most 1,000 here; start with about 100);
   - **your name**;
   - the **approval phrase** the page shows.

   Then press **Switch real money ON**. QuantAgents then:
   - writes the live settings into your settings file;
   - puts the phrase in `.env`;
   - adds a dated row with your name to `docs\STATUS.md`.

   Nothing switches on without your typed phrase.

**Then check it (Real money box, step 3):**
- **Check (reads your Kraken balance):** every gate should say ok, and it shows your free CAD,
  which proves the keys work.
- **Preview real orders:** what it would buy or sell today. Nothing is sent.
- **Send a tiny test order** (type YES first): the smallest buy Kraken accepts, priced 20% under
  the market so it does not fill, then cancelled at once.

From then on, every automatic daily run ends with a step that copies the paper portfolio to
Kraken.

## Every day

- The page's **Real money** box shows what the mirror holds, how many real
  fills it has made, and any unsettled orders.
- `runs\daily.log` shows each real order.
- `state\live_ledger.json` lists every real fill. Back it up. In Canada, every crypto sale is a
  taxable event. Keep this file and Kraken's own trade export for your taxes.
- **Optional phone alerts:**
  1. Make a Telegram bot with @BotFather.
  2. Put `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`.
  3. You will then get a message for every real fill, every halt, and whenever the account
     has used 75% or more of a loss limit (daily, weekly or drawdown).

## When it stops itself

The kill switch engages on any of these:
- a reconciliation break (Kraken holds less than the ledger);
- any error while trading;
- the watchdog finding stale data or a missed run;
- A49 halting the paper cycle.

**To resume:**
1. Open the Kraken website. Check your open orders and balances.
2. Read the end of `runs\daily.log`.
3. Fix the cause.
4. In the **Stop or resume** box, type the reset phrase and press Resume.

## Updating to a new version

- Use **Bring it over** in the new folder's Tools box. It brings the account and the real-money ledger
  over, then stops the old folder (its kill switch is engaged).
  - Two copies running at once would both buy on the same Kraken account.
- **Your approval is not copied.** Switch real money on again in the new folder's page
  (Real money box, step 2) after reading what changed.

## Switch it off

- **Fastest:** the red **STOP** button stops all new trading, paper and real.
- **Back to paper:** **Switch real money OFF** in the Real money box. It removes the live
  settings and the phrase.
  - Your keys stay saved; delete the key on Kraken to stop it working for good.
  - The coins the mirror bought stay on Kraken as they are. Sell them on the Kraken website
    if you want cash.
