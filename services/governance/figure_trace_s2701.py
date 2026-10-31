"""The trace of one cell of a Solvency II nat-cat filing — S.27.01.01, or a group's S.27.01.04 (s2701.tid_of) — on the
figure_trace graph, read from what the filing froze:

  the cell        its row and column as the frozen specification prints them, the instructions naming it (quoted), its
                  value as the form shows it (s2701.grid on the frozen standard-formula result and attested premiums)
  the formula     the frozen standard-formula line the cell is read from (a region, the other regions, a peril, the
                  nat-cat total), on the version of Delegated Regulation 2015/35 the result records
  statements      what the cell rests on that the filer attested: the reinsurance treaty for a figure after risk
                  mitigation, the premiums to be earned for the other regions, and for a group the method of each related
                  undertaking (payload '_group_solvency'); a missing one is the formula's own message
  the book        the policies placed in the cell's region by the rule the formula used (solvency2_natcat.placement),
                  tied to the printed exposure and count; for a group, through the undertaking each belongs to, as the
                  filing froze its entities (payload '_consolidation'), method-2 undertakings shown left out
The standard formula reads sum insured, country, postal code and cover — never a hazard score — so no hazard feed is in
this trace; the formula's own tables are.
"""
from __future__ import annotations

import re

import services.regspec as R
from core.errors import UserError
from core.messages import render
from services.governance import s2701
from services.governance import solvency2_natcat as N
from services.governance import solvency2_natcat_tables as T
from services.governance.figure_trace import Graph, quote_of, regulatory, sources, statement

_KEY = re.compile(r"(S270[14])\.(R\d{4})\.(C\d{4})")
_TREATY_ROLES = {"mitigation", "reinstatement", "after"}       # columns the attested treaty changes
_WITH_OTHER = {"total_other", "total_all", "diversification", "total_after", "peril", "nat_cat"}


def is_cell(cell: str) -> bool:
    return bool(_KEY.fullmatch(cell or ""))


def _version(sf: dict) -> dict | None:
    return next((v for v in T.rules()["versions"] if v["id"] == sf.get("version")), None)


def _value_kind(column_role: str | None) -> str:
    return {"factor": "ratio", "scenario": "text", "simplification": "text"}.get(column_role or "", "money")


def _perils_of(c: dict, sf: dict) -> list[str]:
    """The perils a cell reads: its own, or every peril computed for the nat-cat total and its diversification."""
    if c["peril"]:
        return [c["peril"]]
    return [p for p, r in (sf.get("perils") or {}).items() if r.get("available")]


def _member(c: dict, at: dict, region_methods: dict[str, str]) -> bool:
    """Whether a placed policy is part of what the cell reports."""
    role = c["row_role"]
    if role == "region":
        return at.get("region") == c["region"]
    if role == "total_specified":
        return bool(at.get("region"))
    if role == "total_other":
        return bool(at.get("other"))
    if role == "simplification":
        return bool(at.get("region")) and at.get("zone") is None and region_methods.get(at["region"]) == "grouped_art90b"
    if role in _WITH_OTHER:
        return bool(at.get("region")) or bool(at.get("other"))
    return False                                                # a premium cell: stated, not computed from the book


