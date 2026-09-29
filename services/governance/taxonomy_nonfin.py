"""EU Taxonomy Art. 8 for a non-financial undertaking that owns buildings (a REIT) — Annex II to Delegated Regulation
(EU) 2021/2178, every version, built from the governing specification and the property book.

What each printed row and column means comes from the spec through the declared vocabulary (taxonomy_vocabulary,
family nonfin_taxonomy). This module fills it from the book:
  * turnover — each building's gross rental revenue (IAS 1 para 82(a), Annex I §1.1.1), or its NOI where gross revenue
    is not on file (a counted, disclosed proxy that understates turnover)
  * eligibility and the activity — the classifier's reading from the Taxonomy's activity list (68.20 → 7.7
    'Acquisition and ownership of buildings'), see ml/regulatory/eu_taxonomy_classifier.py
  * alignment — per building, from the activity's criteria and the building's stated facts
    (services.governance.taxonomy_buildings for 7.7): aligned (A.1), not aligned (A.2), or not known — a building whose
    alignment is not known sits in neither A.1 nor A.2 and is counted on the form
  * CapEx and OpEx — the undertaking's own ledger by activity: entered by it (input cells)
The previous year (N-1) comes from the previous period's frozen filing. A cell no building states the fact for is blank.
"""
from __future__ import annotations

from datetime import date

from services.governance import taxonomy_buildings as B
from services.governance import taxonomy_vocabulary as V

FAMILY = "nonfin_taxonomy"
_CODES_FOOTNOTE = "y – yes, taxonomy-eligible and taxonomy-aligned activity"


def _codes_or_percent(spec: dict, tid: str) -> str:
    """Whether the substantial-contribution cells hold verdict codes (Y / N / N/EL, EL / N/EL — as the 2023/2486 footnotes
    define) or a percentage per objective (the earlier templates) — read from the spec's own footnotes."""
    import services.regspec as R
    quotes = " ".join(i["quote"].lower() for i in R.template(spec, tid).get("instructions") or [])
    return "codes" if _CODES_FOOTNOTE in quotes.replace("‑", "-") else "percent"


def _activity(p: dict) -> dict | None:
    """The activity a building is classified to: {'codes': ['CCM 7.7', 'CCA 7.7'], 'title', 'section', 'objectives'}."""
    ref = p.get("taxonomy_activity_ref") or ""
    if p.get("taxonomy_status") != "eligible" or " — " not in ref:
        return None
    codes = [c.strip() for c in ref.split(" — ")[0].split(" / ")]
    return {"codes": codes, "title": ref.split(" — ", 1)[1], "section": codes[0].split()[-1],
            "objectives": [c.split()[0].lower() for c in codes]}


def _turnover(p: dict) -> tuple[float, bool]:
    g = p.get("annual_gross_rental_revenue_eur")
    return (float(g), False) if g is not None else (float(p.get("annual_noi_eur") or 0), True)


def _book(props: list[dict] | None) -> list[dict]:
    out = []
    for p in props or []:
        x, proxy = _turnover(p)
        act = _activity(p)
        ev = B.evaluate(p) if act and act["section"] == "7.7" else {"aligned": None, "reasons": ["activity criteria not evaluated"]}
        out.append({"x": x, "proxy": proxy, "act": act, "aligned": ev["aligned"] if act else False, "ev": ev})
    return out


def _pct(n, d):
    return None if n is None or not d else round(100.0 * n / d, 2)


def _group(b: dict) -> str | None:
    if not b["act"]:
        return "non_eligible"
    return {True: "aligned", False: "eligible_not_aligned"}.get(b["aligned"])      # None: alignment not known


