"""EU Taxonomy Art. 8 for credit institutions — Annex VI to Delegated Regulation (EU) 2021/2178, every version, built
from the governing specification and the exposures' stated facts.

What each printed row holds and each column measures comes from the spec through the declared vocabulary
(services.governance.taxonomy_vocabulary). This module applies Annex V's method to them:

  * an exposure's place — in the GAR numerator, excluded from the numerator, or outside the covered assets — is read
    from the spec's own row tree: the first leaf row whose filter it meets decides (so a version that moves a class,
    as 2026/73 moved derivatives and non-CSRD counterparties out of the denominator, moves it here too)
  * a general-purpose exposure to an undertaking is valued by the counterparty's own KPIs (issuer_taxonomy_kpi,
    frozen with the filing), turnover-based and CapEx-based; the CapEx-based KPI of general lending uses the
    counterparty's turnover KPI (the vocabulary's basis_rules, cited); where the counterparty's KPIs are not on file
    the cell is blank, never estimated
  * a specific-purpose exposure (specialised lending / use of proceeds), a household, a local government or a
    repossessed property is valued by its own stated Taxonomy status, objective and contribution
  * what the Regulation says is not yet disclosed (the phase-ins the spec declares) is marked, not computed
  * a figure the loan tape holds no facts for is entered by the institution (an input cell, with the reason)
  * the previous disclosure reference date (T-1) is computed from the previous period's frozen exposures

A cell is None when no exposure in it states the fact it needs — shown blank, never zero.
"""
from __future__ import annotations

from datetime import date

import services.regspec as R
from services.governance import taxonomy_vocabulary as V
from services.governance.pillar3_gar import facts as _p3_facts
from services.governance.pillar3_grids import gross_of
from services.reference.taxonomy_objectives import codes as objective_codes

_UNDERTAKINGS = ("credit_institution", "other_financial_corporation", "non_financial_corporation")
_GAR_INSTRUMENTS = ("loans_and_advances", "debt_securities", "equity_instruments")
_SCOPES = {"numerator": {"numerator"}, "numerator_excluded": {"numerator_excluded"},
           "covered": {"numerator", "numerator_excluded"}, "not_covered": {"not_covered"}, "total": None}
_OWN_MEASURES = ("eligible", "aligned", "use_of_proceeds", "transitional", "enabling", "adaptation",
                 "transitional_or_adaptation")
NOT_REQUIRED = "not_required"          # a cell a phase-in says is not yet disclosed


# ───────────────────────────── facts ─────────────────────────────

def facts(a: dict, period: tuple[date, date] | None) -> dict:
    """The Pillar 3 GAR facts of an exposure plus what Annex V also needs: CSRD scope and the counterparty's KPIs."""
    f = _p3_facts(a, period)
    f["csrd"] = a.get("csrd_subject")
    f["kpi"] = a.get("counterparty_taxonomy_kpi") or {}
    f["nace"] = a.get("nace_code")
    return f


def _regime(spec: dict) -> str:
    """Which disclosure obligation splits undertakings in this version: the CSRD (2026/73) or the NFRD before it."""
    return "csrd" if any("CSRD" in r["label"] for t in spec["templates"] for r in t.get("rows", [])) else "nfrd"


# ───────────────────────────── filters and scope ─────────────────────────────

def _is(val, want) -> bool:
    return val in want if isinstance(want, list) else val == want


def _match(f: dict, frag: dict, regime: str) -> bool:
    """Does the exposure meet the row's filter (its combined fragment)? The scope key is decided by classification."""
    for k, v in frag.items():
        if k in ("scope", "input", "kpi", "gar_scope_any", "elided", "heading"):
            continue
        if k == "gar":
            if f["trading"] or f["instr"] not in _GAR_INSTRUMENTS:
                return False
        elif k == "govt":
            if f["govt"] not in v:
                return False
        elif k == "purpose_not":
            if f["purpose"] == v:
                return False
        elif k == "subject":
            if f[regime] is not v:
                return False
        elif k in ("nfrd", "csrd"):
            if f[k] is not v:
                return False
        elif k == "assessed":
            if f["assessed"] is not v:
                return False
        elif k in ("cp", "sub", "instr", "purpose", "col", "eu", "trading"):
            if not _is(f[k], v):
                return False
    # in the numerator an undertaking is one subject to the disclosure obligation (Annex V), unless the row says
    if frag.get("scope") == "numerator" and f["cp"] in _UNDERTAKINGS and not ({"nfrd", "csrd", "subject"} & set(frag)):
        if f[regime] is not True:
            return False
    return True


_PLACING = ("numerator", "numerator_excluded", "not_covered")


