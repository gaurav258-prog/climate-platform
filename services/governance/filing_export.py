"""Machine-readable exports rendered from the FROZEN filing snapshot — never a live rebuild.

An attested/submitted filing must be downloadable in exactly the bytes that were frozen and signed off.
The older export endpoints (bank .xlsx, SFDR .xbrl, ESRS ixbrl) recompute from the LIVE engine, so a
downloaded artifact could silently drift from the attested figures — the WORM chain stopped at the JSON
payload. These renderers read straight from `report_snapshots.payload` (the hashed, immutable record) and
stamp the filename with the snapshot version + content-hash prefix, so the file is provably the frozen record.

Honesty: nothing is recomputed or "freshened" — a euro that was withheld at freeze stays withheld; a gap
stays a gap. The export is a faithful serialization of what a human attested.
"""
from __future__ import annotations

import io
import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.governance.filings import EXPORT_FORMATS, get_filing


class ExportError(ValueError):
    pass


def formats_for(framework: str) -> tuple[str, ...]:
    return EXPORT_FORMATS.get(framework, ("json",))


def export_filing(session: Session, org_id: str, filing_id: str, fmt: str) -> tuple[str, str, bytes]:
    """Render a filing's frozen snapshot to (filename, media_type, bytes). Raises ExportError on any gap."""
    filing = get_filing(session, org_id, filing_id, with_payload=True)
    if not filing:
        raise ExportError("filing not found")
    snap = filing.get("snapshot")
    if not snap:
        raise ExportError("this filing has no frozen snapshot yet — prepare it first")
    fmt = (fmt or "").lower()
    if fmt not in formats_for(filing["framework"]):
        raise ExportError(f"'{fmt}' is not an available format for a {filing['framework']} filing")

    payload = snap.get("payload") or {}
    basis = snap.get("reporting_basis") or {}
    version = snap.get("version")
    sha = (snap.get("payload_sha256") or "")[:8]
    stem = f"{filing['framework']}-{filing['period_label']}-v{version}-{sha}"

    if fmt == "json":
        record = {
            "filing_id": filing_id, "framework": filing["framework"],
            "period_label": filing["period_label"], "status": filing["status"],
            "snapshot_version": version, "payload_sha256": snap.get("payload_sha256"),
            "hash_verified": snap.get("hash_verified"), "reporting_basis": basis,
            "engine_versions": snap.get("engine_versions"), "payload": payload,
        }
        return f"{stem}.json", "application/json", json.dumps(record, default=str, indent=2).encode("utf-8")

    if fmt == "xlsx":
        buf = _xlsx(filing["framework"], payload)
        return (f"{stem}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buf.getvalue())

    if fmt == "xbrl":
        xml = _xbrl(session, org_id, filing["framework"], payload, basis)
        return f"{stem}.xbrl", "application/xml", xml.encode("utf-8")

    raise ExportError(f"unknown format '{fmt}'")


def _xlsx(framework: str, payload: dict) -> io.BytesIO:
    from services.templates.workbook import build_export_workbook
    if framework == "bank_tcfd":
        headers = ["asset_name", "sector", "country", "value_eur", "headline_score",
                   "risk_bucket", "taxonomy_status", "h3_cell"]
        rows = [[a.get("asset_name"), a.get("sector"), a.get("country"), a.get("value_eur"),
                 a.get("headline_score"), a.get("headline_bucket") or "unscored",
                 a.get("taxonomy_status"), a.get("h3_cell")] for a in payload.get("assets", [])]
        return build_export_workbook(headers, rows, sheet_name="Physical risk disclosure")
    if framework == "sfdr_pai":
        # build straight from the frozen entity-level indicator rows (fund-level renderer expects a
        # different shape, so we serialize the entity statement's own mandatory-indicator table)
        headers = ["number", "area", "metric", "value", "unit", "coverage_pct", "input_required"]
        rows = []
        for i in payload.get("indicators", []):
            v = i.get("value")
            if isinstance(v, dict):
                v = v.get("total", v)
            rows.append([i.get("number"), i.get("area"), i.get("metric"), v,
                         i.get("unit"), i.get("coverage_pct"), i.get("input_required")])
        return build_export_workbook(headers, rows, sheet_name="SFDR PAI · Annex I Table 1")
    raise ExportError(f"no workbook renderer for '{framework}'")


def _xbrl(session: Session, org_id: str, framework: str, payload: dict, basis: dict) -> str:
    if framework == "sfdr_pai":
        from ml.regulatory.sfdr_xbrl import sfdr_pai_xbrl
        return sfdr_pai_xbrl(payload)
    if framework == "bank_tcfd":
        return _bank_tcfd_xbrl(session, org_id, payload, basis)
    raise ExportError(f"no XBRL renderer for '{framework}'")


# ── compact TCFD/EU-Taxonomy XBRL instance from the frozen bank payload ──────────────────────────
# A valid xbrli instance against a placeholder Tellumen taxonomy (swap the namespace for the official
# EBA/ESRS taxonomy when published). Facts are the entity-level figures actually reported.
_TB_NS = "https://taxonomy.tellumen.eu/tcfd/physical/2024"
_LEI_SCHEME = "http://standards.iso.org/iso/17442"


def _bank_tcfd_xbrl(session: Session, org_id: str, payload: dict, basis: dict) -> str:
    from xml.sax.saxutils import escape
    org = session.execute(text("SELECT lei, legal_name, name FROM organizations WHERE org_id = :o"),
                          {"o": org_id}).mappings().first() or {}
    lei = escape(str(org.get("lei") or "LEIUNAVAILABLE00000"))
    period = str(basis.get("reporting_period_end") or "")[:4] or "2024"
    rollup = payload.get("rollup") or {}
    tax = payload.get("taxonomy") or {}
    em = payload.get("financed_emissions_tco2e") or {}

    facts: list[str] = []

    def fact(name, unit, value, dec="2"):
        if value is None:
            return
        facts.append(f'  <tb:{name} contextRef="d0" unitRef="{unit}" decimals="{dec}">{value}</tb:{name}>')

    fact("TotalBookValue", "uEUR", rollup.get("total_value_eur"), dec="0")
    fact("ValueAtRiskHighPlus", "uEUR", rollup.get("value_at_risk_eur"), dec="0")
    fact("ShareOfBookAtRiskPct", "uPure", rollup.get("pct_value_at_risk"))
    fact("AssetsScored", "uPure", rollup.get("n_scored"), dec="0")
    fact("AssetsInScope", "uPure", rollup.get("n_assets"), dec="0")
    # per-hazard value exposed at High+ (dimension folded into the element name — honest & self-describing)
    for hz, b in (payload.get("by_hazard") or {}).items():
        safe = "".join(ch for ch in hz.title() if ch.isalnum())
        fact(f"ExposedValue{safe}", "uEUR", b.get("exposed_value_eur"), dec="0")
    for k, elem in (("eligible", "TaxonomyEligibleValue"), ("not_eligible", "TaxonomyNotEligibleValue")):
        if isinstance(tax.get(k), dict):
            fact(elem, "uEUR", tax[k].get("value_eur"), dec="0")
    for scope in ("scope1", "scope2", "scope3"):
        fact(f"FinancedEmissions{scope.title()}", "uCO2e", em.get(scope), dec="0")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"',
        '            xmlns:iso4217="http://www.xbrl.org/2003/iso4217"',
        f'            xmlns:tb="{_TB_NS}">',
        f'  <!-- TCFD / EU-Taxonomy physical-risk disclosure · {escape(str(org.get("legal_name") or org.get("name") or ""))} -->',
        '  <xbrli:context id="d0">',
        '    <xbrli:entity>',
        f'      <xbrli:identifier scheme="{_LEI_SCHEME}">{lei}</xbrli:identifier>',
        '    </xbrli:entity>',
        '    <xbrli:period>',
        f'      <xbrli:startDate>{period}-01-01</xbrli:startDate>',
        f'      <xbrli:endDate>{period}-12-31</xbrli:endDate>',
        '    </xbrli:period>',
        '  </xbrli:context>',
        '  <xbrli:unit id="uEUR"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uPure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uCO2e"><xbrli:measure>tb:tCO2e</xbrli:measure></xbrli:unit>',
        *facts,
        '</xbrli:xbrl>',
    ]
    return "\n".join(lines)
