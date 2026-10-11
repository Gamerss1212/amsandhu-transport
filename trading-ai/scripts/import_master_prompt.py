"""Import the owner's strategy registry from docs/specs/AI_Trading_System_Master_Prompt.md into the app's data files:

    backend/tradingai/strategies/data/catalog_st.json     every ST card (text, evidence labels, sources)
    backend/tradingai/strategies/data/sources.json        the source register (S01...)
    backend/tradingai/strategies/data/research_index.json the published equity-signal index (RP001...)

The text is copied as written in the specification; nothing is summarised or scored here.

    python scripts/import_master_prompt.py [path to the master prompt]
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "backend" / "tradingai" / "strategies" / "data"
CARD = re.compile(r"^(ST\d{3}) — (.+?)\. (Evidence .*)$")
GROUP = re.compile(r"^([A-M])\. ([A-Z][A-Z ,\-]+)$")
SOURCE = re.compile(r"^\| (S\d{2,3}) \| \[(.+?)\]\((\S+?)\) \| (.+?) \|\s*$")
INDEX = re.compile(r"^\| (RP\d{3}) \| `([^`]+)` \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \|\s*$")


def _evidence(text: str) -> tuple[str, list[str], str, list[str]]:
    sentence = re.match(r"(Evidence .*?)(?:\.\s+(?=[A-Z])|\.?$)", text).group(1)
    first = re.match(r"Evidence ([RCH])", sentence).group(1)
    labels = sorted(set(re.findall(r"(?:Evidence |, |; |and )([RCH])\b(?= for|\s*\[|\.|,|$)", sentence)) | {first},
                    key="CHR".index)            # alphabetical, as the earlier import stored them
    refs = []
    for group in re.findall(r"\[([^\]]+)\]", sentence):
        for part in group.split(","):
            part = part.strip()
            m = re.match(r"S(\d+)[–-]S(\d+)$", part)
            if m:
                refs += [f"S{n:02d}" for n in range(int(m.group(1)), int(m.group(2)) + 1)]
            elif re.match(r"S\d+$", part):
                refs.append(part)
    return first, labels, sentence.rstrip("."), refs


def parse(path: Path) -> tuple[dict, dict, list]:
    groups, cards, sources, index = {}, [], {}, []
    group = None
    for line in path.read_text(encoding="utf-8").splitlines():
        g = GROUP.match(line.strip())
        if g:
            group = g.group(1)
            groups[group] = g.group(2).title()
        m = CARD.match(line.strip())
        if m:
            cid, name, rest = m.groups()
            first, labels, ev_text, refs = _evidence(rest)
            markets = re.search(r"Markets: ([^;.]+(?:\.[0-9][^;.]*)?)[;.]", rest)
            scope = re.search(r"(?:; |\. )(?:[Ii]nitial )?[Ss]cope: ([^.]+)\.", rest)
            cards.append({"id": cid, "name": name, "group": group, "evidence": first, "evidence_labels": labels,
                          "evidence_text": ev_text, "sources": refs,
                          "markets_text": markets.group(1).strip() if markets else None,
                          "scope_text": scope.group(1).strip() if scope else None, "card": rest})
            continue
        s = SOURCE.match(line)
        if s:
            code, title, url, scope = s.groups()
            sources[code] = {"code": code, "title": title, "url": url, "access": scope.split(";")[0].strip(),
                             "scope": scope.strip()}
            continue
        r = INDEX.match(line)
        if r:
            rid, key, category, authors, relation = (x.strip() for x in r.groups())
            index.append({"id": rid, "key": key, "category": category, "authors": authors, "relation": relation,
                          "cards": re.findall(r"ST\d{3}", relation)})
    return {"groups": groups, "cards": cards}, sources, index


def main(path: str) -> None:
    cat, sources, index = parse(Path(path))
    ids = [c["id"] for c in cat["cards"]]
    assert ids == [f"ST{n:03d}" for n in range(1, len(ids) + 1)], "card ids are not a gapless sequence"
    assert len({r["id"] for r in index}) == len(index)
    missing = sorted({s for c in cat["cards"] for s in c["sources"]} - set(sources))
    assert not missing, f"cards cite sources missing from the register: {missing}"
    (OUT / "catalog_st.json").write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "sources.json").write_text(json.dumps(sources, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "research_index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(cat['cards'])} cards in {len(cat['groups'])} groups, {len(sources)} sources, {len(index)} index entries")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "docs" / "specs" / "AI_Trading_System_Master_Prompt.md"))
