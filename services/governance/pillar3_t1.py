"""Pillar 3 ESG Template 1, columns i, j and k — the financed emissions and the share derived from company reporting,
to the instructions (Annex XL, the same wording under ITS 2022/2453 and ITS 2024/3172; quoted in
data/reference/pillar3/t1_financed_emissions.json, every quote checked against the stored text by
tests/unit/test_t1_financed_emissions.py).

What the instructions leave to the institution is its own statement — governed methodology switches (services.calc_settings,
four eyes where the organisation requires it, stamped on every filing), with no default:
  p3esg_t1_emissions_estimation   which counterparty emissions it estimates: scopes 1-3; scopes 1 and 2 (column j left
                                  blank, as the instructions say); or not yet (columns i and j blank, the plans narrated)
  p3esg_t1_attribution            how a counterparty's emissions are attributed to the exposure: the exposure compared to
                                  the counterparty's total liabilities (accounting liabilities and shareholders' equity)
  p3esg_t1_scope3_sector_average  (scopes 1-3) how sector-average emissions intensity gives a counterparty's scope 3 where
                                  it is not gathered from it — 'Institutions shall base the estimation of scope 3 emissions
                                  on the information on emissions gathered from their counterparties and on the information
                                  on sector-average emissions intensity.' The intensities are the institution's own figures
                                  per NACE division (method.t1_sector_scope3_intensity, with source name and year, attested)
  p3esg_t1_k_scope_1_2            (scopes 1 and 2) what column k counts: k asks for the share for which the institution has
                                  estimated 'scope 1, 2 and 3' from counterparty information, which leaves open whether
                                  scopes 1-2 alone count
Not stated → a named gap: the columns (or column k alone, or the exposures that need a sector average) are not computed
and the filing is blocked (filing_validation).

Per exposure (its gross carrying amount x; its counterparty — the loan tape's counterparty id — with total liabilities L
stated once for the counterparty, E119):
  attributed emissions = x / L × the counterparty's emissions of the scopes the institution estimates
  sector-average scope 3 = the division's stated intensity (tCO2e per EUR million of L) × L / 1 000 000
Column i sums the exposures stating every scope estimated (a missing scope is never 0, E76/E79); column j the attributed
scope 3; column k the share of the row's gross carrying amount whose column-i emissions rest on the counterparty's own
information ('derived from company-specific reporting' — a sector-average scope 3 is not). Not yet estimating: k is 0 %
(the share for which it has been able to estimate is nothing). An exposure without a counterparty id, whose
counterparty's figure is in conflict, without L, or larger than L, is in no column and blocks the filing.

Column j points to the phase-in of Article 5 of Delegated Regulation (EU) 2020/1818 (data/reference/pillar3/
scope3_phase_in.json): for the filing's reference date each NACE division is shown phased in or in its phase-in period.

A filing frozen before E103 (no 't1_emissions' record) printed the counterparties' reported emissions un-attributed; it
is rendered as frozen, and says so.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parents[2] / "data" / "reference" / "pillar3"
ESTIMATION, ATTRIBUTION = "p3esg_t1_emissions_estimation", "p3esg_t1_attribution"
K_READING, S3_BASIS = "p3esg_t1_k_scope_1_2", "p3esg_t1_scope3_sector_average"
INTENSITY = "method.t1_sector_scope3_intensity"
INTENSITY_REVENUE = "method.t1_sector_scope3_intensity_revenue"         # per EUR million of revenue (E133)
_INTENSITY_OF = {"intensity_x_total_liabilities": INTENSITY, "intensity_x_revenue": INTENSITY_REVENUE}
EUR_MILLION = 1_000_000             # the intensity is per EUR million of total liabilities and equity (its unit)
ESTIMATING = ("scope_1_2_3", "scope_1_2")
SCOPES = {"scope_1_2_3": ("ghg1", "ghg2", "ghg3"), "scope_1_2": ("ghg1", "ghg2")}
RECORD = "t1_emissions"            # the payload key a filing freezes the statements and the narrative under
BLOCKED = ("no_counterparty", "conflict", "unattributed", "over")


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads((_DIR / "t1_financed_emissions.json").read_text())


@lru_cache(maxsize=1)
def phase_in_reference() -> dict:
    return json.loads((_DIR / "scope3_phase_in.json").read_text())


def quote(qid: str) -> str:
    q = reference()["quotes"][qid]
    return f"“{q['quote']}” ({q['ref']})"


def switches() -> dict:
    """The statements as interpretation switches: label, the quoted text as description, the allowed options."""
    out = {}
    for key, st in reference()["statements"].items():
        desc = " ".join(quote(q) for q in st["quotes"]) + " Options — " + "; ".join(
            f"'{k}': {v}" for k, v in st["options"].items())
        if st.get("not_offered"):
            desc += " Not offered — " + "; ".join(f"{k}: {v}" for k, v in st["not_offered"].items())
        when = st.get("applies_when")
        desc += (f" Needed when you estimate {' / '.join(when)}; not stated then: " if when else " Not stated: ") + {
            K_READING: "column k is a gap and the filing is blocked.",
            S3_BASIS: "an exposure whose counterparty's scope 3 is not gathered is not in columns i and j, and the filing "
                      "is blocked."}.get(key, "Template 1 columns i-k are a gap and the filing is blocked.")
        out[key] = {"label": st["label"], "description": desc, "allowed": list(st["options"])}
    return out


def narrative_items() -> list[dict]:
    return reference()["narrative"]


def required_narrative(estimation: str | None) -> list[dict]:
    """The narrative items the instructions require for the institution's statement (none until it is stated)."""
    return [n for n in narrative_items() if estimation in n["required_when"]]


