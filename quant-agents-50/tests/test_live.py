"""The real-money mirror (Phase 8), against a fake exchange. No test touches a real account."""

from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from quantagents import alerts, envfile
from quantagents.config import LIVE_APPROVAL_ENV, LIVE_APPROVAL_TOKEN, AppConfig
from quantagents.execution import live
from quantagents.execution.paper import PaperAccount
from quantagents.risk.killswitch import KillSwitch
from quantagents.schemas import Fill, OrderSide

TODAY = date(2026, 10, 6)
BTC, ETH = "BTC-CAD.KRAKEN", "ETH-CAD.KRAKEN"
APPROVED_ROW = "| 2026-10-01 | Approve Phase 8 micro-live | Test Owner |\n"
SECRET = "s3cr3t-value-xyz"


class FakeExchange:
    """Fills, balances and order states like a CCXT client, in memory."""

    def __init__(
        self,
        *,
        bid: float = 100.0,
        ask: float = 100.2,
        cash: float = 500.0,
        coins: dict[str, float] | None = None,
        fill: str = "full",
    ) -> None:
        self.bid, self.ask, self.cash, self.fill = bid, ask, cash, fill
        self.coins = dict(coins or {})
        self.orders: dict[str, dict[str, Any]] = {}
        self.cancelled: list[str] = []
        self.fail_on_create: Exception | None = None

    def load_markets(self) -> dict[str, Any]:
        limits = {"amount": {"min": 0.0001}, "cost": {"min": 5.0}}
        return {"BTC/CAD": {"limits": limits}, "ETH/CAD": {"limits": limits}}

    def fetch_balance(self) -> dict[str, Any]:
        both = {"CAD": self.cash, **self.coins}
        return {"free": dict(both), "total": dict(both)}

    def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        return {"bid": self.bid, "ask": self.ask}

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        value = math.floor(amount * 1e6) / 1e6
        if value <= 0:
            raise ValueError("amount must be greater than the minimum precision")
        return f"{value:.6f}"

    def price_to_precision(self, symbol: str, price: float) -> str:
        return f"{price:.2f}"

    def create_order(
        self, symbol: str, type: str, side: str, amount: float, price: float | None = None
    ) -> dict[str, Any]:
        if self.fail_on_create is not None:
            raise self.fail_on_create
        assert type == "limit" and price is not None
        oid = f"o{len(self.orders) + 1}"
        filled = {"full": amount, "half": amount / 2, "none": 0.0}[self.fill]
        base = symbol.split("/")[0]
        if side == "buy":
            self.cash -= filled * price
            self.coins[base] = self.coins.get(base, 0.0) + filled
        else:
            self.cash += filled * price
            self.coins[base] = self.coins.get(base, 0.0) - filled
        self.orders[oid] = {
            "id": oid,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "filled": filled,
            "average": price if filled else None,
            "status": "closed" if self.fill == "full" else "open",
            "fee": {"cost": round(filled * price * 0.0026, 6), "currency": "CAD"},
        }
        return {"id": oid}

    def fetch_order(self, id: str, symbol: str | None = None) -> dict[str, Any]:
        return dict(self.orders[id])

    def cancel_order(self, id: str, symbol: str | None = None) -> dict[str, Any]:
        self.cancelled.append(id)
        self.orders[id]["status"] = "canceled"
        return {}


def armed_config(budget: float = 200.0, **live_extra: Any) -> AppConfig:
    return AppConfig.model_validate(
        {
            "system": {
                "execution_mode": "live",
                "autonomy_level": 3,
                "live_trading_approved": True,
            },
            "universe": {"asset_class": "crypto_spot", "symbols": [BTC, ETH]},
            "risk": {"quantity_step": 0.0001},
            "live": {"budget": budget, "order_timeout_seconds": 5, **live_extra},
        }
    )


