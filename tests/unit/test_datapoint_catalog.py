"""The canonical datapoint catalog — validity + coverage derivation."""
from services.governance.datapoint_catalog import CATALOG, catalog, coverage, coverage_source

VALID_SOURCES = {"tellumen", "egov", "evendor", "customer", "none"}
VALID_LANES = {"compute", "granular", "provided", "report", "none"}


def test_every_datapoint_is_well_formed():
    for fw, dps in CATALOG.items():
        assert dps, f"{fw} has no datapoints"
        keys = [d["key"] for d in dps]
        assert len(keys) == len(set(keys)), f"{fw} has duplicate datapoint keys"
        for d in dps:
            assert d["source_category"] in VALID_SOURCES, f"{fw}:{d['key']} bad source {d['source_category']}"
            assert d["lane"] in VALID_LANES, f"{fw}:{d['key']} bad lane {d['lane']}"
            # a produced/provided datapoint names who provides it; a gap does not
            if d["lane"] == "none":
                assert d["source_category"] == "none"
            else:
                assert d["provider"], f"{fw}:{d['key']} is sourced but names no provider"
            # source/lane must be consistent: only 'none' pairs with 'none'
            assert (d["source_category"] == "none") == (d["lane"] == "none")


def test_coverage_source_mapping():
    assert coverage_source("compute") == "computed"
    assert coverage_source("granular") == "computed"
    assert coverage_source("provided") == "integrated"
    assert coverage_source("report") == "client"
    assert coverage_source("none") == "out_of_scope"


def test_coverage_derives_from_catalog():
    # bank: 3 computed / 1 integrated (GAR alignment) / 1 client / 1 out-of-scope → 50% produced
    c = coverage("bank_tcfd")
    assert c["counts"] == {"computed": 3, "integrated": 1, "client": 1, "out_of_scope": 1}
    assert c["pct_computed"] == 50
    # sections carry the full taxonomy for the data dictionary / customer docs
    aligned = next(s for s in c["sections"] if "alignment" in s["section"])
    assert aligned["source"] == "integrated" and aligned["lane"] == "provided" and aligned["source_category"] == "customer"
    assert coverage("nonexistent_framework") is None


def test_catalog_lookup():
    assert catalog("sfdr_pai") is not None
    assert catalog("sfdr_pai")[0]["key"] == "pai_climate"
