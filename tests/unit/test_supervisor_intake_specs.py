"""Tier-2 intake specs for the markets (asset manager / REIT) and agri-food (sourcing-plot) supervisors:
the specs live in data/reference/supervision_profiles.json, on the same canonical field ids banking and
insurance already use. No network, no DB — spec validity, canonical-id consistency, and column mapping only.
"""
from __future__ import annotations

from services.supervision.intake import _resolve_row_location, map_rows, suggest_mapping
from services.supervision.profiles import registry

MARKETS_SECTORS = ("asset_manager", "reit")
AGRIFOOD_SECTORS = ("manufacturer",)
REFERENCE_SECTORS = ("bank", "insurer")  # the two sectors the lens already works for


def _intake(sector: str) -> dict:
    sec = registry()["sectors"][sector]
    assert sec.get("intake"), f"{sector} has no Tier-2 intake spec configured"
    return sec["intake"]


def test_markets_and_agrifood_sectors_have_intake_specs():
    for sector in MARKETS_SECTORS + AGRIFOOD_SECTORS:
        intake = _intake(sector)
        for kind in ("submission", "granular"):
            assert kind in intake, f"{sector}.intake.{kind} missing"
        sub = intake["submission"]
        assert sub["framework"] and sub["template"] and sub["label"]
        assert sub["cell_fields"] and sub["basis_fields"]
        gran = intake["granular"]
        assert gran["source"] and gran["label"] and gran["row_fields"]
        assert gran["location_rule"] and gran["precision_label"]
        assert gran["shadow"]["vertical"] and gran["shadow"]["entity_type"] and gran["shadow"]["asset_class"]


def test_new_sectors_are_hidden_without_a_spec_only_before_this_change():
    # every financial + agri sector in the registry must now carry an intake spec — the lens must no longer
    # hide behind "no_intake_spec" for markets or agri-food, the two sectors this task closes.
    for sector in MARKETS_SECTORS + AGRIFOOD_SECTORS + REFERENCE_SECTORS:
        assert registry()["sectors"][sector].get("intake"), sector


def test_canonical_cell_field_ids_match_banking_and_insurance():
    """The lens and plausibility band are sector-agnostic: every sector's submission template must map onto
    the same canonical cell-field ids banking already uses (required core five), even if labels differ."""
    bank_ids = {f["id"] for f in _intake("bank")["submission"]["cell_fields"]}
    core_required = {"geography", "sector", "gross_carrying_amount_eur", "sensitive_physical_eur"}
    assert core_required <= bank_ids
    for sector in MARKETS_SECTORS + AGRIFOOD_SECTORS:
        ids = {f["id"] for f in _intake(sector)["submission"]["cell_fields"]}
        assert core_required <= ids, f"{sector} missing canonical cell fields: {core_required - ids}"


def test_canonical_row_field_ids_match_across_sectors_with_disclosed_extension():
    """Granular row fields share the same canonical ids across every sector. Agri-food's sourcing-plot extract
    carries the EUDR geolocation, which is a genuinely new pair of canonical ids (latitude/longitude) — not
    present for bank/insurer/markets — added once, disclosed here rather than smuggled into a sector-specific
    field id."""
    bank_ids = {f["id"] for f in _intake("bank")["granular"]["row_fields"]}
    core_required = {"instrument_id", "nace_section", "outstanding_eur", "collateral_country"}
    assert core_required <= bank_ids
    for sector in MARKETS_SECTORS:
        ids = {f["id"] for f in _intake(sector)["granular"]["row_fields"]}
        assert core_required <= ids, f"{sector} missing canonical row fields: {core_required - ids}"
        assert ids <= bank_ids | {"latitude", "longitude"}, f"{sector} introduces an undisclosed field id: {ids - bank_ids}"

    agri_ids = {f["id"] for f in _intake("manufacturer")["granular"]["row_fields"]}
    assert core_required <= agri_ids
    new_ids = agri_ids - bank_ids
    assert new_ids == {"latitude", "longitude"}, f"unexpected undisclosed canonical ids: {new_ids}"


