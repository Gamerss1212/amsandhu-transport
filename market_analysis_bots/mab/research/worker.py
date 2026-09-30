"""One research job, run in its own process by mab.research.jobs.Pool.

    main(db_path, job_id, cache_dir)

Handlers
    walk_forward   spec: strategy definition (or id + catalog path), venue, instrument, days, fee_profile,
                   cost_mult, participation, k_folds, draws
    gate_drift     spec: venue, instrument, asset (crypto|stock), days (>= 100), recent_days
    brain_eval     spec: candidate (version), champion (version, or "none" for the no-brain baseline)
"""

from __future__ import annotations

import json
import math
import os
import time
import traceback

from mab.research.jobs import JobQueue, spec_hash


def main(db_path: str, jid: str, cache_dir: str):
    from mab.storage import Storage
    st = Storage(db_path)
    q = JobQueue(st)
    j = q.get(jid)
    if j is None or j["state"] != "running":
        return
    t0 = time.process_time()
    last = [0.0]

    def progress(frac, msg):
        if time.time() - last[0] > 0.5 or frac >= 1.0:
            last[0] = time.time()
            q.progress(jid, frac, msg)
    try:
        fn = {"walk_forward": walk_forward, "gate_drift": gate_drift, "brain_eval": brain_eval}[j["kind"]]
        result, key, fp = fn(st, q, j["spec"], cache_dir, progress)
        cached = bool(result.pop("_cached", False))
        if key and not cached:
            q.cache_put(key, j["kind"], result, fp)
        q.finish(jid, result, cached=cached, cpu_s=round(time.process_time() - t0, 2))
    except Exception as e:                                              # noqa: BLE001
        q.fail(jid, f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")


def _definition(spec: dict) -> dict:
    d = spec.get("definition")
    if d:
        return d
    sid = spec.get("strategy_id")
    cat = spec.get("catalog")
    if not sid or not cat or not os.path.exists(cat):
        raise ValueError("give a strategy definition, or a strategy id and the catalog path")
    with open(cat, encoding="utf-8") as fh:
        for rec in json.load(fh)["strategies"]:
            if rec["id"] == sid and rec.get("definition"):
                return dict(rec["definition"], id=sid)
    raise ValueError(f"strategy {sid} has no executable definition")


def walk_forward(st, q, spec, cache_dir, progress):
    from mab.costs import FEE_PROFILES
    from mab.research import data as D, evaluate as RE
    d = _definition(spec)
    venue, inst = spec["venue"], spec["instrument"]
    tf = d.get("timeframe", "5m")
    days = int(spec.get("days") or 60)
    if not 7 <= days <= 2000:
        raise ValueError("days must be between 7 and 2000")
    asset = "stock" if venue == "yahoo" else "crypto"
    progress(0.02, f"loading {days} days of {tf} bars for {inst}")
    bars, qual = D.fetch(venue, inst, tf, days, cache_dir)
    if len(bars) < 500:
        raise ValueError(f"only {len(bars)} bars available for {venue}:{inst} {tf}; not enough to evaluate")
    fee = FEE_PROFILES.get(spec.get("fee_profile") or "venue")
    key = spec_hash("walk_forward", {k: v for k, v in spec.items() if k != "catalog"} | {"definition": d},
                    qual["fingerprint"])
    hit = q.cache_get(key)
    if hit:
        progress(1.0, "answered from the cache (same question, same data)")
        return dict(hit, _cached=True), key, qual["fingerprint"]
    fr = D.frame(bars, asset)
    res = RE.run(d, fr, venue, fees=fee, cost_mult=float(spec.get("cost_mult") or 1.0),
                 participation=float(spec["participation"]) if spec.get("participation") is not None else 0.05,
                 k_folds=int(spec.get("k_folds") or 5), draws=min(int(spec.get("draws") or 100), 500),
                 seed=int(spec.get("seed") or 7), progress=lambda f, m: progress(0.05 + 0.9 * f, m))
    res.update({"data_quality": qual, "venue": venue, "instrument": inst, "timeframe": tf, "days": days,
                "fee_profile": spec.get("fee_profile") or "venue",
                "summary": f"{d.get('name', d.get('id'))} on {inst}: {res['verdict']}"})
    return res, key, qual["fingerprint"]


def gate_drift(st, q, spec, cache_dir, progress):
    """Recompute the volatility gate over recent history and check it against what it delivered on its held-out test:
    precision of LOUD/QUIET flags on the most recent `recent_days`, and how far recent features moved from training."""
    from mab.research import data as D
    from mab.volgate import FEATURES, HORIZON, Bars, VolGate, features
    asset = spec.get("asset") or ("stock" if spec.get("venue") == "yahoo" else "crypto")
    days, recent = int(spec.get("days") or 130), int(spec.get("recent_days") or 30)
    if days < recent + 95:
        raise ValueError("days must cover the recent window plus 95 days of history for the labels")
    progress(0.05, "loading hourly bars")
    bars, qual = D.fetch(spec["venue"], spec["instrument"], "1h", days, cache_dir)
    if len(bars) < 24 * (recent + 60):
        raise ValueError("not enough hourly history")
    key = spec_hash("gate_drift", spec, qual["fingerprint"])
    hit = q.cache_get(key)
    if hit:
        return dict(hit, _cached=True), key, qual["fingerprint"]
    vg = VolGate()
    m = vg.model.get(asset)
    if not m:
        raise ValueError(f"no volatility gate model for {asset}")
    H = HORIZON[asset]
    t = [b.event_time for b in bars]
    o, h, l, c, v = ([getattr(b, k) for b in bars] for k in ("open", "high", "low", "close", "volume"))
    gb = Bars(t, o, h, l, c, v)
    n = len(bars)
    fwd = [None] * n                                   # the next H hours' range / close (the label quantity)
    for i in range(n - H):
        fwd[i] = (max(h[i + 1:i + 1 + H]) - min(l[i + 1:i + 1 + H])) / c[i]
    start = n - H - recent * 24
    rows, fsum, fcnt = [], [0.0] * len(FEATURES), 0
    for i in range(max(start, 24 * 95), n - H):
        f = features(gb, i)
        if f is None:
            continue
        hist = [fwd[k] for k in range(max(0, i - 90 * 24), i - H) if fwd[k] is not None]
        if len(hist) < 500:
            continue
        hs = sorted(hist)
        lo, hi = hs[len(hs) // 3], hs[2 * len(hs) // 3]
        label = "LOUD" if fwd[i] >= hi else ("QUIET" if fwd[i] <= lo else "NORMAL")
        r = vg.read(gb, i, asset)
        rows.append((r["state"], label))
        fsum = [a + b for a, b in zip(fsum, f)]
        fcnt += 1
        if len(rows) % 100 == 0:
            progress(0.1 + 0.8 * (i - start) / max(1, n - H - start), f"{len(rows)} hourly readings checked")
    out = {"asset": asset, "venue": spec["venue"], "instrument": spec["instrument"], "readings": len(rows),
           "data_quality": qual}
    status = "ok"
    for kind in ("LOUD", "QUIET"):
        flagged = [lab for s, lab in rows if s == kind]
        prec = sum(1 for x in flagged if x == kind) / len(flagged) if flagged else None
        test = (m.get(f"test_{kind.lower()}") or {})
        exp = test.get("precision")
        se = math.sqrt(exp * (1 - exp) / len(flagged)) if flagged and exp else None
        st_k = "insufficient" if len(flagged) < 20 else ("alert" if prec < exp - 3 * se else ("warn" if prec < exp - 2 * se else "ok"))
        out[kind.lower()] = {"flagged": len(flagged), "precision": prec, "expected_precision": exp,
                             "base_rate": test.get("base_rate"), "status": st_k}
        if st_k in ("warn", "alert") and status != "alert":
            status = st_k
    shift = {}
    if fcnt:
        mu = [x / fcnt for x in fsum]
        for k, name in enumerate(FEATURES):
            if k == 0 or not m["std"][k]:
                continue
            z = (mu[k] - m["mean"][k]) / m["std"][k]
            shift[name] = round(z, 3)
        big = {k: z for k, z in shift.items() if abs(z) > 0.75}
        out["feature_shift_sd"] = shift
        out["features_shifted"] = big
        if big and status == "ok":
            status = "warn"
    out["status"] = status
    out["summary"] = (f"volatility gate on {spec['instrument']}: {status}; LOUD precision "
                      f"{_pct(out['loud']['precision'])} (test {_pct(out['loud']['expected_precision'])}), QUIET "
                      f"{_pct(out['quiet']['precision'])} (test {_pct(out['quiet']['expected_precision'])})")
    now = int(time.time() * 1000)
    for kind in ("loud", "quiet"):
        st.write("INSERT INTO drift_reports (ts, subject, metric, value, threshold, status, body) VALUES (?,?,?,?,?,?,?)",
                 (now, f"volgate:{asset}:{spec['instrument']}", f"{kind}_precision", out[kind]["precision"],
                  out[kind]["expected_precision"], out[kind]["status"], json.dumps(out[kind])))
    return out, key, qual["fingerprint"]


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def brain_eval(st, q, spec, cache_dir, progress):
    """Replay both brains' decisions, deterministically, on trades that closed after the candidate was frozen (so the
    candidate has not learned from them): which one kept the better trades and skipped the worse ones."""
    from mab.brain import FleetBrain
    from mab.metrics import bootstrap_ci
    cand = st.query("SELECT * FROM model_versions WHERE model='brain' AND version=?", (spec.get("candidate"),))
    if not cand:
        raise ValueError("unknown candidate brain version")
    since = cand[0]["created"]
    champ = None
    if spec.get("champion") and spec["champion"] != "none":
        r = st.query("SELECT * FROM model_versions WHERE model='brain' AND version=?", (spec["champion"],))
        if not r:
            raise ValueError("unknown champion brain version")
        champ = r[0]
    samples = st.query("SELECT * FROM brain_samples WHERE ts > ? ORDER BY ts", (since,))
    progress(0.2, f"{len(samples)} trades closed since the candidate was frozen")

    def load(row):
        b = FleetBrain(mode="active")
        b.restore(json.loads(row["blob"]))
        return b
    cb = load(cand[0])
    hb = load(champ) if champ else None
    diffs, rows = [], {"candidate": [], "champion": []}
    for s in samples:
        f = json.loads(s["features"] or "[]")
        dc = cb.evaluate_sample(s["strategy_key"], s["instrument"], s["regime"], f, s["cost_r"], s["gate"])
        dh = hb.evaluate_sample(s["strategy_key"], s["instrument"], s["regime"], f, s["cost_r"], s["gate"]) if hb else \
            {"action": "approve", "size": 1.0}
        r = max(-3.0, min(3.0, s["r"]))
        vc, vh = dc["size"] * r, dh["size"] * r
        rows["candidate"].append(vc)
        rows["champion"].append(vh)
        diffs.append(vc - vh)
    n = len(samples)
    out = {"candidate": spec.get("candidate"), "champion": spec.get("champion") or "none", "trades": n,
           "since": since, "min_trades": 50}
    if n:
        out["candidate_value_r"] = round(sum(rows["candidate"]) / n, 4)
        out["champion_value_r"] = round(sum(rows["champion"]) / n, 4)
        out["difference_r"] = round(sum(diffs) / n, 4)
        out["difference_ci95"] = bootstrap_ci(diffs)
    ci = out.get("difference_ci95")
    if n < 50:
        rec = "not enough forward trades yet"
    elif ci and ci[0] > 0:
        rec = "candidate better (95% interval of the difference above zero)"
    elif ci and ci[1] < 0:
        rec = "candidate worse"
    else:
        rec = "no clear difference"
    out["recommendation"] = rec
    out["summary"] = f"brain {out['candidate']} vs {out['champion']}: {rec} ({n} forward trades)"
    return out, None, ""
