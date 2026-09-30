"""Pre-emptive recovery plan — the severe natural-catastrophe stress and the capital indicators of Directive (EU) 2025/1
Art. 5(7) and (8) (specification family irrd_recovery; report type insurer_recovery_stress).

What the platform computes, per the Article's items:
  stress          a severe natural-catastrophe event — the 1-in-200 single event and the 1-in-200 year, net of the
                  attested reinsurance — today and under the undertaking's well-above-2 °C scenario at the nearest
                  horizon, taken from the attested own funds: own funds after the loss, the SCR ratio, whether it
                  breaches the SCR, and which of the plan's trigger levels it crosses (declared reading 'SCR after the
                  event')
  indicators.scr  the capital indicators: the SCR-breach indicator the Article sets as the minimum (100 %) and the
                  undertaking's own attested early-warning and recovery levels, against today's ratio and each stress
Everything else — the other macroeconomic and financial scenarios, the qualitative indicators, the monitoring
arrangements, the remedial action on a breach — is the undertaking's answer (template_answers).
"""
from __future__ import annotations

from datetime import date

FAMILY = "irrd_recovery"
DOCUMENT = "recovery_stress"
COMPUTED = {"stress", "indicators.scr"}
SCR_BREACH_PCT = 100.0                   # Art. 5(8): 'any breach of the Solvency Capital Requirement' — the SCR itself
READINGS = [
    {"subject": "SCR after the event", "declared_by": "Tellumen",
     "reading": "The event's net loss is taken from the attested eligible own funds; the SCR is held at its attested "
                "value. The SCR's own response to the event (less exposure, a reinsurance layer used up) is not "
                "modelled — the coverage ratio shown is that of the loss of own funds alone."},
    {"subject": "Warming horizon", "declared_by": "Tellumen",
     "reading": "A recovery plan is updated at least every two years (Art. 5(4)): the stress under warming uses the "
                "undertaking's well-above-2 °C scenario at the nearest projected horizon, 2030."},
]


def binding(spec: dict) -> dict:
    import services.regspec as R
    return {t["id"]: {"items": {i["id"]: ("computed" if i["id"] in COMPUTED else "input") for i in R.items_to_fill(t)}}
            for t in spec["templates"]}


def compute(session, org_id: str, *, entity_ids=None, value_weights=None, translation=None,
            reporting_entity_id: str | None = None, period_end: date) -> dict:
    from api.routers.insurance import build_disclosure_snapshot, zones_of
    from services.calc_settings import get_calc_settings
    from services.governance.orsa_climate import chosen
    from services.insurer_capital import position
    kw = {"entity_ids": entity_ids, "value_weights": value_weights, "translation": translation,
          "reporting_entity_id": reporting_entity_id}
    warm = chosen(get_calc_settings(session, org_id))["above_2c"]
    today = build_disclosure_snapshot(session, org_id, "baseline", "current", **kw)
    zones = zones_of(today.get("policies") or [])
    warmed = build_disclosure_snapshot(session, org_id, warm, "2030", zones=zones, **kw)
    cap = position(session, org_id, period_end, reporting_entity_id)
    of, scr = cap.get("eligible_own_funds_scr"), cap.get("scr_total")
    triggers = _triggers(session, org_id, period_end, reporting_entity_id)
    events = []
    for label, snap, sc, hz in (("today", today, "baseline", "current"), ("under warming", warmed, warm, "2030")):
        net = (snap.get("reinsurance") or {}).get("net") or {}
        for kind, key in (("1-in-200 single event", "net_oep_eur"), ("1-in-200 year", "net_aep_eur")):
            loss = (net.get(key) or {}).get("rp_200")
            after = (of - loss) if of is not None and loss is not None else None
            ratio = round(100 * after / scr, 1) if after is not None and scr else None
            events.append({"stress": f"{kind}, {label}", "scenario": sc, "horizon": hz, "net_loss_eur": _r(loss),
                           "own_funds_after_eur": _r(after), "scr_ratio_after_pct": ratio,
                           "breaches_scr": None if ratio is None else ratio < SCR_BREACH_PCT,
                           "triggers_crossed": [t["name"] for t in triggers if ratio is not None and t["level_pct"] is not None
                                                and ratio < t["level_pct"]]})
    return {"capital": {"eligible_own_funds_scr": of, "scr_total": scr, "scr_ratio_pct": cap.get("scr_ratio_pct"),
                        "attested": bool(cap.get("provenance"))},
            "treaty_basis": (today.get("reinsurance") or {}).get("program_basis"),
            "warming_scenario": warm, "events": events, "triggers": triggers, "readings": READINGS}


def _r(v):
    return round(v) if v is not None else None


def _triggers(session, org_id: str, period_end: date, entity_id: str | None) -> list[dict]:
    """The capital indicators: the SCR breach (the Article's minimum) and the plan's own attested levels."""
    from services.governance.provided_data import attested_values
    a = {v["key"].removeprefix("provided."): v["value"]
         for v in attested_values(session, org_id, "insurer_recovery_stress", period_end, reporting_entity_id=entity_id)}
    out = [{"name": "SCR breach (Art. 5(8) minimum)", "level_pct": SCR_BREACH_PCT, "source": "Directive (EU) 2025/1 Art. 5(8)"}]
    for key, name in (("scr_trigger_recovery_pct", "Recovery-action level"), ("scr_trigger_early_warning_pct", "Early-warning level")):
        v = a.get(key)
        out.append({"name": name, "level_pct": float(v) if v is not None else None,
                    "source": "the undertaking's plan (attested)" if v is not None else "not yet stated"})
    return out


def computed_value(item_id: str, rec: dict) -> dict | None:
    if not rec:
        return None
    if item_id == "stress":
        cols = [("stress", "Stress"), ("net_loss_eur", "Net loss"), ("own_funds_after_eur", "Own funds after"),
                ("scr_ratio_after_pct", "SCR ratio after (%)"), ("breaches_scr", "Breaches the SCR"),
                ("triggers_crossed", "Indicators crossed")]
        rows = [{**{k: e.get(k) for k, _ in cols}, "breaches_scr": {True: "yes", False: "no", None: "—"}[e["breaches_scr"]],
                 "triggers_crossed": ", ".join(e["triggers_crossed"]) or "none"} for e in rec["events"]]
        return {"table": {"columns": [{"id": k, "label": v} for k, v in cols], "rows": rows,
                          "note": " ".join(r["reading"] for r in rec["readings"])}}
    if item_id == "indicators.scr":
        cols = [("name", "Indicator"), ("level_pct", "SCR ratio level (%)"), ("source", "Set by"),
                ("today", "Today"), ("worst_stress", "Under the worst stress")]
        worst = min((e["scr_ratio_after_pct"] for e in rec["events"] if e["scr_ratio_after_pct"] is not None), default=None)
        now = rec["capital"]["scr_ratio_pct"]
        rows = [{"name": t["name"], "level_pct": t["level_pct"], "source": t["source"],
                 "today": _met(now, t["level_pct"]), "worst_stress": _met(worst, t["level_pct"])} for t in rec["triggers"]]
        return {"table": {"columns": [{"id": k, "label": v} for k, v in cols], "rows": rows,
                          "note": f"SCR ratio today {now if now is not None else '—'}%, under the worst stress "
                                  f"{worst if worst is not None else '—'}%."}}
    return None


def _met(ratio, level) -> str:
    if ratio is None or level is None:
        return "—"
    return f"crossed ({ratio}%)" if ratio < level else f"clear ({ratio}%)"
