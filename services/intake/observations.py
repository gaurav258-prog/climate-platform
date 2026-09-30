"""Every fact about an asset, per source, with its history (intake phase 3).

The live asset row holds ONE value per fact — the resolved one the engine reads. This module keeps, beside it, what
each source stated and when (asset_observations, append-only):

  client    what the organisation told us — a file (method intake_batch, origin batch:<id>), an edit (manual_edit), an
            entry (manual_entry), or, for a fact already on the book before observations were recorded, the book itself
            (method book). A blank is never a statement: it never clears a fact (the intake rule).
  tellumen  a value we derive ourselves, independent of what the client typed — registered in DERIVERS. Today: the
            country under the asset's coordinates (GISCO land layer, ISO 3166 through the country reference). We have
            no independent value, construction type or year built for a client's asset; those facts are the client's.

sync() is the one routine every path calls (intake landing, location edits, the scheduled sweep): it records what is
new — any live value no source has stated yet becomes a client statement, so a fact changed by any path is caught —
derives our values, and hands both to reconciliation (conflicts.reconcile). Hazard science is never a fact here: a
client value can never change a score.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import Callable, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

# ───────────────────────────── the books whose facts are observed ─────────────────────────────

@dataclass(frozen=True)
class Book:
    key: str
    table: str
    id_column: str
    name_column: str
    fields: tuple[str, ...]                               # the facts a client states about an asset
    load: Callable[[Session, str], list[dict]]            # every asset of the org: {"entity_id", <fields>…}


_NOT_FACTS = {"external_ref", "h3_cell"}                  # identifiers / derived keys, not facts about the asset


@lru_cache(maxsize=1)
def books() -> tuple[Book, ...]:
    """Every intake sector's book: its compare fields are exactly the facts a file may state (own operational sites are
    the company_sites sector)."""
    from services.ingest.sector_ingest import SECTORS
    name_col = {"portfolio_entities": "entity_name", "sc_company_sites": "name"}
    return tuple(Book(s.key, s.table, s.id_column, name_col.get(s.table, s.name_field),
                      tuple(f for f in s.compare if f not in _NOT_FACTS), s.existing) for s in SECTORS.values()
                 if not s.history)                     # a year-end value is its own append-only history, not an asset fact


def book_for(table: str) -> list[Book]:
    return [b for b in books() if b.table == table]


# ───────────────────────────── values ─────────────────────────────

def norm(v):
    """A value as it is stored and compared: numbers as float, dates ISO, text trimmed; blank → None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, Decimal)):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10] if isinstance(v, date) and not isinstance(v, datetime) else v.isoformat()
    s = str(v).strip()
    return s or None


def same(a, b) -> bool:
    a, b = norm(a), norm(b)
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= max(1e-9, 1e-9 * max(abs(a), abs(b)))
    return a == b


# ───────────────────────────── what Tellumen derives itself ─────────────────────────────

@dataclass(frozen=True)
class Deriver:
    field: str
    method: str
    origin: str
    derive: Callable[[Session, dict], Optional[object]]
    differs: Callable[[object, object], Optional[str]]     # (client, ours) → why they are a conflict, or None


@lru_cache(maxsize=1)
def _iso2_by_iso3() -> dict[str, str]:
    from core.db.config import SessionLocal
    s = SessionLocal()
    try:
        return {r[0]: r[1] for r in s.execute(text("SELECT iso3, iso2 FROM ref_countries WHERE iso3 IS NOT NULL")).all()}
    finally:
        s.close()


def _country_from_location(session: Session, row: dict) -> Optional[str]:
    lat, lon = row.get("latitude"), row.get("longitude")
    if lat is None or lon is None:
        return None
    from services.geo.cells import iso3_of
    iso3 = iso3_of(float(lat), float(lon))
    return _iso2_by_iso3().get(iso3) if iso3 else None


@lru_cache(maxsize=1)
def _country_names() -> dict[str, str]:
    """Every accepted written form of a country → ISO alpha-2 (the country reference, services/reference/countries)."""
    from core.db.config import SessionLocal
    from services.reference.countries import lookup
    from services.reference.iso_country import ISO_ALPHA2
    s = SessionLocal()
    try:
        return {**{c.lower(): c for c in ISO_ALPHA2}, **lookup(s)}
    finally:
        s.close()


@lru_cache(maxsize=1)
def _drawn() -> frozenset[str]:
    """The countries the land layer draws as their own shapes (ISO alpha-2). The layer can only disagree about these:
    GISCO's world file draws no separate Taiwan, so a point there says nothing against a book that says TW."""
    from services.geo.cells import _iso3_by_code
    iso = _iso2_by_iso3()
    return frozenset(iso[c] for c in _iso3_by_code().values() if c in iso)


def _country_differs(client, ours) -> Optional[str]:
    if client is None or ours is None:
        return None
    from services.ingest.fields import norm_token
    written = str(client).strip()
    iso = _country_names().get(norm_token(written)) or _country_names().get(written.lower())
    if iso is None:
        return f"the book's country '{written}' is not a recognised country code; the coordinates are in {ours}"
    if iso == ours or iso not in _drawn():
        return None
    return f"the coordinates are in {ours}; the book says {iso}"


DERIVERS: tuple[Deriver, ...] = (
    Deriver("country", "land_layer", "GISCO countries 2020 (1:3M) → ISO 3166 (ref_countries)",
            _country_from_location, _country_differs),
)


def deriver_for(field: str) -> Optional[Deriver]:
    return next((d for d in DERIVERS if d.field == field), None)


# ───────────────────────────── recording + reading ─────────────────────────────

