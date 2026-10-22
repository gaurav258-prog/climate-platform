"""The platform's one timeline: global warming in °C above 1995–2014 (the product owner's decisions of 2026-10-22).

Everything is read from data/reference/climate/warming_axis.json and the source files it names, each checked against
its SHA-256 — no warming number lives in the code:

  assessed   IPCC AR6 WG1 SPM.8 panel (a): 20-year averages per pathway with the 5–95% range, moved from 1850–1900 to
             1995–2014 by the series' own 1995–2014 mean (checked against the offset the record states)
  observed   HadCRUT5 annual anomalies, moved from 1961–1990 to 1995–2014 by the file's own 1995–2014 mean

  level(pathway, year)                    a year's assessed 20-year level {low, central, high}, or None outside the series
  window("assessed"|"observed", a, b, p)  the mean level of the years a..b — a window made from climate-model output is
                                          measured on the assessed series under its pathway, one made from observations
                                          on the observed record
  anchor(pathway, horizon)                a platform horizon's level: 'current' its year's level, the others their period's
  bracket(target, levels)                 the two datasets whose levels bracket a target, and how far between them it lies;
                                          None when the target is warmer than every dataset (a named gap)

A pathway is the platform's (orderly_1_5c …) or the SSP it maps to (ssp126 …).
"""
from __future__ import annotations

import csv
import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "data" / "reference" / "climate" / "warming_axis.json"


class AxisError(ValueError):
    pass


@lru_cache(maxsize=1)
def spec() -> dict:
    return json.loads(REF.read_text(encoding="utf-8"))


def _read(path: Path, sha256: str) -> list[dict]:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != sha256:
        raise AxisError(f"{path.name} differs from the file the timeline was declared on (its checksum)")
    return list(csv.DictReader(raw.decode("utf-8").splitlines()))


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs)


def _baseline_years(s: dict) -> range:
    first, last = s["baseline"]["period"]
    return range(first, last + 1)


@lru_cache(maxsize=1)
def _assessed() -> dict:
    """{ssp: {year: (low, central, high)}} on the 1995–2014 baseline, the historical years under every pathway."""
    s = spec()
    a = s["assessed"]
    cols, d = a["columns"], ROOT / a["dir"]

    def series(entry: dict) -> dict[int, tuple[float, float, float]]:
        return {int(float(r[cols["year"]])): (float(r[cols["low"]]), float(r[cols["central"]]), float(r[cols["high"]]))
                for r in _read(d / entry["file"], entry["sha256"])}
    hist = series(a["historical"])
    offset = _mean([hist[y][1] for y in _baseline_years(s)])
    stated = a["stated_offset_c"]
    places = len(str(stated).split(".")[1])
    if round(offset, places) != stated:
        raise AxisError(f"the assessed series' own 1995–2014 mean ({offset:.4f}) is not the stated offset ({stated})")
    out = {}
    for ssp, entry in a["pathways"].items():
        merged = {**hist, **series(entry)}
        out[ssp] = {y: tuple(v - offset for v in vals) for y, vals in merged.items()}
    return out


@lru_cache(maxsize=1)
def _observed() -> dict[int, float]:
    s = spec()
    o = s["observed"]
    rows = {int(r[o["columns"]["year"]]): float(r[o["columns"]["anomaly"]]) for r in _read(ROOT / o["file"], o["sha256"])}
    offset = _mean([rows[y] for y in _baseline_years(s)])
    return {y: v - offset for y, v in rows.items()}


def ssp(pathway: str) -> Optional[str]:
    """The SSP a pathway maps to (an SSP maps to itself); None for a pathway with none (today's climate)."""
    s = spec()
    return pathway if pathway in s["assessed"]["pathways"] else s["pathways"].get(pathway)


def current_year() -> int:
    return spec()["current_year"]


def level(pathway: str, year: int) -> Optional[dict]:
    k = ssp(pathway)
    v = _assessed().get(k, {}).get(int(year)) if k else None
    return None if v is None else {"low": v[0], "central": v[1], "high": v[2]}


def window(source: str, first: int, last: int, pathway: Optional[str] = None) -> Optional[dict]:
    """The mean level of the years first..last. Assessed: under the pathway, a window running past the series' last year
    measured on its years to it (the declared rule); observed: None when any year is not yet observed."""
    if source == "observed":
        obs = _observed()
        years = range(first, last + 1)
        if any(y not in obs for y in years):
            return None
        return {"low": None, "central": _mean([obs[y] for y in years]), "high": None}
    if source != "assessed":
        raise AxisError(f"a window is measured on 'assessed' or 'observed', not {source!r}")
    k = ssp(pathway) if pathway else None
    series = _assessed().get(k) if k else None
    if not series:
        return None
    years = [y for y in range(first, min(last, max(series)) + 1)]
    if not years or any(y not in series for y in years):
        return None
    return {i: _mean([series[y][n] for y in years]) for n, i in enumerate(("low", "central", "high"))}


def anchor(pathway: str, horizon: str) -> Optional[dict]:
    if horizon == "current":
        return level(pathway, current_year())
    period = spec()["anchors"].get(horizon)
    return window("assessed", period[0], period[1], pathway) if period else None


def bracket(target: float, levels: dict[str, float]) -> Optional[tuple[str, str, float]]:
    """(lower, upper, weight): the dataset at or below the target nearest to it, the one above nearest to it, and how far
    the target lies from the lower to the upper (0 at the lower). A target on a dataset's level reads that dataset alone
    (lower = upper, weight 0). None when the target is warmer than every dataset; colder than every dataset is refused."""
    ranked = sorted(levels.items(), key=lambda kv: (kv[1], kv[0]))
    below = [kv for kv in ranked if kv[1] <= target]
    above = [kv for kv in ranked if kv[1] > target]
    if not below:
        raise AxisError(f"a target of {target:+.2f} °C is colder than every dataset")
    lo = below[-1]
    if lo[1] == target:
        return lo[0], lo[0], 0.0
    if not above:
        return None
    hi = above[0]
    return lo[0], hi[0], (target - lo[1]) / (hi[1] - lo[1])
