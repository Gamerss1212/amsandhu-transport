"""The owner's 80-template catalog, portfolio templates (no look-ahead, next-day execution), portfolio bots, the new
controls (pause new entries, flatten), reason codes, the assistant and the 25 roles."""

import time
from decimal import Decimal as D

import numpy as np
import pytest

from tradingai.app import App
from tradingai.engine import portfolio_bot
from tradingai.research import portfolio as P
from tradingai.strategies import catalog


@pytest.fixture()
def app(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False, autopilot=False)
    yield a
    a.shutdown()


# ---------------------------------------------------------------- catalog
def test_catalog_has_all_80_cards_and_47_sources_mapped():
    d = catalog.load()
    assert len(d["cards"]) == 80 and len(d["sources"]) == 47
    assert {c["id"] for c in d["cards"]} == {f"ST{n:03d}" for n in range(1, 81)}
    for c in d["cards"]:
        m = catalog.implementation(c["id"])
        assert m["implementations"] or m["blocked"], c["id"]          # every card is implemented or says why not
        for s in c["sources"]:
            assert s in d["sources"]


def test_catalog_view_states(app):
    v = app.catalog_view()
    states = {c["id"]: c["state"] for c in v["cards"]}
    assert states["ST063"] == "documented"                              # options: no product support
    assert states["ST031"] == "implemented"                             # added generator, not yet tested here
    assert states["ST004"] == "implemented"                             # portfolio template
    assert v["reason_codes"]["PRODUCT_UNSUPPORTED"]


# ---------------------------------------------------------------- portfolio templates
def synthetic_panel(n_days=1200, n=7, seed=1, drift=0.0003, sd=0.01):
    rng = np.random.default_rng(seed)
    r = rng.normal(drift, sd, (n_days, n)) + np.linspace(0.0005, -0.0002, n)
    c = 100 * np.cumprod(1 + r, axis=0)
    days = np.arange(16000, 16000 + n_days)
    rr = np.vstack([np.full((1, n), np.nan), c[1:] / c[:-1] - 1])
    return {"days": days, "c": c, "r": rr, "status": {}}


@pytest.mark.parametrize("sid", list(P.PORTFOLIOS))
def test_portfolio_weights_use_no_future_data(sid):
    spec = P.PORTFOLIOS[sid]
    pan = synthetic_panel(n=len(spec.universe))
    t = 800
    w1 = spec.fn(pan["c"], pan["r"], t, 252.0, **spec.params)
    c2, r2 = pan["c"].copy(), pan["r"].copy()
    c2[t + 1:] *= 3.0                                                   # change every price after the decision day
    r2[t + 1:] = 0.5
    w2 = spec.fn(c2, r2, t, 252.0, **spec.params)
    assert np.allclose(np.nan_to_num(w1), np.nan_to_num(w2)), sid
    assert np.abs(np.nan_to_num(w1)).sum() <= 1.0 + 1e-9                # never leveraged


def test_portfolio_simulation_executes_next_day_and_charges_costs():
    spec = P.PortfolioSpec("T", "test", ["A", "B"], "M", lambda c, r, t, ppy: np.array([1.0, 0.0]), {}, {})
    pan = synthetic_panel(n_days=300, n=2)
    s0 = P.simulate(spec, pan, np.array([0.0, 0.0]), {}, 252.0)
    s1 = P.simulate(spec, pan, np.array([0.01, 0.01]), {}, 252.0)
    assert s1["equity"][-1] < s0["equity"][-1] and s1["costs"] > 0
    first_rb = P.rebalance_days(pan["days"], "M")[0]
    assert np.all(s0["returns"][:first_rb + 1] == 0)                    # nothing held until the day after a decision


def test_futures_portfolios_are_research_only(app):
    assert portfolio_bot.deployable(app, "ST001")[0] is False
    assert portfolio_bot.deployable(app, "ST004")[0] is True


def test_portfolio_bot_rebalances_through_the_risk_service(app, monkeypatch):
    spec = P.PORTFOLIOS["ST045"]
    pan = synthetic_panel(n=3, drift=0.004, sd=0.004)                   # every coin trending up: the template buys
    pan["status"] = {i: {"bars": 1200} for i in spec.universe}
    monkeypatch.setattr(portfolio_bot, "load_panel", lambda md, book, uni, lookback=400: pan)
    prices = {"COINBASE:BTC-USD": 60000.0, "COINBASE:ETH-USD": 3000.0, "COINBASE:SOL-USD": 150.0}
    monkeypatch.setattr(app, "quote", lambda iid: {"price": prices[iid], "ts": 0, "volume": None, "sigma": 0.0,
                                                   "range": 0.0, "simulated": True, "tf": "1m", "fresh": True,
                                                   "currency": "USD"})
    app.paper.quote = app.quote
    bot = app.create_portfolio_bot("ST045", allocation=0.2)
    app.bot_action(bot["bot_id"], "start")
    b = app.bots[bot["bot_id"]]
    rec = portfolio_bot.step(app, b, "paper")
    assert rec["outcome"] == "REBALANCE" and "BTC-USD" in rec["reason"]
    held = portfolio_bot.held_lots(app, "ST045")
    value = sum(float(q) * prices[i] for i, q in held.items())
    assert 0 < value <= 0.2 * 100_000 * 1.001                           # within the bot's allocation
    assert not b.pending                                                # every target was traded or refused
    assert portfolio_bot.step(app, b, "paper") is None                  # nothing new until the next week


