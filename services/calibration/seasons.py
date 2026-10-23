"""When a crop grows in an origin (E163) — data/reference/crop_seasons.json: MIRCA-OS 2015 for the crops it covers (one
share rule), FAO-56 Table 11 rows for olive, citrus and wine grapes in the origins listed. A crop × origin with no season
is held with the reason, never given a guessed one.

A region's season (region_season) is read the same way from the MIRCA-OS units of that region — the units whose
'Province' is the region's name in the official list (services.reference.regions); a region the list does not name (a
NUTS-2 region) takes its country's season, and says so."""
from __future__ import annotations

import csv
import io
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REF = ROOT / "data" / "reference" / "crop_seasons.json"


@lru_cache(maxsize=1)
def reference() -> dict:
    return json.loads(REF.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _mirca() -> list[tuple[int, str, float, int, int, str]]:
    """[(M49 country code, crop, growing area ha, planting month, maturity month, province)] — rainfed and irrigated
    rows."""
    ref = reference()["mirca_os"]
    out = []
    for f in ref["files"]:
        for r in csv.DictReader(io.StringIO((ROOT / f).read_bytes().decode(ref["encoding"]))):
            area = float(r["Growing_area"] or 0)
            if area > 0:
                out.append((int(r["unit_code"]) // 10000, r["Crop"].strip(), area,
                            int(r["Planting_Month"]), int(r["Maturity_Month"]), (r["Province"] or "").strip()))
    return out


def _in_season(p: int, m: int) -> list[tuple[int, bool]]:
    """[(month, previous year?)] from planting to maturity, both included; a season crossing the new year belongs to its
    maturity year."""
    if p <= m:
        return [(x, False) for x in range(p, m + 1)]
    return [(x, True) for x in range(p, 13)] + [(x, False) for x in range(1, m + 1)]


def mirca_season(commodity: str, m49: int, names: list[str], mapped_ha: float | None = None,
                 province: str | None = None) -> dict:
    """The season from the MIRCA-OS units of a country — or of one province of it (`province`: the unit's 'Province',
    matched exactly)."""
    rows = [r for r in _mirca() if r[0] == m49 and r[1] in names and (province is None or r[5] == province)]
    total = sum(r[2] for r in rows)
    if not total:
        return {"held": f"MIRCA-OS holds no growing area for {', '.join(names)} in this "
                        + (f"region ('{province}')" if province else "origin")}
    cover = reference()["mirca_os"]["coverage_min"]
    if mapped_ha and total < cover * mapped_ha:          # the calendars describe a minority of the crop (E168)
        return {"held": f"MIRCA-OS's calendars cover {total:,.0f} ha of the {mapped_ha:,.0f} ha the crop map holds in "
                        f"the {'region' if province else 'origin'} ({100 * total / mapped_ha:.0f}%) — less than half, "
                        "so they do not state its season"}
    share: dict[tuple[int, bool], float] = {}
    for _c, _n, area, p, m, _pr in rows:
        for k in _in_season(p, m):
            share[k] = share.get(k, 0.0) + area
    need = reference()["mirca_os"]["share_min"]
    picked = sorted(k for k, a in share.items() if a / total >= need)
    if not picked:
        return {"held": "no month holds half the crop's growing area (several seasons)"}
    order = sorted(m - 12 if prev else m for m, prev in picked)          # harvest-year order: previous-year months first
    if any(b != a + 1 for a, b in zip(order, order[1:])):
        return {"held": "the months holding half the crop's growing area are not one season (MIRCA-OS lists several "
                        "calendars for the origin)"}
    return {"months": sorted(m for m, prev in picked if not prev), "prev_months": sorted(m for m, prev in picked if prev),
            "basis": f"MIRCA-OS 2015 ({', '.join(names)}): months holding at least half of {total:,.0f} ha growing area"}


def fao56_season(commodity: str, origin: str) -> dict:
    ref = reference()["fao56"]
    row = ref["crops"].get(commodity)
    if row is None:
        return {"held": ref["gaps"].get(commodity, "no FAO-56 Table 11 row is stated for this crop")}
    origins = ref[row["origins"]] if isinstance(row["origins"], str) else row["origins"]
    if origin not in origins:
        return {"held": f"FAO-56 Table 11's '{row['region']}' row is not applied to this origin"}
    import datetime as dt
    start = dt.date(2001, row["start_month"], 1)
    end = start + dt.timedelta(days=sum(row["stages_days"]) - 1)
    months, prev = [], []
    d = start
    while d <= end:
        (months if d.year == end.year else prev).append(d.month)
        d = (d.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return {"months": sorted(set(months)), "prev_months": sorted(set(prev)),
            "basis": f"FAO-56 Table 11 '{row['row']}' ({row['region']}): from {start:%B}, {sum(row['stages_days'])} days"}


def season(commodity: str, origin: str, m49: int | None, mapped_ha: float | None = None) -> dict:
    """{months, prev_months, basis} or {held: reason} for a crop × origin. `mapped_ha`: the crop map's harvested area in
    the origin, which a MIRCA-OS calendar must cover at least half of (E168)."""
    from ml.features.crop_registry import crop
    src = crop(commodity).get("season_source") or {}
    if "mirca_os" in src:
        if m49 is None:
            return {"held": "the origin has no UN M49 code in the country reference"}
        return mirca_season(commodity, m49, src["mirca_os"], mapped_ha)
    if "fao56" in src:
        return fao56_season(commodity, origin)
    return {"held": "the crop registry states no season source for this crop"}


def region_season(commodity: str, region: str, country: str, m49: int | None, region_ha: float | None,
                  country_ha: float | None) -> dict:
    """{months, prev_months, basis} or {held: reason} for a crop × region: MIRCA-OS units of the region by its official
    name (their calendars must cover half the crop map's area in the region, E168); a region without an official name
    (NUTS-2) takes its country's season; FAO-56 crops take their country's row."""
    from ml.features.crop_registry import crop
    from services.reference import regions
    src = crop(commodity).get("season_source") or {}
    name = regions.of_country(country).get(region)
    if "mirca_os" in src and name:
        if m49 is None:
            return {"held": "the region's country has no UN M49 code in the country reference"}
        out = mirca_season(commodity, m49, src["mirca_os"], region_ha, province=name)
        if "basis" in out:
            out["basis"] += f", units of '{name}'"
        return out
    out = season(commodity, country, m49, country_ha)
    if "basis" in out:
        out["basis"] = f"{out['basis']} — the country's season ({region} has no named units)"
    return out
