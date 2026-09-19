"""Parametric / cat-bond basis-risk replay — what the public record lets us check, and no more.

PRE-REGISTERED DESIGN (written 2026-09-19 BEFORE any result was computed; no tuning after the run)

Data (data/parametric_val, see MANIFEST.md): IBTrACS v04r01 tracks; IBRD CAR Jamaica 2024 trigger
figures (ibrd_triggers.json + prospectus figures 1-2); CCRIF payout table + Hazard Event Reports
(INTERNAL RESEARCH ONLY - CCRIF terms forbid redistribution; nothing here may be published as data).

Pre-design geometry check (done once, before this design): the rectangular sub-area grid in
ibrd_triggers.json was compared to the prospectus Figure 2 raster (300 dpi, graticule-calibrated,
Web-Mercator latitude). Box edges agree with the JSON to <=0.01 deg (lon -78.65/-78.15/-77.65/-77.15/
-76.65/-76.15; lat 18.65/18.15/17.65/17.15), i.e. well inside the claimed +-0.05. All 19 MinCP1 labels
match the JSON. Re-reading Figure 1 shows the chamfered sub-areas 1,3,9,10,15,16,19 are RIGHT TRIANGLES
(the covered-area outline is one diagonal each side), not bounding boxes; the replay therefore uses the
triangle polygons (see _TRI_CORNERS), with the JSON bounding boxes kept as a sensitivity variant. The
figures are NOT the legal boundaries (AIR Data File is holders-only): geometry stays "approximate".

PART A - Jamaica IBRD 2024 bond replay (the only trigger geometry that is public).
  Rule (prospectus PT-12/13): per sub-area CCP = lowest central pressure on/in the sub-area, with linear
  interpolation at entry/exit; pct = 0 if CCP > MinCP1; 100% if CCP <= 900; else 30% + 70% x
  (MinCP1-CCP)/(MinCP1-900); Payout Rate = min(100%, sum over sub-areas). Track = IBTrACS USA_LAT/LON/
  USA_PRES (WMO_PRES / LAT/LON fallback), i.e. the backup source, not NHC B-deck; interpolation uses the
  planar fraction along each (<=3 h) segment (differs from great-circle fraction negligibly).
  A1 (consistency with the bond's own published outcome): risk period opens 2024-05-03. Published: Melissa
  paid 100% (US$150m). No other payout was made (the notes were outstanding until Melissa and then fully
  paid; "no other partial payout" is an inference from the case study, not an explicit statement).
  Pass = replayed Melissa rate == 100% AND every other storm in 2024-05-03..2025-10-27 replays 0%.
  A2 (robustness to the digitisation): repeat A1 under 8 shifts of +-0.05 deg and under the bbox variant.
  Report the share of variants that keep A1 passing. A3 (context, no truth): count storms 1980-2025 (46
  seasons; pressure coverage is thinner before ~1990) with replayed rate>0, compare the empirical annual
  frequency to the modelled 2.34% attachment probability with an exact Poisson 95% CI. Descriptive only.

PART B - event x country outcomes vs IBTrACS wind (physical trigger consistency, no geometry needed).
  Pairs = (storm, CCRIF government TC policy) whose paid / not-paid outcome is stated in the Final Event
  Briefings 2024-2026 (transcribed by hand in _PAIRS; ambiguous ones - regional Bahamas Melissa, Saint
  Lucia/Barbados Beryl - are omitted). Feature = max USA_WIND (kt) of that storm within 150 km of the
  country reference point. Metric = AUC(paid vs not). CCRIF pays on its modelled LOSS (exposure-weighted
  wind+surge), not wind, so AUC well below 1 is expected basis risk, not a defect. Descriptive; n stated.

PART C - does our production `storm` score rank CCRIF members in line with TC payouts?
  Score = production storm score at the member's reference point.
  AMENDMENT (2026-09-19, made after run #1, before run #2, WITHOUT seeing any Part-C skill number because
  run #1 returned n=2 - Spearman null): run #1 used the mean of stored canonical_scores cells within 100 km;
  only 2 of 19 members had any stored cell (the stored storm channel is not materialised over the CCRIF
  islands: nearest stored cell to Jamaica/Haiti/Bahamas is >4 deg away). Run #2 uses the same production
  model computed on demand at the point (ml.scoring.storm_return_level.storm_return_level_score, read-only,
  the scorer behind the any-address lookup). Run #1 stays in the ledger as a coverage failure. Caveat: that
  scorer and Part B/yardstick all derive from IBTrACS, so Part C is not independent of the track record.
  Outcome = cumulative government TC-policy payout USD 2007-2026 (table 0 rows, excluding
  Excess Rainfall, COAST, utility, CTCEC rows). Primary set = the 15 members with a payout + members that
  appear in the 2024-26 reports with a TC policy and zero payouts (Cayman, Honduras, Sint Maarten, BVI) = 19.
  Zero payers are ONLY those visible in 2024-26 reports -> selection bias, and payout size also depends on
  policy limits/attachment which we do not have. Secondary (reference, not graded): paid-only set;
  and raw IBTrACS count of >=64 kt track points within 100 km, 1980-2024, as the "how rankable is this at
  all" yardstick. Metric = Spearman with a 20,000-permutation p (seed 0). kind='rank' is used only if
  n >= 8, otherwise the result is labelled DESCRIPTIVE. Nothing here changes any tier: results are
  recorded under hazard_type 'storm_parametric', never 'storm'.

Not replayable (blockers): Mexico 2024 Class D (box vertices/MinCP per box only in the AIR Data File),
Mexico A/B/C, Philippines 2019 (vendor modelled-loss trigger), Jamaica 2021, Pacific Alliance, Chile 2023
(earthquake; per-box thresholds unpublished). CCRIF XSR (rainfall) needs CMORPH/WRF fields not on disk.
"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
from sqlalchemy.orm import Session

from ml.validation import metrics as M
from services.validation.engine import ValidationResult, register

DATA = Path(__file__).resolve().parents[3] / "data" / "parametric_val"
MIN_N_RANK = 8
RISK_START = datetime(2024, 5, 3)
MELISSA_LAST_DAY = datetime(2025, 10, 27)

# corner order (x0,x1,y0,y1 = lon_min, lon_max, lat_min, lat_max): which 3 corners each triangle keeps
_TRI_CORNERS = {
    1: ("x0y0", "x1y0", "x1y1"), 3: ("x0y1", "x0y0", "x1y0"), 9: ("x0y1", "x0y0", "x1y0"),
    10: ("x0y1", "x1y1", "x1y0"), 15: ("x0y1", "x1y1", "x0y0"), 16: ("x0y1", "x1y1", "x1y0"),
    19: ("x0y1", "x1y1", "x0y0"),
}

# (storm NAME, season, basin, country key, paid 0/1) - hand-transcribed from CCRIF Final Event Briefings.
_PAIRS = [
    ("BERYL", 2024, "NA", "Saint Vincent and the Grenadines", 1), ("BERYL", 2024, "NA", "Grenada", 1),
    ("BERYL", 2024, "NA", "Trinidad and Tobago", 1), ("BERYL", 2024, "NA", "Jamaica", 1),
    ("BERYL", 2024, "NA", "Haiti", 0), ("BERYL", 2024, "NA", "Cayman Islands", 0),
    ("SARA", 2024, "NA", "Belize", 0), ("NADINE", 2024, "NA", "Belize", 0),
    ("OSCAR", 2024, "NA", "Turks and Caicos Islands", 0), ("OSCAR", 2024, "NA", "Haiti", 0),
    ("OSCAR", 2024, "NA", "Bahamas SE", 0), ("OSCAR", 2024, "NA", "Bahamas Central", 0),
    ("RAFAEL", 2024, "NA", "Jamaica", 0), ("RAFAEL", 2024, "NA", "Cayman Islands", 0),
    ("ERIN", 2025, "NA", "Saint Kitts and Nevis", 0), ("ERIN", 2025, "NA", "Anguilla", 0),
    ("ERIN", 2025, "NA", "British Virgin Islands", 0), ("ERIN", 2025, "NA", "Antigua and Barbuda", 0),
    ("ERIN", 2025, "NA", "Sint Maarten", 0), ("ERIN", 2025, "NA", "Turks and Caicos Islands", 0),
    ("ERIN", 2025, "NA", "Bahamas SE", 0), ("JERRY", 2025, "NA", "Antigua and Barbuda", 0),
    ("MELISSA", 2025, "NA", "Jamaica", 1), ("IMELDA", 2025, "NA", "Bahamas Central", 1),
    ("IMELDA", 2025, "NA", "Bahamas SE", 1), ("IMELDA", 2025, "NA", "Bahamas NW", 0),
    ("CRISTINA", 2026, "EP", "Nicaragua", 0), ("CRISTINA", 2026, "EP", "Honduras", 0),
]

# approximate reference points (lat, lon); fixed here before the run
_REF = {
    "Jamaica": (18.1, -77.3), "Haiti": (19.0, -72.3), "Nicaragua": (12.9, -85.2), "Belize": (17.2, -88.7),
    "Barbados": (13.19, -59.54), "Saint Lucia": (13.91, -60.98), "Saint Vincent and the Grenadines": (13.25, -61.2),
    "Grenada": (12.12, -61.68), "Dominica": (15.42, -61.35), "Antigua and Barbuda": (17.06, -61.8),
    "Saint Kitts and Nevis": (17.33, -62.75), "Anguilla": (18.22, -63.05),
    "Turks and Caicos Islands": (21.8, -71.8), "Bahamas": (25.03, -77.4), "Trinidad and Tobago": (10.7, -61.2),
    "Cayman Islands": (19.3, -81.25), "Honduras": (14.8, -86.6), "Sint Maarten": (18.05, -63.06),
    "British Virgin Islands": (18.42, -64.62),
    "Bahamas Central": (24.5, -76.0), "Bahamas SE": (22.5, -74.0), "Bahamas NW": (26.5, -78.0),
}
_ZERO_PAYERS = ["Cayman Islands", "Honduras", "Sint Maarten", "British Virgin Islands"]
_NOT_GOV_TC = ("excess rainfall", "coast", "electric", "cwuic", "cayman turtle", "ctcec")
_ALIASES = {"tobago": "Trinidad and Tobago", "trinidad": "Trinidad and Tobago",
            "st vincent": "Saint Vincent and the Grenadines", "st. vincent": "Saint Vincent and the Grenadines",
            "st kitts": "Saint Kitts and Nevis", "st. kitts": "Saint Kitts and Nevis",
            "saint lucia": "Saint Lucia", "turks": "Turks and Caicos Islands", "antigua": "Antigua and Barbuda",
            "bahamas": "Bahamas", "turks & caicos": "Turks and Caicos Islands"}


# ---------------------------------------------------------------------------------------- pure helpers
def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (R=6371); scalar or numpy."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin((p2 - p1) / 2) ** 2
         + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def payout_pct(ccp: float, min1: float, min2: float) -> float:
    """Jamaica-2024 step: 0 above MinCP1, 100% at/below MinCP2, else 30% + 70% linear."""
    if ccp > min1:
        return 0.0
    if ccp <= min2:
        return 1.0
    return 0.3 + 0.7 * (min1 - ccp) / (min1 - min2)


def _ccw(poly):
    area = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
               for i in range(len(poly)))
    return list(poly) if area > 0 else list(reversed(poly))


def clip_segment(p0, p1, poly) -> Optional[tuple]:
    """Cyrus-Beck clip of segment p0->p1 (x=lon, y=lat) to a convex polygon. Returns (t_in, t_out) in [0,1]
    or None when the segment misses (touching counts as inside)."""
    poly = _ccw(poly)
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    t0, t1 = 0.0, 1.0
    for i in range(len(poly)):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % len(poly)]
        ex, ey = bx - ax, by - ay
        num = ex * (p0[1] - ay) - ey * (p0[0] - ax)     # >=0 means inside (left of edge)
        den = ex * dy - ey * dx                         # rate of change of `num` (sign flipped below)
        rate = den
        if abs(rate) < 1e-15:
            if num < -1e-12:
                return None
            continue
        t = -num / rate
        if rate > 0:            # entering
            t0 = max(t0, t)
        else:                   # leaving
            t1 = min(t1, t)
        if t0 > t1 + 1e-12:
            return None
    return (t0, t1)


def calculated_central_pressure(track: list, poly) -> Optional[float]:
    """CCP = min pressure of the track on/within the polygon incl. interpolated entry/exit values.
    `track` = list of (lon, lat, pressure) in time order. None when the track never touches the polygon."""
    best: Optional[float] = None
    for a, b in zip(track[:-1], track[1:]):
        c = clip_segment((a[0], a[1]), (b[0], b[1]), poly)
        if c is None:
            continue
        for t in c:
            p = a[2] + (b[2] - a[2]) * t
            best = p if best is None else min(best, p)
    if best is None and len(track) == 1 and _inside((track[0][0], track[0][1]), poly):
        best = track[0][2]
    return best


def _inside(pt, poly) -> bool:
    poly = _ccw(poly)
    for i in range(len(poly)):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % len(poly)]
        if (bx - ax) * (pt[1] - ay) - (by - ay) * (pt[0] - ax) < -1e-12:
            return False
    return True


def payout_rate(track: list, subareas: list) -> float:
    """Sum of per-sub-area payout percentages over intersected sub-areas, capped at 100%."""
    total = 0.0
    for sa in subareas:
        ccp = calculated_central_pressure(track, sa["poly"])
        if ccp is not None:
            total += payout_pct(ccp, sa["min1"], sa["min2"])
    return min(1.0, total)


def build_subareas(raw: list, *, triangles: bool = True, shift=(0.0, 0.0)) -> list:
    """Polygons from the JSON bbox rows; chamfered sub-areas become right triangles when `triangles`."""
    out = []
    for r in raw:
        x0, x1 = r["approx_bbox_lon_min"] + shift[0], r["approx_bbox_lon_max"] + shift[0]
        y0, y1 = r["approx_bbox_lat_min"] + shift[1], r["approx_bbox_lat_max"] + shift[1]
        corners = {"x0y0": (x0, y0), "x1y0": (x1, y0), "x0y1": (x0, y1), "x1y1": (x1, y1)}
        sid = int(r["subarea"])
        if triangles and sid in _TRI_CORNERS:
            poly = [corners[k] for k in _TRI_CORNERS[sid]]
        else:
            poly = [corners["x0y0"], corners["x1y0"], corners["x1y1"], corners["x0y1"]]
        out.append({"id": sid, "poly": poly, "min1": float(r["min_cp1_hPa"]), "min2": float(r["min_cp2_hPa"])})
    return out


def auc_binary(feature: Iterable[float], positive: Iterable[int]) -> Optional[float]:
    """Mann-Whitney AUC with ties counted half; None if a class is empty."""
    f = np.asarray(list(feature), float)
    y = np.asarray(list(positive), bool)
    pos, neg = f[y], f[~y]
    if len(pos) == 0 or len(neg) == 0:
        return None
    gt = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(gt / (len(pos) * len(neg)))


def poisson_ci(k: int, exposure: float, z: float = 1.96) -> tuple:
    """Approximate exact-style Poisson CI for a rate k/exposure (Garwood via chi2-free Wilson-Hilferty)."""
    def _chi2_q(p, df):   # Wilson-Hilferty approximation of chi-square quantile
        from statistics import NormalDist
        zz = NormalDist().inv_cdf(p)
        return df * (1 - 2 / (9 * df) + zz * math.sqrt(2 / (9 * df))) ** 3
    lo = 0.0 if k == 0 else _chi2_q(0.025, 2 * k) / 2
    hi = _chi2_q(0.975, 2 * (k + 1)) / 2
    return lo / exposure, hi / exposure


def perm_p_spearman(x, y, n_perm: int = 20000, seed: int = 0) -> Optional[float]:
    """Two-sided permutation p for Spearman rho (ties handled by rank-average)."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    obs = M.spearman(x, y)
    if obs is None:
        return None
    rng = np.random.default_rng(seed)
    rx, ry = M.rank(x), M.rank(y)
    cnt = 0
    for _ in range(n_perm):
        if abs(np.corrcoef(rx, rng.permutation(ry))[0, 1]) >= abs(obs) - 1e-12:
            cnt += 1
    return (cnt + 1) / (n_perm + 1)