# ---------------------------------------------------------------- controls and reason codes
def test_pause_entries_blocks_new_exposure_allows_exits_and_survives_restart(tmp_path):
    from tradingai.risk.service import OrderRequest, Snapshot
    home = str(tmp_path / "h")
    a = App(home, offline=True, start_loop=False, autopilot=False)
    a.pause_entries(True, "owner", "test")
    req = OrderRequest(client_order_id="X1", instrument_id="DEMO:DEMO-TREND", market="crypto", side="buy",
                       quantity=D(1), reference_price=D(100), limit_price=None, multiplier=D(1), environment="paper",
                       account_id="PAPER-1", sized_target=D(1))
    d = a.risk.check(req, Snapshot(equity=D(100_000), positions={}, data_age_s=1))
    assert not d.approved and "ENTRIES_PAUSED" in d.reason_codes
    held = {"DEMO:DEMO-TREND": {"qty": D(2), "price": D(100), "multiplier": D(1), "market": "crypto"}}
    exit_ = OrderRequest(client_order_id="X2", instrument_id="DEMO:DEMO-TREND", market="crypto", side="sell",
                         quantity=D(1), reference_price=D(100), limit_price=None, multiplier=D(1), environment="paper",
                         account_id="PAPER-1", reduces_position=True)
    assert a.risk.check(exit_, Snapshot(equity=D(100_000), positions=held, data_age_s=1)).approved
    a.shutdown()
    b = App(home, offline=True, start_loop=False, autopilot=False)
    try:
        assert b.risk.entries_paused is not None
    finally:
        b.shutdown()


def test_flatten_closes_paper_positions_and_reports_each(app, monkeypatch):
    monkeypatch.setattr(app, "quote", lambda iid: {"price": 100.0, "ts": 0, "volume": None, "sigma": 0.0, "range": 0.0})
    app.paper.quote = app.quote
    app.paper.submit_order(client_order_id="P1", instrument_id="DEMO:DEMO-TREND", side="buy", qty=D(3),
                           strategy_id="manual-test")
    out = app.flatten_all("owner")
    assert out["requested"] == 1 and out["closed"] == 1 and out["complete"]
    assert app.paper.get_positions() == {}


def test_stale_data_reason_code():
    from tradingai.risk.service import OrderRequest, RiskService, Snapshot
    req = OrderRequest(client_order_id="S1", instrument_id="A", market="crypto", side="buy", quantity=D(1),
                       reference_price=D(10), limit_price=None, multiplier=D(1), environment="paper", account_id="P")
    d = RiskService().check(req, Snapshot(equity=D(1000), positions={}, data_age_s=10_000, bar_seconds=60))
    assert d.reason_codes == ["STALE_DATA"]


# ---------------------------------------------------------------- assistant and roles
def test_assistant_answers_from_state_and_refuses_money_commands(app):
    a = app.assistant
    assert "bots are running" in a.ask("What are all the bots doing?")["answer"]
    assert a.ask("why are you not trading?")["intent"] == "why_not_trading"
    assert a.ask("How much did fees cost today?")["intent"] == "fees"
    r = a.ask("pause new entries", command_id="CMD-1")
    assert r["action"]["result"] == "completed" and app.risk.entries_paused
    again = a.ask("pause new entries", command_id="CMD-1")
    assert again.get("repeated") is True                                # a retried command is not repeated
    assert a.ask("go live with all my capital")["intent"] == "refused"
    assert a.ask("flatten everything")["intent"] == "refused"
    assert app.mode == "paper"


def test_assistant_announces_kill_switch(app):
    app.assistant.start()
    sid = app.bus.subscribe()
    app.emergency_stop("test", "owner")
    t0, got = time.time(), []
    while time.time() - t0 < 5 and not got:
        got = [e for e in app.bus.drain(sid, 0.5) if e["topic"] == "voice"]
    assert got and got[0]["data"]["severity"] == "critical" and got[0]["data"]["expires"] > got[0]["data"]["created"]


def test_roles_view_lists_25_roles_and_no_model_calls(app):
    from tradingai.engine.roles import view
    v = view(app)
    assert len(v["roles"]) == 25 and v["counts"]["active_model_calls"] == 0
    assert {r["state"] for r in v["roles"] if r["id"] == "16"} == {"blocked"}
