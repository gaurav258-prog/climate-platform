"""The Coverage page's server text, to the UI standard (2026-10-16): the three views (/v1/meta/hazard-coverage,
/projection-coverage, /model-limitations) serve the message catalogue's words only, never the registries' engineers'
notes, and every number those words state is in the registries' record — a fact moved out of sight, never a new one."""
from __future__ import annotations

import re

import pytest

from core import messages
from core import validation_gates as G
from core.hazard_regions import CAVEATS, POOLED_GLOBAL, REGIONAL_EVIDENCE
from core.hazard_taxonomy import CALIBRATED_VALIDATION, EU_TAXONOMY, EXTRA_CHANNELS, MaturityTier
from ml.scoring.model_limitations import model_limitations
from ml.scoring.physical_projection import SENSITIVITY
from ml.scoring.projection_coverage import projection_coverage
from services.intelligence.coverage import (
    _MODE_CODE,
    MODE_ORDER,
    eu_taxonomy_coverage,
    limitations_view,
    projection_view,
)

HAZARDS = (*EU_TAXONOMY, *EXTRA_CHANNELS)
VIEWS = {"hazards": eu_taxonomy_coverage, "projections": projection_view, "limitations": limitations_view}
WORDS = {"label", "name", "area", "what", "why", "next"}                  # the keys whose values a screen reads
NOTES = {"internal_note", "source", "evidence", "ledger", "caveat", "pooled_note", "mechanism", "basis", "gaps",
         "mode_label", "summary", "current_treatment", "unlock", "note", "status_label", "version",
         "projection_engine_version", "params", "code"}                  # the engineers' record and plumbing


def _walk(x, key=None):
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _walk(v, k)
            yield k, None
    elif isinstance(x, list):
        for v in x:
            yield from _walk(v, key)
    else:
        yield key, x


@pytest.mark.parametrize("view", VIEWS)
def test_the_screen_gets_customer_words_and_no_engineers_note(view):
    served = VIEWS[view]()
    keys = {k for k, _ in _walk(served)}
    assert not keys & NOTES, f"{view} sends {sorted(keys & NOTES)}"
    bad = [s for k, s in _walk(served) if k in WORDS and isinstance(s, str) and messages.INTERNAL.search(s)]
    assert bad == [], bad


# ── every number the words state is in the record ─────────────────────────────────────────────────────────────
_NUM = re.compile(r"(?<!\w)(?<!\d[.,])[−-]?\d+(?:[.,]\d+)*k?")


def numbers(text: str) -> set[str]:
    """The numbers a text states, normalised: 1,864 → 1864, 41k → 41000, −0.17 → -0.17, 2022–24 → also 2024."""
    out = set()
    for m in _NUM.finditer(text):
        t = m.group().replace("−", "-")
        k = t.endswith("k")
        t = t.rstrip("k")
        if t.count(".") > 1:                                  # a section number: 11.7.3.5
            out.add(t)
            continue
        t = t.replace(",", "")
        out.add(f"{float(t) * (1000 if k else 1):g}")
    for m in re.finditer(r"\b(\d{2})(\d{2})[–-](\d{2})\b", text):
        out.add(m.group(1) + m.group(3))
    return out


def _template(code: str) -> str:
    """A catalogue message's words without their {placeholders} — those are filled from the code's own constants."""
    m = messages.catalogue()[code]
    return re.sub(r"\{[a-z_]+\}", "", " ".join([m["label"], *m["detail"].values()]))


def _hazard_record(hid: str) -> str:
    h = next(h for h in HAZARDS if h.id == hid)
    parts = [h.internal_note, (CALIBRATED_VALIDATION.get(hid) or {}).get("target", ""), CAVEATS.get(hid, ""),
             POOLED_GLOBAL.get(hid, "")]
    parts += [f"{e.ledger} {e.evidence}" for e in REGIONAL_EVIDENCE.get(hid, ())]
    return " ".join(parts)


def test_every_number_in_a_hazards_words_is_in_its_record():
    bad = {}
    for h in HAZARDS:
        record = numbers(_hazard_record(h.id))
        codes = [f"coverage.hazard.{h.id}", *(f"coverage.region.{h.id}.{e.region}" for e in REGIONAL_EVIDENCE.get(h.id, ()))]
        for code in codes:
            if extra := numbers(_template(code)) - record:
                bad[code] = sorted(extra)
    assert bad == {}, bad


