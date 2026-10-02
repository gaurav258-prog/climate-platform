"""Machine-readable exports rendered from the FROZEN filing snapshot — never a live rebuild.

An attested/submitted filing must be downloadable in exactly the bytes that were frozen and signed off.
The older export endpoints (bank .xlsx, SFDR .xlsx) recompute from the LIVE engine, so a
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

    if fmt == "xlsx":                                  # the form as viewed: frozen figures with their audited overrides
        from services.governance.filings import form_view
        buf = _xlsx(filing["framework"], payload, ((form_view(session, org_id, filing_id) or {}).get("annex")))
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


def _summary_blocks(framework: str, payload: dict, annex: dict | None = None) -> list[dict]:
    """The official-form sections flattened into export blocks, so everything the annex shows — figures, columns and
    each section's note — also lands in the downloadable workbook. `annex` is the filing's form view annex (its merged
    datapoints: the frozen figures and any audited override); without it the annex is rebuilt from the payload alone,
    where a datapoint-bound cell renders '—'."""
    from services.governance.filing_annex import build_annex
    ann = annex if annex is not None else (build_annex(framework, {}, [], payload=payload) or {})
    blocks = []
    for sec in ann.get("sections", []):
        rows = []
        for row in sec.get("rows", []):
            if row.get("type") == "subheader":
                rows.append([row.get("label")])
            else:
                rows.append([_cell_text(c) for c in row.get("cells", [])])
        blocks.append({"title": sec.get("title", ""), "columns": sec.get("columns") or [], "rows": rows,
                       "note": sec.get("note")})
    return blocks


def _cur(headers: list[str], payload: dict) -> list[str]:
    """Column names say the currency the figures are in: value_eur → value_usd for a filing presented in USD."""
    c = presentation_of(payload).lower()
    return headers if c == "eur" else [h[:-4] + "_" + c if h.endswith("_eur") else (c if h == "eur" else h) for h in headers]


def _xlsx(framework: str, payload: dict, annex: dict | None = None) -> io.BytesIO:
    from services.templates.workbook import build_disclosure_workbook, build_export_workbook
    if framework == "bank_tcfd":                       # the frozen book as the templates read it, then the templates (E95)
        from services.governance.bank_taxonomy_report import XLSX_HEADERS, xlsx_rows
        return build_disclosure_workbook(_cur(XLSX_HEADERS, payload), xlsx_rows(payload),
                                         "EU Taxonomy Art. 8 — loan book", _summary_blocks(framework, payload, annex))
    if framework == "bank_p3esg":                      # the frozen book as the templates read it, then the templates (E97)
        from services.governance.pillar3_report import XLSX_HEADERS as P3_HEADERS
        from services.governance.pillar3_report import xlsx_rows as p3_rows
        return build_disclosure_workbook(_cur(P3_HEADERS, payload), p3_rows(payload), "Pillar 3 ESG — banking book",
                                         _summary_blocks(framework, payload, annex))
    if framework == "sfdr_pai":
        # the frozen indicator rows, then the statement as Annex I lays it out: Table 1 (impact, previous period,
        # explanation, actions), the other indicators and the sections of Articles 5 and 7-10
        headers = ["number", "area", "metric", "value", "unit", "coverage_pct", "input_required"]
        rows = []
        for i in payload.get("indicators", []):
            v = i.get("value")
            if isinstance(v, dict):
                v = v.get("total", v)
            rows.append([i.get("number"), i.get("area"), i.get("metric"), v,
                         i.get("unit"), i.get("coverage_pct"), i.get("input_required")])
        return build_disclosure_workbook(_cur(headers, payload), rows, "SFDR PAI · indicators",
                                         _summary_blocks(framework, payload, annex))
    if framework == "reit_tcfd":
        headers = ["property_name", "property_type", "country", "property_value_eur", "headline_score",
                   "risk_bucket", "taxonomy_status", "h3_cell"]
        rows = [[p.get("property_name"), p.get("property_type"), p.get("country"), p.get("property_value_eur"),
                 p.get("headline_score"), p.get("headline_bucket") or "unscored",
                 p.get("taxonomy_status"), p.get("h3_cell")] for p in payload.get("properties", [])]
        return build_disclosure_workbook(_cur(headers, payload), rows, "Property physical risk", _summary_blocks(framework, payload, annex))
    if framework == "insurer_climate":
        headers = ["policy_name", "region", "sum_insured_eur", "headline_score", "risk_bucket", "h3_cell"]
        rows = [[p.get("policy_name"), p.get("region"), p.get("sum_insured_eur"), p.get("headline_score"),
                 p.get("headline_bucket") or "unscored", p.get("h3_cell")] for p in payload.get("policies", [])]
        return build_disclosure_workbook(_cur(headers, payload), rows, "NatCat exposure disclosure", _summary_blocks(framework, payload, annex))
    if framework == "assetmgmt_tcfd":
        headers = ["holding_name", "sector", "country", "position_value_eur", "headline_score",
                   "risk_bucket", "taxonomy_status", "h3_cell"]
        rows = [[h.get("holding_name"), h.get("sector"), h.get("country"), h.get("position_value_eur"),
                 h.get("headline_score"), h.get("headline_bucket") or "unscored",
                 h.get("taxonomy_status"), h.get("h3_cell")] for h in payload.get("holdings", [])]
        return build_disclosure_workbook(_cur(headers, payload), rows, "Holdings physical risk", _summary_blocks(framework, payload, annex))
    if framework == "reit_taxonomy":
        # the property book with each building's EU Taxonomy verdict, then the Annex II templates as blocks
        from services.governance.taxonomy_nonfin import summary_of
        sm = summary_of(payload)
        headers = ["property_name", "turnover_eur", "noi_proxy", "activity", "aligned", "why"]
        rows = [[b["name"], b["turnover"], b["noi_proxy"], b["activity"],
                 {True: "aligned", False: "not aligned", None: "not determined"}[b["aligned"]] if b["activity"] else "not eligible",
                 b["why"]] for b in sm["buildings"]]
        return build_disclosure_workbook(_cur(headers, payload), rows, "EU Taxonomy Art. 8 — buildings",
                                         _summary_blocks(framework, payload, annex))
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
    if framework == "insurer_solvency":                # EIOPA's own taxonomy (services.governance.s2701_xbrl)
        from services.governance.s2701_xbrl import XbrlError, instance
        try:
            return instance(payload, _identity(session, org_id, entity_id))
        except XbrlError as e:
            raise ExportError(str(e)) from e
    # No XBRL for Pillar 3 ESG (E104): the EBA's own taxonomy (the Pillar 3 Data Hub DPM) is not bound, and an instance
    # under Tellumen-made element names is not a filing — as the EU Taxonomy report (E95) and the ESRS (E60). No XBRL for
    # SFDR PAI (E113): no official SFDR PAI taxonomy is held. Filings of every date are refused: the format is not
    # offered for the report type (filings.EXPORT_FORMATS).
    raise ExportError(f"no XBRL renderer for '{framework}'")


def _ixbrl(session: Session, org_id: str, framework: str, payload: dict, basis: dict) -> str:
    """No Inline XBRL for any report type: an ESRS statement is tagged with EFRAG's ESRS taxonomy, whose binding is not
    built (E60), and no official SFDR PAI taxonomy is held (E113). An instance under Tellumen-made names is not a filing."""
    raise ExportError(f"no iXBRL renderer for '{framework}'")
