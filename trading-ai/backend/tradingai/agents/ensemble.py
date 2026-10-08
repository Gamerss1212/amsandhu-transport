"""Ensemble and conflict resolution (sections 170, 198).

1. Only directional agents with status ok and unexpired evidence vote.
2. Votes are averaged WITHIN each information cluster first (all price-trend agents together count as one opinion),
   then across clusters with equal weight. "independent_clusters" says how many separate sources agreed.
3. Conflicts: clusters pointing opposite ways are listed, with their agents.
4. A veto from any data or risk agent blocks NEW entries for this decision (it never forces a trade).
5. The score is a strength in [-1, 1], NOT a probability. A probability is shown only when a calibration model has
   been fitted and evaluated for this instrument and timeframe (`calibrated_probability`, else None).
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from tradingai.agents.base import AgentOutput

ENTRY_THRESHOLD = 0.25          # |score| needed for the ensemble to lean one way
MIN_CLUSTERS = 2                # and at least this many independent clusters must agree


def combine(outputs: list[AgentOutput], calibrator: Optional[Callable[[float], float]] = None) -> dict:
    votes = [o for o in outputs if o.direction is not None and o.status == "ok"]
    stale = [o.agent_id for o in outputs if o.status == "stale"]
    clusters: dict[str, list[AgentOutput]] = {}
    for o in votes:
        clusters.setdefault(o.cluster, []).append(o)
    cluster_scores = {k: float(np.mean([o.score if o.direction else 0.0 for o in v])) for k, v in clusters.items()}
    score = float(np.mean(list(cluster_scores.values()))) if cluster_scores else 0.0
    direction = 0
    agreeing = 0
    if abs(score) >= ENTRY_THRESHOLD:
        sign = 1 if score > 0 else -1
        agreeing = sum(1 for s in cluster_scores.values() if np.sign(s) == sign and abs(s) > 0.05)
        direction = sign if agreeing >= MIN_CLUSTERS else 0
    pos = sorted(k for k, s in cluster_scores.items() if s > 0.05)
    neg = sorted(k for k, s in cluster_scores.items() if s < -0.05)
    conflicts = [{"for": pos, "against": neg}] if pos and neg else []
    vetoes = [{"agent": o.agent_id, "name": o.name, "flags": o.risk_flags, "message": o.message}
              for o in outputs if o.veto and o.group in ("data", "risk", "futures", "forex", "crypto", "meta")]
    flags = sorted({f for o in outputs for f in o.risk_flags})
    return {
        "score": round(score, 4), "direction": direction if not vetoes else 0, "raw_direction": direction,
        "independent_clusters": len(cluster_scores), "agreeing_clusters": agreeing,
        "cluster_scores": {k: round(v, 4) for k, v in cluster_scores.items()},
        "conflicts": conflicts, "vetoes": vetoes, "flags": flags, "stale_ignored": stale,
        "voters": len(votes), "unavailable": sum(1 for o in outputs if o.status == "unavailable"),
        "calibrated_probability": (round(float(calibrator(score)), 4) if calibrator else None),
        "probability_note": ("calibrated on held-out history" if calibrator else
                             "no calibrated probability: the score is a strength, not a chance of winning"),
    }
