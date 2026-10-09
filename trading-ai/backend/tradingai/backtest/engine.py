"""Event-driven backtester (sections 132-133, 138-140, 207, 224, 245-248).

One pass over completed bars, in time order:
  1. orders scheduled at bar t-1's close fill at bar t's OPEN (never at the signal bar's close), paying half the
     spread, slippage and fees; a fill is capped at `participation_cap` of the bar's volume (partial fills carry on)
  2. intrabar exits on bar t: stop and target are checked against the bar's high/low; when both are inside one bar the
     STOP is assumed first (the conservative choice); a gap through the stop fills at the open, not the stop
  3. at bar t's close the strategy's desired direction is read and exits/entries are scheduled for bar t+1
  4. equity is marked at the close

Accounting by market: spot (stocks, ETFs, crypto) moves cash by the full notional; margin products (futures, FX)
book only P&L, with futures P&L = price move x contract multiplier x contracts and FX P&L converted from the quote
currency to the account currency at that bar's rate. A cash account that reaches zero is RUINED and stops.

Futures on a provider's continuous series are forced flat inside the roll window, so a roll jump is never booked as
profit (section 133). Floats (float64) are used for speed; tests check the ledger identity to 1e-6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np

from tradingai.backtest.costs import CostModel, default_for, half_spread_price
from tradingai.data.bars import Bars
from tradingai.features import indicators as I
from tradingai.market.instruments import Instrument, MarketType

SPOT = {MarketType.STOCK, MarketType.ETF, MarketType.CRYPTO_SPOT}


@dataclass
class BTConfig:
    capital: float = 100_000.0
    risk_per_trade: float = 0.01           # equity fraction lost if the stop is hit (stop-based exits)
    vol_target: float = 0.15               # annualized, for exits without a stop ("flip")
    max_leverage: Optional[float] = None   # default: 1 for spot, 5 for FX/futures
    allow_short: Optional[bool] = None     # default: FX and futures only (no borrow data for stocks)
    exit_model: str = "flip"
    exit_params: dict = field(default_factory=dict)
    cost: Optional[CostModel] = None
    cost_mult: float = 1.0
    ppy: float = 252.0
    flat_in_roll_window: bool = True
    fill_ratio: float = 1.0                # Monte Carlo "missed fills": share of entry orders that get filled
    seed: int = 7
    fixed_qty: Optional[float] = None      # golden tests and manual runs: trade exactly this quantity


@dataclass
class Trade:
    side: int
    entry_ts: int
    exit_ts: int
    entry_px: float
    exit_px: float
    qty: float
    gross: float
    fees: float
    spread: float
    slippage: float
    funding: float
    net: float
    r_multiple: Optional[float]
    bars: int
    exit_reason: str
    entry_bar: int

    def as_dict(self) -> dict:
        return dict(vars(self))


@dataclass
class BTResult:
    instrument_id: str
    equity: np.ndarray
    returns: np.ndarray
    exposure: np.ndarray
    trades: list[Trade]
    ts: np.ndarray
    costs: dict
    flags: list[str]
    config: dict
    ruined: bool = False
    partial_fills: int = 0
    missed_fills: int = 0
    undersized: int = 0          # entry signals skipped because one contract/lot is bigger than the sized position


def _fx_to_account(inst: Instrument, price: float) -> float:
    """Multiply a quote-currency amount by this to get USD (the account currency)."""
    if inst.market_type is MarketType.FX_OTC and inst.quote_asset and inst.quote_asset != "USD":
        return 1.0 / price if inst.base_asset == "USD" else 1.0
    return 1.0


def _roll_window_mask(ts: np.ndarray) -> np.ndarray:
    from tradingai.market.calendars import in_roll_window
    days = ts // 86_400_000
    out = np.zeros(len(ts), dtype=bool)
    for d in np.unique(days):
        out[days == d] = in_roll_window(datetime.fromtimestamp(int(d) * 86400, tz=timezone.utc).date())
    return out


def run(bars: Bars, signal: np.ndarray, inst: Instrument, cfg: BTConfig | None = None,
        funding: Optional[np.ndarray] = None) -> BTResult:
    cfg = cfg or BTConfig()
    n = len(bars)
    if len(signal) != n:
        raise ValueError("signal and bars differ in length")
    o, h, lo, c, v = bars.open, bars.high, bars.low, bars.close, bars.volume
    cm = (cfg.cost or default_for(inst))
    if cfg.cost_mult != 1.0:
        cm = cm.scaled(cfg.cost_mult)
    spot = inst.market_type in SPOT
    mult = float(inst.multiplier)
    lev = cfg.max_leverage if cfg.max_leverage is not None else (1.0 if spot else 5.0)
    shortable = cfg.allow_short if cfg.allow_short is not None else not spot
    step_qty = float(inst.quantity_step)
    min_qty = float(inst.min_quantity)
    atr = I.atr(h, lo, c, 14)
    sigma = I.rstd(I.logret(c), 20)
    has_volume = bool(np.any(v > 0))
    rng = np.random.default_rng(cfg.seed)
    roll_flat = (cfg.flat_in_roll_window and "continuous_provider_series" in inst.tags) and _roll_window_mask(bars.ts)
    if roll_flat is False:
        roll_flat = np.zeros(n, dtype=bool)
    sig = np.clip(np.nan_to_num(signal), -1, 1)
    if not shortable:
        sig = np.maximum(sig, 0)

    ep = dict(cfg.exit_params)
    stop_atr = ep.get("stop_atr", 2.0)
    target_r = ep.get("target_r", 2.0)
    max_bars = int(ep.get("max_bars", 20))
    trail_atr = ep.get("trail_atr", 3.0)

    cash = float(cfg.capital)
    pos = 0.0                    # signed quantity
    entry_px = stop = target = trail = 0.0
    entry_ts = entry_bar = 0
    risk_amt = 0.0
    t_fees = t_spread = t_slip = t_fund = 0.0
    tr = {"real": 0.0, "fees": 0.0, "spread": 0.0, "slip": 0.0, "fund": 0.0, "qty": 0.0, "entry": 0.0}
    pending: Optional[float] = None          # desired signed quantity to reach from the next open
    pending_reason = ""
    blocked_dir = 0.0                        # after a stop/target/time exit: no re-entry that way until the signal resets
    equity = np.full(n, float(cfg.capital))
    exposure = np.zeros(n)
    trades: list[Trade] = []
    flags: list[str] = []
    ruined = False
    partial = missed = undersized = 0
    smallest_unit = 0.0                      # notional of one contract/lot at the last undersized signal
    last_under = -2                          # bar of the last undersized signal (consecutive bars count once)

    def mark(i: int) -> float:
        px = c[i]
        if spot:
            return cash + pos * px
        return cash + (px - entry_px) * pos * mult * _fx_to_account(inst, px) if pos else cash

    def fill(i: int, qty: float, ref_px: float) -> float:
        """Trade `qty` (signed, never crossing zero) at `ref_px` (the open, or a stop/target level) on bar i."""
        nonlocal cash, pos, entry_px, t_fees, t_spread, t_slip
        side = 1.0 if qty > 0 else -1.0
        hs = half_spread_price(cm, inst, ref_px)
        slip = cm.slippage_frac(price=ref_px, bar_range=h[i] - lo[i], qty=abs(qty) * mult,
                                bar_volume=v[i] * mult if has_volume else 0.0,
                                sigma_bar=float(sigma[i]) if np.isfinite(sigma[i]) else 0.0) * ref_px
        px = ref_px + side * (hs + slip)
        fx = _fx_to_account(inst, px)
        fee = cm.fees(notional=abs(qty) * px * mult * fx, contracts=abs(qty) if not spot else 0.0)
        reducing = pos != 0 and np.sign(qty) != np.sign(pos)
        if reducing:
            tr["real"] += (px - entry_px) * (-qty) * mult * fx
        if spot:
            cash -= qty * px + fee
        else:
            if reducing:
                cash += (px - entry_px) * (-qty) * mult * fx
            cash -= fee
        t_fees += fee
        t_spread += abs(qty) * hs * mult * fx
        t_slip += abs(qty) * slip * mult * fx
        tr["fees"] += fee
        tr["spread"] += abs(qty) * hs * mult * fx
        tr["slip"] += abs(qty) * slip * mult * fx
        new = pos + qty
        if not reducing:
            entry_px = px if pos == 0 else (entry_px * abs(pos) + px * abs(qty)) / abs(new)
            tr["qty"] = max(tr["qty"], abs(new))
            tr["entry"] = entry_px
        pos = 0.0 if abs(new) < 1e-12 else new
        return px

    def close_trade(i: int, px: float, reason: str, side: int) -> None:
        gross = tr["real"] + tr["spread"] + tr["slip"]
        net = tr["real"] - tr["fees"] - tr["fund"]
        r = net / risk_amt if risk_amt > 0 else None
        trades.append(Trade(side, int(entry_ts), int(bars.ts[i]), float(tr["entry"]), float(px), float(tr["qty"]),
                            float(gross), float(tr["fees"]), float(tr["spread"]), float(tr["slip"]),
                            float(tr["fund"]), float(net), None if r is None else float(r), int(i - entry_bar),
                            reason, int(entry_bar)))
        for k in tr:
            tr[k] = 0.0

    for i in range(n):
        if ruined:
            equity[i] = 0.0
            continue
        # 1. scheduled orders at the open: close first (exits are not volume-capped), then enter
        if pending is not None and i > 0:
            want = pending
            if pos != 0 and (want == 0 or np.sign(want) != np.sign(pos)):
                side = int(np.sign(pos))
                px = fill(i, -pos, o[i])
                close_trade(i, px, pending_reason, side)
            delta = want - pos
            if abs(delta) > 1e-12 and (pos == 0 or np.sign(want) == np.sign(pos)):
                if pos == 0 and cfg.fill_ratio < 1.0 and rng.random() > cfg.fill_ratio:
                    missed += 1
                    want = pos = 0.0
                    delta = 0.0
                elif has_volume:
                    cap = cm.participation_cap * v[i] if v[i] > 0 else 0.0
                    capped = np.floor(cap / step_qty) * step_qty
                    if abs(delta) > capped:
                        delta = np.sign(delta) * capped
                        partial += 1
                if abs(delta) >= min_qty or (pos != 0 and abs(delta) > 0):
                    was_flat = pos == 0
                    px = fill(i, delta, o[i])
                    if was_flat:
                        entry_ts, entry_bar = bars.ts[i], i
                        a = atr[i - 1] if np.isfinite(atr[i - 1]) else 0.0
                        d = np.sign(pos)
                        stop = px - d * stop_atr * a if cfg.exit_model in ("atr_bracket", "time") else 0.0
                        target = px + d * target_r * stop_atr * a if cfg.exit_model == "atr_bracket" else 0.0
                        trail = px - d * trail_atr * a if cfg.exit_model == "trail" else 0.0
            pending = None if abs(pos - want) < 1e-12 or want == 0 else want
        # 2. intrabar exits
        if pos != 0:
            lvl = stop if cfg.exit_model in ("atr_bracket", "time") else trail if cfg.exit_model == "trail" else 0.0
            hit_stop = bool(lvl) and ((pos > 0 and lo[i] <= lvl) or (pos < 0 and h[i] >= lvl))
            hit_tgt = bool(target) and ((pos > 0 and h[i] >= target) or (pos < 0 and lo[i] <= target))
            if hit_stop or hit_tgt:
                if hit_stop:
                    ref = min(o[i], lvl) if pos > 0 else max(o[i], lvl)
                    why = "trailing stop" if cfg.exit_model == "trail" else "stop"
                else:
                    ref = max(o[i], target) if pos > 0 else min(o[i], target)
                    why = "target"
                side = int(np.sign(pos))
                blocked_dir = float(side)
                px = fill(i, -pos, ref)
                close_trade(i, px, why, side)
                pending = None
        # funding on open perpetual positions (rate per bar, positive = longs pay)
        if pos != 0 and funding is not None and np.isfinite(funding[i]):
            f = funding[i] * pos * c[i] * mult
            cash -= f
            t_fund += f
            tr["fund"] += f
        # 3. decide at the close
        want_dir = 0.0 if roll_flat[i] else sig[i]
        if blocked_dir and want_dir != blocked_dir:
            blocked_dir = 0.0
        if blocked_dir and want_dir == blocked_dir:
            want_dir = 0.0 if pos == 0 else want_dir
        cur_dir = float(np.sign(pos))
        sched: Optional[float] = None
        reason = ""
        if pos != 0 and cfg.exit_model == "time" and i - entry_bar >= max_bars:
            sched, reason = 0.0, "time exit"
            blocked_dir = cur_dir
            want_dir = 0.0
        elif pos != 0 and want_dir != cur_dir:
            sched, reason = 0.0, ("roll window" if roll_flat[i] else "signal")
        if cfg.exit_model == "trail" and pos != 0 and np.isfinite(atr[i]):
            nt = c[i] - np.sign(pos) * trail_atr * atr[i]
            trail = max(trail, nt) if pos > 0 else min(trail, nt)
        eq = mark(i)
        if want_dir != 0 and (pos == 0 or sched == 0.0) and i < n - 1 and want_dir != cur_dir:
            a = atr[i]
            have_atr = bool(np.isfinite(a) and a > 0)
            fixed_ok = cfg.fixed_qty is not None and cfg.exit_model == "flip"     # no stop: no ATR needed
            if (have_atr or fixed_ok) and eq > 0:
                fx = _fx_to_account(inst, c[i])
                risk_amt = eq * cfg.risk_per_trade
                if cfg.fixed_qty is not None:
                    q = float(cfg.fixed_qty)
                else:
                    if cfg.exit_model == "flip":
                        vol_ann = float(sigma[i]) * np.sqrt(cfg.ppy) if np.isfinite(sigma[i]) and sigma[i] > 0 else 0.0
                        notional = eq * min(lev, cfg.vol_target / vol_ann) if vol_ann > 0 else 0.0
                    else:
                        dist = (stop_atr if cfg.exit_model != "trail" else trail_atr) * a
                        notional = min(risk_amt / (dist * mult * fx) * c[i] * mult * fx, eq * lev)
                    q = np.floor(notional / (c[i] * mult * fx) / step_qty) * step_qty
                if q >= min_qty:
                    sched = want_dir * q
                    reason = "entry" if pos == 0 else "reverse"
                elif cfg.fixed_qty is None and notional > 0:
                    undersized += last_under != i - 1
                    last_under = i
                    smallest_unit = min_qty * c[i] * mult * fx
        if sched is not None:
            pending, pending_reason = sched, reason
        equity[i] = eq
        exposure[i] = abs(pos) * c[i] * mult * _fx_to_account(inst, c[i]) / eq if eq > 0 else 0.0
        if eq <= 0:
            ruined = True
            flags.append(f"RUINED at bar {i}")
            equity[i] = 0.0
    if pos != 0 and not ruined:                     # close what is still open at the last close
        side = int(np.sign(pos))
        px = fill(n - 1, -pos, c[n - 1])
        close_trade(n - 1, px, "end of test", side)
        equity[-1] = mark(n - 1)
    rets = np.zeros(n)
    rets[1:] = np.where(equity[:-1] > 0, equity[1:] / np.where(equity[:-1] > 0, equity[:-1], 1) - 1, 0.0)
    if spot and not has_volume:
        flags.append("no volume data: no participation cap")
    if "continuous_provider_series" in inst.tags:
        flags.append("futures on a continuous provider series: flat in roll windows")
    if undersized:
        flags.append(f"{undersized} entry signal(s) skipped: one contract/lot (about {smallest_unit:,.0f} USD notional) is "
                     f"larger than the position this capital and sizing allow")
    return BTResult(inst.instrument_id, equity, rets, exposure, trades, bars.ts,
                    {"fees": t_fees, "spread": t_spread, "slippage": t_slip, "funding": t_fund,
                     "model": {"market": cm.market, "labels": cm.labels, "note": cm.note, "x": cfg.cost_mult}},
                    flags, {"exit_model": cfg.exit_model, "exit_params": ep, "capital": cfg.capital,
                            "risk_per_trade": cfg.risk_per_trade, "vol_target": cfg.vol_target,
                            "max_leverage": lev, "allow_short": shortable, "cost_mult": cfg.cost_mult},
                    ruined, partial, missed, undersized)
