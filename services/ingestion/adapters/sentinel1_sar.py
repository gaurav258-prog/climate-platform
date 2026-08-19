"""
Sentinel-1 SAR (C-band, GRD) adapter — Copernicus Data Space Ecosystem (CDSE).

SAR VV backscatter is the primary flood-detection signal: open water is near-specular, so it returns very
low backscatter (VV gamma0 ≲ -17 dB), while dry land is typically -10 to -5 dB. A sudden drop in a cell —
absolute (into the open-water band) or relative to its recent baseline — signals inundation. The value +
its 7-day anomaly are landed as `sar_backscatter_db` / `backscatter_anomaly_7d` in the flood ML feature set
(ml/features/flood.py), which the flood model already consumes.

ACQUISITION — no SNAP, no scene downloads. We use the CDSE **Sentinel Hub Statistical API**, which computes
per-geometry statistics server-side: for each H3 cell we care about (assets / sourcing plots), one request
returns the mean terrain-corrected VV backscatter (dB) over the cell. This replaces the earlier
download-800MB-scene → SNAP-process pipeline, which needed DIAS compute.

CREDENTIALS — a free CDSE account + a Sentinel Hub OAuth client (client_id / client_secret), created in the
CDSE dashboard. Set in the environment / secret manager:
    SENTINEL_HUB_CLIENT_ID=<client id>
    SENTINEL_HUB_CLIENT_SECRET=<client secret>
With those unset the adapter stays in stub mode (SENTINEL1_STUB=true) or lands nothing — honest: the feed is
`planned` in the registry until credentials activate it. No credentials are entered in this environment.

Docs: https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Statistical.html
"""
import csv
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from sqlalchemy import text

from core.config import settings
from core.db.models import SatelliteObservation
from core.db.session import get_session
from core.types import HazardType

from .base import ADAPTER_VERSION, BaseAdapter

logger = logging.getLogger(__name__)

CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
SH_STATISTICS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

# VV gamma0 (dB) open-water threshold — C-band VV over calm open water sits well below this. A cell whose
# mean drops into this band is flagged as carrying an inundation signal. -17 dB is the widely-used
# operational threshold in Copernicus EMS / UN-SPIDER SAR flood-mapping guidance (it is a screening flag,
# not a hydraulic depth — the flood MODEL weighs the value + its anomaly against the other flood features).
OPEN_WATER_DB = -17.0

