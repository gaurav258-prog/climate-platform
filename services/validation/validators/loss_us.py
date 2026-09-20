"""US observed-LOSS validators — production hazard scores vs what US loss records actually show.

PRE-REGISTERED DESIGN (written before any result was computed; never tuned after seeing a ledger row).
Gate for every key here: Spearman rho >= 0.35 (engine rank gate), monotone severity bands, per-macro-region strata
(all CONUS, so one stratum expected). Predicted is ALWAYS the production score (point scorer or the standing
canonical_scores row) - never a research field. Units with no production score are dropped, never filled.

1. loss_us_nfip_flood  (OpenFEMA NFIP claims v3 + policies v2, data/loss_val/nfip)
   Unit      : OpenFEMA-rounded (0.1 deg) lat/lon location cell, USA.
   Exposure  : policy-years = sum(policyCount) over policy records with policyEffectiveDate year 2009-2023.
   Target    : (amountPaidOnBuildingClaim + amountPaidOnContentsClaim) for dateOfLoss year 2009-2023, divided by
               policy-years  ($ paid per policy-year). Secondary (metrics only, never gated): claims per policy-year.
   Eligible  : cells with >= 500 policy-years; seeded random sample (seed 20260919) of at most 400 eligible cells.
   Predicted : ml.scoring.flood_jrc.score_flood_point at the cell centre (production JRC river-flood score).
   Min n     : 50 scored cells, else the result is reported as untestable (never filled).
   Known limit: the flood channel is RIVER flood (JRC maps); NFIP paid loss also includes coastal surge and
   hurricane-driven rain, which the channel does not claim to express.

2. loss_us_storm_convective  (NOAA Storm Events 1996-2025, data/loss_val/noaa_storm_events)
   Unit      : county (CZ_TYPE 'C'; key STATE_FIPS*1000+CZ_FIPS). Universe = every county appearing in any event
               row of any type (so zero-damage counties are kept, no selection on the outcome). County location =
               median BEGIN_LAT/BEGIN_LON of that county's located events of any type; needs >= 10 located events.
   Target    : number of Thunderstorm Wind, Hail and Tornado events with property+crop damage > 0, 1996-2025
               (2026 partial year excluded), per county. Secondary (metrics only): summed damage $.
   Predicted : ml.scoring.severe_convective_point.score_severe_convective_point at the county location.
   Min n     : 200 counties.
   Known limit: no exposure normaliser (no county area/property value pulled); NWS reports track population
   and reporting effort, and larger counties log more events.

3. loss_us_storm_wind  (same Storm Events files)
   Unit      : NWS forecast zone (CZ_TYPE 'Z'; key STATE, CZ_FIPS), the unit High/Strong Wind is issued in.
               Universe = every zone in any event row; location = zone centroid from the NWS zone shapefile that
               scripts/backtest_windstorm_noaa.py already uses.
   Target    : number of High Wind and Strong Wind events with property+crop damage > 0, 1996-2025, per zone.
   Predicted : ml.scoring.windstorm_point.score_windstorm_point at the zone centroid.
   Min n     : 200 zones. Same reporting-bias limit; damaging synoptic wind is sparse (many ties at 0).

4. loss_us_rma_drought  (USDA RMA Summary of Business, cause of loss, data/loss_val/usda_rma)
   Unit      : county (state FIPS + county code), location as in (2); crop years 2001-2025, all crops.
   Target    : indemnity where cause of loss = 'Drought', divided by the summed liability of ALL cause-of-loss rows
               of the same county (an exposure proxy: the cause-of-loss file lists only indemnified records, so
               true insured liability is not available here). Eligible: proxy liability >= $5M.
               Secondary (metrics only): drought share of all-cause indemnity.
   Predicted : production standing 'drought' score in canonical_scores (baseline/current) of the nearest scored H3
               cell within 0.5 deg of the county location; counties with none are dropped.
   Min n     : 100 counties.
   Known limit: denominator is a proxy and is itself correlated with loss frequency; RMA insured crops are
               irrigated and dryland mixed; the score is a climatology of dryness, not crop-specific.
   Not registered: crop HEAT - canonical_scores holds no 'heat_acute' rows in the continental US (0 cells) and there
               is no point scorer, so it cannot be tested without scoring, which is out of scope.

LICENCE (read 2026-09-20, fema.gov/about/openfema/terms-conditions): no separate licence file ("license: None") - the
OpenFEMA terms apply. No commercial-use ban. Conditions: state "This product uses the Federal Emergency Management
Agency's OpenFEMA API, but is not endorsed by FEMA"; cite endpoint, dataset version (claims v3, policies v2) and access
date; no re-identification (we use aggregated 0.1 deg cells only); no decisions on an individual's eligibility (n/a);
FEMA disclaims data quality. Any external quote of the NFIP result must carry that disclaimer + citation; counsel to
confirm the reading before customer-facing use. NOAA Storm Events and USDA RMA are US-government public data (no licence text seen). NOAA damage figures
are local estimates, not insured loss.
"""
from __future__ import annotations

