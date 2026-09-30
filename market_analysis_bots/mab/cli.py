"""Command line: python -m mab <command>

  init                       create config/fleet.json and the data folder
  start [--limit N] [--bots IDS] [--minutes M] [--no-dashboard]
                             run the fleet (paper trading) with the dashboard on 127.0.0.1:8765
  stop                       ask a running fleet to stop
  status                     counts by bot state, account, data health (from the database)
  inspect BOT                a bot's configuration, latest decision with rule outcomes, recent trades
  pause | resume             stop / allow new entries (open positions keep their exits)
  emergency-stop [--reason]  close every paper position now and block entries until cleared
  clear-emergency            allow entries again after an emergency stop
  balance [show|set|deposit|withdraw] [AMOUNT]
  replay BOT [--days D]      re-run a bot over stored or downloaded bars and compare with its log
  test-order BOT [--notional N]  send a small labelled test buy+sell through risk and the paper broker
  recover                    integrity check; restore the newest good backup if the database is corrupt
  backup                     write a database backup now
  bots [--family F]          list configured bots
  dashboard                  serve the dashboard for a fleet running in another process
  secret set|delete NAME     store a credential in the OS-protected secret store (never printed)
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import shutil
import signal
import sys
import time
from typing import Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def project_path(*p) -> str:
    base = os.environ.get("MAB_HOME") or ROOT
    return os.path.join(base, *p)


def load_config(path: str = None) -> dict:
    path = path or project_path("config", "fleet.json")
    if not os.path.exists(path):
        path = project_path("config", "fleet.example.json")
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh)
    cfg["_path"] = path
    return cfg


def catalog_path(cfg: dict) -> str:
    for p in (cfg.get("catalog"), project_path("catalog", "catalog.json"),
              os.path.join(os.path.dirname(ROOT), "strategies", "catalog.json")):
        if p and os.path.exists(p if os.path.isabs(p) else project_path(p)):
            return p if os.path.isabs(p) else project_path(p)
    raise FileNotFoundError("strategy catalog not found (strategies/catalog.json)")


def load_strategies(cfg: dict) -> Dict[str, dict]:
    with open(catalog_path(cfg), encoding="utf-8") as fh:
        cat = json.load(fh)
    out = {}
    for rec in cat["strategies"]:
        d = rec.get("definition")
        if d and rec.get("implementation_status") == "implemented":
            out[rec["id"]] = d
    return out


def load_bots(cfg: dict) -> List[dict]:
    p = cfg.get("bots_file") or "bots/registry.json"
    p = p if os.path.isabs(p) else project_path(p)
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)["bots"]


def _storage(cfg):
    from mab.storage import Storage
    return Storage(os.path.join(project_path(cfg.get("data_dir", "data")), "mab.db"))


def _send(cfg, command, args=None, wait=True):
    st = _storage(cfg)
    cid = st.command(command, args or {})
    if not wait:
        return {"queued": cid}
    for _ in range(50):
        r = st.command_result(cid)
        if r and r["status"] != "pending":
            return {"status": r["status"], "result": json.loads(r["result"]) if r["result"] else None}
        time.sleep(0.2)
    return {"status": "queued", "note": "no running fleet picked this up yet; it will apply at the next start"}


# ============================================================================ commands

def cmd_init(a):
    cfgp = project_path("config", "fleet.json")
    if not os.path.exists(cfgp):
        shutil.copy(project_path("config", "fleet.example.json"), cfgp)
        print(f"created {cfgp}")
    else:
        print(f"{cfgp} already exists (left unchanged)")
    cfg = load_config()
    os.makedirs(project_path(cfg.get("data_dir", "data")), exist_ok=True)
    st = _storage(cfg)
    print(f"database ready: {st.path} (integrity: {st.check()})")
    print(f"strategies executable: {len(load_strategies(cfg))}; bots configured: {len(load_bots(cfg))}")


def run_fleet(limit=None, bot_ids=None, minutes=None, dashboard=True, port=None, config_path=None, stage=None,
              quiet=False, token=None, port_file=None):
    """port=0 binds a free port; port_file then receives {"port", "pid"} so a supervisor can find this fleet.
    token: when set, every request to the fleet's local API must carry "Authorization: Bearer <token>"."""
    from mab.dashboard import Provider, serve
    from mab.runtime import Fleet
    cfg = load_config(config_path)
    strategies = load_strategies(cfg)
    bots = load_bots(cfg)
    if stage:
        bots = [b for b in bots if stage in (b.get("stages") or [])]
    if bot_ids:
        want = set(bot_ids)
        bots = [b for b in bots if b["bot_id"] in want]
    bots = [b for b in bots if b.get("enabled", True)]
    if limit:
        bots = bots[:limit]
    fleet = Fleet(cfg, strategies, bots, project_path())
    fleet.setup()
    httpd = None
    if dashboard:
        d = cfg.get("dashboard", {})
        httpd = serve(Provider(fleet.storage, fleet), "127.0.0.1", d.get("port", 8765) if port is None else port,
                      token=token)
        if port_file:
            tmp = port_file + ".tmp"
            with open(tmp, "w") as fh:
                json.dump({"port": httpd.server_address[1], "pid": os.getpid(), "started": int(time.time())}, fh)
            os.replace(tmp, port_file)
        if not quiet:
            print(f"dashboard: http://127.0.0.1:{httpd.server_address[1]}/")
    pidf = project_path(cfg.get("data_dir", "data"), "fleet.pid")
    with open(pidf, "w") as fh:
        fh.write(str(os.getpid()))
    fleet.start()
    if not quiet:
        print(f"fleet running: {len(fleet.bots)} bots, {len(fleet.hub.series)} shared series. Ctrl+C to stop.")

    def _sig(*_):
        fleet.running = False
    try:
        signal.signal(signal.SIGTERM, _sig)
    except (ValueError, AttributeError):
        pass
    fleet.wait(None if minutes is None else minutes * 60)
    if fleet.running:
        fleet.stop()
    try:
        fleet.health_cycle()
    except Exception:
        pass
    if httpd:
        httpd.shutdown()
    try:
        os.remove(pidf)
    except OSError:
        pass
    return fleet


