from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from quantagents.config import CostConfig
from quantagents.execution.paper import Book, Ledger, PaperAccount, PaperBroker, reconcile
from quantagents.lots import acb_report
from quantagents.market import Bar
from quantagents.schemas import Fill, OrderSide
from tests.helpers import intent

D1, D2, D3 = date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)
COSTS = CostConfig(fee_bps=10, slippage_bps=5)


def fill(
    side: OrderSide,
    qty: float,
    price: float,
    *,
    fid: str = "F1",
    day: date = D1,
    fee: float = 0.0,
    symbol: str = "AAA",
) -> Fill:
    return Fill(
        fill_id=fid,
        intent_id="I",
        symbol=symbol,
        side=side,
        qty=qty,
        price=price,
        fee=fee,
        trade_date=day,
        kind="entry",
    )


def test_book_average_cost_and_realized_pnl() -> None:
    book = Book(1_000.0)
    book.apply(fill(OrderSide.BUY, 10, 10.0, fee=1.0))
    book.apply(fill(OrderSide.BUY, 10, 12.0))
    assert book.positions["AAA"].qty == 20 and book.positions["AAA"].avg_price == pytest.approx(
        11.0
    )
    book.apply(fill(OrderSide.SELL, 5, 13.0))
    assert book.realized_pnl == pytest.approx(10.0)
    book.apply(fill(OrderSide.SELL, 25, 14.0))  # flips to a 10-share short at 14
    assert book.positions["AAA"].qty == -10 and book.positions["AAA"].avg_price == 14.0
    assert book.realized_pnl == pytest.approx(10.0 + 15 * 3.0)
    book.apply(fill(OrderSide.BUY, 10, 15.0))
    assert "AAA" not in book.positions and book.realized_pnl == pytest.approx(55.0 - 10.0)
    assert book.cash == pytest.approx(1_000 - 1 - 100 - 120 + 65 + 350 - 150)
    assert book.equity({}) == pytest.approx(book.cash)
    book.apply(fill(OrderSide.BUY, 2, 10.0))
    assert book.equity({"AAA": 20.0}) == pytest.approx(book.cash + 40.0)
    assert book.equity({}) == pytest.approx(book.cash + 20.0)  # falls back to cost


def test_ledger_is_idempotent() -> None:
    ledger = Ledger(1_000.0)
    f = fill(OrderSide.BUY, 1, 10.0)
    assert ledger.record(f) and not ledger.record(f)
    state = ledger.state({"AAA": 11.0})
    assert (
        state.n_fills == 1
        and state.positions == {"AAA": 1.0}
        and state.equity == pytest.approx(1_001.0)
    )


def test_broker_fills_at_next_open_with_costs() -> None:
    broker = PaperBroker(10_000.0, COSTS)
    broker.submit([intent(qty=10, stop=95.0)], D1)
    assert broker.fill_pending({"AAA": 100.0}, D1) == []  # never on the decision day
    assert broker.fill_pending({}, D2) == []  # no price yet: stays queued
    fills = broker.fill_pending({"AAA": 100.0}, D2)
    assert len(fills) == 1 and broker.pending == []
    f = fills[0]
    assert f.price == pytest.approx(100.05) and f.fee == pytest.approx(10 * 100.05 * 0.001)
    assert f.kind == "entry" and broker.stops == {"AAA": 95.0}
    broker.submit([intent(side=OrderSide.SELL, qty=10, stop=None, intent_id="I2")], D2)
    exit_fill = broker.fill_pending({"AAA": 110.0}, D3)[0]
    assert exit_fill.kind == "exit" and exit_fill.price == pytest.approx(110 * 0.9995)
    assert broker.stops == {} and broker.book.positions == {}


def test_stops_trigger_and_gap() -> None:
    broker = PaperBroker(10_000.0, COSTS)
    broker.submit(
        [intent(qty=10, stop=95.0), intent("BBB", qty=5, ref=50.0, stop=48.0, intent_id="I2")], D1
    )
    broker.fill_pending({"AAA": 100.0, "BBB": 50.0}, D2)
    untouched = broker.check_stops(
        {"AAA": Bar(100, 101, 96, 99, 1e5), "BBB": Bar(50, 51, 49, 50, 1e5)}, D3
    )
    assert untouched == []
    gapped = broker.check_stops(
        {"AAA": Bar(90, 91, 89, 90, 1e5), "BBB": Bar(49, 49.5, 47.5, 48, 1e5)}, D3
    )
    by = {f.symbol: f for f in gapped}
    assert by["AAA"].price == pytest.approx(
        90 * 0.9995
    )  # gapped below the stop: filled at the open
    assert by["BBB"].price == pytest.approx(48 * 0.9995)
    assert all(f.kind == "stop" for f in gapped) and broker.stops == {}
    assert broker.check_stops({}, D3) == []


