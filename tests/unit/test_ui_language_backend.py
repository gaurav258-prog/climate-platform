"""The UI standard's guard on the server (2026-10-16): no file sends a screen more internal language than the baseline
recorded when the standard came in — and the baseline only goes down (scripts/ui_language.py)."""
from __future__ import annotations

import json

from scripts import ui_language as U

BASE = json.loads(U.BASELINE.read_text(encoding="utf-8"))


def test_no_file_sends_more_internal_language_than_its_baseline():
    worse = []
    for p in U.sources():
        rel = str(p.relative_to(U.ROOT))
        got, b = U.scan(p), BASE.get(rel, {})
        worse += [f"{rel}: {k} {b.get(k, 0)} → {got[k]}" for k in got if got[k] > b.get(k, 0)]
    assert worse == [], ("Say it in customer words, or move the internal detail out of what the screen shows: "
                         f"{worse}")


def test_a_fixed_file_lowers_the_baseline():
    stale = []
    for rel, b in BASE.items():
        p = U.ROOT / rel
        got = U.scan(p) if p.exists() else dict.fromkeys(U.KINDS, 0)
        stale += [f"{rel}: {k} {b[k]} → {got.get(k, 0)}" for k in b if got.get(k, 0) < b[k]]
    assert stale == [], f"Lower the baseline: venv/bin/python -m scripts.ui_language --write — {stale}"


def test_a_user_error_names_a_catalogue_code(tmp_path):
    # a UserError's argument is a code, not words — counted only when the catalogue lacks it (a typo would 500)
    f = tmp_path / "r.py"
    f.write_text('def a():\n    raise UserError("supervision.intake.no_spec")\n'
                 'def b():\n    raise UserError("supervision.intake.no_such_code")\n'
                 'def c():\n    raise ValueError("bad at_risk_level")\n', encoding="utf-8")
    assert U.scan(f)["error"] == 2


def test_the_message_catalogue_is_sound():
    from core import messages
    assert messages.check() == []