def paper_config(budget: float = 200.0) -> AppConfig:
    return AppConfig.model_validate(
        {
            "universe": {"asset_class": "crypto_spot", "symbols": [BTC, ETH]},
            "live": {"budget": budget},
        }
    )


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A folder with an approved STATUS row, keys, today's paper cycle and a 20% BTC position."""
    monkeypatch.setenv(LIVE_APPROVAL_ENV, LIVE_APPROVAL_TOKEN)
    monkeypatch.setenv(live.KEY_ENV, "key-abc-123")
    monkeypatch.setenv(live.SECRET_ENV, SECRET)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "STATUS.md").write_text(
        "## Human approvals\n\n| Date | Decision | Owner |\n|---|---|---|\n" + APPROVED_ROW,
        encoding="utf-8",
    )
    write_cycle(tmp_path, date(2026, 10, 5), "NORMAL", {BTC: 100.0, ETH: 50.0})
    account = PaperAccount(10_000.0, AppConfig().costs)
    fill = Fill(
        fill_id="f1", intent_id="i1", symbol=BTC, side=OrderSide.BUY, qty=20.0, price=100.0,
        fee=0.0, trade_date=date(2026, 10, 1), kind="entry",
    )  # fmt: skip
    account.ledger.record(fill)
    account.broker.book.apply(fill)
    account.save(tmp_path / "state" / "paper_account.json")
    return tmp_path


def write_cycle(home: Path, as_of: date, level: str, prices: dict[str, float]) -> None:
    cycles = home / "runs" / "cycles"
    cycles.mkdir(parents=True, exist_ok=True)
    body = {
        "as_of": as_of.isoformat(),
        "risk": {"level": level},
        "snapshot": {"last_close": prices},
    }
    (cycles / f"c-{as_of.isoformat()}.json").write_text(json.dumps(body), encoding="utf-8")


def paths(home: Path) -> dict[str, Any]:
    return {
        "today": TODAY,
        "state_file": home / "state" / "paper_account.json",
        "kill_file": home / "state" / "kill_switch.json",
        "runs_dir": home / "runs",
        "status_file": home / "docs" / "STATUS.md",
        "ccxt_installed": True,
    }


def sync(
    home: Path, fake: FakeExchange, cfg: AppConfig | None = None, *, dry_run: bool = False
) -> tuple[int, str]:
    out: list[str] = []
    ticks = iter(range(10_000))
    code = live.run_sync(
        cfg or armed_config(),
        dry_run=dry_run,
        connect=lambda exchange_id: fake,
        say=out.append,
        sleep=lambda seconds: None,
        clock=lambda: float(next(ticks)),
        **paths(home),
    )
    return code, "\n".join(out)


def ledger(home: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (home / "state" / "live_ledger.json").read_text(encoding="utf-8")
    )
    return data


def test_everything_is_closed_by_default(tmp_path: Path) -> None:
    fake = FakeExchange()
    checks = live.gates(
        AppConfig(),
        status_file=tmp_path / "STATUS.md",
        kill_file=tmp_path / "kill.json",
        runs_dir=tmp_path / "runs",
        today=TODAY,
        ccxt_installed=True,
    )
    closed = {g.name for g in checks if not g.ok}
    assert closed == {g.name for g in checks} - {"ccxt installed", "kill switch armed"}
    out: list[str] = []
    code = live.run_sync(
        AppConfig(),
        dry_run=False,
        connect=lambda exchange_id: fake,
        say=out.append,
        **{**paths(tmp_path), "status_file": tmp_path / "STATUS.md"},
    )
    assert code == 3 and "REFUSED" in out[0] and not fake.orders
    assert any("Real money box, step 2" in line for line in out)  # says where to switch on


def test_the_approval_row_must_be_dated_and_signed(home: Path) -> None:
    status = home / "docs" / "STATUS.md"
    for text in (
        "| (none yet) | | |\n",
        "YYYY-MM-DD | Approve Phase 8 micro-live | <owner name>\n",
        "| 2026-10-01 | Approve Phase 8 micro-live | <owner name> |\n",
        "| 2026-10-01 | Approve Phase 3 schedule | Test Owner |\n",
    ):
        status.write_text(text, encoding="utf-8")
        assert not live.APPROVAL_ROW.search(text)
        assert sync(home, FakeExchange())[0] == 3
    status.write_text(APPROVED_ROW, encoding="utf-8")
    assert sync(home, FakeExchange())[0] == 0


