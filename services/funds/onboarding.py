"""Holdings into a fund — the one onboarding every door uses (moved from api/routers/funds.py, 2026-10-23): the API's
POST /v1/funds/{id}/holdings and the asset manager's standard file (its Fund holdings sheet, services/ingest/fund_books.py).

For each holding: (1) the ISIN resolved to an issuer and security from open data (GLEIF); (2) the issuer's head office
located and scored if it has no site yet; (3) the position recorded, value-weighted. The answer is a coverage report:
what matched, what did not, and which inputs remain gaps (sector, sites, emissions) — never a fabricated fill.

Scale: locating a new issuer runs inline — right for tens of holdings, not thousands (that path should queue).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.errors import UserError
from services import fund_messages as W
from services.funds.holding import Holding, HoldingsUpload, apply_enrichment
from services.reference import gleif
from services.reference.footprint import seed_hq_footprint
from services.reference.fx import FxError, to_eur
from services.reference.resolver import _ASSET_CLASSES, resolve_isin


def onboard(session: Session, org_id: str, fund_id: str, body: HoldingsUpload, actor_id: Optional[str] = None) -> dict:
    """Onboard `body.holdings` into the fund (already known to be the organisation's own)."""
    if not body.holdings:
        raise UserError("disclose.fund.refused.no_holdings")

    as_of = body.as_of_date or date.today()

    # ── FX: normalize every line to EUR at the book's as-of date ───────────
    # A holding may arrive already in EUR (market_value_eur) or in a native
    # currency (market_value + currency). We convert the native ones and keep
    # the original amount + currency for audit. An unknown currency is a hard,
    # surfaced error — EUR is never silently assumed for a non-EUR line.
    # Aggregate repeated ISINs (a book can list the same security as several lots):
    # SUM their EUR value rather than dropping later lots. Enrichment fields keep
    # the first non-null seen; native base only survives if all lots share a ccy.
    by_isin: dict[str, Holding] = {}
    native: dict[str, dict] = {}     # isin -> {base, ccy, mixed}
    fx_applied: dict[str, dict] = {}  # ccy -> {rate, rate_date, source}
    fx_errors: list[str] = []
    for h in body.holdings:
        key = (h.isin or "").strip().upper()
        raw_ccy = (h.currency or "").strip().upper()
        if h.market_value_eur is not None:
            # EUR value supplied directly — no FX guess needed; currency only labels the native base.
            eur = h.market_value_eur
            ccy = raw_ccy or "EUR"
            base = h.market_value if h.market_value is not None else (eur if ccy == "EUR" else None)
        else:
            # Native value → must convert. A blank currency is NOT assumed to be EUR (audit T9):
            # surface it so the uploader supplies a currency or a market_value_eur.
            if not raw_ccy:
                fx_errors.append(f"{key or 'line'}: market value given without a currency — cannot "
                                 "convert to EUR (specify a currency or provide market_value_eur)")
                continue
            ccy = raw_ccy
            try:
                conv = to_eur(session, h.market_value, ccy, as_of)
            except FxError as e:
                fx_errors.append(str(e))
                continue
            eur = conv["eur"]
            base = h.market_value
            if ccy != "EUR":
                fx_applied[ccy] = {k: conv[k] for k in ("rate", "rate_date", "source", "basis", "age_days", "stale", "note")}
        if key in by_isin:
            by_isin[key].market_value_eur += eur
            n = native[key]
            if n["ccy"] == ccy and n["base"] is not None and base is not None:
                n["base"] += base
            else:
                n["mixed"] = True
        else:
            by_isin[key] = h.model_copy(update={"market_value_eur": eur})
            native[key] = {"base": base, "ccy": ccy, "mixed": False}

    total_value = sum(h.market_value_eur for h in by_isin.values()) or 1.0

    resolutions, positions_created, footprints = [], 0, {"seeded": 0, "failed": 0, "already": 0}
    positioned: set[str] = set()
    enriched = {"sector": 0, "emissions": 0, "estimated": 0, "esg": 0, "voluntary": 0}
    voluntary_rejected: list[dict] = []
    for isin, h in by_isin.items():
        res = resolve_isin(session, isin, org_id=org_id, asset_class=h.asset_class or "equity", currency=h.currency)
        resolutions.append(res.to_dict())
        if res.status not in ("resolved", "cached") or not res.security_id:
            continue  # unmatched / errored ISINs are reported, never positioned

        # An explicit asset-class hint (e.g. corporate_bond, sovereign_bond) must
        # relabel an already-cached security — the resolver's cache fast-path skips
        # the upsert, so a bond first seen as the default 'equity' would stay wrong.
        if h.asset_class and h.asset_class in _ASSET_CLASSES:
            session.execute(text("UPDATE securities SET asset_class = :ac WHERE security_id = :s"),
                            {"ac": h.asset_class, "s": res.security_id})

        # Store any issuer data the client supplied on this holding.
        wrote = apply_enrichment(session, res.issuer_id, org_id, h)
        if wrote["sector"]:
            enriched["sector"] += 1
        if wrote["emissions"]:
            enriched["emissions"] += 1
        if wrote["estimated"]:
            enriched["estimated"] += 1
        if wrote["esg"]:
            enriched["esg"] += 1
        if wrote["voluntary"]:
            enriched["voluntary"] += 1
        voluntary_rejected += [{"isin": h.isin, **x} for x in wrote.get("voluntary_rejected", [])]

        # Seed the issuer's footprint if it has none yet, so physical risk is
        # computable. Keyed on "has no facility" (NOT on resolved-vs-cached): an
        # issuer resolved in a prior session but never located would otherwise
        # never get a footprint on re-upload.
        has_fac = session.execute(
            text("SELECT 1 FROM issuer_facilities WHERE issuer_id = :i LIMIT 1"),
            {"i": res.issuer_id}).first()
        if has_fac:
            footprints["already"] += 1
        elif res.lei:
            rec = gleif.fetch_lei(res.lei)
            seeded = seed_hq_footprint(session, res.issuer_id, rec) if rec else None
            footprints["seeded" if seeded else "failed"] += 1
        else:
            footprints["failed"] += 1  # matched security but no LEI to locate from — surfaced

        weight = h.weight_pct if h.weight_pct is not None else round(100.0 * h.market_value_eur / total_value, 6)
        n = native[isin]
        pos_ccy = "EUR" if n["mixed"] else n["ccy"]
        pos_base = None if n["mixed"] else n["base"]
        session.execute(text("""
            INSERT INTO fund_positions (fund_id, security_id, market_value_eur, market_value_native, currency, weight_pct, as_of_date)
            VALUES (:f, :s, :mv, :mvb, :ccy, :w, :d)
            ON CONFLICT (fund_id, security_id, as_of_date)
            DO UPDATE SET market_value_eur = EXCLUDED.market_value_eur,
                          market_value_native = EXCLUDED.market_value_native,
                          currency = EXCLUDED.currency, weight_pct = EXCLUDED.weight_pct
        """), {"f": fund_id, "s": res.security_id, "mv": h.market_value_eur,
               "mvb": pos_base, "ccy": pos_ccy, "w": weight, "d": as_of})
        positions_created += 1
        positioned.add(str(res.security_id))

    removed: list[dict] = []
    if body.complete_book:
        failed = [r["isin"] for r in resolutions if r["status"] not in ("resolved", "cached")] + fx_errors
        if failed or len(positioned) != len(by_isin):
            raise UserError("disclose.fund.refused.incomplete_book", n=len(failed) or 1,
                            items=", ".join(r["isin"] for r in resolutions if r["status"] not in ("resolved", "cached"))
                            or "—")
        removed = [dict(r) for r in session.execute(text("""
            DELETE FROM fund_positions p USING securities s
            WHERE p.fund_id = :f AND p.as_of_date = :d AND s.security_id = p.security_id
              AND NOT (p.security_id::text = ANY(:keep))
            RETURNING s.isin, s.name, CAST(p.market_value_eur AS FLOAT) AS market_value_eur"""),
            {"f": fund_id, "d": as_of, "keep": sorted(positioned)}).mappings()]
        if removed:
            from api.services.rbac import write_audit
            write_audit(session, org_id=org_id, actor_user_id=actor_id, action="fund.positions_removed",
                        target_type="fund", target_id=fund_id,
                        detail={"as_of_date": as_of.isoformat(), "reason": "not in the complete book uploaded",
                                "positions": removed})

    matched = sum(1 for r in resolutions if r["status"] in ("resolved", "cached"))
    # a held ISIN that is one of this manager's OWN share classes is a fund held by a fund: say which, so it can be
    # looked through (POST /funds/{id}/look-through) rather than treated as one opaque security
    from services.eet.share_classes import resolve_isin as own_share_class
    own_classes = [{"isin": i, **sc} for i in by_isin if (sc := own_share_class(session, org_id, i))]
    sector_gaps = [r["isin"] for r in resolutions if r["status"] in ("resolved", "cached") and not r["sector_known"]]
    out = {
        "fund_id": fund_id, "as_of_date": as_of.isoformat(),
        "holdings_submitted": len(body.holdings), "distinct_isins": len(by_isin),
        "positions_created": positions_created,
        "positions_removed": removed,                 # complete_book: positions on the date not in the file (sold)
        "voluntary_rejected": voluntary_rejected,   # indicator values refused (unknown indicator / wrong kind of value)
        "coverage": {
            "matched": matched,
            "match_rate_pct": round(100.0 * matched / len(by_isin), 1) if by_isin else 0.0,
            "unmatched": [r["isin"] for r in resolutions if r["status"] == "unmatched"],
            "errored": [r["isin"] for r in resolutions if r["status"] == "error"],
            "footprints": footprints,
            "sector_gap_isins": sector_gaps,   # matched but NACE unknown → needed for EU Taxonomy
            "client_enriched": enriched,        # issuer data the client supplied on this upload
            "own_share_classes": own_classes,   # held ISINs that are your own funds' share classes → look through
        },
        "fx": {
            "converted_currencies": fx_applied,  # ccy -> {rate (EUR per unit), rate_date, source}
            "errors": fx_errors,                 # lines dropped for an unknown currency (surfaced, never guessed)
        },
        "resolutions": resolutions,
        "note": "Physical risk is now computable for located issuers. Sector/NACE, "
                "multi-facility footprints and issuer emissions are the remaining "
                "enrichment inputs — supply them per holding (optional columns) to "
                "fill the SFDR statement; surfaced, never fabricated.",
    }
    out["messages"] = W.onboarding(out)         # the outcome in customer words (services.fund_messages)
    return out