def sector_intensities(session, org_id: str, period_end: date, concept: str = INTENSITY) -> dict:
    """The institution's attested sector-average scope 3 intensities for the period (per EUR million of total
    liabilities, or — concept INTENSITY_REVENUE — of revenue), per NACE division, with their source (provider and year)
    and who attested them."""
    from services.governance.provided_data import attested_values
    return {v["member"]: {"value": v["value"], "provider": v.get("provider"), "data_vintage": v.get("data_vintage"),
                          "attested_by": v.get("attested_by"), "attested_at": v.get("attested_at")}
            for v in attested_values(session, org_id, "method", period_end)
            if v["concept"] == concept and v.get("member") and v.get("value") is not None}


def record(session, org_id: str, period_end: date | None = None, entity_id: str | None = None) -> dict:
    """What a filing freezes: the statements as stated now, the sector-average intensities stated for the period, the
    disclosure reference date (the period end), and the narrative authored for this institution and reference date
    (template answers; entity_id None: the organisation itself)."""
    from services.calc_settings import get_calc_settings
    from services.governance import pillar3_qualitative as Q
    if period_end is None:
        from services.governance.filings import reporting_period_end
        period_end = reporting_period_end(session, org_id)
    s = get_calc_settings(session, org_id)
    answers = Q.read(session, org_id, entity_id, period_end)
    return {"estimation": s.get(ESTIMATION), "attribution": s.get(ATTRIBUTION), "k_scope_1_2": s.get(K_READING),
            "scope3_sector_average": s.get(S3_BASIS), "reference_date": period_end.isoformat(),
            "sector_intensity": sector_intensities(session, org_id, period_end),
            "sector_intensity_revenue": sector_intensities(session, org_id, period_end, INTENSITY_REVENUE),
            "narrative": {n["key"]: answers[n["key"]] for n in narrative_items() if answers.get(n["key"])}}


def factor(a: dict) -> float | None:
    """The exposure compared to the counterparty's total liabilities (accounting liabilities and shareholders' equity) —
    None when the latter is not stated."""
    from services.governance.pillar3_grids import gross_of
    den = a.get("counterparty_total_liabilities_eur")
    if den in (None, "") or float(den) <= 0:
        return None
    return gross_of(a) / float(den)


def _num(v) -> float | None:
    return None if v in (None, "") else float(v)


def _division(a: dict) -> str | None:
    from services.reference import nace
    return nace.division(a.get("nace_code"))


