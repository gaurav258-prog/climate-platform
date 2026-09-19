"""Every CALIBRATED hazard must say where it is validated; its scope claim is derived, never typed."""
from core import hazard_regions as HR
from core import validation_gates as G
from core.hazard_taxonomy import EU_TAXONOMY, MaturityTier


def _calibrated_ids():
    return {h.id for h in EU_TAXONOMY if h.tier is MaturityTier.CALIBRATED}


def test_every_calibrated_hazard_declares_where_it_is_validated():
    declared = set(HR.REGIONAL_EVIDENCE) | set(HR.POOLED_GLOBAL)
    assert _calibrated_ids() <= declared, f"calibrated with no regional scope: {_calibrated_ids() - declared}"


def test_no_stale_regional_entries():
    stale = (set(HR.REGIONAL_EVIDENCE) | set(HR.POOLED_GLOBAL)) - _calibrated_ids()
    assert not stale, f"regional evidence for hazards that are not CALIBRATED: {stale}"


def test_evidence_rows_are_well_formed():
    for hid, rows in HR.REGIONAL_EVIDENCE.items():
        regions = [r.region for r in rows]
        assert len(regions) == len(set(regions)), f"{hid}: duplicate region"
        for r in rows:
            assert r.region in G.MACRO_REGIONS and r.status in (HR.VALIDATED, HR.MIXED, HR.FAILS)
            assert r.ledger and r.evidence


def test_scope_claim_follows_the_pre_registered_rule(monkeypatch):
    v = lambda region: HR.RegionEvidence(region, HR.VALIDATED, "t", "t")
    # four regions but all Global North + Oceania: not a global claim
    monkeypatch.setitem(HR.REGIONAL_EVIDENCE, "x", (v("europe"), v("north_america"), v("oceania")))
    assert HR.scope_claim("x") == "multi_region"
    # add one outside the Global North and the count reaches the threshold
    monkeypatch.setitem(HR.REGIONAL_EVIDENCE, "x", (v("europe"), v("north_america"), v("oceania"), v("africa")))
    assert HR.scope_claim("x") == "global"
    # 'mixed' regions never count toward a global claim
    mixed = lambda region: HR.RegionEvidence(region, HR.MIXED, "t", "t")
    monkeypatch.setitem(HR.REGIONAL_EVIDENCE, "x", (v("europe"), v("north_america"), mixed("africa"), mixed("asia")))
    assert HR.scope_claim("x") == "multi_region"
    monkeypatch.setitem(HR.REGIONAL_EVIDENCE, "x", (v("europe"),))
    assert HR.scope_claim("x") == "regional"


def test_a_hazard_that_fails_in_regions_is_never_global():
    """Drought fails in the US Corn Belt and South America: it must not read as a general/global score."""
    assert HR.scope_claim("drought") != "global"
    assert any(r.status == HR.FAILS for r in HR.REGIONAL_EVIDENCE["drought"])
    assert HR.CAVEATS["drought"]


def test_coverage_api_carries_scope_for_calibrated_hazards_only():
    from services.intelligence.coverage import eu_taxonomy_coverage
    cov = eu_taxonomy_coverage()
    hazards = [h for f in cov["families"] for h in f["hazards"]]
    for h in hazards:
        assert ("scope" in h) == (h["tier"] == "calibrated")
    claims = cov["summary"]["scope_claims"]
    assert sum(claims.values()) == cov["summary"]["by_tier"]["calibrated"]
    assert set(claims) == {"global", "pooled_global", "multi_region", "regional", "none"}
