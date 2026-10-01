"""ORSA climate change scenario analysis — Directive 2009/138/EC Art. 45a and Art. 51(1b)(e), as inserted by Directive
(EU) 2025/2 (specification family sii_climate; report type insurer_orsa_climate).

What the platform computes, per the Article's items:
  materiality.demonstration   quantified exposure — the sum insured at high hazard, and each scenario's modelled
                              change in expected loss and net 1-in-200 loss against the attested own funds
  scenarios.below_2c/above_2c the two long-term scenarios (data/reference/orsa_climate_scenarios.json, chosen by the
                              undertaking's switches), with their pathway and warming
  impact                      each scenario at each horizon (2030, 2050, 2100) against today: expected annual loss, the
                              technical premium, the net 1-in-200 annual loss, and the SCR ratio if that change were
                              added to the SCR undiversified (declared reading 'Capital impact')
Everything else — the materiality conclusion, the review, the interval, the SNCU derogation, the SFCR statement — is
the undertaking's answer (template_answers). Every run is on the same book with its accumulation zones held fixed
(api.routers.insurance.zones_of), the attested reinsurance and capital of the undertaking the filing is for.
"""
from __future__ import annotations

import json
import os
from datetime import date
from functools import lru_cache

FAMILY = "sii_climate"
DOCUMENT = "orsa_climate"
_REF = os.path.join("data", "reference", "orsa_climate_scenarios.json")
# computed items of the Art. 45a template (the rest of the items to fill are the undertaking's answers)
COMPUTED = {"materiality.demonstration", "scenarios", "scenarios.below_2c", "scenarios.above_2c", "impact"}


@lru_cache(maxsize=1)
def reference() -> dict:
    with open(_REF) as f:
        return json.load(f)


def chosen(settings: dict) -> dict[str, str]:
    """{'below_2c': scenario, 'above_2c': scenario} — the undertaking's switches, else the reference defaults."""
    ref = reference()
    out = {}
    for which in ("below_2c", "above_2c"):
        v = settings.get(f"orsa_scenario_{which}", "orsa_default")
        out[which] = ref["defaults"][which] if v in (None, "orsa_default") else v
    return out


def binding(spec: dict) -> dict:
    import services.regspec as R
    return {t["id"]: {"items": {i["id"]: ("computed" if i["id"] in COMPUTED else "input") for i in R.items_to_fill(t)}}
            for t in spec["templates"]}


def _by_peril(snap: dict) -> dict[str, float | None]:
    """Expected annual loss per insured peril over the book — None for a peril any policy's loss of which is not stated
    (a gap, never a partial sum)."""
    out: dict[str, float | None] = {}
    for p in snap.get("policies") or []:
        for c in (p.get("pricing") or {}).get("perils") or []:
            v, cur = c.get("expected_annual_loss_eur"), out.get(c["hazard"], 0.0)
            out[c["hazard"]] = None if v is None or cur is None else cur + v
    return out


def _zone_losses(snap: dict) -> dict[tuple[str, str], float] | None:
    """Event loss per (peril, region) accumulation zone — None when any policy's loss is not stated."""
    z: dict = {}
    for p in snap.get("policies") or []:
        for c in (p.get("pricing") or {}).get("perils") or []:
            if c.get("net_scenario_loss_eur") is None:
                return None
            k = (c["hazard"], p.get("region") or "unspecified")
            z[k] = z.get(k, 0.0) + c["net_scenario_loss_eur"]
    return z


def _largest_zone_event(snap: dict) -> dict | None:
    """The (peril, region) accumulation zone with the largest event loss — what sets the modelled tail."""
    z = _zone_losses(snap)
    if not z:
        return None
    (hz, region), loss = max(z.items(), key=lambda kv: kv[1])
    return {"hazard": hz, "region": region, "event_loss_eur": round(loss)}


def _projection() -> dict[str, dict]:
    from ml.scoring.projection_coverage import projection_coverage
    return {i["hazard"]: i for i in projection_coverage()["items"]}


def _figures(snap: dict) -> dict:
    roll = snap.get("rollup") or {}
    cat = roll.get("catastrophe") or {}
    net = ((snap.get("reinsurance") or {}).get("net") or {})
    return {"expected_annual_loss_eur": roll.get("total_expected_annual_loss_eur"),
            "technical_premium_eur": roll.get("total_technical_premium_eur"),
            "gross_1_in_200_eur": (cat.get("aep_eur") or {}).get("rp_200"),
            "net_1_in_200_eur": (net.get("net_aep_eur") or {}).get("rp_200"),
            "net_largest_event_1_in_200_eur": (net.get("net_oep_eur") or {}).get("rp_200"),
            "sum_insured_eur": roll.get("total_sum_insured_eur")}