def exposure(a: dict, rec: dict) -> dict | None:
    """One exposure on the institution's stated method: why it is not in the columns (`blocked`), or what it adds —
    `i` (attributed emissions of every scope estimated, when all are there), `j` (attributed scope 3), the scope 3
    `basis` (gathered from the counterparty / sector average), `company_specific` (column k: True / False / None = the
    source is not recorded) and `scope3_gap` (why a scope 3 the method needs is missing). None when the method is not
    stated, or the exposure states none of the emissions estimated."""
    est = rec.get("estimation")
    if est not in SCOPES or not rec.get("attribution"):
        return None
    g1, g2, g3 = _num(a.get("ghg1")), _num(a.get("ghg2")), _num(a.get("ghg3"))
    if (g1, g2) == (None, None) and (est == "scope_1_2" or g3 is None):
        return None
    if not (a.get("counterparty_ref") or "").strip():
        return {"blocked": "no_counterparty"}
    if a.get("counterparty_liabilities_conflict"):
        return {"blocked": "conflict"}
    f = factor(a)
    if f is None:
        return {"blocked": "unattributed"}
    if f > 1:
        return {"blocked": "over"}
    out = {"blocked": None, "i": None, "j": None, "basis": None, "company_specific": None, "scope3_gap": None}
    s3 = None
    if est == "scope_1_2_3":
        if g3 is not None:
            s3, out["basis"] = g3, "gathered"
        else:
            d, how = _division(a), rec.get("scope3_sector_average")
            by_revenue = how == "intensity_x_revenue"
            stated = (rec.get("sector_intensity_revenue" if by_revenue else "sector_intensity") or {}).get(d) if d else None
            if how not in _INTENSITY_OF:
                out["scope3_gap"] = f"not stated: how sector-average intensity is used ({S3_BASIS})"
            elif d is None:
                out["scope3_gap"] = "no NACE division to read a sector-average intensity for"
            elif stated is None:
                out["scope3_gap"] = f"no sector-average scope 3 intensity stated for division {d} ({_INTENSITY_OF[how]})"
            elif by_revenue and _num(a.get("revenue_eur")) is None:
                out["scope3_gap"] = "no revenue stated for the counterparty (template bank_counterparties)"
            elif by_revenue and str(a.get("counterparty_revenue_period_end") or "")[:10] > str(rec.get("reference_date") or ""):
                out["scope3_gap"] = ("the counterparty's revenue is for a financial year ending after the reference date — "
                                     "state the year ending on or before it")
            else:
                base = float(a["revenue_eur"]) if by_revenue else float(a["counterparty_total_liabilities_eur"])
                s3, out["basis"] = float(stated["value"]) * base / EUR_MILLION, "sector_average"
        if s3 is not None:
            out["j"] = f * s3
        if out["scope3_gap"] and (g1 is None or g2 is None):
            out["scope3_gap"] = None             # not in column i for its scopes 1-2 either: not a scope 3 gap
    needed = (g1, g2, s3) if est == "scope_1_2_3" else (g1, g2)
    if all(v is not None for v in needed):
        out["i"] = f * sum(needed)
        rep = a.get("emissions_company_reported")
        if out["basis"] == "sector_average":
            out["company_specific"] = False       # a sector average is not company-specific reporting (column k)
        else:
            out["company_specific"] = None if rep is None else bool(rep)
    return out


def scope3_gaps(payload: dict) -> set[str]:
    """Why the exposures of a frozen book that need a scope 3 have none (each reason once)."""
    rec = (payload or {}).get(RECORD)
    if not rec:
        return set()
    return {r["scope3_gap"] for a in payload.get("assets") or [] if (r := exposure(a, rec)) and r.get("scope3_gap")}


def gaps(rec: dict | None) -> list[str]:
    """Why columns i-k cannot be printed as the institution's own method: each a named gap ([] when none)."""
    if rec is None:
        return []
    out = []
    est, att = rec.get("estimation"), rec.get("attribution")
    if est is None:
        out.append(f"not stated: which counterparty emissions the institution estimates (methodology — {ESTIMATION})")
    elif est in ESTIMATING and att is None:
        out.append(f"not stated: how counterparty emissions are attributed to the exposure (methodology — {ATTRIBUTION})")
    return out


