"""Which markets this program trades: US stocks and crypto, with meme coins as a tagged part of crypto.

Everything else (forex, futures, options, bonds and rates) was removed in 1.7.0. ETFs and the big stock indices stay only
as price REFERENCES (the stock agents compare themselves with SPY); they are never assigned to an agent and never ordered.
The risk service repeats this rule as a deterministic check that no agent, bot or API call can switch off.
"""

from __future__ import annotations

from tradingai.market.instruments import MarketType

# the market names an order may carry
TRADABLE_MARKETS = ("crypto", "stock")
# the instrument types that may be ordered
TRADABLE_TYPES = frozenset({MarketType.STOCK, MarketType.CRYPTO_SPOT})
REMOVED_NOTE = ("this market was removed: the program trades only US stocks, crypto and meme coins "
                "(ETFs and indices are price references only)")


def market_allowed(inst) -> tuple[bool, str]:
    """Whether an instrument may be traded at all, and why not."""
    if inst.market_type in TRADABLE_TYPES:
        return True, "ok"
    if inst.market_type in (MarketType.ETF, MarketType.INDEX_REFERENCE):
        return False, "a price reference only: ETFs and indices are never ordered (" + REMOVED_NOTE + ")"
    return False, REMOVED_NOTE
