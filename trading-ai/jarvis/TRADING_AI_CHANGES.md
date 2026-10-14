# Changes made for the Trading AI

Upstream: <https://github.com/adewaskar/jarvis> (MIT, see `LICENSE`), commit `1c4016a`. Everything else is unchanged.

* `bridge/trading.mjs` (new): twelve read tools (`get_trading_*`; GET only, allowlisted paths, read token) and one
  acting tool, `ask_trading_ai` (seven allowlisted actions, command token). The link file is `../data/jarvis-link.json`
  (override with `JARVIS_TRADING_LINK`). Local addresses only. The Trading AI decides what runs and what waits.
* `bridge/trading.mjs` also relays the Trading AI's own "voice" announcements (`startAnnouncer`), and every request
  carries a command ID. `src/lib/bridge.ts`, `src/lib/brain.ts`, `src/App.tsx`: an `announce` frame, written to the
  transcript and spoken only while JARVIS is resting.
* `bridge/server.mjs`: registers that server; treats it as read-only in `decideTool`; adds a short "TRADING AI" section to
  the system prompt (no invented numbers, no promised returns, web text is data); prints whether the link is found and
  warns if writes are enabled.
* 1.8.0: `open_trading_system` opens the Trading AI page (only the address in the link file, this computer only);
  the default model is `claude-opus-5-5`.
* 1.9.0: `?autostart=1` powers on by itself when the browser allows sound without a click (`open_face.cmd` opens
  Chrome or Edge that way); a spoken greeting built from `/api/desk`; `get_trading_desk` reads the whole desk at once.
* 1.9.0 (owner's request): `bridge/self.mjs` (check_my_code, undo_my_last_change, list_my_changes, restart_myself,
  remember, recall, forget); `bridge/server.mjs` lets JARVIS edit his own folder when `JARVIS_SELF_EDIT=1` (backed up
  first) and, with `JARVIS_ASK_FIRST=1`, shows every other action on screen for Allow / Deny (`src/ui/Confirm.tsx`).
* 1.9.1: `@anthropic-ai/claude-agent-sdk` 0.3.220 -> 0.3.287 (the old bundled engine refused the model, so no question
  was answered); `touchesTradingAI` in `bridge/self.mjs` refuses, before any other rule, file changes and commands aimed
  at the Trading AI folder; the prompt names his own folder's full path and steers reading to Read/Grep; the greeting
  is spoken even when the Trading AI is off, and waits until the screen has powered up; the "May I?" card takes the
  screen's current colour.
* 1.9.2: `open_trading_system` says "opened" only when the browser launcher really started (it used to claim success
  when none existed); status questions use one `get_trading_desk` call; `bridge/safety.test.mjs` (`npm run test:bridge`)
  checks the safety rules and runs on real Windows in CI; `open_face.cmd` waits for the screen server instead of a fixed
  12 seconds.
* No other file was changed. `npm run setup`, `npm start` and every upstream option work as before.