def compute(session, org_id: str, *, entity_ids=None, value_weights=None, translation=None,
            reporting_entity_id: str | None = None, period_end: date) -> dict:
    """The computed part of the ORSA climate analysis for one undertaking (or the group), frozen with the filing."""
    from api.routers.insurance import build_disclosure_snapshot, zones_of
    from services.calc_settings import get_calc_settings
    from services.insurer_capital import position
    ref = reference()
    pick = chosen(get_calc_settings(session, org_id))
    kw = {"entity_ids": entity_ids, "value_weights": value_weights, "translation": translation,
          "reporting_entity_id": reporting_entity_id, "period_end": period_end}
    today = build_disclosure_snapshot(session, org_id, "baseline", "current", **kw)
    zones = zones_of(today.get("policies") or [])                     # one set of accumulation zones for every run
    base = _figures(today)
    cap = position(session, org_id, period_end, reporting_entity_id)
    of, scr = cap.get("eligible_own_funds_scr"), cap.get("scr_total")
    runs, peril_eal, zone_loss = [], {"today": _by_peril(today)}, {}
    for which in ("below_2c", "above_2c"):
        sc = pick[which]
        for hz in ref["horizons"]:
            snap = build_disclosure_snapshot(session, org_id, sc, hz, zones=zones, **kw)
            f = _figures(snap)
            peril_eal[(sc, hz)] = _by_peril(snap)
            zone_loss[(sc, hz)] = _zone_losses(snap)
            d_net = (None if f["net_1_in_200_eur"] is None or base["net_1_in_200_eur"] is None
                     else f["net_1_in_200_eur"] - base["net_1_in_200_eur"])
            runs.append({"scenario_role": which, "scenario": sc, "horizon": hz, **f,
                         "change_expected_loss_pct": _pct(f["expected_annual_loss_eur"], base["expected_annual_loss_eur"]),
                         "change_premium_pct": _pct(f["technical_premium_eur"], base["technical_premium_eur"]),
                         "change_net_1_in_200_eur": None if d_net is None else round(d_net),
                         "change_net_1_in_200_pct_of_own_funds": round(100 * d_net / of, 2) if of and d_net is not None else None,
                         "scr_ratio_pct": (round(100 * of / (scr + max(d_net, 0.0)), 1)
                                           if of and scr and d_net is not None else None)})
    from ml.scoring.insurance_pricing import insured_peril
    # sum insured at or above the stated at-risk level, for the perils a property cover indemnifies only (not e.g. frost)
    hazards = {hz: h for hz, h in (today.get("by_hazard") or {}).items() if insured_peril(hz)}
    ex = [h.get("exposed_value_eur") for h in hazards.values()]
    exposed = None if None in ex else max(ex, default=0)
    proj = _projection()
    worst_key = (pick["above_2c"], ref["horizons"][-1])
    perils = [{"hazard": hz, "projected": bool((proj.get(hz) or {}).get("projects")),
               "projection": (proj.get(hz) or {}).get("mode_label") or "no projection on record",
               "expected_annual_loss_today_eur": None if v is None else round(v),
               "expected_annual_loss_above_2c_eur": (None if (peril_eal.get(worst_key) or {}).get(hz, 0.0) is None
                                                     else round((peril_eal.get(worst_key) or {}).get(hz, 0.0)))}
              for hz, v in sorted(peril_eal["today"].items(), key=lambda kv: -(kv[1] or 0))]
    tail = _largest_zone_event(today)
    if tail:
        tail["projected"] = bool((proj.get(tail["hazard"]) or {}).get("projects"))
        # the same zone's event under the well-above-2 °C scenario at the last horizon
        zl = zone_loss.get(worst_key)
        tail["event_loss_above_2c_eur"] = None if zl is None else round(zl.get((tail["hazard"], tail["region"]), 0.0))
    return {
        "perils": perils, "largest_zone_event": tail, "above_2c_last_horizon": list(worst_key),
        "scenarios": {w: {"scenario": pick[w], **ref["scenarios"][pick[w]]} for w in ("below_2c", "above_2c")},
        "today": base, "runs": runs,
        "capital": {"eligible_own_funds_scr": of, "scr_total": scr, "scr_ratio_pct": cap.get("scr_ratio_pct"),
                    "attested": bool(cap.get("provenance"))},
        "treaty_basis": (today.get("reinsurance") or {}).get("program_basis"),
        "materiality": {"sum_insured_eur": base["sum_insured_eur"],
                        "largest_sum_insured_at_high_hazard_eur": None if exposed is None else round(exposed),
                        "largest_sum_insured_at_high_hazard_pct": (round(100 * exposed / base["sum_insured_eur"], 1)
                                                                   if exposed is not None and base["sum_insured_eur"] else None),
                        "worst": (max(runs, key=lambda r: r["change_net_1_in_200_eur"])
                                  if runs and all(r["change_net_1_in_200_eur"] is not None for r in runs) else None)},
        "readings": ref["interpretations"], "source": ref["_source"],
    }


