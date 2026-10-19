"""Agriculture, the maps and the crop-statistics feeds speak in the catalogue's words (UI standard, 2026-10-16), and the
defects found on the way stay fixed: the maps band a score exactly as the platform does, a publisher's outage is the
publisher's side (E215) whichever way it shows, and every refusal these screens get is a catalogue code. No database."""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
import requests

from core import messages

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web" / "src"
MAPS = ("components/HexMap.tsx", "components/SiteMap.tsx", "pages/RiskMap.tsx")
ADAPTERS = ("nass_quickstats", "fas_psd", "faostat_crops", "eurostat_crops", "statcan_crops")


# ── the maps band a score as the platform does ──────────────────────────────────────────────────────────────────────

def test_the_web_bands_are_the_platforms_bands():
    """lib/bands.ts states each band's lower bound; they must be core/types._BUCKET_THRESHOLDS exactly — a map that
    called 55 'Medium' while every other screen said 'High' is what this stops."""
    from core.types import _BUCKET_THRESHOLDS
    web = re.findall(r"\{ key: '(\w+)', from: (\d+(?:\.\d+)?)", (WEB / "lib" / "bands.ts").read_text(encoding="utf-8"))
    assert [(k, float(f)) for k, f in web] == [(b.value, lo) for lo, _hi, b in _BUCKET_THRESHOLDS]
    named = re.search(r"BUCKET_LABEL[^{]*\{([^}]*)\}", (WEB / "lib" / "hazards.ts").read_text(encoding="utf-8")).group(1)
    assert {k for k, _ in web} <= set(re.findall(r"(\w+):", named)), "every band has its customer name"


@pytest.mark.parametrize("rel", MAPS)
def test_no_map_cuts_a_score_by_its_own_numbers(rel):
    """A map colours and names a score through lib/bands only: no comparison of a score with a number of its own."""
    text = (WEB / rel).read_text(encoding="utf-8")
    assert "lib/bands" in text
    own = re.findall(r"\b(?:s|l|score|hs|hazard_score)\s*[<>]=?\s*\d+", text)
    assert not own, f"{rel} cuts a score at its own thresholds: {own}"


# ── a publisher's outage is the publisher's side (E215), in customer words ──────────────────────────────────────────

class _Answer:
    def __init__(self, status: int):
        self.status_code, self.text, self.content, self.headers = status, "", b"", {}

    def json(self):
        return {}


def _call(mod):
    """One request of the adapter: its cheap check where it has one, else its fetch."""
    if mod.__name__.endswith("eurostat_crops"):
        return mod.fetch("https://x", {}, attempts=1)
    if mod.__name__.endswith("nass_quickstats"):
        return mod._count([("short_desc", "X")])
    if mod.__name__.endswith("fas_psd"):
        return mod._get("countries")
    return mod.published(None, None)


@pytest.fixture()
def keys(monkeypatch):
    from core.config import settings
    monkeypatch.setattr(settings, "NASS_API_KEY", "SECRET-KEY-123")
    monkeypatch.setattr(settings, "USDA_FAS_API_KEY", "SECRET-KEY-456")


@pytest.mark.parametrize("name", ADAPTERS)
@pytest.mark.parametrize("status,outage", [(502, True), (503, True), (504, True), (500, False), (404, False)])
def test_an_outage_answer_is_the_publishers_side(name, status, outage, keys, monkeypatch):
    """Before: each adapter turned a non-200 answer into its own error, so a 503 from USDA, FAOSTAT, Eurostat or
    Statistics Canada was recorded as a fault in our adapter (the E215 rule reads 502/503/504 as the provider's)."""
    import importlib

    from services.data.feeds import source_unreachable
    mod = importlib.import_module(f"services.reference.{name}")
    monkeypatch.setattr(requests, "get", lambda *a, **k: _Answer(status))      # the one module every adapter imports
    monkeypatch.setattr(requests, "head", lambda *a, **k: _Answer(status))
    with pytest.raises(mod.FetchError) as e:
        _call(mod)
    assert source_unreachable(e.value) is outage
    assert e.value.code == ("agri.feed.unavailable" if outage else "agri.feed.refused")
    assert str(e.value) == messages.label(e.value.code, **e.value.params)          # the feed note reads words


@pytest.mark.parametrize("name", ADAPTERS)
def test_a_dropped_connection_is_the_publishers_side_and_never_shows_a_key(name, keys, monkeypatch):
    """NASS rebuilt its error without the chain (the URL carries its key) and so lost the outage with it."""
    import importlib

    from services.data.feeds import source_unreachable
    mod = importlib.import_module(f"services.reference.{name}")

    def boom(url, params=None, **kw):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}?key=SECRET-KEY-123")
    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(requests, "head", boom)
    with pytest.raises(mod.FetchError) as e:
        _call(mod)
    assert source_unreachable(e.value) and e.value.code == "agri.feed.unreachable"
    assert "SECRET-KEY" not in str(e.value) and "SECRET-KEY" not in repr(e.value.params)


