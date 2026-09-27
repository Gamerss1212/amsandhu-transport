"""Authoring helpers for the strategy catalog. `st()` records one candidate strategy; build.py
assigns ids, runs the duplicate review, compiles every executable rule with the platform's
engine, and writes the deliverables.

Research status (set per strategy, justified by its evidence list):
  sourced               a verified source states these rules (or rules differing only in stated,
                        documented adaptations) and reports a test of them
  incompletely sourced  a verified source documents the mechanism or the named setup, but not all of
                        the exact rules used here (thresholds, exits, timeframe or market were filled in)
  hypothesis            no verified source claims this edge; the rule is a practitioner idea or our own
Evidence relations: direct (tests these rules), origin (defines the setup/indicator), mechanism
(documents the behaviour the rule tries to exploit), contrary (finds no edge / edge gone after costs),
context (relevant background).
"""

CATALOG = []

STK = {"entry_start": "09:35", "entry_end": "15:30", "flat_minutes_before_close": 5}
CRY = {"flat_minutes_before_close": 5}
BOTH_SESS = {"stock": STK, "crypto": CRY}
STOCK = ("stock",)
CRYPTO = ("crypto",)
BOTH = ("stock", "crypto")


def st(key, name, family, sub, *, mech, logic, hyp, markets=BOTH, tf="5m", entry=None, direction=None, filters=(),
       order=None, stop=None, target=None, trail=None, exit=None, max_bars=0, session=None, mtd=2, cooldown=0,
       params=None, data=("bars",), ev=(), research="hypothesis", fail=(), notes="", blocked=None, spec=None,
       parent=None, anchor="", instruments=None, sizing=None, distinct=""):
    if isinstance(entry, str):
        entry = {"long": entry}
    if direction is None and entry:
        direction = "both" if ("long" in entry and "short" in entry) else ("long" if "long" in entry else "short")
    definition = None
    if entry and not blocked:
        definition = {"name": name, "family": family, "timeframe": tf, "direction": direction,
                      "params": dict(params or {}), "entry": entry, "filters": list(filters),
                      "order": order or {"type": "market"},
                      "stop": stop or {"type": "atr", "mult": 2.0, "n": 14},
                      "target": target or {"type": "none"}, "trail": trail or {"type": "none"},
                      "exit": exit or {}, "max_bars": max_bars,
                      "session": session if session is not None else (STK if markets == STOCK else
                                                                      (CRY if markets == CRYPTO else BOTH_SESS)),
                      "max_trades_per_day": mtd, "cooldown_bars": cooldown,
                      "sizing": sizing or {"risk_pct": 0.5, "max_notional_pct": 100.0},
                      "data": list(data)}
    CATALOG.append({"key": key, "name": name, "family": family, "subfamily": sub, "mechanism": mech,
                    "logic": logic, "anchor": anchor, "hypothesis": hyp, "markets": list(markets), "timeframe": tf,
                    "definition": definition, "data": list(data), "evidence": [
                        {"source": e[0], "relation": e[1], "note": e[2] if len(e) > 2 else ""} for e in ev],
                    "research_status": research, "failure_modes": list(fail), "notes": notes,
                    "blocked": blocked, "spec": spec, "parent": parent, "instruments": instruments,
                    "distinct": distinct})


def variant(key, parent, name, what, params=None, definition_patch=None, markets=None, tf=None, ev=(), notes=""):
    """A parameter / timeframe / market / same-template variant. Documented, never counted."""
    CATALOG.append({"key": key, "name": name, "parent": parent, "variant_of": parent, "what_changes": what,
                    "params": params or {}, "definition_patch": definition_patch or {}, "markets": markets,
                    "timeframe": tf, "evidence": [{"source": e[0], "relation": e[1], "note": e[2] if len(e) > 2 else ""}
                                                  for e in ev], "notes": notes, "is_variant": True})
