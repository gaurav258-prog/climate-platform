"""The tested-loss risk indicator (losses into decisions, the product owner's decisions of 2026-10-22), shared by the
bank, insurer and REIT sets: the book's tested yearly loss today (services.loss.signals.yearly_loss) — only figures
whose damage curve passed its test, flood at the lead the institution states. No report prints it (live only), and
the platform sets no appetite for it: it is ungraded until the organisation sets its own band (kri_threshold).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

KEY = "tested_yearly_loss"


def tested_loss_kpi(session: Session, org_id: str, scope=None) -> dict:
    """scope: one filer's book (services.governance.kri_scope) — each tested figure at its asset's share of that book,
    the figures of assets outside it left out; None = the whole book."""
    from core import messages
    from services.governance.kri import _amount, _kpi, fact, msg
    from services.loss.signals import yearly_loss
    y = yearly_loss(session, org_id)
    if scope is not None:
        shares = scope.shares(session, org_id)
        y["figures"] = [{**f, "loss_eur": f["loss_eur"] * shares[f["asset_id"]]} for f in y["figures"] if f["asset_id"] in shares]
        if y["value"] is not None:
            y["value"] = sum(f["loss_eur"] for f in y["figures"])
    w = y["withheld"]
    facts = []
    if y["run_id"]:
        facts = [fact("loss_run_date", y["as_of"], "text"), fact("tested_figures", len(y["figures"]), "num")]
        if scope is None:                     # what was withheld is counted for the whole book only
            facts += [fact("figures_not_tested", w.get("held", 0) + w.get("untested", 0), "num"),
                      fact("figures_missing", w.get("gap", 0), "num")]
        if y["headline"] and any(f["peril"] == "flood" for f in y["figures"]):
            facts.append(fact("flood_lead", messages.name("loss.flood_lead", y["headline"]), "text"))
    return _kpi(KEY, "Tested yearly loss", _amount(y["value"]), "eur", tone="#fb7185",
                about=msg("kri.indicator.tested_yearly_loss"), facts=facts,
                missing=msg(y["why"]) if y["why"] else None)
