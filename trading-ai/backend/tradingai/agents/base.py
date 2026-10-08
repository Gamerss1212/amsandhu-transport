"""Agent contract (sections 169-170). Agents are deterministic analytical workers, not language-model calls.

Every agent returns an AgentOutput:
  direction   -1 / 0 / +1, or None for agents that do not vote (data, risk, execution, research, meta)
  score       strength in [-1, 1]. NOT a probability: no agent output is shown as a percentage unless a calibration
              model has been fitted and evaluated (see ml/calibration.py)
  evidence    the real numbers it used
  data_ts     when the newest bar it used became available (UTC ms)
  valid_until data_ts + its validity horizon; older outputs are STALE and ignored by the ensemble
  risk_flags  short codes; veto=True blocks NEW entries for this decision (the risk service decides independently)
  status      ok | abstain | unavailable (needs data this installation lacks) | stale | error
  cluster     the information source (price_trend, volume, ...): ten agents reading the same prices count as one
              opinion in the ensemble, not ten
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

GROUPS = ("data", "market", "technical", "crypto", "futures", "forex", "research", "risk", "execution", "meta")


@dataclass
class AgentOutput:
    agent_id: str
    name: str
    group: str
    cluster: str
    status: str
    direction: Optional[int] = None
    score: float = 0.0
    evidence: dict = field(default_factory=dict)
    data_ts: Optional[int] = None
    valid_until: Optional[int] = None
    risk_flags: list = field(default_factory=list)
    veto: bool = False
    message: str = ""
    ms: float = 0.0

    def as_dict(self) -> dict:
        d = dict(vars(self))
        d["score"] = round(float(d["score"]), 4)
        d["ms"] = round(self.ms, 2)
        return d


@dataclass
class AgentSpec:
    agent_id: str
    name: str
    group: str
    cluster: str
    votes: bool
    horizon_bars: int
    description: str
    requires: tuple[str, ...]
    markets: tuple[str, ...]
    fn: Callable[[Any], dict]


AGENTS: dict[str, AgentSpec] = {}


def agent(agent_id: str, name: str, group: str, cluster: str, *, votes: bool = False, horizon_bars: int = 3,
          requires: tuple[str, ...] = (), markets: tuple[str, ...] = ("crypto", "stock", "etf", "fx", "future", "index"),
          description: str = ""):
    if group not in GROUPS:
        raise ValueError(group)

    def deco(fn: Callable[[Any], dict]):
        AGENTS[agent_id] = AgentSpec(agent_id, name, group, cluster, votes, horizon_bars, description or fn.__doc__ or "",
                                     tuple(requires), tuple(markets), fn)
        return fn
    return deco


def run(spec: AgentSpec, ctx) -> AgentOutput:
    t0 = time.perf_counter()
    base = dict(agent_id=spec.agent_id, name=spec.name, group=spec.group, cluster=spec.cluster)
    if ctx.market not in spec.markets:
        return AgentOutput(**base, status="abstain", message=f"not used for {ctx.market}")
    missing = [r for r in spec.requires if r not in ctx.extra_data]
    if missing:
        return AgentOutput(**base, status="unavailable", message="REQUIRES CONNECTION: needs " + ", ".join(missing))
    try:
        r = spec.fn(ctx) or {}
    except Exception as e:                       # noqa: BLE001 - an agent failure is reported, never hidden
        return AgentOutput(**base, status="error", message=f"{type(e).__name__}: {e}",
                           evidence={"trace": traceback.format_exc(limit=2)[-400:]})
    ts = ctx.data_ts
    step = ctx.step_ms
    out = AgentOutput(**base, status=r.get("status", "ok"), direction=r.get("direction") if spec.votes else None,
                      score=float(max(-1.0, min(1.0, r.get("score", 0.0)))), evidence=_clean(r.get("evidence", {})),
                      data_ts=ts, valid_until=(ts + spec.horizon_bars * step) if ts else None,
                      risk_flags=list(r.get("flags", [])), veto=bool(r.get("veto", False)), message=r.get("message", ""))
    if out.valid_until is not None and ctx.now_ms > out.valid_until and out.status == "ok":
        out.status = "stale"
    out.ms = (time.perf_counter() - t0) * 1000
    return out


def _clean(d: dict) -> dict:
    import math
    out = {}
    for k, v in d.items():
        if isinstance(v, float):
            out[k] = None if not math.isfinite(v) else round(v, 6)
        elif hasattr(v, "item"):
            x = v.item()
            out[k] = None if isinstance(x, float) and not math.isfinite(x) else (round(x, 6) if isinstance(x, float) else x)
        else:
            out[k] = v
    return out
