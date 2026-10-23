"""The official XBRL packages the exports are validated on: pinned in the reference data, fetched only as pinned, and
the S.27.01.01 instance validated with Arelle on EIOPA's published package and EIOPA's own rules (the Pillar 3 package
on the EBA's: tests/unit/test_p3esg_xbrlcsv.py).

The validation runs where the packages are held (XBRL_PACKAGES_DIR — CI's 'XBRL validation' job fetches them with
scripts/fetch_xbrl_packages.py); elsewhere it is skipped, unless XBRL_VALIDATION_REQUIRED=1, where a missing package
fails the run instead of passing it unvalidated.
"""
from __future__ import annotations

import json
import os
from datetime import date

import pytest

import services.regspec as R
from scripts.fetch_xbrl_packages import pins
from services.governance import s2701
from services.governance import s2701_xbrl as X
from services.governance.insurer_solvency import KEY
from services.governance.solvency2_natcat import natcat_scr

HELD = os.environ.get("XBRL_PACKAGES_DIR")
REQUIRED = os.environ.get("XBRL_VALIDATION_REQUIRED") == "1"


def test_every_taxonomy_the_exports_use_is_pinned_to_its_published_file():
    got = pins()
    for m in (X._load("2.8.2"), X._load("2.10.0")):
        pk = m["package"]
        assert pk["url"].startswith("https://dev.eiopa.europa.eu/Taxonomy/Full/") and pk["url"].endswith(pk["file"])
        assert len(pk["sha256"]) == 64 and pk["bytes"] > 10_000_000 and pk["licence"]["quote"]
        assert any(p["file"] == pk["file"] and p["sha256"] == pk["sha256"] for p in got)
    # EIOPA's 2.8.2 entry point names its deactivation list by its published address; the package's own copy is frozen
    # at release, so the list EIOPA keeps current is pinned apart
    assert X._load("2.8.2")["deactivations"]["url"] == "https://dev.eiopa.europa.eu/Taxonomy/Full/deactivations/282/ars-ignore-val.xml"
    assert all(p["url"].startswith("https://") and len(p["sha256"]) == 64 for p in got)
    eba = [p for p in got if p["publisher"] == "eba"]                  # the EBA's taxonomy and its latest rule set
    assert {m["member"] for p in eba for m in p["extract"]} >= {"EBA_XBRL_4.2_Dictionary_4.2.0.0.zip",
                                                                "EBA_XBRL_4.2_Reporting_Frameworks_4.2.0.0.zip",
                                                                "EBA_XBRL_4.2_SET_4.3.0.1.zip"}


def test_a_file_whose_size_is_not_the_pinned_one_is_refused_before_any_download(tmp_path, monkeypatch):
    import scripts.download as D
    from scripts.fetch_xbrl_packages import fetch
    pin = {"publisher": "eiopa", "version": "9.9.9", "file": "x.zip", "url": "https://example.invalid/x.zip",
           "bytes": 100, "sha256": "0" * 64}
    monkeypatch.setattr(D, "remote_size", lambda url: (200, 101))
    monkeypatch.setattr(D, "download", lambda *a, **k: pytest.fail("downloaded a file the pin does not describe"))
    assert fetch(pin, tmp_path).startswith("refused")


def _instance() -> str:
    spec = R.load(s2701.FAMILY, "its_2023_894")
    supplied = {"S2701.R0750.C0040": 5e6}
    sf = natcat_scr([{"country": "DE", "postal_code": "01067", "sum_insured_eur": 1e8},
                     {"country": "FR", "postal_code": "75001", "sum_insured_eur": 1e9},
                     {"country": "ES", "postal_code": "46001", "sum_insured_eur": 2e8},
                     {"country": "US", "sum_insured_eur": 1e9}],
                    ref_date=date(2025, 12, 31), other_inputs=s2701.premiums_from_supplied(spec, supplied))
    payload = {KEY: {"standard_formula_natcat": sf}, "_specs": {s2701.FAMILY: {"version": "its_2023_894"}},
               "_provided_attested": [{"key": "provided." + k, "value": v} for k, v in supplied.items()]}
    return X.instance(payload, {"lei": "5299000J2N45DDNE4Y28", "name": "Test undertaking", "note": "test"})


@pytest.mark.skipif(not (HELD or REQUIRED), reason="EIOPA's package is not held here (XBRL_PACKAGES_DIR)")
def test_the_s2701_instance_passes_eiopas_own_rules_on_the_published_package(tmp_path):
    from scripts.validate_s2701_xbrl import validate
    p = tmp_path / "s2701.xbrl"
    p.write_text(_instance(), encoding="utf-8")
    res = validate(str(p))                       # a missing or altered package raises: never a silent pass
    if os.environ.get("XBRL_VALIDATION_REPORT"):
        with open(os.environ["XBRL_VALIDATION_REPORT"], "w") as out:
            json.dump({**res, "evaluated": {k: list(v) for k, v in res["evaluated"].items()}}, out, indent=1)
    assert res["taxonomy"] == "2.8.2" and res["deactivations"] == "2026-06-03"
    assert {"interval-arithmetics.xml", "math.xml", "isin-check.xml"} <= set(res["functions"])
    assert not res["instance_errors"] and not res["failed_in_scope"], res
    assert set(res["failed_needing_other_submodules"]) <= {"BV264_1-1"}    # needs man-made / other sub-modules
    assert len(res["evaluated"]) >= 15
