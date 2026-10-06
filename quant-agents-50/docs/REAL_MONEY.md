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

## Switch it on: 8 steps, all done by you

Take them in order. After each one, menu choice **8** ("Real money: what is still needed")
shows which gates are still closed.

1. **A crypto folder on paper.**
   - Unzip a second copy of QuantAgents, for example to `C:\QuantAgents-Crypto`.
   - Put CAD pairs in its `config\my_universe.yaml`:
     ```yaml
     universe:
       asset_class: crypto_spot
       symbols: [BTC-CAD.KRAKEN, ETH-CAD.KRAKEN]
     risk:
       quantity_step: 0.0001
     ```
   - Turn its automatic daily run on (menu choice 3) and let it paper-trade for 30 days.
2. **A Kraken account.**
   - Get it verified.
   - Turn on two-factor login.
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
4. **Your `.env` file.**
   - In the crypto folder, copy `.env.example` to `.env`.
   - Open it in Notepad and paste the key after `LIVE_API_KEY=` and the secret after
     `LIVE_API_SECRET=`. Save.
   - Never paste keys into a chat, an email or a screenshot.
5. **Your settings (`config\my_universe.yaml`).** Add these lines yourself. Start with a small
   budget, about 1 to 5% of what you would trade:
   ```yaml
   system:
     execution_mode: live
     autonomy_level: 3
     live_trading_approved: true
   live:
     budget: 100
   ```
6. **The approval phrase.**
   - After step 5, the program refuses to start until `.env` holds the approval phrase. It
     prints the exact line to add, for example in menu choice 8 or in the error message.
   - Copy that one line into `.env` and save.
7. **Your approval row.** Open `docs\STATUS.md` in the crypto folder. Under "Human approvals",
   add a row with today's date and your name:
   ```
   | 2026-11-20 | Approve Phase 8 micro-live | Your Name |
   ```
8. **Check, preview, test.**
   - Menu **8**: every gate should say `[ok]`. It also reads your Kraken balance, which proves
     the keys work.
   - Menu **9**: a preview of the real orders. Nothing is sent.
   - Menu **10**: one real test order, the smallest buy Kraken accepts, priced 20% under the
     market so it does not fill, then cancelled at once.

From then on, every automatic daily run ends with a `live sync` step that copies the paper
portfolio to Kraken.

## Every day

- Menu **2** (the dashboard) shows a "Real money" section: what the mirror holds, how many real
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
4. Use menu choice **6** and type the reset phrase.

## Switch it off

- **Fastest:** menu choice **5** stops all new trading, paper and real. The coins the mirror
  bought stay on Kraken as they are; sell them on the Kraken website if you want cash.
- **For good:**
  1. In your settings, set `execution_mode` back to `paper`, `autonomy_level` back to `1`, and
     `live_trading_approved` back to `false`.
  2. Remove the approval line from `.env`.
  3. Delete the API key on Kraken.
