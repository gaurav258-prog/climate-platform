"""S.27.01.01 (ITS (EU) 2023/894, Annex I; instructions Annex II S.27.01) — the natural-catastrophe part, filled cell by
cell from the standard-formula result (services.governance.solvency2_natcat) and the undertaking's supplied premiums.

The rows, columns and instructions are the specification's (data/reference/regspec/sii_qrt_natcat); nothing about the
template is typed here except the binding: what fills each row and column, and which of our regions each printed
region row is. A cell is reportable when an Annex II instruction names it (its ref 'Cxxxx/Ryyyy[–Rzzzz]'); every
other cell of a block is greyed. coverage() checks the binding against every adopted version of the spec.
"""
from __future__ import annotations

import re

FAMILY = "sii_qrt_natcat"
TID = "S2701"
PERILS = ("windstorm", "earthquake", "flood", "hail", "subsidence")
_SECTION = {"windstorm": "Windstorm", "earthquake": "Earthquake", "flood": "Flood", "hail": "Hail", "subsidence": "Subsidence"}

# our region code (the Annex V-VIII tables) → the region row as printed in the peril's block
REGION_ROW = {
    "windstorm": {"AT": "R0400", "BE": "R0410", "CZ": "R0420", "CH": "R0430", "DK": "R0440", "SI": "R0441", "FR": "R0450",
                  "DE": "R0460", "HU": "R0461", "IS": "R0470", "IE": "R0480", "LU": "R0490", "NL": "R0500", "NO": "R0510",
                  "PL": "R0520", "FI": "R0521", "ES": "R0530", "SE": "R0540", "UK": "R0550", "GU": "R0560", "MA": "R0570",
                  "SM": "R0580", "RE": "R0590"},
    "earthquake": {"AT": "R0830", "BE": "R0840", "BG": "R0850", "CR": "R0860", "CY": "R0870", "CZ": "R0880", "CH": "R0890",
                   "FR": "R0900", "DE": "R0910", "HE": "R0920", "HU": "R0930", "IT": "R0940", "MT": "R0950", "PT": "R0960",
                   "RO": "R0970", "SK": "R0980", "SI": "R0990", "GU": "R1000", "MA": "R1010", "SM": "R1020"},
    "flood": {"AT": "R1260", "BE": "R1270", "BG": "R1280", "CZ": "R1290", "CH": "R1300", "FR": "R1310", "DE": "R1320",
              "HU": "R1330", "IT": "R1340", "PL": "R1350", "RO": "R1360", "SK": "R1370", "SI": "R1380", "UK": "R1390"},
    "hail": {"AT": "R1630", "BE": "R1640", "CZ": "R1641", "CH": "R1650", "FR": "R1660", "DE": "R1670", "IT": "R1680",
             "LU": "R1690", "NL": "R1700", "SI": "R1701", "ES": "R1710"},
}
# a column's role, by its printed label
_COL_ROLE = {"Estimation of the gross premiums to be earned": "premium", "Exposure": "exposure",
             "Specified Gross Loss": "loss", "Catastrophe Risk Charge Factor before risk mitigation": "factor",
             "Scenario A or B": "scenario", "Catastrophe Risk Charge before risk mitigation": "before",
             "Estimated Risk Mitigation": "mitigation", "Estimated Reinstatement Premiums": "reinstatement",
             "Catastrophe Risk Charge after risk mitigation": "after",
             "SCR before risk mitigation": "before", "Total risk mitigation": "mitigation",
             "SCR after risk mitigation": "after", "Simplifications used": "simplification"}
_INPUT_ROLES = {"premium"}


def _peril_of(section: str) -> str | None:
    return next((p for p, s in _SECTION.items() if section.rstrip().endswith(s)), None)


