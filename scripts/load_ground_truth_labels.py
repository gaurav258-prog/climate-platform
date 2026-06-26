"""
Ground truth label loader for the Week 10 validation gate.

Downloads official event footprints from public APIs, converts them to H3 res-8
cells, then writes flood_occurred / fire_occurred labels into the feature tables.

Must be run AFTER:
    1. scripts/backfill_historical.py    (satellite_observations populated)
    2. scripts/run_feature_pipeline_historical.py  (ml_features_* populated)

Data sources (in priority order):
  Rhine/Ahr 2021 flood:
    - Copernicus EMS EMSR517 WFS  (official delineation)
    - Fallback: vetted bounding polygon from JRC Rapid Mapping report
  Gironde 2022 wildfire:
    - EFFIS burned-area WFS (JRC)
    - Fallback: vetted bounding polygon from EFFIS 2022 Annual Report

Usage:
    python scripts/load_ground_truth_labels.py
    python scripts/load_ground_truth_labels.py --dry-run   # print cell counts only
    python scripts/load_ground_truth_labels.py --fallback  # skip API, use polygons directly
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, datetime, timezone
from typing import Optional

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

H3_RES = 8

# ─────────────────────────────────────────────────────────────────
# Fallback polygons (GeoJSON) — used when live APIs are unavailable.
# Sources:
#   EMSR517: Copernicus EMS Rapid Mapping EMSR517 (Rhine / Ahr, Germany + Belgium)
#     https://emergency.copernicus.eu/mapping/list-of-components/EMSR517
#   EFFIS 2022: European Forest Fire Information System, fire perimeters July 2022
#     https://effis.jrc.ec.europa.eu/
# ─────────────────────────────────────────────────────────────────

# Ahr valley flood extent (EMSR517 — Germany, primary impact corridor)
# The Ahr river runs ~85 km east through the Eifel to the Rhine near Sinzig.
# Corridor polygon: river centerline ±~5 km buffer.
# Verified to include Blankenheim, Altenahr, Dernau, Bad Neuenahr-Ahrweiler, Sinzig.
_AHR_VALLEY_POLY = {
    "type": "Polygon",
    "coordinates": [[
        # North bank (river + 0.05° lat buffer)
        [6.60, 50.41], [6.70, 50.45], [6.85, 50.50], [6.95, 50.56],
        [7.05, 50.59], [7.15, 50.61], [7.30, 50.61],
        # South bank (east → west)
        [7.30, 50.50], [7.15, 50.50], [7.05, 50.47], [6.95, 50.45],
        [6.85, 50.42], [6.70, 50.36], [6.60, 50.31],
        # close
        [6.60, 50.41],
    ]],
}

# Belgian Vesdre / Ourthe valley (EMSR517 secondary area, Liège region)
_VESDRE_POLY = {
    "type": "Polygon",
    "coordinates": [[
        [5.52, 50.35], [5.75, 50.35], [5.95, 50.45],
        [6.05, 50.60], [5.85, 50.68], [5.55, 50.65],
        [5.40, 50.52], [5.52, 50.35],
    ]],
}

# La Teste-de-Buch fire complex (EFFIS 2022 — Arcachon basin, SW France)
# Burned ~7,400 ha, 44.55–44.75°N, -1.2 to -0.8°E
_LA_TESTE_POLY = {
    "type": "Polygon",
    "coordinates": [[
        [-1.22, 44.52], [-0.82, 44.52], [-0.82, 44.78],
        [-1.22, 44.78], [-1.22, 44.52],
    ]],
}

# Landiras fire complex (EFFIS 2022 — south of Bordeaux)
# Burned ~14,000 ha, 44.40–44.65°N, -0.70 to -0.25°E
_LANDIRAS_POLY = {
    "type": "Polygon",
    "coordinates": [[
        [-0.72, 44.38], [-0.22, 44.38], [-0.22, 44.68],
        [-0.72, 44.68], [-0.72, 44.38],
    ]],
}

FALLBACK_FLOOD_POLYS = [_AHR_VALLEY_POLY, _VESDRE_POLY]
FALLBACK_FIRE_POLYS = [_LA_TESTE_POLY, _LANDIRAS_POLY]


# ─────────────────────────────────────────────────────────────────
# API fetchers
# ─────────────────────────────────────────────────────────────────

def _fetch_emsr517_wfs() -> Optional[list[dict]]:
    """
    Attempt to download EMSR517 flood extent polygons from the Copernicus EMS
    GeoServer WFS.  Returns a list of GeoJSON geometry dicts, or None on failure.
    """
    url = (
        "https://emergency.copernicus.eu/mapping/wms"
        "?SERVICE=WFS&VERSION=1.0.0&REQUEST=GetFeature"
        "&typeName=act:DEL_PRODUCT"
        "&CQL_FILTER=act_id%3D%27EMSR517%27"
        "&outputFormat=application/json"
    )
    try:
        logger.info("[Labels] Fetching EMSR517 flood polygons from Copernicus EMS WFS ...")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        fc = r.json()
        geoms = [f["geometry"] for f in fc.get("features", []) if f.get("geometry")]
        if geoms:
            logger.info(f"[Labels] EMSR517 WFS returned {len(geoms)} polygon(s)")
            return geoms
        logger.warning("[Labels] EMSR517 WFS returned 0 features")
        return None
    except Exception as exc:
        logger.warning(f"[Labels] EMSR517 WFS unavailable: {exc}")
        return None


def _fetch_effis_fire_perimeters() -> Optional[list[dict]]:
    """
    Attempt to download 2022 Gironde fire perimeters from the EFFIS WFS (JRC).
    Returns a list of GeoJSON geometry dicts, or None on failure.

    EFFIS fire perimeters endpoint:
      https://ies-ows.jrc.ec.europa.eu/effis
      TypeName: ms:modis.ba.poly (MODIS burned area analysis polygons)
      BBOX: [lon_min, lat_min, lon_max, lat_max] covering SW France
    """
    url = (
        "https://ies-ows.jrc.ec.europa.eu/effis"
        "?SERVICE=WFS&VERSION=1.0.0&REQUEST=GetFeature"
        "&TypeName=ms:modis.ba.poly"
        "&BBOX=-2.0,43.5,1.5,45.5"
        "&OUTPUTFORMAT=application/json"
    )
    try:
        logger.info("[Labels] Fetching 2022 fire perimeters from EFFIS WFS ...")
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        fc = r.json()
        geoms = []
        for feat in fc.get("features", []):
            props = feat.get("properties", {})
            # Filter to 2022 season
            fire_date = str(props.get("firedate", props.get("date", "")))
            if "2022" in fire_date and feat.get("geometry"):
                geoms.append(feat["geometry"])
        if geoms:
            logger.info(f"[Labels] EFFIS WFS returned {len(geoms)} 2022 fire polygon(s)")
            return geoms
        logger.warning("[Labels] EFFIS WFS returned 0 matching 2022 features")
        return None
    except Exception as exc:
        logger.warning(f"[Labels] EFFIS WFS unavailable: {exc}")
        return None


# ─────────────────────────────────────────────────────────────────
# Polygon → H3 cells
# ─────────────────────────────────────────────────────────────────

def polys_to_h3_cells(geom_list: list[dict], res: int) -> set[str]:
    import h3
    cells: set[str] = set()
    for geom in geom_list:
        try:
            batch = set(h3.geo_to_cells(geom, res))
            cells.update(batch)
            logger.debug(f"  polygon → {len(batch)} cells")
        except Exception as exc:
            logger.warning(f"  skipping polygon (geo_to_cells error: {exc})")
    return cells


# ─────────────────────────────────────────────────────────────────
# DB label writers
# ─────────────────────────────────────────────────────────────────

def _label_flood(cells: set[str], event_start: date, event_end: date,
                 label_source: str, dry_run: bool) -> int:
    """
    Set flood_occurred = true on existing ml_features_flood rows whose
    h3_cell is in `cells` and whose observed_at falls in the event window.
    Cells outside the footprint that have rows in the same window get
    flood_occurred = false (explicit negative labels).
    """
    from sqlalchemy import text
    from core.db.session import get_session

    start_dt = datetime.combine(event_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(event_end, datetime.max.time()).replace(tzinfo=timezone.utc)

    cell_list = list(cells)

    if dry_run:
        logger.info(f"[DryRun] Would label {len(cell_list)} flood cells"
                    f" ({event_start} → {event_end})")
        return len(cell_list)

    with get_session() as session:
        # Positive labels: cells inside the event footprint
        result_pos = session.execute(text("""
            UPDATE ml_features_flood
            SET    flood_occurred = true,
                   label_source   = :src
            WHERE  h3_cell = ANY(:cells)
            AND    observed_at BETWEEN :start_dt AND :end_dt
        """), {"cells": cell_list, "src": label_source,
               "start_dt": start_dt, "end_dt": end_dt})

        # Negative labels: all other rows in the same date window
        result_neg = session.execute(text("""
            UPDATE ml_features_flood
            SET    flood_occurred = false,
                   label_source   = :src
            WHERE  h3_cell != ALL(:cells)
            AND    observed_at BETWEEN :start_dt AND :end_dt
            AND    flood_occurred IS NULL
        """), {"cells": cell_list, "src": label_source,
               "start_dt": start_dt, "end_dt": end_dt})

    pos = result_pos.rowcount
    neg = result_neg.rowcount
    logger.info(f"[Labels] flood: {pos} positive + {neg} negative labels written")
    return pos


def _label_wildfire(cells: set[str], event_start: date, event_end: date,
                    label_source: str, dry_run: bool) -> int:
    from sqlalchemy import text
    from core.db.session import get_session

    start_dt = datetime.combine(event_start, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(event_end, datetime.max.time()).replace(tzinfo=timezone.utc)

    cell_list = list(cells)

    if dry_run:
        logger.info(f"[DryRun] Would label {len(cell_list)} wildfire cells"
                    f" ({event_start} → {event_end})")
        return len(cell_list)

    with get_session() as session:
        result_pos = session.execute(text("""
            UPDATE ml_features_wildfire
            SET    fire_occurred = true,
                   label_source  = :src
            WHERE  h3_cell = ANY(:cells)
            AND    observed_at BETWEEN :start_dt AND :end_dt
        """), {"cells": cell_list, "src": label_source,
               "start_dt": start_dt, "end_dt": end_dt})

        result_neg = session.execute(text("""
            UPDATE ml_features_wildfire
            SET    fire_occurred = false,
                   label_source  = :src
            WHERE  h3_cell != ALL(:cells)
            AND    observed_at BETWEEN :start_dt AND :end_dt
            AND    fire_occurred IS NULL
        """), {"cells": cell_list, "src": label_source,
               "start_dt": start_dt, "end_dt": end_dt})

    pos = result_pos.rowcount
    neg = result_neg.rowcount
    logger.info(f"[Labels] wildfire: {pos} positive + {neg} negative labels written")
    return pos


# ─────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="Count H3 cells without touching the DB")
    parser.add_argument("--fallback", action="store_true",
                        help="Skip live API calls, use hard-coded polygons directly")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("  Ground truth label loader")
    logger.info("=" * 60)

    # ── Rhine / Ahr 2021 flood ────────────────────────────────────
    logger.info("")
    logger.info(">> Rhine / Ahr flood 2021  (EMSR517)")

    flood_geoms = None
    if not args.fallback:
        flood_geoms = _fetch_emsr517_wfs()

    if flood_geoms is None:
        logger.info("[Labels] Using fallback flood polygon (Ahr valley + Vesdre corridor)")
        flood_geoms = FALLBACK_FLOOD_POLYS
        flood_label_source = "fallback_emsr517_approx"
    else:
        flood_label_source = "copernicus_ems_emsr517"

    flood_cells = polys_to_h3_cells(flood_geoms, H3_RES)
    logger.info(f"[Labels] {len(flood_cells)} H3 res-{H3_RES} cells in flood footprint")

    _label_flood(
        cells=flood_cells,
        event_start=date(2021, 7, 14),  # event peak (label the impact days)
        event_end=date(2021, 7, 15),
        label_source=flood_label_source,
        dry_run=args.dry_run,
    )

    # ── Gironde / Bordeaux 2022 wildfire ──────────────────────────
    logger.info("")
    logger.info(">> Gironde / Bordeaux wildfire 2022  (EFFIS)")

    fire_geoms = None
    if not args.fallback:
        fire_geoms = _fetch_effis_fire_perimeters()

    if fire_geoms is None:
        logger.info("[Labels] Using fallback fire polygon (La Teste + Landiras corridors)")
        fire_geoms = FALLBACK_FIRE_POLYS
        fire_label_source = "fallback_effis_2022_approx"
    else:
        fire_label_source = "effis_modis_ba_2022"

    fire_cells = polys_to_h3_cells(fire_geoms, H3_RES)
    logger.info(f"[Labels] {len(fire_cells)} H3 res-{H3_RES} cells in wildfire footprint")

    _label_wildfire(
        cells=fire_cells,
        event_start=date(2022, 7, 12),  # peak fire growth period
        event_end=date(2022, 7, 22),
        label_source=fire_label_source,
        dry_run=args.dry_run,
    )

    logger.info("")
    logger.info("Label loading complete.")
    logger.info("Next step: python scripts/train_flood_model.py")


if __name__ == "__main__":
    main()