def cmd_start(a):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_fleet(a.limit, a.bots.split(",") if a.bots else None, a.minutes, not a.no_dashboard, a.port, a.config,
              a.stage)


def cmd_stop(a):
    print(_send(load_config(a.config), "stop"))


def cmd_simple(name):
    def f(a):
        args = {}
        if getattr(a, "reason", None):
            args["reason"] = a.reason
        print(_send(load_config(a.config), name, args))
    return f


def cmd_balance(a):
    cfg = load_config(a.config)
    if a.action == "show":
        st = _storage(cfg)
        acct = st.kv_get("account")
        if not acct:
            print("no account yet: it is created on the first start, with the balance from config/fleet.json")
            return
        from mab.account import Account
        print(json.dumps(Account.from_state(acct).summary(), indent=1))
        return
    if a.amount is None:
        raise SystemExit("amount required")
    r = _send(cfg, a.action, {"amount": a.amount})
    if r.get("status") == "queued":
        # no fleet running: apply directly to the stored account
        from mab.account import Account
        st = _storage(cfg)
        acct = st.kv_get("account")
        c = cfg.get("account", {})
        acc = Account.from_state(acct) if acct else Account(c.get("balance", 100_000), c.get("slots", 20))
        rec = getattr(acc, a.action)(a.amount)
        st.save_cash_flow(rec)
        st.kv_set("account", acc.to_state())
        st.write("UPDATE control SET status='done', result=? WHERE status='pending' AND command=?",
                 (json.dumps(rec), a.action))
        r = {"status": "applied to the stored account (fleet not running)", "result": rec}
    print(json.dumps(r, indent=1, default=str))


def cmd_status(a):
    cfg = load_config(a.config)
    st = _storage(cfg)
    r = st.query("SELECT body FROM system_health ORDER BY time DESC LIMIT 1")
    if not r:
        print("no health records yet (has the fleet been started?)")
        return
    h = json.loads(r[0]["body"])
    age = (time.time() * 1000 - h["time"]) / 1000
    print(f"last health record {age:.0f}s ago; uptime {h['uptime_s'] / 60:.1f} min; bots {h['bots']}; series {h['series']}")
    print("bot states:", json.dumps(h["bot_states"]))
    print("series:", json.dumps(h["series_status"]))
    print(f"evaluations {h['completed_evaluations']}/{h['scheduled_evaluations']}; decision p95 {h['eval_ms_p95']} ms; "
          f"latency p95 {h['latency_ms_p95']} ms; requests {h['requests']} (429s {h['http_429']})")
    ac = h["account"]
    print(f"account: equity {ac['equity']:,.2f} {ac['currency']}, cash {ac['cash']:,.2f}, open {ac['open_positions']}, "
          f"realized {ac['realized_pnl']:,.2f}, fees {ac['fees']:,.2f}, TWR {100 * ac['twr']:.3f}%")
    print(f"paused={h['paused']} emergency={h['emergency']} storage_ok={h['storage_ok']}")
    for e in st.query("SELECT time, level, kind, message FROM events ORDER BY id DESC LIMIT 8")[::-1]:
        print(f"  {time.strftime('%H:%M:%S', time.localtime(e['time'] / 1000))} {e['level']:8s} {e['message']}")


