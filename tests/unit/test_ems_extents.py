"""E172: an observed flood extent holds only its own activation's observations, and a terrain fetch is priced before it runs.

  layer      the EMS catalogue listed another activation's layer (EMSR765, a flood in Bolivia) under Storm Boris
             (EMSR756 AOI02); a layer is accepted only when its file names the activation and AOI it is listed under
             and its polygons lie inside that product's outline
  files      every landed extent records the layers it took and the ones it refused, each taken layer its own, and
             the area EMS mapped — every flooded polygon inside it (the validator judges nodes there only)
  terrain    the 30 m tiles are those under the events' boxes, the plan refuses above the approved volume, and the asset
             tiles wait for the refinement's test"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from shapely.geometry import box

from scripts import fetch_glo30
from scripts.fetch_ems_flood_footprints import layer_refusal

VAL = Path(__file__).resolve().parents[2] / "data" / "flood_val"
OUTLINE = box(15.6, 50.7, 16.3, 51.0).wkt


def _layer(file: str) -> dict:
    return {"url": f"https://rapidmapping-viewer.s3.eu-west-1.amazonaws.com/x/{file}", "emsr": "EMSR756", "aoi": 2,
            "extent": OUTLINE}


def test_a_layer_of_another_activation_is_refused():
    why = layer_refusal(_layer("EMSR765_AOI01_DEL_PRODUCT_observedEventA_v1.json"), [box(-63, -16, -62.2, -14.9)])
    assert why == "listed under EMSR756_AOI02 but the file is EMSR765_AOI01_DEL_PRODUCT_observedEventA_v1.json"


def test_a_layer_outside_its_own_outline_is_refused():
    why = layer_refusal(_layer("EMSR756_AOI02_DEL_PRODUCT_observedEventA_v2.json"), [box(15.7, 50.8, 15.9, 50.9),
                                                                                     box(17.0, 50.0, 17.5, 50.5)])
    assert why is not None and "inside the product outline" in why


def test_the_products_own_layer_inside_its_outline_is_taken():
    assert layer_refusal(_layer("EMSR756_AOI02_DEL_PRODUCT_observedEventA_v2.json"), [box(15.7, 50.8, 15.9, 50.9)]) is None


@pytest.mark.parametrize("path", sorted(VAL.glob("ems_*.geojson")), ids=lambda p: p.stem)
def test_every_landed_extent_records_its_own_layers(path):
    doc = json.loads(path.read_text())
    assert "layers" in doc and "refused" in doc, f"{path.name} predates the layer check — refetch it"
    assert doc["layers"], path.name
    for lay in doc["layers"]:
        assert lay["file"].startswith(lay["emsr"]), lay
        if "aoi" in lay:
            assert lay["file"].startswith(f"{lay['emsr']}_AOI{int(lay['aoi']):02d}_"), lay
    assert doc.get("mapped_area"), f"{path.name} records no mapped area — refetch it"
    from shapely.geometry import shape
    from shapely.ops import unary_union
    flooded = unary_union([shape(f["geometry"]) for f in doc["features"]])
    mapped = shape(doc["mapped_area"]).buffer(0)
    assert flooded.intersection(mapped).area >= 0.99 * flooded.area, "flooded land observed outside where EMS mapped"


def test_the_terrain_tiles_are_those_under_the_event_boxes():
    assert fetch_glo30.tiles_of_box(50.65, 15.95, 49.35, 18.05) == {(la, lo) for la in (49, 50) for lo in (15, 16, 17, 18)}
    tiles = fetch_glo30.test_tiles()
    assert all(la >= 30 for la, _lo in tiles), "a test tile outside Europe: an event box is wrong"


def test_the_plan_refuses_above_the_approved_volume():
    plan = [{"tile": "a", "bytes": 3_000_000_000, "status": "to_fetch"}, {"tile": "b", "bytes": 3_000_000_000, "status": "held"}]
    assert fetch_glo30.plan_refusal(plan, 5) is None
    assert "above the approved 2 GB" in fetch_glo30.plan_refusal(plan, 2)


def test_asset_tiles_wait_for_the_refinement_to_be_in_use(tmp_path, monkeypatch):
    f = tmp_path / "layers.json"
    monkeypatch.setattr(fetch_glo30, "LAYERS", f)
    for layer, adopted in (({"status": "candidate", "test": {"passed": False}}, False),
                           ({"status": "candidate", "test": {"passed": True}}, False),     # passing is not adoption
                           ({"status": "in_use", "test": {"passed": True}}, True), ({}, False)):
        f.write_text(json.dumps({"layers": {"jrc_flood_30m": layer} if layer else {}}))
        assert fetch_glo30.refinement_adopted() is adopted, layer