def normalise_member(member: str) -> Optional[str]:
    """Government TC-policy member -> country key, or None if it is a rainfall/utility/other product."""
    m = member.lower().strip()
    if any(tok in m for tok in _NOT_GOV_TC):
        return None
    m = m.replace("tropical cyclone policy -", "").strip()
    for k, v in _ALIASES.items():
        if k in m:
            return v
    for name in _REF:
        if name.lower() == m or name.lower() in m:
            return name
    return None


def cumulative_tc_payouts(rows: Iterable[dict]) -> dict:
    """Sum government TC-policy payouts (table 0, hazard tropical_cyclone) by country."""
    tot: dict = {}
    for r in rows:
        if r.get("hazard") != "tropical_cyclone" or str(r.get("table_idx")) != "0":
            continue
        c = normalise_member(r["member"])
        if c:
            tot[c] = tot.get(c, 0.0) + float(r["payout_usd"])
    return tot


# ---------------------------------------------------------------------------------------- data loading
def _load_ibtracs(min_season: int = 1980):
    import pandas as pd
    df = pd.read_csv(DATA / "ibtracs" / "ibtracs.ALL.list.v04r01.csv", skiprows=[1], keep_default_na=False,
                     usecols=["SID", "SEASON", "NAME", "BASIN", "ISO_TIME", "LAT", "LON", "USA_LAT", "USA_LON",
                              "USA_PRES", "WMO_PRES", "USA_WIND"], low_memory=False)
    df = df[pd.to_numeric(df["SEASON"], errors="coerce") >= min_season].copy()
    for c in ("LAT", "LON", "USA_LAT", "USA_LON", "USA_PRES", "WMO_PRES", "USA_WIND"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["lat"] = df["USA_LAT"].fillna(df["LAT"])
    df["lon"] = df["USA_LON"].fillna(df["LON"])
    df["pres"] = df["USA_PRES"].where(df["USA_PRES"] > 0).fillna(df["WMO_PRES"].where(df["WMO_PRES"] > 0))
    df["t"] = pd.to_datetime(df["ISO_TIME"])
    return df


def _tracks(df, basin="NA"):
    """{SID: (name, season, [(lon,lat,pres,t)...] time-ordered, valid pressure only)}."""
    out = {}
    for sid, g in df[df["BASIN"] == basin].groupby("SID"):
        g = g.sort_values("t")
        gg = g.dropna(subset=["pres", "lat", "lon"])
        if len(gg):
            out[sid] = (g["NAME"].iloc[0], int(g["SEASON"].iloc[0]),
                        [(float(a), float(b), float(c), d) for a, b, c, d in
                         zip(gg["lon"], gg["lat"], gg["pres"], gg["t"])])
    return out


def _load_bond():
    d = json.loads((DATA / "ibrd_triggers.json").read_text())
    b = next(x for x in d["bonds"] if "Jamaica 2024" in x["bond"])
    return b["geographic_definition"]["subareas"]


# ---------------------------------------------------------------------------------------- the parts
def part_a(df) -> dict:
    raw = _load_bond()
    tr = _tracks(df, "NA")
    variants = {"triangles": build_subareas(raw), "bbox": build_subareas(raw, triangles=False)}
    for dx in (-0.05, 0.0, 0.05):
        for dy in (-0.05, 0.0, 0.05):
            if (dx, dy) != (0.0, 0.0):
                variants[f"shift_{dx:+.2f}_{dy:+.2f}"] = build_subareas(raw, shift=(dx, dy))

    def run(sub):
        rates = {sid: (nm, se, payout_rate([(x, y, p) for x, y, p, _ in pts], sub), pts[0][3], pts[-1][3])
                 for sid, (nm, se, pts) in tr.items()}
        mel = [r for r in rates.values() if r[0] == "MELISSA" and r[1] == 2025]
        in_win = [(r[0], r[1], r[2]) for r in rates.values()
                  if r[3] >= RISK_START and r[3] <= MELISSA_LAST_DAY and r[2] > 0]
        hist = [(r[0], r[1], round(r[2], 3)) for r in rates.values() if 1980 <= r[1] <= 2025 and r[2] > 0]
        return {"melissa_rate": round(mel[0][2], 4) if mel else None, "in_window_positive": in_win,
                "hist_events": hist}
    res = {k: run(v) for k, v in variants.items()}
    base = res["triangles"]
    passes = {k: (v["melissa_rate"] is not None and v["melissa_rate"] >= 0.9999
                  and not any(n != "MELISSA" for n, _, _ in v["in_window_positive"])) for k, v in res.items()}
    n_season = 46
    k = len(base["hist_events"])
    lo, hi = poisson_ci(k, n_season)
    mel_pts = [pts for (nm, se, pts) in tr.values() if nm == "MELISSA" and se == 2025][0]
    return {"primary": base, "variants_pass": passes, "share_variants_pass": round(sum(passes.values()) / len(passes), 3),
            "n_variants": len(passes), "hist_annual_freq": round(k / n_season, 4),
            "hist_ci95": [round(lo, 4), round(hi, 4)], "modelled_attachment_prob": 0.0234,
            "melissa_min_pres_in_track": min(p for _, _, p, _ in mel_pts),
            "bbox_melissa": res["bbox"]["melissa_rate"]}


def part_b(df) -> dict:
    rows = []
    for name, season, basin, ctry, paid in _PAIRS:
        g = df[(df["NAME"] == name) & (df["SEASON"] == season) & (df["BASIN"] == basin)]
        lat0, lon0 = _REF[ctry]
        d = haversine_km(g["lat"].to_numpy(float), g["lon"].to_numpy(float), lat0, lon0) if len(g) else np.array([])
        w = g["USA_WIND"].to_numpy(float)[d <= 150] if len(g) else np.array([])
        w = w[~np.isnan(w)]
        rows.append((name, ctry, paid, float(w.max()) if len(w) else 0.0))
    feat = [r[3] for r in rows]
    y = [r[2] for r in rows]
    return {"n_pairs": len(rows), "n_paid": int(sum(y)), "auc_peak_wind_150km": auc_binary(feat, y),
            "paid_wind_kt": sorted(r[3] for r in rows if r[2]), "unpaid_wind_kt": sorted(r[3] for r in rows if not r[2]),
            "unpaid_ge_paid_min": int(sum(1 for r in rows if not r[2] and r[3] >= min(x[3] for x in rows if x[2])))}


def _storm_scores(session: Session, names: list):
    """Production storm score AT the reference point via the read-only on-demand scorer (no DB writes)."""
    from ml.scoring.storm_return_level import storm_return_level_score
    out = {}
    for n in names:
        try:
            out[n] = float(storm_return_level_score(*_REF[n])["score"])
        except Exception:   # noqa: BLE001 - a member the scorer cannot answer is dropped and listed
            out[n] = None
    return out


def part_c(session: Session, df) -> dict:
    with open(DATA / "ccrif" / "ccrif_payouts.csv") as f:
        tot = cumulative_tc_payouts(csv.DictReader(f))
    paid = sorted(tot)
    members = paid + [z for z in _ZERO_PAYERS if z not in tot]
    sc = _storm_scores(session, members)
    ok = [m for m in members if sc.get(m) is not None]
    pred = [sc[m] for m in ok]
    obs = [tot.get(m, 0.0) for m in ok]
    # yardstick: >=64 kt track points within 100 km, 1980-2024, NA basin
    hh = df[(df["SEASON"] <= 2024) & (df["USA_WIND"] >= 64)]
    yard = {}
    for m in ok:
        d = haversine_km(hh["lat"].to_numpy(float), hh["lon"].to_numpy(float), *_REF[m])
        yard[m] = int((d <= 100).sum())
    po = [m for m in ok if m in tot]
    return {"members": ok, "pred": pred, "obs": obs, "dropped_no_score": [m for m in members if m not in ok],
            "spearman": M.spearman(np.array(pred), np.array(obs)), "perm_p": perm_p_spearman(pred, obs),
            "paid_only": {"n": len(po), "spearman": M.spearman(np.array([sc[m] for m in po]), np.array([tot[m] for m in po]))},
            "yardstick_ibtracs_hurricane_pts": {
                "spearman": M.spearman(np.array([yard[m] for m in ok]), np.array(obs)),
                "paid_only_spearman": M.spearman(np.array([yard[m] for m in po]), np.array([tot[m] for m in po]))},
            "score_by_member": {m: round(sc[m], 2) for m in ok}}


def _run(session: Session) -> ValidationResult:
    df = _load_ibtracs(1980)
    a, b, c = part_a(df), part_b(df), part_c(session, df)
    n = len(c["members"])
    descriptive = n < MIN_N_RANK
    notes = (f"PARAMETRIC REPLAY ({'DESCRIPTIVE ONLY, n<8' if descriptive else 'rank on n=%d members' % n}). "
             f"A: Melissa replay rate {a['primary']['melissa_rate']}, other in-window storms >0: "
             f"{[x for x in a['primary']['in_window_positive'] if x[0] != 'MELISSA']}, geometry variants passing "
             f"{a['share_variants_pass']}. B: AUC {b['auc_peak_wind_150km']} on {b['n_pairs']} pairs "
             f"({b['n_paid']} paid). C: Spearman {c['spearman']} (perm p {c['perm_p']}). CCRIF data internal-only; "
             f"payout size confounded by policy limits; selection bias in zero-payer set.")
    return ValidationResult(
        hazard_type="storm_parametric", kind="rank", predicted=c["pred"], observed=c["obs"], labels=c["members"],
        target_source="CCRIF published TC-policy payouts 2007-2026 (internal research only)",
        scope="CCRIF members (Caribbean/Central America)", method="in_sample", notes=notes,
        extra={"part_a": a, "part_b": b, "part_c_secondary": {k: c[k] for k in
               ("paid_only", "yardstick_ibtracs_hurricane_pts", "score_by_member", "dropped_no_score")},
               "descriptive_only": descriptive})


register("storm_parametric")(_run)
