"""Canadian adjusted cost base (ACB) report and superficial-loss flags (spec section 78).

Informational only, not tax advice. CRA uses the average-cost method for identical
properties. A loss is a *possible* superficial loss when the same property was bought
in the 30 days before or after the sale; an accountant must confirm (the rule also
depends on holdings at the end of that window and on affiliated accounts).
Short sales are listed separately and not run through the ACB pool.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from quantagents.schemas import Fill, Message, OrderSide

WINDOW_DAYS = 30


class Disposition(Message):
    symbol: str
    trade_date: str
    qty: float
    proceeds: float
    acb: float
    gain: float
    possible_superficial_loss: bool


class AcbReport(Message):
    dispositions: tuple[Disposition, ...]
    holdings_acb: dict[str, float]
    holdings_qty: dict[str, float]
    skipped_short_sales: tuple[str, ...]
    note: str = "Informational only, not tax advice. Keep records for at least 6 years."


def acb_report(fills: Sequence[Fill]) -> AcbReport:
    ordered = sorted(fills, key=lambda f: (f.trade_date, f.fill_id))
    qty: dict[str, float] = {}
    acb: dict[str, float] = {}
    dispositions: list[Disposition] = []
    skipped: list[str] = []
    for fill in ordered:
        held = qty.get(fill.symbol, 0.0)
        if fill.side is OrderSide.BUY:
            qty[fill.symbol] = held + fill.qty
            acb[fill.symbol] = acb.get(fill.symbol, 0.0) + fill.qty * fill.price + fill.fee
            continue
        sold = min(fill.qty, held)
        if sold <= 0:
            skipped.append(f"{fill.fill_id} {fill.symbol} {fill.trade_date.isoformat()}")
            continue
        cost = acb[fill.symbol] * sold / held
        proceeds = sold * fill.price - fill.fee * sold / fill.qty
        gain = proceeds - cost
        window_start = fill.trade_date - timedelta(days=WINDOW_DAYS)
        window_end = fill.trade_date + timedelta(days=WINDOW_DAYS)
        rebought = any(
            f.symbol == fill.symbol
            and f.side is OrderSide.BUY
            and window_start <= f.trade_date <= window_end
            and f.fill_id != fill.fill_id
            for f in ordered
        )
        dispositions.append(
            Disposition(
                symbol=fill.symbol,
                trade_date=fill.trade_date.isoformat(),
                qty=sold,
                proceeds=proceeds,
                acb=cost,
                gain=gain,
                possible_superficial_loss=gain < 0 and rebought,
            )
        )
        qty[fill.symbol] = held - sold
        acb[fill.symbol] -= cost
        if fill.qty > sold:
            skipped.append(
                f"{fill.fill_id} {fill.symbol} {fill.trade_date.isoformat()} (short part)"
            )
    return AcbReport(
        dispositions=tuple(dispositions),
        holdings_acb={s: v for s, v in sorted(acb.items()) if qty.get(s, 0.0) > 0},
        holdings_qty={s: v for s, v in sorted(qty.items()) if v > 0},
        skipped_short_sales=tuple(skipped),
    )
