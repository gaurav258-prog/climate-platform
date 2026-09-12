"""Which hazard scales may set an asset's headline risk — the one definition behind every "at risk" figure.

A hazard score is a number on a scale, and a scale is built for something. Only a scale that expresses the
likelihood or intensity of damaging conditions at the location may set an asset's headline (the bucket behind
"share at risk", the Pillar 3 sensitivity test, the supervisor's lens and priors, the third-party register).
Three kinds of scale in the engine are NOT that, and are shown as context but never headline:

  • crop scales — frost (coffee thresholds 4 / −2 °C: every temperate city scores 100), root-zone water stress,
    land degradation, soil erosion, ocean acidification: a standing risk for agriculture, not for a building;
  • susceptibility classes — subsidence, landslide, permafrost, avalanche, solifluction, glacial-lake outburst:
    a geophysical predisposition class mapped to 0–100, not a probability of settlement or failure;
  • variability percentiles — temperature/precipitation variability and the "changing" indicators: a rank of
    the location among all land, by construction spreading the world across 0–100.

Plus nowcast signals (today's live reading), which are never a standing headline. The registry is mirrored into
the `hazard_relevance` table for the SQL paths (synced at API start and by the migration); a unit test keeps
the two identical. Nothing filters a hazard by name anywhere else.

A scale belongs to a MODEL, not to a hazard id: the same hazard can be a susceptibility class under one model
version and a measured intensity under another (subsidence: the Herrera class vs the observed EGMS rate). So the
registry also carries per-model-version overrides (`SCALE_BY_MODEL`, matched by version prefix) and every
eligibility question can be asked for a specific row's model version. The SQL side asks the same question through
`hazard_headline_eligible(hazard_type, asset_class, model_version)` (migration relevance_model_version_20260912),
which the physical-risk view and the supervisor analytics use — one definition on both sides.
"""
from __future__ import annotations

from core.types import HAZARD_VALUES

BUILDINGS, AGRICULTURE = "buildings", "agriculture"
ASSET_CLASSES = (BUILDINGS, AGRICULTURE)

# scale kinds
INTENSITY, CROP, SUSCEPTIBILITY, VARIABILITY, NOWCAST_KIND = "intensity", "crop", "susceptibility", "variability", "nowcast"

SCALE: dict[str, tuple[str, str]] = {
    # intensity / likelihood scales — may headline the asset class they apply to
    "flood": (INTENSITY, "inundation likelihood (multi-event ensemble)"),
    "coastal_flood": (INTENSITY, "freeboard of the site against the observed 1-in-10-year extreme still-water level at the nearest tide gauge (GESLA-3), plus sea-level rise; sites with no gauge in range are not scored"),
    "wildfire": (INTENSITY, "fire-weather climatology × burnable fraction × burn history (EFFIS-validated)"),
    "drought": (INTENSITY, "SPEI seasonal climatology (meteorological drought severity)"),
    "storm": (INTENSITY, "tropical-cyclone wind field (IBTrACS Rankine vortex)"),
    "windstorm": (INTENSITY, "extratropical gust climatology"),
    "seismic": (INTENSITY, "ground-motion intensity (GMPE / IPE)"),
    "volcanic": (INTENSITY, "eruption proximity and ashfall (GVP)"),
    "heat_chronic": (INTENSITY, "chronic heat exposure trend"),
    "heavy_precip": (INTENSITY, "extreme-rainfall climatology"),
    "pollution": (INTENSITY, "air-quality exceedance of WHO guideline"),
    "saline_intrusion": (SUSCEPTIBILITY, "low-elevation-coastal-zone susceptibility × sea-level amplifier: a disclosed proxy, not an aquifer-salinity measurement"),
    "coastal_erosion": (INTENSITY, "shoreline retreat exposure"),
    "cold_wave": (INTENSITY, "1-in-10 coldest night against building thresholds (pipe-freeze onset −6.7 °C) and the location's own 99.6 % design temperature"),
    "severe_convective": (INTENSITY, "annual probability of a damaging severe-convective event, anchored on NOAA SPC reports (held-out AUC 0.82, ρ 0.51)"),
    # crop scales
    "frost": (CROP, "crop-frost scale (coffee thresholds 4 / −2 °C): total damage at −2 °C is right for a coffee origin, not for a building"),
    "soil_water": (CROP, "root-zone soil-moisture stress: a crop-yield driver, not a building hazard"),
    "soil_degradation": (CROP, "UNCCD land-degradation index: land productivity, not the built environment"),
    "soil_erosion": (CROP, "GloSEM soil displacement (t ha⁻¹ yr⁻¹): agronomic tolerance scale"),
    "ocean_acidification": (CROP, "marine chemistry: aquaculture and fisheries, not buildings"),
    # susceptibility classes
    "subsidence": (SUSCEPTIBILITY, "Herrera-García global subsidence susceptibility class: a predisposition class, not a settlement probability"),
    "landslide": (SUSCEPTIBILITY, "NASA LHASA landslide susceptibility class: terrain predisposition, not a rainfall-triggered event likelihood"),
    "permafrost": (SUSCEPTIBILITY, "permafrost probability (Obu 2019): thaw-exposure state"),
    "avalanche": (SUSCEPTIBILITY, "terrain-derived avalanche susceptibility"),
    "solifluction": (SUSCEPTIBILITY, "periglacial susceptibility derived from permafrost probability × slope"),
    "glacial_lake_outburst": (SUSCEPTIBILITY, "proximity to glacial lakes: exposure state, not an outburst likelihood"),
    # variability percentiles
    "temp_variability": (VARIABILITY, "percentile of seasonal temperature amplitude among all land"),
    "precip_variability": (VARIABILITY, "percentile of interannual precipitation spread among all land"),
    "changing_temp": (VARIABILITY, "percentile of warming trend among all land"),
    "changing_precip": (VARIABILITY, "percentile of precipitation trend among all land"),
    "changing_wind": (VARIABILITY, "percentile of wind-regime change among all land"),
    # nowcast
    "heat_acute": (NOWCAST_KIND, "today's live temperature reading: a signal of the moment, never a standing headline"),
}

