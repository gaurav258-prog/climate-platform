"""ECB reference-rate feed (services/reference/ecb_fx.py): parsing both ECB formats, and stale data failing loudly."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from services.reference import ecb_fx

CSV = b"Date,USD,JPY,CYP,\n2026-09-25,1.1403,179.7,N/A,\n2026-09-24,1.1367,180.57,N/A,\n"
XML = (b'<?xml version="1.0" encoding="UTF-8"?><gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01" '
       b'xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref"><Cube><Cube time="2026-09-25">'
       b'<Cube currency="USD" rate="1.1403"/><Cube currency="GBP" rate="0.86045"/></Cube></Cube></gesmes:Envelope>')


def test_parse_hist_csv_skips_unquoted_currencies():
    rows = list(ecb_fx.parse_hist_csv(CSV))
    assert ("2026-09-25", "USD", 1.1403) in rows and ("2026-09-24", "JPY", 180.57) in rows
    assert not any(c == "CYP" for _, c, _ in rows) and len(rows) == 4


def test_parse_xml():
    assert list(ecb_fx.parse_xml(XML)) == [("2026-09-25", "USD", 1.1403), ("2026-09-25", "GBP", 0.86045)]


class _S:
    def commit(self):
        pass


def test_stale_ecb_data_fails_instead_of_counting_as_fresh(monkeypatch):
    old = date.today() - timedelta(days=12)
    monkeypatch.setattr(ecb_fx, "_get", lambda url: XML)
    monkeypatch.setattr(ecb_fx, "upsert", lambda s, rows: {"n_rows": 2})
    monkeypatch.setattr(ecb_fx, "latest_ecb_date", lambda s: old)
    with pytest.raises(ecb_fx.EcbFxError, match="12 days old"):
        ecb_fx.refresh(_S())


def test_fresh_ecb_data_passes(monkeypatch):
    monkeypatch.setattr(ecb_fx, "_get", lambda url: XML)
    monkeypatch.setattr(ecb_fx, "upsert", lambda s, rows: {"n_rows": 2})
    monkeypatch.setattr(ecb_fx, "latest_ecb_date", lambda s: date.today() - timedelta(days=1))
    assert ecb_fx.refresh(_S())["age_days"] == 1
