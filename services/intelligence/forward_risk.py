"""Forward-change decision signal — the customer's 'what changes, when, and what do I do' view.

Turns the engine's banded scenario projections into a portfolio DECISION brief, per warming pathway:
  • the €-at-risk TRAJECTORY (value whose worst hazard crosses the High threshold) today → 2030/2050/
    2100, with the CMIP6/AR6 model-disagreement band (an honest range, not a point);
  • NEW crossings — value that deteriorates from below-High today into High+ by each horizon;
  • the MOVERS — the assets driving the deterioration (Δscore × value);
  • the RUNWAY — the earliest horizon at which a material share newly crosses (the 'act by' signal).

This is the input a credit officer / PM / underwriter acts on (reprice / engage / divest) AND the
forward-looking scenario analysis mandated by TCFD / IFRS S2 / the ECB climate stress test. It reads
the same `v_portfolio_entity_physical_risk` the rest of the financial engine uses — one honest source.
`heat_acute` is excluded from the headline (today's live reading, not a standing projection), matching
the portfolio engine's convention.
"""
from __future__ import annotations
from typing import Optional

from sqlalchemy import text

HORIZONS = ["2030", "2050", "2100"]
AT_RISK = 50.0            # High+ boundary (score ≥ 50 = H/VH bucket) — the decision line
MATERIALITY = 0.05        # a horizon is the 'runway' when newly-crossing value ≥ 5% of the book


def forward_risk(session, org_id: str, vertical: str, scenario: str,
                 at_risk: float = AT_RISK) -> dict:
    """Forward-risk decision brief for one portfolio (org × vertical) under one scenario."""
    # the WORST priceable hazard per (entity, horizon) — and ITS OWN band (DISTINCT ON, not a MIN/MAX
    # across hazards, which would borrow a low-scoring hazard's band onto the headline).
    rows = session.execute(text("""
        SELECT DISTINCT ON (v.entity_id, v.time_horizon)
               e.entity_id::text AS eid, e.entity_name,
               CAST(e.primary_value_eur AS FLOAT) AS val,
               v.time_horizon AS horz, v.physical_risk_score AS sc,
               v.physical_risk_ci_lower AS lo, v.physical_risk_ci_upper AS hi
        FROM portfolio_entities e
        JOIN v_portfolio_entity_physical_risk v ON v.entity_id = e.entity_id
        WHERE e.org_id = :o AND e.vertical = :vert AND v.hazard_type <> 'heat_acute'
          AND ( (v.scenario = :scen AND v.time_horizon <> 'current')
                OR (v.scenario = 'baseline' AND v.time_horizon = 'current') )
        ORDER BY v.entity_id, v.time_horizon, v.physical_risk_score DESC
    """), {"o": org_id, "vert": vertical, "scen": scenario}).mappings().all()

    # pivot to per-entity {horizon: (score, lo, hi)}
    ent: dict = {}
    for r in rows:
        d = ent.setdefault(r["eid"], {"name": r["entity_name"], "val": r["val"] or 0.0, "h": {}})
        d["h"][r["horz"]] = (r["sc"], r["lo"], r["hi"])

    book = sum(d["val"] for d in ent.values())
    # today's at-risk value (the baseline of the trajectory — no band, no crossing)
    at_now = sum(d["val"] for d in ent.values()
                 if (d["h"].get("current", (None,))[0] or 0) >= at_risk)
    trajectory = [{"horizon": "current", "at_risk_eur": round(at_now, 2),
                   "at_risk_pct": round(100 * at_now / book, 1) if book else 0.0,
                   "at_risk_band_eur": [round(at_now, 2), round(at_now, 2)],
                   "newly_crossing_eur": 0.0, "newly_crossing_count": 0}]
    runway = None
    for hz in HORIZONS:
        at_c = at_lo = at_hi = newx = 0.0
        n_new = 0
        for d in ent.values():
            cur = d["h"].get("current", (None,))[0]
            fut = d["h"].get(hz)
            if fut is None:
                continue
            sc, lo, hi = fut
            v = d["val"]
            if sc is not None and sc >= at_risk:
                at_c += v
            if lo is not None and lo >= at_risk:
                at_lo += v
            at_hi += v if ((hi if hi is not None else sc) or 0) >= at_risk else 0
            if cur is not None and cur < at_risk and sc is not None and sc >= at_risk:
                newx += v; n_new += 1
        trajectory.append({
            "horizon": hz,
            "at_risk_eur": round(at_c, 2), "at_risk_pct": round(100 * at_c / book, 1) if book else 0.0,
            "at_risk_band_eur": [round(at_lo, 2), round(at_hi, 2)],
            "newly_crossing_eur": round(newx, 2), "newly_crossing_count": n_new,
        })
        if runway is None and book and newx / book >= MATERIALITY:
            runway = hz

    # movers: biggest adverse migration (Δscore × value) at the furthest horizon that has data
    last = next((h for h in reversed(HORIZONS) if any(h in d["h"] for d in ent.values())), None)
    movers = []
    if last:
        for d in ent.values():
            cur = d["h"].get("current", (None,))[0]
            fut = d["h"].get(last, (None,))[0]
            if cur is None or fut is None:
                continue
            movers.append({"entity_name": d["name"], "current_score": round(cur, 1),
                           "future_score": round(fut, 1), "delta": round(fut - cur, 1),
                           "value_eur": round(d["val"], 2), "horizon": last})
        movers.sort(key=lambda m: -(max(0.0, m["delta"]) * m["value_eur"]))
        movers = [m for m in movers if m["delta"] > 0][:5]

    return {
        "scenario": scenario, "vertical": vertical, "book_eur": round(book, 2),
        "at_risk_threshold": at_risk, "entities": len(ent),
        "trajectory": trajectory, "movers": movers, "runway": runway,
        "basis": "worst priceable hazard per asset vs the High (score≥50) line; band = CMIP6/AR6 "
                 "across-model disagreement; heat_acute excluded from the headline.",
    }
