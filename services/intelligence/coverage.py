"""Coverage report — how much of the world we score, measured honestly.

Best-of-breed vendors quote "millions of locations" of PRE-SCORED coverage. Our model is different: a standing
layer of pre-scored cells for the asset universe + baselines, plus ON-DEMAND scoring of any address in seconds
(so we don't need to pre-score the planet to answer for a location). This report quantifies both, per hazard
and resolution, and flags where the standing layer is thin — an honest, reproducible number instead of a
marketing claim. Scaling the standing layer further is a data-generation task, not a code change; the
on-demand path already gives global reach today.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from core import messages

# hazards answerable on demand for any address (volcanic: GVP global catalogue + radial physics, SCREENING)
ON_DEMAND_HAZARDS = ["flood", "wildfire", "drought", "storm", "seismic", "heat_acute", "soil_water",
                     "coastal_flood", "subsidence", "volcanic", "cold_wave"]
THIN_THRESHOLD = 1000   # a standing layer below this many cells is flagged for deepening


def summarize_coverage(per_hazard: list[dict], resolutions: list[int], scenarios: list[str],
                       horizons: list[str]) -> dict:
    """Pure summariser (no DB) — assemble the coverage picture from queried rows."""
    total_cells = max((h["cells"] for h in per_hazard), default=0)
    thin = [h["hazard"] for h in per_hazard if h["cells"] < THIN_THRESHOLD]
    return {
        "standing": {
            "n_cells_max_hazard": total_cells,
            "n_hazards": len(per_hazard),
            "resolutions": sorted(resolutions),
            "scenarios": sorted(scenarios),
            "horizons": sorted(horizons),
            "per_hazard": sorted(per_hazard, key=lambda h: -h["cells"]),
            "thin_layers": thin,
        },
        "on_demand": {
            "global": True,
            "hazards_on_demand": len(ON_DEMAND_HAZARDS),
            "hazards": ON_DEMAND_HAZARDS,
            "note": "any address scored on demand in seconds; pre-scoring the planet is unnecessary",
        },
    }


def _scope_claims() -> dict:
    """Of the CALIBRATED hazards, how many may claim which geographic scope (derived by the pre-registered rule)."""
    from core.hazard_regions import scope_claim
    from core.hazard_taxonomy import EU_TAXONOMY, MaturityTier
    out = {"global": 0, "pooled_global": 0, "multi_region": 0, "regional": 0, "none": 0}
    for h in EU_TAXONOMY:
        if h.tier is MaturityTier.CALIBRATED:
            out[scope_claim(h.id)] += 1
    return out


# ── The Coverage page's three views, to the UI standard (2026-10-16) ──────────────────────────────────────────────
# Every word they serve is the message catalogue's (coverage.* in data/reference/messages.en.json); the registries'
# engineers' notes (core/hazard_taxonomy internal_note, core/hazard_regions evidence and ledger, the projection and
# limitation records) stay on the server. tests/unit/test_coverage_view.py holds the served text to customer language
# and every number it states to the registries' record.
TIER_ORDER = ("calibrated", "by_nature", "screening", "reference", "roadmap")
REGION_STATUSES = ("validated", "mixed", "fails", "untested")
# the projection modes, as the screen lists them: carried by climate models first, flat by design last
MODE_ORDER = ("cmip6_band", "cmip6_environment", "ar6_slr_band", "projection_channel", "parametric_cc",
              "parametric_warming", "parametric_warming_inverse", "variability", "susceptibility_flat", "geophysical_flat")
_MODE_CODE = {"cmip6_band": "models_band", "cmip6_environment": "models_environment", "ar6_slr_band": "sea_level_band"}


def _gates() -> dict:
    """The validation bars the words quote, from the pre-registered gates (never typed into the words)."""
    from core import validation_gates as G
    return {"bar": f"{G.RANK_GATE_SPEARMAN:.2f}", "r2": f"{G.REGRESSION_GATE_R2:.2f}",
            "min": G.GLOBAL_CLAIM_MIN_REGIONS, "n": len(G.MACRO_REGIONS)}


def _msg(code: str, **params) -> dict:
    """A catalogue message as the screen needs it: its label and its detail."""
    r = messages.render(code, **params)
    return {"label": r["label"], "detail": r["detail"]}


def mode_message(mode: str) -> dict:
    return _msg(f"coverage.mode.{_MODE_CODE.get(mode, mode)}")


def _projection_item(it: dict) -> dict:
    return {"channel": it["hazard"], "label": messages.name("coverage.channel", it["hazard"]),
            "projects": it["projects"], "band": it["band"], "mode": it["mode"], "mode_message": mode_message(it["mode"]),
            "message": _msg(f"coverage.projection.{it['hazard']}", **it["params"])}


def _projections() -> dict[str, dict]:
    from ml.scoring.projection_coverage import projection_coverage
    return {it["hazard"]: _projection_item(it) for it in projection_coverage()["items"]}


def _scope(hazard_id: str) -> dict:
    """Where a validated hazard was judged, region by region; its claim is derived, never typed in."""
    from core import validation_gates as G
    from core.hazard_regions import REGIONAL_EVIDENCE, scope_claim
    status = {e.region: e.status for e in REGIONAL_EVIDENCE.get(hazard_id, ())}
    claim = scope_claim(hazard_id)
    return {"claim": claim, "message": _msg(f"coverage.scope.{claim}", **_gates()),
            "regions": [{"region": r, "status": status.get(r, "untested"),
                         "message": _msg(f"coverage.region.{hazard_id}.{r}", **_gates()) if r in status else None}
                        for r in G.MACRO_REGIONS]}


def _hazard(h, projections: dict[str, dict]) -> dict:
    from core.hazard_taxonomy import MaturityTier, screening_status
    st = screening_status(h.id, h.tier)
    d = {"id": h.id, "name": h.name, "label": messages.name("coverage.hazard", h.id), "family": h.family.value,
         "nature": h.nature, "tier": h.tier.value, "phase": h.phase, "internal": [c.value for c in h.internal],
         "message": _msg(f"coverage.hazard.{h.id}", **_gates()),
         "indicator": _msg(f"coverage.indicator.{st}") if st else None,
         "projection": [projections.get(c.value) or {"channel": c.value, "label": messages.name("coverage.channel", c.value),
                                                     "projects": False, "band": False, "mode": None, "mode_message": None,
                                                     "message": _msg("coverage.projection.none")}
                        for c in h.internal]}
    if h.tier is MaturityTier.CALIBRATED:
        d["scope"] = _scope(h.id)                  # WHERE it is validated — the tier alone would read as unbounded
    return d


def eu_taxonomy_coverage() -> dict:
    """Our coverage of the EU Taxonomy's 28 physical climate hazards (Regulation 2021/2139, Appendix A), each stamped
    with a maturity tier, for the screen.

    Pure — derived from the canonical registry in `core.hazard_taxonomy` (no DB): the 28 grouped by family, the honest
    counts, and the channels we carry beyond the list (seismic, volcanic, pollution). Coverage ≠ calibration — the tier
    on each hazard says which claim we're making. Each hazard carries its words, where it is validated and how it is
    carried to future years.
    """
    from core import validation_gates as G
    from core.hazard_taxonomy import (
        EXTRA_CHANNELS,
        HazardFamily,
        coverage_summary,
        eu_hazards_by_family,
    )

    grouped = eu_hazards_by_family()
    proj = _projections()
    return {
        "counts": {**coverage_summary(), "scope_claims": _scope_claims()},
        "tiers": [{"tier": t, **_msg(f"coverage.tier.{t}")} for t in TIER_ORDER],
        "families": [{"family": f.value, "label": messages.name("coverage.family", f.value),
                      "hazards": [_hazard(h, proj) for h in grouped[f.value]]} for f in HazardFamily],
        "extra_label": messages.name("coverage.family", "beyond"),
        "extra_channels": [_hazard(h, proj) for h in EXTRA_CHANNELS],
        "regions": [{"region": r, "label": messages.name("coverage.region", r)} for r in G.MACRO_REGIONS],
        "region_statuses": [{"status": s, "label": messages.name("coverage.region_status", s)} for s in REGION_STATUSES],
    }


def projection_view() -> dict:
    """How each hazard is carried to 2030, 2050 and 2100, for the screen: one row per scored channel, grouped by mode."""
    from core.hazard_taxonomy import EU_TAXONOMY, EXTRA_CHANNELS
    from ml.scoring.projection_coverage import HORIZONS, SCENARIOS, projection_coverage

    reg = projection_coverage()
    hazard_of = {c.value: h.id for h in (*EU_TAXONOMY, *EXTRA_CHANNELS) for c in h.internal}
    items = [{**_projection_item(it), "hazard_id": hazard_of.get(it["hazard"])} for it in reg["items"]]
    modes = [*MODE_ORDER, *sorted({it["mode"] for it in items} - set(MODE_ORDER))]
    return {
        "scenarios": [{"key": s, "label": messages.name("scenario", s)} for s in SCENARIOS],
        "horizons": HORIZONS,
        "counts": {"hazards": reg["n_hazards"], "projected": reg["n_projected"], "flat": reg["n_flat_by_design"],
                   "band": reg["n_with_band"]},
        "modes": [{"mode": m, "message": mode_message(m), "projects": rows[0]["projects"], "channels": [i["channel"] for i in rows]}
                  for m in modes if (rows := [i for i in items if i["mode"] == m])],
        "items": items,
    }


def limitations_view() -> dict:
    """What the engine deliberately does not model yet, for the screen: each limitation's words, status and area."""
    from ml.scoring.model_limitations import STATUSES, model_limitations

    reg = model_limitations()
    return {
        "counts": reg["counts"],
        "statuses": [{"status": s, **_msg(f"coverage.status.{s}")} for s in STATUSES],
        "items": [{"id": it["id"], "status": it["status"], "area": messages.name("coverage.area", it["id"]),
                   "message": _msg(f"coverage.limitation.{it['id']}", **_gates()),
                   "today": _msg(f"coverage.limitation.{it['id']}.today")}
                  for it in reg["items"]],
    }


def coverage_report(session: Session, horizon: str = "current") -> dict:
    """DB-backed coverage report over canonical_scores (the standing golden source)."""
    per_hazard = [dict(r) for r in session.execute(text("""
        SELECT hazard_type AS hazard, count(DISTINCT h3_cell) AS cells
        FROM canonical_scores WHERE valid_to IS NULL AND time_horizon = :h
        GROUP BY hazard_type ORDER BY cells DESC
    """), {"h": horizon}).mappings().all()]
    resolutions = [int(r[0]) for r in session.execute(text(
        "SELECT DISTINCT h3_resolution FROM canonical_scores WHERE valid_to IS NULL AND h3_resolution IS NOT NULL")).all()]
    scenarios = [r[0] for r in session.execute(text(
        "SELECT DISTINCT scenario FROM canonical_scores WHERE valid_to IS NULL")).all()]
    horizons = [r[0] for r in session.execute(text(
        "SELECT DISTINCT time_horizon FROM canonical_scores WHERE valid_to IS NULL")).all()]
    return summarize_coverage(per_hazard, resolutions, scenarios, horizons)