def _formula(g: Graph, c: dict, sf: dict, v: dict | None, ccy: str) -> str:
    """The frozen standard-formula line the cell is read from, with the act of the formula in the law layer."""
    perils = sf.get("perils") or {}
    pr = perils.get(c["peril"]) or {} if c["peril"] else {}
    facts: dict = {"version": (v or {}).get("name") or sf.get("version_name"), "reference_date": sf.get("reference_date"),
                   "currency": ccy, "peril": c["peril"], "citation": pr.get("citation")}
    msgs: list = []
    role = c["row_role"]
    if role == "region" or (role == "total_specified" and c["peril"] == "subsidence"):
        line = next((x for x in pr.get("regions") or [] if x["region"] == c["region"]), None)
        if line is None:
            msgs.append(render("trace.formula.nothing"))
        else:
            facts.update({k: line.get(k) for k in ("region_name", "n_policies", "exposure_eur", "specified_gross_loss_eur",
                                                   "charge_factor", "scenario", "before_eur", "mitigation_eur",
                                                   "reinstatement_eur", "after_eur")})
            msgs.append(line.get("method_message"))
            if c["peril"] == "subsidence" and pr.get("before_zone_diversification"):
                facts["zones_before_diversification"] = pr["before_zone_diversification"]
    elif role in ("other_region", "total_other"):
        o = pr.get("other_regions") or {}
        facts.update({k: o.get(k) for k in ("exposure_eur", "premium_eur", "div", "factor", "before_eur", "mitigation_eur",
                                            "reinstatement_eur", "after_eur")})
        msgs.append(o.get("message"))
    elif c["peril"]:
        facts.update({k: pr.get(k) for k in ("regions_before_eur", "regions_after_eur", "all_before_eur", "all_after_eur",
                                             "diversification_before_eur", "diversification_after_eur", "before_eur",
                                             "after_eur")})
        facts["n_regions"] = len(pr.get("regions") or [])
        msgs += pr.get("missing") or []
    elif role == "simplification":
        facts["grouped"] = [{"peril": p, "regions": [x["region_name"] for x in r.get("regions") or []
                                                      if x.get("method") == "grouped_art90b"]}
                            for p, r in perils.items() if r.get("available")]
    else:                                                     # the nat-cat total and the diversification between perils
        facts.update({"before_eur": sf.get("natcat_scr_before_mitigation_eur"), "after_eur": sf.get("natcat_scr_eur"),
                      "diversification_before_eur": sf.get("diversification_between_perils_before_eur"),
                      "diversification_after_eur": sf.get("diversification_between_perils_after_eur"),
                      "by_peril_eur": sf.get("scr_by_peril_eur")})
        msgs += sf.get("missing") or []
    facts["readings"] = sf.get("readings")
    node = g.add("formula", "basis", "formula", None, facts=facts, msgs=msgs,
                 tone="warn" if (pr if c["peril"] else sf).get("complete") is False else None)
    if v is not None:
        from services.reference import legal_texts as L
        held = next((cx for cx in L.manifest() if cx in (v.get("source") or "")), None)
        act = g.add("act-formula", "law", "act", v.get("name"), tone="good" if held else "warn",
                    facts={"role": "formula", "source": v.get("source"), "text_held": bool(held), "held_as": held,
                           "applies_from": (v.get("applies") or {}).get("from"),
                           "applies_until": (v.get("applies") or {}).get("until")})
        g.link(act, node)
    return node


def _statements(g: Graph, c: dict, spec: dict, tid: str, sf: dict, payload: dict, cell: str) -> list[str]:
    """The attested values the cell rests on, or the formula's message where one is missing."""
    attested = {a["key"].removeprefix("provided."): a for a in payload.get("_provided_attested") or []}
    out: list[str] = []
    role, col_role = c["row_role"], c["column_role"]
    if col_role in _TREATY_ROLES and role not in ("other_region",):
        if sf.get("treaty_basis") == "attested":
            from services.insurer_capital import REINSTATEMENT, TREATY
            out += [statement(g, attested[k]) for k in (*TREATY, *REINSTATEMENT) if k in attested]
        else:
            out.append(g.add("stmt-treaty", "basis", "statement", None, tone="warn",
                             msgs=[sf.get("treaty_message") or render("solvency.reinsurance.not_attested")]))
    if role == "other_region" or role in _WITH_OTHER:
        rows = s2701.other_region_rows(spec, tid)
        cols = s2701.premium_column(spec, tid)
        label = {r["id"]: r["label"] for r in R.template(spec, tid)["rows"]}
        wanted = [(p, rid) for p in _perils_of(c, sf) for rid in (rows.get(p) or {}).values()]
        if role == "other_region":
            wanted = [(c["peril"], c["row"])]
        for p, rid in wanted:
            key = f"{tid}.{rid}.{cols.get(p)}"
            if key in attested:
                out.append(statement(g, attested[key], label.get(rid)))
            elif role == "other_region":
                out.append(g.add(f"stmt-{key}", "basis", "statement", label.get(rid), tone="warn",
                                 msgs=[render("trace.gap.premium_not_stated")]))
    return out


