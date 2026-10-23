"""Pillar 3 ESG as the EBA's xBRL-CSV package for the Pillar 3 data hub: the binding read from the EBA's package, the
values in the EBA's types, the package to the EBA Filing Rules v5.8, and — where the EBA's packages are held
(XBRL_PACKAGES_DIR; CI's 'XBRL validation' job) — Arelle on the EBA's taxonomy.
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import zipfile
from datetime import date, datetime
from pathlib import Path

import pytest

from services.governance import p3esg_xbrlcsv as P

ROOT = Path(__file__).resolve().parents[2]
MAP = json.loads((ROOT / "data/reference/eba/p3esg_xbrlcsv.4.2.json").read_text())
HELD = os.environ.get("XBRL_PACKAGES_DIR")
REQUIRED = os.environ.get("XBRL_VALIDATION_REQUIRED") == "1"
LEI = "52990095BOVVFBIRFI19"
CREATED = datetime(2026, 7, 15, 10, 30, 0, 123000)


def _payload(period_end="2026-06-30", **extra):
    sys.path.insert(0, str(ROOT / "tests" / "unit"))
    from test_pillar3_grids import BOOK, METHOD
    book = BOOK + [{"nace_code": "35.11", "outstanding_loan_balance_eur": 500, "country": "ES", "emission_intensity": 410.0},
                   {"nace_code": "50.20", "outstanding_loan_balance_eur": 1000, "country": "ES", "emission_intensity": 28.8}]
    return {"assets": book, "method": METHOD, "_spec": {"version": "its_2024_3172"}, "_regulation": {"period_end": period_end},
            "_provided_attested": [{"key": "provided.T10.5.c", "value": 12500000}, {"key": "provided.T10.5.d", "value": "Yes"},
                                   {"key": "provided.T3.5.g", "value": 22.0}], **extra}


def _package(payload=None, role="consolidated"):
    return P.package(payload or _payload(), {"lei": LEI, "currency": "EUR"}, role=role, country="ES", created=CREATED)


def test_every_eba_datapoint_of_the_module_is_bound_to_an_its_cell():
    c = MAP["counts"]
    assert c["datapoints_not_bound"] == 0 and c["cells"] > 2500 and MAP["module"]["code"] == "ESGDIS"
    assert MAP["module"]["applies"] == {**MAP["module"]["applies"], "from": "2026-03-31", "until": None}
    # each bound cell's EBA code names the table the ITS template is printed in ('Template 1' → K_41.00)
    for key, e in MAP["cells"].items():
        if not key.startswith("NARRATIVE"):
            assert MAP["tables"][e["table"]]["template"] == key.split("|")[0], key
    # the ITS cells without a datapoint are cells the ITS greys out — none a printed total of a bound template
    assert "T1|56|a" in MAP["cells"] and "T8|16|ae" in MAP["cells"]          # EBA's 'qe.' label resolved by its column path
    assert all(MAP["row_keys"]["T10"][r]["MCY"] and MAP["row_keys"]["T10"][r]["CTN"] for r in MAP["row_keys"]["T10"])
    assert [MAP["row_keys"]["T3"][str(r)]["IEA"] for r in range(1, 9)] == [
        "eba_CT:x84", "eba_CT:x85", "eba_CT:x86", "eba_CT:x87", "eba_CT:x88", "eba_CT:x89", "eba_CT:x90", "eba_CT:x100"]


def test_the_annex_xl_crosswalk_is_the_ebas_template3_nace_list_code_for_code():
    """E339: the transcribed Annex XL list held '811' (NACE 81.1) under cement where the table has 08.11; the EBA's
    machine-readable list of the same table is the check."""
    xwalk = json.loads((ROOT / "data/reference/pillar3/nace_iea_crosswalk.json").read_text())["crosswalk"]
    allowed = next(k["allowed"] for k in MAP["tables"]["K_43.00.a"]["keys"] if k["name"] == "NAC")
    ours = {r["nace"] for r in xwalk}
    assert all(P._nace_member(allowed, code) for code in ours), sorted(c for c in ours if not P._nace_member(allowed, c))
    assert len(ours) == len(allowed)                                      # and nothing on the EBA's list is missing


def test_values_take_the_ebas_types():
    assert P.fact_value("m", 1234.5) == "1234" and P.fact_value("m", 1235.5) == "1236"   # to the unit, half to even
    assert P.fact_value("p", 12.34) == "0.1234" and P.fact_value("p", 100) == "1"         # a percentage as a ratio
    assert P.fact_value("i", 7.5) == "8" and P.fact_value("r", 410.0) == "410"
    assert P.fact_value("m", None) is None and P.fact_value("s", " ") is None              # a blank is no fact


def test_the_module_follows_the_reference_date():
    assert P.map_for(date(2026, 6, 30))["framework_release"] == "4.2"
    with pytest.raises(P.XbrlCsvError) as e:
        P.map_for(date(2025, 12, 31))
    assert e.value.code == "filing.refused.xbrlcsv_reference_date" and e.value.params["start"] == "2026-03-31"


def test_the_package_follows_the_eba_filing_rules(tmp_path):
    from scripts.validate_p3esg_xbrlcsv import filing_rules
    name, data, summary = _package()
    assert re.fullmatch(rf"{LEI}\.CON_ES_PILLAR3020100_ESGDIS_2026-06-30_20260715103000123\.zip", name)
    path = tmp_path / name
    path.write_bytes(data)
    problems, m = filing_rules(str(path))
    assert problems == [] and m["framework_release"] == "4.2"
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = name[:-4]
        read = {n[len(root) + 1:]: z.read(n).decode() for n in z.namelist()}
    assert read["reports/parameters.csv"].splitlines()[:3] == ["name,value", f"entityID,rs:{LEI}.CON", "refPeriod,2026-06-30"]
    fi = dict(line.split(",") for line in read["reports/FilingIndicators.csv"].splitlines()[1:])
    assert set(fi) == set(MAP["indicators"]) and fi["K_00.03"] == "false" and fi["K_41.00"] == "true"
    # Template 3: one row per sector × NACE code, keyed by the EBA's codes; the supplied target on its sector's rows
    t3 = read["reports/k_43.00.a.csv"].splitlines()
    assert t3[0] == "datapoint,factValue,IEA,NAC,ALG"
    assert any(",eba_CT:x88,eba_NC:H50_20," in line for line in t3) and any(line.startswith("dp470598,22,eba_CT:x88") for line in t3)
    # Template 5 row 13 by NACE section, per geography; Template 10 by instrument and counterparty
    assert {line.split(",")[2] for line in read["reports/k_45.00.b.csv"].splitlines()[1:]} == {"eba_NC:I", "eba_NC:J", "eba_NC:K"}
    assert "dp475417,12500000,eba_MC:x1281,eba_CT:x8" in read["reports/k_50.00.csv"].splitlines()
    assert summary["left_out"] == {"not_in_eba_model": [], "named_gaps": [], "unknown_member": []}
    assert _package()[1] == data                                           # the same frozen filing, the same bytes


def test_template2_column_p_goes_to_the_file_as_the_ebas_percentage():
    """Column p is the share of column o with an EP estimate (EBA Q&A 2022_6625), datapoint pi977, a ratio in the file."""
    import services.regspec as R
    from services.governance import pillar3_gar
    res = dict(immovable_collateral="residential", counterparty_sector="household")
    payload = _payload()
    payload["assets"] = payload["assets"] + [
        {"outstanding_loan_balance_eur": 200, "country": "DE", "ep_score_kwh_m2": 150, "ep_score_estimated": True, **res},
        {"outstanding_loan_balance_eur": 300, "country": "DE", **res}]
    p = pillar3_gar.build(R.load("bank_p3esg", "its_2024_3172"), payload["assets"], date(2026, 6, 30))["T2"]["1"]["p"]
    assert p is not None and 0 < p < 100
    name, data, summary = _package(payload)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        t2 = z.read(f"{name[:-4]}/reports/k_42.00.b.csv").decode().splitlines()
    assert f"{MAP['cells']['T2|1|p']['dp']},{P.fact_value('p', p)}" in t2 and summary["left_out"]["named_gaps"] == []


def test_every_reading_records_the_regulators_qa_check():
    """E341 guard — the standard for every regulatory reading: the EBA's Q&A is searched before a reading is declared or a
    gap named, and what it says is recorded (id, status, publishing date, the EBA's words) or 'none found', with the
    date of the check."""
    day = re.compile(r"\d{4}-\d{2}-\d{2}")
    for key, r in MAP["readings"].items():
        assert day.fullmatch(r.get("qa_checked") or ""), key
        qa = r.get("qa")
        assert (isinstance(qa, str) and qa.startswith("none found")) or (isinstance(qa, list) and qa), key
        for q in qa if isinstance(qa, list) else []:
            assert re.fullmatch(r"\d{4}_\d{4}", q["id"]) and q["url"].endswith("/publicId/" + q["id"]), (key, q)
            assert q["status"] in ("Final Q&A", "Rejected question") and day.fullmatch(q["published"]) and q["answer"], (key, q)


def test_a_filing_that_does_not_say_individual_or_consolidated_is_refused():
    with pytest.raises(P.XbrlCsvError) as e:
        _package(role="whole_org")
    assert e.value.code == "filing.refused.xbrlcsv_level"
    with pytest.raises(P.XbrlCsvError) as e:
        _package(_payload(_spec={"version": "its_2022_2453"}))
    assert e.value.code == "filing.refused.xbrlcsv_spec"


@pytest.mark.skipif(not (HELD or REQUIRED), reason="the EBA's packages are not held here (XBRL_PACKAGES_DIR)")
def test_the_package_is_valid_on_the_ebas_taxonomy(tmp_path):
    from scripts.validate_p3esg_xbrlcsv import validate
    name, data, _ = _package()
    path = tmp_path / name
    path.write_bytes(data)
    res = validate(str(path))                     # a missing or altered package raises: never a silent pass
    assert res["filing_rules"] == [] and res["xbrl_errors"] == [], res
    # the EBA's severity sets switch every ESGDIS assertion off (data/reference/eba 'validation'): none evaluates
    assert res["assertions"] == 2743 and res["evaluated"] == 0 and res["module"] == "ESGDIS 2.1.0"
