"""A fund's SFDR template answers — the governing sfdr_product annex for the fund's classification, answered in the
one store of template answers (services.governance.template_answers) — and the live (unfrozen) document. A periodic
answer belongs to one reference period; a pre-contractual one stands until changed."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

import services.regspec as R
from services.governance import product_filings as P
from services.governance import sfdr_product as S
from services.governance import template_answers as T
from services.governance.template_answers import (
    AnswerError,  # noqa: F401 — raised to callers of this module
)

DOCUMENTS = {"precontractual": "sfdr_precontractual", "periodic": "sfdr_periodic"}


def _context(session: Session, org_id: str, fund_id: str, document: str, on: date | None = None) -> tuple[dict, dict, dict, date | None]:
    if document not in DOCUMENTS:
        raise AnswerError("document is 'precontractual' or 'periodic'")
    fund = P.fund_of(session, org_id, fund_id)
    if fund is None:
        raise AnswerError("fund not found")
    try:
        P.check(session, org_id, DOCUMENTS[document], None, fund_id)
    except P.ProductScopeError as e:
        raise AnswerError(str(e)) from e
    from services.governance.filings import reporting_period_end
    period = reporting_period_end(session, org_id) if document == "periodic" else None
    spec = R.governing(S.FAMILY, period_end=period or date.today(), disclosure_date=on)
    if spec is None:
        raise AnswerError("no adopted SFDR template specification governs today")
    t = R.template(spec, P.annex(DOCUMENTS[document], fund["sfdr_classification"]))
    return fund, spec, t, period


def save(session: Session, org_id: str, fund_id: str, document: str, answers: dict, user_id: str | None) -> dict:
    """Validate every answer against the governing template, store the valid ones (services.governance.template_answers),
    report the refused ones."""
    fund, spec, t, period = _context(session, org_id, fund_id, document)
    return T.save(session, org_id, S.FAMILY, document, t, S.binding(spec)[t["id"]]["items"], answers, user_id,
                  fund_id=fund_id, period_end=period, label=f"{t['code']} of {spec['act']['short']}",
                  computed_from="the fund")


def live(session: Session, org_id: str, fund_id: str, document: str) -> dict:
    """The fund's document as it stands now (not frozen): every item of the governing template with its value."""
    from services.governance.sfdr_product_forms import missing
    fund, spec, t, period = _context(session, org_id, fund_id, document)
    book = S.freeze(session, org_id, fund_id, document, period or date.today())
    built = S.build(spec, t["id"], book)
    return {"fund": {"fund_id": fund_id, "name": fund["name"], "sfdr_classification": fund["sfdr_classification"]},
            "document": document, "report_type": DOCUMENTS[document], "template": t["id"], "title": t["title"],
            "citation": R.citation(spec, t["id"]), "spec_version": spec["version"], "period_end": period and period.isoformat(),
            "items": built, "missing": [m["id"] for m in missing(built)],
            "unmapped": {k: v for k, v in book["answers"].items() if k.startswith(("legacy.", "website."))},
            "interpretations": [i for i in spec.get("interpretations") or [] if i.get("resolves", {}).get("template") == t["id"]]}
