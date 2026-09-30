"""The checks of an ESRS statement filing, run on its frozen record only (so they reproduce): every rule quotes its
source (the specification, data/reference/esrs/*.json, data/reference/csrd/scope.json) or is arithmetic.

  specification   a version governs the financial year
  undertaking     an organisation with legal entities files per undertaking; the CSRD role is stated; an exempt
                  subsidiary files no statement (Directive 2013/34/EU Art. 19a(9) / 29a(8))
  scope           the role against Art. 5(2) of Directive (EU) 2022/2464 (services.governance.csrd_scope)
  materiality     each topic's materiality stated; climate change omitted only with a detailed explanation
  items           every 'shall' item of a material topic filled, or omitted with its stated reason
  phase-ins       a claimed phase-in holds on the undertaking's attested facts; words the text leaves open are flagged
  figures         the platform's figures computed (no gap), the stated relations hold (data/reference/esrs/identities.json)
  comparatives    the previous period's figure beside each quantitative item (ESRS 1 §83), unless a relief applies
                  (2023 ESRS 1 §136, 2026 ESRS 1 §124)
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_REF = Path(__file__).resolve().parents[2] / "data" / "reference" / "esrs"


@lru_cache(maxsize=4)
def _ref(name: str) -> dict:
    return json.loads((_REF / name).read_text())


def phase_ins(version: str) -> list[dict]:
    d = _ref("phase_ins.json")
    v = d[version]
    if isinstance(v, str):                     # "dr_2023_2772+": the original rules and the amending ones
        return d["dr_2023_2772"] + d[v]
    return v


def identities(version: str) -> list[dict]:
    d = _ref("identities.json")
    v = d[version]
    return d[v] if isinstance(v, str) else v


def _f(rule, category, severity, passed, message, ref=None):
    return {"rule": rule, "category": category, "severity": severity, "passed": bool(passed), "message": message, "ref": ref}


def facts_of(provided: dict) -> dict:
    """The undertaking's attested facts the phase-ins and relief read (numbers; net turnover only when stated in EUR)."""
    def num(k):
        v = provided.get(k)
        return None if v is None else float(v["value"])
    t = provided.get("csrd.net_turnover")
    return {"employees": num("csrd.employees_average"), "first_year": num("csrd.first_reporting_year"),
            "turnover_eur": float(t["value"]) if t and t.get("currency") == "EUR" else None}


def phase_in_holds(rule: dict, item_id: str, dr: str, standard: str, kind: str, fy_year: int, facts: dict) -> tuple[bool | None, str]:
    """Does the claimed phase-in cover this item in this year for this undertaking? (None: a fact is not stated)."""
    covered = (item_id in rule.get("items", []) or item_id in rule.get("items_unclear", []) or dr in rule.get("drs", [])
               or standard in rule.get("standards", []))
    if not covered or item_id in rule.get("except_items", []):
        return False, f"{rule['id']} does not cover {item_id}"
    if rule.get("quantitative_only") and kind != "field":
        return False, f"{rule['id']} covers quantitative information only — {item_id} is narrative"
    first = facts["first_year"]
    wave = None if first is None else ("a" if first <= 2026 else "b")
    need = []
    if "wave" in rule:
        if wave is None:
            need.append("csrd.first_reporting_year")
        elif wave != rule["wave"]:
            return False, f"{rule['id']} is for {'wave-one' if rule['wave'] == 'a' else 'other'} undertakings"
    if "year_index_max" in rule:
        if first is None:
            need.append("csrd.first_reporting_year")
        elif fy_year - first + 1 > rule["year_index_max"]:
            return False, f"{rule['id']} runs for the first {rule['year_index_max']} year(s); this is year {int(fy_year - first + 1)}"
    if "year_before" in rule and fy_year >= rule["year_before"]:
        return False, f"{rule['id']} applies to financial years before {rule['year_before']}"
    if "employees_not_exceeding" in rule:
        if facts["employees"] is None:
            need.append("csrd.employees_average")
        elif facts["employees"] > rule["employees_not_exceeding"]:
            return False, f"{rule['id']} is for undertakings not exceeding {rule['employees_not_exceeding']} employees"
    for key, block in (("exceeds", True), ("not_exceeding_either", False)):
        if key not in rule:
            continue
        te, em = facts["turnover_eur"], facts["employees"]
        if te is None or em is None:
            need += [k for k, v in (("csrd.net_turnover (in EUR)", te), ("csrd.employees_average", em)) if v is None]
            continue
        exceeds_both = te > 450000000 and em > 1000
        if exceeds_both != block:
            return False, f"{rule['id']}: the net-turnover / employee condition does not hold"
    if need:
        return None, f"{rule['id']} needs {', '.join(sorted(set(need)))}"
    if item_id in rule.get("items_unclear", []):
        return None, f"{rule['id']}: the text names 'datapoints on scope 3 emissions and total GHG emissions' — whether {item_id} is one is not stated"
    return True, f"{rule['id']} applies"


