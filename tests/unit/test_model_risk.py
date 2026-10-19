"""Model-risk register: a card's review is bound to its facts only (never its words or its feeds' freshness), conclusions
are fixed, refusals are catalogue messages, and the CSV and card PDF render from a card in the catalogue's words."""
import pytest

from core import messages
from core.errors import UserError
from services.governance import model_risk as MR
from services.governance.model_risk import (
    CONCLUSIONS,
    canonical_json,
    facts_of,
    register_csv,
    render_card_pdf,
    sha256,
)


def _card(**kw):
    c = {"ref": "model:abc", "kind": "score", "hazard": "seismic", "register_hazard": "seismic", "model": "seismic-gmpe-ipe-v1",
         "algorithm": "physics_ipe_omori", "lifecycle": "active", "active": True, "standing": "screening",
         "r2_oos": None, "auc": None, "gate": 0.40,
         "fidelity": {"family_label": "Ranking Fidelity", "symbol": "RF", "value": 83.3, "band": "strong", "band_label": "Strong", "published": True, "floor": 35.0},
         "validation": {"level": "hazard", "kind": "discrimination", "method": "temporal_holdout", "design": "held_out", "record": "USGS/EMSC seismic",
                        "n_samples": 9568, "skill_grade": "fair", "passed_gate": True, "metrics": {}, "at": "2026-08-28T00:00:00"},
         "data": {"training_vintage": "2026-06-25", "training_cells": 9241, "feeds": ["geophysical"]},
         "governance": {"approved_by": None, "approved_at": None, "activated_by": "backtest_seismic", "activated_at": None, "registered_at": "2026-06-27",
                        "events": [{"from": None, "to": "candidate", "actor": "a", "reason": "registered", "r2_oos": None, "at": "2026-06-27T00:00:00"}]},
         "controls": ["C-MOD-01"], "review": None, "review_state": "none"}
    c.update(kw)
    c["card_sha256"] = sha256(facts_of(c))
    MR._words(c, [{"key": "geophysical", "name": "USGS seismic", "status": "fresh", "last_refresh": "2026-10-18T22:00:00"}], {})
    return c


def test_card_hash_is_canonical_and_changes_with_its_facts():
    a, b = _card(), _card()
    assert a["card_sha256"] == b["card_sha256"] and len(a["card_sha256"]) == 64
    assert _card(r2_oos=0.5)["card_sha256"] != a["card_sha256"]
    assert _card(lifecycle="retired")["card_sha256"] != a["card_sha256"]
    assert canonical_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_a_review_is_bound_to_the_facts_not_the_words_or_a_feed_refreshing():
    """E235: the hash covered each feed's last refresh, so every scheduled feed refresh made every review stale; and
    it covered the card's sentences, so rewording made them stale too. Only the facts are hashed now."""
    a = _card()
    refreshed = dict(a, feeds=[{"key": "geophysical", "name": "USGS seismic", "status": "overdue", "last_refresh": "2026-10-19T09:00:00"}])
    assert sha256(facts_of(refreshed)) == a["card_sha256"]
    reworded = dict(a, claim={"label": "Other words", "detail": {"what": "Other words."}}, method_name="Something else")
    assert sha256(facts_of(reworded)) == a["card_sha256"]
    assert sha256(facts_of(a)) == a["card_sha256"]            # the words added after hashing leave the facts as they were
    assert not set(MR.WORDS) & set(facts_of(a))


def test_a_card_speaks_in_the_catalogues_words():
    c = _card()
    assert c["claim"]["code"] == "coverage.tier.screening" and c["basis"]["code"] == "coverage.hazard.seismic"
    assert c["method_name"] == messages.name("model.risk.method", "physics_ipe_omori")
    assert c["governance_names"]["activated_by"] == messages.name("model.risk.actor", "process")   # a process's own id is not a name
    assert c["validation_names"]["design"] == "Held out in time" and c["lifecycle_name"] == "In use"
    assert _card(active=False, lifecycle="candidate")["claim"]["code"] == "model.risk.claim.not_in_use"


def test_conclusions_are_fixed_and_explicit():
    assert set(CONCLUSIONS) == {"fit_for_use", "restricted_use", "not_fit"}


@pytest.mark.parametrize("conclusion,comment,code", [("perfect", None, "model.risk.error.conclusion"),
                                                     ("restricted_use", "  ", "model.risk.error.comment")])
def test_a_refused_review_is_a_catalogue_message(conclusion, comment, code):
    with pytest.raises(UserError) as e:
        MR.review(None, org_id="o", org_type="bank", model_ref="model:abc", actor={"id": "u"}, conclusion=conclusion, comment=comment, next_review_by=None)
    assert e.value.code == code and code in messages.catalogue()


def test_csv_and_card_pdf_render():
    impact = _card(ref="calibration:x:ES:drought", kind="impact", hazard="drought", commodity="Olive oil", origin="ES", standing="ranged",
                   lifecycle="published", r2_oos=0.51, active=True, algorithm="ranged_fit", fidelity={"value": 51.0, "band_label": "Directional"},
                   validation={"level": "model", "kind": "regression", "method": "loo_cv", "design": "harvests", "n_years": 31, "baseline": [1991, 2021], "challenger": None})
    lines = register_csv({"cards": [_card(), impact]}).decode("utf-8").splitlines()
    assert len(lines) == 3 and lines[0].startswith("Ref,Kind,Model,Hazard")
    assert "Publishes a euro range" in lines[2] and "physics_ipe_omori" not in lines[1]
    pdf = render_card_pdf(_card(), "Test Foods", [{"reviewed_at": "2026-09-09T20:00:00", "reviewer": "Ana", "conclusion_label": "Fit for use with restrictions (see comment)", "comment": "screening only", "next_review_by": "2027-03-31", "evidence_sha256": "abcd" * 16}])
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2500
