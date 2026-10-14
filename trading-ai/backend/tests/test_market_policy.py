"""Only US stocks, crypto and meme coins are traded. Forex, futures, options and bonds were removed; ETFs and indices are
price references only. The rule is enforced in the universe, the roster and, deterministically, in the risk service."""

from collections import Counter
from decimal import Decimal as D

import pytest

from test_safety import failed, req, snap
from tradingai.engine import master as M
from tradingai.market import universe
from tradingai.market.instruments import MarketType
from tradingai.market.policy import market_allowed
from tradingai.risk.service import RiskService

CHECK = "market supported (US stocks and crypto only)"


def test_the_universe_has_no_forex_or_futures_and_etfs_are_references_only():
    book, _ = universe.build()
    kinds = Counter(i.market_type for i in book._items.values())
    assert kinds[MarketType.STOCK] and kinds[MarketType.CRYPTO_SPOT]
    assert not kinds[MarketType.FX_OTC] and not kinds[MarketType.FUTURE] and not kinds[MarketType.FX_FUTURE]
    spy = book.get("US:SPY")
    assert "reference_only" in spy.tags and universe.paper_tradable(spy)[0] is False
    assert universe.paper_tradable(book.get("US:AAPL"))[0] is True
    assert universe.paper_tradable(book.get("COINBASE:BTC-USD"))[0] is True
    assert market_allowed(book.get("INDEX:SPX"))[0] is False


def test_exactly_100_agents_in_crypto_meme_and_stock_roles_only():
    assert len(M.PLAN) and sum(last - first + 1 for _, first, last, _ in M.PLAN) == 100
    by_group = Counter()
    for role, first, last, _ in M.PLAN:
        assert M.ROLES[role].market in ("crypto", "stock"), role
        by_group["meme" if role.startswith("meme") else M.ROLES[role].market] += last - first + 1
    assert by_group == {"crypto": 40, "meme": 15, "stock": 45}
    fixed = [i for _, _, _, ids in M.PLAN if ids for i in ids]
    assert len(fixed) == len(set(fixed))                                   # no instrument has two owners
    assert not any(i.startswith(("FX:", "CME:", "CBOT:", "COMEX:")) for i in fixed)


@pytest.mark.parametrize("market", ["etf", "fx", "future", "index", "option"])
def test_the_risk_service_denies_entries_in_a_removed_market(market):
    d = RiskService().check(req(market=market), snap())
    assert not d.approved and CHECK in failed(d)


@pytest.mark.parametrize("market", ["crypto", "stock"])
def test_the_supported_markets_pass_that_check(market):
    assert CHECK not in failed(RiskService().check(req(market=market, instrument_id="X:Y"), snap()))


def test_an_old_position_in_a_removed_market_can_still_be_closed():
    held = {"US:SPY": {"qty": "10", "price": "500", "market": "etf"}}
    d = RiskService().check(req(market="etf", instrument_id="US:SPY", side="sell", quantity=D(10), reduces_position=True,
                                reference_price=D(500), sized_target=D(10)), snap(positions=held))
    assert CHECK not in failed(d)                                          # exits are never blocked by this rule


def test_the_coverage_matrix_lists_only_crypto_and_stocks(tmp_path):
    from tradingai.app import App
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    try:
        assert [r["market"] for r in a.coverage()] == ["Crypto spot (including meme coins)", "US stocks"]
    finally:
        a.shutdown()
