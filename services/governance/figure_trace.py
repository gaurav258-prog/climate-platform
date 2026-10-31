"""One linkage graph per filed figure — the regulatory trace (services.governance.regulatory_lineage) and the data trace
(services.governance.filing_lineage, engine_runs) of a filing joined at the figure, read only from what it froze.

Layers, left to right:
  law     the act the template is printed under (its quoted basis; is the official text held, is the quote found in it
          word for word) and, for a computed figure, the act its formula comes from
  spec    the specification version frozen with the filing (unchanged since? signed by two people?) and the
          instructions of the template that name the cell, as quoted
  cell    the figure as the form prints it, with how its row and column are filled
  basis   how it was computed (the frozen calculation line) and the statements it rests on — values the undertaking or
          the group provided and a second person attested (who, when), or the message saying one is missing
  book    what it was computed from: a group's undertakings (in, or left out and why) and the policies or exposures,
          capped per group of nodes (expand: show more of a group)
  source  what the calculation read: the book as the run read it (its fingerprint), the last data file landed, the
          reference tables of the formula; for a hazard figure, the scored hazard records and their feeds

A node carries facts (machine keys a screen names in its own words), messages from the catalogue where something is
missing, and a quote where the law is quoted. Nothing is computed again: the frozen calculation is read, and the
book's part of a cell is found with the very rule the calculation used, then tied back to the printed figure.
Per report type, a resolver builds the cell's own layers: figure_trace_s2701 (S.27.01.01 / S.27.01.04),
figure_trace_t5 (Pillar 3 Template 5).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from core.errors import UserError
from core.messages import render

LAYERS = ("law", "spec", "cell", "basis", "book", "source")
CAP = 8            # nodes of a group shown before a "more" node
STEP = 25          # nodes each expansion of a group adds


class Graph:
    """The nodes and edges of one trace, with groups of nodes capped (expand: {group: times expanded})."""

    def __init__(self, expand: dict[str, int] | None = None):
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self._ids: set[str] = set()
        self._pairs: set[tuple[str, str]] = set()
        self.expand = expand or {}

    def add(self, nid: str, layer: str, kind: str, label: str | None = None, *, facts: dict | None = None,
            tone: str | None = None, msgs: list | None = None, quote: dict | None = None,
            group: str | None = None) -> str:
        if layer not in LAYERS:
            raise ValueError(f"no layer {layer}")
        if nid in self._ids:
            return nid
        self._ids.add(nid)
        node: dict = {"id": nid, "layer": layer, "kind": kind, "label": label}
        if facts:
            node["facts"] = {k: v for k, v in facts.items() if v is not None}
        for k, v in (("tone", tone), ("msgs", [m for m in msgs or [] if m]), ("quote", quote), ("group", group)):
            if v:
                node[k] = v
        self.nodes.append(node)
        return nid

    def get(self, nid: str) -> dict:
        return next(n for n in self.nodes if n["id"] == nid)

    def note(self, nid: str, msg: dict | None) -> None:
        """Add a catalogue message to a node already placed."""
        if msg:
            self.get(nid).setdefault("msgs", []).append(msg)

    def link(self, a: str | None, b: str | None) -> None:
        if a and b and a in self._ids and b in self._ids and (a, b) not in self._pairs:
            self._pairs.add((a, b))
            self.edges.append({"source": a, "target": b})

    def capped(self, group: str, items: list) -> tuple[list, int]:
        """The items of a group to show (first CAP, STEP more per expansion) and how many stay hidden."""
        limit = CAP + STEP * max(0, int(self.expand.get(group, 0)))
        return items[:limit], max(0, len(items) - limit)

    def more(self, group: str, layer: str, hidden: int, parents: list[str]) -> str | None:
        """The node standing for a group's hidden items; selecting it expands the group."""
        if hidden <= 0:
            return None
        nid = self.add(f"more-{group}", layer, "more", None, facts={"hidden": hidden, "group": group})
        for p in parents:
            self.link(p, nid)
        return nid

    def out(self) -> dict:
        return {"layers": list(LAYERS), "nodes": self.nodes, "edges": self.edges}


def parse_expand(values: list[str] | None) -> dict[str, int]:
    """'group:n' pairs (a group expanded n times); anything else is ignored."""
    out: dict[str, int] = {}
    for v in values or []:
        group, _, n = (v or "").rpartition(":")
        if group and n.isdigit():
            out[group] = min(int(n), 400)
    return out


def quote_of(text: str | None, ref: str | None = None) -> dict | None:
    """A quote of the law with the stored official text it is found in word for word, and that text's title (None: not
    found in any text held)."""
    if not text:
        return None
    from services.reference import legal_texts as L
    found = L.contains(text)
    return {"text": text, "ref": ref, "found_in": found, "found_in_title": L.title(found) if found else None}


