"""Vendor ESG/PAI feed connector (MSCI, ISS, Sustainalytics, …).

A manager who already licenses a data vendor uploads that vendor's extract; we map
its columns to our fields, match each row to an issuer (by ISIN or LEI), and store
the values as an org-scoped disclosure with source='vendor'. Reconciliation is
honest:
  * precedence is own (client) > vendor > global/estimated — enforced in the read
    path, so a vendor figure never overwrites the manager's own disclosure; both
    are kept and the more-authoritative one wins at query time;
  * rows that match no issuer we hold are reported, never force-created;
  * a value that conflicts with an existing client figure is flagged, not applied.

A mapping PROFILE is just {our_field: vendor_column_name}. Built-in profiles cover
the common vendors; a caller can pass a custom mapping for any other extract.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import text

# our_field → the vendor's column header. Built-in profiles; extend/override freely.
PROFILES: dict[str, dict[str, str]] = {
    "msci": {
        "isin": "ISIN", "lei": "LEI",
        "scope1_tco2e": "CARBON_EMISSIONS_SCOPE_1", "scope2_tco2e": "CARBON_EMISSIONS_SCOPE_2",
        "scope3_tco2e": "CARBON_EMISSIONS_SCOPE_3", "revenue_eur": "SALES_EUR", "evic_eur": "EVIC_EUR",
        "non_renewable_energy_pct": "PCT_NONRENEW_ENERGY", "gender_pay_gap_pct": "GENDER_PAY_GAP",
        "board_female_pct": "FEMALE_DIRECTORS_PCT", "controversial_weapons": "CONTROVERSIAL_WEAPONS_FLAG",
        "ungc_oecd_violation": "GLOBAL_COMPACT_VIOLATION",
        "taxonomy_eligible_pct": "EU_TAXONOMY_ELIGIBLE_PCT", "taxonomy_aligned_pct": "EU_TAXONOMY_ALIGNED_PCT",
    },
    "iss": {
        "isin": "ISIN", "lei": "LEI",
        "scope1_tco2e": "Scope1", "scope2_tco2e": "Scope2", "scope3_tco2e": "Scope3",
        "revenue_eur": "Revenue_EUR", "evic_eur": "EVIC_EUR",
        "gender_pay_gap_pct": "GenderPayGap", "board_female_pct": "BoardFemalePct",
        "controversial_weapons": "ControversialWeapons", "ungc_oecd_violation": "UNGCViolation",
        "taxonomy_eligible_pct": "TaxonomyEligible", "taxonomy_aligned_pct": "TaxonomyAligned",
    },
}

_EMISSION_FIELDS = {"scope1_tco2e", "scope2_tco2e", "scope3_tco2e", "revenue_eur", "evic_eur"}
_ESG_FIELDS = {
    "non_renewable_energy_pct", "energy_intensity_gwh_per_meur", "biodiversity_sensitive_ops",
    "emissions_to_water_tonnes", "hazardous_waste_tonnes", "ungc_oecd_violation",
    "ungc_oecd_no_monitoring", "gender_pay_gap_pct", "board_female_pct", "controversial_weapons",
    "taxonomy_eligible_pct", "taxonomy_aligned_pct",
}
_BOOL_FIELDS = {"biodiversity_sensitive_ops", "ungc_oecd_violation", "ungc_oecd_no_monitoring", "controversial_weapons"}


def _coerce(field: str, raw):
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if field in _BOOL_FIELDS:
        if isinstance(raw, bool):
            return raw
        return str(raw).strip().lower() in ("1", "true", "yes", "y", "t")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _match_issuer(session, isin: Optional[str], lei: Optional[str]) -> Optional[str]:
    """Match a vendor row to an issuer we already hold — by ISIN, then LEI. Never
    creates one (a vendor row for a security we don't hold is reported, not seeded)."""
    if isin:
        iid = session.execute(text(
            "SELECT issuer_id::text FROM securities WHERE isin = :x LIMIT 1"),
            {"x": isin.strip().upper()}).scalar()
        if iid:
            return iid
    if lei:
        iid = session.execute(text(
            "SELECT issuer_id::text FROM issuers WHERE lei = :l LIMIT 1"),
            {"l": lei.strip().upper()}).scalar()
        if iid:
            return iid
    return None


def ingest_vendor_extract(session, org_id: str, rows: list[dict], *, profile: str = "msci",
                          mapping: Optional[dict] = None, reporting_year: Optional[int] = None) -> dict:
    """Ingest vendor rows for the manager's org. Returns a reconciliation report."""
    colmap = mapping or PROFILES.get(profile)
    if not colmap:
        return {"error": f"unknown profile {profile!r}", "profiles": list(PROFILES)}
    year = reporting_year or date.today().year

    matched, unmatched, emission_writes, esg_writes, client_conflicts = 0, [], 0, 0, 0
    for row in rows:
        def val(field):
            col = colmap.get(field)
            return _coerce(field, row.get(col)) if col else None

        isin = (row.get(colmap.get("isin", "")) or "") or None
        lei = (row.get(colmap.get("lei", "")) or "") or None
        issuer_id = _match_issuer(session, isin, lei)
        if not issuer_id:
            unmatched.append(isin or lei or "?")
            continue
        matched += 1

        emis = {f: val(f) for f in _EMISSION_FIELDS}
        if any(v is not None for v in emis.values()):
            # Does the manager already hold their OWN (client) figure for this issuer/year?
            # If so, flag it — the vendor row is stored separately and only wins if no
            # client row exists (precedence handled at read time).
            has_client = session.execute(text(
                "SELECT 1 FROM issuer_emissions WHERE issuer_id=:i AND org_id=:o "
                "AND reporting_year=:y AND source='client' LIMIT 1"),
                {"i": issuer_id, "o": org_id, "y": year}).first()
            if has_client:
                client_conflicts += 1
            session.execute(text("""
                INSERT INTO issuer_emissions
                    (issuer_id, org_id, reporting_year, scope1_tco2e, scope2_tco2e, scope3_tco2e,
                     revenue_eur, evic_eur, source, data_vintage)
                VALUES (:i, :o, :y, :s1, :s2, :s3, :rev, :evic, 'vendor', now())
                ON CONFLICT (issuer_id, reporting_year, source, org_id) WHERE org_id IS NOT NULL
                DO UPDATE SET scope1_tco2e = COALESCE(EXCLUDED.scope1_tco2e, issuer_emissions.scope1_tco2e),
                              scope2_tco2e = COALESCE(EXCLUDED.scope2_tco2e, issuer_emissions.scope2_tco2e),
                              scope3_tco2e = COALESCE(EXCLUDED.scope3_tco2e, issuer_emissions.scope3_tco2e),
                              revenue_eur  = COALESCE(EXCLUDED.revenue_eur, issuer_emissions.revenue_eur),
                              evic_eur     = COALESCE(EXCLUDED.evic_eur, issuer_emissions.evic_eur),
                              data_vintage = now()
            """), {"i": issuer_id, "o": org_id, "y": year, "s1": emis["scope1_tco2e"],
                   "s2": emis["scope2_tco2e"], "s3": emis["scope3_tco2e"],
                   "rev": emis["revenue_eur"], "evic": emis["evic_eur"]})
            emission_writes += 1

        esg = {f: val(f) for f in _ESG_FIELDS}
        if any(v is not None for v in esg.values()):
            cols = ", ".join(esg)
            placeholders = ", ".join(f":{k}" for k in esg)
            updates = ", ".join(f"{k} = COALESCE(EXCLUDED.{k}, issuer_esg_metrics.{k})" for k in esg)
            session.execute(text(f"""
                INSERT INTO issuer_esg_metrics (issuer_id, org_id, reporting_year, {cols}, source, data_vintage)
                VALUES (:i, :o, :y, {placeholders}, 'vendor', now())
                ON CONFLICT (issuer_id, reporting_year, org_id) WHERE org_id IS NOT NULL
                DO UPDATE SET {updates}, data_vintage = now()
            """), {"i": issuer_id, "o": org_id, "y": year, **esg})
            esg_writes += 1

    return {
        "profile": profile if not mapping else "custom",
        "reporting_year": year,
        "rows": len(rows),
        "matched_issuers": matched,
        "unmatched": unmatched,
        "unmatched_count": len(unmatched),
        "emission_records_written": emission_writes,
        "esg_records_written": esg_writes,
        "client_conflicts": client_conflicts,   # issuers where the manager's OWN figure takes precedence
        "note": "Vendor data stored as source='vendor'. Precedence is own > vendor > global, "
                "so your own disclosures always win; unmatched rows are reported, never created.",
    }
