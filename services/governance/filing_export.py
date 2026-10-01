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
from services.governance.money_format import presentation_of


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
            "presentation_currency": presentation_of(payload),
            "amounts_note": "Amount fields keep their *_eur names; they are in presentation_currency (see payload._fx).",
            "hash_verified": snap.get("hash_verified"), "reporting_basis": basis,
            "engine_versions": snap.get("engine_versions"), "payload": payload,
        }
        return f"{stem}.json", "application/json", json.dumps(record, default=str, indent=2).encode("utf-8")

    if fmt == "xlsx":
        buf = _xlsx(filing["framework"], payload)
        return (f"{stem}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buf.getvalue())

    if fmt == "xbrl":
        xml = _xbrl(session, org_id, filing["framework"], payload, basis, filing.get("entity_id"))
        return f"{stem}.xbrl", "application/xml", xml.encode("utf-8")

    if fmt == "ixbrl":
        doc = _ixbrl(session, org_id, filing["framework"], payload, basis)
        return f"{stem}.xhtml", "application/xhtml+xml", doc.encode("utf-8")

    if fmt == "html":                                  # a document template (SFDR Annexes II–V): the annex as filed
        from services.governance import sfdr_product_forms
        from services.governance.sfdr_product_html import render
        if not payload.get("fund"):
            raise ExportError("this filing froze no fund")
        spec, tid, built = sfdr_product_forms.items(payload, filing["framework"])
        import services.regspec as R
        doc = render(R.template(spec, tid)["title"], R.citation(spec, tid), payload["fund"], built,
                     payload["period"]["end"] if payload.get("document") == "periodic" else None)
        return f"{stem}.html", "text/html", doc.encode("utf-8")

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


def _cur(headers: list[str], payload: dict) -> list[str]:
    """Column names say the currency the figures are in: value_eur → value_usd for a filing presented in USD."""
    c = presentation_of(payload).lower()
    return headers if c == "eur" else [h[:-4] + "_" + c if h.endswith("_eur") else (c if h == "eur" else h) for h in headers]


def _xlsx(framework: str, payload: dict) -> io.BytesIO:
    from services.templates.workbook import build_disclosure_workbook, build_export_workbook
    if framework == "bank_tcfd":                       # the frozen book as the templates read it, then the templates (E95)
        from services.governance.bank_taxonomy_report import XLSX_HEADERS, xlsx_rows
        return build_disclosure_workbook(_cur(XLSX_HEADERS, payload), xlsx_rows(payload),
                                         "EU Taxonomy Art. 8 — loan book", _summary_blocks(framework, payload))
    if framework == "bank_p3esg":
        headers = ["asset_name", "sector", "country", "value_eur", "headline_score",
                   "risk_bucket", "taxonomy_status", "h3_cell"]
        rows = [[a.get("asset_name"), a.get("sector"), a.get("country"), a.get("value_eur"),
                 a.get("headline_score"), a.get("headline_bucket") or "unscored",
                 a.get("taxonomy_status"), a.get("h3_cell")] for a in payload.get("assets", [])]
        return build_disclosure_workbook(_cur(headers, payload), rows, "Physical risk disclosure", _summary_blocks(framework, payload))
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
        return build_export_workbook(_cur(headers, payload), rows, sheet_name="SFDR PAI · Annex I Table 1")
    if framework == "reit_tcfd":
        headers = ["property_name", "property_type", "country", "property_value_eur", "headline_score",
                   "risk_bucket", "taxonomy_status", "h3_cell"]
        rows = [[p.get("property_name"), p.get("property_type"), p.get("country"), p.get("property_value_eur"),
                 p.get("headline_score"), p.get("headline_bucket") or "unscored",
                 p.get("taxonomy_status"), p.get("h3_cell")] for p in payload.get("properties", [])]
        return build_disclosure_workbook(_cur(headers, payload), rows, "Property physical risk", _summary_blocks(framework, payload))
    if framework == "insurer_climate":
        headers = ["policy_name", "region", "sum_insured_eur", "headline_score", "risk_bucket", "h3_cell"]
        rows = [[p.get("policy_name"), p.get("region"), p.get("sum_insured_eur"), p.get("headline_score"),
                 p.get("headline_bucket") or "unscored", p.get("h3_cell")] for p in payload.get("policies", [])]
        return build_disclosure_workbook(_cur(headers, payload), rows, "NatCat exposure disclosure", _summary_blocks(framework, payload))
    if framework == "assetmgmt_tcfd":
        headers = ["holding_name", "sector", "country", "position_value_eur", "headline_score",
                   "risk_bucket", "taxonomy_status", "h3_cell"]
        rows = [[h.get("holding_name"), h.get("sector"), h.get("country"), h.get("position_value_eur"),
                 h.get("headline_score"), h.get("headline_bucket") or "unscored",
                 h.get("taxonomy_status"), h.get("h3_cell")] for h in payload.get("holdings", [])]
        return build_disclosure_workbook(_cur(headers, payload), rows, "Holdings physical risk", _summary_blocks(framework, payload))
    if framework == "reit_taxonomy":
        # the property book with each building's EU Taxonomy verdict, then the Annex II templates as blocks
        from services.governance.taxonomy_nonfin import summary_of
        sm = summary_of(payload)
        headers = ["property_name", "turnover_eur", "noi_proxy", "activity", "aligned", "why"]
        rows = [[b["name"], b["turnover"], b["noi_proxy"], b["activity"],
                 {True: "aligned", False: "not aligned", None: "not determined"}[b["aligned"]] if b["activity"] else "not eligible",
                 b["why"]] for b in sm["buildings"]]
        return build_disclosure_workbook(_cur(headers, payload), rows, "EU Taxonomy Art. 8 — buildings",
                                         _summary_blocks(framework, payload))
    if framework == "insurer_solvency":
        # the frozen payload is a summary, not a per-policy book: {"rollup", "s2701"} (report_snapshots._insurer_solvency,
        # insurer_solvency.s2701_natcat; 's2601' in filings frozen before the template was corrected)
        from services.governance import s2701_forms
        from services.governance.insurer_solvency import TEMPLATE, natcat_block
        from services.governance.solvency2_natcat import lines
        laid_out = s2701_forms.workbook(payload)            # the template as Annex I prints it (spec-frozen filings)
        if laid_out is not None:
            return laid_out
        nb = natcat_block(payload)
        headers = ["section", "line", "exposure_eur", "specified_gross_loss_eur", "scenario", "before_mitigation_eur",
                   "risk_mitigation_eur", "reinstatement_premiums_eur", "after_mitigation_eur", "note"]
        rows: list[list] = []
        if nb.get("available", True):
            nc = nb.get("natcat_scr") or {}
            im = "Modelled 1-in-200 (stated method; not an approved internal model)"
            rows += [[im, "Modelled 1-in-200 loss — gross", None, None, None, nc.get("gross_1_in_200_eur"), None, None, None, ""],
                     [im, "Modelled 1-in-200 loss — net of reinsurance", None, None, None, None, None, None, nc.get("net_of_reinsurance_1_in_200_eur"), ""],
                     [im, "Mean annual loss", None, None, None, nc.get("mean_annual_loss_eur"), None, None, None, ""]]
            for p in nb.get("perils", []):
                rows.append(["Peril accumulation", p.get("peril"), p.get("exposed_value_eur"), None, None, None, None, None,
                             None, f"{p.get('n_exposed', 0)} policies exposed"])
            sf = nb.get("standard_formula_natcat") or {}
            if sf.get("available") and "perils" in sf and "version" in sf:
                for ln in lines(sf):
                    rows.append([f"Standard formula · {ln['peril']}", ln["line"], ln.get("exposure_eur"),
                                 ln.get("specified_gross_loss_eur"), ln.get("scenario"), ln.get("before_eur"),
                                 ln.get("mitigation_eur"), ln.get("reinstatement_eur"), ln.get("after_eur"), ln.get("note") or ""])
                rows += [["Standard formula", "Incomplete", None, None, None, None, None, None, None, x] for x in sf.get("incomplete", [])]
            elif sf.get("available"):                       # a filing frozen before the standard formula was rebuilt
                rows.append(["Standard formula (as frozen)", "Nat-cat SCR", None, None, None, None, None, None,
                             sf.get("natcat_scr_eur"), "gross of reinsurance, country level (superseded method)"])
        else:
            rows.append(["Unavailable", nb.get("reason", "no scored policies"), None, None, None, None, None, None, None, ""])
        return build_export_workbook(_cur(headers, payload), rows, sheet_name=f"Solvency II · {TEMPLATE}")
    raise ExportError(f"no workbook renderer for '{framework}'")


def _identity(session: Session, org_id: str, entity_id: str | None) -> dict:
    """Who the filing identifies to the regulator: the filing entity's own LEI (a solo or sub-group filing), else the
    organisation's (a whole-organisation filing, or an entity without one — said so in the file). No LEI at all refuses
    the export: an XBRL instance with a made-up identifier is not a filing."""
    org = session.execute(text("SELECT lei, legal_name, name FROM organizations WHERE org_id = :o"),
                          {"o": org_id}).mappings().first() or {}
    name = org.get("legal_name") or org.get("name") or ""
    if entity_id:
        ent = session.execute(text("SELECT lei, name FROM reporting_entities WHERE org_id = :o AND entity_id = :e"),
                              {"o": org_id, "e": entity_id}).mappings().first()
        if ent and ent["lei"]:
            return {"lei": ent["lei"].strip(), "name": ent["name"], "note": "identified by the filing entity's own LEI"}
        if org.get("lei"):
            return {"lei": org["lei"].strip(), "name": name,
                    "note": f"{ent['name'] if ent else 'the filing entity'} has no LEI on file — identified by the organisation's LEI"}
    elif org.get("lei"):
        return {"lei": org["lei"].strip(), "name": name, "note": "identified by the organisation's LEI"}
    raise ExportError("no LEI on file for this filing — add the entity's LEI (Admin → Entities) or the organisation's, "
                      "then export again")


def _xbrl(session: Session, org_id: str, framework: str, payload: dict, basis: dict, entity_id: str | None = None) -> str:
    if framework == "sfdr_pai":
        from ml.regulatory.sfdr_xbrl import XbrlIdentityError, sfdr_pai_xbrl
        try:
            return sfdr_pai_xbrl(payload)
        except XbrlIdentityError as e:
            raise ExportError(str(e)) from e
    if framework == "insurer_solvency":                # EIOPA's own taxonomy (services.governance.s2701_xbrl)
        from services.governance.s2701_xbrl import XbrlError, instance
        try:
            return instance(payload, _identity(session, org_id, entity_id))
        except XbrlError as e:
            raise ExportError(str(e)) from e
    if framework == "bank_p3esg":
        return _bank_p3esg_xbrl(session, org_id, payload, basis, entity_id)
    raise ExportError(f"no XBRL renderer for '{framework}'")


def _ixbrl(session: Session, org_id: str, framework: str, payload: dict, basis: dict) -> str:
    """Inline XBRL (iXBRL/ESEF): one document a person reads and a machine parses, tagged from the FROZEN
    snapshot so the filed bytes are exactly what was reproducible-by-hash. SFDR only: an ESRS statement is tagged with
    EFRAG's ESRS XBRL taxonomy, whose binding is not built (no ESRS XBRL is produced)."""
    if framework == "sfdr_pai":
        from ml.regulatory.sfdr_xbrl import XbrlIdentityError, sfdr_pai_ixbrl
        try:
            return sfdr_pai_ixbrl(payload)
        except XbrlIdentityError as e:
            raise ExportError(str(e)) from e
    raise ExportError(f"no iXBRL renderer for '{framework}' (available for SFDR filings)")


# ── XBRL helpers ─────────────────────────────────────────────────────────────────────────────
# (the bank_tcfd XBRL under a Tellumen-made namespace was removed, E95: no official XBRL binding of the EU Taxonomy
# Art. 8 templates is held, and an instance under invented element names is not a filing — as E60 for the ESRS)
_LEI_SCHEME = "http://standards.iso.org/iso/17442"


def _at(value, dec: str):
    """A fact's value written to the precision its `decimals` attribute states (decimals="0" → whole units), so the
    stated accuracy and the value agree (XBRL 2.1 §4.6.5)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    d = int(dec)
    return int(round(value)) if d <= 0 else round(float(value), d)


# ── Pillar 3 ESG XBRL instance from the frozen bank payload ──────────────────────

def _p3_act(payload: dict) -> str:
    """The implementing act the filing was prepared under (its frozen specification)."""
    from services.governance.filing_annex import _p3_spec
    spec = _p3_spec(payload)
    return spec["act"].get("short") or spec["act"]["title"]
# Same faithful-serialization contract: facts are recomputed deterministically from the FROZEN per-asset
# book (the annex grids are pure functions of it), never a live re-score. Concept QNames live in Tellumen's
# namespace; map them to the official EBA DPM taxonomy element IDs when filing to the regulator's collector.
_P3_NS = "https://taxonomy.tellumen.eu/p3esg/2024"
_P3_BINDING_FILE = Path(os.getenv("EBA_P3ESG_BINDING", "config/eba_p3esg_binding.json"))


def _load_p3_binding() -> dict:
    """Official EBA Pillar 3 ESG element map, if supplied → {namespace, elements{fact: element}}.
    A scaffold with null elements is honestly ignored (stays provisional); only a real namespace +
    real element names bind. Drop `config/eba_p3esg_binding.json` in when the EBA publishes the
    Pillar-3-Data-Hub taxonomy — no code change. The file's template/column refs are checked against the governing
    template specification by a test; only the machine element id is pending."""
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


def p3esg_facts() -> list[str]:
    """Every fact the Pillar 3 export can carry — the element map file is the one list (its 'elements' keys)."""
    return list(json.loads(_P3_BINDING_FILE.read_text()).get("elements", {}))


def p3esg_binding_status() -> dict:
    """Coverage of the EBA element binding — how many of our facts carry an official element id vs provisional."""
    b = _load_p3_binding()
    emap = b.get("elements", {})
    facts = p3esg_facts()                                    # the one list: config/eba_p3esg_binding.json
    bound = [f for f in facts if f in emap]
    return {"profile": "eba_dpm" if emap else "provisional",
            "status": "bound" if len(bound) == len(facts) else ("partial" if bound else "pending_eba_taxonomy"),
            "namespace": b.get("namespace") or _P3_NS,
            "facts_total": len(facts), "facts_bound": len(bound),
            "note": ("Bound to the supplied EBA Pillar 3 ESG element map."
                     if bound else
                     "Provisional Tellumen namespace — a real tagged-fact layer, NOT a validated EBA "
                     "submission. Drop config/eba_p3esg_binding.json (EBA taxonomy pending, ITS amended "
                     "Jun-2026, ref 31 Dec 2026 / 2027 SNCIs) to bind. Template/column refs follow the governing template specification.")}


def _bank_p3esg_xbrl(session: Session, org_id: str, payload: dict, basis: dict, entity_id: str | None = None) -> str:
    from xml.sax.saxutils import escape

    from services.governance import pillar3_gar
    from services.governance.filing_annex import _p3_spec, _period_end
    from services.governance.pillar3_grids import BINDING
    from services.governance.pillar3_grids import build as p3_build

    who = _identity(session, org_id, entity_id)
    lei = escape(who["lei"])
    period = str(basis.get("reporting_period_end") or "")[:4] or "2024"
    assets = payload.get("assets") or []
    rollup = payload.get("rollup") or {}
    spec = _p3_spec(payload)
    g = pillar3_gar.build(spec, assets, _period_end(payload)) if assets else {}
    t7, t8 = g.get("T7") or {}, (g.get("T8") or {}).get("1") or {}
    gar = {"total_assets": (t7.get("50") or {}).get("a"), "covered_assets": (t7.get("45") or {}).get("a"),
           "eligible": (t7.get("32") or {}).get("l"), "aligned": (t7.get("32") or {}).get("m"), "gar_stock_pct": t8.get("l")}
    t1 = next((r["values"] for r in p3_build(spec, "T1", assets)["rows"] if BINDING["T1"]["rows"][r["id"]] == "computed:total"), {}) if assets else {}
    # Template 5 has no total row: the sector rows (non-financial corporations) summed — collateral rows are another population
    from services.governance.pillar3_templates import stated_level
    level = stated_level(payload)
    t5: dict = {}
    for r in (p3_build(spec, "T5", assets, level)["rows"] if assets and level is not None else []):
        if not BINDING["T5"]["rows"][r["id"]].startswith("computed:collateral"):
            for k in ("sensitive", "h", "i", "j"):
                t5[k] = t5.get(k, 0.0) + (r["values"].get(k) or 0.0)
    from services.scoring.pcaf import gross_emissions
    ge = gross_emissions(assets)                      # a scope no exposure states has no total — its fact is not emitted
    s1, s2, s3 = ge["scope1"], ge["scope2"], ge["scope3"]

    binding = _load_p3_binding()
    ns = binding.get("namespace") or _P3_NS
    emap = binding.get("elements") or {}

    facts: list[str] = []

    ccy = presentation_of(payload)

    listed = set(p3esg_facts())

    def fact(name, unit, value, dec="2"):
        if name not in listed:
            raise ValueError(f"XBRL fact {name} is not in config/eba_p3esg_binding.json — add it there first")
        if value is None:
            return
        el = emap.get(name, name)  # official EBA element when bound, else our provisional local-name
        unit = f"u{ccy}" if unit == "uMONEY" else unit
        facts.append(f'  <p3:{el} contextRef="d0" unitRef="{unit}" decimals="{dec}">{_at(value, dec)}</p3:{el}>')

    # rollup + Template 5 physical risk
    fact("TotalBookValue", "uMONEY", rollup.get("total_value_eur"), dec="0")
    fact("PhysicalRiskSensitiveExposure", "uMONEY", t5.get("sensitive"), dec="0")
    fact("PhysicalRiskChronicOnlyExposure", "uMONEY", t5.get("h"), dec="0")
    fact("PhysicalRiskAcuteOnlyExposure", "uMONEY", t5.get("i"), dec="0")
    fact("PhysicalRiskChronicAndAcuteExposure", "uMONEY", t5.get("j"), dec="0")
    # Templates 6–8 Green Asset Ratio
    fact("GARTotalAssets", "uMONEY", gar.get("total_assets"), dec="0")
    fact("GARCoveredAssets", "uMONEY", gar.get("covered_assets"), dec="0")
    fact("GAREligibleExposure", "uMONEY", gar.get("eligible"), dec="0")
    fact("GARAlignedExposure", "uMONEY", gar.get("aligned"), dec="0")
    fact("GreenAssetRatioStockPct", "uPure", gar.get("gar_stock_pct"))
    # Template 1 financed emissions (Scope 1–3)
    fact("FinancedEmissionsScope1", "uCO2e", s1 or None, dec="0")
    fact("FinancedEmissionsScope2", "uCO2e", s2 or None, dec="0")
    fact("FinancedEmissionsScope3", "uCO2e", s3 or None, dec="0")
    fact("FinancedEmissionsTotal", "uCO2e", t1.get("i"), dec="0")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"',
        '            xmlns:iso4217="http://www.xbrl.org/2003/iso4217"',
        f'            xmlns:p3="{ns}">',
        f'  <!-- Pillar 3 ESG physical-risk & Taxonomy disclosure ({escape(_p3_act(payload))}) · {escape(who["name"])} · {escape(who["note"])} -->',
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
        f'  <xbrli:unit id="u{ccy}"><xbrli:measure>iso4217:{ccy}</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uPure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>',
        '  <xbrli:unit id="uCO2e"><xbrli:measure>p3:tCO2e</xbrli:measure></xbrli:unit>',
        *facts,
        '</xbrli:xbrl>',
    ]
    return "\n".join(lines)
