"""Build the European ESG Template (EET) — one row per active share class, every field in FinDatEx order.

Where each value comes from (nothing is invented; an empty field stays empty and is reported):

  computed by Tellumen   data-set header, manufacturer identity (the manager's filing profile), the share class
                         (ISIN, name, currency), the SFDR article, fund NAV (EUR), and every principal-adverse-impact
                         figure with its coverage and eligible-asset share — from the fund's SFDR PAI statement: the
                         FILED statement for its reference year when there is one, else the live draft (said so).
  stated by the manager  everything Tellumen can't know (commitments, minimum proportions, exclusions, links):
                         org_eet_answers for manufacturer fields (codes below 20000), fund_eet_answers per fund.
                         A computed field can't be overridden by an answer.

Completeness is checked against the uses the file is for (SFDR entity / periodic / pre-contractual, MiFID, IDD):
a Mandatory field left empty BLOCKS publishing; a Conditional one is blocking only where its condition is known to
apply (Art. 8 fields on an Art. 8 product, Art. 9 on Art. 9, 20050 on a product outside SFDR), else listed to review.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.eet import fields as F

SFDR_TYPE = {"article_6": "6", "article_8": "8", "article_8_plus": "8", "article_9": "9"}

# PAI value fields (name without the numeric code) → (indicator number, how to read the value, holding group)
_PAI = {
    "GHG_Emissions_Scope_1_Value": (1, lambda v, i: _k(v, "scope_1"), "companies"),
    "GHG_Emissions_Scope_2_Value": (1, lambda v, i: _k(v, "scope_2"), "companies"),
    "GHG_Emissions_Scope_3_Value": (1, lambda v, i: _k(v, "scope_3"), "companies"),
    "GHG_Emissions_Total_Scope12_Value": (1, lambda v, i: _sum(v, "scope_1", "scope_2"), "companies"),
    "GHG_Emissions_Total_Scope123_Value": (1, lambda v, i: _k(v, "total"), "companies"),
    "Carbon_Footprint_Scope123_Value": (2, lambda v, i: v, "companies"),
    "GHG_Intensity_Of_Investee_Companies_Scope12_Value": (3, lambda v, i: i.get("value_scope_1_2"), "companies"),
    "GHG_Intensity_Of_Investee_Companies_Scope123_Value": (3, lambda v, i: v, "companies"),
    "Exposure_To_Companies_Active_In_The_Fossil_Fuel_Sector_Value": (4, lambda v, i: _pct(v), "companies"),
    "Activities_Negatively_Affecting_Biodiversity-sensitive_Areas_Value": (7, lambda v, i: _pct(v), "companies"),
    "Water_Emissions_Value": (8, lambda v, i: v, "companies"),
    "Hazardous_Waste_Ratio_Value": (9, lambda v, i: v, "companies"),
    "Share_Of_Companies_Involved_In_Violation_Of_UN_Global_Compact_Principles_And_OECD_Guidelines_For_Multinational_Enterprises_Value": (10, lambda v, i: _pct(v), "companies"),
    "Share_Of_Companies_Without_Policies_To_Monitor_Compliance_With_UNGCP_And_OECD_Guidelines_For_Multinational_Enterprises_Value": (11, lambda v, i: _pct(v), "companies"),
    "Unadjusted_Gender_Pay_Gap_Value": (12, lambda v, i: _pct(v), "companies"),
    "Board_Gender_Diversity_Value": (13, lambda v, i: _pct(v), "companies"),
    "Share_Of_Investments_Involved_In_Controversial_Weapons_Value": (14, lambda v, i: _pct(v), "companies"),
    "GHG_Intensity_Value": (15, lambda v, i: v, "sovereigns"),
    "Number_Of_Countries_Subject_To_Social_Violations_Value": (16, lambda v, i: v, "sovereigns"),
    "Exposure_To_Fossil_Fuels_Extraction_Storage_Transport_Manufacture_Value": (17, lambda v, i: _pct(v), "real_estate"),
    "Exposure_To_Energy-inefficient_Real_Estate_Assets_Value": (18, lambda v, i: _pct(v), "real_estate"),
}
_GROUPS = {"companies": ("equity", "corporate_bond"), "sovereigns": ("sovereign_bond",), "real_estate": ("real_estate",)}
# PAI 6 — energy consumption intensity per high-impact climate sector: the NACE section each EET field is for
NACE_SECTIONS = {"A": range(1, 4), "B": range(5, 10), "C": range(10, 34), "D": range(35, 36), "E": range(36, 40),
                 "F": range(41, 44), "G": range(45, 48), "H": range(49, 54), "L": range(68, 69), "M": range(69, 76)}
_NACE_STEM = "Energy_Consumption_Intensity_Per_High_Impact_Climate_Sector_NACE_{}"
NOTES = {
    "Carbon_Footprint_Scope12_Value": "Scope 1+2 footprint = the Scope 1+2+3 footprint × (Scope 1+2 ÷ total) financed emissions.",
}


def _k(v, key):
    return v.get(key) if isinstance(v, dict) else None


def _sum(v, *keys):
    vals = [_k(v, k) for k in keys]
    return sum(vals) if all(x is not None for x in vals) else None


def _pct(v):
    return v / 100.0 if isinstance(v, (int, float)) else None


def _strip(name: str) -> str:
    return name.split("_", 1)[1]


def _field_by_stem() -> "_Stems":
    return _Stems({_strip(f["name"]).lower(): f["name"] for f in F.fields()})


class _Stems(dict):
    """Field name by its name-without-code, case-insensitively — FinDatEx's own list spells some siblings
    differently ('Share_Of_Companies…_Value' but 'Share_of_Companies…_Coverage')."""
    def __getitem__(self, k):
        return dict.__getitem__(self, k.lower())

    def __contains__(self, k):
        return dict.__contains__(self, str(k).lower())


def computed_names() -> set[str]:
    """Every field Tellumen fills itself — an answer can't override these."""
    stems = _field_by_stem()
    out = {"00010_EET_Version", "00050_EET_File_Generation_Date_And_Time", *F.USE_FLAG.values(), "10000_Manufacturer_Name",
           "10010_Manufacturer_Code_Type", "10020_Manufacturer_Code", "10040_General_Reference_Date",
           "20000_Financial_Instrument_Identifying_Data", "20010_Financial_Instrument_Type_Of_Identification_Code",
           "20020_Financial_Instrument_Name", "20030_Financial_Instrument_Currency", "20040_Financial_Instrument_SFDR_Product_Type",
           "30010_PAI_Reference_Date", "70010_Financial_Instrument_Total_Fund_NAV_Or_Notional"}
    for stem in list(_PAI) + ["Carbon_Footprint_Scope12_Value"]:
        base = stem[:-len("_Value")]
        for suffix in ("_Value", "_Coverage", "_Eligible_Assets"):
            if base + suffix in stems:
                out.add(stems[base + suffix])
    return out & set(F.by_name())


