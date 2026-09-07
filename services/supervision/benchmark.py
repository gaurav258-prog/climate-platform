"""Peer benchmarking across a regulator's supervised population — configuration-driven, sector-agnostic.

For each sector in the regulator's profile: compute every configured metric for every supervised entity of that
type (from the cross-sector asset reader), then the population distribution (min / p25 / median / p75 / max) and
each entity's percentile rank and supervisory flag. Thresholds come from the profile (overridable per regulator);
the metric definitions are shared with the entity's own pages, so supervisor and entity see the same number.
"""
from __future__ import annotations

from statistics import median

from services.geo.org_assets import org_asset_points
from services.supervision import metrics as M


def _pct(values: list[float], v: float, lower_is_better: bool) -> float:
    """Percentile rank of v among values: 100 = best-placed under the metric's direction."""
    if len(values) < 2:
        return 50.0
    better = sum(1 for x in values if (x > v if lower_is_better else x < v))
    return round(100.0 * better / (len(values) - 1), 0)


def _quartiles(vals: list[float]) -> dict:
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    q = lambda f: s[min(len(s) - 1, int(round(f * (len(s) - 1))))]  # noqa: E731
    return {"n": len(s), "min": s[0], "p25": q(0.25), "median": median(s), "p75": q(0.75), "max": s[-1]}


def benchmark(session, cfg: dict, entities: list[dict], scenario: str, horizon: str) -> dict:
    """cfg = resolved profile; entities = supervised orgs [{org_id, name, type}] → per-sector benchmark tables."""
    out: dict = {"scenario": scenario, "horizon": horizon, "profile_id": cfg["profile_id"], "sectors": {}}
    for sec, scfg in cfg["sectors"].items():
        ents = [e for e in entities if e["type"] == sec]
        rows = []
        for e in ents:
            pts = org_asset_points(session, e["org_id"], scenario, horizon)
            rows.append({"org_id": e["org_id"], "name": e["name"], "n_assets": len(pts),
                         "values": M.compute(scfg["metrics"], pts)})
        metrics_out = []
        for m in scfg["metrics"]:
            vals = [r["values"][m["id"]] for r in rows if r["values"][m["id"]] is not None]
            lower = m.get("direction") == "lower_is_better"
            per_entity = []
            for r in rows:
                v = r["values"][m["id"]]
                per_entity.append({"org_id": r["org_id"], "name": r["name"], "value": v,
                                   "flag": M.flag(m, v),
                                   "percentile": (_pct(vals, v, lower) if v is not None and m.get("direction") != "neutral" else None)})
            metrics_out.append({**{k: v for k, v in m.items() if k != "adapter"}, "distribution": _quartiles(vals),
                                "entities": per_entity})
        out["sectors"][sec] = {"label": scfg["label"], "book_noun": scfg["book_noun"], "frameworks": scfg["frameworks"],
                               "n_entities": len(rows), "entities": [{"org_id": r["org_id"], "name": r["name"], "n_assets": r["n_assets"]} for r in rows],
                               "metrics": metrics_out}
    return out


def entity_position(bench: dict, org_id: str) -> list[dict]:
    """One entity's row across every metric of its sector — the 'peer position' block of its entity file."""
    for sec in bench["sectors"].values():
        if any(e["org_id"] == org_id for e in sec["entities"]):
            return [{"id": m["id"], "label": m["label"], "unit": m["unit"], "direction": m.get("direction"),
                     "distribution": m["distribution"],
                     **next(e for e in m["entities"] if e["org_id"] == org_id)} for m in sec["metrics"]]
    return []
