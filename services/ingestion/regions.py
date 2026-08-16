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
    # Spain olive belt — Andalusia + Extremadura + Castilla-La Mancha. Spain is ~45% of world
    # olive oil (IOC), and the 2022/23 drought+heat collapse (crop roughly halved, prices
    # roughly doubled) is the backtest event for this origin. Also carries the demo book's
    # Andalusian durum wheat and Extremaduran wine-grape plots.
    "spain_olive": Region("spain_olive", "Spain olive belt (Andalusia/Extremadura)", 36.0, 40.5, -7.5, -1.0),
    # Valencia / Murcia — the Spanish citrus belt (demo book's citrus plots).
    "spain_citrus": Region("spain_citrus", "Spain citrus belt (Valencia/Murcia)", 37.5, 40.0, -1.5, 0.5),
    # Castilla y León — Spain's real sugar-BEET belt (Valladolid/Palencia/Zamora). Spain grows
    # no commercial sugar cane; the demo book previously placed "cane sugar" plots in Valencia,
    # which is citrus country. Beet here is a dry continental crop: drought/heat, not flood.
    "spain_beet": Region("spain_beet", "Spain sugar-beet belt (Castilla y León)", 41.0, 42.6, -6.0, -3.8),
    # Extremadura — the demo book's wine-grape plots.
    "spain_extremadura": Region("spain_extremadura", "Extremadura, Spain", 38.0, 40.5, -7.5, -4.6),
    # Alentejo — the demo book's almond plots.
    "portugal_alentejo": Region("portugal_alentejo", "Alentejo, Portugal", 37.8, 39.3, -8.9, -6.9),
    # Morocco cereal belt (Gharb / Chaouia / Saïs — the NW rain-fed plains). The rain-fed
    # reference: Moroccan wheat is entirely rain-fed and its harvest swings with the winter
    # rains (national cereal output routinely halves in a drought), so climate should EXPLAIN
    # far more of its yield than any irrigated European crop — the step-2 test.
    "morocco_wheat": Region("morocco_wheat", "Morocco cereal belt (NW plains)", 31.0, 35.0, -9.0, -5.0),
    # Australian wheat belt (WA + SA + NSW/Vic) — the other classic dryland cereal, El Niño-driven.
    "australia_wheat": Region("australia_wheat", "Australia wheat belt", -37.0, -28.0, 115.0, 150.0),
    # Algeria cereal belt — the Hauts Plateaux + Tell (Sétif, Constantine, Tiaret, Guelma). Rain-fed
    # durum on the same Mediterranean winter-rain system as Morocco; national output swings with the
    # winter rains. The Maghreb rain-fed cluster (with Morocco/Tunisia) where climate should EXPLAIN yield.
    "algeria_wheat": Region("algeria_wheat", "Algeria cereal belt (Hauts Plateaux/Tell)", 34.5, 36.8, 1.0, 7.5),
    # Tunisia cereal belt — the northern Medjerda valley (Béja, Jendouba, Le Kef, Siliana). Rain-fed durum.
    "tunisia_wheat": Region("tunisia_wheat", "Tunisia cereal belt (north/Medjerda)", 35.5, 37.2, 8.3, 10.3),
    # Turkey cereal belt — the Central Anatolian plateau (Konya basin + Ankara/Eskişehir). The country's
    # rain-fed winter-wheat heartland; output swings with the spring rains on the plateau.
    "turkey_wheat": Region("turkey_wheat", "Turkey cereal belt (Central Anatolia)", 37.5, 40.0, 31.0, 36.0),
    # Syria cereal belt — the NE Jazira (Al-Hasakah/Deir ez-Zor) + Aleppo plains. Rain-fed wheat whose
    # national output collapses in drought (the 2007-09 drought is the textbook case).
    "syria_wheat": Region("syria_wheat", "Syria cereal belt (NE Jazira/Aleppo)", 35.0, 37.2, 37.0, 42.0),
    # Argentina wheat — the Pampas (Buenos Aires, Córdoba, Santa Fe, La Pampa). Rain-fed temperate cereal,
    # ENSO-influenced; a major Southern-Hemisphere exporter, so a distinct climate system from the Maghreb.
    "argentina_wheat": Region("argentina_wheat", "Argentina wheat belt (Pampas)", -38.5, -31.0, -64.0, -58.0),
    # Iran dryland wheat — the western Zagros belt (Kermanshah, Kurdistan, Hamadan, Lorestan). Iran's
    # RAIN-FED wheat (the central plateau is irrigated); western output swings with the winter-spring rains.
    "iran_wheat": Region("iran_wheat", "Iran dryland wheat (western Zagros)", 33.0, 38.0, 45.0, 50.0),
    # Kazakhstan spring wheat — the northern steppe (Kostanay, Akmola, North Kazakhstan). Rain-fed,
    # continental, spring-sown/summer-grown; high-latitude (~52°N), a distinct dryland cereal system.
    "kazakhstan_wheat": Region("kazakhstan_wheat", "Kazakhstan spring-wheat steppe (north)", 50.0, 54.5, 62.0, 72.0),
    # Wildfire-year stress check (2026 Mediterranean fires). NOT crop-calibrated belts — added to let
    # our drought/heat engine speak for the AGRICULTURAL regions adjacent to the July-2026 fires.
    # Gironde/Bordeaux wine country (the 2,400 ha blaze west of Bordeaux ran through pine forest + vineyards).
    "bordeaux_wine": Region("bordeaux_wine", "Bordeaux/Gironde wine belt", 44.4, 45.4, -1.0, 0.2),
    # Central Spain cereal/olive fringe around the Sierra Norte de Guadalajara (La Mierla, ~32,000 ha).
    "spain_central": Region("spain_central", "Central Spain cereal/olive (Castilla-La Mancha)", 39.0, 41.0, -4.5, -2.0),
    # Diversity / EUDR crop expansion (2026-07). Proving the method generalises beyond Mediterranean drought.
    # US Corn Belt (Iowa/Illinois/Indiana) — the iconic rain-fed maize+soy system; July silking-window drought/heat.
    "us_cornbelt": Region("us_cornbelt", "US Corn Belt (Iowa/Illinois/Indiana)", 39.0, 43.0, -97.0, -85.0),
    # Indo-Gangetic rice (Punjab/UP/Bihar) — monsoon kharif rice; heavily irrigated in Punjab (irrigation test).
    "india_rice": Region("india_rice", "Indo-Gangetic rice belt (Punjab/UP/Bihar)", 24.0, 30.0, 75.0, 87.0),
    # South African maize triangle (Free State + North West + Mpumalanga Highveld). Rain-fed, El Niño-
    # driven; repeated droughts (1991/92, 2015/16) devastate the crop — a genuine multi-realization
    # ranged-drought signal, unlike the US Corn Belt's single 2012 event.
    "south_africa_maize": Region("south_africa_maize", "South Africa maize triangle (Highveld)", -29.0, -25.5, 24.5, 29.5),
    # Tier-B crop-calibration sweep (2026-08) — world-staple expansion. Each region below was TESTED
    # against 1991–2024 national yield (FAOSTAT) and honestly HELD below the r²≥0.40 out-of-sample floor:
    # no meteorological index (SPEI/SPI/heat) was both strong and correctly signed. Kept as reusable
    # geographic infrastructure (re-fittable if regional-yield targets or a different driver land later).
    # Brazil soy/maize — Mato Grosso + Goiás cerrado. Tested: soy drought r=−0.25, maize r=0.32 → held (humid).
    "brazil_soy": Region("brazil_soy", "Brazil soy/maize (Mato Grosso/cerrado)", -20.0, -7.0, -60.0, -45.0),
    # India cane belt — Uttar Pradesh/Maharashtra. Tested: drought r=0.19 → held (heavily irrigated).
    "india_cane": Region("india_cane", "India sugar-cane belt (UP/Maharashtra)", 15.0, 30.0, 73.0, 85.0),
    # Indonesia palm — Sumatra/Kalimantan. Tested: drought r=0.16 → held (humid equatorial).
    "indonesia_palm": Region("indonesia_palm", "Indonesia oil-palm (Sumatra/Kalimantan)", -6.0, 6.0, 95.0, 119.0),
    # Canadian Prairies — SK/AB/MB canola. Tested incl. the 2021 heat-dome: drought r=0.03, heat r=0.04,
    # r²_oos −0.13 → held (national canola yield not explained by seasonal-mean climate).
    "canada_prairies": Region("canada_prairies", "Canada Prairies canola (SK/AB/MB)", 49.0, 60.0, -120.0, -95.0),
    # Nigeria Sahel sorghum — Kano/Kaduna/Bauchi savanna. Tested: drought r=0.06, r²_oos −0.12 → held.
    "nigeria_sorghum": Region("nigeria_sorghum", "Nigeria Sahel sorghum belt", 8.0, 13.0, 3.0, 14.0),
    # Sub-national ranged sweep (2026-08): the DROUGHT-PRONE Brazilian soy belt — Rio Grande do Sul,
    # rainfed, hit by every La Niña drought (2004/05, 2011/12, 2021/22, 2022/23). Going sub-national
    # WORKED as a method — RS soy vs state yield gives drought r=0.60 (vs r≈0.1 national/cerrado), driver
    # clearly drought, no biennial — but it still HELD: r²_oos=0.10, well below the 0.40 gate (a couple of
    # drought years drive the raw correlation; it doesn't generalise out-of-sample). Kept as infra + evidence.
    "brazil_rs": Region("brazil_rs", "Rio Grande do Sul soy (rainfed, drought-prone)", -34.0, -27.0, -58.0, -49.0),
}

DEFAULT_REGION = "eu"


def get_region(key: str | None) -> Region:
    return REGIONS[key or DEFAULT_REGION]
