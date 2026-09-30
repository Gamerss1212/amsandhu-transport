"""News from feeds the owner configured (RSS or Atom). Nothing else is fetched, and no bot reads it.

Headlines are external, unverified text: they are stored and shown as such, and they can be summarised by the
research assistant (as untrusted data). They never reach a strategy, the brain, the risk layer or the order path.
No sentiment score is computed: this build ships no sentiment model that has been calibrated and evaluated, so it
does not pretend to have one.
"""

from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import List

MAX_BYTES = 600_000
MAX_FEEDS = 12


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()[:300]


def validate_url(url: str) -> str:
    u = urllib.parse.urlparse((url or "").strip())
    if u.scheme != "https" or not u.netloc or u.hostname in ("localhost", "127.0.0.1") or \
            (u.hostname or "").endswith(".local"):
        raise ValueError("feeds must be public https:// addresses")
    return u.geturl()


def feeds(storage) -> List[str]:
    return list(storage.kv_get("news_feeds", []) or [])


def set_feeds(storage, urls: List[str]) -> List[str]:
    out = []
    for u in urls or []:
        if u and u.strip():
            out.append(validate_url(u))
    if len(out) > MAX_FEEDS:
        raise ValueError(f"at most {MAX_FEEDS} feeds")
    storage.kv_set("news_feeds", out)
    storage.audit("data", f"news feeds set: {len(out)} configured (external, unverified text; no bot reads them)",
                  stage="news_config", payload={"feeds": out})
    return out


def _fetch(url: str, timeout: float = 10.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvus/7 (feed reader)", "Accept": "application/rss+xml, "
                                               "application/atom+xml, application/xml;q=0.9, */*;q=0.5"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(MAX_BYTES + 1)[:MAX_BYTES]


def parse(data: bytes, source: str) -> List[dict]:
    if b"<!ENTITY" in data[:5000].upper():
        raise ValueError("feed declares XML entities; refused")
    root = ET.fromstring(data)
    items = []
    atom = "{http://www.w3.org/2005/Atom}"
    for it in root.iter():
        tag = it.tag
        if tag == "item":
            t = it.find("title")
            title = "".join(t.itertext()) if t is not None else None       # titles may carry inline markup
            link, pub = it.findtext("link"), it.findtext("pubDate")
        elif tag == f"{atom}entry":
            t = it.find(f"{atom}title")
            title = "".join(t.itertext()) if t is not None else None
            ln = it.find(f"{atom}link")
            link = ln.get("href") if ln is not None else None
            pub = it.findtext(f"{atom}updated") or it.findtext(f"{atom}published")
        else:
            continue
        ts = None
        try:
            ts = int(parsedate_to_datetime(pub).timestamp() * 1000) if pub and "," in pub else None
        except (TypeError, ValueError):
            ts = None
        if ts is None and pub:
            try:
                from datetime import datetime
                ts = int(datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp() * 1000)
            except ValueError:
                ts = None
        if title:
            items.append({"title": _clean(title), "link": (link or "").strip()[:500], "published": ts, "source": source,
                          "untrusted": True})
    return items


def refresh(storage, fetch=_fetch) -> dict:
    out, errors = [], {}
    for url in feeds(storage):
        try:
            out.extend(parse(fetch(url), urllib.parse.urlparse(url).hostname))
        except Exception as e:                                          # noqa: BLE001
            errors[url] = f"{type(e).__name__}: {e}"[:200]
    out.sort(key=lambda x: x.get("published") or 0, reverse=True)
    seen, uniq = set(), []
    for x in out:
        k = x["title"].lower()
        if k not in seen:
            seen.add(k)
            uniq.append(x)
    storage.kv_set("news_items", {"time": int(time.time() * 1000), "items": uniq[:200], "errors": errors})
    return {"items": len(uniq[:200]), "errors": errors}


def items(storage, symbol: str = None, limit: int = 50) -> dict:
    d = storage.kv_get("news_items", {}) or {}
    rows = d.get("items", [])
    if symbol:
        key = symbol.split(":")[-1].split("-")[0].upper()
        names = {key, {"BTC": "BITCOIN", "ETH": "ETHER", "SOL": "SOLANA", "DOGE": "DOGECOIN"}.get(key, key)}
        rows = [x for x in rows if any(n in x["title"].upper() for n in names if n)] or []
    return {"fetched": d.get("time"), "items": rows[:limit], "errors": d.get("errors", {}), "feeds": feeds(storage),
            "sentiment": None, "note": "external, unverified headlines from feeds you configured; no bot reads them and "
                                       "no sentiment model is used"}
