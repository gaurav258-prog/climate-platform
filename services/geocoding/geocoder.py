"""Cache-aware, provider-swappable geocoding front door.

Two production concerns the raw Nominatim call doesn't handle:
  1. **Rate/scale** — the public Nominatim instance rate-limits hard, so bulk supplier uploads throttle.
     We persist every resolved query in `geocode_cache` (keyed on provider + normalized query + limit),
     so a repeated or re-uploaded address is served from Postgres, not the provider.
  2. **Provider swap** — `GEOCODER_PROVIDER` selects the backend. Only `nominatim` is implemented today,
     but the seam lets a paid provider (Google/HERE/Mapbox) drop in without touching any call site.

The per-candidate confidence / precision / low_confidence flags come from the provider layer, so the
UI can ask the user to confirm a coarse hit rather than silently scoring a bad point.
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings
from services.geocoding import nominatim

_PROVIDERS = {"nominatim": nominatim.geocode_candidates}


def _provider_fn():
    fn = _PROVIDERS.get(settings.GEOCODER_PROVIDER)
    if fn is None:                     # unknown config → fail safe to the implemented default
        return nominatim.geocode_candidates
    return fn


def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def candidates(session: Session, query: str, limit: int = 5) -> dict:
    """Ranked candidates for `query`, cache-first. Returns {results, provider, cached}."""
    provider = settings.GEOCODER_PROVIDER
    qn = _norm(query)
    row = session.execute(text("""
        SELECT results FROM geocode_cache
        WHERE provider = :p AND query_norm = :q AND limit_n = :l
    """), {"p": provider, "q": qn, "l": limit}).mappings().first()
    if row:
        session.execute(text("""
            UPDATE geocode_cache SET hit_count = hit_count + 1, last_used_at = now()
            WHERE provider = :p AND query_norm = :q AND limit_n = :l
        """), {"p": provider, "q": qn, "l": limit})
        session.commit()
        return {"results": row["results"], "provider": provider, "cached": True}

    results = _provider_fn()(query, limit=limit)
    # cache even an empty result — a miss is a fact worth not re-asking the provider for
    session.execute(text("""
        INSERT INTO geocode_cache (provider, query_norm, limit_n, results)
        VALUES (:p, :q, :l, CAST(:r AS jsonb))
        ON CONFLICT (provider, query_norm, limit_n) DO UPDATE SET results = EXCLUDED.results, last_used_at = now()
    """), {"p": provider, "q": qn, "l": limit, "r": _json(results)})
    session.commit()
    return {"results": results, "provider": provider, "cached": False}


def best(session: Session, query: str) -> dict | None:
    """Single best candidate (cache-aware), or None."""
    hits = candidates(session, query, limit=1)["results"]
    return hits[0] if hits else None


def _json(obj) -> str:
    import json
    return json.dumps(obj, default=str)