# Sentinel-1 evalscript: terrain-corrected gamma0 VV, converted to dB. `dataMask` is mandatory and lets the
# Statistical API average only valid pixels (no-data / masked pixels are excluded from the mean).
S1_VV_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["VV", "dataMask"] }],
    output: [{ id: "vv_db", bands: 1, sampleType: "FLOAT32" },
             { id: "dataMask", bands: 1 }]
  };
}
function evaluatePixel(s) {
  var db = 10.0 * Math.log(Math.max(s.VV, 1e-7)) / Math.LN10;   // linear gamma0 -> dB
  return { vv_db: [db], dataMask: [s.dataMask] };
}
"""

STUB_FIXTURE = Path(__file__).parent.parent.parent.parent / "tests/fixtures/sample_sar_features.csv"


def flood_quality(backscatter_db: float) -> tuple[int, Optional[str]]:
    """Screening flag for a VV backscatter reading. quality_flag 0 = clean land return; 1 = open-water /
    inundation signal (the value crossed the open-water threshold). Pure + deterministic → unit-tested."""
    if backscatter_db <= OPEN_WATER_DB:
        return 1, f"open-water/inundation signal (VV {backscatter_db:.1f} dB ≤ {OPEN_WATER_DB} dB)"
    return 0, None


def _cell_geojson(h3_cell: str) -> dict:
    """The H3 cell boundary as a closed GeoJSON polygon (lon,lat order). Used as the Statistical API bounds."""
    import h3
    ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(h3_cell)]
    ring.append(ring[0])  # close the ring
    return {"type": "Polygon", "coordinates": [ring]}


class Sentinel1SARAdapter(BaseAdapter):
    source_provider = "sentinel1_sar_grd"

    def __init__(self, target_date: Optional[date] = None, cells: Optional[list[str]] = None,
                 lookback_days: int = 7, max_cells: int = 500):
        self.target_date = target_date or (date.today() - timedelta(days=1))
        self.cells = cells            # explicit cells to observe; None → the org's exposure cells
        self.lookback_days = lookback_days
        self.max_cells = max_cells
        self.stub = os.getenv("SENTINEL1_STUB", "false").lower() == "true"

    # ── fetch ────────────────────────────────────────────────────────────────────────────────────────────
    def fetch(self) -> list[dict]:
        if self.stub:
            logger.info("[S1-SAR] stub mode — returning fixture data")
            return [{"stub": True}]

        if not (settings.SENTINEL_HUB_CLIENT_ID and settings.SENTINEL_HUB_CLIENT_SECRET):
            logger.warning("[S1-SAR] SENTINEL_HUB_CLIENT_ID/SECRET not set — nothing to fetch. "
                           "Set them (CDSE Sentinel Hub) to land per-cell backscatter, or SENTINEL1_STUB=true for dev.")
            return []

        token = self._sh_token()
        if not token:
            return []

        cells = self.cells or self._target_cells()
        if not cells:
            logger.info("[S1-SAR] no target H3 cells (no exposure) — nothing to fetch")
            return []

        logger.info(f"[S1-SAR] requesting VV backscatter for {len(cells)} cells via CDSE Statistical API")
        out: list[dict] = []
        for cell in cells:
            stat = self._cell_statistics(token, cell)
            if stat is not None:
                out.append(stat)
        logger.info(f"[S1-SAR] got backscatter for {len(out)}/{len(cells)} cells")
        return out

    # ── to_observations ──────────────────────────────────────────────────────────────────────────────────
    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        if not raw:
            return []
        if raw[0].get("stub"):
            return self._stub_observations()

        obs = []
        for r in raw:
            db = r.get("backscatter_db")
            if db is None:
                continue
            flag, notes = flood_quality(db)
            obs.append(SatelliteObservation(
                h3_cell=r["h3_cell"],
                h3_resolution=settings.H3_RESOLUTION,
                source_provider=self.source_provider,
                hazard_type=HazardType.FLOOD.value,
                observed_at=r["observed_at"],
                raw_value=round(db, 3),
                raw_unit="dB",
                quality_flag=flag,
                quality_notes=notes,
                adapter_version=ADAPTER_VERSION,
            ))
        return obs

    # ── CDSE Sentinel Hub Statistical API ────────────────────────────────────────────────────────────────
    def _sh_token(self) -> Optional[str]:
        try:
            resp = httpx.post(CDSE_TOKEN_URL, data={
                "grant_type": "client_credentials",
                "client_id": settings.SENTINEL_HUB_CLIENT_ID,
                "client_secret": settings.SENTINEL_HUB_CLIENT_SECRET,
            }, timeout=30)
            resp.raise_for_status()
            return resp.json()["access_token"]
        except Exception as exc:
            logger.error(f"[S1-SAR] CDSE Sentinel Hub auth failed: {exc}")
            return None

    def _statistics_body(self, h3_cell: str) -> dict:
        end = self.target_date + timedelta(days=1)
        start = self.target_date - timedelta(days=self.lookback_days)
        return {
            "input": {
                "bounds": {"geometry": _cell_geojson(h3_cell),
                           "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}},
                "data": [{"type": "sentinel-1-grd",
                          # terrain-corrected gamma0 is the radiometrically-normalised product for flood work
                          "processing": {"backCoeff": "GAMMA0_TERRAIN", "orthorectify": True}}],
            },
            "aggregation": {
                "timeRange": {"from": f"{start.isoformat()}T00:00:00Z", "to": f"{end.isoformat()}T00:00:00Z"},
                "aggregationInterval": {"of": "P1D"},
                "evalscript": S1_VV_EVALSCRIPT,
                "resx": 20, "resy": 20,   # ~20 m — Sentinel-1 GRD native resolution
            },
        }

    def _cell_statistics(self, token: str, h3_cell: str) -> Optional[dict]:
        """POST one cell to the Statistical API; return the MOST RECENT interval that has valid pixels."""
        try:
            resp = httpx.post(SH_STATISTICS_URL, json=self._statistics_body(h3_cell),
                              headers={"Authorization": f"Bearer {token}"}, timeout=60)
            resp.raise_for_status()
            intervals = resp.json().get("data", [])
        except Exception as exc:
            logger.warning(f"[S1-SAR] statistics failed for {h3_cell}: {exc}")
            return None
        for entry in reversed(intervals):   # latest first
            stats = (((entry.get("outputs") or {}).get("vv_db") or {}).get("bands") or {}).get("B0", {}).get("stats")
            if not stats:
                continue
            valid = (stats.get("sampleCount") or 0) - (stats.get("noDataCount") or 0)
            mean = stats.get("mean")
            if valid > 0 and mean is not None:
                iso = (entry.get("interval") or {}).get("from") or f"{self.target_date.isoformat()}T00:00:00Z"
                observed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                return {"h3_cell": h3_cell, "backscatter_db": float(mean), "observed_at": observed, "n_valid": int(valid)}
        return None

    def _target_cells(self) -> list[str]:
        """The H3 cells worth observing — where we actually have exposure (assets + sourcing plots). Targeted
        acquisition (not a blind EU sweep) keeps the Statistical API call count proportional to the book."""
        try:
            with get_session() as s:
                rows = s.execute(text("""
                    SELECT DISTINCT h3_cell FROM portfolio_entities WHERE h3_cell IS NOT NULL
                    UNION
                    SELECT DISTINCT h3_cell FROM sc_sourcing_plots WHERE h3_cell IS NOT NULL
                    LIMIT :lim
                """), {"lim": self.max_cells}).scalars().all()
            return [c for c in rows if c]
        except Exception as exc:
            logger.warning(f"[S1-SAR] could not resolve target cells: {exc}")
            return []

    # ── stub ─────────────────────────────────────────────────────────────────────────────────────────────
    def _stub_observations(self) -> list[SatelliteObservation]:
        """Synthetic SAR observations from the fixture CSV for local dev / CI (same shape as the live path,
        including the open-water quality flag) so the whole adapter → features → model chain is exercisable."""
        if not STUB_FIXTURE.exists():
            logger.warning(f"[S1-SAR] fixture not found: {STUB_FIXTURE}")
            return []
        observations = []
        observed_at = datetime.combine(self.target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        with open(STUB_FIXTURE) as f:
            for row in csv.DictReader(f):
                try:
                    db = float(row["backscatter_db"])
                    flag, notes = flood_quality(db)
                    observations.append(SatelliteObservation(
                        h3_cell=row["h3_cell"],
                        h3_resolution=settings.H3_RESOLUTION,
                        source_provider=self.source_provider,
                        hazard_type=HazardType.FLOOD.value,
                        observed_at=observed_at,
                        raw_value=db,
                        raw_unit="dB",
                        quality_flag=flag,
                        quality_notes=notes,
                        adapter_version=ADAPTER_VERSION,
                    ))
                except (ValueError, KeyError) as exc:
                    logger.warning(f"[S1-SAR] skipping malformed stub row: {exc}")
        logger.info(f"[S1-SAR] stub: returned {len(observations)} synthetic observations")
        return observations