def _leaves(res: dict, labels: dict[str, str]) -> list[tuple[str, dict]]:
    """The rows that partition the book, in printed order: rows with no sub-rows other than 'of which' rows (an 'of
    which' row is a part of its parent, not a class of its own), in the numerator, excluded from it, or outside the
    covered assets. Total rows (covered assets, total assets) add classes up and place nothing."""
    def of_which(rid):
        return labels[rid].split(" > ")[-1].strip().lower().startswith("of which")
    parents = {p for rid, p in res["parents"].items() if p and not of_which(rid)}
    return [(rid, fr) for rid, fr in res["rows"].items()
            if rid not in parents and not of_which(rid) and fr.get("scope") in _PLACING and not fr.get("input")]


def classify(f: dict, leaves: list, regime: str) -> str | None:
    """numerator / numerator_excluded / not_covered — the scope of the first leaf row the exposure meets."""
    for _, fr in leaves:
        if _match(f, fr, regime):
            return fr["scope"]
    return None


# ───────────────────────────── values ─────────────────────────────

def _kpi_basis(f: dict, basis: str, rules: dict) -> str:
    if basis == "capex" and f["instr"] == "loans_and_advances":
        return rules.get("capex_general_lending_uses", "capex")
    return basis


def _general_purpose(f: dict) -> bool:
    return f["cp"] in _UNDERTAKINGS and f["specialised"] is not True


def _objectives(objective: str, measure: str, ph: dict | None) -> tuple[str, ...]:
    """The objectives a column adds up. 'all' is every objective the disclosure covers: while a phase-in says an
    objective is disclosed for eligibility only, its alignment is left out of every aligned total (Art. 10(7))."""
    if objective != "all":
        return (objective,)
    if ph and measure not in ("eligible", "gross", "non_assessed"):
        only = ph["eligibility_only"].get("objectives")
        return () if only == "all" else tuple(o for o in objective_codes() if o not in (only or []))
    return objective_codes()


def _one(f: dict, x: float, measure: str, objs: tuple[str, ...], basis: str, rules: dict) -> float | None:
    """This exposure's part of a column over the given objectives (None = the fact it needs is not stated)."""
    if _general_purpose(f):
        if measure in ("use_of_proceeds", "adaptation", "transitional_or_adaptation"):
            return 0.0 if measure == "use_of_proceeds" else None
        b = _kpi_basis(f, basis, rules)
        vals = [(f["kpi"].get(f"{b}:{o}") or {}).get(measure) for o in objs]
        if all(v is None for v in vals):
            return None
        return x * sum(float(v) for v in vals if v is not None) / 100.0
    # a specific-purpose exposure: its own stated status
    if not f["assessed"]:
        return None
    if f["eligible"] and not f["objective"]:
        return None                                      # eligible, but to which objective is not stated
    hit = f["eligible"] and f["objective"] in objs
    if measure == "eligible":
        return x if hit else 0.0
    if not f["aligned_known"]:
        return None
    aligned = hit and f["aligned"]
    if measure == "aligned":
        return x if aligned else 0.0
    if measure == "use_of_proceeds":
        return x if aligned and f["specialised"] else 0.0
    if not aligned:
        return 0.0
    if not f["contribution"]:
        return None
    want = {"transitional": ("transitional",), "enabling": ("enabling",), "adaptation": ("adaptation",),
            "transitional_or_adaptation": ("transitional", "adaptation")}[measure]
    return x if f["contribution"] in want else 0.0


def amount(pop: list, measure: str, objective: str, basis: str, rules: dict, ph: dict | None = None) -> float | None:
    if measure == "gross":
        return sum(x for _, x in pop)
    if measure == "non_assessed":
        return sum(x for f, x in pop if not f["assessed"] and not (_general_purpose(f) and f["kpi"]))
    objs = _objectives(objective, measure, ph)
    if not objs:
        return None
    parts = [_one(f, x, measure, objs, basis, rules) for f, x in pop]
    known = [p for p in parts if p is not None]
    return sum(known) if known else None


def _phase(spec: dict, disclosure: date) -> dict | None:
    for ph in spec.get("phase_in") or []:
        if ph["disclosures"]["from"] <= disclosure.isoformat() <= ph["disclosures"]["until"]:
            return ph
    return None


def _not_required(ph: dict | None, measure: str | None, objective: str | None) -> bool:
    """A phase-in says this cell is not yet disclosed: an alignment figure for an objective (or all objectives) that
    is disclosed for eligibility only."""
    if not ph or measure in (None, "gross", "eligible", "non_assessed"):
        return False
    only = ph["eligibility_only"].get("objectives")
    return only == "all" or (objective != "all" and objective in (only or []))


def _pct(n, d):
    return None if n is None or not d else round(100.0 * n / d, 2)


# ───────────────────────────── the templates ─────────────────────────────

