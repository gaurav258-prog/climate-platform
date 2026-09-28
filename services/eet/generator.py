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
from services.eet import rules as R

_NACE_CELLS = "{section}"   # placeholder in a rules stem that a NACE section letter fills


def _groups() -> dict[str, tuple]:
    """Holding groups each PAI applies to — the SFDR statement's own asset-class definitions, not a copy."""
    from ml.regulatory.sfdr_pai import REAL_ESTATE_ASSET_CLASSES, SOVEREIGN_ASSET_CLASSES
    return {"sovereigns": tuple(SOVEREIGN_ASSET_CLASSES), "real_estate": tuple(REAL_ESTATE_ASSET_CLASSES)}


def _eligible(comp: dict) -> dict[str, Optional[float]]:
    """Share of the fund's value each group of PAIs applies to; companies = everything neither sovereign nor property."""
    total = sum(v for v in comp.values() if isinstance(v, (int, float))) or 0.0
    if not total:
        return {"companies": None, "sovereigns": None, "real_estate": None}
    g = _groups()
    out = {k: sum(comp.get(c, 0) or 0 for c in cls) / total for k, cls in g.items()}
    out["companies"] = max(0.0, 1.0 - sum(out.values()))
    return out


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
    out = {"00010_EET_Version", "00050_EET_File_Generation_Date_And_Time", *R.use_flags().values(), "10000_Manufacturer_Name",
           "10010_Manufacturer_Code_Type", "10020_Manufacturer_Code", "10040_General_Reference_Date",
           "20000_Financial_Instrument_Identifying_Data", "20010_Financial_Instrument_Type_Of_Identification_Code",
           "20020_Financial_Instrument_Name", "20030_Financial_Instrument_Currency", "20040_Financial_Instrument_SFDR_Product_Type",
           "30010_PAI_Reference_Date", "70010_Financial_Instrument_Total_Fund_NAV_Or_Notional"}
    for spec in R.load()["pai_values"]:
        bases = ([spec["stem"].format(section=s) for s in spec["sections"]] if "sections" in spec else [spec["stem"]])
        for base in bases:
            base = base[:-len("_Value")] if base.endswith("_Value") else base
            for suffix in ("_Value", "_Coverage", "_Eligible_Assets"):
                if base + suffix in stems:
                    out.add(stems[base + suffix])
    for t in R.load()["taxonomy_values"]:
        out.update({t["incl_sovereign"], t["excl_sovereign"]})
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
    from services.reference import nace
    total = sum(r["mv"] or 0 for r in rows)
    sections = next((s["sections"] for s in R.load()["pai_values"] if "sections" in s), "")
    out = {k: 0.0 for k in sections}
    for r in rows:
        sec = nace.section(r["nace_code"])
        if sec in out and total:
            out[sec] += (r["mv"] or 0) / total
    return out


def _pai_fields(st: dict, nace_shares: Optional[dict] = None) -> tuple[dict, list[str]]:
    """PAI value / coverage / eligible-asset fields from one SFDR statement, as the version's rules map them."""
    stems, out, notes = _field_by_stem(), {}, []
    inds = {i["number"]: i for i in (st.get("indicators") or []) + (st.get("sovereign_indicators") or [])
            + (st.get("real_estate_indicators") or [])}
    eligible = _eligible(st.get("holdings_composition") or {})

    def put(base: str, value, coverage, elig) -> None:
        if value is not None and base + "_Value" in stems:
            out[stems[base + "_Value"]] = value
        if coverage is not None and base + "_Coverage" in stems:
            out[stems[base + "_Coverage"]] = coverage
        if elig is not None and base + "_Eligible_Assets" in stems:
            out[stems[base + "_Eligible_Assets"]] = elig

    for spec in R.load()["pai_values"]:
        if "read" in spec:                          # one statement figure → one EET field (+ coverage, eligible share)
            base, group = spec["stem"][:-len("_Value")], spec["holdings"]
            if eligible[group] == 0:                # e.g. no sovereign bonds: PAI 15-16 don't apply to this product
                put(base, None, 0.0, 0.0)
                continue
            v = R.read(spec, inds)
            if v is None:
                continue
            cov = (inds.get(spec["indicator"]) or {}).get("coverage_pct")
            put(base, v, cov / 100.0 if cov is not None else None, eligible[group])
            if spec.get("note"):
                notes.append(spec["note"])
            continue
        ind = inds.get(spec["indicator"]) or {}
        cells = ({s: (ind.get(spec["cells"]) or {}).get(s) for s in spec["sections"]} if "sections" in spec
                 else {None: ind.get(spec["cell"])})
        for sec, cell in cells.items():
            base = spec["stem"].format(section=sec) if sec else spec["stem"]
            if cell is None:
                share = (nace_shares or {}).get(sec) if sec else None   # a statement frozen before per-section figures
                if share is not None:
                    put(base, None, 0.0 if share == 0 else None, share)
                continue
            if not cell.get("eligible_pct"):
                put(base, None, 0.0, 0.0)
                continue
            scale = spec.get("scale", 1.0)
            put(base, cell["value"] * scale if cell.get("value") is not None else None,
                cell["coverage_pct"] / 100.0 if cell.get("value") is not None else None, cell["eligible_pct"] / 100.0)
            if cell.get("estimated_pct"):
                notes.append(f"{base.replace('_', ' ')}: {cell['estimated_pct']}% of fund value rests on estimates "
                             f"({'; '.join(cell.get('bases') or [])}).")
    return out, notes


