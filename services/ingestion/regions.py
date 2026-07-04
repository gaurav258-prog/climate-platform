"""
Ingestion regions — the geographic targets for every data source.

The ingestion adapters used to hard-code a Europe bounding box each. That made the
whole platform EU-only: to score West-Africa cocoa or Brazil coffee you had to edit
five files. This registry parameterises geography once; an adapter takes a `region`
(default 'eu', so existing behaviour is unchanged) and derives the provider-specific
format (CDS `area`, NASA FIRMS string, CDSE WKT, EMSC bbox) from a single bbox.

Bounding boxes are (min_lat, max_lat, min_lon, max_lon). Add a region here to make
every source pullable there — no adapter edits.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    key: str
    label: str
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    @property
    def cds_area(self) -> list[float]:
        """Copernicus CDS order: [North, West, South, East]."""
        return [self.max_lat, self.min_lon, self.min_lat, self.max_lon]

    @property
    def firms(self) -> str:
        """NASA FIRMS area string: plain 'west,south,east,north', no labels.

        Confirmed live against the real FIRMS API: the previous 'W=...,S=...,
        E=...,N=...' labeled format is genuinely rejected (400 "West greater
        than East") for every bbox tested (EU, Guatemala) — this adapter's
        live fetches have been silently failing whenever actually invoked
        against the real API, not just in this one case."""
        return f"{self.min_lon},{self.min_lat},{self.max_lon},{self.max_lat}"

    @property
    def wkt(self) -> str:
        """CDSE OData polygon (lon lat pairs, closed ring)."""
        return (f"POLYGON(({self.min_lon} {self.min_lat}, {self.max_lon} {self.min_lat}, "
                f"{self.max_lon} {self.max_lat}, {self.min_lon} {self.max_lat}, "
                f"{self.min_lon} {self.min_lat}))")

    @property
    def emsc_bbox(self) -> tuple[float, float, float, float]:
        """EMSC/FDSN order: (min_lat, max_lat, min_lon, max_lon)."""
        return (self.min_lat, self.max_lat, self.min_lon, self.max_lon)


REGIONS: dict[str, Region] = {
    # Europe — the original MVP extent (unchanged).
    "eu": Region("eu", "Europe", 35.0, 72.0, -10.0, 30.0),
    # West-Africa cocoa belt — Côte d'Ivoire, Ghana, Togo, Benin, Nigeria, Cameroon
    # (≈60% of world cocoa). The agriculture flagship origin.
    "west_africa_cocoa": Region("west_africa_cocoa", "West Africa cocoa belt", 4.0, 8.5, -8.5, 15.0),
    # Brazil coffee (Minas Gerais + São Paulo arabica belt) — the 2021 frost region.
    "brazil_coffee": Region("brazil_coffee", "Brazil coffee (Minas/SP)", -25.0, -14.0, -52.0, -40.0),
    # Vietnam robusta (Central Highlands).
    "vietnam_coffee": Region("vietnam_coffee", "Vietnam Central Highlands", 11.0, 15.5, 107.0, 109.5),
    # Guatemala volcanic highlands — Fuego/Acatenango/Agua, the Antigua coffee belt.
    # Primary backtest geography for the volcanic hazard: Fuego 2018's documented
    # destruction footprint (banking) and the volcanic-soil Antigua coffee origin
    # (agriculture) sit in the same small bbox.
    "guatemala_volcanic": Region("guatemala_volcanic", "Guatemala volcanic highlands", 14.3, 14.7, -91.0, -90.6),
    # Taal (Philippines) — secondary backtest, cleaner ashfall-only calibration.
    "philippines_taal": Region("philippines_taal", "Taal Volcano, Philippines", 13.9, 14.2, 120.8, 121.1),
    # Puerto Rico — the storm-hazard backtest geography: Hurricane Maria's September 2017
    # landfall track, San Juan infrastructure (banking) and Puerto Rico coffee (agriculture)
    # sit in the same small bbox, same dual-purpose logic as Fuego for volcanic.
    "puerto_rico": Region("puerto_rico", "Puerto Rico", 17.8, 18.6, -67.3, -65.2),
}

DEFAULT_REGION = "eu"


def get_region(key: str | None) -> Region:
    return REGIONS[key or DEFAULT_REGION]
