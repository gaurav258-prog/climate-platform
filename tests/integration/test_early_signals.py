"""CRCS early warning: regulators' feeds and the press — unconfirmed until the official register records a change.

  * topics match whole words only ('regarding' is not 'GAR'); an item naming no tracked topic is not kept
  * an EU item reaches organisations filing a framework it concerns; a UK or US item only those present there
  * an item the register later records is marked confirmed and linked; a dismissed item is no longer shown
Runs inside a rolled-back transaction, with simulated feeds."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from services.regulatory_monitoring import early_signals as E
from tests.integration.test_intake_pipeline import BANK_ORG

pytestmark = pytest.mark.integration
NOW = datetime.now(timezone.utc)


def test_topics_match_whole_words_only():
    assert E.classify("EBA consults on Pillar 3 ESG risk disclosures") == (["pillar3_esg"], ["bank_p3esg"])
    assert E.classify("A note regarding the garden") == ([], [])
    t, f = E.classify("ESMA updates Q&A on SFDR and the EU Taxonomy")
    assert set(t) == {"sfdr", "taxonomy"} and "sfdr_pai" in f and "bank_tcfd" in f


@pytest.fixture()
def s(session_rolled_back, monkeypatch):
    feeds = {
        "eba": [{"url": "https://t.example/eba-1", "title": "EBA final draft ITS on Pillar 3 ESG risks", "summary": "", "published_at": NOW - timedelta(days=3)},
                {"url": "https://t.example/eba-2", "title": "EBA staff changes", "summary": "", "published_at": NOW}],
        "fca": [{"url": "https://t.example/fca-1", "title": "FCA consults on climate-related disclosure for listed issuers", "summary": "", "published_at": NOW}],
    }
    monkeypatch.setattr(E, "_rss", lambda url: next((v for k, v in feeds.items() if f"{k}." in url or f"/{k}" in url), []))
    monkeypatch.setattr(E, "_gdelt", lambda src: [])
    monkeypatch.setattr(session_rolled_back, "commit", session_rolled_back.flush)
    return session_rolled_back


def _fws():
    return ["bank_tcfd", "bank_p3esg"]


def test_only_relevant_items_are_kept_and_jurisdiction_filters(s):
    out = E.sweep(s)
    urls = {r[0] for r in s.execute(text("SELECT url FROM reg_early_signal WHERE url LIKE 'https://t.example/%'")).all()}
    assert urls == {"https://t.example/eba-1", "https://t.example/fca-1"} and out["errors"] == []
    s.execute(text("UPDATE organizations SET country = 'DE' WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG})
    s.execute(text("UPDATE reporting_entities SET country = NULL WHERE org_id = CAST(:o AS uuid)"), {"o": BANK_ORG})
    seen = {x["url"] for x in E.for_org(s, BANK_ORG, _fws())["signals"]}
    assert "https://t.example/eba-1" in seen and "https://t.example/fca-1" not in seen       # no UK presence
    ent = s.execute(text("SELECT entity_id FROM reporting_entities WHERE org_id = CAST(:o AS uuid) LIMIT 1"), {"o": BANK_ORG}).scalar()
    if ent:
        s.execute(text("UPDATE reporting_entities SET country = 'GB' WHERE entity_id = :e"), {"e": ent})
        assert "https://t.example/fca-1" in {x["url"] for x in E.for_org(s, BANK_ORG, _fws())["signals"]}


def test_the_register_confirms_and_a_dismissed_item_is_hidden(s):
    E.sweep(s)
    s.execute(text("""INSERT INTO reg_detected_change (framework, celex, title, summary, status)
                      VALUES ('bank_p3esg', '32099R0077', 'Pillar 3 — a new act', 's', 'pending_review')"""))
    E.sweep(s)                    # (a real Pillar 3 change already on the register may have confirmed it on the first sweep)
    sig = s.execute(text("SELECT signal_id::text, status, confirmed_by FROM reg_early_signal WHERE url = 'https://t.example/eba-1'")).mappings().first()
    assert sig["status"] == "register_confirmed" and sig["confirmed_by"] is not None
    E.dismiss(s, sig["signal_id"])
    assert "https://t.example/eba-1" not in {x["url"] for x in E.for_org(s, BANK_ORG, _fws())["signals"]}
