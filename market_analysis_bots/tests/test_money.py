"""Your money, live, and any balance: open positions are valued at the market's price right now (so the balance
moves like a real account), an older price never replaces a newer one, a failing price source never stops
anything; small accounts use fewer, larger capital slots so their orders clear venue minimums; US stocks can be
bought in fractions in paper; a huge account cannot buy more than the market trades."""

import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mab import backtest  # noqa: E402
from mab.account import Account  # noqa: E402
from mab.broker import PaperBroker  # noqa: E402
from mab.models import OrderIntent, now_ms  # noqa: E402
from mab.strategy import TradeManager, compile_strategy  # noqa: E402
from test_autopilot import make  # noqa: E402
from test_deployments import STRAT  # noqa: E402


# ------------------------------------------------------------------ live marking
def test_positions_are_valued_at_the_live_price_and_the_balance_moves(tmp_path, monkeypatch):
    fl = make(tmp_path)
    fl.account.apply_fill("R-0", "demo", "DEMO-BTC", "buy", 0.5, 60_000.0, 5.0)       # the AI bought half a coin
    assert fl.account.equity() == pytest.approx(99_995.0)                             # valued at its own buy price
    quotes = [61_000.0, 59_000.0]
    ad = fl.hub.adapters["demo"]
    monkeypatch.setattr(ad, "last_price", lambda sym: (quotes.pop(0), now_ms() + 1, "test quote"))
    fl.mark_live()
    up = fl.money_view()
    assert up["equity"] == pytest.approx(99_995.0 + 0.5 * 1_000.0)                    # +$500 as the price rose
    p = up["positions"][0]
    assert p["symbol"] == "DEMO-BTC" and p["price"] == 61_000.0 and p["price_source"] == "test quote"
    assert p["pnl"] == pytest.approx(500.0) and p["pnl_pct"] == pytest.approx(500 / 30_000 * 100)
    assert up["unrealized"] == pytest.approx(500.0) and up["invested"] == pytest.approx(30_500.0)
    fl.live_prices.clear()
    monkeypatch.setattr(ad, "last_price", lambda sym: (59_000.0, now_ms() + 2, "test quote"))
    fl.mark_live()
    down = fl.money_view()
    assert down["equity"] == pytest.approx(99_995.0 - 0.5 * 1_000.0)                  # and falls when it falls
    assert down["positions"][0]["pnl"] == pytest.approx(-500.0)


def test_only_markets_with_open_positions_are_asked_and_failures_change_nothing(tmp_path, monkeypatch):
    fl = make(tmp_path)
    asked = []
    ad = fl.hub.adapters["demo"]

    def quote(sym):
        asked.append(sym)
        raise RuntimeError("network down")
    monkeypatch.setattr(ad, "last_price", quote)
    assert fl.mark_live() == {} and asked == []                                       # nothing open: no requests at all
    fl.account.apply_fill("R-1", "demo", "DEMO-ETH", "buy", 2.0, 3_000.0, 1.0)
    eq = fl.account.equity()
    assert fl.mark_live() == {} and asked == ["DEMO-ETH"]                             # one market asked, once
    assert fl.account.equity() == pytest.approx(eq)                                    # a failed quote changes nothing
    monkeypatch.setattr(ad, "last_price", lambda s: (0.0, now_ms(), "bad"))
    assert fl.mark_live() == {}                                                        # a zero price is ignored


def test_an_older_price_never_replaces_a_newer_one():
    a = Account(10_000)
    a.apply_fill("b", "v", "X", "buy", 10.0, 100.0, 0.0)
    now = now_ms()
    a.mark("v", "X", 110.0, now)                                                       # live quote
    a.mark("v", "X", 90.0, now - 3_600_000)                                            # the close of a bar that ended an hour ago
    assert a.equity() == pytest.approx(9_000.0 + 10 * 110.0)
    a.mark("v", "X", 120.0, now + 1)
    assert a.equity() == pytest.approx(9_000.0 + 10 * 120.0)