def _answers(session: Session, org_id: str, fund_id: str) -> dict[str, str]:
    org = dict(session.execute(text("SELECT field_name, value FROM org_eet_answers WHERE org_id = CAST(:o AS uuid)"),
                               {"o": org_id}).all())
    fund = dict(session.execute(text("SELECT field_name, value FROM fund_eet_answers WHERE fund_id = CAST(:f AS uuid)"),
                                {"f": fund_id}).all())
    return {**org, **fund}


def _na(stems, out: dict, base: str) -> None:
    """An indicator the product has nothing to report on (no holdings of that kind): 0% eligible, 0% covered."""
    for suffix in ("_Coverage", "_Eligible_Assets"):
        if base + suffix in stems:
            out[stems[base + suffix]] = 0.0


def _nace_shares(session: Session, fund_id: str) -> dict[str, float]:
    """Share of the fund's value (latest holdings) in each high-impact NACE section, from the issuers' NACE codes."""
    from services.asset_manager_engine import fund_descendant_ids
    rows = session.execute(text("""
        SELECT i.nace_code, CAST(p.market_value_eur AS FLOAT) AS mv
        FROM fund_positions p JOIN securities s ON s.security_id = p.security_id JOIN issuers i ON i.issuer_id = s.issuer_id
        WHERE p.fund_id = ANY(:f) AND p.as_of_date = (SELECT MAX(as_of_date) FROM fund_positions WHERE fund_id = p.fund_id)
    """), {"f": fund_descendant_ids(session, fund_id)}).mappings().all()
    total = sum(r["mv"] or 0 for r in rows)
    out = {k: 0.0 for k in NACE_SECTIONS}
    for r in rows:
        try:
            div = int(str(r["nace_code"] or "").strip()[:2])
        except ValueError:
            continue
        for sec, rng in NACE_SECTIONS.items():
            if div in rng:
                out[sec] += (r["mv"] or 0) / total if total else 0
    return out


