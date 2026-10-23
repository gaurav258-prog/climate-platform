"""Issuers' real sites from public registers (the product owner's decisions of 2026-10-23), without a database.

  weights   a register states no site's share of the company's value: a register site's weight is 'not stated' — the
            look-through names it as a gap, never a number, and an issuer whose only sites are such is named apart
  facts     the owner's share is the register's own percentage as a share (none or zero → not stated); a year's
            emissions are the sum of the periods the register states for it
  names     the EEA register's parent company is proposed to an issuer only when it is, once case, accents,
            punctuation and spacing are set aside, a name GLEIF records for the issuer or an entity it consolidates;
            a name two entities share is ambiguous and never proposes"""
from __future__ import annotations

import pandas as pd
import pytest

from services.loss import lookthrough
from services.reference import register_matching as M
from services.reference import register_sites as R


def _site(basis, proxy=False):
    return {"facility_id": f"f-{basis}", "issuer_id": "i", "name": "Plant", "facility_type": "cement", "country": "DE",
            "region": None, "weight": 0.0, "weight_basis": basis, "source": "climate_trace", "proxy": proxy}


def test_a_register_site_never_counts_and_names_why():
    out = lookthrough._issuer([_site("not_stated"), _site("equal", proxy=True)], {"figures": [], "not_carried": []},
                              ["assets"], None)
    assert out["share"] is None and out["why"]["code"] == "lookthrough.gap.weights_not_stated"
    assert out["sites"][0]["why"]["code"] == "lookthrough.site.weight_not_stated" and out["sites"][0]["counts"] is False


def test_a_register_site_beside_a_weighted_one_is_counted_by_its_own_reason():
    w = {**_site("revenue"), "facility_id": "f-r", "weight": 0.5}
    out = lookthrough._issuer([_site("not_stated"), w], {"figures": [], "not_carried": []}, ["assets"], None)
    assert out["why"]["code"] == "lookthrough.gap.no_weighted_site"


def test_the_owner_share_is_the_register_s_percentage_or_not_stated():
    assert R._share("87.5") == 0.875 and R._share("100") == 1.0
    assert R._share(None) is None and R._share("0") is None and R._share("not found") is None and R._share("120") is None


def test_a_year_s_facts_are_the_sum_of_its_periods_and_the_last_period_s_capacity():
    rows = pd.DataFrame({"start_time": ["2025-11-01", "2025-12-01", "2026-01-01", "2026-02-01"],
                         "emissions_quantity": ["10", "20", "1", "2"], "activity": ["5", "5", "1", None],
                         "activity_units": ["MWh"] * 4, "capacity": ["100", "100", "120", "130"],
                         "capacity_units": ["MW"] * 4, "temporal_granularity": ["month"] * 4,
                         "source_type": ["gas"] * 4})
    f = R._year_facts(rows)
    assert f["year"] == 2026 and f["periods"] == 2 and f["emissions_t_co2e_100yr"] == pytest.approx(3.0)
    assert f["activity"] == pytest.approx(1.0) and f["capacity"] == 130.0 and f["capacity_period"] == "2026-02-01"


def test_names_compare_without_case_accents_punctuation_or_spacing():
    assert M.normalise("Volkswagen Poznań Sp. z o.o.") == "volkswagen poznan sp z o o"
    assert M.normalise("  TOTALENERGIES  SE ") == M.normalise("TotalEnergies SE")
    assert M.normalise("Holcim (Deutschland) GmbH") == "holcim deutschland gmbh"


def _ent(lei, legal, other=()):
    return {"id": lei, "attributes": {"entity": {"legalName": {"name": legal},
                                                 "otherNames": [{"name": o} for o in other]}}}


def test_the_issuer_and_its_consolidated_entities_propose_and_a_shared_name_never_does():
    doc = {"record": _ent("L1", "ACME AG"), "ultimate_children": [_ent("L2", "Acme Zement GmbH", ["Acme Cement"]),
                                                                  _ent("L3", "Shared Name SA")],
           "direct_children": [_ent("L4", "Shared Name SA")]}
    names = M.entity_names(doc)
    assert names["acme ag"] == ("L1", "ACME AG", "issuer")
    assert names["acme cement"] == ("L2", "Acme Zement GmbH", "consolidated_entity")
    assert "shared name sa" not in names


def _tif(path, values):
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(path, "w", driver="GTiff", height=1, width=len(values), count=1, dtype="float32", nodata=-9999,
                       crs="EPSG:4326", transform=from_origin(0.0, 1.0, 1.0, 1.0)) as dst:
        dst.write(np.array([values], dtype="float32"), 1)


@pytest.mark.parametrize("reads_as, sea", [("outside", ("outside_coverage", None)), (None, ("sampled", 0.0))])
def test_coastal_no_data_is_outside_the_map_and_river_no_data_is_dry(tmp_path, monkeypatch, reads_as, sea):
    from services.loss import intensity, registry
    path = tmp_path / "map.tif"
    _tif(path, [-9999.0, 0.0, 1.5])
    L = {"version": "t", "return_periods": [100], "dry_below": 0.0, **({"no_data": {"value": -9999, "reads_as": reads_as}}
                                                                       if reads_as else {})}
    monkeypatch.setattr(registry, "layer", lambda key: L)
    monkeypatch.setattr(intensity, "map_path", lambda key, v, rp: path)
    rows = intensity.map_rows("k", {"scenario": "present", "period": "present", "climate_model": ""},
                              [(0.5, 0.5), (0.5, 1.5), (0.5, 2.5)])
    assert (rows[0]["status"], rows[0]["value"]) == sea
    assert (rows[1]["status"], rows[1]["value"], rows[1]["cell_fraction"]) == ("sampled", 0.0, 0.0)
    assert (rows[2]["value"], rows[2]["cell_fraction"], rows[2]["cell_mean"]) == (1.5, 1.0, 1.5)
