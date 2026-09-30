# Jarvus architecture

Standard-library Python (no required packages), one SQLite database per workspace, a browser UI served from
`127.0.0.1`. The optional `anthropic` SDK powers the AI research assistant.

## Processes

```
JarvusTerminal.exe / run.py
└── app server (server.py, ThreadingHTTPServer on 127.0.0.1)
    ├── sign-in, sessions, workspaces ............ engine/auth.py  -> data/app.db
    ├── supervisor ................................ engine/supervisor.py
    │   ├── bot engine process per running workspace (mab.runtime.Fleet, spawned)
    │   │     311 research bots (24 in demo) + your own bots, the brain, execution engine,
    │   │     order router, providers, risk; a local control API with a bearer token
    │   └── research pool: worker processes (spawned) with per-job time and memory limits
    └── live event stream (Server-Sent Events) from the workspace's audit log
```

* The app server never trades. It reads the workspace database, forwards commands to the engine's control API
  and streams the audit log. A few safety commands work with the engine stopped: EMERGENCY STOP, clearing it,
  revoking live authorisation, switching autopilot.
* An engine is restarted by a watchdog if it stops unexpectedly (autostart workspaces, bounded restarts).
* `JARVUS_MAX_FLEETS` limits concurrent engines; `JARVUS_RESEARCH_WORKERS`, `JARVUS_JOB_TIMEOUT_S` and
  `JARVUS_JOB_MEMORY_MB` bound research.

## Data

* `data/app.db`: users (scrypt password hashes), sessions (hashed tokens, CSRF secret, idle and absolute
  expiry), workspaces (each user has Main and Demo), login failures (lockout).
* `data/workspaces/<user>/<main|demo>/data/mab.db`: everything a workspace does, in WAL mode. Versioned
  migrations (`mab/migrations.py`, checksummed, applied under an exclusive lock, database backed up first).
  Key tables: `audit_events` (append-only, sanitised, correlation ids), `signals`, `deployments`,
  `user_bots`, `broker_orders` / `order_events` / `broker_fills` (execution state machine),
  `exec_positions`, `trades` (labelled by mode, deployment and connection), `connections` and
  `connection_snapshots`, `account_equity`, `research_jobs` / `research_cache`, `strategy_versions`,
  `model_versions`, `promotions`, `drift_reports`, `brain_samples`, `assistant_usage` / `assistant_outputs`.
* Credentials: an encrypted vault outside the data folder (`mab/secrets_store.py`, `mab/crypto_box.py`:
  HMAC-SHA256 stream encryption with encrypt-then-MAC, the secret's name bound as associated data; master key
  protected by Windows DPAPI, the system keyring, or an owner-only file). Names are namespaced per workspace
  and connection. Audit payloads are sanitised and a logging filter masks any secret value the process read.

## A decision, end to end (every stage is an audit event with one correlation id)

1. **Market update**: a bar closes on a shared series (one download serves every bot on that market); data
   quality is checked (gaps, duplicates, stale data) and the bar's source, receive time and age recorded.
2. **Signal**: the strategy's rules are evaluated on the closed bar; every condition, its values, the
   strategy version, data age and model versions are recorded. No-trade is a decision too.
3. **Brain**: cost gate (costs as a share of the stop), volatility gate, learned expected edge with its
   spread and evidence, bench; it approves, resizes or refuses. A win probability is shown only once
   calibrated on enough trades and better than the base rate.
4. **Risk** (independent of the brain, which cannot enlarge a trade): per-bot limits, per-account drawdown,
   daily loss, exposure, orders per minute, emergency stop, live authorisation, mode/environment match.
5. **Order**: written before it is sent (deterministic client order id), rate-limited, sent; the provider's
   acknowledgement, rejection or silence is recorded. A lost response is resolved by looking the order up by
   its client id, never by resending.
6. **Fills**: cumulative fills applied without double counting; fees, fee currency and slippage against the
   price at decision recorded.
7. **Position management**: a protective stop rests on the provider (stop or stop-limit by asset class);
   trailing stops are replaced cancel-then-place; exits cancel the stop first, then sell (limit, then
   market), re-protecting anything left.
8. **Exit**: the trade is booked with P&L after fees, R multiple, mode, deployment and account; the brain
   learns from it (and from refused trades followed as shadows).

Restart recovery reloads open orders and positions and reconciles them with the provider.

## Research and model governance

* Walk-forward evaluation (`mab/research/evaluate.py`): chronological 60/20/20 split with an embargo, k-fold
  consistency, costs (fees, spread, slippage by liquidity tier), a 2x-cost stress test, gross results, a
  liquidity cap per bar, a random-entry baseline with the same exits, bootstrap confidence intervals; a fixed
  list of pass/fail checks and a plain verdict.
* Jobs (`mab/research/jobs.py`) are queued in the workspace database, claimed atomically by worker processes,
  cached by (question, data fingerprint, code version), cancellable, and bounded in time and memory.
* Registry (`mab/research/registry.py`): every strategy version and brain snapshot is recorded; live use needs
  an evaluation of that exact version plus the owner's approval (typed acceptance if checks failed); every
  promotion is logged. Live bots score with the approved (frozen) brain; the learning brain keeps learning on
  paper. Drift reports compare live results with evaluations.
* AUTOPILOT's schedule adds jobs at a lower priority than the owner's, at most two waiting at once, and never
  promotes anything.

## AI research assistant (`mab/assistant.py`)

Official `anthropic` SDK, model `claude-opus-5-5`, explicit effort per purpose, server-side fallback on
refusals (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`), refusals reported as such, JSON-schema
structured output for strategy candidates, daily request and token budgets, every call and output stored. Log
text and headlines are wrapped as untrusted data; the assistant has no tools and cannot trade. Candidates are
compiled in the rule language and registered as untested research versions only.

## Web UI (`web/`)

Plain ES modules, no build step, strict Content-Security-Policy (scripts from the app only). Text is always
inserted as text, never parsed as HTML. TradingView Lightweight Charts 5 (Apache-2.0) is vendored with its
licence. Three destinations: Command Center, Connections, Live Intelligence; everything else is a tab, drawer
or modal. Live updates arrive over SSE with `Last-Event-ID` resume.
