"""Trading cost assumptions and the backtest fill model.

Fees are the published base-tier (lowest volume) rates, recorded with their source in
docs/COSTS.md. Spreads are ASSUMPTIONS by liquidity tier, not measurements; every evaluation
is re-run with costs doubled and tripled (cost sensitivity), so a result that only survives
at the assumed cost is visible as such.

Fill rules used by backtests (live paper fills use real order books where the venue
publishes them; see mab.paper):
* market orders fill at the reference price (next bar's open) +/- half the spread + impact
* stop orders fill at the stop price, or at the open if the bar opened beyond it, with
  twice the normal slippage (stops execute into momentum)
* limit orders need the price to trade THROUGH the limit by at least one tick; a touch is
  not a fill (queue position is unknown)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from mab.clock import is_equity
from mab.strategy import Filler

# fraction of notional per side
FEES: Dict[str, Dict[str, float]] = {
    "coinbase": {"taker": 0.0120, "maker": 0.0060},   # Coinbase Advanced "Intro 1" (<$1K/30d), secondary source
    "kraken": {"taker": 0.0080, "maker": 0.0040},     # Kraken Pro $0+ tier, kraken.com/features/fee-schedule
    "okx": {"taker": 0.0010, "maker": 0.0008},        # OKX spot Lv1: NOT verified (page not readable); data source only
    "yahoo": {"taker": 0.0, "maker": 0.0},            # US stocks: commission-free broker assumed
    "demo": {"taker": 0.0010, "maker": 0.0008},       # the synthetic DEMO market: a low-fee exchange's rates
}

# Which exchange's fees the crypto bots pay. "venue" (the default) charges each bot its own data venue's
# fees above. Choosing the exchange the owner actually trades on makes paper results, the cost gate and
# the brain's starting knowledge match that exchange. The NDAX rate is the flat rate NDAX publishes;
# owners should check their own account's schedule.
FEE_PROFILES: Dict[str, Optional[Dict[str, float]]] = {
    "venue": None,
    "coinbase": {"taker": 0.0120, "maker": 0.0060},
    "kraken": {"taker": 0.0080, "maker": 0.0040},
    "ndax": {"taker": 0.0020, "maker": 0.0020},
    "low_fee": {"taker": 0.0010, "maker": 0.0008},
}
FEE_PROFILE_LABELS = {
    "venue": "each bot's own exchange (Coinbase 1.20%, Kraken 0.80%, OKX 0.10% taker)",
    "coinbase": "Coinbase Advanced, entry tier (0.60% maker / 1.20% taker)",
    "kraken": "Kraken Pro, entry tier (0.40% / 0.80%)",
    "ndax": "NDAX (0.20% flat)",
    "low_fee": "a low-fee exchange (0.08% / 0.10%)",
}

# regulatory fees on US stock SALES only (fraction of sale notional); see docs/COSTS.md
US_SELL_FEES = 0.0000278

# assumed half-spread + impact, fraction of price, by liquidity tier
SLIPPAGE_TIER = {"major": 0.0001, "liquid": 0.0003, "mid": 0.0008, "small": 0.0020}

MAJORS = {"BTC-USD", "ETH-USD", "XBTUSD", "XXBTZUSD", "XETHZUSD", "BTC-USDT", "ETH-USDT", "BTC-USDT-SWAP",
          "ETH-USDT-SWAP", "SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"}


def tier_for(instrument: str, asset_type: str) -> str:
    if instrument in MAJORS:
        return "major"
    if is_equity(asset_type):
        return "liquid"
    return "mid"


@dataclass
class CostModel:
    venue: str
    tier: str = "mid"
    cost_mult: float = 1.0          # sensitivity: 2.0 doubles fees and slippage
    tick: float = 0.0
    stock: bool = False
    fees: Optional[Dict[str, float]] = None      # a fee profile overriding the venue's fees (crypto only)

    @property
    def slip(self) -> float:
        return SLIPPAGE_TIER[self.tier] * self.cost_mult

    def fee_rate(self, liquidity: str) -> float:
        table = self.fees if (self.fees and not self.stock) else FEES.get(self.venue, FEES["kraken"])
        return table[liquidity] * self.cost_mult

    def describe(self) -> dict:
        return {"venue": self.venue, "tier": self.tier, "cost_mult": self.cost_mult,
                "taker_fee": self.fee_rate("taker"), "maker_fee": self.fee_rate("maker"), "slippage": self.slip,
                "sell_regulatory_fee": US_SELL_FEES if self.stock else 0.0}


class BacktestFiller(Filler):
    def __init__(self, cm: CostModel):
        self.cm = cm
        self.side_hint = 0

    def fee(self, notional: float, liquidity: str) -> float:
        return notional * self.cm.fee_rate(liquidity)

    def market_price(self, side: int, ref_price: float, qty: float) -> Optional[float]:
        return ref_price * (1 + side * self.cm.slip)

    def stop_price(self, side: int, stop: float, bar_open: float) -> float:
        return stop * (1 + side * 2 * self.cm.slip)

    def limit_fill(self, side: int, limit: float, o: float, h: float, l: float) -> Optional[float]:
        tick = self.cm.tick or limit * 1e-5
        if side > 0:
            return min(limit, o) if l <= limit - tick else None
        return max(limit, o) if h >= limit + tick else None


class StockBacktestFiller(BacktestFiller):
    """Adds the US regulatory fee on sells (SEC Section 31 fee), charged via fee() at exit."""

    def fee(self, notional: float, liquidity: str) -> float:
        return notional * (self.cm.fee_rate(liquidity) + US_SELL_FEES / 2)   # averaged over buy and sell sides


def round_trip(filler, limit_entry: bool = False) -> float:
    """Round-trip cost as a fraction of price, as the brain's cost gate counts it: the entry pays the maker fee
    for a limit (resting) entry, else taker fee plus slippage; the exit is assumed to be a stop or market exit
    (taker fee plus slippage), the conservative case."""
    entry = filler.fee(1.0, "maker") if limit_entry else filler.fee(1.0, "taker") + filler.cm.slip
    return entry + filler.fee(1.0, "taker") + filler.cm.slip


def filler_for(venue: str, instrument: str, asset_type: str, cost_mult: float = 1.0, tick: float = 0.0) -> BacktestFiller:
    cm = CostModel(venue, tier_for(instrument, asset_type), cost_mult, tick, is_equity(asset_type))
    return StockBacktestFiller(cm) if cm.stock else BacktestFiller(cm)
