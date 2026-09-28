"""CRCS early warning — what the regulators' own feeds and the press say before a change reaches the official register.

Sources and topics are reference data (data/reference/crcs/signal_sources.json): the EBA, ESMA, UK FCA and US SEC news
feeds (RSS, read with the standard-library XML parser — Expat 2.4+ refuses entity-expansion attacks and nothing
external is ever fetched from a feed; each download is capped) and the GDELT news index. An item is kept only when
its title or summary names a topic we track; the topic says which frameworks it concerns.

Every item is UNCONFIRMED. It never moves a date, a deadline or a filing. When the official register later records a
change for one of its frameworks (reg_detected_change, after the item was published), the item is marked
'register_confirmed' and linked to that change. A person can dismiss an item as irrelevant.

Who sees what: EU items reach every organisation filing an EU framework the item concerns; a UK or US item reaches an
organisation only when it or one of its entities is in that country (organisations.country / reporting_entities.country).
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

_FILE = Path(__file__).resolve().parents[2] / "data" / "reference" / "crcs" / "signal_sources.json"
_MAX_BYTES = 5_000_000
_UA = {"User-Agent": "Tellumen regulatory monitor (compliance early warning; contact: operations@tellumen.example)"}


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(_FILE.read_text())


@lru_cache(maxsize=1)
def _patterns() -> list[tuple[dict, re.Pattern]]:
    return [(t, re.compile(r"\b(" + "|".join(re.escape(w) for w in t["words"]) + r")\b", re.I)) for t in reference()["topics"]]


def classify(title: str, summary: str = "") -> tuple[list[str], list[str]]:
    """(topics, frameworks) an item concerns — by whole words in its title or summary."""
    hay = f"{title} {summary}"
    topics, fws = [], []
    for t, pat in _patterns():
        if pat.search(hay):
            topics.append(t["key"])
            fws += [f for f in t["frameworks"] if f not in fws]
    return topics, fws


def _clean(s: Optional[str]) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", s or "").split())


def _date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:   # the FCA writes 'Monday, September 28, 2026 - 14:29' — UK time
        from zoneinfo import ZoneInfo
        return datetime.strptime(s.strip(), "%A, %B %d, %Y - %H:%M").replace(tzinfo=ZoneInfo("Europe/London"))
    except ValueError:
        return None       # no date given (ESMA): first_seen_at stands in


def _rss(url: str) -> list[dict]:
    r = httpx.get(url, headers=_UA, timeout=30, follow_redirects=True)
    r.raise_for_status()
    if len(r.content) > _MAX_BYTES:
        raise ValueError(f"feed larger than {_MAX_BYTES} bytes")
    root = ET.fromstring(r.content)
    out = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        if link:
            out.append({"url": link, "title": _clean(it.findtext("title")), "summary": _clean(it.findtext("description"))[:600],
                        "published_at": _date(it.findtext("pubDate"))})
    return out


def _gdelt(src: dict) -> list[dict]:
    from services.regulatory_monitoring.scrapers.news_aggregator import NewsAggregator
    return [{"url": a["url"], "title": a["title"], "summary": a.get("content", ""), "published_at": _date(a.get("published_date"))}
            for a in NewsAggregator(src.get("query")).get_climate_news(hours=72) if a.get("url")]


def sweep(session: Session) -> dict:
    """Read every source; keep new items that concern a tracked topic; confirm those the register has since recorded."""
    added, errors = 0, []
    for src in reference()["sources"]:
        try:
            items = _rss(src["url"]) if src["kind"] == "rss" else _gdelt(src)
        except Exception as exc:  # noqa: BLE001 — a source that can't be read is skipped this run, never guessed
            errors.append(f"{src['key']}: {type(exc).__name__}")
            continue
        for it in items:
            topics, fws = classify(it["title"], it["summary"])
            if not topics:
                continue
            n = session.execute(text("""
                INSERT INTO reg_early_signal (source_key, jurisdiction, url, title, summary, published_at, topics, frameworks)
                VALUES (:s, :j, :u, :t, :m, :p, :tp, :fw) ON CONFLICT (url) DO NOTHING
            """), {"s": src["key"], "j": src["jurisdiction"], "u": it["url"][:2000], "t": it["title"][:500], "m": it["summary"],
                   "p": it["published_at"], "tp": topics, "fw": fws}).rowcount
            added += n
    confirmed = session.execute(text("""
        UPDATE reg_early_signal s SET status = 'register_confirmed', confirmed_by = d.change_id
        FROM reg_detected_change d
        WHERE s.status = 'unconfirmed' AND d.framework = ANY(s.frameworks) AND d.status <> 'dismissed'
          AND d.detected_at >= COALESCE(s.published_at, s.first_seen_at)
    """)).rowcount
    session.commit()
    return {"added": added, "confirmed": confirmed, "errors": errors}


def _jurisdictions(session: Session, org_id: str) -> set[str]:
    rows = session.execute(text("""
        SELECT country FROM organizations WHERE org_id = CAST(:o AS uuid)
        UNION SELECT country FROM reporting_entities WHERE org_id = CAST(:o AS uuid) AND country IS NOT NULL
    """), {"o": org_id}).all()
    return {"EU"} | {(r[0] or "").strip().upper() for r in rows if r[0]}


def for_org(session: Session, org_id: str, frameworks: list[str], limit: int = 30) -> dict:
    """The signals an organisation should see: its jurisdictions, and its frameworks (or general climate disclosure in a
    non-EU jurisdiction it operates in)."""
    js = _jurisdictions(session, org_id)
    rows = session.execute(text("""
        SELECT s.signal_id::text, s.source_key, s.jurisdiction, s.url, s.title, s.summary, s.published_at, s.topics, s.frameworks,
               s.status, d.title AS confirmed_title
        FROM reg_early_signal s LEFT JOIN reg_detected_change d ON d.change_id = s.confirmed_by
        WHERE s.status <> 'dismissed' AND s.jurisdiction = ANY(:j)
          AND (s.frameworks && CAST(:f AS text[]) OR (s.jurisdiction <> 'EU' AND 'climate_disclosure' = ANY(s.topics)))
        ORDER BY s.published_at DESC NULLS LAST LIMIT :n
    """), {"j": list(js), "f": frameworks, "n": limit}).mappings().all()
    names = {s["key"]: s["authority"] for s in reference()["sources"]}
    labels = {t["key"]: t["label"] for t in reference()["topics"]}
    return {"signals": [{**dict(r), "source": names.get(r["source_key"], r["source_key"]),
                         "topics": [labels.get(t, t) for t in r["topics"]],
                         "published_at": r["published_at"].isoformat() if r["published_at"] else None} for r in rows],
            "jurisdictions": sorted(js),
            "note": "Early signals are unconfirmed: they never move a date, a deadline or a filing. One the official EU register "
                    "later records is marked confirmed."}


def dismiss(session: Session, signal_id: str) -> None:
    session.execute(text("UPDATE reg_early_signal SET status = 'dismissed' WHERE signal_id = CAST(:s AS uuid)"), {"s": signal_id})
