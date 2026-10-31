"""Whose book a KRI set is on: one filer's (E351).

Since E348–E350 a report whose act names its filers (services.governance.report_filers) is filed by one filer at a time,
keyed by (entity, role): a group on its consolidated figures, an undertaking or institution on its own. Its KRIs read
the same book. The live value is on the filer's scope — the entities its filing covers, weighted by how each
consolidates, group-internal exposures removed (filings._book_basis, the very book its filing freezes). The filed
trend reads that filer's filings only. Each drill-down reads the same scoped book, so it sums to the figure it explains.

The board opens on the report at the head of the structure, on its consolidated figures — the level each text names
for the consolidated report:
  bank_p3esg        "institutions should disclose the information at the highest level of consolidation in the EU"
                    (EBA Q&A 2023_6708 and 2022_6652, QA below; CRR Art. 13(1), first subparagraph)
  bank_tcfd         a credit institution's KPIs "on the basis of the scope of their prudential consolidation"
                    (Delegated Regulation (EU) 2021/2178, Annex V, 1.1.1)
  reit_taxonomy     "at the level of the group where the undertaking prepares consolidated non-financial statements"
                    (Delegated Regulation (EU) 2021/2178, Annex I, 1.2(f))
  insurer_solvency  the group's S.27.01.04, by the undertaking "at the head of the insurance or reinsurance group"
                    (Implementing Regulation (EU) 2023/894, Annex III, S.01.02)
That is: exactly one filer at the top of the tree reporting for its group; else the only filer; else the board asks
which (as the ESRS set does, services.governance.kri_esrs). Every other filer is offered by name; one chosen is shown,
not monitored (kri_monitor watches the default only). No filer for the year is a named gap, never the whole book.

Unchanged: an organisation with fewer than two reporting entities, one that is itself the filer (report_filers.is_filer:
it records no undertaking of its own), and a report without filer rules (SFDR; the ESRS set picks its own undertaking)
keep the whole book and every filing in the trend.

Money stays in the engine's currency, EUR — the board's and its appetite bands' (multi-currency decision 3): the
scope's book is read as stored, never re-translated, with the consolidation weights and the eliminations its filing
applies. A filed money figure joins the trend only when its filing is presented in EUR (kri_t5's rule, every figure).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

FRAMEWORKS = frozenset({"bank_tcfd", "bank_p3esg", "reit_taxonomy", "insurer_solvency"})
VERTICAL = {"bank_tcfd": "banking", "bank_p3esg": "banking", "reit_taxonomy": "realestate", "insurer_solvency": "insurance"}
BOOK_CCY = "EUR"
# EBA Single Rulebook Q&A read for the default (checked 2026-10-31): id → (status, submitted, published, the answer)
QA = {
    "checked": "2026-10-31",
    "2023_6708": ("Final", "30 Jan 2023", "25 Aug 2023",
                  "institutions should disclose the information at the highest level of consolidation in the EU"),
    "2022_6652": ("Final", "07 Dec 2022", "10 Mar 2023", "at the highest level of consolidation in the EU"),
}
# why the board opens on the head's report: the sentence in customer words (with the legal reference, shown in the pop-up
# only), and the words of the text it rests on — each in its rule's QUOTES (checked word for word against
# data/sources/legal) or, for Pillar 3, the EBA's answer above (tests/unit/test_kri_scope.py)
HEAD = {
    "bank_p3esg": ("Pillar 3 ESG is disclosed at the highest level of consolidation in the EU (EBA Q&A 2023_6708; "
                   "Regulation (EU) No 575/2013, Art. 13(1))",
                   ("crr_filers", "CRR Art. 13(1), first subparagraph", "on the basis of their consolidated situation")),
    "bank_tcfd": ("A credit institution reports its EU Taxonomy KPIs on the scope of its prudential consolidation "
                  "(Delegated Regulation (EU) 2021/2178, Annex V, 1.1.1)",
                  ("csrd_filers", "Del. Reg. 2021/2178 Annex V, 1.1.1", "on the basis of the scope of their prudential consolidation")),
    "reit_taxonomy": ("An undertaking that prepares consolidated statements reports its EU Taxonomy KPIs at the level of "
                      "the group (Delegated Regulation (EU) 2021/2178, Annex I, 1.2(f))",
                      ("csrd_filers", "Del. Reg. 2021/2178 Annex I, 1.2(f)",
                       "at the level of the group where the undertaking prepares consolidated non-financial statements")),
    "insurer_solvency": ("The group's natural catastrophe report is submitted by the undertaking at the head of the group "
                         "(Implementing Regulation (EU) 2023/894, Annex III, S.01.02)",
                         ("sii_filers", "ITS Annex III S.01.02 C0010/R0010", "at the head of the insurance or reinsurance group")),
}


class NoFiler(ValueError):
    """No one filer to show: none files the report for the year, several could open the board, or the one asked for is
    not a filer. `notice` says which in the catalogue's words (kri.filer.*); `filers` are the ones to choose from."""

    def __init__(self, code: str, filers: list[dict], **params):
        from core import messages
        super().__init__(code)
        self.notice = messages.render(code, **params)
        self.filers = filers