def test_money_view_reports_todays_result_without_counting_balance_changes(tmp_path):
    fl = make(tmp_path)
    fl.risk.reset_peak(fl.account.equity())                                            # the day starts at 100,000
    fl.account.apply_fill("R-0", "demo", "DEMO-BTC", "buy", 1.0, 50_000.0, 0.0)
    fl.account.mark("demo", "DEMO-BTC", 52_000.0)
    m = fl.money_view()
    assert m["change_today"] == pytest.approx(2_000.0) and m["change_today_pct"] == pytest.approx(2.0)
    fl.set_paper_balance("paper-research", "deposit", 10_000.0)                        # the owner adds simulated money
    m = fl.money_view()
    assert m["equity"] == pytest.approx(112_000.0)
    assert m["change_today"] == pytest.approx(0.0)                                     # not counted as profit
    assert m["real_money"] is False and m["connection_id"] == "paper-research"


# ------------------------------------------------------------------ any balance
def test_small_accounts_use_fewer_larger_slots():
    assert Account(100).slot_equity() == pytest.approx(25.0) and Account(100).slots_in_use() == 4
    assert Account(499).slots_in_use() == 19 and Account(500).slots_in_use() == 20
    assert Account(1_000).slot_equity() == pytest.approx(50.0)
    assert Account(100_000).slot_equity() == pytest.approx(5_000.0)
    assert Account(10_000_000).slots_in_use() == 20
    assert Account(10).slots_in_use() == 1 and Account(10).slot_equity() == pytest.approx(10.0)
    assert Account(0.0).slot_equity() == 0.0
    a = Account(100)
    a.set_balance(2_000.0)                                                             # grows with the account
    assert a.slots_in_use() == 20 and a.slot_equity() == pytest.approx(100.0)
    assert a.summary()["slots_in_use"] == 20


def test_us_stocks_are_bought_in_fractions_in_paper_but_not_your_own_or_canadian_ones(tmp_path):
    fl = make(tmp_path)
    stock = {"venue": "yahoo", "symbol": "AAPL", "asset_type": "stock", "lot_size": 1.0, "min_qty": 1.0}
    f = fl._paper_rules(stock, user=False)
    assert f["lot_size"] == pytest.approx(1e-6) and f["min_notional"] == 1.0 and f["min_qty"] == 0.0
    assert fl._paper_rules(stock, user=True) is stock                                  # your own bots keep exact rules
    ca = {"venue": "yahoo", "symbol": "RY.TO", "asset_type": "stock_ca", "lot_size": 1.0, "min_qty": 1.0}
    assert fl._paper_rules(ca, user=False) is ca
    crypto = {"venue": "coinbase", "symbol": "BTC-USD", "asset_type": "crypto", "lot_size": 1e-8}
    assert fl._paper_rules(crypto, user=False) is crypto
    fl.cfg.setdefault("paper", {})["fractional_us_stocks"] = False
    assert fl._paper_rules(stock, user=False) is stock
    # and the paper broker really fills a $60 slice of a $300 share
    pb = PaperBroker(SimpleNamespace(adapters={}), Account(1_000), latency_ms=0, max_slippage_bps=50)
    res = pb.execute(OrderIntent("i1", "b", "s", "AAPL", "yahoo", "buy", "market", 0.2), 300.0, f)
    assert res["status"] == "filled" and res["filled_qty"] == pytest.approx(0.2)
    whole = pb.execute(OrderIntent("i2", "b", "s", "AAPL", "yahoo", "buy", "market", 0.2), 300.0, stock)
    assert whole["status"] == "rejected"                                               # a whole-share account could not


def test_a_huge_account_cannot_buy_more_than_the_market_trades():
    c = compile_strategy(STRAT, None, "crypto")
    filler = backtest.filler_for("coinbase", "BTC-USD", "crypto", 1.0, 0.0)
    f = SimpleNamespace(v=[10.0] * 30)                                                 # 10 coins per bar
    tm = TradeManager(c, filler, lambda: 10 ** 9, 1e-8, 1.0, False, "BTC-USD", max_participation=0.05)
    assert tm._liquidity_cap(100.0, f, 29) == pytest.approx(0.5)                        # 5% of 10 coins
    assert tm._liquidity_cap(0.2, f, 29) == pytest.approx(0.2)                          # small orders are untouched
    assert tm._liquidity_cap(100.0, SimpleNamespace(v=[0.0] * 30), 29) == 100.0         # no volume data: no cap
    free = TradeManager(c, filler, lambda: 10 ** 9, 1e-8, 1.0, False, "BTC-USD")
    assert free._liquidity_cap(100.0, f, 29) == 100.0                                   # the cap is optional (your own bots)