def test_short_stop_and_missing_bar() -> None:
    broker = PaperBroker(10_000.0, COSTS)
    broker.submit([intent(side=OrderSide.SELL, qty=5, stop=105.0)], D1)
    broker.fill_pending({"AAA": 100.0}, D2)
    assert broker.check_stops({"AAA": Bar(float("nan"), 1, 1, 1, 1)}, D3) == []
    assert broker.check_stops({"AAA": Bar(101, 104, 100, 102, 1e5)}, D3) == []
    f = broker.check_stops({"AAA": Bar(103, 106, 102, 105.5, 1e5)}, D3)[0]
    assert f.side is OrderSide.BUY and f.price == pytest.approx(105 * 1.0005)


def test_reconciliation_detects_breaks() -> None:
    account = PaperAccount(10_000.0, COSTS)
    account.broker.submit([intent(qty=10, stop=95.0)], D1)
    fills = account.broker.fill_pending({"AAA": 100.0}, D2)
    assert not reconcile(account.ledger, account.broker).ok  # ledger has not seen the fill yet
    account.ledger.record(fills[0])
    report = reconcile(account.ledger, account.broker)
    assert report.ok and report.diffs == ()
    account.ledger.book.cash += 5.0
    assert any("cash" in d for d in reconcile(account.ledger, account.broker).diffs)


def test_account_state_roundtrip_and_loss_metrics(tmp_path: Path) -> None:
    account = PaperAccount(10_000.0, COSTS)
    account.broker.submit([intent(qty=10, stop=95.0)], D1)
    for f in account.broker.fill_pending({"AAA": 100.0}, D2):
        account.ledger.record(f)
    account.broker.submit([intent("BBB", qty=3, ref=50.0, stop=48.0, intent_id="I9")], D2)
    account.record_equity(D1, 10_000.0)
    account.record_equity(D2, 9_900.0)
    account.record_equity(D2, 9_800.0)  # same day replaces
    path = tmp_path / "account.json"
    account.save(path)
    loaded = PaperAccount.load_or_new(path, 10_000.0, COSTS)
    assert loaded.to_json() == account.to_json()
    assert reconcile(loaded.ledger, loaded.broker).ok
    assert PaperAccount.load_or_new(tmp_path / "none.json", 5.0, COSTS).capital == 5.0
    daily, weekly, drawdown = loaded.loss_metrics(D3, 9_604.0)
    assert daily == pytest.approx(2.0) and drawdown == pytest.approx(3.96)
    assert weekly == pytest.approx(
        3.96
    )  # no earlier week on record: measured from starting capital
    assert PaperAccount(1_000.0, COSTS).loss_metrics(D1, 1_100.0) == (0.0, 0.0, 0.0)
    later = loaded.loss_metrics(date(2026, 10, 6), 9_500.0)
    assert later[1] == pytest.approx((9_800 - 9_500) / 9_800 * 100)


def test_acb_report_and_superficial_loss_flag() -> None:
    fills = [
        fill(OrderSide.BUY, 10, 10.0, fid="F1", day=date(2026, 1, 5), fee=1.0),
        fill(OrderSide.SELL, 5, 8.0, fid="F2", day=date(2026, 1, 20), fee=0.5),
        fill(OrderSide.BUY, 5, 7.0, fid="F3", day=date(2026, 2, 3)),
        fill(OrderSide.SELL, 10, 12.0, fid="F4", day=date(2026, 6, 1)),
        fill(OrderSide.SELL, 2, 12.0, fid="F5", day=date(2026, 6, 2), symbol="BBB"),
    ]
    report = acb_report(fills)
    first, second = report.dispositions
    assert first.acb == pytest.approx(50.5) and first.proceeds == pytest.approx(39.5)
    assert first.gain < 0 and first.possible_superficial_loss
    assert second.qty == 10 and not second.possible_superficial_loss
    assert report.holdings_qty == {} and len(report.skipped_short_sales) == 1
    partly_short = acb_report(
        [fill(OrderSide.BUY, 2, 10.0, fid="G1"), fill(OrderSide.SELL, 3, 11.0, fid="G2")]
    )
    assert (
        partly_short.dispositions[0].qty == 2
        and "short part" in partly_short.skipped_short_sales[0]
    )