def regulatory(g: Graph, session: Session, payload: dict, family: str) -> str:
    """law → specification for one family as the filing froze it; returns the specification node."""
    from services.governance.regulatory_lineage import family_entry
    rec = (payload.get("_specs") or {}).get(family) or {}
    if not rec.get("version"):
        return g.add(f"spec-{family}", "spec", "spec", None, tone="warn", msgs=[render("trace.gap.no_spec")])
    fe = family_entry(session, family, rec)
    act, sp = fe["act"], fe["spec"]
    q = quote_of(act.get("quote"), act.get("article"))
    a = g.add(f"act-{family}", "law", "act", act.get("title"), quote=q,
              tone="good" if q and q["found_in"] and act.get("text_held") else "warn",
              facts={"role": "template", "official_reference": act.get("celex"), "status": act.get("status"),
                     "article": act.get("article"), "templates_in": act.get("templates_in"),
                     "instructions_in": act.get("instructions_in"), "text_held": act.get("text_held")})
    so = sp.get("signoff_of_frozen_file") or {}
    signed_ok = bool(so.get("approved")) and not so.get("one_person")
    s = g.add(f"spec-{family}", "spec", "spec", None,
              tone="good" if sp.get("changed_since") is False and signed_ok else "warn",
              facts={"version": fe["version"], "changed_since": sp.get("changed_since"),
                     "applies_from": (sp.get("applies") or {}).get("from"),
                     "approved": so.get("approved"), "one_person": so.get("one_person"),
                     "signed": [{"role": x.get("role_label") or x.get("role"), "by": x.get("by"), "at": x.get("signed_at")}
                                for x in so.get("signed") or []],
                     "fingerprint": (sp.get("sha256_frozen") or "")[:16] or None,
                     "readings": [{"subject": i["subject"], "reading": i["reading"]} for i in fe.get("interpretations") or []]})
    g.link(a, s)
    return s


def statement(g: Graph, a: dict, label: str | None = None) -> str:
    """A value the filer provided and a second person attested, as frozen with the filing (payload '_provided_attested')."""
    return g.add(f"stmt-{a['key']}", "basis", "statement", label or a.get("label"), tone="good",
                 facts={"value": a.get("value"), "unit": a.get("unit"), "currency": a.get("currency"),
                        "attested_by": a.get("attested_by"), "attested_at": a.get("attested_at"),
                        "provider": a.get("provider"), "period_end": a.get("reporting_period_end")})


def sources(g: Graph, run: dict | None, froms: list[str]) -> str:
    """What the calculation read: the book as the run read it, and the last data file landed before it."""
    if run is None:
        r = g.add("run", "source", "run", None, tone="warn", msgs=[render("trace.gap.no_run")])
    else:
        inp = run.get("inputs") or {}
        r = g.add("run", "source", "run", None, tone="good" if run.get("status") == "pass" else "warn",
                  facts={"run_at": run.get("created_at"), "status": run.get("status"),
                         "fingerprint": (run.get("inputs_sha256") or "")[:16] or None,
                         "books": [{"label": b.get("label"), "n_assets": b.get("n_assets"),
                                    "total_value_eur": b.get("total_value_eur"),
                                    "fingerprint": (b.get("facts_sha256") or "")[:16] or None}
                                   for b in inp.get("books") or []],
                         "open_differences": inp.get("open_differences")})
        lb = inp.get("last_batch")
        b = g.add("batch", "source", "batch", None, facts={"template": lb.get("template"), "imported_at": lb.get("imported_at")}) \
            if lb else g.add("batch", "source", "batch", None, msgs=[render("trace.gap.no_batch")])
        g.link(r, b)
    for f in froms:
        g.link(f, r)
    return r


def build(session: Session, org_id: str, filing_id: str, cell: str, expand: dict[str, int] | None = None) -> dict:
    """The trace of one figure of a frozen filing: cell is the form's key of it ('S2701.R0530.C0050')."""
    from services.governance.filings import get_filing
    from services.governance.money_format import presentation_of
    f = get_filing(session, org_id, filing_id, with_payload=True)
    if not f:
        raise UserError("error.not_found")
    snap = f.get("snapshot") or {}
    payload = snap.get("payload")
    if not payload:
        raise UserError("trace.not_frozen")
    head = {"filing_id": filing_id, "framework": f["framework"], "period_label": f.get("period_label"),
            "period": payload.get("_period"),         # the period frozen with it: a financial year or its first half
            "status": f["status"], "filing_role": f.get("filing_role"), "currency": presentation_of(payload),
            "hash_verified": snap.get("hash_verified")}
    resolver = _resolver(f["framework"], cell)
    if resolver is None:
        return {"supported": False, "filing": head, "msg": render("trace.unsupported")}
    g = Graph(expand)
    out = resolver(g, session, {**f, "org_id": org_id, "filing_id": filing_id}, payload, cell)
    if out.get("unsupported_msg"):                       # the report's own trace says why it has none
        return {"supported": False, "filing": head, "msg": out["unsupported_msg"]}
    return {"supported": True, "filing": head, **out, **g.out()}


def _resolver(framework: str, cell: str):
    from services.governance import figure_trace_s2701 as S
    from services.governance import figure_trace_t5 as T5
    if framework == "insurer_solvency" and S.is_cell(cell):
        return S.trace
    if framework == T5.FAMILY and T5.is_cell(cell):
        return T5.trace
    return None