def _pai_fields(st: dict, nace: Optional[dict] = None) -> tuple[dict, list[str]]:
    """PAI value / coverage / eligible-asset fields from one SFDR statement."""
    stems, out, notes = _field_by_stem(), {}, []
    inds = {i["number"]: i for i in (st.get("indicators") or []) + (st.get("sovereign_indicators") or [])
            + (st.get("real_estate_indicators") or [])}
    comp = st.get("holdings_composition") or {}
    total = sum(v for v in comp.values() if isinstance(v, (int, float))) or 0.0
    eligible = {g: (sum(comp.get(c, 0) or 0 for c in cls) / total if total else None) for g, cls in _GROUPS.items()}
    footprint_parts = None
    for stem, (num, read, group) in _PAI.items():
        if eligible[group] == 0:                 # e.g. no sovereign bonds: PAI 15-16 don't apply to this product
            _na(stems, out, stem[:-len("_Value")])
            continue
        ind = inds.get(num)
        if not ind or ind.get("value") is None or ind.get("method") == "not_applicable":
            continue
        v = read(ind["value"], ind)
        if v is None:
            continue
        base = stem[:-len("_Value")]
        out[stems[stem]] = v
        if ind.get("coverage_pct") is not None and base + "_Coverage" in stems:
            out[stems[base + "_Coverage"]] = ind["coverage_pct"] / 100.0
        if eligible[group] is not None and base + "_Eligible_Assets" in stems:
            out[stems[base + "_Eligible_Assets"]] = eligible[group]
        if num == 1:
            footprint_parts = ind["value"]
        if stem in NOTES:
            notes.append(NOTES[stem])
    # PAI 5 split and PAI 6 per section, as the statement carries them (reported → vendor → estimated per company)
    split = {"Share_Energy_Consumption_From_Non-Renewable_Sources": ((inds.get(5) or {}).get("consumption"), True),
             "Share_Energy_Production_From_Non-Renewable_Sources": ((inds.get(5) or {}).get("production"), True)}
    by_sec = (inds.get(6) or {}).get("by_section") or {}
    split.update({_NACE_STEM.format(s): (cell, False) for s, cell in by_sec.items()})
    for base, (cell, is_pct) in split.items():
        if not cell or base + "_Value" not in stems:
            continue
        if not cell.get("eligible_pct"):
            _na(stems, out, base)
            continue
        if cell.get("value") is not None:
            out[stems[base + "_Value"]] = cell["value"] / 100.0 if is_pct else cell["value"]
            out[stems[base + "_Coverage"]] = cell["coverage_pct"] / 100.0
        out[stems[base + "_Eligible_Assets"]] = cell["eligible_pct"] / 100.0
        if cell.get("estimated_pct"):
            notes.append(f"{base.replace('_', ' ')}: {cell['estimated_pct']}% of fund value rests on estimates "
                         f"({'; '.join(cell.get('bases') or [])}).")
    for sec, share in ({} if by_sec else (nace or {})).items():   # statements frozen before per-section figures
        base = _NACE_STEM.format(sec)
        if base + "_Value" not in stems:
            continue
        if share == 0:
            _na(stems, out, base)
        else:                                    # the value needs issuer energy data per sector; eligibility is known
            out[stems[base + "_Eligible_Assets"]] = share
    for base in ("GHG_Intensity", "Number_Of_Countries_Subject_To_Social_Violations", "Percent_Of_Countries_Subject_To_Social_Violations"):
        if eligible["sovereigns"] == 0:
            _na(stems, out, base)
    fp = inds.get(2)
    if fp and fp.get("value") is not None and footprint_parts and _k(footprint_parts, "total"):
        s12 = _sum(footprint_parts, "scope_1", "scope_2")
        if s12 is not None:
            out[stems["Carbon_Footprint_Scope12_Value"]] = fp["value"] * s12 / footprint_parts["total"]
            if fp.get("coverage_pct") is not None:
                out[stems["Carbon_Footprint_Scope12_Coverage"]] = fp["coverage_pct"] / 100.0
            if eligible["companies"] is not None:
                out[stems["Carbon_Footprint_Scope12_Eligible_Assets"]] = eligible["companies"]
            notes.append(NOTES["Carbon_Footprint_Scope12_Value"])
    return out, notes