def _pct(new, old) -> float | None:
    return round(100 * (new - old) / old, 1) if new is not None and old else None


def _eur(v) -> str:
    return "—" if v is None else f"€{v:,.0f}"


def computed_value(item_id: str, orsa: dict) -> dict | None:
    """The value of a computed item, in the document's answer shapes (text, or a table with its own columns)."""
    if not orsa:
        return None
    sc = orsa["scenarios"]
    if item_id == "scenarios":
        return {"text": "Two long-term climate change scenarios, specified below, projected at "
                        + ", ".join(sorted({r['horizon'] for r in orsa['runs']})) + "."}
    if item_id in ("scenarios.below_2c", "scenarios.above_2c"):
        s = sc[item_id.split(".")[1]]
        lo, hi = s["very_likely_c"]
        return {"text": f"{s['label']} — {s['warming_2081_2100_c']} °C by 2081–2100 (very likely {lo}–{hi} °C; IPCC AR6 WGI "
                        "Table SPM.1)."}
    if item_id == "materiality.demonstration":
        m, cap = orsa["materiality"], orsa["capital"]
        w = m["worst"] or {}
        pct = m['largest_sum_insured_at_high_hazard_pct']
        parts = [f"Sum insured {_eur(m['sum_insured_eur'])}; largest share at or above the undertaking's stated level of "
                 f"material physical risk for one insured peril: "
                 + (f"{pct}%." if pct is not None else "not determinable — the level (method.at_risk_level) is not stated.")]
        if w and w["change_net_1_in_200_eur"]:
            parts.append(f"Largest modelled change in the net 1-in-200 annual loss: {_eur(w['change_net_1_in_200_eur'])} "
                         f"({w['scenario']}, {w['horizon']})"
                         + (f" — {w['change_net_1_in_200_pct_of_own_funds']}% of eligible own funds." if cap["eligible_own_funds_scr"] else
                            " — own funds not yet attested."))
        elif w:
            parts.append("The modelled net 1-in-200 annual loss does not change under either scenario at any horizon.")
        t = orsa.get("largest_zone_event")
        if t:
            sc, hz = orsa.get("above_2c_last_horizon") or ["", ""]
            head = f"The largest single accumulation event is {t['hazard']} in {t['region']} ({_eur(t['event_loss_eur'])})"
            if not t["projected"]:
                parts.append(head + f"; the platform holds {t['hazard']} at today's level (no climate projection on record), "
                             "so the scenarios do not move it — its climate change is not in these figures.")
            elif t.get("event_loss_above_2c_eur") == t["event_loss_eur"]:
                parts.append(head + f"; {t['hazard']} is projected, but this zone's event is the same under {sc} {hz} — "
                             "the change in the tail comes from other zones.")
            else:
                parts.append(head + f", {_eur(t.get('event_loss_above_2c_eur'))} under {sc} {hz}.")
        flat = [p["hazard"] for p in orsa.get("perils") or [] if not p["projected"]]
        if flat:
            parts.append("Perils held at today's level: " + ", ".join(flat) + ".")
        return {"text": " ".join(parts)}
    if item_id == "impact":
        cols = [("scenario", "Scenario"), ("horizon", "Horizon"), ("expected_annual_loss_eur", "Expected annual loss"),
                ("change_expected_loss_pct", "Change in expected loss (%)"), ("change_premium_pct", "Change in technical premium (%)"),
                ("net_1_in_200_eur", "Net 1-in-200 annual loss"), ("change_net_1_in_200_eur", "Change in net 1-in-200"),
                ("change_net_1_in_200_pct_of_own_funds", "Change, % of own funds"), ("scr_ratio_pct", "SCR ratio (%)")]
        today = {"scenario": "today", "horizon": "current", **orsa["today"], "scr_ratio_pct": orsa["capital"]["scr_ratio_pct"]}
        sc, hz = orsa.get("above_2c_last_horizon") or ["", ""]
        by_peril = "; ".join(f"{p['hazard']} {_eur(p['expected_annual_loss_today_eur'])} → {_eur(p['expected_annual_loss_above_2c_eur'])}"
                             + ("" if p["projected"] else " (held at today's level)") for p in orsa.get("perils") or [])
        return {"table": {"columns": [{"id": k, "label": v} for k, v in cols],
                          "rows": [{k: r.get(k) for k, _ in cols} for r in [today, *orsa["runs"]]],
                          "note": next(x["reading"] for x in orsa["readings"] if x["subject"] == "Capital impact")
                          + f" Expected annual loss by peril, today → {sc} {hz}: {by_peril}."}}
    return None