@dataclass(frozen=True)
class Scope:
    framework: str
    filer: dict                       # {entity_id, name, role, label}
    filers: list[dict]
    period_end: date
    entity_ids: list[str]
    value_weights: dict | None
    base: object                      # the filing's translation plan, re-presented in EUR (copied fresh per book)
    default: bool
    period_label: str = ""            # the period's label — FY2026, or FY2026-H1 for a half-year (E354)

    def book(self) -> dict:
        """The keyword arguments a sector's build_disclosure_snapshot (and the report freezes) take for this book."""
        t = self.base
        fresh = None if t is None else replace(t, rates_used={}, per_entity={}, eliminations=[],
                                               unexplained={"n": 0, "value": 0.0})
        return {"entity_ids": self.entity_ids, "value_weights": self.value_weights, "translation": fresh}

    def shares(self, session: Session, org_id: str) -> dict[str, float]:
        """Each asset of the scope's book → the share of its stored value the book counts (its entity's consolidation
        weight, less what is eliminated as group-internal) — for the figures read off the stored book, not the snapshot
        (the forward projection, the tested yearly loss). An asset outside the scope is absent."""
        from services.governance.translation import elimination_share
        rows = session.execute(text("""
            SELECT entity_id::text AS entity_id, reporting_entity_id::text AS reporting_entity_id,
                   intragroup_entity_id::text AS intragroup_entity_id
            FROM portfolio_entities WHERE org_id = CAST(:o AS uuid) AND vertical = :v
              AND reporting_entity_id = ANY(CAST(:ids AS uuid[]))"""),
            {"o": org_id, "v": VERTICAL[self.framework], "ids": self.entity_ids}).mappings()
        out = {}
        for r in rows:
            w = (self.value_weights or {}).get(r["reporting_entity_id"], 1.0)
            kept = 1.0 - (elimination_share(self.base, r) if self.base is not None else 0.0)
            if w * kept > 0:
                out[r["entity_id"]] = w * kept
        return out


def label(f: dict) -> str:
    """A filer as the picker names it: the entity, '(group)' for its consolidated report."""
    return f"{f['name']} (group)" if f["role"] == "consolidated" else f["name"]


def _whole_book(session: Session, org_id: str, framework: str) -> bool:
    from services.governance import report_filers as RF
    if framework not in FRAMEWORKS:
        return True
    n = session.execute(text("SELECT count(*) FROM reporting_entities WHERE org_id = CAST(:o AS uuid)"), {"o": org_id}).scalar()
    return n < 2 or RF.is_filer(session, org_id)


def pick(filers: list[dict], tops: set[str]) -> dict | None:
    """The filer the board opens on: the one at the top of the tree (`tops`) reporting for its group; else the only
    filer; else None (the board asks which)."""
    head = [f for f in filers if f["role"] == "consolidated" and f["entity_id"] in tops]
    if len(head) == 1:
        return head[0]
    return filers[0] if len(filers) == 1 else None


def default(session: Session, org_id: str, filers: list[dict]) -> dict | None:
    from services.governance import report_filers as RF
    return pick(filers, {e["entity_id"] for e in RF.entities(session, org_id) if e["parent_entity_id"] is None})


