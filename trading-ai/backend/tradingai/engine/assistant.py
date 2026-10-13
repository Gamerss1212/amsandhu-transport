"""The voice and reporting assistant (owner's specification sections 10-11), JARVIS-inspired in tone.

Honest scope of this build:
* Understanding is a fixed set of typed intents (keyword grammar), not a language model: no cloud AI is connected.
  Every answer is built from verified application state with templates, so quantities, order states and the account
  mode are never changed by phrasing.
* Speech is done by the browser (Web Speech API: system voices, en-GB preferred; listening uses the browser's own
  recognizer where available). Proactive announcements, mute, quiet hours and the transcript live on the page.
* Commands go through the same backend calls as the buttons. Allowed by voice: status questions, pause/resume new
  entries, summaries, navigation, and EMERGENCY STOP (it only reduces risk). Going live, raising limits, flattening,
  re-arming or moving money are refused by voice and pointed to the deliberate control on the page.

Announcements are structured events: id, category, severity, subject, text, created, expiry, dedupe key and the record
they refer to. They are deduplicated, rate limited, batched (fills) and dropped when they expire.
"""

from __future__ import annotations

import re
import threading
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

from tradingai.core.ids import new_id
from tradingai.storage.db import now_ms

if TYPE_CHECKING:
    from tradingai.app import App

SEV_RANK = {"info": 0, "warning": 1, "error": 2, "critical": 3}


