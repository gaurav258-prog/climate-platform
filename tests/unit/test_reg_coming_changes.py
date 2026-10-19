"""The curated register of coming changes (data/reference/crcs/coming_changes.json) is read by the Regulatory outlook:
its 'Need data from you' figure counts the changes that ask the customer to prepare data. A change that asks you to
prepare lists the fields it asks for — a 'no action yet' note is a data-to-be-confirmed note, never a request (the
CSRD Omnibus entry once sat under 'prepare' and was counted as a data request)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

REGISTER = Path(__file__).resolve().parents[2] / "data" / "reference" / "crcs" / "coming_changes.json"
CHANGES = json.loads(REGISTER.read_text(encoding="utf-8"))["changes"]


def test_a_change_that_asks_you_to_prepare_lists_the_fields():
    for c in CHANGES:
        if c.get("prepare"):
            assert c.get("data_fields"), f"{c['title']}: 'prepare' without the fields it asks for"
        for f in c.get("data_fields") or []:
            assert f.get("field") and f.get("key"), f"{c['title']}: a field needs its words and its key"


def test_dates_are_exact_or_absent():
    for c in CHANGES:
        if c.get("date") is not None:
            date.fromisoformat(c["date"])        # a fixed date from the cited text, never a guess
        assert c.get("sectors") and c.get("title") and c.get("citation"), c.get("title")
