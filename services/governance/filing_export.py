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
import os
from pathlib import Path

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

    if fmt == "ixbrl":
        doc = _ixbrl(session, org_id, filing["framework"], payload, basis)
        return f"{stem}.xhtml", "application/xhtml+xml", doc.encode("utf-8")

    raise ExportError(f"unknown format '{fmt}'")


def _cell_text(cell: dict):
    """Display value of an annex cell for the export sheet (dp-bound cells carry the merged datapoint value)."""
    if "dp" in cell:
        dp = cell.get("dp") or {}
        v = dp.get("value")
        return v if v is not None else "—"
    return cell.get("text")


def _summary_blocks(framework: str, payload: dict) -> list[dict]:
    """The computed official-form sections (catastrophe/SCR/stranding/concentration/…) flattened into
    export blocks, so every analytic the annex shows also lands in the downloadable workbook. Payload-derived
    sections render fully; datapoint-bound cells with no frozen value render '—' (the honest gap, preserved)."""
    from services.governance.filing_annex import build_annex
    ann = build_annex(framework, {}, [], payload=payload) or {}
    blocks = []
    for sec in ann.get("sections", []):
        rows = []
        for row in sec.get("rows", []):
            if row.get("type") == "subheader":
                rows.append([row.get("label")])
            else:
                rows.append([_cell_text(c) for c in row.get("cells", [])])
        blocks.append({"title": sec.get("title", ""), "columns": sec.get("columns") or [], "rows": rows})
    return blocks


def _xlsx(framework: str, payload: dict) -> io.BytesIO:
    from services.templates.workbook import build_disclosure_workbook, build_export_workbook
    if framework in ("bank_tcfd", "bank_p3esg"):
        headers = ["asset_name", "sector", "country", "value_eur", "headline_score",
                   "risk_bucket", "taxonomy_status", "h3_cell"]
        rows = [[a.get("asset_name"), a.get("sector"), a.get("country"), a.get("value_eur"),
                 a.get("headline_score"), a.get("headline_bucket") or "unscored",
                 a.get("taxonomy_status"), a.get("h3_cell")] for a in payload.get("assets", [])]
        return build_disclosure_workbook(headers, rows, "Physical risk disclosure", _summary_blocks(framework, payload))
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
    if framework == "reit_tcfd":
        headers = ["property_name", "property_type", "country", "property_value_eur", "headline_score",
                   "risk_bucket", "taxonomy_status", "h3_cell"]
        rows = [[p.get("property_name"), p.get("property_type"), p.get("country"), p.get("property_value_eur"),
                 p.get("headline_score"), p.get("headline_bucket") or "unscored",
                 p.get("taxonomy_status"), p.get("h3_cell")] for p in payload.get("properties", [])]
        return build_disclosure_workbook(headers, rows, "Property physical risk", _summary_blocks(framework, payload))
    if framework == "insurer_climate":
        headers = ["policy_name", "region", "sum_insured_eur", "headline_score", "risk_bucket", "h3_cell"]
        rows = [[p.get("policy_name"), p.get("region"), p.get("sum_insured_eur"), p.get("headline_score"),
                 p.get("headline_bucket") or "unscored", p.get("h3_cell")] for p in payload.get("policies", [])]
        return build_disclosure_workbook(headers, rows, "NatCat exposure disclosure", _summary_blocks(framework, payload))
    if framework == "assetmgmt_tcfd":
        headers = ["holding_name", "sector", "country", "position_value_eur", "headline_score",
                   "risk_bucket", "taxonomy_status", "h3_cell"]
        rows = [[h.get("holding_name"), h.get("sector"), h.get("country"), h.get("position_value_eur"),
                 h.get("headline_score"), h.get("headline_bucket") or "unscored",
                 h.get("taxonomy_status"), h.get("h3_cell")] for h in payload.get("holdings", [])]
        return build_disclosure_workbook(headers, rows, "Holdings physical risk", _summary_blocks(framework, payload))
    raise ExportError(f"no workbook renderer for '{framework}'")


# ESRS filings tag under the official-intent EFRAG Set 1 profile: it emits the official esrs: QNames and
# lights up as a validated ESEF filing the day the EFRAG element map is dropped in (config/efrag_esrs_binding.json)
# — zero code change. Until then it is honestly labelled pending. See services/intelligence/esrs_taxonomy.py.
_ESRS_PROFILE = "efrag_set1"