import glob
import io
import re
import zipfile
from pathlib import Path
from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.validation.engine import ValidationResult, register

BASE = Path("data/loss_val")
NFIP_CLAIMS = BASE / "nfip" / "NfipClaimsV3.parquet"
NFIP_POLICIES = BASE / "nfip" / "FimaNfipPoliciesV2.parquet"
STORM_GLOB = str(BASE / "noaa_storm_events" / "*.csv.gz")
RMA_GLOB = str(BASE / "usda_rma" / "colsom_*.zip")

SEED = 20260919
NFIP_YEARS = (2009, 2023)
NFIP_MIN_POLICY_YEARS = 500
NFIP_MAX_CELLS = 400
NFIP_MIN_N = 50
STORM_YEARS = (1996, 2025)
STORM_MIN_LOCATED = 10
STORM_MIN_N = 200
CONVECTIVE_TYPES = ("Thunderstorm Wind", "Hail", "Tornado")
WIND_TYPES = ("High Wind", "Strong Wind")
RMA_YEARS = (2001, 2025)
RMA_MIN_LIABILITY = 5_000_000.0
RMA_MIN_N = 100
RMA_MAX_DIST_DEG = 0.5


# ── pure helpers (unit-tested) ────────────────────────────────────────────────────────────────────────────────

_MULT = {"": 1.0, "K": 1e3, "M": 1e6, "B": 1e9}


def parse_damage(v) -> float:
    """NOAA damage string ('10.00K', '1.5M', '0', NaN) -> dollars; unparseable -> 0."""
    if v is None:
        return 0.0
    s = str(v).strip().upper()
    m = re.fullmatch(r"([0-9]*\.?[0-9]+)([KMB]?)", s)
    if not m:
        return 0.0
    return float(m.group(1)) * _MULT[m.group(2)]


def county_fips(state_fips, county) -> Optional[int]:
    try:
        return int(float(state_fips)) * 1000 + int(float(county))
    except (TypeError, ValueError):
        return None


def sample_cells(cells: list, n: int, seed: int = SEED) -> list:
    """Deterministic seeded sample of at most n cells (order-independent of input order)."""
    cells = sorted(cells)
    if len(cells) <= n:
        return cells
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(cells), size=n, replace=False)
    return [cells[i] for i in sorted(idx)]


def nearest_within(lat: float, lon: float, lats: np.ndarray, lons: np.ndarray, max_deg: float) -> Optional[int]:
    """Index of the nearest point within max_deg (Euclidean in degrees, lon scaled by cos lat), else None."""
    if len(lats) == 0:
        return None
    d = np.hypot(lats - lat, (lons - lon) * np.cos(np.radians(lat)))
    i = int(d.argmin())
    return i if d[i] <= max_deg else None


def _result(hazard, obs_pairs, target, scope, vintage, notes, extra, min_n, labels=None, strata=None):
    if len(obs_pairs) < min_n:
        return ValidationResult(hazard_type=f"{hazard}_loss", kind="rank", predicted=[], observed=[], target_source=target, scope=scope,
                                method="out_of_sample", data_vintage=vintage,
                                notes=f"untestable: only {len(obs_pairs)} scored units (< {min_n}). {notes}", extra=extra)
    return ValidationResult(hazard_type=f"{hazard}_loss", kind="rank", predicted=[float(p) for p, _ in obs_pairs],
                            observed=[float(o) for _, o in obs_pairs], labels=labels, strata=strata, target_source=target,
                            scope=scope, method="out_of_sample", data_vintage=vintage, notes=notes, extra=extra)


def _rho(a, b) -> Optional[float]:
    from scipy.stats import spearmanr
    if len(a) < 5:
        return None
    r = spearmanr(a, b)[0]
    return None if r != r else round(float(r), 4)


def _region(lat, lon):
    from ml.validation.regional import macro_region
    return macro_region(float(lat), float(lon))


# ── NFIP flood ────────────────────────────────────────────────────────────────────────────────────────────────