def _row_role(label: str) -> str:
    low = label.lower()
    if low.startswith("total") and "specified regions" in low:
        return "total_specified"
    if low.startswith("total") and "other regions" in low:
        return "total_other"
    if low.startswith("total") and "all regions" in low:
        return "total_all"
    if low.startswith("diversification effect"):
        return "diversification"
    if low.startswith("total") and "after diversification" in low:
        return "total_after"
    if low.startswith("total") and "before diversification" in low:     # subsidence: one territory
        return "total_specified"
    return "region"


def binding(spec: dict) -> dict:
    """{TID: {"rows": {row: source}, "columns": {col: source}}} — every row and column of the spec mapped."""
    from services.regspec import template
    t = template(spec, TID)
    annex3 = _annex_iii_names()
    ours = {r for m in REGION_ROW.values() for r in m.values()}
    rows = {}
    for r in t["rows"]:
        peril = _peril_of(r["section"])
        if r["id"] == "R0002":
            rows[r["id"]] = "computed:simplification"
        elif peril is None:
            rows[r["id"]] = "computed:summary"
        elif r["id"] in ours:
            rows[r["id"]] = "computed:region"
        elif r["label"] in annex3:
            rows[r["id"]] = "input:other_region"              # its premium is supplied; the charge is on the total row
        elif _row_role(r["label"]) != "region" or peril == "subsidence":
            rows[r["id"]] = f"computed:{_row_role(r['label'])}"
        else:
            rows[r["id"]] = "n/a"                             # a printed region with no table in the version in force
    cols = {c["id"]: ("input:premium|EUR" if _COL_ROLE.get(c["label"]) in _INPUT_ROLES else f"computed:{_COL_ROLE.get(c['label'], '?')}")
            for c in t["columns"]}
    return {TID: {"rows": rows, "columns": cols}}


def _annex_iii_names() -> list[str]:
    from services.governance.solvency2_natcat_tables import rules
    return [r["name"] for r in rules()["other_regions"]["annex_iii_regions"]["regions"]]


def other_region_rows(spec: dict) -> dict[str, dict[int, str]]:
    """{peril: {Annex III region number: row id}} — the other-region rows of each peril block, by printed name."""
    from services.regspec import template
    t = template(spec, TID)
    names = _annex_iii_names()
    out: dict[str, dict[int, str]] = {}
    for r in t["rows"]:
        p = _peril_of(r["section"])
        if p and r["label"] in names:
            out.setdefault(p, {})[names.index(r["label"]) + 1] = r["id"]
    return out


def premium_column(spec: dict) -> dict[str, str]:
    """{peril: the column of its block that holds the premiums to be earned}."""
    from services.regspec import template
    return {p: c["id"] for c in template(spec, TID)["columns"] for p in PERILS
            if _peril_of(c["section"]) == p and _COL_ROLE.get(c["label"]) == "premium"}


def reportable(spec: dict) -> set[tuple[str, str]]:
    """Every (row, column) an Annex II instruction names; the rest of each block is greyed."""
    from services.regspec import template
    t = template(spec, TID)
    order = [r["id"] for r in t["rows"]]
    cells = set()
    for ins in t.get("instructions") or []:
        ref = ins["ref"].strip()
        m = re.fullmatch(r"(C\d{4})/(R\d{4})(?:\s*[–-]\s*(R\d{4}))?", ref)
        if m:
            col, a, b = m.group(1), m.group(2), m.group(3) or m.group(2)
        elif (m := re.fullmatch(r"(R\d{4})/(C\d{4})", ref)):                  # printed row first
            col, a, b = m.group(2), m.group(1), m.group(1)
        else:
            continue
        if a in order and b in order:
            cells |= {(r, col) for r in order[order.index(a): order.index(b) + 1]}
    return cells


