"""CRCS record retention: how long a filed report must be kept, under which law — and a legal hold.

  * a management-report document takes its framework rules plus the accounting law of the filer's country; the
    latest date wins; a pre-submission 'publication' rule is provisional
  * a reporting entity's own country overrides the organisation's
  * the organisation's own policy can lengthen, never shorten
  * a country without a verified rule is said plainly
  * a legal hold is set with a reason; lifting it needs a second person
Runs inside a rolled-back transaction, with sample rules (the real periods live in the reference file)."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import text

from services.governance import record_retention as R
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration

SAMPLE = {
    "version": "test",
    "documents": {"bank_tcfd": {"document": "management_report", "rules": ["listed_afr"], "national": True},
                  "bank_p3esg": {"document": "pillar3", "rules": ["crr_434"], "national": False}},
    "frameworks": {
        "listed_afr": {"key": "listed_afr", "years": 10, "runs_from": "publication", "act": "Directive 2004/109/EC", "article": "Art. 4(1)",
                       "url": "https://eur-lex.europa.eu/eli/dir/2004/109/oj", "quote": "at least ten years"},
        "crr_434": {"key": "crr_434", "years": 5, "runs_from": "publication", "act": "Regulation (EU) 575/2013", "article": "Art. 434",
                    "url": "https://eur-lex.europa.eu/eli/reg/2013/575/oj", "quote": "five years"},
    },
    "national": {
        "DE": [{"key": "de_hgb", "covers": ["management_report"], "years": 10, "runs_from": "end_of_calendar_year_prepared",
                "act": "HGB", "article": "§ 257", "url": "https://www.gesetze-im-internet.de/hgb/__257.html", "quote": "zehn Jahre"}],
        "ES": [{"key": "es_ccom", "covers": ["management_report"], "years": 6, "runs_from": "end_of_calendar_year_prepared",
                "act": "Código de Comercio", "article": "art. 30", "url": "https://www.boe.es", "quote": "seis años"}],
    },
}


@pytest.fixture()
def s(session_rolled_back, monkeypatch):
    monkeypatch.setattr(R, "rules", lambda: SAMPLE)
    session_rolled_back.execute(text("UPDATE organizations SET country = 'DE' WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG})
    return session_rolled_back


_YEAR = iter(range(2040, 2140))


def _filing(s, framework="bank_tcfd", entity_id=None):
    snap = s.execute(text("SELECT snapshot_id FROM report_snapshots WHERE org_id = CAST(:o AS uuid) LIMIT 1"), {"o": BANK_ORG}).scalar()
    return s.execute(text("""INSERT INTO regulatory_filing (org_id, framework, period_end, period_label, status, snapshot_id, entity_id)
                             VALUES (CAST(:o AS uuid), :f, :pe, 'FY' || EXTRACT(YEAR FROM CAST(:pe AS date))::int, 'draft', :s, CAST(:e AS uuid)) RETURNING filing_id::text"""),
                     {"o": BANK_ORG, "f": framework, "s": snap, "e": entity_id, "pe": date(next(_YEAR), 12, 31)}).scalar()


def test_framework_and_national_rules_the_latest_wins_and_unsubmitted_is_provisional(s):
    fid = _filing(s)
    r = R.retention_for(s, BANK_ORG, fid)
    keys = {x["key"] for x in r["rules"]}
    assert keys == {"listed_afr", "de_hgb"} and r["country"] == "DE" and r["provisional"]
    assert r["keep_until"] == max(x["until"] for x in r["rules"]) and not r["may_be_archived"]
    hgb = next(x for x in r["rules"] if x["key"] == "de_hgb")
    frozen_year = int(hgb["from"][:4])
    assert hgb["from"].endswith("-12-31") and hgb["until"] == date(frozen_year + 10, 12, 31).isoformat()


def test_a_pillar3_document_takes_only_its_own_rule(s):
    r = R.retention_for(s, BANK_ORG, _filing(s, "bank_p3esg"))
    assert [x["key"] for x in r["rules"]] == ["crr_434"] and r["document"] == "pillar3"


def test_an_entitys_own_country_governs_and_an_unknown_country_is_said(s):
    ent = s.execute(text("SELECT entity_id::text FROM reporting_entities WHERE org_id = CAST(:o AS uuid) LIMIT 1"), {"o": BANK_ORG}).scalar()
    if not ent:
        pytest.skip("no seeded entity")
    s.execute(text("UPDATE reporting_entities SET country = 'ES' WHERE entity_id = CAST(:e AS uuid)"), {"e": ent})
    r = R.retention_for(s, BANK_ORG, _filing(s, entity_id=ent))
    assert r["country"] == "ES" and "es_ccom" in {x["key"] for x in r["rules"]}
    s.execute(text("UPDATE reporting_entities SET country = 'JP' WHERE entity_id = CAST(:e AS uuid)"), {"e": ent})
    r = R.retention_for(s, BANK_ORG, _filing(s, entity_id=ent))
    assert r["country"] == "JP" and any("JP" in g for g in r["gaps"])


def test_the_organisations_policy_lengthens_never_shortens(s, monkeypatch):
    fid = _filing(s)
    base = R.retention_for(s, BANK_ORG, fid)
    monkeypatch.setattr(R, "_org_policy_years", lambda session, org: 1)
    assert R.retention_for(s, BANK_ORG, fid)["keep_until"] == base["keep_until"]
    monkeypatch.setattr(R, "_org_policy_years", lambda session, org: 40)
    longer = R.retention_for(s, BANK_ORG, fid)
    assert longer["keep_until"] > base["keep_until"] and longer["policy_until"] == longer["keep_until"]


def test_a_legal_hold_is_set_with_a_reason_and_lifted_only_by_a_second_person(s):
    fid = _filing(s)
    maker = s.execute(text("SELECT user_id::text FROM users WHERE email = 'admin@meridian.demo'")).scalar()
    checker = s.execute(text("SELECT user_id::text FROM users WHERE email = 'approver@meridian.demo'")).scalar()
    with pytest.raises(R.RetentionError):
        R.set_hold(s, BANK_ORG, fid, maker, "  ")
    assert R.set_hold(s, BANK_ORG, fid, maker, "tax audit 2027")["legal_hold"]["on"]
    req = R.request_lift(s, BANK_ORG, fid, maker, "audit closed")
    assert R.retention_for(s, BANK_ORG, fid)["legal_hold"]["on"]                  # nothing changes before approval
    payload = s.execute(text("SELECT payload FROM approval_requests WHERE request_id = CAST(:r AS uuid)"), {"r": req["approval_request_id"]}).scalar()
    assert R.apply_lift(s, BANK_ORG, payload, "approved", checker)["applied"]
    assert not R.retention_for(s, BANK_ORG, fid)["legal_hold"]["on"]
    events = [r[0] for r in s.execute(text("SELECT action FROM regulatory_filing_event WHERE filing_id = CAST(:f AS uuid) ORDER BY created_at, event_id"), {"f": fid}).all()]
    assert events[-2:] == ["legal_hold.set", "legal_hold.lifted"]


# ── the real reference file (verified 2026-09-28) ─────────────────────────────────────────────────────────────

@pytest.fixture()
def real(session_rolled_back):
    R.rules.cache_clear()
    return session_rolled_back


def _set(s, country, listed):
    s.execute(text("UPDATE organizations SET country = :c WHERE org_id = CAST(:o AS uuid)"), {"c": country, "o": BANK_ORG})
    s.execute(text("UPDATE reporting_entities SET country = NULL WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG})
    s.execute(text("DELETE FROM org_regulatory_attribute WHERE org_id = CAST(:o AS uuid) AND attribute = 'listed'"), {"o": BANK_ORG})
    if listed is not None:
        s.execute(text("""INSERT INTO org_regulatory_attribute (org_id, attribute, value_bool, source, updated_at)
                          VALUES (CAST(:o AS uuid), 'listed', :v, 'entity', now())"""), {"o": BANK_ORG, "v": listed})


def test_every_rule_in_the_reference_file_is_cited():
    R.rules.cache_clear()
    ref = R.rules()
    rules = [r for rs in ref["national"].values() for r in rs] + list(ref["frameworks"].values())
    assert rules and all(r["url"].startswith("https://") and r["quote"] and r["article"] for r in rules)
    assert all(r["runs_from"] in ref["runs_from"] for r in rules if r.get("years"))


def test_germany_names_the_management_report_ten_years(real):
    _set(real, "DE", False)
    r = R.retention_for(real, BANK_ORG, _filing(real))
    de = next(x for x in r["rules"] if x["key"] == "de_hgb_257")
    assert de["years"] == 10 and de["coverage"] == "named" and not any("td_art4" == x["key"] for x in r["rules"])


def test_a_listed_issuer_keeps_ten_years_from_publication_and_unknown_listing_is_asked(real):
    _set(real, "AT", True)
    r = R.retention_for(real, BANK_ORG, _filing(real))
    assert {x["key"] for x in r["rules"]} == {"td_art4", "at_ugb_212"} and r["provisional"]
    _set(real, "AT", None)
    r = R.retention_for(real, BANK_ORG, _filing(real))
    assert any("listed" in g for g in r["gaps"])


def test_pillar3_takes_the_national_period_and_the_uk_has_no_statutory_period(real):
    _set(real, "PL", True)
    r = R.retention_for(real, BANK_ORG, _filing(real, "bank_p3esg"))
    assert [x["key"] for x in r["rules"]] == ["crr_434:pl_uor_74_1"] and r["rules"][0]["years"] == 5
    _set(real, "GB", True)
    r = R.retention_for(real, BANK_ORG, _filing(real, "bank_p3esg"))
    assert r["rules"] == [] and any("Companies Act 2006" in g for g in r["gaps"])
