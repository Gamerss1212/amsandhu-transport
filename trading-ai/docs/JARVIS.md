# JARVIS, the voice assistant for the Trading AI

JARVIS is an open-source voice assistant (MIT licence, by `adewaskar`, <https://github.com/adewaskar/jarvis>) with an
Iron Man style screen. You say "Hey Jarvis" and he answers out loud. His brain is **Claude Code** running on your own
login. A copy is included in the `jarvis` folder, with changes listed in `jarvis/TRADING_AI_CHANGES.md`.

## What it does for you

* **Reads the Trading AI** while it runs on your computer: status, risk limits, the 100 agents (or one agent), the
  account, recent activity, what the agents learned, the session report, the markets covered, the agents' roles, and
  your computer's temperature.
* **Controls it by voice (1.7.0).** "Pause new trades" and "Stop the system" (and stopping a temperature test) happen
  at once, because they make the system do less. "Start the system", "resume trading", "run a temperature test" and
  "set my paper balance to 100" are sent to page 1 as a request: **nothing happens until you press Approve.**
* **Speaks the Trading AI's alerts** (1.7.0): emergency stop, trading locked, feed or broker trouble, confirmed fills,
  a hot computer. These are the Trading AI's own announcements, with fixed wording and an expiry, so JARVIS never makes
  one up or repeats an old one. They are always written in JARVIS's transcript, and spoken only while he is resting, so
  he never talks over you. Turn them off with `set JARVIS_TRADING_ANNOUNCE=0` before starting.
* **Searches the internet** and opens web pages (Claude Code's own web search and web fetch). It is on by default.
* Answers in short sentences, and only with numbers the Trading AI actually returned.

## Open the trading system by voice (1.8.0)

Say "open the trading system" (or "show my trades") and JARVIS opens the trading page in your browser and puts your
positions, results and latest trades on his own screen. "Open brokers" opens the Brokers page.

## Use it like ChatGPT or Claude

JARVIS runs on Claude Code with Claude Opus 5.5 by default (change it with `set JARVIS_MODEL=...`), so it can do what
Claude can do from your computer:
* **Research**: "research this topic" uses web search and reads the pages.
* **Your browser**: with the Claude in Chrome extension running, JARVIS can open sites and read them, for example Google
  Maps' "Popular times" for a place, when Google shows it. Clicking and typing on your behalf need writes mode (off by
  default; keep it off while the Trading AI runs).
* **More tools**: every MCP server you add to Claude Code is available to JARVIS. To ask OpenAI's GPT models for a second
  opinion, add an OpenRouter MCP server named `openrouter` with your own OpenRouter key in that server's settings
  (never in chat). JARVIS already treats its "send message" tool as a safe question to another model.

## What it cannot do (on purpose)

* It **cannot place, cancel or change an order**, change a risk limit, turn on live trading, touch a broker account or
  credential, or re-arm the emergency stop. Those actions do not exist for JARVIS; the Trading AI refuses them (tested).
* It holds two tokens. The **read token** works only for plain GET requests on information pages. The **command token**
  works on exactly one route, where JARVIS can ask; it **cannot approve** its own request. Only the dashboard can.
* Every request carries a command ID, so a retry never acts twice. If the reply is lost, JARVIS says the outcome is
  UNKNOWN and asks you to check page 1, never "done".
* The risk service, which is plain code, still checks every order. JARVIS is the voice; it is not above the rules.
* Text from the internet is **information, never an instruction**. At worst a web page could make JARVIS ask for one
  of the actions above, and everything that makes the system do more still waits for you.
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