def build(spec: dict, properties: list[dict], period_end: date, *, previous_properties: list[dict] | None = None) -> dict:
    """{template_id: {kpi: grid}, 'counts', 'inputs', 'activities'}; grid rows keyed by row id, activity rows as
    '<slot row id>:<n>' (the undertaking's activities fill a flexible template's illustrative rows)."""
    cur, prev = _book(properties), _book(previous_properties)
    tot = sum(b["x"] for b in cur)
    ptot = sum(b["x"] for b in prev)
    acts: dict[str, dict] = {}
    for b in cur:
        if b["act"]:
            acts.setdefault(" / ".join(b["act"]["codes"]), b["act"])

    def amount(bk, group=None, act_key=None, objective=None, category=None):
        if bk is prev and not prev:
            return None                                      # no previous filing: the N-1 figure is not known (blank)
        pop = [b for b in bk if (group is None or group == "all" or _group(b) == group
                                 or (group == "eligible" and b["act"]))]
        if act_key:
            pop = [b for b in pop if b["act"] and " / ".join(b["act"]["codes"]) == act_key]
        if objective:
            # an aligned building is aligned under the objective its criteria were evaluated for (7.7: mitigation);
            # eligibility counts under every objective the activity is eligible for (a declared reading, on the form)
            pop = [b for b in pop if b["act"] and (objective == "ccm" if group == "aligned" else objective in b["act"]["objectives"])]
        if category:
            pop = [b for b in pop if b["act"] and category == (b["act"].get("category"))]
        return sum(b["x"] for b in pop)

    out: dict = {"counts": {}, "inputs": {}, "activities": acts}
    for t in spec["templates"]:
        tid = t["id"]
        res = V.resolve(spec, tid)
        kind = res["kind"]
        if kind in V.vocabulary(FAMILY)["inputs"]:
            out["inputs"][tid] = V.input_reason({"input": kind}, FAMILY)
            continue
        out[tid] = {}
        if kind == "kpi_summary":                            # printed once, a row per KPI
            out[tid]["all"] = _summary(res, tot, ptot, cur, prev, amount)
            continue
        for kpi in V.kpis_of(spec, tid):
            if kpi != "turnover" and kind != "kpi_summary":
                out[tid][kpi] = {"_input": "ledger"}          # CapEx / OpEx: the undertaking's own ledger
                continue
            out[tid][kpi] = (_objectives(res, tot, cur, amount) if kind == "per_objective" else
                             _activities(spec, t, res, tot, ptot, cur, prev, acts, amount))
    unknown = [b for b in cur if b["act"] and b["aligned"] is None]
    out["counts"] = {"properties": len(cur), "turnover": tot, "noi_proxy": sum(1 for b in cur if b["proxy"]),
                     "noi_proxy_turnover": sum(b["x"] for b in cur if b["proxy"]),
                     "eligible": sum(b["x"] for b in cur if b["act"]),
                     "alignment_unknown": len(unknown), "alignment_unknown_turnover": sum(b["x"] for b in unknown),
                     "unknown_reasons": _top_reasons(unknown), "previous_period": bool(prev)}
    return out


def _top_reasons(unknown: list[dict]) -> list[tuple[str, int]]:
    from collections import Counter
    # 'built 2010: EPC B; top-15 % … not stated' → the reason itself (the year only says which test applied)
    c = Counter(r.split(": ", 1)[1] if r.startswith("built") and ": " in r else r for b in unknown for r in b["ev"]["reasons"])
    return c.most_common(4)


