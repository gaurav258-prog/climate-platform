"""Regulatory-package methodology states only what the platform does: sources come from the feed registry,
coverage from the hazard registry, model versions from the scores themselves — no withdrawn or unused sources,
no ensemble the scores were never produced by."""
from __future__ import annotations

from datetime import datetime

import pytest

from core.hazard_taxonomy import EU_TAXONOMY
from ml.regulatory import csrd, ecb, packager
from services.data.feeds import FEEDS, HAZARD_FEEDS

ROWS = [
    {"location_id": "L1", "location_name": "Site 1", "h3_cell": "881f1d4815fffff", "asset_type": "office",
     "asset_value": 1.0, "hazard_type": hz, "scenario": sc, "time_horizon": "current", "risk_score": 55.0,
     "risk_bucket": "MEDIUM", "compound_flag": False, "regulatory_fingerprint": f"fp-{hz}-{sc}",
     "model_version": mv, "scored_at": datetime(2026, 9, 1)}
    for hz, mv in [("flood", "flood-jrc-glofas-rp-v3"), ("wildfire", "wildfire-climatology-v1"),
                   ("coastal_flood", "sea-level-ar6-v3-gauge-ewl"), ("landslide", "landslide-nasa-lhasa-susc-v1")]
    for sc in ("baseline", "hot_house_3_5c")
]


def _both():
    return {"csrd": csrd._methodology(ROWS, ["C10"]), "ecb": ecb._table5_methodology(ROWS)}


@pytest.mark.parametrize("name", ["csrd", "ecb"])
def test_methodology_names_no_withdrawn_or_unused_source_or_model(name):
    m = _both()[name]
    model = m.get("scoring_model") or m["scoring_methodology"]
    for banned in ("GloFAS", "XGBoost", "LightGBM", "Logistic", "ensemble", "NGFS Phase 4", "planned for 2025"):
        assert banned.lower() not in model.lower()
        assert all(banned.lower() not in src.lower() for src in m["data_sources"])
        assert banned.lower() not in m["hazard_coverage"].lower()
    # planned (not-in-production) feeds are never presented as a source
    planned = {f["name"] for f in FEEDS if f["maturity"] == "planned"}
    assert not planned & set(m["data_sources"])


@pytest.mark.parametrize("name", ["csrd", "ecb"])
def test_sources_come_from_feed_registry_for_package_hazards(name):
    m = _both()[name]
    by_key = {f["key"]: f for f in FEEDS}
    hazards = {r["hazard_type"] for r in ROWS}
    expected_keys = {k for hz in hazards for k in HAZARD_FEEDS.get(hz, [])}
    detail = m["data_source_detail"]
    assert {s["key"] for s in detail["sources"]} == expected_keys
    for s in detail["sources"]:
        assert s["name"] == by_key[s["key"]]["name"] and s["maturity"] == by_key[s["key"]]["maturity"]
        assert set(s["hazards"]) <= hazards
    assert m["data_sources"] == [s["name"] for s in detail["sources"]]
    # a hazard with no registered feed is disclosed, not given an invented source
    assert set(detail["hazards_without_registered_feed"]) == {hz for hz in hazards if not HAZARD_FEEDS.get(hz)}
    # the flood feed is the ERA5-Land proxy, and its caveat travels with it
    flood = next(s for s in detail["sources"] if s["key"] == "flood")
    assert flood["maturity"] == "proxy" and flood["caveat"] == by_key["flood"]["note"]


@pytest.mark.parametrize("name", ["csrd", "ecb"])
def test_coverage_and_versions_come_from_registries_and_scores(name):
    m = _both()[name]
    tiers = {c.value: h.tier.value for h in EU_TAXONOMY for c in h.internal}
    cov = {c["hazard_type"]: c for c in m["hazard_coverage_detail"]}
    assert set(cov) == {r["hazard_type"] for r in ROWS}
    for hz, c in cov.items():
        assert c["tier"] == tiers[hz]
    assert m["model_versions"] == {r["hazard_type"]: [r["model_version"]] for r in ROWS}
    assert m["scenarios"] == ["baseline", "hot_house_3_5c"]


def test_packager_stamps_real_model_versions_not_ensemble():
    stamp = packager._infer_model_version({"methodology": csrd._methodology(ROWS, [])})
    assert stamp.startswith("per-hazard-4-models-") and len(stamp) <= 50
    one = [r for r in ROWS if r["hazard_type"] == "wildfire"]
    assert packager._infer_model_version({"t5_methodology": ecb._table5_methodology(one)}) == "wildfire-climatology-v1"
    assert packager._infer_model_version({}) == "no-scores"
