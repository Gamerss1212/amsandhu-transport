ULTRON WATCH: the smarter, fully automatic successor of Jarvus Watch.
It watches the market 24/7 and tells your phone and computer exactly what to do: when to BUY, when to SELL HALF and
move the stop, and when to SELL. It uses NO Claude usage, reads public prices only, and never places an order: you
click buy and sell yourself. No Python needed on Windows.

SETUP (3 minutes, once)
1. Unzip this folder anywhere (for example Desktop\ULTRON-Watch).
2. Phone alerts: install the free "ntfy" app on your phone. Double-click SETUP-ALERTS.bat. It prints a private topic
   name (if you used Jarvus Watch before, it reuses the same topic, so your phone is already set up). In the ntfy app
   tap +, Subscribe to topic, type it exactly. Press a key: you get a test alert.
3. Right-click START-WATCH.bat -> Edit, change 1000 to your account size, save. Double-click START-WATCH.bat.
   Leave the window open (minimise it). If Windows SmartScreen warns: More info -> Run anyway.

WHAT IT WATCHES (only setups that held up on unseen data since Dec 2025)
- Every hour: 50 trained AI agents (1h and 4h crypto councils) on BTC, ETH, SOL, DOGE, SHIB, PEPE, BONK, WIF, FLOKI.
- Once a day after the close: the daily markets council on SPY, QQQ, IWM, DIA, AAPL, MSFT, NVDA, AMZN, GOOGL, META,
  TSLA, JPM, AMD, NFLX, XIU, RY, TD, ENB, SHOP, CNQ, EURUSD, GBPUSD, USDJPY, USDCAD, AUDUSD, GLD, SLV, USO.
- Radar: "VERY LOUD" alerts when a big move is very likely in the next 12 hours on BTC, ETH or SOL (right about
  9 in 10 times on unseen data; direction unknown). --radar all for every coin, --radar off to switch it off.

WHAT AN ALERT LOOKS LIKE
  ULTRON BUY SOL (1h crypto)
  Buy (limit) 121.07 · sell half at 122.07, rest at 129.07 · stop 117.07
  Size $180 (1.49 SOL) · cancel if not filled by Sat 12:00 MT
Then, for the same trade:  "ULTRON SELL HALF SOL: first target hit, stop now at breakeven 121.6"
and finally:               "ULTRON SELL SOL: target hit / stop-loss hit / breakeven stop / time limit reached".
Place the buy as a LIMIT order and set the stop. Cancel it if it has not filled by the time shown.

TESTED RESULTS (paper, after fees, untouched test since Dec 2025)
  1h crypto (sell half at 0.5R, rest 2R)   about 7 in 10 trades closed in profit
  4h crypto (sell all at 2R)               fewer, bigger wins
  daily markets (sell all at 0.5R)         about 8 in 10 trades closed in profit
  Past results, not a promise. Most days there is no alert; that is the system being selective.

KEEP IT RUNNING 24/7
- The computer must stay on and awake, with internet: Settings > System > Power > Sleep = Never.
- Start with Windows: press Win+R, type shell:startup, put a shortcut to START-WATCH.bat in that folder.
- No spare PC? github-actions-ultron-watch.yml runs it in the free GitHub cloud (see the comments in the file).

COMMANDS (in a terminal in this folder)
  UltronWatch.exe status     what it is watching and the open plans
  UltronWatch.exe run --account 5000 --fees kraken --radar all --no-desktop --no-heartbeat
Mac/Linux: from the project folder,  python3 ultron/watch/ultron_watch.py run --account 1000   (needs: pip install numpy)

PRIVACY: alerts go through the free public ntfy.sh server and contain only the plan (symbol, prices, size). Your topic
is the only password: never post it. Prefer Discord? Set the environment variable JARVUS_WEBHOOK_URL to a Discord
webhook URL. Nothing about your exchange account is ever stored or needed.

Educational, not advice. An alert is a plan to check, not a guarantee.