def record(session: Session, rows: list[dict]) -> None:
    """rows: {org_id, asset_table, asset_id, field, value, source, method, origin?, as_of?}. Append-only."""
    if not rows:
        return
    session.execute(text("""
        INSERT INTO asset_observations (org_id, asset_table, asset_id, field, value, source, method, origin, as_of)
        VALUES (CAST(:org_id AS uuid), :asset_table, CAST(:asset_id AS uuid), :field, CAST(:value AS jsonb), :source,
                :method, :origin, CAST(:as_of AS date))
    """), [{**r, "value": json.dumps(norm(r.get("value"))), "origin": r.get("origin"), "as_of": r.get("as_of")} for r in rows])


def latest(session: Session, org_id: str, table: str, asset_ids: Optional[Iterable[str]] = None) -> dict[tuple, dict]:
    """(asset_id, field, source) → the latest statement {observation_id, value, method, origin, observed_at}."""
    ids = list(asset_ids) if asset_ids is not None else None
    rows = session.execute(text("""
        SELECT DISTINCT ON (asset_id, field, source) observation_id, asset_id::text AS asset_id, field, source, value,
               method, origin, observed_at
        FROM asset_observations
        WHERE org_id = CAST(:o AS uuid) AND asset_table = :t AND (CAST(:ids AS uuid[]) IS NULL OR asset_id = ANY(CAST(:ids AS uuid[])))
        ORDER BY asset_id, field, source, observation_id DESC
    """), {"o": org_id, "t": table, "ids": ids}).mappings().all()
    return {(r["asset_id"], r["field"], r["source"]): dict(r) for r in rows}


def history(session: Session, org_id: str, table: str, asset_id: str) -> list[dict]:
    rows = session.execute(text("""
        SELECT observation_id, field, source, value, method, origin, as_of, observed_at FROM asset_observations
        WHERE org_id = CAST(:o AS uuid) AND asset_table = :t AND asset_id = CAST(:a AS uuid)
        ORDER BY field, observation_id DESC
    """), {"o": org_id, "t": table, "a": asset_id}).mappings().all()
    return [{**dict(r), "observed_at": r["observed_at"].isoformat(), "as_of": r["as_of"].isoformat() if r["as_of"] else None}
            for r in rows]


def _taken_from_us(session: Session, table: str, ids: list[str]) -> set[tuple[str, str]]:
    """(asset, field) whose live value is ours by an approved decision — that value is not a new client statement."""
    rows = session.execute(text("""
        SELECT DISTINCT ON (asset_id, field) asset_id::text, field, resolution FROM asset_conflicts
        WHERE asset_table = :t AND asset_id = ANY(CAST(:ids AS uuid[])) AND status = 'resolved'
        ORDER BY asset_id, field, resolved_seq DESC          -- not resolved_at: one transaction shares now() (E52)
    """), {"t": table, "ids": ids}).all()
    return {(r[0], r[1]) for r in rows if r[2] == "tellumen"}


# ───────────────────────────── the one routine ─────────────────────────────

def sync(session: Session, org_id: str, *, asset_ids: Optional[Iterable[str]] = None, tables: Optional[Iterable[str]] = None,
         method: str = "book", origin: Optional[str] = None, as_of: Optional[str] = None) -> dict:
    """Record what is new about these assets (all of the org's, when asset_ids is None), derive our values, reconcile.
    A live value no source has stated yet is recorded as the client's, with `method` / `origin` saying how it came."""
    from services.intake import conflicts
    wanted = set(asset_ids) if asset_ids is not None else None
    counts = {"client": 0, "tellumen": 0, "opened": 0, "agreed": 0}
    for book in books():
        if tables is not None and book.table not in set(tables):
            continue
        rows = [r for r in book.load(session, org_id) if wanted is None or r["entity_id"] in wanted]
        if not rows:
            continue
        ids = [r["entity_id"] for r in rows]
        seen = latest(session, org_id, book.table, ids)
        ours_live = _taken_from_us(session, book.table, ids)
        new: list[dict] = []
        for r in rows:
            aid = r["entity_id"]
            base = {"org_id": org_id, "asset_table": book.table, "asset_id": aid}
            for f in book.fields:
                v = norm(r.get(f))
                if v is None:
                    continue
                prev = seen.get((aid, f, "client"))
                if prev is not None and same(prev["value"], v):
                    continue
                t = seen.get((aid, f, "tellumen"))
                if (aid, f) in ours_live and t is not None and same(t["value"], v):
                    continue
                new.append({**base, "field": f, "value": v, "source": "client", "method": method, "origin": origin, "as_of": as_of})
                counts["client"] += 1
            for d in DERIVERS:
                if d.field not in book.fields:
                    continue
                ours = norm(d.derive(session, r))
                prev = seen.get((aid, d.field, "tellumen"))
                if (prev is None and ours is None) or (prev is not None and same(prev["value"], ours)):
                    continue
                new.append({**base, "field": d.field, "value": ours, "source": "tellumen", "method": d.method,
                            "origin": d.origin, "as_of": date.today().isoformat()})
                counts["tellumen"] += 1
        record(session, new)
        c = conflicts.reconcile(session, org_id, book.table, ids)
        counts["opened"] += c["opened"]
        counts["agreed"] += c["agreed"]
    return counts


def sync_all(session: Session) -> dict:
    """The scheduled sweep: every organisation's books (catches facts written by any path)."""
    orgs = [r[0] for r in session.execute(text("SELECT org_id::text FROM organizations")).all()]
    out = {}
    for o in orgs:
        c = sync(session, o)
        if any(c.values()):
            out[o] = c
    session.commit()
    return out