def cmd_inspect(a):
    cfg = load_config(a.config)
    st = _storage(cfg)
    bots = {b["bot_id"]: b for b in load_bots(cfg)}
    b = bots.get(a.bot)
    if not b:
        raise SystemExit(f"unknown bot {a.bot}")
    print(json.dumps(b, indent=1))
    strat = load_strategies(cfg).get(b["strategy_id"])
    print("strategy rules:", json.dumps({k: strat.get(k) for k in ("entry", "filters", "stop", "target", "exit")}, indent=1))
    for s in st.query("SELECT * FROM signals WHERE bot_id=? ORDER BY id DESC LIMIT 5", (a.bot,)):
        print(f"\n{time.strftime('%Y-%m-%d %H:%M', time.gmtime(s['bar_time'] / 1000))}Z  {s['action']}: {s['reason']}")
        for r in json.loads(s["rules"] or "[]"):
            mark = {True: "PASS", False: "FAIL", None: "????"}[r["passed"]]
            print(f"   {mark} {r['rule']}   [{r['detail']}]")
        feats = json.loads(s["features"] or "{}")
        if feats:
            print("   values:", ", ".join(f"{k}={v}" for k, v in list(feats.items())[:10]))
    tr = st.query("SELECT * FROM trades WHERE bot_id=? ORDER BY id DESC LIMIT 10", (a.bot,))
    print(f"\n{len(tr)} recent trades")
    for t in tr:
        print(f"  {'long' if t['side'] > 0 else 'short'} {t['qty']:.6g} {t['entry_price']:.6g} -> {t['exit_price']:.6g}"
              f"  pnl {t['pnl']:.2f}  R {t['r'] if t['r'] is None else round(t['r'], 2)}  {t['exit_reason']}")
    stt = st.load_bot_states().get(a.bot)
    print("\nsaved state:", json.dumps(stt, default=str)[:600])


def cmd_recover(a):
    import sqlite3
    cfg = load_config(a.config)
    dbp = os.path.join(project_path(cfg.get("data_dir", "data")), "mab.db")
    bdir = os.path.join(project_path(cfg.get("data_dir", "data")), "backups")
    ok = False
    try:
        con = sqlite3.connect(dbp)
        res = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        ok = res == "ok"
        print(f"integrity check: {res}")
    except sqlite3.DatabaseError as e:
        print(f"database unreadable: {e}")
    if ok:
        st = _storage(cfg)
        states = st.load_bot_states()
        bad = [k for k, v in states.items() if v.get("corrupt")]
        acct = st.kv_get("account")
        print(f"bot states: {len(states)} saved, {len(bad)} unreadable {bad[:10]}")
        if acct:
            from mab.account import Account
            acc = Account.from_state(acct)
            fills = st.query("SELECT bot_id, venue, instrument, side, qty FROM fills")
            net: Dict[tuple, float] = {}
            for f in fills:
                k = (f["bot_id"], f["venue"], f["instrument"])
                net[k] = net.get(k, 0.0) + (f["qty"] if f["side"] == "buy" else -f["qty"])
            recorded = {k: p["qty"] for k, p in acc.positions.items()}
            diffs = {str(k): (recorded.get(k, 0.0), round(v, 12)) for k, v in net.items()
                     if abs(recorded.get(k, 0.0) - v) > 1e-9}
            print(f"positions reconcile against fills: {'OK' if not diffs else 'MISMATCH ' + json.dumps(diffs)[:500]}")
        return
    backups = sorted(f for f in os.listdir(bdir) if f.endswith(".db")) if os.path.isdir(bdir) else []
    for f in reversed(backups):
        p = os.path.join(bdir, f)
        try:
            con = sqlite3.connect(p)
            if con.execute("PRAGMA integrity_check").fetchone()[0] == "ok":
                con.close()
                bad = dbp + f".corrupt-{int(time.time())}"
                if os.path.exists(dbp):
                    os.replace(dbp, bad)
                for sfx in ("-wal", "-shm"):
                    if os.path.exists(dbp + sfx):
                        os.remove(dbp + sfx)
                shutil.copy(p, dbp)
                print(f"restored {f}; the damaged file was kept as {bad}")
                return
        except sqlite3.DatabaseError:
            continue
    print("no readable backup found; start fresh with `python -m mab init` after moving the damaged file away")