def test_every_number_in_a_projections_words_is_in_its_record():
    bad = {}
    for it in projection_coverage()["items"]:
        record = numbers(" ".join([it["mechanism"], it["basis"], *it["gaps"], it["mode_label"]]))
        if extra := numbers(_template(f"coverage.projection.{it['hazard']}")) - record:
            bad[it["hazard"]] = sorted(extra)
    assert bad == {}, bad


def test_every_number_in_a_limitations_words_is_in_its_record():
    bad = {}
    for it in model_limitations()["items"]:
        record = numbers(" ".join(str(it[k]) for k in ("title", "summary", "evidence", "current_treatment", "unlock")))
        for code in (f"coverage.limitation.{it['id']}", f"coverage.limitation.{it['id']}.today"):
            if extra := numbers(_template(code)) - record:
                bad[code] = sorted(extra)
    assert bad == {}, bad


def test_the_general_words_state_no_number_of_their_own():
    """Tiers, scope claims, modes and statuses quote the gates only through placeholders filled from core.validation_gates."""
    general = [c for c in messages.catalogue() if c.split(".")[1] in ("tier", "indicator", "scope", "mode", "status")
               and c.startswith("coverage.")]
    assert general and all(numbers(_template(c)) == set() for c in general)
    glob = next(h for f in eu_taxonomy_coverage()["families"] for h in f["hazards"]
                if "scope" in h and h["scope"]["claim"] == "global")
    assert str(G.GLOBAL_CLAIM_MIN_REGIONS) in glob["scope"]["message"]["detail"]["what"]


def test_the_bar_is_the_gate():
    wildfire = next(h for h in EU_TAXONOMY if h.id == "wildfire")
    assert wildfire.tier is MaturityTier.CALIBRATED
    words = next(h for f in eu_taxonomy_coverage()["families"] for h in f["hazards"] if h["id"] == "wildfire")
    assert f"{G.RANK_GATE_SPEARMAN:.2f} bar" in words["message"]["detail"]["why"]


def test_projected_rates_come_from_the_engine():
    flood = next(i for i in projection_view()["items"] if i["channel"] == "flood")
    assert f"{SENSITIVITY['flood'].per_c * 100:.0f}%" in flood["message"]["label"]


# ── one set of words per registry row, and no words left over ──────────────────────────────────────────────────
def _codes(prefix: str) -> set[str]:
    return {c[len(prefix):] for c in messages.catalogue() if c.startswith(prefix)}


def test_every_registry_row_has_its_words_and_none_are_left_over():
    ids = {h.id for h in HAZARDS}
    assert _codes("coverage.hazard.") == ids
    assert set(messages.names()["coverage.hazard"]) == ids
    assert _codes("coverage.region.") == {f"{h}.{e.region}" for h, ev in REGIONAL_EVIDENCE.items() for e in ev}
    channels = {it["hazard"] for it in projection_coverage()["items"]}
    assert _codes("coverage.projection.") == channels | {"none"}
    assert set(messages.names()["coverage.channel"]) == channels | {c.value for h in HAZARDS for c in h.internal}
    modes = {it["mode"] for it in projection_coverage()["items"]}
    assert modes <= set(MODE_ORDER)
    assert _codes("coverage.mode.") == {_MODE_CODE.get(m, m) for m in MODE_ORDER}
    lims = {it["id"] for it in model_limitations()["items"]}
    assert _codes("coverage.limitation.") == lims | {f"{i}.today" for i in lims}
    assert set(messages.names()["coverage.area"]) == lims


def test_where_a_hazard_is_validated_is_stated_once():
    """The scope of a validated hazard is derived from core/hazard_regions.py; a hazard's note that restates it goes
    stale (the wildfire note still said 'elsewhere a screening indicator' after the derived claim became global)."""
    region = r"(?:Europe|North America|Latin America|Africa|Asia|Oceania)"
    scope = re.compile(rf"\belsewhere\b|\b(?:in|outside) {region}\b[^.;]*\bonly\b", re.I)
    stated = [h.id for h in EU_TAXONOMY if h.tier is MaturityTier.CALIBRATED and scope.search(h.internal_note)]
    assert stated == []


def test_a_projection_gap_names_only_open_limitations():
    """The coastal-flood gap still read 'v1 = global-mean' after sea level v2 applied the ocean term: a gap that defers
    to the limitations registry names its rows, and those rows must still be open."""
    open_ = {it["id"] for it in model_limitations()["items"]}
    named = {n.strip() for it in projection_coverage()["items"] for g in it["gaps"]
             for m in re.finditer(r"model_limitations: ([a-z_, ]+)", g) for n in m.group(1).split(",")}
    assert named and named <= open_