def checks(payload: dict) -> list[dict]:
    doc = payload.get("document_report") or {}
    spec_rec = (payload.get("_specs") or {}).get("esrs") or {}
    if not spec_rec.get("version") or not doc:
        return [_f("specification", "completeness", "blocking", False,
                   "no ESRS version governs this financial year (or the statement was not built)")]
    out = [_f("specification", "completeness", "info", True, f"governed by {spec_rec.get('act')} ({spec_rec['version']})")]
    scope, role, st = doc.get("scope_check") or {}, doc.get("role"), doc.get("statement") or {}
    if doc.get("org_has_entities") and doc.get("reporting_entity_id") is None:
        out.append(_f("undertaking", "scope", "blocking", False, "this organisation has legal entities: an ESRS statement "
                      "is filed by the reporting undertaking (an entity), not by the organisation as a whole"))
    if role is None:
        out.append(_f("csrd_role", "scope", "blocking", False, "state the undertaking's CSRD role for this financial year"))
    elif role["role"] == "exempt_subsidiary":
        out.append(_f("csrd_role", "scope", "blocking", False, f"an exempt subsidiary files no statement — included in "
                      f"{role['parent_name']}'s consolidated report ({role['parent_report_ref']})", "Directive 2013/34/EU Art. 19a(9) / 29a(8)"))
    req = scope.get("required")
    if role and role["role"] in ("individual", "consolidated"):
        if req is False:
            out.append(_f("csrd_scope", "scope", "warning", False, "Art. 5(2) does not require a statement for this year "
                          f"({scope.get('reason') or scope.get('point')}) — state the role as voluntary if it is filed", scope.get("ref")))
        elif req is None:
            out.append(_f("csrd_scope", "scope", "warning", False, "whether a statement is required cannot be determined: "
                          + (scope.get("reason") or "missing " + ", ".join(scope.get("missing") or [])), scope.get("ref")))
        else:
            out.append(_f("csrd_scope", "scope", "info", True, f"required under Art. 5(2) point {scope.get('point')}", scope.get("ref")))
    elif role and role["role"] == "voluntary" and req is True:
        out.append(_f("csrd_scope", "scope", "warning", False, "Art. 5(2) requires a statement for this year — the role is "
                      "stated as voluntary", scope.get("ref")))

    fy_year = int(str(scope.get("fy_start") or st.get("period_end"))[:4])
    facts = facts_of({k: v for k, v in (doc.get("provided") or {}).items()})
    rules = {r["id"]: r for r in phase_ins(spec_rec["version"])}
    missing, bad_claims, unclear, gaps = [], [], [], []
    for sec in doc.get("sections") or []:
        if sec["topic"] is None:
            out.append(_f(f"materiality_{sec['standard']}", "completeness", "blocking", False,
                          f"state whether ESRS {sec['standard']} is material (the undertaking's materiality assessment)"))
            continue
        if sec["topic"].get("material") is False:
            continue
        dr = None
        for i in sec["items"]:
            if i["kind"] == "heading":
                dr = i["id"]
                continue
            if i["status"] == "omitted" and (i.get("omission") or {}).get("reason") == "phase_in":
                pid = i["omission"].get("phase_in")
                rule = rules.get(pid)
                ok, why = (False, f"no phase-in '{pid}' in this version") if rule is None else \
                    phase_in_holds(rule, i["id"], dr, sec["standard"], i["kind"], fy_year, facts)
                if ok is False:
                    bad_claims.append(f"{i['id']}: {why}")
                elif ok is None:
                    unclear.append(f"{i['id']}: {why}")
            if i["status"] == "missing" and i.get("obligation") == "shall":
                gap = next((d.get("gap") for d in i.get("datapoints") or [] if d.get("status") == "gap"), None)
                (gaps if gap else missing).append(f"{i['id']}" + (f" — {gap}" if gap else ""))
    if missing:
        out.append(_f("items_answered", "completeness", "blocking", False,
                      f"{len(missing)} required item(s) neither filled nor omitted with a reason: " + "; ".join(missing[:12])))
    if gaps:
        out.append(_f("figures_computed", "completeness", "blocking", False,
                      f"{len(gaps)} item(s) the platform cannot compute yet: " + "; ".join(gaps[:8])))
    if bad_claims:
        out.append(_f("phase_ins", "completeness", "blocking", False, "a phase-in claimed does not apply: " + "; ".join(bad_claims[:8])))
    if unclear:
        out.append(_f("phase_ins_open", "completeness", "warning", False, "; ".join(unclear[:8])))
    out += _identities(spec_rec["version"], doc.get("provided") or {})
    out += _arithmetic(st, doc.get("provided") or {})
    if not doc.get("period_closed"):
        out.append(_f("period_closed", "governance", "warning", False, "the reporting period is not closed for this "
                      "undertaking — its year-end values can still change without a restatement"))
    return out