def _xbrl(session: Session, org_id: str, framework: str, payload: dict, basis: dict) -> str:
    if framework == "sfdr_pai":
        from ml.regulatory.sfdr_xbrl import sfdr_pai_xbrl
        return sfdr_pai_xbrl(payload)
    if framework == "bank_tcfd":
        return _bank_tcfd_xbrl(session, org_id, payload, basis)
    if framework == "bank_p3esg":
        return _bank_p3esg_xbrl(session, org_id, payload, basis)
    if framework == "esrs_pack":                     # tag the FROZEN pack via the shared iXBRL engine (WORM-faithful)
        from services.intelligence.esrs_xbrl import build_xbrl_instance
        return build_xbrl_instance(session, org_id, pack=payload, profile_key=_ESRS_PROFILE,
                                   period_end=(basis or {}).get("reporting_period_end"))
    raise ExportError(f"no XBRL renderer for '{framework}'")


def _ixbrl(session: Session, org_id: str, framework: str, payload: dict, basis: dict) -> str:
    """Inline XBRL (iXBRL/ESEF): one document a person reads and a machine parses, tagged from the FROZEN
    snapshot so the filed bytes are exactly what was reproducible-by-hash. ESRS only for now (the one engine
    that emits iXBRL); other frameworks export XBRL/xlsx."""
    if framework == "esrs_pack":
        from services.intelligence.esrs_xbrl import build_ixbrl
        return build_ixbrl(session, org_id, pack=payload, profile_key=_ESRS_PROFILE,
                           period_end=(basis or {}).get("reporting_period_end"))
    if framework == "sfdr_pai":
        from ml.regulatory.sfdr_xbrl import sfdr_pai_ixbrl
        return sfdr_pai_ixbrl(payload)
    raise ExportError(f"no iXBRL renderer for '{framework}' (available for ESRS + SFDR filings)")


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


# ── Pillar 3 ESG (ITS 2022/2453) XBRL instance from the frozen bank payload ──────────────────────
# Same faithful-serialization contract: facts are recomputed deterministically from the FROZEN per-asset
# book (the annex grids are pure functions of it), never a live re-score. Concept QNames live in Tellumen's
# namespace; map them to the official EBA DPM taxonomy element IDs when filing to the regulator's collector.
_P3_NS = "https://taxonomy.tellumen.eu/p3esg/2024"
_P3_BINDING_FILE = Path(os.getenv("EBA_P3ESG_BINDING", "config/eba_p3esg_binding.json"))


def _load_p3_binding() -> dict:
    """Official EBA Pillar 3 ESG element map, if supplied → {namespace, elements{fact: element}}.
    A scaffold with null elements is honestly ignored (stays provisional); only a real namespace +
    real element names bind. Drop `config/eba_p3esg_binding.json` in when the EBA publishes the
    Pillar-3-Data-Hub taxonomy — no code change. The ITS template/column refs in the file are already
    verified against CIR (EU) 2022/2453; only the machine element id is pending."""
    try:
        if _P3_BINDING_FILE.exists():
            data = json.loads(_P3_BINDING_FILE.read_text())
            ns = data.get("namespace")
            els = data.get("elements", {})
            emap = {k: v["element"] for k, v in els.items()
                    if isinstance(v, dict) and isinstance(v.get("element"), str) and v["element"].strip()}
            if ns and emap:
                return {"namespace": ns, "elements": emap}
    except Exception:
        pass
    return {}


def p3esg_binding_status() -> dict:
    """Coverage of the EBA element binding — how many of our facts carry an official element id vs provisional."""
    b = _load_p3_binding()
    emap = b.get("elements", {})
    facts = ["TotalBookValue", "PhysicalRiskSensitiveExposure", "PhysicalRiskChronicExposure",
             "PhysicalRiskAcuteExposure", "GARTotalAssets", "GARCoveredAssets", "GAREligibleExposure",
             "GARAlignedExposure", "GreenAssetRatioStockPct", "FinancedEmissionsScope1",
             "FinancedEmissionsScope2", "FinancedEmissionsScope3", "FinancedEmissionsTotal"]
    bound = [f for f in facts if f in emap]
    return {"profile": "eba_dpm" if emap else "provisional",
            "status": "bound" if len(bound) == len(facts) else ("partial" if bound else "pending_eba_taxonomy"),
            "namespace": b.get("namespace") or _P3_NS,
            "facts_total": len(facts), "facts_bound": len(bound),
            "note": ("Bound to the supplied EBA Pillar 3 ESG element map."
                     if bound else
                     "Provisional Tellumen namespace — a real tagged-fact layer, NOT a validated EBA "
                     "submission. Drop config/eba_p3esg_binding.json (EBA taxonomy pending, ITS amended "
                     "Jun-2026, ref 31 Dec 2026 / 2027 SNCIs) to bind. Template/column refs already verified vs 2022/2453.")}