def _nfip_table():
    import pandas as pd
    import pyarrow.parquet as pq
    y0, y1 = NFIP_YEARS
    pf = pq.ParquetFile(NFIP_POLICIES)
    parts = []
    for i in range(pf.num_row_groups):
        d = pf.read_row_group(i, columns=["latitude", "longitude", "policyCount", "policyEffectiveDate"]).to_pandas()
        d["latitude"] = pd.to_numeric(d.latitude, errors="coerce"); d["longitude"] = pd.to_numeric(d.longitude, errors="coerce")
        d["policyCount"] = pd.to_numeric(d.policyCount, errors="coerce").fillna(0)
        d = d[pd.to_datetime(d.policyEffectiveDate, errors="coerce").dt.year.between(y0, y1)].dropna(subset=["latitude", "longitude"])
        if len(d):
            parts.append(d.groupby([d.latitude.round(1), d.longitude.round(1)])["policyCount"].sum())
    pol = pd.concat(parts).groupby(level=[0, 1]).sum().rename("policy_years").reset_index()
    pol.columns = ["lat", "lon", "policy_years"]
    c = pd.read_parquet(NFIP_CLAIMS, columns=["dateOfLoss", "latitude", "longitude", "amountPaidOnBuildingClaim",
                                              "amountPaidOnContentsClaim"]).dropna(subset=["latitude", "longitude"])
    for col in ("latitude", "longitude", "amountPaidOnBuildingClaim", "amountPaidOnContentsClaim"):
        c[col] = pd.to_numeric(c[col], errors="coerce")
    c = c.dropna(subset=["latitude", "longitude"])
    c = c[pd.to_datetime(c.dateOfLoss, errors="coerce").dt.year.between(y0, y1)]
    c["paid"] = c.amountPaidOnBuildingClaim.fillna(0) + c.amountPaidOnContentsClaim.fillna(0)
    cl = c.groupby([c.latitude.round(1), c.longitude.round(1)]).agg(paid=("paid", "sum"), n_claims=("paid", "size")).reset_index()
    cl.columns = ["lat", "lon", "paid", "n_claims"]
    t = pol.merge(cl, on=["lat", "lon"], how="left").fillna({"paid": 0.0, "n_claims": 0})
    t = t[t.policy_years >= NFIP_MIN_POLICY_YEARS].copy()
    t["loss_rate"] = t.paid / t.policy_years
    t["claim_rate"] = t.n_claims / t.policy_years
    return t.reset_index(drop=True)


def _nfip_flood(session: Session) -> ValidationResult:
    target = "OpenFEMA NFIP claims v3: $ paid per policy-year, 0.1° cells, 2009-2023"
    if not (NFIP_CLAIMS.exists() and NFIP_POLICIES.exists()):
        return ValidationResult(hazard_type="flood_loss", kind="rank", predicted=[], observed=[], target_source=target, scope="US",
                                method="out_of_sample", notes="data/loss_val/nfip missing")
    from ml.scoring.flood_jrc import score_flood_point
    t = _nfip_table()
    keep = sample_cells(list(zip(t.lat.round(1), t.lon.round(1))), NFIP_MAX_CELLS)
    t = t.set_index([t.lat.round(1), t.lon.round(1)]).loc[keep].reset_index(drop=True)
    pairs, rows, dropped = [], [], 0
    for r in t.itertuples():
        s = score_flood_point(float(r.lat), float(r.lon))
        if s.get("status") == "insufficient_data" or s.get("risk_score") is None:
            dropped += 1
            continue
        pairs.append((float(s["risk_score"]), float(r.loss_rate))); rows.append(r)
    extra = {"n_eligible_sampled": int(len(t)), "n_dropped_unscored": dropped,
             "rho_claims_per_policy_year": _rho([p for p, _ in pairs], [r.claim_rate for r in rows]),
             "licence": "NFIP licence UNVERIFIED (OpenFEMA metadata 'license: None')"}
    return _result("flood", pairs, target, "US", f"policies v2 + claims v3, {NFIP_YEARS[0]}-{NFIP_YEARS[1]}",
                   "production JRC river-flood score at the cell centre vs NFIP paid loss per policy-year; design pre-registered in the "
                   "module docstring. Limits: river-flood channel vs NFIP losses that include coastal/hurricane; NFIP licence unverified.",
                   extra, NFIP_MIN_N, labels=[f"{r.lat:.1f},{r.lon:.1f}" for r in rows],
                   strata=[_region(r.lat, r.lon) for r in rows])


# ── NOAA Storm Events ─────────────────────────────────────────────────────────────────────────────────────────

