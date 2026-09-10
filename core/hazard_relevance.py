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
    "coastal_flood": (SUSCEPTIBILITY, "low elevation × distance to coast × sea-level rise: an exposure state until a local surge return level (tide gauges) anchors it to a flooding likelihood"),
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

_HEADLINE_KINDS = {BUILDINGS: {INTENSITY}, AGRICULTURE: {INTENSITY, CROP}}


def scale_kind(hazard: str) -> str:
    return SCALE.get(hazard, (INTENSITY, ""))[0]


def relevance(hazard: str) -> dict[str, bool]:
    """{buildings: bool, agriculture: bool} — may this hazard's scale set the headline for the asset class?"""
    k = scale_kind(hazard)
    return {ac: k in kinds for ac, kinds in _HEADLINE_KINDS.items()}


def reason(hazard: str, asset_class: str = BUILDINGS) -> str | None:
    """Why the hazard cannot headline this asset class (None when it can)."""
    if relevance(hazard)[asset_class]:
        return None
    k, note = SCALE.get(hazard, (INTENSITY, ""))
    label = {CROP: "crop scale", SUSCEPTIBILITY: "susceptibility class", VARIABILITY: "variability percentile", NOWCAST_KIND: "nowcast"}[k]
    return f"{label} — {note}"


def registry() -> list[dict]:
    """Every hazard × asset class — what the `hazard_relevance` table mirrors."""
    return [{"hazard_type": hz, "asset_class": ac, "headline": relevance(hz)[ac], "scale_kind": scale_kind(hz), "note": reason(hz, ac)}
            for hz in HAZARD_VALUES for ac in ASSET_CLASSES]


def headline_exclude(asset_class: str = BUILDINGS) -> tuple[str, ...]:
    """The hazards never used as a headline for this asset class."""
    return tuple(hz for hz in HAZARD_VALUES if not relevance(hz)[asset_class])


def is_headline_eligible(hazard: str, asset_class: str = BUILDINGS) -> bool:
    return relevance(hazard).get(asset_class, False)


def sync_table(session) -> int:
    """Mirror the registry into hazard_relevance (idempotent). Called at API start and by the migration."""
    from sqlalchemy import text
    session.execute(text("""CREATE TABLE IF NOT EXISTS hazard_relevance (hazard_type TEXT NOT NULL, asset_class TEXT NOT NULL, headline BOOLEAN NOT NULL, note TEXT,
                            PRIMARY KEY (hazard_type, asset_class))"""))
    session.execute(text("ALTER TABLE hazard_relevance ADD COLUMN IF NOT EXISTS scale_kind TEXT"))
    n = 0
    for r in registry():
        session.execute(text("""INSERT INTO hazard_relevance (hazard_type, asset_class, headline, scale_kind, note) VALUES (:h, :a, :e, :k, :n)
                                ON CONFLICT (hazard_type, asset_class) DO UPDATE SET headline = EXCLUDED.headline, scale_kind = EXCLUDED.scale_kind, note = EXCLUDED.note"""),
                        {"h": r["hazard_type"], "a": r["asset_class"], "e": r["headline"], "k": r["scale_kind"], "n": r["note"]})
        n += 1
    return n
