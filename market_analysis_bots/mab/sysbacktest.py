"""Full-system backtest: the fleet replayed on history, many times.

A strategy backtest asks "does this rule make money?". This asks "does the software, as a whole, make
money, and does its brain help?" Each run replays a set of bots over a window of history with the
same pieces the live fleet uses: every bot's own rules and exits, per-venue fees and slippage, the
Fleet Brain (cost gate, volatility gate, learned veto/resize, benching, online learning from closed
and blocked trades), account-level sizing (risk per trade from the slot equity) and portfolio limits
(maximum open positions, daily loss halt).

Speed comes from a two-step design:
1. Candidates (once): every bot is backtested over the whole dataset on its own. Each trade it would
   take becomes a candidate with its entry and exit times, its result in R after costs, and the
   context the brain sees at the signal bar (features, market regime, volatility gate, cost in R).
2. Runs (many): a run walks the candidates of a bot subset in time order. At each entry the brain
   decides; a vetoed candidate becomes a shadow trade the brain learns from at its exit; an approved
   one is sized from the current equity and settles at its exit.

Approximation, stated: a bot's candidate list comes from its unfiltered backtest, so when the brain
vetoes a trade the bot does not get the other entries it might have taken while it was flat instead.

Three arms are run on the same window and bots (paired): "none" (every candidate taken, size 1, no
gates), "gates" (cost and volatility gates only) and "brain" (everything). Differences between arms
are the measured value of the gates and of the learning.
"""

from __future__ import annotations

import bisect
import math
import random
from typing import Dict, List, Optional

from mab.brain import FleetBrain, regime_key, regime_of
from mab import volgate as VG

DAY = 86_400_000


class Candidate:
    __slots__ = ("bot", "bkey", "inst", "venue", "asset", "family", "t_in", "t_out", "side", "r", "cost_r", "f", "rkey", "gate")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


def hourly_from(frame, horizon: Optional[int] = None):
    """Hourly bars resampled from a finer frame (for the volatility gate)."""
    horizon = horizon or VG.HORIZON["stock" if frame.asset_type.startswith("stock") else "crypto"]
    step = 3_600_000
    t, o, h, l, c, v = [], [], [], [], [], []
    for i in range(frame.n):
        k = frame.t[i] - frame.t[i] % step
        if t and t[-1] == k:
            h[-1], l[-1], c[-1], v[-1] = max(h[-1], frame.h[i]), min(l[-1], frame.l[i]), frame.c[i], v[-1] + frame.v[i]
        else:
            t.append(k), o.append(frame.o[i]), h.append(frame.h[i]), l.append(frame.l[i]), c.append(frame.c[i]), v.append(frame.v[i])
    return VG.Bars(t, o, h, l, c, v, horizon)


def gate_at(gate: VG.VolGate, hb: VG.Bars, t_ms: int, asset: str) -> Optional[dict]:
    """Gate reading from the last hourly bar completed at t_ms (no look-ahead)."""
    j = bisect.bisect_right(hb.t, t_ms - 3_600_000) - 1
    if j < 0:
        return None
    r = gate.read(hb, j, asset)
    return None if r["state"] == "UNKNOWN" else r


def candidates_for(result, frame, bkey, bot_id, inst, venue, family, filler, gate, hb) -> List[Candidate]:
    """Turn one bot's backtest trades into candidates with the brain's context at the signal bar."""
    out = []
    asset = "stock" if frame.asset_type.startswith("stock") else "crypto"
    round_trip = 2 * filler.fee(1.0, "taker") + 2 * filler.cm.slip
    for tr in result.trades:
        if tr.r is None or not tr.qty:
            continue
        i = bisect.bisect_right(frame.t, tr.entry_time - frame.step) - 1
        if i < 1:
            continue
        risk_amt = abs(tr.pnl / tr.r) if tr.r else None
        stop_dist = risk_amt / tr.qty if risk_amt else None
        cost_r = round_trip * tr.entry_price / stop_dist if stop_dist else None
        g = gate_at(gate, hb, tr.entry_time, asset) if (gate is not None and hb is not None) else None
        reg = regime_of(frame.c, i)
        try:
            f = FleetBrain.features(frame, i, tr.side, 0.0, reg, cost_r, g)
        except Exception:
            continue
        out.append(Candidate(bot=bot_id, bkey=bkey, inst=inst, venue=venue, asset=asset, family=family,
                             t_in=tr.entry_time, t_out=tr.exit_time, side=tr.side, r=float(tr.r), cost_r=cost_r,
                             f=[round(x, 5) for x in f], rkey=regime_key(reg, tr.side), gate=g))
    return out


