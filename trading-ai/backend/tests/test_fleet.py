"""The trading fleet A001-A320, its brain, market discovery and the one order authority (specification revision 13,
sections 3-4). Discovery is tested against recorded-shape fake responses: no network."""

import threading
import time
from decimal import Decimal

import pytest

from tradingai.app import App
from tradingai.brokers.base import BrokerOrder
from tradingai.core.events import EventBus
from tradingai.engine.fleet import GROUPS, NO_ACCESS, TARGET
from tradingai.execution.oms import OMS
from tradingai.market import discovery as D
from tradingai.risk.service import Limits, OrderRequest, RiskService, Snapshot
from tradingai.storage.db import Database


@pytest.fixture()
def app(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    a.autopilot.cfg.screens_per_hour = 0
    a.autopilot.cfg.confirms_per_hour = 0
    yield a
    a.shutdown()


def record(app, sid, iid, tf, verdict):
    eid = app.ledger.start(family="test", strategy_id=sid, hypothesis="test", instrument=iid, tf=tf,
                           profile="STANDARD", seed=7, dataset={"simulated": True})
    app.ledger.finish(eid, {"status": "ok", "verdict": verdict, "operating_mode": "intraday", "quality": {"score": 60},
                            "test": {"trades": 40},
                            "reproducibility": {"simulated_data": True}, "checks": []})
    time.sleep(0.002)
    return eid


# ---------------------------------------------------------------- fleet
def test_320_agents_registered_with_stable_ids_and_groups(app):
    f = app.fleet
    assert len(f.agents) == TARGET == 320
    assert sorted(f.agents) == [f"A{n:03d}" for n in range(1, 321)]
    for gid, first, last, _, _ in GROUPS:
        assert sum(1 for a in f.agents.values() if a.group == gid) == last - first + 1
    c = f.counts()
    assert c["registered"] == 320 and c["configured"] == 320 and c["target"] == 320


def test_each_instrument_has_exactly_one_owner(app):
    f = app.fleet
    seen = {}
    for a in f.agents.values():
        for i in a.partition:
            assert i not in seen, f"{i} owned by {seen[i]} and {a.agent_id}"
            seen[i] = a.agent_id
    assert seen == f.owner and len(seen) > 0
    assert all(app.book.get(i).tradable for i in seen)          # an index is a reference, never owned


def test_agents_without_a_market_are_blocked_with_the_reason_not_counted_ready(app):
    app.fleet.cycle()
    v = app.fleet.view()
    for g in v["groups"]:
        if g["group"] in NO_ACCESS:
            assert g["gap"] and "PRODUCT_UNSUPPORTED" in g["gap"]
    blocked = [a for a in app.fleet.agents.values() if not a.partition]
    assert blocked and all(a.runtime == "blocked" and a.detail for a in blocked)
    assert v["counts"]["data_ready"] <= v["counts"]["assigned"] < 320
    assert v["brain"]["kind"].startswith("coordinating service")    # the brain is not counted as a trader
    assert "0 model calls" in v["brain"]["model"]


def test_assignment_is_stable_across_replans(app):
    before = {a.agent_id: list(a.partition) for a in app.fleet.agents.values()}
    out = app.fleet.assign()
    assert out["changed"] == 0
    assert {a.agent_id: list(a.partition) for a in app.fleet.agents.values()} == before


def test_one_failing_bot_does_not_stop_its_agent_or_others(app):
    class B:
        def __init__(self, bid, iid):
            self.bot_id, self.instrument_id = bid, iid
    iids = list(app.fleet.owner)[:3]
    bots = [B("ok1", iids[0]), B("bad", iids[1]), B("ok2", iids[1]), B("ok3", iids[2])]

    def fn(b):
        if b.bot_id == "bad":
            raise RuntimeError("boom")
        return b.bot_id
    assert app.fleet.run_bots(bots, fn) == ["ok1", "ok2", "ok3"]
    owner = app.fleet.agents[app.fleet.owner[iids[1]]]
    assert any("boom" in e["error"] for e in owner.errors)


def test_budgets_are_zero_until_a_strategy_qualifies_and_sum_within_the_limit(app):
    f = app.fleet
    assert all(f.budget(aid) == 0 for aid in f.agents)
    iids = [i for i in f.owner if i.startswith("DEMO:")]
    for i in iids:
        record(app, "tsmom.none.flip", i, "1h", "PAPER TEST")
    f._budget_cache = (0.0, set())
    eq = app.paper.get_balance().equity
    lim = app.risk.limits
    budgets = {aid: f.budget(aid) for aid in f.agents}
    funded = {aid for aid, b in budgets.items() if b > 0}
    assert funded == {f.owner[i] for i in iids}
    assert sum(budgets.values()) <= eq * Decimal(str(lim.max_gross_exposure))
    assert all(b <= eq * Decimal(str(lim.max_position_pct_equity)) for b in budgets.values())


def test_fleet_grows_beyond_320_and_refuses_to_shrink_an_agent_holding_a_position(app):
    f = app.fleet
    f.set_desired(330)
    assert len(f.agents) == 330 and f.agents["A330"].group == "overflow"
    assert app.db.get_setting("fleet")["desired"] == 330
    f.set_desired(320)
    assert len(f.agents) == 320
    iid = f.agents["A097"].partition[0] if f.agents["A097"].partition else next(iter(f.owner))
    aid = f.owner[iid]
    if int(aid[1:]) <= 300:
        f.set_desired(300)                          # agents above 300 hold nothing: allowed
        assert len(f.agents) == 300
    real = app.paper.get_positions
    app.paper.get_positions = lambda: {iid: Decimal(1)}
    try:
        with pytest.raises(ValueError, match="drained"):
            f.set_desired(int(aid[1:]) - 1)
    finally:
        app.paper.get_positions = real


def test_autopilot_deploys_only_on_owned_instruments(app):
    record(app, "tsmom.none.flip", "DEMO:DEMO-TREND", "1h", "PAPER TEST")
    owner = app.fleet.owner.pop("DEMO:DEMO-TREND")
    app.autopilot.cycle()
    assert not app.autopilot.bots()                 # no owning agent: nothing deployed
    app.fleet.owner["DEMO:DEMO-TREND"] = owner
    app.autopilot.cycle()
    assert [b.instrument_id for b in app.autopilot.bots()] == ["DEMO:DEMO-TREND"]


# ---------------------------------------------------------------- one order authority, atomic reservation
class FakeBroker:
    name, environment, connected = "fake", "paper", True

    def __init__(self):
        self.orders = []
        self.lock = threading.Lock()

    def get_order(self, cid):
        return None

    def submit_order(self, *, client_order_id, instrument_id, side, qty, **kw):
        time.sleep(0.005)                           # widen the race window
        with self.lock:
            self.orders.append((instrument_id, qty))
        return BrokerOrder(client_order_id, "b-" + client_order_id, instrument_id, side, qty, Decimal(0), None, "NEW")


def test_concurrent_agents_cannot_overspend_through_the_order_authority(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    risk = RiskService(Limits(max_order_pct_equity=0.2, max_position_pct_equity=0.2, max_gross_exposure=0.5,
                              max_open_positions=100, max_orders_per_minute=100,
                              max_asset_class_pct={"crypto": 5.0}))
    oms = OMS(db, risk, EventBus(), lambda *a, **k: None)
    broker = FakeBroker()

    def positions(_):
        with broker.lock:
            return {i: {"qty": q, "price": Decimal(100), "multiplier": Decimal(1), "market": "crypto"}
                    for i, q in broker.orders}
    oms.refresh_positions = positions
    results = []

    def agent(n):
        req = OrderRequest(client_order_id="", instrument_id=f"X:{n}", market="crypto", side="buy", quantity=Decimal(100),
                           reference_price=Decimal(100), limit_price=None, multiplier=Decimal(1), environment="paper",
                           account_id="paper")
        out = oms.place(decision_id=f"D{n}", req=req, snapshot=Snapshot(equity=Decimal(100_000), positions={}),
                        broker=broker, broker_symbol=f"X{n}", mode="paper", strategy_id=None, decided_at=time.time())
        results.append(out["status"])
    ts = [threading.Thread(target=agent, args=(n,)) for n in range(16)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    # each order is 10% of equity; gross exposure is capped at 50%: exactly five can be reserved
    assert results.count("NEW") == 5 and results.count("BLOCKED_BY_RISK") == 11
    assert len(broker.orders) == 5


def test_agent_budget_check_denies_entries_but_not_exits():
    risk = RiskService(Limits(max_open_positions=100))
    base = dict(instrument_id="X:1", market="crypto", reference_price=Decimal(100), limit_price=None,
                multiplier=Decimal(1), environment="paper", account_id="paper", agent_id="A101",
                agent_budget=Decimal(500), agent_instruments=("X:1",))
    snap = Snapshot(equity=Decimal(100_000), positions={"X:1": {"qty": Decimal(4), "price": Decimal(100),
                                                                "multiplier": Decimal(1), "market": "crypto"}})
    d = risk.check(OrderRequest(client_order_id="c1", side="buy", quantity=Decimal(2), **base), snap)
    assert not d.approved and "agent budget" in d.reason
    assert risk.check(OrderRequest(client_order_id="c2", side="buy", quantity=Decimal(1), **base), snap).approved
    snap.positions["X:1"]["qty"] = Decimal(9)
    exit_ = risk.check(OrderRequest(client_order_id="c3", side="sell", quantity=Decimal(9),
                                      reduces_position=True, **base), snap)
    assert exit_.approved


# ---------------------------------------------------------------- discovery (fake provider responses)
class FakeHttp:
    def __init__(self):
        self.products = [
            {"id": "BTC-USD", "base_currency": "BTC", "quote_currency": "USD", "status": "online",
             "quote_increment": "0.01", "base_increment": "0.00000001"},
            {"id": "DOGE-USD", "base_currency": "DOGE", "quote_currency": "USD", "status": "online",
             "quote_increment": "0.00001", "base_increment": "0.1"},
            {"id": "PEPE-USD", "base_currency": "PEPE", "quote_currency": "USD", "status": "online",
             "quote_increment": "0.00000001", "base_increment": "1"},
            {"id": "OLD-USD", "base_currency": "OLD", "quote_currency": "USD", "status": "online",
             "trading_disabled": True},
            {"id": "ETH-EUR", "base_currency": "ETH", "quote_currency": "EUR", "status": "online"},
        ]
        self.calls = []

    def get_json(self, url):
        self.calls.append(url)
        if url == D.COINBASE_PRODUCTS:
            return self.products
        if url == D.KRAKEN_PAIRS:
            return {"result": {"XDGUSD": {"base": "XXDG", "quote": "ZUSD", "altname": "XDGUSD", "status": "online"}}}
        if url == D.COINBASE_STATS:
            return {"BTC-USD": {"stats_24hour": {"last": "60000", "open": "59000", "volume": "1000"}},
                    "DOGE-USD": {"stats_24hour": {"last": "0.1", "open": "0.1", "volume": "5000000"}},
                    "PEPE-USD": {"stats_24hour": {"last": "0.00001", "open": "0.00001", "volume": "1"}}}
        if url == D.KRAKEN_TICKER:
            return {"result": {"XDGUSD": {"c": ["0.1", "1"], "o": "0.1", "v": ["1", "900000"]}}}
        raise AssertionError(url)


def test_discovery_inventory_snapshot_meme_tags_and_delisting(app):
    http = FakeHttp()
    app.md.http = http
    d = app.discovery
    assert d.refresh_listings() == {"COINBASE": 5, "KRAKEN": 1}
    assert d.snapshot() == 4 and d.version == 1
    rows = {r["symbol"]: r for r in d.listed("COINBASE")}
    assert rows["OLD-USD"]["status"] == "disabled"                  # trading disabled is not "online"
    elig = [r["symbol"] for r in d.listed() if d.execution_eligible(r)]
    assert sorted(elig) == ["BTC-USD", "DOGE-USD", "PEPE-USD"]       # online Coinbase USD pairs only
    assert [r["symbol"] for r in d.tradable_crypto(2)] == ["BTC-USD", "DOGE-USD"]   # most liquid first
    cov = d.coverage()
    assert cov["venues"]["COINBASE"]["listed"] == 5 and cov["venues"]["KRAKEN"]["listed"] == 1
    assert cov["venues"]["COINBASE"]["snapshot_fresh"] == 3 and cov["venues"]["COINBASE"]["stale_or_missing"] == 2
    memes = {(m["venue"], m["base"]) for m in cov["meme"]["pairs"]}
    assert memes == {("COINBASE", "DOGE"), ("COINBASE", "PEPE"), ("KRAKEN", "XXDG")}   # Kraken's DOGE code mapped
    assert all("unverified" in m["confidence"] for m in cov["meme"]["pairs"])
    assert cov["uncovered"] and "not every market" in cov["denominator"]
    # a pair that disappears from the listing is kept and marked delisted
    http.products = [p for p in http.products if p["id"] != "PEPE-USD"]
    d.refresh_listings()
    pepe = {r["symbol"]: r for r in d.listed("COINBASE")}["PEPE-USD"]
    assert pepe["status"] == "delisted" and pepe["delisted"]
    assert d.coverage()["venues"]["COINBASE"]["delisted"] == 1


def test_discovered_pairs_are_owned_by_crypto_agents_when_online(app):
    app.md.http = FakeHttp()
    app.discovery.refresh_listings()
    app.discovery.snapshot()
    app.offline = False
    try:
        app.fleet.assign()
        owner = app.fleet.owner.get("COINBASE:DOGE-USD")
        assert owner and app.fleet.agents[owner].group in ("crypto",) + NO_ACCESS
        inst = app.book.get("COINBASE:DOGE-USD")
        assert "discovered" in inst.tags and app.sources["COINBASE:DOGE-USD"].provider == "coinbase"
        assert not any(i.startswith("DEMO:") for i in app.fleet.owner)    # demo markets only in offline mode
        assert len(set(app.fleet.owner.values())) == len(app.fleet.owner)
    finally:
        app.offline = True


def test_discovery_is_off_in_offline_mode(app):
    app.discovery.start()
    assert app.discovery._thread is None and "offline" in app.discovery.status()


class ManyPairs(FakeHttp):
    def __init__(self, n=400):
        super().__init__()
        self.products = [{"id": f"C{k:03d}-USD", "base_currency": f"C{k:03d}", "quote_currency": "USD",
                          "status": "online", "quote_increment": "0.01", "base_increment": "0.001"} for k in range(n)]

    def get_json(self, url):
        if url == D.COINBASE_STATS:
            return {p["id"]: {"stats_24hour": {"last": "1", "open": "1", "volume": str(1000 + i)}}
                    for i, p in enumerate(self.products)}
        return super().get_json(url)


def test_every_agent_gets_a_distinct_market_when_enough_pairs_are_listed(app):
    app.md.http = ManyPairs()
    app.discovery.refresh_listings()
    app.discovery.snapshot()
    app.offline = False
    try:
        app.fleet.assign()
        f = app.fleet
        assert all(a.partition for a in f.agents.values())                    # 320 of 320 have a market
        owned = [i for a in f.agents.values() for i in a.partition]
        assert len(owned) == 320 and len(set(owned)) == 320                  # all different
        eq = [a for a in f.agents.values() if a.group == "equities"]
        assert all(app.book.get(a.partition[0]).market_type.name in ("STOCK", "ETF") for a in eq)
        groups = {g["group"]: g for g in f._groups()}
        assert groups["fx"]["reassigned"] == 27 and groups["fx"]["gap"]      # moved agents keep the gap visible
        app.fleet.cycle()
        assert app.fleet.counts()["blocked"] == 0
    finally:
        app.offline = True