def _group(g: Graph, payload: dict) -> dict:
    """A group's undertakings as the filing froze them: {entity: undertaking id}, their nodes, the method statements."""
    st = payload.get("_group_solvency") or {}
    ents = {e["entity_id"]: e for e in (payload.get("_consolidation") or {}).get("entities") or []}
    method = {u["entity_id"]: u for u in st.get("undertakings") or []}
    from services.governance.group_solvency import CHOICES
    stmts = {}
    for u in st.get("undertakings") or []:
        stated = u.get("method") in CHOICES
        stmts[u["entity_id"]] = g.add(f"method-{u['entity_id']}", "basis", "method", u["name"],
                                      tone="good" if stated else "warn",
                                      facts={"method": CHOICES.get(u.get("method")), "attested_by": u.get("attested_by"),
                                             "attested_at": u.get("attested_at")},
                                      msgs=[] if stated else [render("trace.gap.method_not_stated", name=u["name"])])

    def undertaking_of(eid: str | None) -> str | None:
        cur = eid
        while cur in ents and (ents[cur].get("kind") or "").strip().lower() == "branch" and ents[cur].get("parent_entity_id"):
            cur = ents[cur]["parent_entity_id"]
        return cur
    return {"entities": ents, "method": method, "statements": stmts, "undertaking_of": undertaking_of,
            "group_id": st.get("group_entity_id"), "recorded": bool(ents)}