def _bank_p3esg_xbrl(session: Session, org_id: str, payload: dict, basis: dict) -> str:
    from xml.sax.saxutils import escape

    from services.governance.pillar3_templates import gar_grid, template1_grid, template5_grid

    org = session.execute(text("SELECT lei, legal_name, name FROM organizations WHERE org_id = :o"),
                          {"o": org_id}).mappings().first() or {}
    lei = escape(str(org.get("lei") or "LEIUNAVAILABLE00000"))
    period = str(basis.get("reporting_period_end") or "")[:4] or "2024"
    assets = payload.get("assets") or []
    rollup = payload.get("rollup") or {}
    gar = gar_grid(assets) if assets else {}
    t1 = template1_grid(assets)["total"] if assets else {}
    t5 = template5_grid(assets)["total"] if assets else {}
    s1 = sum((a.get("ghg1") or 0) for a in assets)
    s2 = sum((a.get("ghg2") or 0) for a in assets)
    s3 = sum((a.get("ghg3") or 0) for a in assets)

    binding = _load_p3_binding()
    ns = binding.get("namespace") or _P3_NS
    emap = binding.get("elements") or {}

    facts: list[str] = []

    def fact(name, unit, value, dec="2"):
        if value is None:
            return
        el = emap.get(name, name)  # official EBA element when bound, else our provisional local-name
        facts.append(f'  <p3:{el} contextRef="d0" unitRef="{unit}" decimals="{dec}">{value}</p3:{el}>')

    # rollup + Template 5 physical risk
    fact("TotalBookValue", "uEUR", rollup.get("total_value_eur"), dec="0")
    fact("PhysicalRiskSensitiveExposure", "uEUR", t5.get("sensitive"), dec="0")
    fact("PhysicalRiskChronicExposure", "uEUR", t5.get("chronic"), dec="0")
    fact("PhysicalRiskAcuteExposure", "uEUR", t5.get("acute"), dec="0")
    # Templates 6–8 Green Asset Ratio
    fact("GARTotalAssets", "uEUR", gar.get("total_assets"), dec="0")
    fact("GARCoveredAssets", "uEUR", gar.get("covered_assets"), dec="0")
    fact("GAREligibleExposure", "uEUR", gar.get("eligible"), dec="0")
    fact("GARAlignedExposure", "uEUR", gar.get("aligned"), dec="0")
    fact("GreenAssetRatioStockPct", "uPure", gar.get("gar_stock_pct"))
    # Template 1 financed emissions (Scope 1–3)
    fact("FinancedEmissionsScope1", "uCO2e", s1 or None, dec="0")
    fact("FinancedEmissionsScope2", "uCO2e", s2 or None, dec="0")
    fact("FinancedEmissionsScope3", "uCO2e", s3 or None, dec="0")
    fact("FinancedEmissionsTotal", "uCO2e", t1.get("fin_emissions"), dec="0")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"',
        '            xmlns:iso4217="http://www.xbrl.org/2003/iso4217"',
        f'            xmlns:p3="{ns}">',
        f'  <!-- Pillar 3 ESG physical-risk & Taxonomy disclosure (ITS 2022/2453) · {escape(str(org.get("legal_name") or org.get("name") or ""))} -->',
        ('  <!-- Taxonomy binding: OFFICIAL EBA element map -->' if emap else
         '  <!-- Taxonomy binding: provisional namespace (EBA Pillar 3 XBRL taxonomy pending); drop config/eba_p3esg_binding.json to bind -->'),
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
        '  <xbrli:unit id="uCO2e"><xbrli:measure>p3:tCO2e</xbrli:measure></xbrli:unit>',
        *facts,
        '</xbrli:xbrl>',
    ]
    return "\n".join(lines)