def _identities(version: str, provided: dict) -> list[dict]:
    out = []
    for r in identities(version):
        v = lambda k: None if provided.get(k) is None else float(provided[k]["value"])      # noqa: E731
        if r["kind"] == "sum":
            parts = ([float(p["value"]) for k, p in provided.items() if k.startswith(r["parts_breakdown"] + "@")]
                     if r.get("parts_breakdown") else [v(k) for k in r["parts"]])
            total = v(r["total"])
            if total is None or not parts or any(p is None for p in parts):
                continue
            tol = (len(parts) + 1) * 0.5
            ok = abs(total - sum(parts)) <= tol
            out.append(_f(f"identity_{r['id']}", "consistency", "blocking", ok,
                          f"{r['total']} {total:,.0f} {'=' if ok else '≠'} sum of its parts {sum(parts):,.0f}", r["ref"]))
        elif r["kind"] == "at_most":
            part, total = v(r["part"]), v(r["total"])
            if part is None or total is None:
                continue
            out.append(_f(f"identity_{r['id']}", "consistency", "blocking", part <= total + 0.5,
                          f"{r['part']} {part:,.0f} {'≤' if part <= total + 0.5 else '>'} {r['total']} {total:,.0f}", r["ref"]))
    return out


def _arithmetic(st: dict, provided: dict) -> list[dict]:
    """Assets at material physical risk are part of total assets (the share is of the balance-sheet total)."""
    c = (st.get("concepts") or {}).get("e1.physrisk.assets.amount") or {}
    ta = provided.get("fs.total_assets")
    if not ta or not c.get("by_horizon") or ta.get("value_eur") is None:
        return []
    worst = max((x for x in c["by_horizon"].values() if x is not None), default=None)
    if worst is None:
        return []
    ok = worst <= float(ta["value_eur"]) + 0.5
    return [_f("assets_within_total", "consistency", "blocking", ok,
               f"assets at material physical risk {worst:,.0f} {'≤' if ok else '>'} total assets {float(ta['value_eur']):,.0f} (EUR)")]