def _activities(spec, t, res, tot, ptot, cur, prev, acts, amount) -> dict:
    fmt = _codes_or_percent(spec, t["id"])
    grid: dict = {}
    filled_groups: set[str] = set()                         # a group's activities fill its first illustrative row only
    for r in t["rows"]:
        fr = res["rows"][r["id"]]
        if not fr.get("activity_slot") and (fr.get("heading") or (fr.get("group") and not fr.get("total"))):
            continue                                        # a section heading ('A.1. …'), not a row of figures
        if fr.get("activity_slot"):
            group = fr.get("group")
            if group is None:                               # 2026/73 Template 2: one list of the aligned activities
                group = "aligned"
            if group in filled_groups:
                continue                                    # a further illustrative row of the same group
            filled_groups.add(group)
            keys = [k for k in acts if amount(cur, group, k)]
            for n, k in enumerate(keys):
                grid[f"{r['id']}:{n}"] = _activity_row(res, k, acts[k], group, tot, ptot, cur, prev, amount, fmt)
            grid[r["id"]] = {"_first_of_group": True, "_n": len(keys)}
            continue
        total = fr.get("total")
        row = {}
        for cid, fc in res["columns"].items():
            m = fc.get("measure")
            bk, base = (prev, ptot) if fc.get("period") == "previous" else (cur, tot)
            g = "all" if total == "all" else total
            if m == "amount":
                row[cid] = amount(bk, g, category=fr.get("category"))
            elif m == "proportion":
                row[cid] = _pct(amount(bk, g, objective=fc.get("objective") if fc.get("status") == "aligned" else None,
                                       category=fr.get("category")), base)
            elif m == "aligned_in_eligible":
                row[cid] = _pct(amount(bk, "aligned"), amount(bk, "eligible"))
        grid[r["id"]] = row
    return grid


def _activity_row(res, key, act, group, tot, ptot, cur, prev, amount, fmt) -> dict:
    row = {"_activity": act["title"], "_codes": key}
    for cid, fc in res["columns"].items():
        m, crit, obj = fc.get("measure"), fc.get("criterion"), fc.get("objective")
        if fc.get("label") == "activity":
            row[cid] = act["title"]
        elif fc.get("label") == "code":
            row[cid] = key
        elif m == "amount":
            row[cid] = amount(prev if fc.get("period") == "previous" else cur, group, key)
        elif m == "proportion":
            bk, base = (prev, ptot) if fc.get("period") == "previous" else (cur, tot)
            row[cid] = _pct(amount(bk, group, key, objective=obj if fc.get("status") == "aligned" else None), base)
        elif m == "aligned_in_eligible":
            row[cid] = _pct(amount(cur, "aligned", key), amount(cur, "eligible", key))
        elif crit == "sc" and obj:
            if fmt == "percent":
                row[cid] = _pct(amount(cur, group, key, objective=obj), tot) if group == "aligned" else None
            elif group == "aligned":
                row[cid] = "Y" if obj == "ccm" else ("N" if obj in act["objectives"] else "N/EL")
            else:
                row[cid] = "EL" if obj in act["objectives"] else "N/EL"
        elif crit == "dnsh" and obj:
            row[cid] = "Y" if group == "aligned" else None   # 7.7: adaptation by Appendix A; the other four 'N/A'
        elif crit == "ms":
            row[cid] = "Y" if group == "aligned" else None
        elif m == "category":
            row[cid] = ({"enabling": "E", "transitional": "T"}[fc["category"]]
                        if act.get("category") == fc["category"] else None)
    return row


def _objectives(res, tot, cur, amount) -> dict:
    """The per-objective table: the aligned and the eligible proportion of the KPI, objective by objective."""
    grid = {}
    for rid, fr in res["rows"].items():
        o = fr.get("objective")
        grid[rid] = {cid: _pct(amount(cur, fc["status"], objective=o), tot)
                     for cid, fc in res["columns"].items() if fc.get("measure") == "proportion" and fc.get("status")}
    return grid


def _summary(res, tot, ptot, cur, prev, amount) -> dict:
    grid = {}
    names = {"turnover": "Turnover", "capex": "CapEx", "opex": "OpEx"}
    for rid, fr in res["rows"].items():
        if fr.get("kpi") != "turnover":                     # CapEx / OpEx: the undertaking's ledger
            grid[rid] = {cid: (names.get(fr.get("kpi"), "") if fc.get("label") == "kpi" else {"_input": "ledger"})
                         for cid, fc in res["columns"].items()}
            continue
        row = {}
        for cid, fc in res["columns"].items():
            m, st, obj = fc.get("measure"), fc.get("status"), fc.get("objective")
            if fc.get("label") == "kpi":
                row[cid] = names["turnover"]
                continue
            bk, base = (prev, ptot) if fc.get("period") == "previous" else (cur, tot)
            if fc.get("input"):
                row[cid] = {"_input": fc["input"]}
            elif m == "amount":
                row[cid] = base if st == "all" else amount(bk, st, category=fc.get("category"))
            elif m == "proportion":
                row[cid] = _pct(amount(bk, st, objective=obj if st == "aligned" else None, category=fc.get("category")), base)
        grid[rid] = row
    return grid



