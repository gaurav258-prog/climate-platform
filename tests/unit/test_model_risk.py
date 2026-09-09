"""Model-risk register: cards are hashed canonically, conclusions are fixed, the CSV and card PDF render from a card."""
from services.governance.model_risk import (
    CONCLUSIONS,
    canonical_json,
    register_csv,
    render_card_pdf,
    sha256,
)


def _card(**kw):
    c = {"ref": "model:abc", "kind": "score", "hazard": "seismic", "name": "seismic-gmpe-ipe-v1", "algorithm": "physics_ipe_omori", "lifecycle": "active", "active": True, "tier": "screening",
         "claim": "Screening signal only: no euro figure is published on this model.", "use": "score", "r2_oos": None, "auc": None, "gate": 0.40,
         "fidelity": {"family_label": "Ranking Fidelity", "symbol": "RF", "value": 83.3, "band_label": "Strong", "published": True},
         "validation": {"level": "hazard", "kind": "discrimination", "method": "temporal_holdout", "skill_grade": "fair", "passed_gate": True, "at": "2026-08-28T00:00:00", "note": "hazard level"},
         "data": {"training_vintage": "2026-06-25", "training_cells": 9241, "feeds": [{"key": "geophysical", "name": "USGS", "status": "fresh", "last_refresh": None}]},
         "limitations": ["Physics-based; no fitted classifier."], "governance": {"approved_by": None, "approved_at": None, "activated_by": None, "activated_at": None, "registered_at": "2026-06-27", "events": [{"from": None, "to": "candidate", "actor": "a", "reason": "registered", "at": "2026-06-27T00:00:00"}]},
         "controls": ["C-MOD-01"], "review": None, "review_state": "none"}
    c.update(kw); c["card_sha256"] = sha256({k: v for k, v in c.items() if k not in ("card_sha256", "review", "review_state")})
    return c


def test_card_hash_is_canonical_and_changes_with_content():
    a, b = _card(), _card()
    assert a["card_sha256"] == b["card_sha256"] and len(a["card_sha256"]) == 64
    assert _card(r2_oos=0.5)["card_sha256"] != a["card_sha256"]
    assert canonical_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_conclusions_are_fixed_and_explicit():
    assert set(CONCLUSIONS) == {"fit_for_use", "restricted_use", "not_fit"}


def test_csv_and_card_pdf_render():
    v = {"cards": [_card(), _card(ref="calibration:x:ES:drought", kind="impact", name="Olive oil · ES · drought", tier="ranged", r2_oos=0.51, active=True,
                                  validation={"kind": "regression", "method": "leave-one-out cross-validation on observed yield", "n_years": 31, "baseline": "1991–2020", "challenger": None})]}
    lines = register_csv(v).decode("utf-8").splitlines()
    assert len(lines) == 3 and lines[0].startswith("Ref,Kind,Hazard,Model")
    pdf = render_card_pdf(_card(), "Test Foods", [{"reviewed_at": "2026-09-09T20:00:00", "reviewer": "Ana", "conclusion_label": "Fit for use with restrictions (see comment)", "comment": "screening only", "next_review_by": "2027-03-31", "evidence_sha256": "abcd" * 16}])
    assert pdf[:5] == b"%PDF-" and len(pdf) > 2500