def _conditional_applies(name: str, sfdr: str, fund_type: Optional[str] = None) -> Optional[bool]:
    if name.startswith(("20070_", "20080_")):             # look-through share of Art 8 / 9 sub-funds: funds of funds only
        return fund_type == "fund_of_funds" and sfdr in ("8", "9")
    if "_Art_8" in name:
        return sfdr == "8"
    if "_Art_9" in name:
        return sfdr == "9"
    if name.startswith("20050_"):
        return sfdr == "0"
    return None                                             # condition not evaluated here: a person reviews it


def build(session: Session, org_id: str, uses: tuple[str, ...], fund_ids: Optional[list[str]] = None) -> dict:
    from ml.regulatory.sfdr_pai import frozen_or_live_statement
    from services.fund_disclosure import fund_esg_pai  # company figures that look like unit slips
    uses = tuple(u for u in F.USES if u in uses) or ("entity",)
    now = datetime.now(timezone.utc)
    classes = session.execute(text("""
        SELECT c.fund_id::text AS fund_id, c.isin, c.name, c.currency, f.sfdr_classification, f.fund_type,
               (SELECT MAX(as_of_date) FROM fund_positions p WHERE p.fund_id = c.fund_id) AS as_of
        FROM fund_share_classes c JOIN funds f ON f.fund_id = c.fund_id
        WHERE c.org_id = CAST(:o AS uuid) AND c.status = 'active' AND (CAST(:f AS uuid[]) IS NULL OR c.fund_id = ANY(CAST(:f AS uuid[])))
        ORDER BY f.name, c.name
    """), {"o": org_id, "f": fund_ids}).mappings().all()
    header = {"00010_EET_Version": F.version(), "00050_EET_File_Generation_Date_And_Time": now.strftime("%Y-%m-%d %H:%M:%S"),
              **{flag: ("Y" if u in uses else "N") for u, flag in F.USE_FLAG.items()}}
    rows, per_fund, notes, checks = [], {}, set(), []
    for c in classes:
        if c["fund_id"] not in per_fund:
            st, frozen = frozen_or_live_statement(session, c["fund_id"])
            ent = st.get("entity") or {}
            pai, pnotes = ({}, []) if st.get("error") else _pai_fields(st, _nace_shares(session, c["fund_id"]))
            notes.update(pnotes)
            ref_year = (st.get("summary") or {}).get("reference_year")
            general = c["as_of"].isoformat() if c["as_of"] else None
            fund_vals = {
                "10000_Manufacturer_Name": ent.get("manager_legal_name") or ent.get("manager"),
                "10010_Manufacturer_Code_Type": "L" if ent.get("manager_lei") else "N",
                "10020_Manufacturer_Code": ent.get("manager_lei"),
                "10040_General_Reference_Date": general,
                "20040_Financial_Instrument_SFDR_Product_Type": SFDR_TYPE.get(c["sfdr_classification"] or "", "0"),
                "30010_PAI_Reference_Date": f"{ref_year}-12-31" if (frozen and ref_year) else general,
                "70010_Financial_Instrument_Total_Fund_NAV_Or_Notional": ent.get("total_value_eur"),
                **pai,
            }
            checks += [{**o, "fund_id": c["fund_id"], "fund_name": ent.get("fund_name")}
                       for o in (fund_esg_pai(session, c["fund_id"]) or {}).get("energy_outliers", [])]
            per_fund[c["fund_id"]] = {"values": fund_vals, "answers": _answers(session, org_id, c["fund_id"]),
                                      "statement": "filed" if frozen else "live draft",
                                      "reference_year": ref_year, "fund_name": ent.get("fund_name")}
        pf = per_fund[c["fund_id"]]
        cls_vals = {"20000_Financial_Instrument_Identifying_Data": c["isin"],
                    "20010_Financial_Instrument_Type_Of_Identification_Code": "1",
                    "20020_Financial_Instrument_Name": c["name"], "20030_Financial_Instrument_Currency": c["currency"]}
        computed = {**header, **pf["values"], **cls_vals}
        row = {k: v for k, v in pf["answers"].items() if k not in computed}
        row.update({k: (F._num(float(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v))
                    for k, v in computed.items() if v is not None})
        rows.append({"fund_id": c["fund_id"], "isin": c["isin"], "fund_type": c["fund_type"], "values": row})
    return {"eet_version": F.version(), "uses": list(uses), "generated_at": now.isoformat(),
            "field_names": [f["name"] for f in F.fields()], "rows": rows,
            "funds": {k: {kk: v[kk] for kk in ("statement", "reference_year", "fund_name")} for k, v in per_fund.items()},
            "notes": sorted(notes), "data_checks": checks, "completeness": completeness(rows, uses, checks)}


def _not_applicable(values: dict, name: str) -> bool:
    """A PAI value whose eligible-asset share is 0 (e.g. sovereign intensity for a fund with no sovereign bonds)."""
    if not name.endswith("_Value"):
        return False
    stems = _field_by_stem()
    base = _strip(name)[:-len("_Value")]
    el = stems.get((base + "_Eligible_Assets").lower())
    return bool(el) and values.get(el) == "0"


def completeness(rows: list[dict], uses: tuple[str, ...], data_checks: Optional[list] = None) -> dict:
    blocking: dict[str, dict] = {}
    review: dict[str, int] = {}
    n_req = n_filled = 0
    for r in rows:
        sfdr = r["values"].get("20040_Financial_Instrument_SFDR_Product_Type", "0")
        for f in F.fields():
            level = F.requirement(f, uses)
            if level not in ("M", "C"):
                continue
            filled = bool(r["values"].get(f["name"]))
            if not filled and _not_applicable(r["values"], f["name"]):
                continue                                  # the product holds nothing this indicator is about
            applies = _conditional_applies(f["name"], sfdr, r.get("fund_type")) if level == "C" or f["name"].startswith(("20070_", "20080_")) else True
            if applies is False:
                continue
            if applies is None:
                if not filled:
                    review[f["name"]] = review.get(f["name"], 0) + 1
                continue
            n_req += 1
            n_filled += filled
            if not filled:
                b = blocking.setdefault(f["name"], {"field": f["name"], "section": f["section"], "definition": f["definition"],
                                                    "codification": (f["codification"] or "").split("\n")[0],
                                                    "answerable": f["name"] not in computed_names(), "isins": []})
                b["isins"].append(r["isin"])
    return {"n_rows": len(rows), "n_required": n_req, "n_filled": n_filled,
            "filled_pct": round(100 * n_filled / n_req, 1) if n_req else None,
            "n_blocking": len(blocking), "blocking": sorted(blocking.values(), key=lambda b: b["field"]),
            "n_to_review": len(review), "to_review": sorted(review)[:200],
            "n_data_checks": len(data_checks or []),
            "ready": bool(rows) and not blocking and not data_checks}