class Assistant:
    def __init__(self, app: "App"):
        self.app = app
        self.sid = app.bus.subscribe()
        self._stop = threading.Event()
        self._last: dict[str, float] = {}
        self._fills: list[dict] = []
        self._fill_since = 0.0
        self.announced = 0
        self.commands: dict[str, dict] = {}
        # what "that bot" refers to: the bot most recently named in an answer or an announcement (expires in 30 min)
        self.context: dict[str, Any] = {"bot_id": None, "ts": 0.0, "source": None}
        self._thread = threading.Thread(target=self._run, name="assistant", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.app.bus.unsubscribe(self.sid)

    def status(self) -> str:
        return f"listening to system events; {self.announced} announcement(s) so far; deterministic (no cloud AI)"

    # ------------------------------------------------------------------ proactive announcements
    def _run(self) -> None:
        while not self._stop.is_set():
            for ev in self.app.bus.drain(self.sid, 1.0):
                try:
                    self._consider(ev)
                except Exception:                                  # noqa: BLE001 - announcements are optional
                    pass
            if self._fills and time.time() - self._fill_since > 15:
                self._flush_fills()

    def _announce(self, category: str, severity: str, subject: str, text: str, key: str, cooldown: float,
                  ttl_s: float, ref: Any = None) -> None:
        now = time.time()
        if now - self._last.get(key, 0) < cooldown:
            return
        self._last[key] = now
        self.announced += 1
        self.app.bus.publish("voice", {"id": new_id("VOX"), "category": category, "severity": severity,
                                       "subject": subject, "text": text, "created": now_ms(),
                                       "expires": now_ms() + int(ttl_s * 1000), "dedupe": key, "ref": ref},
                             severity=severity)

    def _consider(self, ev: dict) -> None:
        t, d = ev["topic"], ev.get("data") or {}
        if t == "voice":
            return
        if t == "kill_switch":
            self._announce("risk", "critical", "STOP ALL TRADING", "Emergency stop engaged. All bots are stopped and "
                           "no new orders can be sent. Positions were kept unless flattening is enabled.",
                           "kill", 5, 600, ev["id"])
        elif t == "risk.locked":
            self._announce("risk", "critical", "Trading locked", f"Trading is locked by the {', '.join(d.get('breakers', []))} "
                           "limit. Only orders that reduce positions are allowed until you re-arm.", "locked", 60, 600)
        elif t == "risk.entries":
            self._announce("risk", "warning", "New entries", "New entries are paused. Existing positions continue under "
                           "their exit rules." if d.get("paused") else "New entries are allowed again.", "entries", 3, 120)
        elif t == "order.update" and d.get("status") == "FILLED":
            self._fills.append(d)
            if len(self._fills) == 1:
                self._fill_since = time.time()
        elif t == "autopilot":
            msg = d.get("message", "")
            if msg.startswith("AUTOPILOT"):
                self._announce("autopilot", "info", "System", "The master agent is " +
                               ("on." if msg.endswith("ON") else "off."), "ap:" + msg[:60], 30, 900)
        elif t == "master":
            msg = d.get("message", "")
            if re.search(r": (active|rolled_back) \(|-> active|suspended", msg):
                bad = "rolled_back" in msg or "suspended" in msg
                self._announce("master", "warning" if bad else "info", "Master agent",
                               "Master agent: " + msg.split(" (")[0] + ".", "ma:" + msg[:60], 30, 900)
        elif t == "learning" and not d.get("repeat"):
            self._announce("learning", "info", "Lesson learned", f"New lesson from {d.get('agent') or 'the system'}: "
                           f"{str(d.get('root_cause', '')).replace('_', ' ').lower()}. Its safeguard now applies to all "
                           "agents.", "les:" + str(d.get("root_cause")), 60, 900)
        elif t == "state" and d.get("to") in ("ERROR", "RECONCILIATION_REQUIRED"):
            self._announce("system", "critical", "System state", f"Attention: the system moved to "
                           f"{d['to'].replace('_', ' ').lower()}. {d.get('reason', '')}", "state:" + d["to"], 60, 900)
        elif t == "reconcile":
            self._announce("system", "critical", "Reconciliation", "Local records and the account disagree. New "
                           "exposure is frozen until it is resolved.", "recon", 300, 1800)
        elif t == "data.error":
            self._announce("data", "warning", "Data feed", "A market data feed is failing; bots that depend on it are "
                           "waiting.", "data", 900, 600)
        elif t == "research.done" and d.get("state") == "failed":
            return

    def remember(self, bot_id: Optional[str], source: str) -> None:
        if bot_id and bot_id in self.app.bots:
            self.context = {"bot_id": bot_id, "ts": time.time(), "source": source}

    def _flush_fills(self) -> None:
        fills, self._fills = self._fills, []
        if not fills:
            return
        last = fills[-1].get("instrument")
        owner = next((b.bot_id for b in self.app.bots.values() if b.instrument_id == last), None)
        self.remember(owner, "fill announcement")
        if len(fills) == 1:
            f = fills[0]
            txt = f"{'Paper' if self.app.mode != 'live' else 'Live'} fill confirmed: {f.get('side')} {f.get('qty')} " \
                  f"{f.get('instrument')}."
        else:
            txt = f"{len(fills)} {'paper' if self.app.mode != 'live' else 'live'} fills confirmed in the last few " \
                  f"seconds: " + ", ".join(f"{f.get('side')} {f.get('instrument')}" for f in fills[:4]) + "."
        self._announce("execution", "info", "Fills", txt, f"fills:{fills[-1].get('client_order_id')}", 0, 120)

    # ------------------------------------------------------------------ questions and commands
    def ask(self, text: str, command_id: Optional[str] = None) -> dict:
        q = " ".join(text.lower().strip().split())
        cid = command_id or new_id("CMD")
        if cid in self.commands:                                    # a retried command is not executed twice
            return dict(self.commands[cid], repeated=True)
        for pattern, fn in INTENTS:
            if re.search(pattern, q):
                out = fn(self, q)
                break
        else:
            out = {"intent": "help", "answer": HELP}
        out["command_id"] = cid
        out["ts"] = now_ms()
        if out.get("action"):
            self.commands[cid] = out
            self.app.audit("assistant", f"assistant command '{text[:80]}': {out['action'].get('result')}",
                           data={"intent": out["intent"], "action": out["action"]})
        return out

    # helpers that read verified state
    def _acct(self) -> dict:
        return self.app.account_view()


def _money(v: Any) -> str:
    try:
        return f"{Decimal(str(v)):,.2f} dollars"
    except Exception:                                               # noqa: BLE001
        return "unavailable"


NAMES = {"bitcoin": "BTC", "btc": "BTC", "xbt": "BTC", "ether": "ETH", "ethereum": "ETH", "solana": "SOL",
         "dogecoin": "DOGE", "doge": "DOGE", "pepe": "PEPE", "shiba": "SHIB", "euro": "EURUSD", "gold": "GC",
         "s&p": "SPY", "nasdaq": "QQQ", "apple": "AAPL", "tesla": "TSLA", "nvidia": "NVDA", "microsoft": "MSFT"}
PRONOUN = r"\b(that|this|the same|it|its|it's)\b"


def resolve_bot(a: Assistant, q: str) -> tuple[Optional[Any], str]:
    """Which bot the owner means: an explicit id, a market named in the question, "that bot" (the last one mentioned,
    for 30 minutes), or the only bot there is. Returns (bot or None, how it was resolved)."""
    bots = list(a.app.bots.values())
    m = re.search(r"\bbot[-_ ]?([0-9a-z]{6,})", q)
    if m:
        hit = [b for b in bots if b.bot_id.lower().replace("-", "").endswith(m.group(1).replace("-", ""))]
        if hit:
            return hit[0], "named by id"
    words = set(re.findall(r"[a-z0-9&]+", q))
    wanted = {NAMES[w] for w in words if w in NAMES} | {w.upper() for w in words}
    hits = [b for b in bots if b.instrument_id.split(":")[-1].split("-")[0].upper() in wanted]
    if len(hits) == 1:
        return hits[0], "named by market"
    if len(hits) > 1:
        run = [b for b in hits if b.state == "running"]
        return (run or hits)[0], "named by market (first of several)"
    if re.search(PRONOUN, q) and a.context["bot_id"] in a.app.bots and time.time() - a.context["ts"] < 1800:
        return a.app.bots[a.context["bot_id"]], f"the bot from the last {a.context['source']}"
    if len(bots) == 1:
        return bots[0], "the only bot"
    return None, "unresolved"


def _bot_line(a: Assistant, b: Any) -> str:
    d = a.app.db.one("SELECT ts, outcome, reason FROM decisions WHERE bot_id=? ORDER BY ts DESC LIMIT 1", (b.bot_id,))
    owner = a.app.fleet.owner_of(b.instrument_id)
    txt = (f"{b.strategy_id.split('.')[0].replace('_', ' ')} on {b.instrument_id.split(':')[-1]} {b.tf} is {b.state}"
           + (f", owned by agent {owner}" if owner else "") + ".")
    if d:
        txt += f" Its last decision, {int((now_ms() - d['ts']) / 60000)} minutes ago, was " \
               f"{d['outcome'].replace('_', ' ').lower()}: {d['reason']}."
    else:
        txt += " It has not made a decision yet."
    return txt


def i_that_bot(a: Assistant, q: str) -> dict:
    b, how = resolve_bot(a, q)
    if b is None:
        return {"intent": "bot_detail", "answer": "Which bot do you mean? I have no recent bot to refer to. Name its "
                "market, for example: what is the bitcoin bot doing?", "resolved": how}
    a.remember(b.bot_id, "question")
    if re.search(r"\b(pause|stop|halt)\b", q):
        if b.state != "running":
            return {"intent": "pause_bot", "answer": f"That bot is already {b.state}.", "resolved": how,
                    "facts": {"bot_id": b.bot_id}}
        a.app.bot_action(b.bot_id, "pause", by="assistant")
        return {"intent": "pause_bot", "answer": f"Paused {b.strategy_id.split('.')[0].replace('_', ' ')} on "
                f"{b.instrument_id.split(':')[-1]}. Its open position, if any, is kept; resume it on the dashboard.",
                "resolved": how, "facts": {"bot_id": b.bot_id},
                "action": {"name": "pause_bot", "bot_id": b.bot_id, "result": "completed"}}
    return {"intent": "bot_detail", "answer": _bot_line(a, b), "resolved": how, "facts": {"bot_id": b.bot_id}}


def i_bots(a: Assistant, q: str) -> dict:
    app = a.app
    bots = list(app.bots.values())
    run = [b for b in bots if b.state == "running"]
    c = app.fleet.counts()
    parts = [f"The master agent runs {c['registered']} trading agents in {app.mode} mode: {c['assigned']} have a market, "
             f"{c['validated']} have a validated version and {c['execution_eligible']} may open trades now.",
             f"{len(run)} of {len(bots)} bots are running (each is one agent's execution loop)."]
    for b in run[:6]:
        parts.append(f"{(b.agent_id + ': ') if getattr(b, 'agent_id', None) else ''}"
                     f"{b.strategy_id.split('.')[0].replace('_', ' ')} on {b.instrument_id.split(':')[1]} {b.tf}.")
    parts.append(f"The master is on: {app.fleet.doing}." if app.autopilot.cfg.enabled else
                 "The master agent is off: press Start System.")
    if len(run) == 1:
        a.remember(run[0].bot_id, "status answer")
    return {"intent": "bots", "answer": " ".join(parts), "facts": {"running": len(run), "bots": len(bots)}}


def i_why_not(a: Assistant, q: str) -> dict:
    app, r = a.app, a.app.risk
    if r.kill_switch:
        why = f"Emergency stop is engaged ({r.kill_switch['reason']}). Re-arm it on the dashboard when you are ready."
    elif r.trading_locked:
        why = f"Trading is locked: {r.trading_locked['reason']}."
    elif r.entries_paused:
        why = "New entries are paused; exits still run."
    elif app.state.state == "RECONCILIATION_REQUIRED":
        why = "Reconciliation is required: new exposure is frozen until local records match the account."
    elif not any(b.state == "running" for b in app.bots.values()):
        none_qualified = not app.autopilot.candidates()
        why = ("No agent has a validated version yet, so the system stays in cash by design while the master trains "
               "them. " if none_qualified else "No agent's execution loop is running. ") + (
            "Right now: " + app.fleet.doing + "." if app.autopilot.cfg.enabled
            else "Press Start System to let the master agent run.")
    else:
        last = app.db.one("SELECT outcome, reason, instrument_id FROM decisions ORDER BY ts DESC LIMIT 1")
        why = ("Bots are running; the latest decision was " + f"{last['outcome'].replace('_', ' ').lower()} on "
               f"{last['instrument_id']}: {last['reason']}." if last else "Bots are running and waiting for the next "
               "completed bar.") + " Not trading is a valid outcome when no rule qualifies."
    return {"intent": "why_not_trading", "answer": why}


def i_why_trade(a: Assistant, q: str) -> dict:
    b, how = resolve_bot(a, q) if re.search(PRONOUN + r"|\bbot\b", q) else (None, "")
    if b is not None:
        d = a.app.db.one("SELECT decision_id, instrument_id, strategy_id, reason, ts, mode, bot_id FROM decisions "
                         "WHERE outcome='ORDER' AND bot_id=? ORDER BY ts DESC LIMIT 1", (b.bot_id,))
        if not d:
            return {"intent": "why_trade", "answer": f"{_bot_line(a, b)} It has not placed an order yet.",
                    "resolved": how}
    else:
        d = a.app.db.one("SELECT decision_id, instrument_id, strategy_id, reason, ts, mode, bot_id FROM decisions "
                         "WHERE outcome='ORDER' ORDER BY ts DESC LIMIT 1")
    if not d:
        return {"intent": "why_trade", "answer": "There is no trade yet in this installation."}
    a.remember(d["bot_id"], "trade explanation")
    return {"intent": "why_trade", "answer": f"The last {d['mode']} order was on {d['instrument_id']} by "
            f"{(d['strategy_id'] or '').split('.')[0].replace('_', ' ')}: {d['reason']}. Every risk check it passed is "
            "listed on Agent Activity under that decision.", "facts": {"decision_id": d["decision_id"]},
            "navigate": "/intelligence"}


def i_fees(a: Assistant, q: str) -> dict:
    day0 = int(time.time() // 86400 * 86400 * 1000)
    rows = a.app.db.query("SELECT fee, environment FROM fills WHERE ts>=?", (day0,))
    fee = sum((Decimal(r["fee"]) for r in rows), Decimal(0))
    env = "live" if any(r["environment"] == "live" for r in rows) else "paper"
    return {"intent": "fees", "answer": f"Fees today: {_money(fee)} across {len(rows)} {env} fill"
            f"{'s' if len(rows) != 1 else ''}.", "facts": {"fees": str(fee)}}


def i_review(a: Assistant, q: str) -> dict:
    app = a.app
    cat = app.catalog_view()
    rs = cat["research_states"]
    cands = app.autopilot.candidates()[:3]
    txt = (f"Of {len(cat['cards'])} catalog strategies, {cat['qualifying']['count']} qualify. "
           f"{rs.get('IMPLEMENTED_RESEARCH_ONLY', 0)} are waiting for their first test, "
           f"{rs.get('TEST_COMPLETE', 0)} need more research and {rs.get('REJECTED_UNDER_TEST', 0)} were rejected; "
           f"{rs.get('DATA_BLOCKED', 0)} are blocked by missing data or products.")
    if cands:
        txt += " Agents with a validated version: " + "; ".join(
            f"{c['agent']} {c['strategy_id'].split('.')[0].replace('_', ' ')} on {c['iid'].split(':')[1]}"
            for c in cands) + "."
    if app.fleet.jobs:
        txt += f" {len(app.fleet.jobs)} training job{'s are' if len(app.fleet.jobs) != 1 else ' is'} running."
    return {"intent": "review", "answer": txt}


def i_exposure(a: Assistant, q: str) -> dict:
    v = a._acct()
    pos = v["positions"]
    if not pos:
        return {"intent": "exposure", "answer": "There are no open positions. Cash is a valid position."}
    eq = Decimal(v["account"]["equity"] or "0")
    gross = sum((abs(Decimal(p["qty"])) * Decimal(p["price"] or p["avg_price"]) * Decimal(p["multiplier"])
                 for p in pos), Decimal(0))
    top = sorted(pos, key=lambda p: -abs(float(p["qty"]) * float(p["price"] or p["avg_price"])))[:3]
    return {"intent": "exposure", "answer": f"{len(pos)} open position{'s' if len(pos) != 1 else ''}, gross exposure "
            f"{(gross / eq if eq else 0):.0%} of equity. Largest: " + ", ".join(p["instrument_id"].split(":")[1]
                                                                                for p in top) + ".",
            "facts": {"gross": str(gross)}}


def i_risk(a: Assistant, q: str) -> dict:
    r = a.app.risk
    st = "engaged" if r.kill_switch else "locked" if r.trading_locked else "armed"
    return {"intent": "risk", "answer": f"Risk service {st}. Daily loss limit {r.limits.max_daily_loss_pct:.0%}, "
            f"drawdown limit {r.limits.max_drawdown_pct:.0%}. {r.counters['denied']} orders denied and "
            f"{r.counters['adjusted']} reduced this session." + (" New entries are paused." if r.entries_paused else "")}


def i_broker(a: Assistant, q: str) -> dict:
    conns = a.app.connections_view()
    live = [c for c in conns if c.get("environment") == "live"]
    return {"intent": "broker", "answer": f"{len(conns)} connection{'s' if len(conns) != 1 else ''}: the paper account"
            + (f" and {len(conns) - 1} broker connection{'s' if len(conns) - 1 != 1 else ''}" if len(conns) > 1 else "")
            + f". Live trading is {'armed' if a.app.live.get('armed') else 'off'}" + (
                f"; {len(live)} live connection(s) saved, none verified." if live and not a.app.live.get("armed") else "."),
            "navigate": "/broker"}


def i_summary(a: Assistant, q: str) -> dict:
    from tradingai.engine.reports import session_report
    s = session_report(a.app)
    v = a._acct()
    return {"intent": "summary", "answer": f"This session: {s['trades']} {'paper' if s['simulated'] else 'live'} fill"
            f"{'s' if s['trades'] != 1 else ''}, fees {_money(s['fees'])}, {s['decisions'].get('RISK_REJECT', 0)} "
            f"orders blocked by risk, {len(s['incidents'])} warnings. Equity {_money(v['account']['equity'])}, "
            f"today's change {_money(v['day_pnl'])}."}


def i_pause(a: Assistant, q: str) -> dict:
    on = not re.search(r"\b(resume|unpause|allow)\b", q)
    a.app.pause_entries(on, "assistant", "voice/text command")
    return {"intent": "pause_entries", "answer": ("New entries are paused. Existing positions continue under their "
                                                  "exit rules.") if on else "New entries are allowed again.",
            "action": {"name": "pause_entries", "requested": on, "result": "completed"}}


def i_estop(a: Assistant, q: str) -> dict:
    a.app.emergency_stop("assistant command", "assistant")
    return {"intent": "emergency_stop", "answer": "Emergency stop engaged. Bots stopped; no new orders. Positions were "
            "kept unless flattening is enabled. Re-arm on the dashboard.", "action": {"name": "emergency_stop",
                                                                                      "result": "completed"}}


def i_refuse(a: Assistant, q: str) -> dict:
    return {"intent": "refused", "answer": "That changes money or permissions, so it needs the deliberate control on "
            "the page: live arming and limits on Brokers & Accounts, flattening and re-arming on the AI Trading System "
            "page. I won't do it from a voice or chat command."}


def i_navigate(a: Assistant, q: str) -> dict:
    if "broker" in q or "account" in q:
        return {"intent": "navigate", "answer": "Opening Brokers & Accounts.", "navigate": "/broker"}
    if "agent" in q or "activity" in q:
        return {"intent": "navigate", "answer": "Opening the AI Supercomputer page.", "navigate": "/intelligence"}
    return {"intent": "navigate", "answer": "Opening the AI Trading System page.", "navigate": "/"}


HELP = ("I can tell you what the bots are doing, why you are or aren't trading, why the last trade happened, today's "
        "fees, which strategies are under review, your exposure and risk state, broker connections, and a session "
        "summary. Ask about one bot by its market (the bitcoin bot) or as that bot after I mention one. I can pause a "
        "bot, pause or resume new entries and engage the emergency stop. Going live, raising limits, "
        "flattening and re-arming stay on the page.")

INTENTS = [
    (r"\b(go live|live mode|raise|increase).*(limit|capital|leverage|live)|\b(go live|arm live)\b|\bflatten|\bre-?arm"
     r"|\bwithdraw|\bdeposit|\btransfer", i_refuse),
    (r"emergency stop|stop all trading|kill switch", i_estop),
    (r"\b(pause|resume|unpause|allow)\b.*\bentr", i_pause),
    (r"\b(pause|stop|halt)\b.*\bbot\b", i_that_bot),
    (r"why .*(not|n't|no) (trad|buy|sell)|why .*idle|why .*nothing", i_why_not),
    (r"why .*(trade|buy|sell|enter|order)|last trade|that trade", i_why_trade),
    (r"\bfee", i_fees),
    (r"review|probation|candidate|research", i_review),
    (r"exposure|position", i_exposure),
    (r"\brisk|limit|drawdown|loss", i_risk),
    (r"broker|connection", i_broker),
    (r"show|open|go to|navigate", i_navigate),
    (r"summary|report|how (am i|are we) doing|today", i_summary),
    (PRONOUN + r".*\bbot\b|\bthe [a-z0-9&]+ bot\b|\bbot[-_ ]?[0-9a-z]{6,}", i_that_bot),
    (r"bot|doing|status|what.*happening", i_bots),
    (r"help|what can you", lambda a, q: {"intent": "help", "answer": HELP}),
]
