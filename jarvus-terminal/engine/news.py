#!/usr/bin/env python3
"""Real news from public RSS feeds, matched to the markets on screen.

Parsed with the standard library's XML module rather than a feed library so the app
keeps its no-install promise. Feeds break, rename and redirect constantly, so every
source is fetched independently and a dead one is reported rather than fatal.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Dict, List, Optional

import config
from engine import http

# Words that historically precede violent repricing. Used only to flag an item as
# worth reading, never as a trading signal.
HOT_WORDS = [
    "hack", "exploit", "breach", "drain", "rug", "insolven", "bankrupt", "halt", "freeze",
    "sec ", "lawsuit", "sue", "regulat", "ban", "delist", "list on", "listing",
    "etf", "approval", "approve", "unlock", "upgrade", "fork", "mainnet", "outage",
    "liquidat", "crash", "plunge", "surge", "soar", "record high", "all-time high",
    "fed", "cpi", "inflation", "rate cut", "rate hike", "fomc",
]


def _text(el, tag) -> str:
    node = el.find(tag)
    return html.unescape((node.text or "").strip()) if node is not None and node.text else ""


def _parse_date(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S"):
            try:
                d = datetime.strptime(s.strip(), fmt)
                return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip()


def fetch_feed(name: str, url: str) -> List[dict]:
    text = http.get_text(url, ttl=config.CACHE_TTL_NEWS)
    if not text:
        return []
    try:
        root = ET.fromstring(text.encode("utf-8", errors="replace"))
    except ET.ParseError:
        return []
    items = []
    # RSS 2.0
    for it in root.iter("item"):
        title = _text(it, "title")
        if not title:
            continue
        items.append({"source": name, "title": title, "link": _text(it, "link"),
                      "published": _parse_date(_text(it, "pubDate")),
                      "summary": _strip_html(_text(it, "description"))[:280]})
    # Atom
    if not items:
        ns = "{http://www.w3.org/2005/Atom}"
        for it in root.iter(f"{ns}entry"):
            title_el = it.find(f"{ns}title")
            link_el = it.find(f"{ns}link")
            if title_el is None:
                continue
            items.append({
                "source": name,
                "title": html.unescape((title_el.text or "").strip()),
                "link": (link_el.get("href") if link_el is not None else ""),
                "published": _parse_date(_text(it, f"{ns}updated") or _text(it, f"{ns}published")),
                "summary": _strip_html(_text(it, f"{ns}summary"))[:280],
            })
    return items


def headlines(limit: int = None) -> dict:
    limit = limit or config.NEWS_MAX_ITEMS
    all_items: List[dict] = []
    ok, dead = [], []
    for name, url in config.NEWS_FEEDS:
        got = fetch_feed(name, url)
        (ok if got else dead).append(name)
        all_items += got

    seen = set()
    unique = []
    for it in all_items:
        key = it["title"].lower()[:90]
        if key in seen:
            continue
        seen.add(key)
        low = (it["title"] + " " + it["summary"]).lower()
        it["hot"] = [w.strip() for w in HOT_WORDS if w in low][:4]
        it["published_iso"] = it["published"].strftime("%Y-%m-%dT%H:%M:%SZ") if it["published"] else None
        it["age_minutes"] = (int((datetime.now(timezone.utc) - it["published"]).total_seconds() // 60)
                             if it["published"] else None)
        it.pop("published", None)
        unique.append(it)

    unique.sort(key=lambda i: (i["age_minutes"] is None, i["age_minutes"] or 0))
    return {"items": unique[:limit], "sources_ok": ok, "sources_dead": dead,
            "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def match_symbols(items: List[dict], bases: List[str]) -> Dict[str, List[dict]]:
    """Attach headlines to the assets they name. Short tickers need word boundaries."""
    out: Dict[str, List[dict]] = {b: [] for b in bases}
    names = {b: re.compile(rf"\b{re.escape(b)}\b", re.I) for b in bases if len(b) >= 2}
    aliases = {"BTC": ["bitcoin"], "ETH": ["ethereum", "ether"], "SOL": ["solana"],
               "XRP": ["ripple"], "DOGE": ["dogecoin"], "ADA": ["cardano"], "AVAX": ["avalanche"]}
    for it in items:
        blob = it["title"] + " " + it["summary"]
        for b, rx in names.items():
            hit = bool(rx.search(blob)) or any(a in blob.lower() for a in aliases.get(b, []))
            if hit:
                out[b].append(it)
    return {k: v for k, v in out.items() if v}