def test_a_missing_key_names_the_publisher_not_the_setting(monkeypatch):
    from core.config import settings
    from services.data.feeds import source_unreachable
    from services.reference import fas_psd, nass_quickstats
    monkeypatch.setattr(settings, "NASS_API_KEY", None)
    monkeypatch.setattr(settings, "USDA_FAS_API_KEY", None)
    for call in (lambda: nass_quickstats._count([]), lambda: fas_psd._get("countries")):
        with pytest.raises(RuntimeError) as e:
            call()
        assert e.value.code == "agri.feed.no_key" and not source_unreachable(e.value)
        assert not messages.INTERNAL.search(str(e.value))


@pytest.mark.parametrize("name", ADAPTERS + ("eurostat_regional", "nass_county"))
def test_every_adapter_error_is_a_catalogue_code(name):
    """An adapter raises its FetchError with a code of the catalogue (or through the publisher helpers) — never a
    sentence of its own, which a failed refresh's note would show as it is."""
    tree = ast.parse((ROOT / "services" / "reference" / f"{name}.py").read_text(encoding="utf-8"))
    for n in ast.walk(tree):
        if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call):
            f = n.exc.func
            fname = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if fname == "FetchError":
                code = n.exc.args[0]
                assert isinstance(code, ast.Constant) and code.value in messages.catalogue(), \
                    f"{name}.py:{n.lineno} raises FetchError with words, not a catalogue code"
            else:
                assert fname in ("unreachable", "answered", "no_key"), f"{name}.py:{n.lineno} raises {fname}"


# ── the screens' explanations are catalogue messages ────────────────────────────────────────────────────────────────

def test_supply_concentration_flags_and_method_are_messages_naming_the_hazard():
    """The concentration card printed 'Peril concentration: 68.7% of spend exposed to drought' and its method as a
    paragraph in the code font; each is now a catalogue message, the hazard by its name."""
    from services.intelligence.supply_concentration import supply_concentration
    book = [{"commodity": c, "annual_spend_eur": v, "top_hazard": h, "status": "held"}
            for c, v, h in (("Citrus", 70.0, "soil_water"), ("Cocoa", 20.0, "soil_water"), ("Olive oil", 10.0, "drought"))]
    out = supply_concentration(book)
    assert {f["code"] for f in out["flags"]} == {"agri.concentration.crop", "agri.concentration.peril",
                                                  "agri.concentration.diversification"}
    peril = next(f for f in out["flags"] if f["code"] == "agri.concentration.peril")
    assert peril["params"]["hazard"] == messages.name("hazard", "soil_water")
    assert out["method"]["code"] == "agri.concentration.method"
    for m in [*out["flags"], out["method"]]:
        assert not messages.INTERNAL.search(" ".join([m["label"], *m["detail"].values()]))
    assert supply_concentration([])["reason"]["code"] == "agri.concentration.no_spend"


def test_a_calibration_refusal_carries_its_code_to_the_approvals_screen():
    """The approvals path passes a refusal's own words on when it carries a catalogue code (admin.approvals
    .not_applied); a calibration batch's refusals were plain sentences with a table name in them."""
    from api.routers.approvals import _not_applied
    from services.calibration.publish import PublishError
    e = PublishError("agri.calibration.not_modelled", commodity="Quinoa")
    assert str(e) == "Quinoa is not a modelled commodity"
    assert _not_applied(e).params["reason"] == "Quinoa is not a modelled commodity"
    tree = ast.parse((ROOT / "services" / "calibration" / "publish.py").read_text(encoding="utf-8"))
    raised = [n.exc.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
              and getattr(n.exc.func, "id", "") == "PublishError"]
    assert raised and all(c in messages.catalogue() for c in raised)


def test_the_irrigation_and_downtime_explanations_come_from_the_catalogue():
    from api.routers.supply import irrigation_context
    wet = irrigation_context("irrigated", ["drought"])
    assert wet["message"]["code"] == "agri.plot.irrigated" and wet["note"].startswith(wet["message"]["detail"]["what"])
    assert irrigation_context("rain_fed", ["soil_water"])["message"]["code"] == "agri.plot.rain_fed"
    assert irrigation_context("irrigated", []) == {"status": "irrigated", "buffers": []}


def test_every_agri_code_is_sound():
    codes = [c for c in messages.catalogue() if c.startswith(("agri.location", "agri.site", "agri.plot", "agri.map",
                                                              "agri.concentration", "agri.calibration", "agri.feed"))]
    assert len(codes) >= 30
    assert not [p for p in messages.check() if p.split(":")[0] in codes]
