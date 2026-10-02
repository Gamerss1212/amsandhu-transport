#!/usr/bin/env python3
"""Jarvus's knowledge lookup: prints ONE entry in a few lines instead of Claude reading whole files.

  python3 know.py hammer                 # the entry, plus Jarvus's own measured result if it has one
  python3 know.py "golden cross"         # any candle, pattern, indicator, strategy, crypto or meme topic
  python3 know.py list [candles|charts|indicators|crypto|memes|trading|strategies]
  python3 know.py find <word>            # titles that mention a word
  python3 know.py measured [best|candles|charts|indicators|playbooks]
  --full prints a long section in full (default: the first ~900 characters)

Library: references/kb-*.md (≈220 short entries) first, then every `##`/`###` section of the other references
(the 320-strategy encyclopedia, the scoreboard, the untested library, the handbooks, the manual).
Measured results come from assets/signal_results.json (tools/measure_signals.py); nothing else is quoted.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REF = os.path.join(ROOT, "references")
RESULTS = os.path.join(ROOT, "assets", "signal_results.json")
KB = {"candles": "kb-candles.md", "charts": "kb-chart-patterns.md", "indicators": "kb-indicators.md",
      "crypto": "kb-crypto.md", "memes": "kb-memecoins.md", "trading": "kb-daytrading.md"}
SKIP = {"kb-measured.md"}
MARK = {"held up and made money": "✓", "beat random, still lost after fees": "+", "worse than random": "✗",
        "slightly better, not reliable": "~", "no better than random": "·", "too few": "n/a"}
LEGEND = "(R/trade, Jarvus exits, NDAX fees, vs random entries; ✓ beat random & profitable both halves, + beat random but lost after fees, ~ unreliable, · no better, ✗ worse)"
STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "on", "what", "is", "how", "do", "does", "i", "me", "about",
        "tell", "explain", "teach", "jarvus", "jarvis", "for", "with", "it", "work", "works", "use", "trade", "trading"}


def norm(s):
    return re.sub(r"[^a-z0-9%.+]+", " ", s.lower().replace("_", " ")).strip()


def words(s):
    return [w for w in norm(s).split() if w not in STOP]


def load():
    entries = []
    for path in sorted(glob.glob(os.path.join(REF, "*.md"))):
        fname = os.path.basename(path)
        if fname in SKIP:
            continue
        kb = fname.startswith("kb-")
        lines = open(path, encoding="utf-8").read().splitlines()
        cur = None
        for ln in lines:
            m = re.match(r"^(#{2,3}) (.+)$", ln)
            if m and (not kb or m.group(1) == "###"):
                cur = {"title": m.group(2).strip(), "file": fname, "kb": kb, "level": len(m.group(1)),
                       "ids": [], "aka": [], "body": []}
                entries.append(cur)
                continue
            if cur is None or (kb and ln.startswith("## ")):
                if kb and ln.startswith("## "):
                    cur = None
                continue
            if kb and (ln.startswith("id:") or ln.startswith("aka:")):
                for part in ln.split(" · "):
                    k, _, v = part.partition(":")
                    vals = [x.strip() for x in v.split(",") if x.strip()]
                    (cur["ids"] if k.strip() == "id" else cur["aka"]).extend(vals)
                continue
            cur["body"].append(ln)
    return entries


def score(e, q, qw):
    full = norm(e["title"])
    names = [re.sub(r"^(strat \d+|\d+) ", "", full)] + [norm(a) for a in e["aka"]] + [norm(i) for i in e["ids"]]
    qs = " ".join(qw)
    best = 0
    if full.startswith(q + " ") or full == q:
        best = 900                                       # "STRAT-075", "5." style ids
    for n in names:
        if not n:
            continue
        if n == q or n == qs:
            best = max(best, 1000)
        elif q and len(q) >= 3 and re.search(rf"\b{re.escape(q)}\b", n):
            best = max(best, 600 - min(200, len(n) - len(q)))
        elif (len(n) >= 4 or n in qw) and re.search(rf"\b{re.escape(n)}\b", q):
            best = max(best, 400 + min(150, len(n)))
    if qw:
        pool = set(" ".join(names).split())
        hit = sum(1 for w in qw if w in pool or (len(w) > 3 and any(p.startswith(w) for p in pool)))
        best = max(best, int(300 * hit / len(qw)) if hit == len(qw) else int(150 * hit / len(qw)))
        body = norm(" ".join(e["body"][:40]))
        best += min(30, 6 * sum(1 for w in qw if f" {w} " in f" {body} "))
    if e["kb"]:
        best += 60
    elif e["level"] == 2:
        best -= 10
    return best


def results():
    try:
        with open(RESULTS, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def measured_lines(ids, data):
    if not data or not ids:
        return []
    R, defs = data["results"], data["meta"]["defs"]
    out, dirs = [], []
    for sid in ids:
        if sid not in defs:
            continue
        cells = []
        for g, gl in (("majors", "majors"), ("memes", "memes")):
            for tf in ("1h", "4h"):
                r = R[g][tf].get(sid)
                if not r or r.get("n_all", 0) < 30:
                    cells.append(f"{gl} {tf} n/a")
                    continue
                cells.append(f"{gl} {tf} {MARK[r['label']]} {r['r_all']:+.2f} vs {r['b_all']:+.2f} ({r['n_all']})")
                if r["n"] >= 30 and abs(r["t_dir"]) >= 2.5:
                    dirs.append(f"{defs[sid]['name'] if len(ids) > 1 else ''} {gl} {tf} {r['ex12']:+.2f}%".strip())
        out.append(f"Measured · {defs[sid]['name']}: " + " · ".join(cells))
    if out:
        out.append("12h move after it vs an average bar: " + ("; ".join(dirs) if dirs else "no reliable difference"))
        out.append(LEGEND)
    return out


def show(e, full, data, entries=()):
    body = [ln for ln in e["body"] if ln.strip()]
    if not e["kb"] and e["level"] == 2 and len(body) < 3:          # a "##" heading whose text sits in "###" parts
        k = entries.index(e) + 1
        while k < len(entries) and entries[k]["file"] == e["file"] and entries[k]["level"] == 3:
            body += [f"**{entries[k]['title']}**"] + [ln for ln in entries[k]["body"] if ln.strip()]
            k += 1
    head = e["title"] + ("" if e["kb"] else f"  [{e['file']}]")
    if e["kb"]:
        lines = [head] + body[:10]
    else:
        lines, size = [head], 0
        for ln in body:
            if not full and size + len(ln) > 900:
                lines.append(f"… (more: python3 scripts/know.py \"{e['title']}\" --full)")
                break
            if full and size > 6000:
                lines.append(f"… (rest in references/{e['file']})")
                break
            lines.append(ln)
            size += len(ln)
    return "\n".join(lines + measured_lines(e["ids"], data))


def cmd_list(entries, what):
    what = (what or "").lower()
    if what in ("strategies", "strategy"):
        parts, cur = [], None
        for e in entries:
            if e["file"] == "strategy-encyclopedia.md":
                if e["level"] == 2 and e["title"].startswith("Part"):
                    cur = [e["title"], 0]
                    parts.append(cur)
                elif e["level"] == 3 and cur and re.match(r"^\d+\.", e["title"]):
                    cur[1] += 1
        return "\n".join(f"{t} ({n})" for t, n in parts if n) + "\nAsk: python3 scripts/know.py <strategy name>"
    files = [KB[what]] if what in KB else list(KB.values())
    out = []
    for f in files:
        names = [e["title"] for e in entries if e["file"] == f]
        label = next(k for k, v in KB.items() if v == f)
        out.append(f"{label} ({len(names)}): " + ", ".join(names))
    return "\n".join(out)


def cmd_find(entries, word):
    w = norm(word)
    hits = [e for e in entries if w in norm(e["title"]) or any(w in norm(a) for a in e["aka"])]
    if not hits:
        hits = [e for e in entries if w in norm(" ".join(e["body"]))]
    return "\n".join(f"{e['title']}  [{e['file']}]" for e in hits[:25]) + (f"\n… {len(hits) - 25} more" if len(hits) > 25 else "") \
        if hits else f"Nothing mentions '{word}'."


def cmd_measured(what, data):
    if not data:
        return "No measurement file (run tools/measure_signals.py)."
    R, defs = data["results"], data["meta"]["defs"]
    fam = {"candles": "candle", "charts": "chart", "indicators": "indicator", "playbooks": "playbook"}.get((what or "").lower())
    rows, counts = [], {}
    for sid, d in defs.items():
        if fam and d["family"] != fam:
            continue
        for g in ("majors", "memes"):
            for tf in ("1h", "4h"):
                r = R[g][tf].get(sid)
                if not r or r.get("n_all", 0) < 30:
                    continue
                m = MARK[r["label"]]
                counts[m] = counts.get(m, 0) + 1
                if m in ("✓", "+") if fam else m == "✓":
                    rows.append((r["r_all"], f"{m} {d['name']} — {g} {tf}: {r['r_all']:+.2f}R vs random {r['b_all']:+.2f}R, n {r['n_all']}"))
    rows.sort(reverse=True)
    head = (f"Jarvus measured {fam or 'all'} signals on {', '.join(data['meta']['coins'])} hourly data (1h and 4h), "
            f"exits: {data['meta']['exits']}, NDAX fees. Cells: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    tail = "Many tests on coins that move together: a few marks are luck. Not a forecast. Full table: references/kb-measured.md"
    return "\n".join([head] + [x for _, x in rows[:15]] + [tail])


def main(argv):
    full = "--full" in argv
    argv = [a for a in argv if a != "--full"]
    if not argv:
        print(__doc__.strip().splitlines()[0])
        print("Topics: " + ", ".join(KB) + ", strategies. Try: python3 scripts/know.py list candles")
        return 0
    entries = load()
    if argv[0] == "list":
        print(cmd_list(entries, argv[1] if len(argv) > 1 else ""))
        return 0
    if argv[0] == "find" and len(argv) > 1:
        print(cmd_find(entries, " ".join(argv[1:])))
        return 0
    if argv[0] == "measured":
        print(cmd_measured(argv[1] if len(argv) > 1 else "", results()))
        return 0
    query = " ".join(argv)
    q, qw = norm(query), words(query)
    ranked = sorted(entries, key=lambda e: score(e, q, qw), reverse=True)
    top = ranked[0] if ranked else None
    if not top or score(top, q, qw) < 140:
        near = ", ".join(e["title"] for e in ranked[:5])
        print(f"Not in Jarvus's library as asked. Closest: {near}")
        return 0
    print(show(top, full, results(), entries))
    others = [e["title"] for e in ranked[1:4] if score(e, q, qw) >= score(top, q, qw) - 40 and e["title"] != top["title"]]
    if others:
        print("Also: " + ", ".join(others))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