def resolve(session: Session, org_id: str, framework: str, entity_id: str | None = None,
            role: str | None = None) -> Scope | None:
    """The filer scope a KRI set is on — None for the whole book (the unchanged cases). NoFiler when there is no one
    filer to show."""
    if _whole_book(session, org_id, framework):
        return None
    from services.governance import filings as F
    from services.governance import report_filers as RF
    pe, kind = F.reporting_period(session, org_id)
    filers = [{**f, "label": label(f)} for f in RF.choices(session, org_id, framework, pe)]
    d = default(session, org_id, filers)
    filers = [{**f, "default": d is not None and (f["entity_id"], f["role"]) == (d["entity_id"], d["role"])} for f in filers]
    year, report = F.period_label(pe, kind), F.FRAMEWORKS[framework]["label"]
    if entity_id is not None:
        filer = next((f for f in filers if f["entity_id"] == str(entity_id) and role in (None, f["role"])), None)
        if filer is None:
            raise NoFiler("kri.filer.not_found", filers, report=report, year=year)
    else:
        filer = next((f for f in filers if f["default"]), None)
        if filer is None:
            if not filers:
                raise NoFiler("kri.filer.none", [], report=report, year=year,
                              shows=(RF.scope_basis(framework) or {}).get("shows") or "")
            raise NoFiler("kri.filer.choose", filers, report=report, year=year,
                          choices=", ".join(f["label"] for f in filers))
    # the filing's own scope and book (filings._scope_role / _book_basis): only a report of _OWN_BOOK takes the role
    frole = F._scope_role(session, org_id, framework, filer["entity_id"], filer["role"] if framework in F._OWN_BOOK else None)
    ids, weights, t = F._book_basis(session, org_id, framework, filer["entity_id"], pe, frole)
    base = None if t is None else replace(t, presentation=BOOK_CCY, functional={k: BOOK_CCY for k in t.functional})
    return Scope(framework, filer, filers, pe, ids, weights, base, filer["default"], year)


def message(scope: Scope) -> dict:
    """Whose figures the board shows, for its basis line and pop-up (kri.filer.scope.*)."""
    from core import messages
    f = scope.filer
    who = f"{f['name']}, on its {'consolidated' if f['role'] == 'consolidated' else 'own'} figures"
    book = ("its entities, each weighted by how it consolidates, with the exposures between them removed"
            if f["role"] == "consolidated" else "its own book, its branches included")
    if not scope.default:
        d = default_name(scope)
        return messages.render("kri.filer.scope.chosen", who=who, book=book, default=d or "—")
    code = ("kri.filer.scope.only" if f["role"] != "consolidated"
            else "kri.filer.scope.head" if len(scope.filers) > 1 else "kri.filer.scope.head_alone")
    return messages.render(code, who=who, book=book, why=HEAD[scope.framework][0],
                           year=scope.period_label or f"FY{scope.period_end.year}")


def default_name(scope: Scope) -> str | None:
    """The label of the filer the board opens on, when the shown one was chosen."""
    d = next((f for f in scope.filers if f.get("default")), None)
    return d["label"] if d else None


def history_filter(scope: Scope | None) -> tuple[str, dict]:
    """SQL (filing alias rf) and its values: a filer's filings only — by entity, and by role where one entity holds two
    reports (filings._role_match); the whole book reads every filing."""
    if scope is None:
        return "", {}
    from services.governance.filings import _role_match
    return (f" AND rf.entity_id = CAST(:scope_e AS uuid) AND {_role_match('rf', 'CAST(:scope_e AS uuid)', 'CAST(:scope_r AS text)')}",
            {"scope_e": scope.filer["entity_id"], "scope_r": scope.filer["role"]})


def eur_only(history: list[dict]) -> list[dict]:
    """A filed money figure counts for the trend only from a filing presented in the book's currency (EUR): figures in
    two currencies are not one trend (kri_t5's rule, for every money figure)."""
    for h in history:
        if (h.get("currency") or BOOK_CCY) == BOOK_CCY:
            continue
        for f in h.get("figures") or []:
            if f.get("fmt") == "eur":
                f["value"] = None
        for k in ("total_value", "value_at_risk"):
            if k in h:
                h[k] = None
    return history
