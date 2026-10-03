"""Ultron's brain: one learned decision-maker over 50 agents. The same code runs in the backtests and in the app.

What it knows: the after-cost result (in R) of every signal every agent has ever produced, also the ones it
refused. It pools them in a hierarchy so thin evidence borrows from related evidence:

    fleet -> family (candle / chart / indicator / playbook) x group (majors / memes)
          -> agent -> agent in this volatility state (LOUD / NORMAL / QUIET)
          -> agent in this volatility state and this Bitcoin regime (above / below its 200-day average)

Each level's expected R is shrunk toward its parent with the weight of `shrink` pseudo-trades. A trade is taken
only if   expected R - z x standard error >= theta   and every hard rule passes (cost, volatility, weekend,
regime, caps). Size = 1 + size_a x expected R (0.5x to 1.5x), halved when costs are 0.20-0.33R.
It learns by adding every completed signal (taken or not) as it completes. It never changes its own code.
"""

from __future__ import annotations

import math

DEFAULT_PARAMS = {
    "theta": 0.05, "z": 1.0, "shrink": 20.0, "size_a": 1.0, "gate_rule": "no_quiet", "loud_mult": 0.6,
    "weekend_off": True, "regime_rule": "memes_off_in_bear", "max_open": 3, "max_major_open": 1, "max_meme_open": 2,
    "risk_major": 0.006, "risk_meme": 0.003, "daily_stop_r": -3.0, "loss_streak": 3, "sel_z": 1.0, "sel_min_n": 40,
    "max_per_signal": 2, "n_agents": 50, "variants": "all", "sel_window_days": 0, "evidence": "all",
}
VARIANTS = {"all": {"any", "loud", "trend", "loudtrend"}, "loud_only": {"loud", "loudtrend"}, "loudtrend": {"loudtrend"}}
CLIP = 3.0


class Brain:
    def __init__(self, params=None, stats=None):
        self.p = dict(DEFAULT_PARAMS, **(params or {}))
        self.stats = stats if stats is not None else {}          # key -> [w, sum_r, sum_r2]

    # ------------------------------------------------------------ learning
    @staticmethod
    def keys(ev):
        a = ev["agent"]
        return ("fleet",), ("fam", ev["fam"], ev["group"]), ("a", a), ("ag", a, ev["gate"]), ("agr", a, ev["gate"], ev["bull"])

    def learn(self, ev, r, w=1.0, agent_level=True):
        r = max(-CLIP, min(CLIP, r))
        for k in (self.keys(ev) if agent_level else self.keys(ev)[:2]):
            s = self.stats.get(k)
            if s is None:
                self.stats[k] = [w, w * r, w * r * r]
            else:
                s[0] += w
                s[1] += w * r
                s[2] += w * r * r

    # ------------------------------------------------------------ estimating
    def estimate(self, ev):
        """(expected R, standard error, evidence) for this signal in this context."""
        k = self.p["shrink"]
        m, chain = 0.0, self.keys(ev)
        for key in chain:
            s = self.stats.get(key)
            w, sr = (s[0], s[1]) if s else (0.0, 0.0)
            m = (sr + k * m) / (w + k)
        a = self.stats.get(("a", ev["agent"])) or self.stats.get(("fam", ev["fam"], ev["group"])) or self.stats.get(("fleet",))
        if a and a[0] > 1:
            var = max(0.25, a[2] / a[0] - (a[1] / a[0]) ** 2)
            w = self.stats.get(("a", ev["agent"]), [0])[0]
        else:
            var, w = 1.5, 0.0
        return m, math.sqrt(var / (w + k)), w

    # ------------------------------------------------------------ deciding (one signal)
    def decide(self, ev):
        """-> (take, size_multiplier, reason, expected_R, standard_error)"""
        p = self.p
        m, se, w = self.estimate(ev)
        if ev["cost_r"] > 0.33:
            return False, 0.0, "fees too high for this stop (cost > 0.33R)", m, se
        g = ev["gate"]
        if g == "U":
            return False, 0.0, "no volatility reading yet", m, se
        if p["gate_rule"] == "loud_only" and g != "L":
            return False, 0.0, "waiting for a LOUD (big-move) period", m, se
        if p["gate_rule"] == "no_quiet" and g == "Q":
            return False, 0.0, "market too quiet for the fees", m, se
        if p["weekend_off"] and ev["group"] == "majors" and ev["weekend"]:
            return False, 0.0, "weekend: no new BTC/ETH/SOL trades", m, se
        if p["regime_rule"] == "memes_off_in_bear" and ev["group"] == "memes" and ev["bull"] is False:
            return False, 0.0, "Bitcoin below its 200-day average: memes off", m, se
        if m - p["z"] * se < p["theta"]:
            return False, 0.0, f"learned edge too small ({m:+.2f}R)", m, se
        size = max(0.5, min(1.5, 1 + p["size_a"] * m))
        if ev["cost_r"] > 0.20:
            size *= 0.5
        if g == "L":
            size *= p["loud_mult"]
        return True, size, f"approved: learned edge {m:+.2f}R", m, se

    # ------------------------------------------------------------ choosing the 50 agents
    def select(self, cand_stats, defs):
        """cand_stats: {candidate_id: (n, mean, sd)} from completed history. Returns the chosen ids, best first."""
        p = self.p
        scored = []
        allowed = VARIANTS[p["variants"]]
        for cid, (n, mean, sd) in cand_stats.items():
            if n < p["sel_min_n"] or defs[cid].get("variant", "any") not in allowed:
                continue
            lcb = mean - p["sel_z"] * sd / math.sqrt(n)
            scored.append((lcb, cid))
        scored.sort(reverse=True)
        out, per_sig = [], {}
        for lcb, cid in scored:
            sig = defs[cid]["signal"]
            if per_sig.get(sig, 0) >= p["max_per_signal"]:
                continue
            per_sig[sig] = per_sig.get(sig, 0) + 1
            out.append(cid)
            if len(out) >= p["n_agents"]:
                break
        return out


class Book:
    """The account rules every decision must also pass: open-trade caps, one trade per coin, daily stop."""

    def __init__(self, params):
        self.p = params
        self.open = {}               # coin -> group
        self.day, self.day_r, self.streak = None, 0.0, 0

    def can_open(self, coin, group, day):
        p = self.p
        if day != self.day:
            self.day, self.day_r, self.streak = day, 0.0, 0
        if coin in self.open:
            return False, "already in this coin"
        if self.day_r <= p["daily_stop_r"]:
            return False, "daily loss limit reached"
        if self.streak >= p["loss_streak"]:
            return False, f"{p['loss_streak']} losses in a row today"
        if len(self.open) >= p["max_open"]:
            return False, "too many open trades"
        n_grp = sum(1 for g in self.open.values() if g == group)
        if group == "majors" and n_grp >= p["max_major_open"]:
            return False, "already holding BTC/ETH/SOL (they move together)"
        if group == "memes" and n_grp >= p["max_meme_open"]:
            return False, "meme trade limit reached"
        return True, ""

    def opened(self, coin, group):
        self.open[coin] = group

    def closed(self, coin, r_sized, day):
        self.open.pop(coin, None)
        if day != self.day:
            self.day, self.day_r, self.streak = day, 0.0, 0
        self.day_r += r_sized
        self.streak = self.streak + 1 if r_sized < 0 else 0