def test_armed_sync_buys_the_paper_weight_of_the_budget(home: Path) -> None:
    fake = FakeExchange()
    code, out = sync(home, fake)
    assert code == 0, out
    (order,) = fake.orders.values()
    assert order["side"] == "buy" and order["symbol"] == "BTC/CAD"
    assert order["price"] == pytest.approx(100.2 * 1.005, abs=0.01)  # ask + 0.5% at most
    assert order["amount"] * order["price"] == pytest.approx(0.20 * 200.0, rel=1e-3)
    assert "paper weight 20.0% -> target 40.00 CAD" in out and "BOUGHT" in out
    book = ledger(home)
    assert book["qty"] == {BTC: pytest.approx(order["amount"])} and not book["pending"]
    assert book["trades"][0]["side"] == "buy"
    # a second run finds nothing to do: the mirror already matches the paper portfolio
    code, out = sync(home, fake)
    assert code == 0 and len(fake.orders) == 1 and "No orders needed" in out


def test_an_alert_when_a_loss_limit_is_75_percent_used(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    def fake_send(text: str, **kwargs: object) -> bool:
        sent.append(text)
        return True

    monkeypatch.setattr(alerts, "send", fake_send)
    state = home / "state" / "paper_account.json"
    account = PaperAccount.load_or_new(state, 10_000.0, AppConfig().costs)
    account.record_equity(date(2026, 9, 1), 11_364.0)  # the peak: today is 12% below it
    account.record_equity(date(2026, 10, 2), 10_000.0)  # flat since last week
    account.save(state)
    code, out = sync(home, FakeExchange())
    assert code == 0 and "WARNING" in out and "used 80% of a loss limit" in out
    assert "drawdown 12.00% of 15%" in out
    assert any(s.startswith("Limit warning") for s in sent) and any("real fill" in s for s in sent)


def test_large_targets_are_split_over_runs(home: Path) -> None:
    fake = FakeExchange()
    sync(home, fake, armed_config(budget=1000.0, max_order_value=50.0))
    (order,) = fake.orders.values()
    assert order["amount"] * order["price"] == pytest.approx(50.0, rel=1e-3)


def test_sells_come_first_and_only_what_the_mirror_bought(home: Path) -> None:
    live.LiveLedger("kraken", {ETH: 1.0}).save(home / "state" / "live_ledger.json")
    fake = FakeExchange(bid=50.0, ask=50.1, coins={"ETH": 5.0})  # the owner holds 4 more ETH
    write_cycle(home, date(2026, 10, 5), "NORMAL", {BTC: 50.0, ETH: 50.0})
    code, out = sync(home, fake)
    assert code == 0, out
    first, second = fake.orders.values()
    assert (first["side"], first["symbol"], first["amount"]) == ("sell", "ETH/CAD", 1.0)
    assert first["price"] == pytest.approx(50.0 * 0.995, abs=0.01)
    assert second["side"] == "buy"
    assert fake.coins["ETH"] == pytest.approx(4.0)  # the owner's own coins are untouched
    assert ETH not in ledger(home)["qty"]


def test_a_reconciliation_break_stops_everything(home: Path) -> None:
    live.LiveLedger("kraken", {BTC: 1.0}).save(home / "state" / "live_ledger.json")
    fake = FakeExchange(coins={"BTC": 0.5})
    code, out = sync(home, fake)
    assert code == 1 and not fake.orders
    switch = KillSwitch(home / "state" / "kill_switch.json").state()
    assert switch.engaged and "ReconciliationBreak" in switch.reason and switch.by == "live"
    assert "kill switch is ENGAGED" in out
    # and nothing more is sent until the owner has reviewed and reset it
    assert sync(home, FakeExchange(coins={"BTC": 1.0}))[0] == 3


def test_rounding_dust_is_trimmed_not_a_break(home: Path) -> None:
    live.LiveLedger("kraken", {BTC: 0.4}).save(home / "state" / "live_ledger.json")
    code, _ = sync(home, FakeExchange(coins={"BTC": 0.3995}))
    assert code == 0
    assert not KillSwitch(home / "state" / "kill_switch.json").engaged


def test_unfilled_orders_are_cancelled_after_the_timeout(home: Path) -> None:
    fake = FakeExchange(fill="none")
    code, out = sync(home, fake)
    assert code == 0 and fake.cancelled == ["o1"]
    assert "nothing filled" in out and ledger(home)["qty"] == {} and not ledger(home)["pending"]


def test_a_partial_fill_books_only_what_filled(home: Path) -> None:
    fake = FakeExchange(fill="half")
    sync(home, fake)
    order = fake.orders["o1"]
    assert fake.cancelled == ["o1"]
    assert ledger(home)["qty"][BTC] == pytest.approx(order["amount"] / 2)


def test_a_fee_charged_in_the_coin_is_booked() -> None:
    book = live.LiveLedger("kraken")
    order = {"id": "x", "filled": 1.0, "average": 10.0, "fee": {"cost": 0.01, "currency": "BTC"}}
    book.settle(order, BTC, "buy")
    assert book.qty[BTC] == pytest.approx(0.99)
    book.settle({**order, "filled": 0.5}, BTC, "sell")
    assert book.qty[BTC] == pytest.approx(0.48)


def test_buys_need_the_price_inside_the_band(home: Path) -> None:
    fake = FakeExchange(bid=120.0, ask=120.2)  # 20% above the paper close of 100
    code, out = sync(home, fake)
    assert code == 0 and not fake.orders and "buy skipped" in out and "band 5%" in out


def test_buys_are_capped_by_free_cash(home: Path) -> None:
    fake = FakeExchange(cash=20.0)
    sync(home, fake)
    (order,) = fake.orders.values()
    assert order["amount"] * order["price"] <= 20.0 * 0.99 + 1e-9
    fake = FakeExchange(cash=1.0)
    home.joinpath("state", "live_ledger.json").unlink()
    code, out = sync(home, fake)
    assert code == 0 and not fake.orders and "not enough free CAD" in out


def test_any_error_engages_the_kill_switch_and_hides_secrets(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    def fake_send(text: str, **kwargs: object) -> bool:
        sent.append(text)
        return True

    monkeypatch.setattr(alerts, "send", fake_send)
    fake = FakeExchange()
    fake.fail_on_create = RuntimeError(f"invalid signature for secret {SECRET}")
    code, out = sync(home, fake)
    assert code == 1 and SECRET not in out and "***" in out
    assert KillSwitch(home / "state" / "kill_switch.json").engaged
    assert sent and "HALT" in sent[0] and SECRET not in sent[0]


def test_an_order_left_by_a_crash_is_settled_before_anything_else(home: Path) -> None:
    fake = FakeExchange()
    fake.create_order("BTC/CAD", "limit", "buy", 0.1, 100.0)  # sent, then the computer died
    book = live.LiveLedger(
        "kraken", {}, [{"id": "o1", "symbol": BTC, "pair": "BTC/CAD", "side": "buy"}]
    )
    book.save(home / "state" / "live_ledger.json")
    code, out = sync(home, fake)
    assert code == 0 and "Settled an earlier order: BOUGHT 0.1" in out
    assert ledger(home)["qty"][BTC] > 0.1 and not ledger(home)["pending"]


def test_the_preview_sends_nothing_and_needs_only_the_keys(home: Path) -> None:
    fake = FakeExchange()
    code, out = sync(home, fake, paper_config(), dry_run=True)
    assert code == 0 and not fake.orders
    assert "Would BUY" in out and "Preview only: nothing was sent" in out
    assert not (home / "state" / "live_ledger.json").exists()


def test_a_halted_or_stale_paper_cycle_blocks_real_orders(home: Path) -> None:
    write_cycle(home, date(2026, 10, 5), "HALTED", {BTC: 100.0, ETH: 50.0})
    code, out = sync(home, FakeExchange())
    assert code == 3 and "HALTED" in out
    write_cycle(home, date(2026, 9, 20), "NORMAL", {BTC: 100.0, ETH: 50.0})
    (home / "runs" / "cycles" / "c-2026-10-05.json").unlink()
    code, out = sync(home, FakeExchange())
    assert code == 3 and "too old" in out


def test_the_test_order_rests_under_the_market_and_is_cancelled(home: Path) -> None:
    fake = FakeExchange(fill="none")
    out: list[str] = []
    code = live.run_test_order(
        armed_config(), connect=lambda e: fake, say=out.append, **paths(home)
    )
    assert code == 0, out
    (order,) = fake.orders.values()
    assert order["price"] == pytest.approx(80.0) and order["side"] == "buy"
    assert fake.cancelled == ["o1"] and ledger(home)["qty"] == {}
    assert "can place and cancel orders" in "\n".join(out)


def test_check_lists_every_gate(home: Path) -> None:
    armed, lines = live.check_lines(armed_config(), connect=lambda e: FakeExchange(), **paths(home))
    text = "\n".join(lines)
    assert armed and "Real money is ARMED" in text and "[--]" not in text
    assert "Connected to kraken (read only): free CAD 500.00" in text and SECRET not in text
    armed, lines = live.check_lines(
        paper_config(budget=0), connect=lambda e: FakeExchange(), **paths(home)
    )
    text = "\n".join(lines)
    assert not armed and "Real money is OFF: 4 of 11 gates closed" in text
    assert "[--] config: execution_mode live" in text


def test_venue_needs_one_exchange_and_one_currency() -> None:
    assert isinstance(live.venue(["SPY", BTC]), str)
    assert "one exchange" in str(live.venue([BTC, "ETH-CAD.NDAX"]))
    assert "one quote currency" in str(live.venue([BTC, "ETH-USD.KRAKEN"]))
    assert "supports kraken in this version, not ndax" in str(live.venue(["ETH-CAD.NDAX"]))
    where = live.venue([BTC, ETH])
    assert isinstance(where, live.Venue) and where.exchange == "kraken" and where.quote == "CAD"
    assert where.pairs == {BTC: "BTC/CAD", ETH: "ETH/CAD"}


def test_weights_follow_the_paper_orders_still_queued(home: Path) -> None:
    from quantagents.schemas import OrderIntent

    account = PaperAccount.load_or_new(
        home / "state" / "paper_account.json", 1.0, AppConfig().costs
    )
    sell = OrderIntent(
        intent_id="i2", decision_id=None, symbol=BTC, side=OrderSide.SELL, qty=20.0,
        ref_price=100.0, reason="exit",
    )  # fmt: skip
    assert live.decided_weights(account, {BTC: 100.0}, 0.25) == {BTC: pytest.approx(0.2)}
    account.broker.submit([sell], date(2026, 10, 5))
    assert live.decided_weights(account, {BTC: 100.0}, 0.25) == {}
    with pytest.raises(ValueError, match="no price"):
        live.decided_weights(
            PaperAccount.load_or_new(home / "state" / "paper_account.json", 1.0, AppConfig().costs),
            {},
            1.0,
        )


def test_nothing_can_move_money_off_the_exchange(repo_root: Path) -> None:
    calls = re.compile(r"\.(withdraw|transfer|fetch_deposit_address)\w*\(")
    for path in (repo_root / "src").rglob("*.py"):
        assert not calls.search(path.read_text(encoding="utf-8")), path


def test_env_file_is_read_without_overriding_or_printing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / ".env"
    path.write_text(
        "# comment\nexport A_KEY=one\nB_KEY = 'two words'\nC_KEY=\nD_KEY=\"x\"\nnot a line\n",
        encoding="utf-8",
    )
    env = {"D_KEY": "kept"}
    assert envfile.load(path, env) == ["A_KEY", "B_KEY"]
    assert env == {"A_KEY": "one", "B_KEY": "two words", "D_KEY": "kept"}
    assert envfile.load(tmp_path / "missing.env", env) == []
    assert capsys.readouterr().out == ""


def test_alerts_are_optional_and_never_raise() -> None:
    posted: list[tuple[str, bytes]] = []
    assert not alerts.send("hi", env={}, post=lambda u, d: posted.append((u, d)))
    env = {alerts.TOKEN_ENV: "123:abc", alerts.CHAT_ENV: "42"}
    assert alerts.send("filled", env=env, post=lambda u, d: posted.append((u, d)))
    assert posted[0][0].endswith("/bot123:abc/sendMessage") and b"chat_id=42" in posted[0][1]

    def broken(url: str, data: bytes) -> None:
        raise OSError(f"cannot reach {url}")

    assert not alerts.send("x", env=env, post=broken)


def test_the_preview_reports_problems_without_stopping_anything(home: Path) -> None:
    pending = [{"id": "o9", "symbol": BTC, "pair": "BTC/CAD", "side": "buy"}]
    live.LiveLedger("kraken", {BTC: 1.0}, pending).save(home / "state" / "live_ledger.json")
    code, out = sync(home, FakeExchange(), paper_config(), dry_run=True)
    assert code == 1 and "unsettled" in out and "Reconciliation break" in out
    assert not KillSwitch(home / "state" / "kill_switch.json").engaged


def test_a_ledger_from_another_exchange_is_refused(home: Path) -> None:
    live.LiveLedger("coinbase", {BTC: 1.0}).save(home / "state" / "live_ledger.json")
    code, out = sync(home, FakeExchange())
    assert code == 1 and "belongs to coinbase" in out
    assert KillSwitch(home / "state" / "kill_switch.json").engaged


def test_a_test_order_that_cannot_be_afforded_is_not_sent(home: Path) -> None:
    fake, out = FakeExchange(cash=2.0), list[str]()
    code = live.run_test_order(
        armed_config(), connect=lambda e: fake, say=out.append, **paths(home)
    )
    assert code == 1 and not fake.orders and "Nothing was sent" in out[-1]


def test_a_failed_test_order_stops_everything(home: Path) -> None:
    fake, out = FakeExchange(fill="none"), list[str]()

    def broken_cancel(id: str, symbol: str | None = None) -> dict[str, Any]:
        raise ConnectionError("exchange went away")

    fake.cancel_order = broken_cancel  # type: ignore[method-assign]
    code = live.run_test_order(
        armed_config(), connect=lambda e: fake, say=out.append, **paths(home)
    )
    text = "\n".join(out)
    assert code == 1 and "kill switch is ENGAGED" in text and "Order o1 may still be open" in text
    assert KillSwitch(home / "state" / "kill_switch.json").engaged


def test_check_survives_an_unreachable_exchange(home: Path) -> None:
    def down(exchange_id: str) -> live.Exchange:
        raise ConnectionError(f"no route; key was {SECRET}")

    armed, lines = live.check_lines(armed_config(), connect=down, **paths(home))
    text = "\n".join(lines)
    assert armed and "Could not read the kraken account" in text and SECRET not in text
    assert not KillSwitch(home / "state" / "kill_switch.json").engaged


def test_status_line_for_the_mirror(home: Path) -> None:
    state = home / "state" / "paper_account.json"
    assert live.mirror_summary(state) is None
    live.LiveLedger("kraken", {BTC: 0.5}).save(home / "state" / "live_ledger.json")
    assert live.mirror_summary(state) == (
        "Real-money mirror on kraken: holds 0.5 BTC | real fills 0 | unsettled orders 0"
    )
    (home / "state" / "live_ledger.json").write_text("{broken", encoding="utf-8")
    assert "unreadable" in str(live.mirror_summary(state))


def test_two_real_money_runs_never_overlap(home: Path, tmp_path: Path) -> None:
    from quantagents.runlock import RunLock

    held = RunLock(home / "state" / live.LOCK_NAME)
    assert held.acquire()  # a scheduled run is still going...
    fake = FakeExchange()
    code, out = sync(home, fake)  # ...so a click at the same time sends nothing
    assert code == 3 and "another real-money run is still going" in out and not fake.orders
    out_lines: list[str] = []
    code = live.run_test_order(
        armed_config(), connect=lambda e: fake, say=out_lines.append, **paths(home)
    )
    assert code == 3 and not fake.orders
    assert sync(home, fake, dry_run=True)[0] == 0  # a preview sends nothing, so it may run
    held.release()
    assert sync(home, fake)[0] == 0 and len(fake.orders) == 1
    assert not (home / "state" / live.LOCK_NAME).exists()  # released after the run


def test_a_lock_left_by_a_crash_is_taken_over(tmp_path: Path) -> None:
    import os

    from quantagents.runlock import RunLock

    path = tmp_path / "x.lock"
    first, second = RunLock(path), RunLock(path)
    assert first.acquire() and not second.acquire()
    os.utime(path, (0, 0))  # an hour-old lock: its run crashed
    assert second.acquire() and second.held
    second.release()
    assert not path.exists()
    first.held = False  # the crashed run never comes back to release it