def build(spec: dict, assets: list[dict], period_end: date, *, previous_assets: list[dict] | None = None,
          previous_period_end: date | None = None, disclosure_date: date | None = None) -> dict:
    """{template_id: {basis: {row_id: {col_id: value | NOT_REQUIRED | None}}}, 'counts': {...}, 'inputs': {...}}.
    basis is 'turnover' and 'capex' (Annex VI: each template is disclosed for both); a template without a basis split
    has the single key 'all'."""
    rules = V.vocabulary().get("basis_rules", {})
    regime = _regime(spec)
    ph = _phase(spec, disclosure_date or date.today())
    t1 = V.resolve(spec, "T1")
    leaves = _leaves(t1, {r["id"]: r["label"] for r in R.template(spec, "T1")["rows"]})

    def book(rows: list[dict] | None, pe: date | None) -> list[tuple[dict, float, str | None]]:
        if not rows or pe is None:
            return []
        period = (date(pe.year, 1, 1), pe)
        out = []
        for a in rows:
            x = gross_of(a)
            if x:
                f = facts(a, period)
                out.append((f, x, classify(f, leaves, regime)))
        return out

    cur = book(assets, period_end)
    prev = book(previous_assets, previous_period_end)
    totals = {}
    for name, bk in (("current", cur), ("previous", prev)):
        totals[name] = {s: sum(x for _, x, sc in bk if (allowed is None or sc in allowed))
                        for s, allowed in _SCOPES.items()}
        totals[name]["new_covered"] = sum(x for f, x, sc in bk if f["new"] and sc in _SCOPES["covered"])

    def population(bk, frag, flow=False):
        allowed = _SCOPES.get(frag.get("scope")) if frag.get("scope") else None
        return [(f, x) for f, x, sc in bk if (allowed is None or sc in allowed) and (not flow or f["new"]) and _match(f, frag, regime)]

    out: dict = {"counts": {}, "inputs": {}}
    for t in spec["templates"]:
        tid = t["id"]
        res = V.resolve(spec, tid)
        kind = res["kind"]
        if kind in V.vocabulary()["inputs"]:
            out["inputs"][tid] = V.input_reason({"input": kind})
            continue
        bases = ("turnover", "capex") if kind in ("gar_assets", "sectors", "gar_ratio_stock", "gar_ratio_flow") else ("all",)
        out[tid] = {}
        for basis in bases:
            grid: dict = {}
            if kind == "sectors":
                grid = _sectors(t, res, cur, basis, rules, regime, ph)
            elif kind == "summary":
                grid = _summary(res, cur, totals["current"], rules, regime, ph, population)
            else:
                flow = kind == "gar_ratio_flow"
                for r in t["rows"]:
                    frow = res["rows"][r["id"]]
                    if frow.get("input") or frow.get("elided"):
                        grid[r["id"]] = {"_input": frow.get("input")} if frow.get("input") else {}
                        continue
                    row = {}
                    for c in t["columns"]:
                        fcol = res["columns"][c["id"]]
                        bk = prev if fcol.get("period") == "previous" else cur
                        tot = totals["previous" if fcol.get("period") == "previous" else "current"]
                        b = fcol.get("basis") or basis
                        m, o = fcol.get("measure"), fcol.get("objective", "all")
                        if fcol.get("input"):
                            row[c["id"]] = {"_input": fcol["input"]}
                            continue
                        if _not_required(ph, m, o):
                            row[c["id"]] = NOT_REQUIRED
                            continue
                        pop = population(bk, frow, flow)
                        if kind == "gar_assets":
                            # outside the numerator only the gross carrying amount is reported (the rest is shaded)
                            if frow.get("scope") != "numerator" and m not in (None, "gross"):
                                row[c["id"]] = None
                                continue
                            row[c["id"]] = amount(pop, m or "gross", o, b, rules, ph)
                        else:                              # a GAR KPI: the row's amount over the covered assets
                            denom = tot["new_covered"] if flow else tot["covered"]
                            if fcol.get("coverage"):
                                base = tot["total"] if fcol["coverage"] == "stock" else sum(x for f, x, _ in bk if f["new"])
                                row[c["id"]] = _pct(amount(pop, "gross", o, b, rules, ph), base)
                            elif m == "aligned_in_eligible":
                                row[c["id"]] = _pct(amount(pop, "aligned", o, b, rules, ph), amount(pop, "eligible", o, b, rules, ph))
                            else:
                                row[c["id"]] = _pct(amount(pop, m or "gross", o, b, rules, ph), denom)
                    grid[r["id"]] = row
            out[tid][basis] = grid
    out["counts"] = {
        "exposures": len(cur),
        "unclassified": sum(1 for _, _, sc in cur if sc is None),
        "unclassified_gross": sum(x for _, x, sc in cur if sc is None),
        "subject_unstated": sum(1 for f, _, sc in cur if f["cp"] in _UNDERTAKINGS and f[regime] is None),
        "general_purpose_without_kpi": sum(1 for f, _, sc in cur if sc == "numerator" and _general_purpose(f) and not f["kpi"]),
        "previous_period": bool(prev), "regime": regime,
        "phase_in": ph and {"ref": ph["ref"], "quote": ph["quote"], "note": ph.get("note")},
        "covered": totals["current"]["covered"], "total": totals["current"]["total"]}
    return out


