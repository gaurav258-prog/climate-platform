"""EUDR deforestation-free determination — the computed answer, per plot.

Combines the three facts EUDR turns on into one honest status:
  1. is the commodity in EUDR scope at all (cattle, cocoa, coffee, oil palm, rubber, soya, wood)?
  2. is the geolocation sufficient (a polygon, or a point only where the plot is ≤ 4 ha)?
  3. did the land inside the plot lose forest AFTER the 31-Dec-2020 cutoff (services...forest)?

The output is a determination WE compute from satellite data — it replaces treating the
customer's self-declared `eudr_status` flag as truth. It is deliberately conservative and
honest: when geolocation is incomplete or the forest layer can't be read, the status is
'geolocation_incomplete' / 'insufficient', never a green "deforestation_free" we didn't earn.

Statuses:
  not_covered            — commodity is outside EUDR scope; the rule doesn't apply
  deforestation_free     — geolocated, and no post-cutoff forest loss inside the plot
  non_compliant          — post-cutoff forest loss detected inside the plot
  geolocation_incomplete — a >4 ha plot was given as a point; EUDR needs the boundary
  insufficient           — the forest layer could not be read for this plot
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from shapely.geometry import Point

from services.intelligence.forest import forest_loss_since, EUDR_CUTOFF_YEAR
from services.intelligence.geometry import build_plot_geom, EUDR_POINT_MAX_HA

NOT_COVERED = "not_covered"
DEFORESTATION_FREE = "deforestation_free"
NON_COMPLIANT = "non_compliant"
GEO_INCOMPLETE = "geolocation_incomplete"
INSUFFICIENT = "insufficient"


@dataclass
class EudrDetermination:
    status: str
    reason: str
    eudr_covered: bool
    geolocation: str                    # 'polygon' | 'point' | 'none'
    area_ha: Optional[float] = None
    first_loss_year: Optional[int] = None
    loss_ha: float = 0.0
    forest_source: Optional[str] = None
    evidence: dict = field(default_factory=dict)

    def as_row(self) -> dict:
        """Flat dict for persistence on sc_sourcing_plots."""
        return {
            "eudr_determination": self.status, "eudr_loss_ha": self.loss_ha,
            "eudr_first_loss_year": self.first_loss_year, "eudr_forest_source": self.forest_source,
            "eudr_evidence": self.evidence,
        }


def determine_plot(*, eudr_covered: bool, plot_geometry: Optional[dict] = None,
                   latitude: Optional[float] = None, longitude: Optional[float] = None,
                   area_ha: Optional[float] = None, cutoff_year: int = EUDR_CUTOFF_YEAR) -> EudrDetermination:
    """Compute the EUDR determination for one plot from its stored fields.

    `plot_geometry` is the GeoJSON boundary (preferred); otherwise a lat/lon point is used. Pure
    (no DB) so it is unit-testable; the endpoint layer persists `.as_row()`."""
    if not eudr_covered:
        return EudrDetermination(NOT_COVERED, "Commodity is not within EUDR scope.",
                                 eudr_covered=False, geolocation="none")

    # Resolve the geometry: polygon boundary if given, else a point.
    if plot_geometry:
        try:
            pg = build_plot_geom(plot_geometry)
        except ValueError as e:
            return EudrDetermination(INSUFFICIENT, f"Plot boundary is invalid: {e}",
                                     eudr_covered=True, geolocation="none")
        geom, kind, eff_area = pg.geom, pg.kind, pg.area_ha
    elif latitude is not None and longitude is not None:
        geom, kind, eff_area = Point(float(longitude), float(latitude)), "point", area_ha
    else:
        return EudrDetermination(INSUFFICIENT, "No geolocation supplied.",
                                 eudr_covered=True, geolocation="none")

    # EUDR geolocation rule: a point is only valid at/below 4 ha.
    if kind == "point" and eff_area is not None and eff_area > EUDR_POINT_MAX_HA:
        return EudrDetermination(
            GEO_INCOMPLETE,
            f"Plot is {eff_area:.1f} ha (>{EUDR_POINT_MAX_HA:g}); EUDR requires a polygon boundary, not a point.",
            eudr_covered=True, geolocation="point", area_ha=eff_area)

    fl = forest_loss_since(geom, cutoff_year=cutoff_year)
    if fl.insufficient:
        return EudrDetermination(INSUFFICIENT, "Forest-loss data could not be read for this plot.",
                                 eudr_covered=True, geolocation=kind, area_ha=eff_area,
                                 forest_source=fl.source, evidence=fl.as_evidence())
    if fl.has_loss:
        return EudrDetermination(
            NON_COMPLIANT,
            f"Forest loss detected inside the plot in {fl.first_loss_year} (after the {cutoff_year} cutoff).",
            eudr_covered=True, geolocation=kind, area_ha=eff_area, first_loss_year=fl.first_loss_year,
            loss_ha=fl.loss_ha, forest_source=fl.source, evidence=fl.as_evidence())
    return EudrDetermination(
        DEFORESTATION_FREE, f"No forest loss inside the plot after the {cutoff_year} cutoff.",
        eudr_covered=True, geolocation=kind, area_ha=eff_area, forest_source=fl.source,
        evidence=fl.as_evidence())
