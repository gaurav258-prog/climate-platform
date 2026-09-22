"""IFRS S2 Climate-related Disclosures, paragraph 16(a) — actual, incurred current-period financial effects.

Verified against the issued standard text (IFRS Foundation, issbs2.html): paragraph 15 introduces the financial
-effects disclosure; paragraph 16 details it — (a) "how climate-related risks and opportunities have affected
its financial position, financial performance and cash flows FOR THE REPORTING PERIOD" (backward-looking,
ACTUAL), (b) risks with a significant risk of material adjustment next period, (c)-(d) expected/ANTICIPATED
changes over the short/medium/long term. ¶16(a) is therefore the separate, backward-looking half of the SAME
paragraph as the anticipated figures — not, as an earlier draft of this gap assumed, paragraph 22 (which is
climate-RESILIENCE / scenario analysis, a different requirement entirely).

The platform already covers ¶16(c)-(d) — the ANTICIPATED financial effects — via the modelled expected annual
loss (ml/scoring/cat_accumulation.py) and the NatCat SCR, both internal-model and prescribed standard-formula
(services/governance/solvency2_natcat.py, services/governance/insurer_solvency.py). ¶16(a) — actual, INCURRED
losses for the reporting period — had zero coverage anywhere in services/intelligence, services/governance or
kri.py: this module closes that gap.

Honesty discipline (same as EVIC / REIT gross revenue): actual incurred claims are real financial data the
platform cannot compute or observe itself — it must come from the insurer's own claims/financial records,
customer-supplied via POST /v1/insurance/incurred-losses (api/routers/insurance.py). Never fabricated, never
silently zeroed, and never silently omitted from the disclosure: when nothing has been supplied yet the summary
says so explicitly (status: "not_yet_supplied").
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import text

REGULATION = "IFRS S2 Climate-related Disclosures, paragraph 16(a) — current-period financial effects"


def submit_incurred_loss(session, org_id: str, period_start, period_end, peril: str,
                          gross_incurred_loss_eur: float, net_incurred_loss_eur: float | None = None,
                          source: str = "client", created_by: str | None = None) -> dict:
    """Record one actual incurred NatCat loss for a (org, reporting period, peril). Additive: a second
    submission for the same period+peril is a SEPARATE record (e.g. a claims-development update), never an
    overwrite — the summary rolls them up, so restating history stays visible in the raw list."""
    row = session.execute(text("""
        INSERT INTO insurer_incurred_losses
            (org_id, period_start, period_end, peril, gross_incurred_loss_eur, net_incurred_loss_eur,
             source, created_by)
        VALUES (CAST(:org AS uuid), :ps, :pe, :peril, :gross, :net, :source, CAST(:by AS uuid))
        RETURNING loss_id::text AS loss_id, reported_at
    """), {"org": org_id, "ps": period_start, "pe": period_end, "peril": peril,
           "gross": gross_incurred_loss_eur, "net": net_incurred_loss_eur,
           "source": source, "by": created_by}).mappings().first()
    return dict(row)


def list_incurred_losses(session, org_id: str) -> list[dict]:
    """Every incurred-loss record on file for this org, newest reporting period first — the raw ledger behind
    the rollup, and what /v1/insurance/incurred-losses (GET) returns."""
    rows = session.execute(text("""
        SELECT loss_id::text AS loss_id, period_start, period_end, peril,
               CAST(gross_incurred_loss_eur AS FLOAT) AS gross_incurred_loss_eur,
               CAST(net_incurred_loss_eur AS FLOAT) AS net_incurred_loss_eur,
               source, reported_at
        FROM insurer_incurred_losses
        WHERE org_id = CAST(:org AS uuid)
        ORDER BY period_start DESC, peril
    """), {"org": org_id}).mappings().all()
    return [dict(r) for r in rows]


def incurred_loss_summary(session, org_id: str, modeled: dict | None = None) -> dict:
    """The ¶16(a) actual-incurred-loss disclosure: rolled up by peril and by reporting period. When `modeled`
    is passed (the ¶16(c)-(d) anticipated figures — EAL, standard-formula/internal-model NatCat SCR, from the
    caller's already-computed disclosure snapshot), it is surfaced ALONGSIDE the actual figures so a reader can
    compare "what we modelled" vs "what actually happened" — the whole point of ¶16 having both a backward- and
    forward-looking half. Honest gap: when nothing has been supplied, says so explicitly rather than a silent
    zero or a dropped section."""
    rows = list_incurred_losses(session, org_id)
    return summarize_incurred_losses(rows, modeled=modeled)


def summarize_incurred_losses(rows: list[dict], modeled: dict | None = None) -> dict:
    """Pure rollup over already-fetched incurred-loss rows (peril + period), independent of the DB — the
    testable core of incurred_loss_summary."""
    if not rows:
        return {
            "framework": "ifrs_s2_incurred_losses",
            "regulation": REGULATION,
            "status": "not_yet_supplied",
            "note": ("No actual incurred NatCat losses have been submitted for any reporting period yet. This "
                     "is customer-supplied data — the insurer's own claims/financial records — which the "
                     "platform cannot compute or observe itself. Submit via POST /v1/insurance/incurred-losses."),
            "by_peril": [], "by_period": [], "records": [],
            "modeled": modeled,
        }

    by_peril: dict[str, dict] = defaultdict(lambda: {"gross_incurred_loss_eur": 0.0, "net_incurred_loss_eur": 0.0,
                                                       "has_net": False, "n_records": 0})
    by_period: dict[tuple, dict] = defaultdict(lambda: {"gross_incurred_loss_eur": 0.0, "net_incurred_loss_eur": 0.0,
                                                          "has_net": False, "perils": set()})
    total_gross = 0.0
    total_net = 0.0
    any_net = False
    for r in rows:
        gross = r["gross_incurred_loss_eur"] or 0.0
        net = r["net_incurred_loss_eur"]

        p = by_peril[r["peril"]]
        p["gross_incurred_loss_eur"] += gross
        p["n_records"] += 1
        if net is not None:
            p["net_incurred_loss_eur"] += net
            p["has_net"] = True

        period_key = (r["period_start"], r["period_end"])
        pp = by_period[period_key]
        pp["gross_incurred_loss_eur"] += gross
        pp["perils"].add(r["peril"])
        if net is not None:
            pp["net_incurred_loss_eur"] += net
            pp["has_net"] = True

        total_gross += gross
        if net is not None:
            total_net += net
            any_net = True

    peril_rows = sorted((
        {"peril": k, "gross_incurred_loss_eur": round(v["gross_incurred_loss_eur"]),
         "net_incurred_loss_eur": round(v["net_incurred_loss_eur"]) if v["has_net"] else None,
         "n_records": v["n_records"]}
        for k, v in by_peril.items()
    ), key=lambda r: -r["gross_incurred_loss_eur"])

    period_rows = sorted((
        {"period_start": str(ps), "period_end": str(pe), "gross_incurred_loss_eur": round(v["gross_incurred_loss_eur"]),
         "net_incurred_loss_eur": round(v["net_incurred_loss_eur"]) if v["has_net"] else None,
         "perils": sorted(v["perils"])}
        for (ps, pe), v in by_period.items()
    ), key=lambda r: r["period_start"], reverse=True)

    result = {
        "framework": "ifrs_s2_incurred_losses",
        "regulation": REGULATION,
        "status": "supplied",
        "n_records": len(rows),
        "total_gross_incurred_loss_eur": round(total_gross),
        "total_net_incurred_loss_eur": round(total_net) if any_net else None,
        "by_peril": peril_rows,
        "by_period": period_rows,
        "records": rows,
        "modeled": modeled,
    }
    if modeled is not None:
        result["comparison_note"] = (
            "Actual incurred losses (¶16(a), customer-supplied, backward-looking) shown alongside the "
            "platform's modelled/anticipated figures (¶16(c)-(d): expected annual loss and the standard-formula "
            "/ internal-model NatCat SCR — forward-looking). The two are not directly additive or reconciling: "
            "incurred losses are actual claims for a stated past period; EAL/SCR are model outputs drawn from "
            "the full simulated hazard × return-period distribution. Comparing them over time is itself a "
            "useful calibration signal for the modelled figures.")
    return result
