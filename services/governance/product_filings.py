"""Filings whose subject is a financial product (a fund), not a legal entity: the SFDR pre-contractual and periodic
templates (Annexes II–V to Delegated Regulation (EU) 2022/1288) are disclosed per product.

A product-scoped report type needs a fund of the organisation that promotes E/S characteristics (Art. 8) or has a
sustainable investment objective (Art. 9) — that decides which annex applies — and never an entity scope. Everything
else about the filing (freeze, four-eyes review, attest, export, restate) is the ordinary lifecycle in filings.py.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages
from core.errors import UserError

# report type -> the document it is (template_answers.document) and the annex per SFDR article
PRODUCT_SCOPED = {
    "sfdr_precontractual": {"document": "precontractual", "annex": {"article_8": "AII", "article_9": "AIII"}},
    "sfdr_periodic": {"document": "periodic", "annex": {"article_8": "AIV", "article_9": "AV"}},
}


class ProductScopeError(UserError, ValueError):
    """A scope a product report refuses, as a message-catalogue code with its values (UI standard, 2026-10-16): the API answers it as a UserError
    (core/errors.py); str() is the catalogue's sentence."""

    def __str__(self) -> str:
        return messages.render(self.code, **self.params)["detail"]["what"]


def fund_of(session: Session, org_id: str, fund_id: str) -> dict | None:
    import uuid
    try:
        uuid.UUID(str(fund_id))
    except ValueError:
        return None
    r = session.execute(text("""
        SELECT fund_id::text AS fund_id, name, lei, sfdr_classification, base_currency
        FROM funds WHERE fund_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"""),
        {"f": fund_id, "o": org_id}).mappings().first()
    return dict(r) if r else None


def check(session: Session, org_id: str, framework: str, entity_id: str | None, fund_id: str | None) -> dict | None:
    """The fund a filing of this report type is about (None for a report type that is not product-scoped). Refuses a
    fund scope on an entity-level report, a product report without its fund, another organisation's fund, and a fund
    outside Art. 8 / 9."""
    spec = PRODUCT_SCOPED.get(framework)
    if spec is None:
        if fund_id is not None:
            raise ProductScopeError("filing.refused.not_per_product")
        return None
    if entity_id is not None:
        raise ProductScopeError("filing.refused.per_product_not_entity")
    if fund_id is None:
        raise ProductScopeError("filing.refused.choose_fund")
    fund = fund_of(session, org_id, fund_id)
    if fund is None:
        raise ProductScopeError("filing.refused.fund_not_found")
    if fund["sfdr_classification"] not in spec["annex"]:
        raise ProductScopeError("filing.refused.fund_not_classified", fund=fund["name"])
    return fund


def annex(framework: str, sfdr_classification: str) -> str:
    return PRODUCT_SCOPED[framework]["annex"][sfdr_classification]


def funds_owing(session: Session, org_id: str) -> list[dict]:
    """The organisation's Art. 8 / 9 funds (top-level: a sub-fund's disclosure is its own product only if it is one)."""
    return [dict(r) for r in session.execute(text("""
        SELECT fund_id::text AS fund_id, name, sfdr_classification FROM funds
        WHERE org_id = CAST(:o AS uuid) AND sfdr_classification IN ('article_8', 'article_9')
        ORDER BY name"""), {"o": org_id}).mappings().all()]


def preflight_summary(session: Session, org_id: str, framework: str, fund_id: str, period_end) -> dict:
    """The confirm-data step for a fund's document: its holdings in the reference period, and how many of the
    template's items are answered — over exactly what the filing will freeze."""
    import services.regspec as R
    from services.governance import sfdr_product as S
    from services.governance.sfdr_product_forms import missing
    doc = PRODUCT_SCOPED[framework]["document"]
    book = S.freeze(session, org_id, fund_id, doc, period_end)
    spec = R.governing(S.FAMILY, period_end=period_end)
    gaps = []
    if spec is None:
        return {"coverage": None, "total_value_eur": None, "noun": "items", "gaps": [messages.render("filing.gap.no_spec")]}
    tid = annex(framework, book["fund"]["sfdr_classification"])
    built = S.build(spec, tid, book)
    todo = [i for i in built if i["source"] != "fixed"]
    open_ = missing(built)
    if doc == "periodic" and not book["holdings"]:     # the pre-contractual document computes nothing from holdings
        gaps.append(messages.render("filing.gap.no_holdings"))
    if open_:
        gaps.append(messages.render("filing.gap.unanswered", n=len(open_)))
    total = sum(h["value"] for h in book["holdings"]) / max(1, len(book["position_dates"]))
    return {"coverage": {"label": "template items answered", "done": len(todo) - len(open_), "total": len(todo),
                         "pct": round(100 * (len(todo) - len(open_)) / len(todo), 1) if todo else 0},
            "total_value_eur": round(total, 2), "value_at_risk_eur": None, "noun": "holdings",
            "positions": len({h["issuer_id"] for h in book["holdings"]}), "gaps": gaps,
            "fund": {"fund_id": fund_id, "name": book["fund"]["name"], "template": tid}}
