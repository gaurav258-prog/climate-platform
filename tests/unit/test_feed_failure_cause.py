"""E215: a failed feed refresh is put down to the provider only when the error says so — the provider could not be
reached, answered 502/503/504, or the adapter said so after its retries — and never when our adapter is at fault."""
import urllib.error

import pytest
import requests

from services.data.feeds import OUTAGE_STATUS, SourceUnreachable, source_unreachable
from services.reference.imf_fx import ImfFxError, ImfFxUnavailable


def _http(code: int) -> requests.HTTPError:
    r = requests.Response()
    r.status_code = code
    return requests.HTTPError(f"{code} Server Error", response=r)


@pytest.mark.parametrize("code", sorted(OUTAGE_STATUS))
def test_a_gateway_or_service_outage_is_the_providers_side(code):
    assert source_unreachable(_http(code))
    assert source_unreachable(urllib.error.HTTPError("https://x", code, "outage", {}, None))


@pytest.mark.parametrize("code", [400, 401, 403, 404, 429, 500])
def test_any_other_status_may_be_our_request(code):
    assert not source_unreachable(_http(code))
    assert not source_unreachable(urllib.error.HTTPError("https://x", code, "no", {}, None))


def test_no_connection_is_the_providers_side():
    for e in (requests.ConnectionError("refused"), requests.Timeout("slow"), ConnectionResetError(54, "reset"),
              TimeoutError(), urllib.error.URLError("no route"), SourceUnreachable("after 4 attempts")):
        assert source_unreachable(e), e


def test_an_adapters_wrapped_error_is_read_through_its_cause():
    try:
        try:
            raise _http(502)
        except requests.HTTPError as inner:
            raise RuntimeError("Copernicus refused the request") from inner
    except RuntimeError as e:
        assert source_unreachable(e)
    try:
        try:
            raise requests.ConnectionError("https://api?key=secret")
        except requests.RequestException:
            raise RuntimeError("USDA NASS could not be reached (ConnectionError)") from None   # replaced, not chained
    except RuntimeError as e:
        assert source_unreachable(e)


def test_a_fault_while_handling_an_outage_stays_ours():
    try:
        try:
            raise requests.ConnectionError("refused")
        except requests.ConnectionError:
            {}["missing"]                                    # a bug in the handler, not the outage
    except KeyError as e:
        assert not source_unreachable(e)


def test_our_own_faults_stay_ours():
    for e in (KeyError("value"), ValueError("not a number"), RuntimeError("FIRMS 503"), AttributeError("get")):
        assert not source_unreachable(e), e


def test_the_imf_gateway_refusing_every_retry_is_an_outage_and_still_an_imf_error():
    e = ImfFxUnavailable("upstream unavailable: api.imf.org refused 5 attempts")
    assert isinstance(e, ImfFxError) and source_unreachable(e)
    assert not source_unreachable(ImfFxError("the IMF returned no usable rates"))
