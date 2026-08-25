"""
Sentinel-3 SLSTR (Sea and Land Surface Temperature Radiometer) adapter — CDSE.

Thermal-infrared surface temperature is the acute-heat signal. The value + its anomaly vs the ERA5 baseline
are landed as `lst_kelvin` in the heat feature set (ml/features/heat.py), which the heat model consumes.

ACQUISITION (Path A — the live path) — no scene downloads, no SNAP/GDAL. We use the CDSE **Sentinel Hub
Statistical API**, exactly like the Sentinel-1 SAR adapter: for each H3 cell we care about (assets / sourcing
plots) one request returns the mean thermal brightness temperature over the cell, per satellite pass; we take
the PEAK over a short lookback window as the acute-heat reading.

HONEST — WHAT THIS BAND IS. CDSE Sentinel Hub's SLSTR collection exposes the Level-1 thermal channels, not the
Level-2 LST product — verified against the live API: the collection has no `LST` band, so we read **S8**, the
10.85 µm thermal-infrared **brightness temperature** (Kelvin). Brightness temperature is a real, direct heat
signal but it is NOT the emissivity-corrected, split-window Land-Surface-Temperature product: it runs slightly
cooler than true LST. It lands under the `sentinel3_slstr_lst` provider (the heat feature contract) with a
quality note stating it is S8 BT. The emissivity-corrected L2 LST (the SL_2_LST product) is the Path-B upgrade
— it needs raw-scene download + processing (a GDAL/NetCDF worker); the OData search for it is kept below,
guarded, for when that compute path is provisioned.

CREDENTIALS — a CDSE account + a Sentinel Hub OAuth client (client_id / client_secret), created in the CDSE
dashboard. Set in the environment / secret manager:
    SENTINEL_HUB_CLIENT_ID=<client id>
    SENTINEL_HUB_CLIENT_SECRET=<client secret>
With those unset the adapter stays in stub mode (SENTINEL3_STUB=true) or lands nothing — honest: the feed is
`planned` in the registry until credentials activate it.

Docs: https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Statistical.html
Register at https://dataspace.copernicus.eu/
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

# OData product catalog (Path B — raw L2 LST download; kept for the emissivity-corrected upgrade)
CDSE_SEARCH_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
EU_WKT = "POLYGON((-10 35, 30 35, 30 72, -10 72, -10 35))"

# SLSTR S8 — 10.85 µm thermal-infrared brightness temperature (Kelvin). `dataMask` is mandatory so the
# Statistical API averages only valid pixels.
S3_BT_EVALSCRIPT = """//VERSION=3
function setup() {
  return {
    input: [{ bands: ["S8", "dataMask"] }],
    output: [{ id: "bt", bands: 1, sampleType: "FLOAT32" },
             { id: "dataMask", bands: 1 }]
  };
}
function evaluatePixel(s) {
  return { bt: [s.S8], dataMask: [s.dataMask] };
}
"""

STUB_FIXTURE = Path(__file__).parent.parent.parent.parent / "tests/fixtures/sample_slstr_features.csv"


def _cell_geojson(h3_cell: str) -> dict:
    """The H3 cell boundary as a closed GeoJSON polygon (lon,lat order) — the Statistical API bounds."""
    import h3
    ring = [[lng, lat] for lat, lng in h3.cell_to_boundary(h3_cell)]
    ring.append(ring[0])
    return {"type": "Polygon", "coordinates": [ring]}


class Sentinel3SLSTRAdapter(BaseAdapter):
    source_provider = "sentinel3_slstr_lst"   # the heat-feature contract (ml/features/heat.py)

    def __init__(self, target_date: Optional[date] = None, cells: Optional[list[str]] = None,
                 lookback_days: int = 14, max_cells: int = 500):
        self.target_date = target_date or (date.today() - timedelta(days=1))
        self.cells = cells                    # explicit cells; None → the org's exposure cells
        self.lookback_days = lookback_days    # SLSTR revisits ~daily but has gaps/cloud — window + take the peak
        self.max_cells = max_cells
        self.stub = os.getenv("SENTINEL3_STUB", "false").lower() == "true"

    # ── fetch ────────────────────────────────────────────────────────────────────────────────────────────
    def fetch(self) -> list[dict]:
        if self.stub:
            logger.info("[S3-SLSTR] stub mode — returning fixture data")
            return [{"stub": True}]

        if not (settings.SENTINEL_HUB_CLIENT_ID and settings.SENTINEL_HUB_CLIENT_SECRET):
            logger.warning("[S3-SLSTR] SENTINEL_HUB_CLIENT_ID/SECRET not set — nothing to fetch. "
                           "Set them (CDSE Sentinel Hub) to land per-cell heat, or SENTINEL3_STUB=true for dev.")
            return []

        token = self._sh_token()
        if not token:
            return []

        cells = self.cells or self._target_cells()
        if not cells:
            logger.info("[S3-SLSTR] no target H3 cells (no exposure) — nothing to fetch")
            return []

        logger.info(f"[S3-SLSTR] requesting SLSTR S8 brightness temperature for {len(cells)} cells via CDSE Statistical API")
        out: list[dict] = []
        for cell in cells:
            stat = self._cell_statistics(token, cell)
            if stat is not None:
                out.append(stat)
        logger.info(f"[S3-SLSTR] got a heat reading for {len(out)}/{len(cells)} cells")
        return out

    # ── to_observations ──────────────────────────────────────────────────────────────────────────────────
    def to_observations(self, raw: list[dict]) -> list[SatelliteObservation]:
        if not raw:
            return []
        if raw[0].get("stub"):
            return self._stub_observations()

        obs = []
        for r in raw:
            k = r.get("bt_kelvin")
            if k is None:
                continue
            obs.append(SatelliteObservation(
                h3_cell=r["h3_cell"],
                h3_resolution=settings.H3_RESOLUTION,
                source_provider=self.source_provider,
                hazard_type=HazardType.HEAT_ACUTE.value,
                observed_at=r["observed_at"],
                raw_value=round(k, 3),
                raw_unit="K",
                quality_flag=0,
                quality_notes=("SLSTR S8 (10.85 µm) thermal-IR brightness temperature — peak over "
                               f"{self.lookback_days}d window; not emissivity-corrected L2 LST (runs slightly cool)"),
                adapter_version=ADAPTER_VERSION,
            ))
        return obs

    # ── CDSE Sentinel Hub Statistical API (Path A) ─────────────────────────────────────────────────────────
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
            logger.error(f"[S3-SLSTR] CDSE Sentinel Hub auth failed: {exc}")
            return None

    def _statistics_body(self, h3_cell: str) -> dict:
        end = self.target_date + timedelta(days=1)
        start = self.target_date - timedelta(days=self.lookback_days)
        return {
            "input": {
                "bounds": {"geometry": _cell_geojson(h3_cell),
                           "properties": {"crs": "http://www.opengis.net/def/crs/OGC/1.3/CRS84"}},
                "data": [{"type": "sentinel-3-slstr"}],
            },
            "aggregation": {
                "timeRange": {"from": f"{start.isoformat()}T00:00:00Z", "to": f"{end.isoformat()}T00:00:00Z"},
                "aggregationInterval": {"of": "P1D"},
                "evalscript": S3_BT_EVALSCRIPT,
                "resx": 0.01, "resy": 0.01,   # ~1 km — SLSTR thermal native resolution, in CRS84 degrees
            },
        }

    def _cell_statistics(self, token: str, h3_cell: str) -> Optional[dict]:
        """POST one cell; return the PEAK valid brightness temperature across the window (hottest pass = the
        acute-heat signal), with the date of that peak."""
        try:
            resp = httpx.post(SH_STATISTICS_URL, json=self._statistics_body(h3_cell),
                              headers={"Authorization": f"Bearer {token}"}, timeout=60)
            resp.raise_for_status()
            intervals = resp.json().get("data", [])
        except Exception as exc:
            logger.warning(f"[S3-SLSTR] statistics failed for {h3_cell}: {exc}")
            return None
        peak_k: Optional[float] = None
        peak_iso: Optional[str] = None
        for entry in intervals:
            stats = (((entry.get("outputs") or {}).get("bt") or {}).get("bands") or {}).get("B0", {}).get("stats")
            if not stats:
                continue
            valid = (stats.get("sampleCount") or 0) - (stats.get("noDataCount") or 0)
            mx = stats.get("max")
            if valid > 0 and mx is not None and (peak_k is None or mx > peak_k):
                peak_k = float(mx)
                peak_iso = (entry.get("interval") or {}).get("from")
        if peak_k is None:
            return None
        observed = datetime.fromisoformat((peak_iso or f"{self.target_date.isoformat()}T00:00:00Z").replace("Z", "+00:00"))
        return {"h3_cell": h3_cell, "bt_kelvin": peak_k, "observed_at": observed}

    def _target_cells(self) -> list[str]:
        """The H3 cells worth observing — where we have exposure (assets + sourcing plots). Targeted
        acquisition keeps the Statistical API call count proportional to the book (same as the SAR adapter)."""
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
            logger.warning(f"[S3-SLSTR] could not resolve target cells: {exc}")
            return []

    # ── stub ─────────────────────────────────────────────────────────────────────────────────────────────
    def _stub_observations(self) -> list[SatelliteObservation]:
        if not STUB_FIXTURE.exists():
            logger.warning(f"[S3-SLSTR] fixture not found: {STUB_FIXTURE}")
            return []
        observations = []
        observed_at = datetime.combine(self.target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        with open(STUB_FIXTURE) as f:
            for row in csv.DictReader(f):
                try:
                    observations.append(SatelliteObservation(
                        h3_cell=row["h3_cell"],
                        h3_resolution=settings.H3_RESOLUTION,
                        source_provider=self.source_provider,
                        hazard_type=HazardType.HEAT_ACUTE.value,
                        observed_at=observed_at,
                        raw_value=float(row["lst_kelvin"]),
                        raw_unit="K",
                        quality_flag=int(row.get("quality_flag", 0)),
                        adapter_version=ADAPTER_VERSION,
                    ))
                except (ValueError, KeyError) as exc:
                    logger.warning(f"[S3-SLSTR] skipping malformed stub row: {exc}")
        logger.info(f"[S3-SLSTR] stub: returned {len(observations)} synthetic observations")
        return observations