def grid(spec: dict, sf: dict, supplied: dict | None = None) -> dict[str, dict[str, object]]:
    """{row: {column: value}} for every reportable cell the standard-formula result or the supplied premiums fill.
    A reportable cell with nothing to report is absent (shown blank); supplied premiums are shown as supplied."""
    from services.regspec import template
    t = template(spec, TID)
    cols_by_peril: dict[str, dict[str, str]] = {}
    summary_cols: dict[str, str] = {}
    for c in t["columns"]:
        p, role = _peril_of(c["section"]), _COL_ROLE.get(c["label"])
        if p:
            cols_by_peril.setdefault(p, {})[role] = c["id"]
        elif role:
            summary_cols[role] = c["id"]
    ok = reportable(spec)
    out: dict[str, dict[str, object]] = {}

    def put(row: str, col: str | None, v) -> None:
        if col and v is not None and (row, col) in ok:
            out.setdefault(row, {})[col] = v

    put("R0002", summary_cols.get("simplification"), simplification_codes(spec, sf))
    perils = sf.get("perils") or {}
    summary_row = {p: next(r["id"] for r in t["rows"] if _peril_of(r["section"]) is None and r["label"] == _SECTION[p])
                   for p in PERILS}
    for p, pr in perils.items():
        if not pr.get("available"):
            continue
        b, a = pr["before_eur"], pr["after_eur"]
        for role, v in (("before", b), ("mitigation", b - a), ("after", a)):
            put(summary_row[p], summary_cols.get(role), v)
    bef, aft = sf.get("natcat_scr_before_mitigation_eur"), sf.get("natcat_scr_eur")
    for role, v in (("before", bef), ("mitigation", None if bef is None else bef - aft), ("after", aft)):
        put("R0010", summary_cols.get(role), v)
    div_b, div_a = sf.get("diversification_between_perils_before_eur"), sf.get("diversification_between_perils_after_eur")
    for role, v in (("before", -div_b if div_b is not None else None), ("after", -div_a if div_a is not None else None),
                    ("mitigation", None if div_b is None else -(div_b - div_a))):
        put("R0070", summary_cols.get(role), v)

    other_rows = other_region_rows(spec)
    for p, pr in perils.items():
        cols = cols_by_peril.get(p, {})
        rows_of = [r for r in t["rows"] if _peril_of(r["section"]) == p]
        role_row = {_row_role(r["label"]): r["id"] for r in rows_of if _row_role(r["label"]) != "region"}
        if not pr.get("available"):
            continue
        if p == "subsidence":                       # one territory, France: zones before / after their diversification
            fr = next((g for g in pr["regions"] if g["region"] == "FR"), None)
            u = pr.get("before_zone_diversification")
            if fr and u:
                r1950 = role_row.get("total_specified", "")
                for role, v in (("exposure", fr["exposure_eur"]), ("loss", u["specified_gross_loss_eur"]),
                                ("factor", round(u["specified_gross_loss_eur"] / fr["exposure_eur"], 6) if fr["exposure_eur"] else None),
                                ("before", u["before_eur"]), ("mitigation", u["mitigation_eur"]),
                                ("reinstatement", u["reinstatement_eur"]), ("after", u["after_eur"])):
                    put(r1950, cols.get(role), v)
                put(role_row.get("diversification", ""), cols.get("before"), fr["before_eur"] - u["before_eur"])
                put(role_row.get("diversification", ""), cols.get("after"), fr["after_eur"] - u["after_eur"])
                put(role_row.get("total_after", ""), cols.get("before"), fr["before_eur"])
                put(role_row.get("total_after", ""), cols.get("after"), fr["after_eur"])
            continue
        for code, g in {g["region"]: g for g in pr["regions"]}.items():
            row = REGION_ROW.get(p, {}).get(code)
            if row is None:
                continue
            for role in ("exposure", "loss", "factor", "scenario", "before", "mitigation", "reinstatement", "after"):
                v = {"exposure": g["exposure_eur"], "loss": g["specified_gross_loss_eur"], "factor": g["charge_factor"],
                     "scenario": g["scenario"], "before": g["before_eur"], "mitigation": g["mitigation_eur"],
                     "reinstatement": g["reinstatement_eur"], "after": g["after_eur"]}[role]
                put(row, cols.get(role), v)
        spec_sum = {k: sum(g[f] for g in pr["regions"]) for k, f in (
            ("exposure", "exposure_eur"), ("loss", "specified_gross_loss_eur"), ("before", "before_eur"),
            ("mitigation", "mitigation_eur"), ("reinstatement", "reinstatement_eur"), ("after", "after_eur"))}
        if spec_sum["exposure"]:
            spec_sum["factor"] = round(spec_sum["loss"] / spec_sum["exposure"], 6)
        for role, v in spec_sum.items():
            put(role_row.get("total_specified", ""), cols.get(role), v)
        o = pr.get("other_regions") or {}
        for n, row in other_rows.get(p, {}).items():
            put(row, cols.get("premium"), (o.get("premium_by_region") or {}).get(n))
        tot_o = role_row.get("total_other", "")
        put(tot_o, cols.get("premium"), o.get("premium_eur"))
        for role in ("before", "mitigation", "reinstatement", "after"):
            put(tot_o, cols.get(role), o.get(f"{role}_eur"))
        for role in ("before", "mitigation", "reinstatement", "after"):
            v = spec_sum.get(role, 0) + (o.get(f"{role}_eur") or 0)
            put(role_row.get("total_all", ""), cols.get(role), v)
        put(role_row.get("diversification", ""), cols.get("before"), -pr["diversification_before_eur"])
        put(role_row.get("diversification", ""), cols.get("after"), -pr["diversification_after_eur"])
        put(role_row.get("total_after", ""), cols.get("before"), pr["before_eur"])
        put(role_row.get("total_after", ""), cols.get("after"), pr["after_eur"])
    for key, v in (supplied or {}).items():                       # premiums as supplied, shown whatever the engine used
        tid, _, rest = key.partition(".")
        row, _, col = rest.partition(".")
        if tid == TID and (row, col) in ok:
            out.setdefault(row, {})[col] = v
    return out


