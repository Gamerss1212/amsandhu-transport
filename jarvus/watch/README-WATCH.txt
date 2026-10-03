JARVUS WATCHER: Jarvus looks at the market all day and alerts you when the rules say BUY.
It uses NO Claude usage. It only reads public prices. It never places an order: you click buy and sell yourself.

SETUP (5 minutes, once)
1. Install Python 3 (free): https://www.python.org/downloads/  (Windows: tick "Add python.exe to PATH").
2. Unzip this folder anywhere.
3. Phone alerts: install the free "ntfy" app. Double-click SETUP-ALERTS-WINDOWS.bat (Mac/Linux:
   ./start-mac-linux.sh setup). It prints a private topic name. In the ntfy app tap +, Subscribe to topic, type it
   exactly. Keep the topic private. Then press a key: you get a test alert on your phone.
4. Double-click START-WINDOWS.bat (Mac/Linux: ./start-mac-linux.sh). Leave the window open (minimise it).

WHAT YOU GET
- A phone + computer alert the moment one of SOL, ETH, BTC, DOGE or BONK turns BUY, with the plan:
    SOL $121.19 → BUY
    Buy (limit) 121.07 · Sell 129.47 · Stop 116.87
    Size $173 · cancel if not filled by Sat 12:00 MT · out by Wed 09:00 MT
  Place that as a LIMIT buy, set the stop, and cancel the order if it has not filled in 3 hours.
- One "Jarvus is alive" message a day, and a warning if it cannot read the market.
- No alert at all most days: the rules only say BUY about 3-5 times a month across the five coins.

KEEP IT RUNNING 24/7
- The computer must stay on and awake, with internet. Windows: Settings > System > Power > Sleep = Never.
- Start with Windows: press Win+R, type shell:startup, put a shortcut to START-WINDOWS.bat in that folder.
- No spare PC? A GitHub Actions version that runs in the cloud is in github-actions-jarvus-watch.yml
  (needs a repository secret named JARVUS_NTFY_TOPIC; see the comments in the file).

CHANGE THE SETTINGS (edit the .bat, add to the last line):
  --account 5000    your balance (sizes the plan)           --fees kraken   if you don't use NDAX
  --coins SOL,BTC   fewer coins                              --every 5       minutes between checks
  --no-heartbeat    no daily "alive" message                 --no-desktop    no pop-up on this computer

PRIVACY: alerts go through the free public ntfy.sh server and contain only the plan (coin, prices, size). Your topic
is the only password: anyone who learns it can read your alerts, so never post it. Prefer Discord? Set the environment
variable JARVUS_WEBHOOK_URL to a Discord webhook URL. Nothing is ever stored about your exchange account.

Educational, not advice. Jarvus's tested edge is small (about 3-5 signals a month, best result +0.2 to +0.5 R per trade
before real-world slippage). An alert is a plan to check, not a guarantee.
