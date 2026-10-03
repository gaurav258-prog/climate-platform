"""A flagged company figure is resolved by a person — corrected, or confirmed with a reason for that exact value (a
changed figure is checked again) — and an open flag blocks an EET version. A vendor never overwrites the manager's own
figure. Rolled back."""
import pytest
from sqlalchemy import text

from services.eet import share_classes as S
from services.eet.publication import EETError, prepare
from services.fund_disclosure import fund_esg_pai
from services.fund_energy import confirm
from services.reference.vendor_ingest import ingest_vendor_extract

pytestmark = pytest.mark.integration


def _setup(s):
    """Nordkap's Global Equity Fund and two of the fictional demo issuers it holds (E147: the demo holds no real
    company); the manager's own 2023 figure for Iberia Foods is stated here, inside the rolled-back transaction."""
    org, fund = s.execute(text("SELECT org_id::text, fund_id::text FROM funds WHERE name = 'Nordkap Global Equity Fund'")).first()
    foods = s.execute(text("SELECT issuer_id::text FROM securities WHERE isin = 'ES00FOODS001'")).scalar()
    logis = s.execute(text("SELECT issuer_id::text FROM securities WHERE isin = 'NL00LOGIS001'")).scalar()
    assert foods and logis, "the fictional demo issuers are seeded (scripts/seed_demo_asset_manager.py)"
    s.execute(text("""INSERT INTO issuer_esg_metrics (issuer_id, org_id, reporting_year, non_renewable_energy_pct, source)
                      VALUES (CAST(:i AS uuid), CAST(:o AS uuid), 2023, 18, 'client')
                      ON CONFLICT (issuer_id, reporting_year, org_id) WHERE org_id IS NOT NULL
                      DO UPDATE SET non_renewable_energy_pct = 18, energy_consumption_gwh = NULL, source = 'client'"""),
              {"i": foods, "o": org})
    return org, fund, foods, logis


def _flags(s, fund):
    return [(o["issuer"], o["field"]) for o in fund_esg_pai(s, fund)["energy_outliers"]]


def test_a_unit_slip_is_flagged_until_corrected_or_confirmed(session_rolled_back):
    s = session_rolled_back
    org, fund, _, logis = _setup(s)
    assert _flags(s, fund) == []
    s.execute(text("UPDATE issuer_esg_metrics SET energy_intensity_gwh_per_meur = 50 WHERE issuer_id = CAST(:i AS uuid)"), {"i": logis})
    assert _flags(s, fund) == [("Global Logistics NV", "energy_intensity")]       # 50 GWh/€M: MWh typed as GWh
    S.create(s, org, fund, {"isin": "LU0274208692", "name": "A", "currency": "EUR", "distribution": "accumulating"}, None)
    with pytest.raises(EETError, match="unit slip"):
        prepare(s, org, None, ["entity"])
    with pytest.raises(ValueError, match="say why"):
        confirm(s, org, logis, "energy_intensity", 50, " ", None)
    confirm(s, org, logis, "energy_intensity", 50, "checked against the 2024 annual report, p. 212", None)
    assert _flags(s, fund) == []
    s.execute(text("UPDATE issuer_esg_metrics SET energy_intensity_gwh_per_meur = 60 WHERE issuer_id = CAST(:i AS uuid)"), {"i": logis})
    assert _flags(s, fund) == [("Global Logistics NV", "energy_intensity")]       # a different value is checked again


def test_a_vendor_never_overwrites_the_managers_own_figure(session_rolled_back):
    s = session_rolled_back
    org, _, foods, _ = _setup(s)
    before = s.execute(text("SELECT CAST(non_renewable_energy_pct AS FLOAT), CAST(energy_consumption_gwh AS FLOAT) FROM issuer_esg_metrics "
                            "WHERE issuer_id = CAST(:i AS uuid) AND reporting_year = 2023 AND org_id = CAST(:o AS uuid)"),
                       {"i": foods, "o": org}).first()
    rep = ingest_vendor_extract(s, org, [{"ISIN": "ES00FOODS001", "PCT_NONRENEW_ENERGY": "90", "ENERGY_CONSUMPTION_GWH": "410"}],
                                profile="msci", reporting_year=2023)
    after = s.execute(text("SELECT CAST(non_renewable_energy_pct AS FLOAT), CAST(energy_consumption_gwh AS FLOAT), source FROM issuer_esg_metrics "
                           "WHERE issuer_id = CAST(:i AS uuid) AND reporting_year = 2023 AND org_id = CAST(:o AS uuid)"),
                      {"i": foods, "o": org}).first()
    assert after[0] == before[0] == 18.0 and after[2] == "client"               # the manager's 18% stands
    assert after[1] == 410.0 and before[1] is None                               # the vendor filled a blank
    assert rep["client_conflicts"] >= 1


def test_the_check_band_is_the_organisations_governed_setting(session_rolled_back):
    from services.calc_settings import upsert_calc_settings
    s = session_rolled_back
    org, fund, _, logis = _setup(s)
    s.execute(text("UPDATE issuer_esg_metrics SET energy_intensity_gwh_per_meur = 5 WHERE issuer_id = CAST(:i AS uuid)"), {"i": logis})
    assert _flags(s, fund) == [("Global Logistics NV", "energy_intensity")]
    upsert_calc_settings(s, org, {"esg_energy_intensity_check_factor": 1000.0}, None)
    assert _flags(s, fund) == []