# model-version overrides: {hazard: {model_version_prefix: (kind, note)}} — a model that changed what the scale
# expresses. Matched by prefix so a patch version inherits its scale.
SCALE_BY_MODEL: dict[str, dict[str, tuple[str, str]]] = {
    "subsidence": {"subsidence-egms-observed": (INTENSITY, "observed InSAR subsidence rate at the cell (Copernicus EGMS), held out in time (ρ 0.85): a measured intensity")},
}

_HEADLINE_KINDS = {BUILDINGS: {INTENSITY}, AGRICULTURE: {INTENSITY, CROP}}


def _scale(hazard: str, model_version: str | None = None) -> tuple[str, str]:
    if model_version:
        for prefix, kind_note in SCALE_BY_MODEL.get(hazard, {}).items():
            if model_version.startswith(prefix):
                return kind_note
    return SCALE.get(hazard, (INTENSITY, ""))


def scale_kind(hazard: str, model_version: str | None = None) -> str:
    return _scale(hazard, model_version)[0]


def relevance(hazard: str, model_version: str | None = None) -> dict[str, bool]:
    """{buildings: bool, agriculture: bool} — may this hazard's scale (under this model version) set the headline?"""
    k = scale_kind(hazard, model_version)
    return {ac: k in kinds for ac, kinds in _HEADLINE_KINDS.items()}


def reason(hazard: str, asset_class: str = BUILDINGS, model_version: str | None = None) -> str | None:
    """Why the hazard cannot headline this asset class (None when it can)."""
    if relevance(hazard, model_version)[asset_class]:
        return None
    k, note = _scale(hazard, model_version)
    label = {CROP: "crop scale", SUSCEPTIBILITY: "susceptibility class", VARIABILITY: "variability percentile", NOWCAST_KIND: "nowcast"}[k]
    return f"{label} — {note}"


def registry() -> list[dict]:
    """Every hazard × asset class (model_version_prefix '' = the hazard's default scale) plus the per-model overrides —
    what the `hazard_relevance` table mirrors."""
    rows = [{"hazard_type": hz, "asset_class": ac, "model_version_prefix": "", "headline": relevance(hz)[ac],
             "scale_kind": scale_kind(hz), "note": reason(hz, ac)} for hz in HAZARD_VALUES for ac in ASSET_CLASSES]
    for hz, by_prefix in SCALE_BY_MODEL.items():
        for prefix in by_prefix:
            rows += [{"hazard_type": hz, "asset_class": ac, "model_version_prefix": prefix, "headline": relevance(hz, prefix)[ac],
                      "scale_kind": scale_kind(hz, prefix), "note": reason(hz, ac, prefix)} for ac in ASSET_CLASSES]
    return rows


def headline_exclude(asset_class: str = BUILDINGS) -> tuple[str, ...]:
    """The hazards whose DEFAULT scale never headlines this asset class. A row-level decision must use
    `is_headline_eligible(hazard, asset_class, model_version)`: a hazard listed here can still headline under an
    overriding model version (subsidence under the observed EGMS model)."""
    return tuple(hz for hz in HAZARD_VALUES if not relevance(hz)[asset_class])


def is_headline_eligible(hazard: str, asset_class: str = BUILDINGS, model_version: str | None = None) -> bool:
    return relevance(hazard, model_version).get(asset_class, False)


def sync_table(session) -> int:
    """Mirror the registry into hazard_relevance (idempotent). Called at API start and by the migration."""
    from sqlalchemy import text
    session.execute(text("""CREATE TABLE IF NOT EXISTS hazard_relevance (hazard_type TEXT NOT NULL, asset_class TEXT NOT NULL,
                            model_version_prefix TEXT NOT NULL DEFAULT '', headline BOOLEAN NOT NULL, scale_kind TEXT, note TEXT,
                            PRIMARY KEY (hazard_type, asset_class, model_version_prefix))"""))
    session.execute(text("ALTER TABLE hazard_relevance ADD COLUMN IF NOT EXISTS scale_kind TEXT"))
    session.execute(text("ALTER TABLE hazard_relevance ADD COLUMN IF NOT EXISTS model_version_prefix TEXT NOT NULL DEFAULT ''"))
    n = 0
    for r in registry():
        session.execute(text("""INSERT INTO hazard_relevance (hazard_type, asset_class, model_version_prefix, headline, scale_kind, note)
                                VALUES (:h, :a, :p, :e, :k, :n)
                                ON CONFLICT (hazard_type, asset_class, model_version_prefix)
                                DO UPDATE SET headline = EXCLUDED.headline, scale_kind = EXCLUDED.scale_kind, note = EXCLUDED.note"""),
                        {"h": r["hazard_type"], "a": r["asset_class"], "p": r["model_version_prefix"], "e": r["headline"], "k": r["scale_kind"], "n": r["note"]})
        n += 1
    return n
