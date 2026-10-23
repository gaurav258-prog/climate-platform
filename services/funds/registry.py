"""A fund as the manager states it (E144): its name, what it is, the SFDR article it discloses under (Regulation (EU)
2019/2088 Art. 6, 8 or 9 — the manager's classification, never defaulted), its base currency (ISO 4217); a sub-portfolio
names the fund it belongs to; a fund LEI is optional and verified against GLEIF like every LEI.

  check(session, org_id, …)     the stated fund, refused in the catalogue's words where it cannot stand
  create(session, org_id, …)    the fund written and audited
  update(session, org_id, …)    an existing fund's stated type, article, currency, parent or LEI changed and audited
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.errors import UserError

FUND_TYPES = ("fund", "sub_portfolio", "mandate", "fund_of_funds")
SFDR_ARTICLES = ("article_6", "article_8", "article_9")
_LEI_REFUSAL = {"invalid": "disclose.fund.lei.invalid", "unknown": "disclose.fund.lei.unknown",
                "unreachable": "disclose.fund.lei.unreachable"}


def verified_lei(lei: str):
    """An LEI checked against GLEIF (services.reference.gleif.verified_lei), or the refusal in the catalogue's words:
    malformed, not in the register, or the register unreachable."""
    from services.reference import gleif
    try:
        return gleif.verified_lei(lei)
    except gleif.LeiError as e:
        raise UserError(_LEI_REFUSAL.get(e.kind, "disclose.fund.lei.invalid"), lei=(lei or "").strip().upper()) from e


def check(session: Session, org_id: str, *, name: str, fund_type: str, sfdr_classification: str, base_currency: str,
          parent_fund_id: Optional[str] = None, lei: Optional[str] = None, existing_id: Optional[str] = None) -> dict:
    """The fund as it will be stored. `existing_id`: the fund being restated (its own name is not a duplicate)."""
    from services.reference import iso4217
    name = (name or "").strip()
    ccy = (base_currency or "").strip().upper()
    if ccy not in iso4217.codes():
        raise UserError("disclose.fund.refused.currency", currency=base_currency)
    if fund_type not in FUND_TYPES or sfdr_classification not in SFDR_ARTICLES:
        raise UserError("disclose.fund.refused.kind")
    if session.execute(text("""SELECT 1 FROM funds WHERE org_id = CAST(:o AS uuid) AND lower(name) = lower(:n)
                               AND fund_id IS DISTINCT FROM CAST(:x AS uuid)"""),
                       {"o": org_id, "n": name, "x": existing_id}).first():
        raise UserError("disclose.fund.refused.duplicate", name=name)
    parent = str(parent_fund_id) if parent_fund_id else None
    if (fund_type == "sub_portfolio") != (parent is not None):
        raise UserError("disclose.fund.refused.parent")
    if parent and not session.execute(text("SELECT 1 FROM funds WHERE fund_id = CAST(:p AS uuid) AND org_id = CAST(:o AS uuid)"),
                                      {"p": parent, "o": org_id}).first():
        raise UserError("disclose.fund.refused.parent")
    return {"name": name, "fund_type": fund_type, "sfdr_classification": sfdr_classification, "base_currency": ccy,
            "parent_fund_id": parent, "lei": verified_lei(lei).lei if (lei or "").strip() else None}


def create(session: Session, org_id: str, fund: dict, *, actor_id: Optional[str]) -> str:
    """Write a fund already checked (check()) and audit it. Returns its id."""
    from api.services.rbac import write_audit
    fid = session.execute(text("""
        INSERT INTO funds (org_id, name, fund_type, sfdr_classification, base_currency, parent_fund_id, lei)
        VALUES (CAST(:o AS uuid), :n, :t, :a, :c, CAST(:p AS uuid), :lei) RETURNING fund_id::text"""),
        {"o": org_id, "n": fund["name"], "t": fund["fund_type"], "a": fund["sfdr_classification"],
         "c": fund["base_currency"], "p": fund["parent_fund_id"], "lei": fund["lei"]}).scalar()
    write_audit(session, org_id=org_id, actor_user_id=actor_id, action="fund.created", target_type="fund", target_id=fid,
                detail=dict(fund))
    return fid


def update(session: Session, org_id: str, fund_id: str, fund: dict, *, actor_id: Optional[str]) -> None:
    """Restate an existing fund (checked with check(existing_id=…)) and audit what it now states."""
    from api.services.rbac import write_audit
    session.execute(text("""
        UPDATE funds SET name = :n, fund_type = :t, sfdr_classification = :a, base_currency = :c,
               parent_fund_id = CAST(:p AS uuid), lei = COALESCE(:lei, lei), updated_at = now()
        WHERE fund_id = CAST(:f AS uuid) AND org_id = CAST(:o AS uuid)"""),
        {"f": fund_id, "o": org_id, "n": fund["name"], "t": fund["fund_type"], "a": fund["sfdr_classification"],
         "c": fund["base_currency"], "p": fund["parent_fund_id"], "lei": fund["lei"]})
    write_audit(session, org_id=org_id, actor_user_id=actor_id, action="fund.restated", target_type="fund",
                target_id=fund_id, detail=dict(fund))