def k_gap(rec: dict | None) -> str | None:
    """Column k alone is a gap: the institution estimates scopes 1 and 2 and has not stated what k counts then."""
    if rec and rec.get("estimation") == "scope_1_2" and not gaps(rec) and rec.get("k_scope_1_2") is None:
        return f"not stated: what column k counts while scope 3 is not yet estimated (methodology — {K_READING})"
    return None


def k_value(g: dict, n: dict, rec: dict) -> float | None:
    """Column k (a percentage of the row's gross carrying amount), or None where it cannot be read."""
    if not g["gross"] or k_gap(rec):
        return None
    est = rec.get("estimation")
    if est == "not_yet_estimating" or (est == "scope_1_2" and rec.get("k_scope_1_2") == "all_three_scopes"):
        return 0.0
    return None if n["rep_unknown"] else round(g["rep"] / g["gross"] * 100, 1)


def missing_narrative(rec: dict | None) -> list[dict]:
    """The required narrative items not authored when the filing was frozen."""
    if rec is None:
        return []
    have = rec.get("narrative") or {}
    return [n for n in required_narrative(rec.get("estimation")) if not (have.get(n["key"]) or "").strip()]


# ── the scope 3 phase-in (Annex XL column j → Delegated Regulation (EU) 2020/1818 Article 5(1)) ──

def _day(words: str) -> date:
    return datetime.strptime(words, "%d %B %Y").date()


@lru_cache(maxsize=1)
def phase_in_points() -> tuple[dict, ...]:
    """Each point of Article 5(1): its id, the last day of its period (the anchor date plus the years it names — the
    period ends with the day falling on the same date, Regulation (EEC, Euratom) No 1182/71 Article 3(1) and 3(2)(c),
    quoted in the reference file), and the NACE divisions it covers (codes of data/reference/nace_rev2.csv)."""
    import csv
    ref = phase_in_reference()
    anchor = _day(ref["anchor"])
    with (_DIR.parent / "nace_rev2.csv").open() as fh:
        divisions = {int(r["dotted"]): r["code"] for r in csv.DictReader(fh) if r["level"] == "division"}
    named: set[str] = set()
    out = []
    for p in ref["points"]:
        if p["divisions"] == "all_other":
            codes = sorted(set(divisions.values()) - named)
        else:
            codes = sorted(divisions[n] for lo, hi in p["divisions"] for n in range(lo, hi + 1) if n in divisions)
            named |= set(codes)
        out.append({"point": p["id"], "from": date(anchor.year + p["years"], anchor.month, anchor.day),
                    "divisions": tuple(codes), "words": p["words"]})
    return tuple(out)


def all_sectors_from() -> date:
    """The reference date from which the ITS itself requires scope 3 for every sector of the template."""
    return _day(next(b["all_sectors_from"] for b in phase_in_reference()["basis"] if b.get("all_sectors_from")))


def phase_in(division: str | None, reference_date: date) -> dict | None:
    """A NACE division's Article 5(1) status on a disclosure reference date (None without a division)."""
    p = next((p for p in phase_in_points() if division in p["divisions"]), None)
    if p is None:
        return None
    return {"division": division, "point": p["point"], "from": p["from"].isoformat(),
            "phased_in": reference_date >= p["from"], "its_all_sectors": reference_date >= all_sectors_from()}


def phase_in_summary(assets: list[dict], reference_date: date | None) -> dict | None:
    """For one template row: the divisions of its exposures still in their phase-in period on the reference date."""
    if reference_date is None:
        return None
    pending: dict[str, dict] = {}
    for a in assets:
        st = phase_in(_division(a), reference_date)
        if st and not st["phased_in"]:
            pending.setdefault(st["division"], {**st, "n": 0})["n"] += 1
    return {"reference_date": reference_date.isoformat(), "in_phase_in": sorted(pending.values(), key=lambda x: x["division"]),
            "its_all_sectors": reference_date >= all_sectors_from()}


