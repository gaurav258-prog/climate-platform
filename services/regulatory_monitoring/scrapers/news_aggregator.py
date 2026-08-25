"""
News feed aggregator — regulatory-climate news as an EARLY signal.

The official-document scrapers (EUR-Lex / SEC / FCA) detect a rule once it is published. News breaks earlier —
a consultation opened, a delegated act agreed, an EBA/ESMA statement — so this feed is the leading indicator
that a change is coming, feeding the same change-detection → diff → snapshot pipeline as the doc scrapers
(it returns documents in the identical shape).

SOURCE — **GDELT DOC 2.0** (https://api.gdeltproject.org/api/v2/doc/doc): a free, global news index, **no API
key required**. Optional upgrade: set NEWS_API_KEY to use NewsAPI.org instead (richer metadata, needs a key);
premium wires (Reuters/Bloomberg) need a commercial licence and are not wired here. With no source reachable
this returns [] — honest: no fabricated news.

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWSAPI_URL = "https://newsapi.org/v2/everything"

# GDELT asks for ≤ 1 request / 5 s. Enforce it process-wide so the per-framework loop can't trip the limit.
_GDELT_MIN_INTERVAL_S = 5.5
_gdelt_last_call = 0.0


def _gdelt_throttle() -> None:
    global _gdelt_last_call
    wait = _GDELT_MIN_INTERVAL_S - (time.monotonic() - _gdelt_last_call)
    if wait > 0:
        time.sleep(wait)
    _gdelt_last_call = time.monotonic()

# Broad climate-regulatory query (GDELT syntax: quoted phrases, OR/AND). Scoped to regulatory signal so it is
# a leading indicator on rule-making, not general climate news.
_DEFAULT_QUERY = ('(CSRD OR SFDR OR "EU taxonomy" OR "Pillar 3" OR EUDR OR "climate disclosure" OR '
                  '"sustainability reporting") (regulation OR directive OR EBA OR ESMA OR EFRAG OR SEC)')


class NewsAggregator:
    """Aggregate regulatory-climate news from a free news index (GDELT), or NewsAPI when a key is configured."""

    def __init__(self, query: Optional[str] = None):
        self.query = query or _DEFAULT_QUERY

    def get_climate_news(self, hours: int = 48, query: Optional[str] = None) -> List[dict]:
        """Recent regulatory-climate news as document-shaped dicts (title/url/published_date/content/source),
        newest first — the shape the change-detector's diff pipeline consumes."""
        q = query or self.query
        if settings.NEWS_API_KEY:
            items = self._newsapi(q, hours)
            if items:
                return items
            logger.info("[news] NEWS_API_KEY set but returned nothing — falling back to GDELT")
        return self._gdelt(q, hours)

    # ── GDELT DOC 2.0 (free, no key) ───────────────────────────────────────────────────────────────────────
    def _gdelt(self, query: str, hours: int) -> List[dict]:
        params = {"query": query, "mode": "ArtList", "format": "json",
                  "timespan": f"{max(1, hours)}h", "sort": "DateDesc", "maxrecords": 25}
        headers = {"User-Agent": "Mozilla/5.0 tellumen-regmonitor"}
        articles: list = []
        for attempt in range(2):   # one throttled retry on the 1-req/5s rate limit
            _gdelt_throttle()
            try:
                resp = httpx.get(GDELT_DOC_URL, params=params, headers=headers, timeout=30)
            except Exception as exc:
                logger.warning(f"[news] GDELT fetch failed: {exc}")
                return []
            body = resp.text.strip()
            if resp.status_code == 429 or body.startswith("Please limit"):
                logger.info("[news] GDELT rate-limited (1 req/5s); backing off%s", " and retrying" if attempt == 0 else " — no news this run")
                continue
            articles = resp.json().get("articles", []) if body.startswith("{") else []
            break
        out = []
        for a in articles:
            seen = a.get("seendate")   # e.g. 20260824T120000Z
            iso = seen
            try:
                if seen:
                    iso = datetime.strptime(seen, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
            out.append({
                "title": a.get("title") or "", "url": a.get("url") or "",
                "published_date": iso or "", "document_type": "news",
                # GDELT ArtList carries no body; the title + domain is the signal we diff on
                "content": f"{a.get('title') or ''} — {a.get('domain') or ''} ({a.get('sourcecountry') or ''})",
                "source": "GDELT News", "scrape_time": datetime.now(timezone.utc).isoformat(),
            })
        logger.info(f"[news] GDELT returned {len(out)} regulatory-climate articles (last {hours}h)")
        return out

    # ── NewsAPI.org (optional, needs NEWS_API_KEY) ─────────────────────────────────────────────────────────
    def _newsapi(self, query: str, hours: int) -> List[dict]:
        try:
            resp = httpx.get(NEWSAPI_URL, params={
                "q": query, "sortBy": "publishedAt", "language": "en", "pageSize": 25,
            }, headers={"X-Api-Key": settings.NEWS_API_KEY}, timeout=30)
            resp.raise_for_status()
            articles = resp.json().get("articles", [])
        except Exception as exc:
            logger.warning(f"[news] NewsAPI fetch failed: {exc}")
            return []
        return [{
            "title": a.get("title") or "", "url": a.get("url") or "",
            "published_date": a.get("publishedAt") or "", "document_type": "news",
            "content": (a.get("description") or a.get("title") or ""),
            "source": f"NewsAPI · {(a.get('source') or {}).get('name') or ''}".strip(" ·"),
            "scrape_time": datetime.now(timezone.utc).isoformat(),
        } for a in articles]