def run(cands: List[Candidate], t0: int, t1: int, arm: str, seed: int = 0, priors: Optional[str] = None,
        families: Optional[Dict[str, str]] = None, capital: float = 100_000.0, slots: int = 20, risk_pct: float = 0.5,
        max_open: int = 40, daily_loss: float = 0.03) -> dict:
    """One replay of the candidates entering in [t0, t1). arm: none | gates | brain."""
    evs = []
    for k, c in enumerate(cands):
        if t0 <= c.t_in < t1:
            evs.append((c.t_in, 1, k))
            evs.append((c.t_out, 0, k))                       # exits sort before entries at the same time
    evs.sort()
    brain = None
    if arm in ("gates", "brain"):
        brain = FleetBrain(mode="active", seed=seed)
        if arm == "brain" and priors:
            brain.load_priors(priors, segment="train")
        for c in {c.bot: c for c in cands}.values():
            brain.connect(c.bot, c.bkey, (families or {}).get(c.bkey.split("@")[0]), None, c.inst)
    equity = peak = capital
    max_dd, day, day_start, halted = 0.0, None, capital, False
    open_: Dict[int, tuple] = {}
    blocked: Dict[int, dict] = {}
    taken, wins, sum_r, vetoes, skipped_cap, skipped_halt = 0, 0, 0.0, {}, 0, 0
    daily = {}
    for t, kind, k in evs:
        c = cands[k]
        d = t // DAY
        if d != day:
            if day is not None:
                daily[day] = equity / day_start - 1
            day, day_start, halted = d, equity, False
        if kind == 1:
            if halted:
                skipped_halt += 1
                continue
            if len(open_) >= max_open:
                skipped_cap += 1
                continue
            size, dec = 1.0, None
            if arm == "gates":
                if c.cost_r is not None and c.cost_r > 0.33:
                    vetoes["cost"] = vetoes.get("cost", 0) + 1
                    continue
                if c.gate and c.gate["state"] == "QUIET":
                    vetoes["quiet"] = vetoes.get("quiet", 0) + 1
                    continue
                if c.cost_r is not None and c.cost_r > 0.20:
                    size *= 0.5
                if c.gate and c.gate["state"] == "LOUD":
                    size *= 0.6
            elif arm == "brain":
                dec = brain.decide(c.bot, c.bkey, c.inst, c.side, c.f, c.rkey, None, c.cost_r, c.gate)
                if dec["action"] == "veto":
                    vetoes[dec["veto_kind"]] = vetoes.get(dec["veto_kind"], 0) + 1
                    blocked[k] = dec
                    continue
                size = dec["size"]
            open_[k] = (equity / slots * risk_pct / 100.0 * size, dec)
        else:
            if k in open_:
                risk_amt, dec = open_.pop(k)
                equity += c.r * risk_amt
                taken += 1
                wins += int(c.r > 0)
                sum_r += c.r
                if arm == "brain":
                    brain.learn(c.bot, c.bkey, c.inst, c.r, dec)
                peak = max(peak, equity)
                max_dd = max(max_dd, 1 - equity / peak)
                if equity < day_start * (1 - daily_loss):
                    halted = True
            elif k in blocked:
                brain.learn_counterfactual(c.bot, blocked.pop(k), c.r, "backtest")
    if day is not None:
        daily[day] = equity / day_start - 1
    rets = list(daily.values())
    mu = sum(rets) / len(rets) if rets else 0.0
    sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / (len(rets) - 1)) if len(rets) > 1 else 0.0
    out = {"arm": arm, "return": equity / capital - 1, "max_dd": max_dd, "trades": taken,
           "win_rate": wins / taken if taken else None, "avg_r": sum_r / taken if taken else None,
           "sharpe_daily": (mu / sd * math.sqrt(365)) if sd else None, "vetoes": vetoes,
           "skipped_cap": skipped_cap, "skipped_halt": skipped_halt, "days": len(rets)}
    if brain is not None and arm == "brain":
        s = brain.summary()
        out["brain"] = {k: s[k] for k in ("trades_learned", "shadow_trades", "shadow_avg_r", "benched_now", "brier", "trust",
                                          "high_score_avg_r", "high_score_trades", "low_score_avg_r", "low_score_trades")}
        out["brain"]["shadow_by_kind"] = s["shadow_by_kind"]
    return out


def sample_runs(cands: List[Candidate], bots: List[str], t_start: int, t_end: int, n_runs: int, window_days: int,
                bots_per_run: int, priors: Optional[str], families: Dict[str, str], seed: int = 12345):
    """n_runs paired runs (none / gates / brain) on random windows and random bot subsets."""
    rng = random.Random(seed)
    by_bot: Dict[str, List[Candidate]] = {}
    for c in cands:
        by_bot.setdefault(c.bot, []).append(c)
    span = t_end - t_start - window_days * DAY
    results = []
    for n in range(n_runs):
        t0 = t_start + (rng.randrange(max(1, span // DAY)) * DAY if span > 0 else 0)
        t1 = t0 + window_days * DAY
        subset = rng.sample(bots, min(bots_per_run, len(bots)))
        cs = sorted((c for b in subset for c in by_bot.get(b, [])), key=lambda c: c.t_in)
        row = {"run": n, "t0": t0, "t1": t1, "bots": len(subset), "candidates": sum(1 for c in cs if t0 <= c.t_in < t1)}
        for arm in ("none", "gates", "brain"):
            row[arm] = run(cs, t0, t1, arm, seed=seed + n, priors=priors, families=families)
        results.append(row)
    return results