def trace(g: Graph, session, filing: dict, payload: dict, cell: str) -> dict:
    from services.governance.filing_annex import _supplied
    from services.governance.insurer_solvency import natcat_block
    from services.governance.money_format import presentation_of
    tid, row, col = _KEY.fullmatch(cell).groups()
    sf = natcat_block(payload).get("standard_formula_natcat") or {}
    rec = (payload.get("_specs") or {}).get(s2701.FAMILY) or {}
    if tid != s2701.tid_of(payload) or not rec.get("version") or "version" not in sf:
        raise UserError("trace.cell.unknown")
    spec = R.load(s2701.FAMILY, rec["version"])
    try:
        c = s2701.cell_of(spec, tid, row, col)
    except KeyError as e:
        raise UserError("trace.cell.unknown") from e
    if not c["reportable"]:
        raise UserError("trace.cell.greyed")
    ccy = presentation_of(payload)

    spec_node = regulatory(g, session, payload, s2701.FAMILY)
    ins = [g.add(f"instruction-{i}", "spec", "instruction", x.get("item"), quote=quote_of(x.get("quote"), x.get("ref")),
                 facts={"ref": x.get("ref"), "printed_ref": x.get("printed_ref")})
           for i, x in enumerate(s2701.instructions_for(spec, tid, row, col))]
    for n in ins:
        g.link(spec_node, n)
    t = R.template(spec, tid)
    value = (s2701.grid(spec, sf, _supplied(payload), tid).get(row) or {}).get(col)
    cell_facts = {"template": t["code"], "row": row, "column": col, "row_label": c["row_label"],
                  "column_label": c["column_label"], "section": c["section"], "value": value, "currency": ccy,
                  "value_kind": _value_kind(c["column_role"]), "row_source": (c["row_source"] or "").split(":")[0],
                  "column_source": (c["column_source"] or "").split(":")[0], "period": payload.get("_period")}
    cell_node = g.add("cell", "cell", "cell", c["row_label"], facts=cell_facts)
    for n in ins or [spec_node]:
        g.link(n, cell_node)

    v = _version(sf)
    formula = _formula(g, c, sf, v, ccy)
    g.link(cell_node, formula)
    for s in _statements(g, c, spec, tid, sf, payload, cell):
        g.link(cell_node, s)

    # the book: every policy the cell's peril(s) place where the cell reports, by the formula's own rule
    members: dict[str, dict] = {}
    if v is not None and c["row_role"] != "other_region":
        for p in _perils_of(c, sf):
            table = N.peril_table(v, p)
            if not table:
                continue
            methods = {x["region"]: x.get("method") for x in (sf.get("perils") or {}).get(p, {}).get("regions") or []}
            for pol in payload.get("policies") or []:
                at = N.placement(pol, p, v=v, table=table, uk_reading=sf.get("uk_reading") or "region_only")
                if at and not at.get("unlocated") and _member(c, at, methods):
                    m = members.setdefault(pol["policy_id"], {"pol": pol, "si": 0.0, "zone": at.get("zone"),
                                                              "region": at.get("region")})
                    m["si"] = max(m["si"], at["si"]) if not c["peril"] else at["si"]
    ranked = sorted(members.values(), key=lambda m: -m["si"])
    tie = None
    if c["row_role"] == "region" or (c["row_role"] == "total_specified" and c["peril"] == "subsidence"):
        line = next((x for x in (sf.get("perils") or {}).get(c["peril"], {}).get("regions") or []
                     if x["region"] == c["region"]), None)
        if line is not None:
            traced = round(sum(m["si"] for m in ranked))
            tie = {"printed_exposure": line["exposure_eur"], "traced_exposure": traced,
                   "printed_n": line["n_policies"], "traced_n": len(ranked),
                   "ties": traced == line["exposure_eur"] and len(ranked) == line["n_policies"]}
            g.get(cell_node).setdefault("facts", {})["tie"] = tie

    book_nodes: list[str] = []

    def policies(group: str, items: list[dict], parent: str, undertaking: str | None = None) -> None:
        shown, hidden = g.capped(group, items)
        for m in shown:
            pol = m["pol"]
            n = g.add(f"policy-{pol['policy_id']}", "book", "policy", pol.get("policy_name"), group=group,
                      facts={"country": pol.get("country"), "postal_code": pol.get("postal_code"), "zone": m.get("zone"),
                             "sum_insured": round(m["si"]), "currency": ccy, "undertaking": undertaking,
                             "policy_type": pol.get("policy_type")})
            g.link(parent, n)
            book_nodes.append(n)
        mn = g.more(group, "book", hidden, [parent])
        if mn:
            book_nodes.append(mn)

    if tid == s2701.GROUP_TID:
        G = _group(g, payload)
        for s in G["statements"].values():
            g.link(cell_node, s)
        if not G["recorded"]:
            g.note(formula, render("trace.gap.undertaking_not_recorded"))
            policies("policies", ranked, formula)
        else:
            by_und: dict[str, list] = {}
            all_by_und: dict[str, int] = {}
            for pol in payload.get("policies") or []:
                u = G["undertaking_of"](pol.get("reporting_entity_id"))
                all_by_und[u] = all_by_und.get(u, 0) + 1
            for m in ranked:
                by_und.setdefault(G["undertaking_of"](m["pol"].get("reporting_entity_id")), []).append(m)
            for eid in sorted(set(by_und) | set(G["method"]), key=lambda e: (G["entities"].get(e) or {}).get("name") or ""):
                e, u = G["entities"].get(eid) or {}, G["method"].get(eid) or {}
                out = u.get("method") == "method_2"
                items = by_und.get(eid) or []
                un = g.add(f"undertaking-{eid}", "book", "undertaking", e.get("name") or u.get("name"),
                           tone="out" if out else None,
                           facts={"method": u.get("method"), "weight": e.get("weight"),
                                  "consolidation_method": e.get("consolidation_method"),
                                  "ownership_pct": e.get("ownership_pct"), "n_policies": len(items),
                                  "sum_insured": round(sum(m["si"] for m in items)), "currency": ccy,
                                  "n_policies_left_out": all_by_und.get(eid, 0) if out else None},
                           msgs=[render("trace.book.left_out")] if out else [])
                g.link(formula, un)
                g.link(G["statements"].get(eid), un)
                book_nodes.append(un)
                policies(f"policies-{eid}", items, un, e.get("name"))
    else:
        policies("policies", ranked, formula)

    attested = {a["key"].removeprefix("provided.") for a in payload.get("_provided_attested") or []}
    if c["row_role"] == "other_region" and cell in attested:           # the premium the filer entered and had attested
        g.note(formula, render("trace.book.premium_stated"))

    sources(g, filing.get("run"), [n for n in book_nodes if not n.startswith("undertaking-")] or book_nodes)
    if v is not None:
        tables = g.add("tables", "source", "tables", None, tone="good",
                       facts={"version": v.get("name"), "source": v.get("source"), "peril": c["peril"]})
        g.link(formula, tables)
    return {"cell": {**cell_facts, "key": cell, "tie": tie}}