def phase_in_note(ph: dict) -> str:
    """Column j's phase-in on the reference date, for the template's note: the quoted basis, the declared reading, and
    the divisions of the book still in their Article 5(1) phase-in period."""
    ref = phase_in_reference()
    pend = ph.get("in_phase_in") or []
    head = (f"Scope 3 phase-in on {ph['reference_date']} — “{ref['basis'][0]['quote']}” (Annex XL, column j); Article 5(1) "
            "of Delegated Regulation (EU) 2020/1818, read as a calendar per NACE division (declared reading, "
            "data/reference/pillar3/scope3_phase_in.json). ")
    body = ("Every division of the book is phased in." if not pend else "In their phase-in period (not yet required by "
            "Article 5): " + ", ".join(f"{p['division']} (point ({p['point']}), from {p['from']}; {p['n']} exposure{'' if p['n'] == 1 else 's'})"
                                       for p in pend) + ".")
    its = (" From 30 June 2024 the ITS requires scope 3 for all sectors of the template: “"
           + ref["basis"][1]["quote"] + "”") if ph.get("its_all_sectors") else ""
    return head + body + its


def ref_date(rec: dict | None) -> date | None:
    return date.fromisoformat(rec["reference_date"]) if rec and rec.get("reference_date") else None


# ── the method note ──

def describe(rec: dict | None) -> str:
    """The method note under Template 1, from what the filing froze."""
    if rec is None:
        return ("Method (frozen before the institution's statements were recorded): columns i and j are the "
                "counterparties' reported emissions, not attributed to the exposure; k the share of the row's gross "
                "carrying amount whose emissions the company reported itself.")
    g = gaps(rec)
    if g:
        return "Columns i-k not computed — " + "; ".join(g) + "."
    est = rec["estimation"]
    if est == "not_yet_estimating":
        return ("The institution states it is not yet estimating its counterparties' emissions: columns i and j are "
                "blank and column k is 0 % (the share for which it has been able to estimate them); its plans are in the "
                "narrative. " + quote("i_plans") + " " + quote("k_what"))
    st = reference()["statements"]
    parts = [f"The institution estimates {st[ESTIMATION]['options'][est]}",
             f"Attribution: {st[ATTRIBUTION]['options'][rec['attribution']]} {quote('i_proportion')}",
             "Each counterparty's total liabilities and equity are stated once for the counterparty (its id on the loan tape)."]
    if est == "scope_1_2_3":
        basis = rec.get("scope3_sector_average")
        parts.append(quote("i_basis") + " " + (
            f"Where a counterparty's scope 3 is not gathered: {st[S3_BASIS]['options'][basis]}" if basis else
            f"Not stated how sector-average intensity is used ({S3_BASIS}): an exposure without gathered scope 3 is "
            "a gap, never zero."))
        by_revenue = basis == "intensity_x_revenue"
        src = rec.get("sector_intensity_revenue" if by_revenue else "sector_intensity") or {}
        if src:
            per = "of revenue" if by_revenue else "of total liabilities and equity"
            parts.append(f"Sector-average intensities stated (per EUR million {per}) for divisions " + ", ".join(
                f"{d} ({v['value']:g} tCO2e/EUR m, {v.get('provider')} {str(v.get('data_vintage') or '')[:4]})"
                for d, v in sorted(src.items())) + ".")
    if est == "scope_1_2":
        parts.append(quote("j_blank"))
        kr = rec.get("k_scope_1_2")
        parts.append("Column k: " + (st[K_READING]["options"][kr] if kr else k_gap(rec) + ".") + " " + quote("k_what"))
    else:
        parts.append("Column k: " + quote("k_what") + " " + quote("k_title") + " — read from each exposure's record of "
                     "its emissions' source; a sector-average scope 3 is not company-specific.")
    return " ".join(parts)


def narrative_lines(rec: dict | None) -> list[str]:
    """The frozen narrative accompanying the template, item by item."""
    if not rec:
        return []
    have = rec.get("narrative") or {}
    return [f"{n['prompt']}: {have[n['key']]}" for n in narrative_items() if have.get(n["key"])]
