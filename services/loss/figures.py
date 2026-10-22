"""The one door through which anything outside the loss engine reads loss figures (the product owner's decision of
2026-10-20: filings, risk indicators and decisions take only tested loss figures; held and untested ones are shown
for reference on the loss screen, never carried further).

  tested(session, org_id, book, …)   the book's latest run (by sequence) and its tested figures only — standing
                                     'published' — each with the value its curve applies to (or, for an issuer's site,
                                     the share of that value: the share columns); every other figure is counted by its
                                     standing (and a gap by its code), never handed out — only which asset and peril it
                                     was and why (its standing, or its gap code and values), for a screen to name

The loss screen's own API (api/routers/loss.py) shows every figure with its standing; any other reader of
loss_results or loss_ep_points goes through here — tests/unit/test_loss_one_door.py fails when one does not.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

TESTED = "published"


def tested(session: Session, org_id: str, book: str, scenario: str = "baseline",
           horizon: str = "current") -> Optional[dict]:
    """{run_id, as_of, figures: [tested figure per asset and peril], withheld: {standing or 'gap': count},
    gaps: {gap code: count}, not_carried: [{asset_kind, asset_id, peril, standing, gap_code, gap_params}]}; None when the
    book has no run for this scenario and horizon."""
    run = session.execute(text("""
        SELECT run_id::text, as_of FROM loss_runs
        WHERE org_id = CAST(:o AS uuid) AND book = :b AND scenario = :s AND time_horizon = :h
        ORDER BY seq DESC LIMIT 1"""), {"o": org_id, "b": book, "s": scenario, "h": horizon}).mappings().first()
    if run is None:
        return None
    rows = session.execute(text("""
        SELECT asset_kind, asset_id::text, peril, curve_key, standing, gap IS NOT NULL OR gap_code IS NOT NULL AS is_gap,
               gap_code, CAST(exposed_value_eur AS FLOAT) AS exposed_value_eur, CAST(eal_eur AS FLOAT) AS eal_eur,
               CAST(eal_low_eur AS FLOAT) AS eal_low_eur,
               CAST(eal_high_eur AS FLOAT) AS eal_high_eur, CAST(eal_defended_eur AS FLOAT) AS eal_defended_eur,
               CAST(eal_defended_low_eur AS FLOAT) AS eal_defended_low_eur,
               CAST(eal_defended_high_eur AS FLOAT) AS eal_defended_high_eur, protection_rp_years, loss_at_rp,
               eal_ratio, eal_ratio_low, eal_ratio_high, eal_defended_ratio, eal_defended_ratio_low,
               eal_defended_ratio_high, ratio_at_rp, gap_params
        FROM loss_results WHERE run_id = CAST(:r AS uuid) ORDER BY asset_id, peril"""), {"r": run["run_id"]}).mappings()
    figures, withheld, gaps, not_carried = [], {}, {}, []
    for r in rows:
        if not r["is_gap"] and r["standing"] == TESTED:
            figures.append({k: v for k, v in r.items() if k not in ("standing", "is_gap", "gap_code", "gap_params")})
        else:
            k = "gap" if r["is_gap"] else r["standing"]
            withheld[k] = withheld.get(k, 0) + 1
            if r["is_gap"]:
                gaps[r["gap_code"]] = gaps.get(r["gap_code"], 0) + 1
            not_carried.append({"asset_kind": r["asset_kind"], "asset_id": r["asset_id"], "peril": r["peril"],
                                "standing": None if r["is_gap"] else r["standing"], "gap_code": r["gap_code"],
                                "gap_params": r["gap_params"]})
    return {"run_id": run["run_id"], "as_of": run["as_of"].isoformat(), "figures": figures, "withheld": withheld,
            "gaps": gaps, "not_carried": not_carried}
