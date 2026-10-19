"""What the KRI dashboard and the model-risk register send a screen, on the demo organisations (E-next): customer words
from the catalogue, the hazard register's standing on every score card, and a review bound to the card's facts only.

Requires PostgreSQL."""
from __future__ import annotations

import re

import pytest

from core import messages
from core.db.session import get_session
from services.governance import model_risk as MR
from services.governance.kri import kri, kri_detail, kri_frameworks
from services.intelligence.model_validation import hazard_for_channel

SETS = [("11111111-1111-4111-8111-111111111111", "bank_tcfd"), ("11111111-1111-4111-8111-111111111111", "bank_p3esg"),
        ("22222222-2222-4222-8222-222222222222", "insurer_solvency"), ("33333333-3333-4333-8333-333333333333", "reit_taxonomy"),
        ("44444444-4444-4444-8444-444444444444", "sfdr_pai"), ("55555555-5555-4555-8555-555555555555", "esrs_pack")]
# what a set sends as data, not words: codes, keys, the regulator's references (shown one click away)
DATA = {"key", "code", "params", "framework", "fmt", "kind", "status", "direction", "tone", "reg_tier", "group", "filing_id",
        "hazard", "entity_id", "esrs_version", "gap", "column", "unit", "id", "reg", "legal_basis", "form_url", "act", "where", "scenario"}
CITATION = re.compile(r"\bArt(?:icles?|s)?\.?\s?\d+|\bAnnex(?:es)?\s(?:[IVXL]+|\d+)\b|\bTemplate\s\d+")


def _words(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            if k not in DATA:
                yield from _words(v, f"{path}.{k}")
    elif isinstance(x, list):
        for v in x:
            yield from _words(v, path)
    elif isinstance(x, str):
        yield path, x


@pytest.mark.integration
@pytest.mark.parametrize("org,fw", SETS)
def test_a_kri_set_speaks_in_customer_words(org, fw):
    with get_session() as s:
        d = kri(s, org, fw)
        assert d["supported"] and d["kpis"]
        for k in d["kpis"]:
            assert k["about"]["code"].startswith("kri."), k["key"]
            assert k["hint"] == k["about"]["detail"]["what"]                 # the one-line readers get the same words
            for f in k["facts"]:
                assert f["label"] == messages.name("kri.fact", f["key"])
            assert k["gap"] is None or re.fullmatch(r"not stated: method\.[a-z0-9_]+(, method\.[a-z0-9_]+)*", k["gap"])
        bad = [(p, t[:80]) for p, t in _words(d) if messages.INTERNAL.search(t)]
        assert not bad, bad
        assert not CITATION.search(d["label"]), d["label"]                  # the set's name is on the main screen
        det = kri_detail(s, org, fw, d["kpis"][0]["key"])
        assert det["supported"] and not [(p, t) for p, t in _words(det) if messages.INTERNAL.search(t)]
        s.rollback()


@pytest.mark.integration
@pytest.mark.parametrize("org_type", ["bank", "insurer", "reit", "asset_manager", "manufacturer"])
def test_the_report_picker_names_reports_without_citations(org_type):
    for f in kri_frameworks(org_type):
        assert not CITATION.search(f["label"]) and not messages.INTERNAL.search(f["label"]), f


@pytest.mark.integration
def test_a_score_card_claims_what_the_hazard_register_holds():
    """E-next: the card's tier was its own rule (calibrated when the model's r² ≥ 0.40), so every rank-validated score —
    flood, wildfire, storms, heat — read 'screening, no euro figure' against the register's Validated."""
    with get_session() as s:
        for c in MR.cards(s, "manufacturer"):
            if c["kind"] != "score":
                continue
            reg = hazard_for_channel(c["hazard"])
            assert reg is not None and c["standing"] == reg.tier.value, c["ref"]
            assert c["claim"]["code"] == (f"coverage.tier.{reg.tier.value}" if c["active"] else "model.risk.claim.not_in_use")


@pytest.mark.integration
def test_a_review_is_bound_to_facts_a_feed_refresh_does_not_change(monkeypatch):
    """E-next: the hash covered each feed's last refresh, so every review went stale at the next scheduled refresh."""
    import services.data.feeds as F
    with get_session() as s:
        before = {c["ref"]: c["card_sha256"] for c in MR.cards(s, "manufacturer")}
        real = F.feeds_for_hazard
        monkeypatch.setattr(F, "feeds_for_hazard", lambda session, hz: [dict(f, status="overdue", last_refresh="2000-01-01T00:00:00")
                                                                          for f in real(session, hz)])
        after = MR.cards(s, "manufacturer")
        assert {c["ref"]: c["card_sha256"] for c in after} == before
        assert all(c["card_sha256"] == MR.sha256(MR.facts_of(c)) for c in after)


@pytest.mark.integration
def test_the_register_speaks_in_customer_words():
    """E-next: the card showed the registry's engineers' notes (file paths, table names) as its limitations, and its
    method, lifecycle and actors as raw codes."""
    from sqlalchemy import text
    with get_session() as s:
        algorithms = s.execute(text("""SELECT DISTINCT algorithm FROM model_registry
                                       WHERE lifecycle_status IN ('active', 'approved', 'challenger', 'candidate') AND hazard_type <> 'loop_test'""")).scalars().all()
        named = messages.names()["model.risk.method"]
        assert [a for a in algorithms if a not in named] == [], "a registered model's method has no name in the catalogue"
        v = MR.view(s, "55555555-5555-4555-8555-555555555555", "manufacturer")
        words = {k: c[k] for c in v["cards"] for k in MR.WORDS if k in c}
        bad = [(p, t[:80]) for p, t in _words({"cards": [{k: c.get(k) for k in MR.WORDS} for c in v["cards"]], "about": v["about"]})
               if messages.INTERNAL.search(t)]
        assert words and not bad, bad
