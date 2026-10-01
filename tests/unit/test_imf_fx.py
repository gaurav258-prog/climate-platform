"""IMF monthly rates (services/reference/imf_fx.py): guards against wrong rates."""
from __future__ import annotations

from datetime import date

from services.reference.imf_fx import parse

HDR = "COUNTRY,INDICATOR,TYPE_OF_TRANSFORMATION,FREQUENCY,TIME_PERIOD,OBS_VALUE\n"


def _csv(rows):
    return (HDR + "".join(",".join(r) + "\n" for r in rows)).encode()


CC = {"GHA": ("GHS", date(2007, 7, 3)), "USA": ("USD", date(1792, 1, 1)), "HTI": ("HTG", None), "ECU": ("USD", date(2000, 9, 10)),
      "DEU": ("EUR", date(1999, 1, 1))}
ISO2 = {"GHA": "GH", "USA": "US", "HTI": "HT", "ECU": "EC", "DEU": "DE"}


def test_month_end_and_average_are_kept_apart_and_dated_month_end():
    out = parse(_csv([("GHA", "XDC_EUR", "EOP_RT", "M", "2026-M01", "13.05"), ("GHA", "XDC_EUR", "PA_RT", "M", "2026-M01", "12.9")]),
                CC, today=date(2026, 9, 26), iso2_of=ISO2)
    assert sorted((r[1], r[2], r[3]) for r in out["rows"]) == [(date(2026, 1, 31), "month_end", 13.05), (date(2026, 1, 31), "period_average", 12.9)]


def test_future_and_pre_currency_periods_are_refused():
    out = parse(_csv([("GHA", "XDC_EUR", "EOP_RT", "M", "2027-M03", "13"), ("GHA", "XDC_EUR", "EOP_RT", "M", "2006-M12", "1300"),
                      ("DEU", "XDC_EUR", "EOP_RT", "M", "2026-M01", "1")]), CC, today=date(2026, 9, 26), iso2_of=ISO2)
    assert out["rows"] == [] and out["refused"] == {"period in the future": 1, "before the country's current currency began": 1}


def test_a_shared_currency_comes_from_its_home_country():
    out = parse(_csv([("ECU", "XDC_EUR", "EOP_RT", "M", "2026-M08", "1.14"), ("USA", "XDC_EUR", "EOP_RT", "M", "2026-M07", "1.15")]),
                CC, today=date(2026, 9, 26), iso2_of=ISO2)
    assert {r[4] for r in out["rows"] if r[0] == "USD"} == {"USA"}      # US, even though Ecuador's data is newer


def test_a_transient_refusal_is_retried_and_a_wrong_request_is_not():
    """The IMF gateway answers some anonymous calls with 401/429/5xx and the same call then succeeds: retried with
    backoff. A 404 (a wrong URL or query — ours) fails at once; a provider that keeps refusing is named as upstream."""
    import io
    import urllib.error
    from unittest.mock import patch

    import pytest

    from services.reference import imf_fx

    class _Ok(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def err(code):
        return urllib.error.HTTPError(imf_fx.API, code, "x", {}, None)

    waits = []
    with patch("urllib.request.urlopen", side_effect=[err(401), err(503), _Ok(b"data")]):
        assert imf_fx._get("2025-01", sleep=waits.append) == b"data"
    assert waits == [1, 2]
    with patch("urllib.request.urlopen", side_effect=[err(404)]):
        with pytest.raises(urllib.error.HTTPError):
            imf_fx._get("2025-01", sleep=waits.append)
    with patch("urllib.request.urlopen", side_effect=[err(401)] * imf_fx._ATTEMPTS):
        with pytest.raises(imf_fx.ImfFxError, match="upstream unavailable"):
            imf_fx._get("2025-01", sleep=lambda s: None)
