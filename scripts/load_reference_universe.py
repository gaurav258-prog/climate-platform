"""Pre-load the common EU-listed universe into the reference layer.

Why this exists (plain English): our promise to an asset manager is "just give
us the ISINs and it works". That only feels magical if the important data is
ALREADY there when they upload. So before any customer arrives, we walk a list
of the companies these funds commonly hold and, for each one, look up who it is
(GLEIF), find its head office on the map, and score the climate danger there.

After this runs, a customer who uploads those same ISINs gets an instant answer
from our own store — no live lookup, no waiting.

What it does NOT do (honest): it places ONE head-office point per company (our
current footprint proxy), not every factory; and it fills identity + location +
physical risk only — sector, revenue and emissions stay as disclosed gaps for
the customer to supply. Those are deliberate, surfaced elsewhere.

Idempotent & resumable: a company already resolved AND located is skipped, so
you can re-run this safely or top it up with more names.

Usage:
    python -m scripts.load_reference_universe                       # default CSV
    python -m scripts.load_reference_universe --csv path.csv --limit 10
"""
from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path

from sqlalchemy import text

from core.db.session import get_session
from services.reference import gleif
from services.reference.footprint import seed_hq_footprint
from services.reference.resolver import resolve_isin, link_isin_to_record

logging.basicConfig(level=logging.WARNING, format="%(message)s")
log = logging.getLogger("universe")
log.setLevel(logging.INFO)

DEFAULT_CSV = Path(__file__).resolve().parent.parent / "data" / "universe" / "eu_common_equities.csv"


def _already_loaded(session, isin: str) -> bool:
    """True if this ISIN already resolves AND its issuer has at least one facility."""
    row = session.execute(
        text(
            """
            SELECT (SELECT count(*) FROM issuer_facilities f WHERE f.issuer_id = s.issuer_id) AS n_fac
            FROM securities s WHERE s.isin = :isin
            """
        ),
        {"isin": isin},
    ).first()
    return bool(row and row[0] and row[0] > 0)


def load_universe(csv_path: Path, limit: int | None = None) -> dict:
    with open(csv_path, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if (r.get("isin") or "").strip()]
    if limit:
        rows = rows[:limit]

    total = len(rows)
    counts = {"loaded": 0, "skipped": 0, "unmatched": 0, "error": 0, "located": 0, "no_location": 0}
    log.info("Loading %d companies from %s", total, csv_path.name)

    for i, row in enumerate(rows, 1):
        isin = row["isin"].strip().upper()
        name = (row.get("name") or "").strip()

        with get_session() as s:
            if _already_loaded(s, isin):
                counts["skipped"] += 1
                log.info("[%d/%d] %-42s already loaded — skip", i, total, name[:42])
                continue

            res = resolve_isin(s, isin)
            if res.status == "unmatched":
                # GLEIF's ISIN→LEI file may simply not cover this instrument even
                # though the entity exists. Since we curated the NAME, fall back to
                # a name lookup and, if found, record the ISIN→issuer link in our
                # own store (so future customer ISIN uploads cache-hit).
                try:
                    named = gleif.resolve_name(name) if name else None
                except Exception:
                    named = None
                if named:
                    res = link_isin_to_record(s, isin, named)
                    log.info("[%d/%d] %-42s ✓ %s — via name (ISIN gap in GLEIF)", i, total, name[:42], named.lei)
                else:
                    counts["unmatched"] += 1
                    log.info("[%d/%d] %-42s NO GLEIF match (%s) — surfaced, not guessed", i, total, name[:42], isin)
                    continue
            if res.status == "error":
                counts["error"] += 1
                log.info("[%d/%d] %-42s source error — retry later", i, total, name[:42])
                continue

            # resolved or cached → ensure it has a located footprint.
            # A transient GLEIF/geocoder failure here must NOT abort the whole
            # batch: mark this one for retry and move on (idempotent re-run picks
            # it up). The issuer is already resolved, so no data is lost.
            try:
                rec = gleif.fetch_lei(res.lei) if res.lei else None
                seeded = seed_hq_footprint(s, res.issuer_id, rec) if rec else None
            except Exception as exc:  # network blip / geocoder outage — retryable
                counts["error"] += 1
                log.info("[%d/%d] %-42s located later (transient: %s)", i, total, name[:42], str(exc)[:60])
                continue
            if seeded:
                counts["located"] += 1
                counts["loaded"] += 1
                log.info("[%d/%d] %-42s ✓ %s — located %s", i, total, name[:42], res.lei, seeded["h3_cell"])
            else:
                counts["no_location"] += 1
                counts["loaded"] += 1
                log.info("[%d/%d] %-42s resolved but HQ not geocodable — no footprint", i, total, name[:42])

    matched = counts["loaded"] + counts["skipped"]
    log.info("")
    log.info("── Done ──")
    log.info("Companies in list:        %d", total)
    log.info("Now in our store:         %d  (%.0f%%)", matched, 100.0 * matched / total if total else 0)
    log.info("  newly loaded this run:  %d", counts["loaded"])
    log.info("  already had:            %d", counts["skipped"])
    log.info("With a located HQ + score: %d newly located", counts["located"])
    log.info("Couldn't match in GLEIF:  %d  %s", counts["unmatched"], "(check the ISINs)" if counts["unmatched"] else "")
    log.info("Source errors (retry):    %d", counts["error"])
    return {"total": total, **counts}


def main() -> None:
    ap = argparse.ArgumentParser(description="Pre-load the common EU-listed universe into the reference layer.")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="CSV with name,isin columns")
    ap.add_argument("--limit", type=int, default=None, help="only load the first N rows")
    args = ap.parse_args()
    load_universe(args.csv, args.limit)


if __name__ == "__main__":
    main()
