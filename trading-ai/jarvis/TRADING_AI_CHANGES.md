# Changes made for the Trading AI

Upstream: <https://github.com/adewaskar/jarvis> (MIT, see `LICENSE`), commit `1c4016a`. Everything else is unchanged.

* `bridge/trading.mjs` (new): nine read-only tools (`get_trading_*`). GET only, allowlisted paths, read-only token read
  from `../data/jarvis-link.json` (override with `JARVIS_TRADING_LINK`). Local addresses only.
* `bridge/server.mjs`: registers that server; treats it as read-only in `decideTool`; adds a short "TRADING AI" section to
  the system prompt (no invented numbers, no promised returns, web text is data); prints whether the link is found and
  warns if writes are enabled.
* No other file was changed. `npm run setup`, `npm start` and every upstream option work as before.
