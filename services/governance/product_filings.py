"""Filings whose subject is a financial product (a fund), not a legal entity: the SFDR pre-contractual and periodic
templates (Annexes II–V to Delegated Regulation (EU) 2022/1288) are disclosed per product.

A product-scoped report type needs a fund of the organisation that promotes E/S characteristics (Art. 8) or has a
sustainable investment objective (Art. 9) — that decides which annex applies — and never an entity scope. Everything
else about the filing (freeze, four-eyes review, attest, export, restate) is the ordinary lifecycle in filings.py.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# report type -> the document it is (fund_sfdr_answers.document) and the annex per SFDR article
PRODUCT_SCOPED = {
    "sfdr_precontractual": {"document": "precontractual", "annex": {"article_8": "AII", "article_9": "AIII"}},
    "sfdr_periodic": {"document": "periodic", "annex": {"article_8": "AIV", "article_9": "AV"}},
}


class ProductScopeError(ValueError):
    pass


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
            raise ProductScopeError("this report is not disclosed per financial product — leave the fund out")
        return None
    if entity_id is not None:
        raise ProductScopeError("this report is disclosed per financial product, not per legal entity — choose the fund")
    if fund_id is None:
        raise ProductScopeError("this report is disclosed per financial product — choose the fund")
    fund = fund_of(session, org_id, fund_id)
    if fund is None:
        raise ProductScopeError("fund not found")
    if fund["sfdr_classification"] not in spec["annex"]:
        raise ProductScopeError(f"{fund['name']} is not classified Article 8 or Article 9 under SFDR, so this template "
                                "does not apply — set its SFDR classification first")
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
        return {"coverage": None, "total_value_eur": None, "noun": "items", "gaps": ["no template specification governs"]}
    tid = annex(framework, book["fund"]["sfdr_classification"])
    built = S.build(spec, tid, book)
    todo = [i for i in built if i["source"] != "fixed"]
    open_ = missing(built)
    if not book["holdings"]:
        gaps.append("no holdings on file for the reference period" if doc == "periodic" else "no holdings on file")
    if open_:
        gaps.append(f"{len(open_)} items have no answer yet — answer them on the fund's disclosure page")
    total = sum(h["value"] for h in book["holdings"]) / max(1, len(book["position_dates"]))
    return {"coverage": {"label": "template items answered", "done": len(todo) - len(open_), "total": len(todo),
                         "pct": round(100 * (len(todo) - len(open_)) / len(todo), 1) if todo else 0},
            "total_value_eur": round(total, 2), "value_at_risk_eur": None, "noun": "holdings",
            "positions": len({h["issuer_id"] for h in book["holdings"]}), "gaps": gaps,
            "fund": {"fund_id": fund_id, "name": book["fund"]["name"], "template": tid}}
