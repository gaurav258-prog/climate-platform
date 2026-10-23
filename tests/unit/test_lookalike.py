"""The lookalike customers' standard files hold only official figures and the assumptions they state (the product owner's
decisions of 2026-10-23: made-up firms, real places, values from official statistics where a country publishes them).
Read from the committed files themselves, so the test needs none of the large source data."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from services.ingest.fund_books import isin_ok
from services.intake.workbooks import sheets

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "data" / "demo" / "lookalike"
PRICES = json.loads((DIR / "prices.json").read_text())
STATED = json.loads((DIR / "assumptions.json").read_text())


def _rows(firm: str, sheet: str) -> list[dict]:
    wb = load_workbook(DIR / f"{firm}_standard_file.xlsx", read_only=True, data_only=True)
    ws = wb[sheet]
    head = [str(c).removesuffix(" *") for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=True))]
    return [dict(zip(head, r)) for r in ws.iter_rows(min_row=2, values_only=True) if any(v is not None for v in r)]


def test_every_figure_source_is_quoted_with_its_checksum():
    for s in PRICES["sources"]:
        assert s["url"].startswith("https://") and len(s["sha256"]) == 64 and s["licence"] and s["publisher"]


@pytest.mark.parametrize("firm", ["weserland", "brezal", "skarvholm", "kestrel", "quejigo"])
def test_each_file_reads_back_as_its_sectors_books(firm):
    raw = (DIR / f"{firm}_standard_file.xlsx").read_bytes()
    got = {k: n for _, k, n in sheets(raw, STATED[firm]["type"]) if n}
    assert got, firm


def test_spanish_values_are_the_ministrys_price_times_the_stated_size():
    floor = STATED["brezal"]["assumptions"]["floor_m2_per_building"]
    official = {round(v["eur_per_m2"] * floor) for v in PRICES["es_residential"]["by_nuts3"].values()}
    rows = _rows("brezal", "Property schedule")
    assert len(rows) == STATED["brezal"]["assumptions"]["buildings"]
    assert {r["property_value_eur"] for r in rows} <= official


def test_swedish_sums_insured_are_the_official_rebuild_cost():
    se = PRICES["se_rebuild"]
    rebuild = round(se["building_price_sek_per_m2"] * se["floor_m2_per_dwelling"])
    rows = _rows("skarvholm", "Statement of Values")
    assert {(r["building_value_eur"], r["sum_insured_eur"], r["currency"]) for r in rows} == {(rebuild, rebuild, "SEK")}


def test_german_values_are_the_stated_assumption_by_area_type():
    a = STATED["weserland"]["assumptions"]
    rows = _rows("weserland", "Loan tape")
    assert {r["appraised_value_eur"] for r in rows} <= set(a["appraised_value_eur_by_area_type"].values())
    assert all(r["outstanding_loan_balance_eur"] == round(r["appraised_value_eur"] * a["loan_to_value"]) for r in rows)
    assert {r["counterparty_sector"] for r in rows} == {"household"} and all(r.get("counterparty_evic_eur") is None for r in rows)


def test_olive_spend_is_official_yield_times_oil_share_times_price():
    o, a = PRICES["olive_jaen"], STATED["quejigo"]["assumptions"]
    per_kg = o["oil_price_eur_per_100kg_jaen_mix"] / 100
    want = {"irrigated": round(a["plot_area_ha"] * o["yield_irrigated_kg_ha"] * o["oil_per_olive"] * per_kg),
            "rain_fed": round(a["plot_area_ha"] * o["yield_dry_kg_ha"] * o["oil_per_olive"] * per_kg)}
    rows = _rows("quejigo", "Sourcing plots")
    assert len(rows) == a["plots"] and all(r["annual_spend_eur"] == want[r["irrigation_status"]] for r in rows)


def test_the_fund_holds_real_listed_companies_by_isin():
    universe = {r["isin"] for r in csv.DictReader((ROOT / "data" / "universe" / "eu_common_equities.csv").open())}
    rows = _rows("kestrel", "Fund holdings")
    assert len(rows) == STATED["kestrel"]["assumptions"]["holdings"]
    assert all(isin_ok(r["isin"]) and r["isin"] in universe for r in rows)
