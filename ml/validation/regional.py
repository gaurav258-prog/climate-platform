"""Regional validation helpers — judge a claim per macro-region, not just pooled.

A pooled skill number can hide a failing region (Simpson's paradox): a score that ranks well over Europe+US and
is noise in the tropics still produces a healthy pooled ρ. Global-scope claims are therefore assessed per
macro-region under the pre-registered gates in `core/validation_gates.py`, and a pooled pass that conceals a
failing region is flagged (`hides_failure`).

Pure and DB-free apart from the one-off country-boundary load (data/reference/geo/countries_world_03m_2020.geojson.gz).
"""
from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

import numpy as np

from core import validation_gates as G
from ml.validation import metrics as M

_COUNTRIES = Path(__file__).resolve().parents[2] / "data" / "reference" / "geo" / "countries_world_03m_2020.geojson.gz"
_NEAREST_MAX_DEG = 1.0     # a point this close to a country (coast, offshore gauge, island) is assigned to it

_REGION_ISO2: dict[str, frozenset] = {
    "europe": frozenset("AD AL AT AX BA BE BG BY CH CY CZ DE DK EE ES FI FO FR GB GG GI GR EL HR HU IE IM IS IT JE LI LT LU LV MC MD ME MK MT NL NO PL PT RO RS SE SI SJ SK SM UA UK VA XK".split()),
    "north_america": frozenset("US CA GL PM BM".split()),
    "latin_america_caribbean": frozenset(
        "MX BZ CR SV GT HN NI PA AG AI AW BB BL BQ BS CU CW DM DO GD GP HT JM KN KY LC MF MQ MS PR SX TC TT VC VG VI "
        "AR BO BR CL CO EC FK GF GY PE PY SR UY VE".split()),
    "africa": frozenset(
        "AO BF BI BJ BW CD CF CG CI CM CV DJ DZ EG EH ER ET GA GH GM GN GQ GW KE KM LR LS LY MA MG ML MR MU MW MZ NA NE "
        "NG RE RW SC SD SL SN SO SS ST SZ TD TG TN TZ UG YT ZA ZM ZW SH".split()),
    "asia": frozenset(
        "AE AF AM AZ BD BH BN BT CN GE HK ID IL IN IQ IR JO JP KG KH KP KR KW KZ LA LB LK MM MN MO MV MY NP OM PH PK PS "
        "QA SA SG SY TH TJ TL TM TR TW UZ VN YE".split()),
    "oceania": frozenset("AS AU CK FJ FM GU KI MH MP NC NR NU NZ PF PG PN PW SB TK TO TV VU WF WS".split()),
}
_ISO2_TO_REGION = {iso: r for r, isos in _REGION_ISO2.items() for iso in isos}
_RU_EUROPE_MAX_LON = 60.0     # Russia straddles two macro-regions: west of the Urals is Europe, east is Asia


def macro_region_from_iso2(iso2: Optional[str], lon: Optional[float] = None) -> Optional[str]:
    """Macro-region of an ISO-3166 alpha-2 code (Eurostat GISCO variants EL/UK included). Russia splits at 60°E when
    a longitude is given. None for Antarctica or an unknown code — never a guess."""
    if not iso2:
        return None
    iso2 = iso2.upper()
    if iso2 == "RU":
        return "europe" if lon is not None and lon < _RU_EUROPE_MAX_LON else ("asia" if lon is not None else None)
    return _ISO2_TO_REGION.get(iso2)


@lru_cache(maxsize=1)
def _index():
    from shapely.geometry import shape
    from shapely.strtree import STRtree
    feats = json.load(gzip.open(_COUNTRIES))["features"]
    geoms, isos = [], []
    for f in feats:
        geoms.append(shape(f["geometry"]))
        isos.append(f["properties"]["CNTR_ID"])
    return STRtree(geoms), geoms, isos


def macro_region(lat: float, lon: float) -> Optional[str]:
    """Macro-region of a WGS84 point: inside a country polygon → that country's region; within ~1° of one (coast,
    offshore gauge, island) → nearest; otherwise None (open ocean / Antarctica are left unassigned, not guessed)."""
    from shapely.geometry import Point
    tree, geoms, isos = _index()
    pt = Point(float(lon), float(lat))
    hit = tree.query(pt, predicate="intersects")
    if len(hit):
        return macro_region_from_iso2(isos[int(hit[0])], lon)
    i = int(tree.nearest(pt))
    if pt.distance(geoms[i]) <= _NEAREST_MAX_DEG:
        return macro_region_from_iso2(isos[i], lon)
    return None


def stratified_report(pred: Sequence[float], obs: Sequence[float], strata: Sequence[Optional[str]], *,
                      min_n: int = G.MIN_N_REGION_CLAIM, floor: float = G.REGION_PASS_SPEARMAN) -> dict:
    """Rank skill pooled and per stratum (macro-region or climate zone).

    Per-stratum status: 'validated' (n ≥ min_n and ρ ≥ floor) · 'fails' (n ≥ min_n and ρ < floor) · 'insufficient'
    (too few samples for a regional claim). `hides_failure` is True when the pooled result passes the gate while at
    least one adequately-sampled stratum fails — the pooled number must not be quoted as the regional truth."""
    p = np.asarray(pred, float)
    o = np.asarray(obs, float)
    s = np.array([x if x else "unassigned" for x in strata], dtype=object)
    pooled_rho = M.spearman(list(p), list(o))
    out: dict = {}
    for name in sorted(set(s)):
        m = s == name
        n = int(m.sum())
        rho = M.spearman(list(p[m]), list(o[m])) if n >= M.MIN_N else None
        if n >= min_n and rho is not None:
            status = "validated" if rho >= floor else "fails"
        else:
            status = "insufficient"
        bm = M.band_monotone(p[m], o[m])
        out[str(name)] = {"n": n, "spearman": None if rho is None else round(float(rho), 4), "status": status,
                          "monotone": bm["monotone"], "monotone_method": bm["method"], "monotone_n_bands": bm["n_bands"]}
    pooled_pass = pooled_rho is not None and pooled_rho >= G.RANK_GATE_SPEARMAN
    return {
        "pooled": {"n": int(len(p)), "spearman": None if pooled_rho is None else round(float(pooled_rho), 4)},
        "by_stratum": out,
        "min_n": min_n,
        "floor": floor,
        "hides_failure": bool(pooled_pass and any(v["status"] == "fails" for v in out.values())),
    }


def loro_folds(strata: Iterable[Optional[str]]) -> Iterator[tuple[str, np.ndarray, np.ndarray]]:
    """Leave-one-region-out folds for a FITTED model: yields (held_out_region, train_idx, test_idx). For a fixed-formula
    score there is nothing to fit, so the per-stratum report above IS the transfer test; this is for models with
    parameters estimated from data, where fitting on region A and scoring region B is the honest transfer check."""
    s = np.array([x if x else "unassigned" for x in strata], dtype=object)
    for name in sorted(set(s)):
        test = np.where(s == name)[0]
        train = np.where(s != name)[0]
        if len(test) and len(train):
            yield str(name), train, test
