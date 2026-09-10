"""Station-extremes validators — the cold-wave, chronic-heat and heavy-precipitation channels against what
weather stations actually measured (NOAA GHCN-Daily, 1991–2020, one station per 1° box across Europe and the
contiguous US; see scripts/ingest_ghcn_extremes.py).

Why this is the honest target: the three channels are built from reanalysis (NASA POWER / MERRA-2) and gridded
ERA5 climatologies; a station thermometer or rain gauge is an independent observation of the same physical
quantity. Each test is RANK skill (kind 'rank'): does the channel's 0–100 score order locations the way the
observed extreme does? The observed quantity is the physical one the channel claims to express —
  • cold_wave    vs the observed 1-in-10 coldest night (colder = higher hazard, so the sign is flipped),
  • heat_chronic vs observed days ≥ 30 °C per year,
  • heavy_precip vs the observed mean annual maximum 1-day precipitation.
A station whose cell the channel has not scored is simply absent — never filled. Gate: Spearman ≥ 0.35 with
monotone severity bands, the platform's standard for a ranking channel.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

_SQL = """
    SELECT se.station_id, se.name, se.region, {obs} AS obs, CAST(cs.risk_score AS FLOAT) AS score
    FROM station_extremes se
    JOIN canonical_scores cs ON cs.h3_cell = se.h3_cell AND cs.hazard_type = :hz AND cs.scenario = 'baseline'
         AND cs.time_horizon = 'current' AND cs.valid_to IS NULL
    WHERE {obs} IS NOT NULL {where}
    ORDER BY se.station_id
"""


def _station_rank(hazard: str, obs_col: str, target: str, region: str | None, sign: float = 1.0):
    def run(session: Session) -> ValidationResult:
        where = "AND se.region = :reg" if region else ""
        rows = session.execute(text(_SQL.format(obs=obs_col, where=where)), {"hz": hazard, **({"reg": region} if region else {})}).mappings().all()
        return ValidationResult(
            hazard_type=hazard, kind="rank",
            predicted=[float(r["score"]) for r in rows], observed=[sign * float(r["obs"]) for r in rows],
            labels=[f"{r['station_id']} {r['name']}" for r in rows],
            target_source=f"NOAA GHCN-Daily station observations 1991–2020 — {target}",
            scope=region or "EU+US", method="out_of_sample",
            data_vintage=f"{len(rows)} stations, one per 1° box, ≥20 complete years",
            notes=("channel score at the station's cell vs the independently observed extreme at the station; "
                   "rank skill across stations; stations the channel has not scored are absent, never filled"),
        )
    return run


for _region in (None, "EU", "US"):
    _sfx = f"_{_region.lower()}" if _region else ""
    register(f"cold_wave_stations{_sfx}")(_station_rank("cold_wave", "se.coldest_1in10_c", "1-in-10 coldest night (°C)", _region, sign=-1.0))
    register(f"heat_chronic_stations{_sfx}")(_station_rank("heat_chronic", "se.hot_days_per_yr", "days ≥ 30 °C per year", _region))
    register(f"heavy_precip_stations{_sfx}")(_station_rank("heavy_precip", "se.prcp_1day_max_mm", "mean annual maximum 1-day precipitation (mm)", _region))