def _storm_frame():
    import pandas as pd
    cols = ["YEAR", "STATE", "STATE_FIPS", "CZ_TYPE", "CZ_FIPS", "EVENT_TYPE", "BEGIN_LAT", "BEGIN_LON", "DAMAGE_PROPERTY", "DAMAGE_CROPS"]
    df = pd.concat([pd.read_csv(f, compression="gzip", usecols=cols, low_memory=False) for f in sorted(glob.glob(STORM_GLOB))],
                   ignore_index=True)
    df = df[df.YEAR.between(*STORM_YEARS)]
    df["damage"] = df.DAMAGE_PROPERTY.map(parse_damage) + df.DAMAGE_CROPS.map(parse_damage)
    return df


def _storm_run(hazard: str, kind: str):
    def run(session: Session) -> ValidationResult:
        import pandas as pd
        types = CONVECTIVE_TYPES if kind == "county" else WIND_TYPES
        target = f"NOAA Storm Events {STORM_YEARS[0]}-{STORM_YEARS[1]}: damaging {'/'.join(types)} events per {'county' if kind == 'county' else 'NWS zone'}"
        if not glob.glob(STORM_GLOB):
            return ValidationResult(hazard_type=f"{hazard}_loss", kind="rank", predicted=[], observed=[], target_source=target, scope="US",
                                    method="out_of_sample", notes="data/loss_val/noaa_storm_events missing")
        df = _storm_frame()
        if kind == "county":
            from ml.scoring.severe_convective_point import score_severe_convective_point as scorer
            d = df[df.CZ_TYPE == "C"].copy()
            d["key"] = [county_fips(a, b) for a, b in zip(d.STATE_FIPS, d.CZ_FIPS)]
            d = d.dropna(subset=["key"])
            loc = d.dropna(subset=["BEGIN_LAT", "BEGIN_LON"]).groupby("key").agg(lat=("BEGIN_LAT", "median"), lon=("BEGIN_LON", "median"),
                                                                                  n=("BEGIN_LAT", "size"))
            loc = loc[loc.n >= STORM_MIN_LOCATED]
        else:
            from scripts.backtest_windstorm_noaa import _ABBR, _zone_centroids
            from ml.scoring.windstorm_point import score_windstorm_point as scorer
            zc = _zone_centroids()
            d = df[df.CZ_TYPE == "Z"].copy()
            d["key"] = [(str(s).upper(), int(z)) for s, z in zip(d.STATE, d.CZ_FIPS.fillna(-1))]
            recs = {}
            for k in d.key.unique():
                c = zc.get((_ABBR.get(k[0]), k[1]))
                if c:
                    recs[k] = c
            loc = pd.DataFrame([{"key": k, "lat": v[0], "lon": v[1]} for k, v in recs.items()]).set_index("key")
        hit = d[d.EVENT_TYPE.isin(types) & (d.damage > 0)]
        cnt = hit.groupby("key").size(); dmg = hit.groupby("key").damage.sum()
        pairs, rows, dropped = [], [], 0
        for k, r in loc.iterrows():
            s = scorer(float(r.lat), float(r.lon))
            if s.get("status") == "insufficient_data" or s.get("risk_score") is None:
                dropped += 1
                continue
            pairs.append((float(s["risk_score"]), float(cnt.get(k, 0)))); rows.append((k, r, float(dmg.get(k, 0.0))))
        extra = {"n_universe_located": int(len(loc)), "n_dropped_unscored": dropped,
                 "rho_damage_usd": _rho([p for p, _ in pairs], [x[2] for x in rows]),
                 "share_units_zero_events": round(float(np.mean([o == 0 for _, o in pairs])), 3) if pairs else None}
        return _result(hazard, pairs, target, "US", f"Storm Events csv {STORM_YEARS[0]}-{STORM_YEARS[1]}",
                       f"production {hazard} score at the unit location vs count of damaging events; design pre-registered in the module "
                       "docstring. Limits: no exposure normaliser, reporting tracks population, larger units log more events.",
                       extra, STORM_MIN_N, labels=[str(k) for k, _, _ in rows], strata=[_region(r.lat, r.lon) for _, r, _ in rows])
    return run


# ── USDA RMA drought ──────────────────────────────────────────────────────────────────────────────────────────

def parse_rma_line(line: str):
    """One pipe-delimited cause-of-loss row -> (year, county_fips, cause, liability, indemnity) or None.
    Layout (measured on the files): [0]=year [1]=state code [3]=county code [12]=cause desc, then from the END:
    [-1]=loss ratio [-2]=indemnity $; liability is field index 20."""
    f = line.rstrip("\n").split("|")
    if len(f) < 24:
        return None
    try:
        return int(f[0]), county_fips(f[1], f[3]), f[12].strip(), float(f[20]), float(f[-2])
    except (ValueError, IndexError):
        return None


