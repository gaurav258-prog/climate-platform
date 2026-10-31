"""The trace of one cell of a Pillar 3 ESG filing's Template 5 (banking book, physical risk) on the figure_trace graph,
read from what the filing froze — the data side is the existing cell trace, services.governance.pillar3_lineage:

  the cell        its row (a sector, or real estate), its column and geography, the value printed and the sum of its
                  contributors, which must agree
  instructions    the instructions of the frozen specification that name the cell's column ('column b', 'columns c-o')
  how computed    the sum (column g: the weighted average maturity) over the exposures of the row the template counts,
                  on the at-risk level the institution stated for the period — a statement with who attested it
  the book        the exposures, each with its contribution and the hazards that make it sensitive
  sources         per hazard, the scored records those exposures sit on (a model re-run since is flagged) and the feeds
                  the hazard is derived from; the run that read the book
"""
from __future__ import annotations

import re

import services.regspec as R
from core.errors import UserError
from core.messages import render
from services.governance.figure_trace import Graph, quote_of, regulatory, sources, statement

FAMILY = "bank_p3esg"
_KEY = re.compile(r"T5\.([0-9A-Za-z_]+)\.([a-z])(?:@([A-Z0-9_?-]{1,12}))?")    # '?': geography not stated
_COLS = re.compile(r"columns?\s+([a-z])(?:\s*[–-]\s*([a-z]))?\b")


def is_cell(cell: str) -> bool:
    return bool(_KEY.fullmatch(cell or ""))


def key(row: str, column: str, geography: str = "ALL") -> str:
    """The trace key of a Template 5 cell: 'T5.<row>.<column>' for all geographies, '@<geography>' for one."""
    return f"T5.{row}.{column}" + ("" if geography == "ALL" else f"@{geography}")


def instructions_for(spec: dict, column: str) -> list[dict]:
    """The instructions of Template 5 that name this column, alone or in a range of columns."""
    out = []
    for i in R.template(spec, "T5").get("instructions") or []:
        m = _COLS.search(i.get("ref") or "")
        if m and (m.group(1) <= column <= (m.group(2) or m.group(1))):
            out.append(i)
    return out


def trace(g: Graph, session, filing: dict, payload: dict, cell: str) -> dict:
    from services.governance.filing_annex import _p3_spec
    from services.governance.pillar3_lineage import t5_cell_lineage
    row, column, geo = _KEY.fullmatch(cell).groups()
    try:
        d = t5_cell_lineage(session, filing["org_id"], filing["filing_id"], row, column, geo or "ALL")
    except (ValueError, KeyError) as e:
        raise UserError("trace.cell.unknown") from e
    if not d.get("supported"):
        return {"cell": None, "unsupported_msg": d.get("msg")}
    spec = _p3_spec(payload)
    ccy = d.get("currency")
    spec_node = regulatory(g, session, payload, FAMILY)
    ins = [g.add(f"instruction-{i}", "spec", "instruction", x.get("ref"), quote=quote_of(x.get("quote"), x.get("ref")),
                 facts={"ref": x.get("ref")}) for i, x in enumerate(instructions_for(spec, column))]
    for n in ins:
        g.link(spec_node, n)
    c = d["cell"]
    kind = "years" if c["kind"] == "weighted_average" else "money"
    cell_facts = {"template": R.template(spec, "T5")["code"], "row": row, "column": column,
                  "row_label": d["row"]["label"], "column_label": d["column"]["label"].split(" > ")[-1],
                  "column_path": d["column"]["label"], "geography": d["geography"]["label"], "value": c["printed"],
                  "currency": ccy, "value_kind": kind, "period": payload.get("_period")}
    tie = {"printed": c["printed"], "traced": c["from_contributors"], "traced_n": len(d["contributors"]),
           "ties": c["ties"], "kind": c["kind"]}
    cell_node = g.add("cell", "cell", "cell", d["row"]["label"], facts={**cell_facts, "tie": tie},
                      tone="good" if c["ties"] else "warn")
    for n in ins or [spec_node]:
        g.link(n, cell_node)

    rule = g.add("rule", "basis", "rule", None,
                 facts={"kind": c["kind"], "at_risk_level": d.get("at_risk_level"), "n_in_row": d.get("n_in_row"),
                        "n_contributors": len(d["contributors"]), "scenario": (d.get("basis") or {}).get("scenario"),
                        "horizon": (d.get("basis") or {}).get("horizon"), "currency": ccy})
    g.link(cell_node, rule)
    level = next((u for u in (payload.get("method") or {}).get("used") or []
                  if u and u.get("key") == "method.at_risk_level" and u.get("member") is None), None)
    if level is not None:
        from services.money.params import parameters
        s = statement(g, {"key": "method.at_risk_level", "value": level.get("value"), "unit": "score",
                          "attested_by": level.get("attested_by"), "attested_at": level.get("attested_at")},
                      parameters()["method.at_risk_level"]["short"])
        g.link(cell_node, s)

    shown, hidden = g.capped("exposures", d["contributors"])
    book: list[str] = []
    scores: dict[str, str] = {}
    for x in shown:
        n = g.add(f"exposure-{x['asset_id']}", "book", "exposure", x.get("asset_name"), group="exposures",
                  facts={"amount": x.get("amount"), "weight": x.get("weight"), "maturity": x.get("maturity"),
                         "gross_carrying_amount": x.get("gross_carrying_amount_eur"), "country": x.get("country"),
                         "nace_code": x.get("nace_code"), "ifrs9_stage": x.get("ifrs9_stage"), "currency": ccy,
                         "hazards": [{"hazard": h["hazard"], "score": (h.get("filed") or {}).get("score"),
                                      "drift": h.get("drift")} for h in x.get("hazards") or []]},
                  tone="warn" if any(h.get("drift") for h in x.get("hazards") or []) else None)
        g.link(rule, n)
        book.append(n)
        for h in x.get("hazards") or []:
            hz = h["hazard"]
            if hz not in scores:
                hits = [y for y in d["contributors"] for k in y.get("hazards") or [] if k["hazard"] == hz]
                drift = sum(1 for y in d["contributors"] for k in y.get("hazards") or [] if k["hazard"] == hz and k.get("drift"))
                models = sorted({(k.get("filed") or {}).get("model_version") for y in d["contributors"]
                                 for k in y.get("hazards") or [] if k["hazard"] == hz} - {None})
                scores[hz] = g.add(f"score-{hz}", "source", "score", None, tone="warn" if drift else "good",
                                   facts={"hazard": hz, "n_exposures": len(hits), "drift": drift, "models": models})
                for f in (d.get("sources") or {}).get(hz) or []:
                    fn = g.add(f"feed-{f['key']}", "source", "feed", f.get("name"),
                               tone={"fresh": "good", "live": "good", "overdue": "warn", "failed": "warn"}.get(f.get("status") or ""),
                               facts={"status": f.get("status"), "last_refresh": f.get("last_refresh"),
                                      "maturity": f.get("maturity")})
                    g.link(scores[hz], fn)
            g.link(n, scores[hz])
    m = g.more("exposures", "book", hidden, [rule])
    if m:
        book.append(m)
    if not d["contributors"]:
        g.note(rule, render("trace.formula.no_exposure"))
    sources(g, filing.get("run"), book)
    return {"cell": {**cell_facts, "key": cell, "tie": tie}}