def _summary(res: dict, cur: list, tot: dict, rules: dict, regime: str, ph, population) -> dict:
    """Template 0: the GAR on stock and on flow from the book; the other KPIs are entered by the institution."""
    grid = {}
    num = [(f, x) for f, x, sc in cur if sc == "numerator"]
    new_num = [(f, x) for f, x in num if f["new"]]
    all_objectives_phased = bool(ph) and ph["eligibility_only"].get("objectives") == "all"
    for rid, fr in res["rows"].items():
        k = fr.get("kpi")
        if k not in ("gar_stock", "gar_flow"):
            grid[rid] = {"_input": fr.get("input") or "off_balance"}
            continue
        pop, denom = (num, tot["covered"]) if k == "gar_stock" else (new_num, tot["new_covered"])
        row = {}
        for cid, fc in res["columns"].items():
            b = fc.get("basis") or "turnover"
            if fc.get("coverage"):
                row[cid] = _pct(tot["covered"], tot["total"]) if k == "gar_stock" else None
            elif fc.get("share_of_total"):
                row[cid] = _pct(tot[fc["share_of_total"]], tot["total"]) if k == "gar_stock" else None
            elif fc.get("measure") == "non_assessed":
                row[cid] = _pct(amount(pop, "non_assessed", "all", b, rules, ph), denom)
            elif all_objectives_phased:                    # Art. 10(3): alignment is not yet disclosed at all
                row[cid] = NOT_REQUIRED
            elif fc.get("measure") == "aligned":
                row[cid] = amount(pop, "aligned", "all", b, rules, ph)
            elif fc.get("unit") == "pct":                  # the KPI: aligned over covered assets
                row[cid] = _pct(amount(pop, "aligned", "all", b, rules, ph), denom)
            else:
                row[cid] = None
        grid[rid] = row
    return grid


def _sectors(t: dict, res: dict, cur: list, basis: str, rules: dict, regime: str, ph) -> dict:
    """Template 2: the top NACE 4-digit sectors of the numerator's non-financial undertakings, one per slot row."""
    from services.reference import nace as _nace
    nfc = [(f, x) for f, x, sc in cur if f["cp"] == "non_financial_corporation" and sc in ("numerator", "numerator_excluded")]
    by: dict[str, float] = {}
    for f, x in nfc:
        hit = _nace.lookup(f["nace"])
        if hit and len(hit["dotted"].replace(".", "")) >= 4:
            by[hit["dotted"][:5]] = by.get(hit["dotted"][:5], 0.0) + x
    ranked = sorted(by, key=lambda k: -by[k])
    slots = [r["id"] for r in t["rows"] if not res["rows"][r["id"]].get("input") and not res["rows"][r["id"]].get("elided")
             and res["rows"][r["id"]].get("assessed") is None]
    grid = {}
    for i, rid in enumerate(slots):
        code = ranked[i] if i < len(ranked) else None
        row = {"_sector": code and f"{code} {(_nace.lookup(code) or {}).get('label', '')}".strip()}
        if code:
            pop = [(f, x) for f, x in nfc if ((_nace.lookup(f["nace"]) or {}).get("dotted") or "")[:5] == code]
            for cid, fc in res["columns"].items():
                if fc.get("sector"):
                    continue
                m, o = fc.get("measure") or "gross", fc.get("objective", "all")
                if _not_required(ph, m, o):
                    row[cid] = NOT_REQUIRED
                    continue
                sub = [(f, x) for f, x in pop if _match(f, {k: v for k, v in fc.items() if k in ("cp", "nfrd", "csrd")}, regime)]
                v = amount(sub, m, o, fc.get("basis") or basis, rules, ph)
                row[cid] = v / 1e6 if (v is not None and fc.get("unit") == "meur") else v
        grid[rid] = row
    for r in t["rows"]:
        fr = res["rows"][r["id"]]
        if fr.get("input"):
            grid[r["id"]] = {"_input": fr["input"]}
        elif fr.get("assessed") is False:                   # 'Of which non-assessed exposures'
            grid[r["id"]] = {cid: amount([(f, x) for f, x in nfc if not f["assessed"]], "gross", "all", basis, rules)
                             for cid, fc in res["columns"].items() if fc.get("measure") == "gross"}
    return grid