def cmd_backup(a):
    cfg = load_config(a.config)
    st = _storage(cfg)
    print(st.backup(os.path.join(project_path(cfg.get("data_dir", "data")), "backups")))


def cmd_bots(a):
    cfg = load_config(a.config)
    strat = load_strategies(cfg)
    n = 0
    for b in load_bots(cfg):
        fam = (strat.get(b["strategy_id"]) or {}).get("family", "?")
        if a.family and a.family != fam:
            continue
        n += 1
        print(f"{b['bot_id']:9s} {b['strategy_id']:10s} {fam:22s} {b['venue']:9s} {b['instrument']:16s} "
              f"{'on' if b.get('enabled', True) else 'off'}")
    print(f"{n} bots")


def cmd_replay(a):
    from mab.replay import replay_bot
    cfg = load_config(a.config)
    print(json.dumps(replay_bot(cfg, a.bot, a.days), indent=1, default=str))


def cmd_dashboard(a):
    from mab.dashboard import Provider, serve
    cfg = load_config(a.config)
    print(f"dashboard (database mode): http://127.0.0.1:{a.port}/")
    serve(Provider(_storage(cfg)), "127.0.0.1", a.port, block=True)


def cmd_secret(a):
    from mab import secrets_store
    if a.action == "set":
        val = getpass.getpass(f"value for {a.name} (input hidden): ")
        secrets_store.set_secret(a.name, val)
        print(f"stored {a.name} ({secrets_store.backend_name()})")
    elif a.action == "delete":
        secrets_store.delete_secret(a.name)
        print(f"deleted {a.name}")
    else:
        print("names stored:", ", ".join(secrets_store.list_names()) or "none")


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m mab", description="Market analysis bots: paper-trading fleet")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    s = sub.add_parser("start")
    s.add_argument("--limit", type=int)
    s.add_argument("--bots")
    s.add_argument("--stage")
    s.add_argument("--minutes", type=float)
    s.add_argument("--port", type=int)
    s.add_argument("--no-dashboard", action="store_true")
    s.set_defaults(fn=cmd_start)
    sub.add_parser("stop").set_defaults(fn=cmd_stop)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    s = sub.add_parser("inspect"); s.add_argument("bot"); s.set_defaults(fn=cmd_inspect)
    sub.add_parser("pause").set_defaults(fn=cmd_simple("pause"))
    sub.add_parser("resume").set_defaults(fn=cmd_simple("resume"))
    s = sub.add_parser("emergency-stop"); s.add_argument("--reason", default="operator"); s.set_defaults(fn=cmd_simple("emergency_stop"))
    sub.add_parser("clear-emergency").set_defaults(fn=cmd_simple("clear_emergency"))
    s = sub.add_parser("balance"); s.add_argument("action", choices=["show", "set", "deposit", "withdraw"], nargs="?", default="show")
    s.add_argument("amount", type=float, nargs="?"); s.set_defaults(fn=lambda a: cmd_balance(
        argparse.Namespace(**{**vars(a), "action": {"set": "set_balance"}.get(a.action, a.action)})))
    s = sub.add_parser("replay"); s.add_argument("bot"); s.add_argument("--days", type=float, default=2); s.set_defaults(fn=cmd_replay)
    sub.add_parser("recover").set_defaults(fn=cmd_recover)
    s = sub.add_parser("test-order"); s.add_argument("bot"); s.add_argument("--notional", type=float, default=50.0)
    s.set_defaults(fn=lambda a: print(json.dumps(_send(load_config(a.config), "test_order",
                                                       {"bot_id": a.bot, "notional": a.notional}), indent=1, default=str)))
    sub.add_parser("backup").set_defaults(fn=cmd_backup)
    s = sub.add_parser("bots"); s.add_argument("--family"); s.set_defaults(fn=cmd_bots)
    s = sub.add_parser("dashboard"); s.add_argument("--port", type=int, default=8765); s.set_defaults(fn=cmd_dashboard)
    s = sub.add_parser("secret"); s.add_argument("action", choices=["set", "delete", "list"]); s.add_argument("name", nargs="?", default="")
    s.set_defaults(fn=cmd_secret)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