def simplification_codes(spec: dict, sf: dict) -> str:
    """R0002/C0001 as the instruction's options: the Art. 90b option of each peril where a region was grouped, else
    'Simplifications not used' ('Options 1 to 5 may be used simultaneously')."""
    from services.regspec import template
    ins = next(i for i in template(spec, TID)["instructions"] if i["ref"] == "R0002/C0001")
    by_peril = {o.split(" – ")[0]: o for o in ins["options"]}
    code = {p: str(n) for n, p in enumerate(PERILS, 1)}
    used = [code[p] for p, pr in (sf.get("perils") or {}).items() if pr.get("available")
            and any(g["method"] == "grouped_art90b" for g in pr.get("regions") or [])]
    if not used:
        return next(o for o in ins["options"] if o.startswith("9"))
    assert all(by_peril[c].endswith(PERILS[int(c) - 1]) for c in used)   # the option names the peril it stands for
    return "; ".join(by_peril[c] for c in sorted(used, key=int))


def unrepresented(sf: dict) -> list[str]:
    """Regions of the version in force that the template prints no row for (added by 2026/269 after ITS 2023/894)."""
    out = []
    for p, pr in (sf.get("perils") or {}).items():
        for g in pr.get("regions") or []:
            if p != "subsidence" and g["region"] not in REGION_ROW.get(p, {}):
                out.append(f"{_SECTION[p]} {g['region']}")
            elif p == "subsidence" and g["region"] != "FR":
                out.append(f"Subsidence {g['region']}")
    return out


def premiums_from_supplied(spec: dict, supplied: dict) -> dict[str, dict]:
    """{peril: {"by_region": {Annex III region: premium}}} from supplied cells {'S2701.<row>.<col>': value} — the
    premiums to be earned the undertaking states on the other-region rows (regions outside Annex XIII)."""
    rows, col = other_region_rows(spec), premium_column(spec)
    out: dict[str, dict] = {}
    for p, by_n in rows.items():
        got = {n: float(supplied[f"{TID}.{row}.{col[p]}"]) for n, row in by_n.items()
               if supplied.get(f"{TID}.{row}.{col[p]}") is not None}
        out[p] = {"by_region": got}
    return out