def rma_county_table(lines) -> "dict[int, dict]":
    out: dict = {}
    for ln in lines:
        p = parse_rma_line(ln)
        if not p or p[1] is None or not (RMA_YEARS[0] <= p[0] <= RMA_YEARS[1]):
            continue
        _, key, cause, liab, ind = p
        e = out.setdefault(key, {"liab": 0.0, "ind_all": 0.0, "ind_drought": 0.0})
        e["liab"] += liab; e["ind_all"] += ind
        if cause == "Drought":
            e["ind_drought"] += ind
    return out


def _rma_drought(session: Session) -> ValidationResult:
    import h3
    target = f"USDA RMA cause-of-loss {RMA_YEARS[0]}-{RMA_YEARS[1]}: drought indemnity / all-cause liability per county"
    files = sorted(glob.glob(RMA_GLOB))
    if not files:
        return ValidationResult(hazard_type="drought_loss", kind="rank", predicted=[], observed=[], target_source=target, scope="US",
                                method="out_of_sample", notes="data/loss_val/usda_rma missing")
    tab: dict = {}
    for f in files:
        yr = int(re.search(r"colsom_(\d{4})", f).group(1))
        if not (RMA_YEARS[0] <= yr <= RMA_YEARS[1]):
            continue
        with zipfile.ZipFile(f) as z:
            for n in z.namelist():
                part = rma_county_table(io.TextIOWrapper(z.open(n), encoding="latin-1"))
                for k, v in part.items():
                    e = tab.setdefault(k, {"liab": 0.0, "ind_all": 0.0, "ind_drought": 0.0})
                    for kk in e:
                        e[kk] += v[kk]
    d = _storm_frame()
    d = d[d.CZ_TYPE == "C"].copy()
    d["key"] = [county_fips(a, b) for a, b in zip(d.STATE_FIPS, d.CZ_FIPS)]
    loc = d.dropna(subset=["key", "BEGIN_LAT", "BEGIN_LON"]).groupby("key").agg(lat=("BEGIN_LAT", "median"), lon=("BEGIN_LON", "median"),
                                                                                   n=("BEGIN_LAT", "size"))
    loc = loc[loc.n >= STORM_MIN_LOCATED]
    rows = session.execute(text("""SELECT h3_cell, CAST(risk_score AS FLOAT) rs FROM canonical_scores
                                   WHERE hazard_type='drought' AND scenario='baseline' AND time_horizon='current' AND valid_to IS NULL
                                     AND COALESCE(score_lane,'standing')='standing'""")).all()
    ll = np.array([h3.cell_to_latlng(c) for c, _ in rows]); sc = np.array([s for _, s in rows])
    us = (ll[:, 0] > 24) & (ll[:, 0] < 50) & (ll[:, 1] > -126) & (ll[:, 1] < -66) if len(ll) else np.array([], dtype=bool)
    ll, sc = ll[us], sc[us]
    pairs, keep, share = [], [], []
    for key, e in tab.items():
        if key not in loc.index or e["liab"] < RMA_MIN_LIABILITY:
            continue
        la, lo = float(loc.loc[key, "lat"]), float(loc.loc[key, "lon"])
        i = nearest_within(la, lo, ll[:, 0], ll[:, 1], RMA_MAX_DIST_DEG) if len(ll) else None
        if i is None:
            continue
        pairs.append((float(sc[i]), e["ind_drought"] / e["liab"])); keep.append((key, la, lo))
        share.append(e["ind_drought"] / e["ind_all"] if e["ind_all"] > 0 else 0.0)
    extra = {"rho_drought_share_of_indemnity": _rho([p for p, _ in pairs], share), "n_counties_with_rma": len(tab)}
    return _result("drought", pairs, target, "US", f"RMA colsom {RMA_YEARS[0]}-{RMA_YEARS[1]}; Storm Events county locations",
                   "production standing drought score (nearest scored cell within 0.5°) vs drought indemnity per unit all-cause liability; "
                   "design pre-registered in the module docstring. Limits: denominator is an exposure proxy, score is a dryness climatology "
                   "not crop-specific. Crop heat not registered (no US heat_acute scores).",
                   extra, RMA_MIN_N, labels=[str(k) for k, _, _ in keep], strata=[_region(a, b) for _, a, b in keep])


register("loss_us_nfip_flood")(_nfip_flood)
register("loss_us_storm_convective")(_storm_run("severe_convective", "county"))
register("loss_us_storm_wind")(_storm_run("windstorm", "zone"))
register("loss_us_rma_drought")(_rma_drought)
