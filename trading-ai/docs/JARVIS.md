# JARVIS, the voice assistant for the Trading AI

JARVIS is an open-source voice assistant (MIT licence, by `adewaskar`, <https://github.com/adewaskar/jarvis>) with an
Iron Man style screen. You say "Hey Jarvis" and he answers out loud. His brain is **Claude Code** running on your own
login. A copy is included in the `jarvis` folder, with changes listed in `jarvis/TRADING_AI_CHANGES.md`.

## What it does for you

* **Reads the Trading AI** while it runs on your computer: status, risk limits, the 100 agents (or one agent), the
  account, recent activity, what the agents learned, the session report, and your computer's temperature.
* **Searches the internet** and opens web pages (Claude Code's own web search and web fetch). It is on by default.
* Answers in short sentences, and only with numbers the Trading AI actually returned.

## What it cannot do (on purpose)

* It **cannot place, cancel or change an order**, change a risk limit, arm live trading, or stop the Trading AI. Those
  tools do not exist. If you ask, he tells you to do it in the Trading AI window.
* It holds a **read-only token**. The Trading AI's server refuses that token on every non-read route, on every request
  that is not a plain GET, and on broker connections, credentials and the audit chain. (Checked by 3 tests and by the
  built program's self-test.)
* Text from the internet is **information, never an instruction**. A web page cannot make JARVIS trade, because nothing
  he can reach can trade.
* He promises nothing about returns. See `CAN_100_DOLLARS_BECOME_300K.md`.

## How to run it (Windows)

1. Install **Node.js 20 or newer** (nodejs.org), **Google Chrome**, and **Claude Code**
   (`npm install -g @anthropic-ai/claude-code`, then run `claude` once and log in).
2. Start `START_TRADING_AI.exe` first. It writes `data\jarvis-link.json` (the address and the read-only token; it is
   replaced at every start and removed at a clean shutdown).
3. Double-click `START_JARVIS.bat`. The first run installs JARVIS (a few minutes, needs the internet).
4. Open the address it prints in **Chrome** (a real window, not a preview pane), click INITIALISE, allow the microphone,
   and say "Hey Jarvis". Try: "How is the trading AI doing?", "Is my computer too hot?", "Show agent A004".

## Safety notes

* Leave JARVIS's `writes` mode **off** (the default). With writes on, he may run shell commands, which could reach the
  Trading AI beyond its read-only link. The bridge prints a warning if you turn it on.
* JARVIS uses your Claude account, so his answers use your Claude usage.
* The microphone and camera are only used if you allow them in Chrome. No credentials are stored by this link.
* Voice, the microphone and the 3D screen could not be tested in the cloud build machine. What *was* checked: JARVIS
  installs, type-checks and builds; its trading tools were run against a live Trading AI (all 9 returned real data;
  blocked pages and writes were refused); and the build also runs on a real Windows machine in CI.