# ───────────────────────────── the binding (for coverage and supplied cells) ─────────────────────────────

def binding(spec: dict) -> dict:
    """How every row and column of this version is filled: 'computed:…' from the property book, 'input:ledger' where
    the undertaking enters its CapEx / OpEx, 'n/a' for section headings. A template disclosed once per KPI carries
    'bases' (the KPIs) and 'input_bases' (the KPIs it enters) — a supplied cell names it: 'T2@capex.r3.6'."""
    out = {}
    for t in spec["templates"]:
        res = V.resolve(spec, t["id"])
        kpis = V.kpis_of(spec, t["id"])
        entered = res["kind"] in V.vocabulary(FAMILY)["inputs"] or kpis in (["capex"], ["opex"])
        why = "nuclear_gas" if res["kind"] == "nuclear_gas" else "ledger"
        rows = {}
        for rid, fr in res["rows"].items():
            heading = not fr.get("activity_slot") and (fr.get("heading") or (fr.get("group") and not fr.get("total")))
            if heading:
                rows[rid] = "n/a"
            elif entered or fr.get("kpi") in ("capex", "opex"):
                rows[rid] = f"input:{why}"
            else:
                rows[rid] = "computed:activity" if fr.get("activity_slot") else "computed:total"
        cols = {cid: (f"input:{fc['input']}" if fc.get("input") else f"input:{why}" if entered else
                      f"computed:{fc.get('measure') or fc.get('criterion') or fc.get('label') or 'value'}")
                for cid, fc in res["columns"].items()}
        b = {"rows": rows, "columns": cols}
        if len(kpis) > 1 and res["kind"] != "kpi_summary":
            b.update(bases=kpis, input_bases=[k for k in kpis if k != "turnover"])
        out[t["id"]] = b
    return out


def summary(properties: list[dict]) -> dict:
    """The turnover split every surface shows (form data tab, pre-filing checks, export): total, eligible, aligned
    (A.1), eligible but not aligned (A.2), alignment not known, non-eligible — and each building's verdict."""
    bk = _book(properties)
    tot = sum(b["x"] for b in bk)
    parts = {"eligible": sum(b["x"] for b in bk if b["act"]),
             "aligned": sum(b["x"] for b in bk if _group(b) == "aligned"),
             "not_aligned": sum(b["x"] for b in bk if _group(b) == "eligible_not_aligned"),
             "unknown": sum(b["x"] for b in bk if b["act"] and b["aligned"] is None),
             "non_eligible": sum(b["x"] for b in bk if not b["act"])}
    return {"turnover": tot, **parts, "pct": {k: _pct(v, tot) for k, v in parts.items()},
            "noi_proxy": sum(1 for b in bk if b["proxy"]), "noi_proxy_turnover": sum(b["x"] for b in bk if b["proxy"]),
            "n": len(bk), "n_unknown": sum(1 for b in bk if b["act"] and b["aligned"] is None),
            "unknown_reasons": _top_reasons([b for b in bk if b["act"] and b["aligned"] is None]),
            "buildings": [{"name": p.get("property_name") or p.get("entity_name"), "turnover": b["x"], "noi_proxy": b["proxy"],
                           "activity": " / ".join(b["act"]["codes"]) if b["act"] else None,
                           "aligned": b["aligned"] if b["act"] else None,
                           "why": "; ".join(b["ev"]["reasons"]) if b["act"] else "not eligible"}
                          for p, b in zip(properties, bk)]}