def test_markets_reit_sector_key_is_verbatim_not_nace():
    # a REIT's "sector" bucket is the property type as reported, not a NACE section — the spec must say so
    assert _intake("reit")["submission"].get("sector_key") == "verbatim"
    assert _intake("asset_manager")["submission"].get("sector_key") == "nace_section"
    assert _intake("manufacturer")["submission"].get("sector_key") == "verbatim"


def test_column_mapping_suggests_correctly_for_each_new_spec():
    cases = {
        "asset_manager": (["Geography (issuer / asset country)", "Issuer sector (NACE section or bucket)",
                           "Position value (€)", "of which in physical-risk zones (€)"], "submission"),
        "reit": (["Geography (property country / region)", "Property type (office, logistics, retail …)",
                 "Property value (€)", "of which in physical-risk zones (€)"], "submission"),
        "manufacturer": (["Origin country (ISO2)", "Commodity (as reported)", "Annual sourcing spend (€)",
                         "of which in physical-risk zones (€)"], "submission"),
    }
    for sector, (columns, kind) in cases.items():
        fields = _intake(sector)[kind]["cell_fields"]
        mapping = suggest_mapping(columns, fields)
        assert mapping["geography"] == columns[0]
        assert mapping["sector"] == columns[1]
        assert mapping["gross_carrying_amount_eur"] == columns[2]
        assert mapping["sensitive_physical_eur"] == columns[3]


def test_map_rows_validates_manufacturer_sourcing_plot_extract():
    fields = _intake("manufacturer")["granular"]["row_fields"]
    columns = ["Plot ID", "Commodity", "Annual sourcing spend", "Origin country", "Latitude", "Longitude"]
    mapping = suggest_mapping(columns, fields)
    assert mapping["instrument_id"] == "Plot ID"
    assert mapping["nace_section"] == "Commodity"
    assert mapping["outstanding_eur"] == "Annual sourcing spend"
    assert mapping["collateral_country"] == "Origin country"
    assert mapping["latitude"] == "Latitude" and mapping["longitude"] == "Longitude"

    csv_bytes = (
        "Plot ID,Commodity,Annual sourcing spend,Origin country,Latitude,Longitude\n"
        "PLOT-1,Cocoa,627000,GH,5.661263,-2.700859\n"
        "PLOT-2,Wheat,932000,CA,,\n"
    ).encode()
    rep = map_rows(csv_bytes, "plots.csv", fields, mapping)
    assert rep["ok"] and rep["n_valid"] == 2 and rep["n_error"] == 0
    assert rep["rows"][0]["latitude"] == 5.661263 and rep["rows"][0]["longitude"] == -2.700859
    assert rep["rows"][1]["latitude"] is None and rep["rows"][1]["longitude"] is None


def test_resolve_row_location_prefers_eudr_point_over_region():
    # a plot with a valid geolocation resolves to that exact point (point-resolved) — no network, no DB
    loc = _resolve_row_location({"latitude": 6.335089, "longitude": -2.104342, "collateral_country": "GH"})
    assert loc == {"lat": 6.335089, "lon": -2.104342, "name": None, "location_precision": "point"}

    # an out-of-range pair is not trusted as a point — falls through to the honest "unlocated" (no region fields)
    bad = _resolve_row_location({"latitude": 999, "longitude": -2.1, "collateral_country": "GH"})
    assert bad is None

    # no geolocation at all, and no region fields either → unlocated, never fabricated
    none_loc = _resolve_row_location({"collateral_country": "GH"})
    assert none_loc is None


def test_shadow_book_vertical_mapping_covers_all_five_sectors():
    """services.supervision.intake.build_shadow_book must resolve a vertical + entity type for every org type
    the profiles registry knows about, including the agri-food manufacturer — read from the same source file
    used at runtime so this test fails the moment the two drift apart."""
    import inspect

    src = inspect.getsource(__import__("services.supervision.intake", fromlist=["build_shadow_book"]).build_shadow_book)
    assert '"manufacturer": "agriculture"' in src
    assert '"agriculture": "plot"' in src