def _code(name: str) -> int:
    return int(name.split("_", 1)[0])


def _taxonomy_fields(st: dict) -> dict:
    """Last-reported Taxonomy-aligned shares from the fund's own figures — company-reported turnover / CapEx alignment,
    value-weighted over ALL investments (so: including sovereigns); excluding sovereigns = the same aligned value over
    the non-sovereign part. OpEx is not computed (no company OpEx KPI held) and is left blank."""
    tx, comp = st.get("taxonomy") or {}, st.get("holdings_composition") or {}
    elig = _eligible(comp)
    non_sov = 1.0 - (elig["sovereigns"] or 0.0) if elig["sovereigns"] is not None else None
    out = {}
    for rule in R.load()["taxonomy_values"]:
        v = tx.get(rule["from"])
        if v is None or non_sov is None:
            continue
        out[rule["incl_sovereign"]] = v / 100.0
        if non_sov > 0:
            out[rule["excl_sovereign"]] = min(1.0, v / 100.0 / non_sov)
    return {k: v for k, v in out.items() if k in F.by_name()}


def _conditional_applies(name: str, sfdr: str, fund_type: Optional[str] = None, values: Optional[dict] = None,
                         uses: tuple = ()) -> Optional[bool]:
    """Whether a Conditional field applies to this row — from the version's rules file (each rule quotes the FinDatEx
    condition it encodes). None = depends on an answer not given yet: listed for a person to review."""
    return R.applies(name, {"sfdr": sfdr, "fund_type": fund_type, "values": values or {}, "uses": tuple(uses)})


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
              **{flag: ("Y" if u in uses else "N") for u, flag in R.use_flags().items()}}
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
                "20040_Financial_Instrument_SFDR_Product_Type": R.sfdr_code(c["sfdr_classification"]),
                "30010_PAI_Reference_Date": f"{ref_year}-12-31" if (frozen and ref_year) else general,
                "70010_Financial_Instrument_Total_Fund_NAV_Or_Notional": ent.get("total_value_eur"),
                **_taxonomy_fields(st),
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
        computed = {k: v for k, v in {**header, **pf["values"], **cls_vals}.items() if v is not None}
        # a figure from the book always wins; the manager's answer fills only what the book can't give
        row = {k: v for k, v in pf["answers"].items() if k not in computed}
        row.update({k: (F._num(float(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v))
                    for k, v in computed.items()})
        rows.append({"fund_id": c["fund_id"], "isin": c["isin"], "fund_type": c["fund_type"], "values": row,
                     "from_book": sorted(computed), "overridden_answers": sorted(k for k in pf["answers"] if k in computed)})
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
            applies = (_conditional_applies(f["name"], sfdr, r.get("fund_type"), r["values"], uses)
                       if level == "C" or f["name"].startswith(("20070_", "20080_")) else True)
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
                                                    "answerable": f["name"] not in r.get("from_book", ()), "isins": []})
                b["isins"].append(r["isin"])
    return {"n_rows": len(rows), "n_required": n_req, "n_filled": n_filled,
            "filled_pct": round(100 * n_filled / n_req, 1) if n_req else None,
            "n_blocking": len(blocking), "blocking": sorted(blocking.values(), key=lambda b: b["field"]),
            "n_to_review": len(review), "to_review": sorted(review)[:200],
            "n_data_checks": len(data_checks or []),
            "ready": bool(rows) and not blocking and not data_checks}
