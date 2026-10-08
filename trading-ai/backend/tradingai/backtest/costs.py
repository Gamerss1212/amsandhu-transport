"""Transaction costs (sections 138-140). Every default below is an ASSUMPTION, editable on the page, and labelled as
one: fees change, and the owner's broker tier decides them. Nothing here claims to be a broker's current price list.

Per fill the engine charges:
  commission/fees  crypto: taker or maker % of notional; futures: per contract per side; stocks/FX: 0 by default
  spread           half the modelled bid/ask spread (the data has no historical quotes; see `spread_bps`)
  slippage         one of: fixed bps | spread only | volatility (share of the bar's range) | participation
                   (square-root market impact: k * sigma_bar * sqrt(qty / bar volume)) | composite = max(vol, impact)
  funding          perpetual swaps, when a funding-rate series is supplied (none for spot)
  financing        FX overnight financing at an annual rate differential (default 0: REQUIRES CONNECTION for rates)
and caps each fill at `participation_cap` of the bar's volume (the rest is filled on later bars or cancelled).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from tradingai.market.instruments import Instrument, MarketType

FX_HALF_SPREAD_PIPS = {"EURUSD": 0.4, "GBPUSD": 0.6, "USDJPY": 0.5, "USDCAD": 0.8, "AUDUSD": 0.5}
FUT_FEE_PER_SIDE = {"ES": 2.25, "NQ": 2.25, "YM": 2.25, "RTY": 2.25, "GC": 2.40, "CL": 2.40, "6E": 2.40, "ZN": 1.90,
                    "MES": 0.62, "MNQ": 0.62, "MYM": 0.62, "M2K": 0.62, "MGC": 0.80, "MCL": 0.80}


@dataclass
class CostModel:
    market: str
    commission_pct: float = 0.0            # of notional, per side
    maker_pct: float = 0.0
    fee_per_contract: float = 0.0          # per side
    half_spread_bps: float = 1.0
    slippage_model: str = "composite"      # fixed | spread | volatility | participation | composite
    slippage_bps: float = 0.0              # for "fixed"
    vol_slip_frac: float = 0.05            # share of the bar's range paid on a market order ("volatility")
    impact_k: float = 1.0                  # square-root impact coefficient ("participation")
    participation_cap: float = 0.10
    fx_financing_annual: float = 0.0
    half_spread_pips: float = 0.0          # FX only
    half_spread_ticks: float = 0.5         # futures only
    pip: float = 0.0001                    # FX only
    note: str = "assumption: edit to match your broker"
    labels: list = field(default_factory=list)

    def scaled(self, mult: float) -> "CostModel":
        d = asdict(self)
        for k in ("commission_pct", "maker_pct", "fee_per_contract", "half_spread_bps", "slippage_bps",
                  "vol_slip_frac", "impact_k", "fx_financing_annual", "half_spread_pips"):
            d[k] = d[k] * mult
        d["note"] = f"{self.note} (x{mult} cost stress)"
        return CostModel(**d)

    def slippage_frac(self, *, price: float, bar_range: float, qty: float, bar_volume: float, sigma_bar: float) -> float:
        """Slippage as a fraction of price for a market order of `qty` in a bar."""
        m = self.slippage_model
        if m == "fixed":
            return self.slippage_bps / 1e4
        if m == "spread":
            return 0.0
        vol = self.vol_slip_frac * (bar_range / price) if price > 0 else 0.0
        if m == "volatility":
            return vol
        impact = self.impact_k * sigma_bar * (qty / bar_volume) ** 0.5 if bar_volume > 0 and qty > 0 else 0.0
        if m == "participation":
            return impact
        return max(vol, impact)

    def fees(self, *, notional: float, contracts: float, maker: bool = False) -> float:
        pct = self.maker_pct if maker and self.maker_pct else self.commission_pct
        return abs(notional) * pct + abs(contracts) * self.fee_per_contract


def default_for(inst: Instrument) -> CostModel:
    mt = inst.market_type
    if mt in (MarketType.CRYPTO_SPOT, MarketType.CRYPTO_PERP):
        major = (inst.base_asset or inst.symbol).startswith(("BTC", "ETH", "XBT", "DEMO"))
        return CostModel("crypto", commission_pct=0.004, maker_pct=0.0025, half_spread_bps=1.0 if major else 4.0,
                         labels=["taker 0.40% / maker 0.25% per side: a retail exchange tier, assumption"])
    if mt in (MarketType.STOCK, MarketType.ETF):
        return CostModel("stock" if mt is MarketType.STOCK else "etf", half_spread_bps=1.0 if mt is MarketType.ETF
                         else 2.0, labels=["$0 commission (common at US brokers); exchange/regulatory sell fees "
                                           "not modelled"])
    if mt is MarketType.FX_OTC:
        pip = 0.01 if inst.quote_asset == "JPY" else 0.0001
        pips = FX_HALF_SPREAD_PIPS.get(inst.symbol, 1.0)
        return CostModel("fx", half_spread_bps=0.0, slippage_model="volatility", vol_slip_frac=0.02,
                         half_spread_pips=pips, pip=pip, note=f"half spread {pips} pips",
                         labels=[f"half spread {pips} pip (assumption: no dealer quotes)",
                                 "overnight financing not modelled: needs interest-rate data (REQUIRES CONNECTION)"])
    if mt in (MarketType.FUTURE, MarketType.FX_FUTURE):
        fee = FUT_FEE_PER_SIDE.get(inst.root or inst.symbol, 2.25)
        return CostModel("future", fee_per_contract=fee, half_spread_bps=0.0, slippage_model="volatility",
                         vol_slip_frac=0.02, labels=[f"${fee} per contract per side (commission + exchange, "
                                                     "assumption)", "half a tick of spread per side"])
    return CostModel("other")


def half_spread_price(cm: CostModel, inst: Instrument, price: float) -> float:
    """Half the bid/ask spread in price units."""
    if cm.market == "fx":
        return cm.half_spread_pips * cm.pip
    if cm.market == "future":
        return cm.half_spread_ticks * float(inst.tick_size)
    return price * cm.half_spread_bps / 1e4
