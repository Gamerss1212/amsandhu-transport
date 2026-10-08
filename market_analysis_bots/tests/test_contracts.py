"""Instruments, money and futures (master prompt sections 130-137, 202, 207, 285, 322-324): small hand-computed cases
whose answers are exact, so the money math is proven before any long backtest is trusted."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from mab import futures as F
from mab import instrument_spec as I
from mab import metrics as M

D = Decimal


def test_money_is_exact_and_refuses_floats() -> None:
    assert I.money("0.1") + I.money("0.2") == I.money("0.3")
    with pytest.raises(TypeError):
        I.money(0.1)
    with pytest.raises(ValueError):
        I.money("ten")


def test_futures_pnl_includes_the_multiplier() -> None:
    es, mes = I.future_from_spec("ES"), I.future_from_spec("MES")
    assert es.tick_value == D("12.50") and mes.tick_value == D("1.25")
    # long 2 ES from 5000.00 to 5010.25: 10.25 points x 50 x 2 = 1,025 USD, minus 4.20 fees
    assert I.pnl(es, "5000.00", "5010.25", 2, fees="4.20") == D("1020.80")
    # the same move on MES is a tenth of it
    assert I.pnl(mes, "5000.00", "5010.25", 2) == D("102.50")
    # short 1 CL from 80.00 to 80.50: -0.50 x 1000 = -500 USD
    assert I.pnl(I.future_from_spec("CL"), "80.00", "80.50", -1) == D("-500.00")
    assert I.pnl(I.future_from_spec("ZN"), "110.5", "110.515625", 1) == D("15.625")


def test_stock_pnl_and_account_currency_conversion_needs_a_rate() -> None:
    td = I.Instrument("yahoo:TD.TO", I.MarketType.STOCK, "TD.TO", "yahoo", "CAD")
    assert I.pnl(td, "80.10", "81.35", 100, fees="2") == D("123.00")
    with pytest.raises(ValueError, match="needs a CAD->USD rate"):
        I.pnl(td, "80", "81", 100, account_currency="USD")
    assert I.pnl(td, "80", "81", 100, account_currency="USD", fx_to_account="0.73") == D("73.00")


def test_an_index_is_a_reference_and_cannot_be_traded() -> None:
    spx = I.Instrument("index:SPX", I.MarketType.INDEX_REFERENCE, "SPX", "index", "USD",
                       settlement=I.Settlement.NONE)
    assert not spx.tradable and spx.unit is I.Unit.INDEX_POINTS
    with pytest.raises(ValueError, match="index reference"):
        I.pnl(spx, "5000", "5010", 1)
    book = I.InstrumentBook([spx, I.future_from_spec("MES"), I.future_from_spec("ES")])
    assert [p.symbol for p in book.proxies("SPX")] == ["MES", "ES"]   # SPY not loaded in this book: not invented
    with pytest.raises(KeyError, match="resolve it through the registry"):
        book.get("SPY")


def test_size_from_risk_rounds_down_and_never_forces_a_trade() -> None:
    mes = I.future_from_spec("MES")
    # 500 USD risk, 10-point stop on MES = 50 USD per contract (+1.24 costs) -> 9 contracts (9.75 rounded down)
    assert I.size_from_risk(mes, 500, "5000", "4990", cost_per_unit="1.24") == D(9)
    # the same risk on ES (500 USD per contract per 10 points + costs) is less than one contract: no trade
    assert I.size_from_risk(I.future_from_spec("ES"), 500, "5000", "4990", cost_per_unit="2") == D(0)
    btc = I.Instrument("coinbase:BTC-USD", I.MarketType.CRYPTO_SPOT, "BTC-USD", "coinbase", "USD",
                       quantity_step=D("0.0001"), min_quantity=D("0.0001"))
    assert I.size_from_risk(btc, 100, "60000", "58500") == D("0.0666")
    with pytest.raises(ValueError):
        I.size_from_risk(mes, 100, "5000", "5000")


def test_prices_round_to_ticks_and_quantities_round_down() -> None:
    es = I.future_from_spec("ES")
    assert es.round_price("5000.13") == D("5000.25") and es.round_price("5000.12") == D("5000.00")
    stock = I.Instrument("yahoo:SPY", I.MarketType.ETF, "SPY", "yahoo", "USD")
    assert stock.round_quantity("12.9") == D(12)


def test_fx_pips_differ_for_yen_pairs() -> None:
    eur = I.Instrument("oanda:EUR_USD", I.MarketType.FX_OTC, "EUR_USD", "oanda", "USD", base_asset="EUR",
                       quote_asset="USD", tick_size=D("0.00001"))
    jpy = I.Instrument("oanda:USD_JPY", I.MarketType.FX_OTC, "USD_JPY", "oanda", "JPY", base_asset="USD",
                       quote_asset="JPY", tick_size=D("0.001"))
    assert I.pip_size(eur) == D("0.0001") and I.pip_value(eur, 100_000) == D("10.0000")
    assert I.pip_size(jpy) == D("0.01") and I.pip_value(jpy, 100_000) == D("1000.00")     # in JPY
    with pytest.raises(ValueError):
        I.pip_size(I.future_from_spec("6E"))                    # currency futures are a different product


def test_broker_contract_must_match_the_spec_before_an_order() -> None:
    gc = I.future_from_spec("GC")
    good = {"exchange": "COMEX", "currency": "USD", "multiplier": "100", "contract_month": "2026-12",
            "expiry": "2026-12-29", "first_notice": "2026-11-27", "broker_symbol": "GCZ6"}
    c = I.resolve_contract(gc, good)
    assert c.verified_with_broker and c.instrument_id == "COMEX:GC:2026-12" and c.first_notice == "2026-11-27"
    for change, why in (({"multiplier": "10"}, "multiplier"), ({"exchange": "NYMEX"}, "exchange"),
                        ({"first_notice": None}, "first notice"), ({"expiry": ""}, "expiry")):
        with pytest.raises(ValueError, match=why):
            I.resolve_contract(gc, {**good, **change})


def test_delivery_guard_blocks_physical_contracts_near_delivery() -> None:
    gc = I.resolve_contract(I.future_from_spec("GC"), {
        "exchange": "COMEX", "currency": "USD", "multiplier": "100", "contract_month": "2026-12",
        "expiry": "2026-12-29", "first_notice": "2026-11-27"})
    assert F.delivery_guard(gc, "2026-11-10") == (True, "ok")
    ok, why = F.delivery_guard(gc, "2026-11-25")
    assert not ok and "first notice" in why
    unknown = I.future_from_spec("CL")                       # no first notice date from a broker: unsafe
    assert not F.delivery_guard(unknown, "2026-11-01")[0]
    es = I.resolve_contract(I.future_from_spec("ES"), {"exchange": "CME", "currency": "USD", "multiplier": "50",
                                                       "contract_month": "2026-12", "expiry": "2026-12-18"})
    assert F.delivery_guard(es, "2026-12-10")[0] and not F.delivery_guard(es, "2026-12-17")[0]


def _two_contracts():
    expiries = {"2026-09": "2026-09-18", "2026-12": "2026-12-18"}
    bars = {"2026-09": {"2026-09-10": D("100"), "2026-09-11": D("101"), "2026-09-14": D("102")},
            "2026-12": {"2026-09-10": D("103"), "2026-09-11": D("104"), "2026-09-14": D("106"),
                        "2026-09-15": D("107")}}
    return expiries, bars


def test_roll_and_continuous_series_golden_case() -> None:
    expiries, bars = _two_contracts()
    days = ["2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15"]
    sched = F.roll_schedule(expiries, days, roll_days_before=5)
    assert sched == {"2026-09-10": "2026-09", "2026-09-11": "2026-09", "2026-09-14": "2026-12",
                     "2026-09-15": "2026-12"}                   # rolled 4 days before the September expiry
    ex = F.execution_prices(bars, sched)
    assert ex["2026-09-11"] == ("2026-09", D("101")) and ex["2026-09-14"] == ("2026-12", D("106"))
    # the roll gap measured on 09-11 (the last day on September): 104 - 101 = 3
    assert F.continuous(bars, sched, "stitched") == {"2026-09-10": D("100"), "2026-09-11": D("101"),
                                                     "2026-09-14": D("106"), "2026-09-15": D("107")}
    assert F.continuous(bars, sched, "difference") == {"2026-09-10": D("103"), "2026-09-11": D("104"),
                                                       "2026-09-14": D("106"), "2026-09-15": D("107")}
    ratio = F.continuous(bars, sched, "ratio")
    assert ratio["2026-09-14"] == D("106") and ratio["2026-09-11"] == D("104")
    assert ratio["2026-09-10"] == D("100") * D("104") / D("101")
    # open interest moves the roll earlier, never later
    oi = {"2026-09": {"2026-09-10": 900.0, "2026-09-11": 400.0}, "2026-12": {"2026-09-10": 500.0, "2026-09-11": 800.0}}
    early = F.roll_schedule(expiries, days, roll_days_before=5, open_interest=oi)
    assert early["2026-09-10"] == "2026-09" and early["2026-09-11"] == "2026-12"


def test_a_missing_bar_or_no_contract_left_is_an_error_not_a_guess() -> None:
    expiries, bars = _two_contracts()
    with pytest.raises(KeyError, match="no 2026-09 bar"):
        F.execution_prices(bars, {"2026-09-12": "2026-09"})
    with pytest.raises(ValueError, match="no listed contract left"):
        F.roll_schedule({"2026-09": "2026-09-18"}, ["2026-09-25"])


def test_a_cash_account_stops_at_zero_instead_of_losing_more_than_it_has() -> None:
    def t(pnl, day):
        ms = int(__import__("datetime").datetime(2026, 1, day, 12, tzinfo=__import__("datetime").timezone.utc)
                 .timestamp() * 1000)
        return SimpleNamespace(pnl=pnl, r=-1.0 if pnl < 0 else 1.0, fees=1.0, exit_time=ms, side=1, bars=1,
                               mfe_r=0.0, mae_r=-1.0)
    days = ["2026-01-01", "2026-01-02", "2026-01-03"]
    m = M.compute([t(-600, 1), t(-600, 2), t(+500, 3)], 1000.0, days, 365)
    assert m["ruined"] and m["ruin_day"] == "2026-01-02"
    assert m["net_return"] == -1.0 and m["max_drawdown"] == 1.0 and m["net_pnl"] == -1000.0
    assert m["net_pnl_uncapped"] == -700.0                     # kept for reference, never shown as the account
    ok = M.compute([t(-100, 1), t(+300, 3)], 1000.0, days, 365)
    assert not ok["ruined"] and ok["net_return"] == 0.2
