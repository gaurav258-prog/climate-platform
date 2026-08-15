"""Coffee frost-EXTENT index + the resolution-ladder validation test (defensibility record).

WHY THIS EXISTS. Coffee's 2021 drought+frost event is real and market-moving, but it does NOT
validate against yield: the seasonal-drought regression fails, and the old frost score (region
COLDEST-cell season-minimum) SATURATES near 100 almost every year, so it has no interannual
signal. This script builds the fix — a frost-EXTENT index (fraction of the coffee region whose
winter minimum dropped below a damaging threshold) — which DOES discriminate (correctly ranks the
1994 / 2021 / 2000 frosts), and then runs the honest resolution-ladder test that decided coffee's
tier. Keep it: (a) the frost-extent function is the better frost HAZARD metric, reusable to upgrade
the frost score for every asset; (b) it is the reproducible evidence behind coffee = HELD.

VERDICT (2026-08-16): frost is physically real and its yield effect is correctly signed and
strengthens with target resolution (MG state lag-1 r=-0.08 -> Sul de Minas lag-1 r=-0.23), but even
at the frost-prone mesoregion it explains only r2~0.05 — ~8x below the r2>=0.40 out-of-sample publish
gate. Coffee is HELD; exposure stays live, the euro is withheld. Municipality-level (IBGE PAM n6) is
the only untried rung, low odds given the ladder.

Run: .venv/bin/python -m scripts.analyze_coffee_frost_extent
Data: IBGE PAM (apisidra.ibge.gov.br, table 1613) sub-national yield + local ERA5 frost-hourly.
"""
from __future__ import annotations

import json
import statistics as st
import urllib.request

import h3

from ml.features.crop_cycle import decompose
from ml.features.frost import load_hourly_years, to_h3_frame

FROST_MONTHS = [5, 6, 7, 8, 9]
DAMAGE_THRESHOLD_C = 2.0            # 2m screen-height ~2C ≈ leaf-level 0C frost damage (arabica)
COFFEE_2723 = "2723"               # IBGE PAM product code: Café (em grão) Total
# Sul/Sudoeste de Minas mesoregion (SIDRA level n8, code 3110) — the frost-prone arabica heartland.
SUL_DE_MINAS = ("n8", "3110", (-23.0, -20.5, -47.0, -44.5))   # (lat_min, lat_max, lon_min, lon_max)


def _sidra(var: str, level: str, code: str) -> dict[int, float]:
    url = f"https://apisidra.ibge.gov.br/values/t/1613/{level}/{code}/v/{var}/p/all/c82/{COFFEE_2723}"
    with urllib.request.urlopen(url, timeout=60) as r:
        d = json.load(r)
    return {int(x["D3N"]): float(x["V"]) for x in d[1:]
            if x.get("V") not in (None, "...", "-", "..", "X")}


def yield_series(level: str, code: str) -> dict[int, float]:
    """Sub-national coffee yield (t/ha) = production / harvested area."""
    prod, area = _sidra("214", level, code), _sidra("216", level, code)
    return {y: prod[y] / area[y] for y in sorted(set(prod) & set(area)) if area[y] > 0}


def frost_extent(ds, year: int, bbox=None, thr: float = DAMAGE_THRESHOLD_C):
    """Fraction of region cells whose season-minimum 2m temperature fell to/below `thr`.
    The discriminating frost metric (vs the saturating region-minimum). Optional lat/lon bbox
    restricts to a sub-region so a frost-free area doesn't dilute the signal."""
    df = to_h3_frame(ds, year, FROST_MONTHS)
    if df.empty:
        return None
    if bbox:
        la = df["h3_cell"].map(lambda c: h3.cell_to_latlng(c)[0])
        lo = df["h3_cell"].map(lambda c: h3.cell_to_latlng(c)[1])
        df = df[(la >= bbox[0]) & (la <= bbox[1]) & (lo >= bbox[2]) & (lo <= bbox[3])]
    return None if len(df) == 0 else float((df["season_min_tmin_c"] <= thr).mean())


def _corr(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return cov / (sx * sy) if sx * sy else 0.0


def main() -> int:
    ds = load_hourly_years("data/era5_baseline/frost_hourly_years", "brazil_coffee")
    level, code, bbox = SUL_DE_MINAS
    yld = yield_series(level, code)
    dec = decompose({y: yld[y] * 1000 for y in yld})
    anom = {y: dec["years"][y]["climate_pct"] for y in dec["years"]
            if dec["years"][y]["trend_full_window"]}
    fx = {y: frost_extent(ds, y, bbox) for y in range(1991, 2025)}
    fx = {y: v for y, v in fx.items() if v is not None}

    print(f"Sul de Minas coffee yield: {len(yld)} yrs, mean {st.mean(yld.values()):.3f} t/ha, "
          f"biennial phi={dec.get('phi', 0):.3f}")
    print("frost-extent (<=%.0fC) worst years: %s" % (
        DAMAGE_THRESHOLD_C, [(y, round(v, 2)) for y, v in sorted(fx.items(), key=lambda k: -k[1])[:4]]))
    print("yield-anomaly vs frost extent (expect NEGATIVE — more frost -> lower yield):")
    for lag in (0, 1, 2):
        pairs = [(fx[y - lag], anom[y]) for y in sorted(anom) if (y - lag) in fx]
        r = _corr([a for a, _ in pairs], [b for _, b in pairs])
        print(f"  lag-{lag}: n={len(pairs)}  r={r:+.3f}  r2={r * r:.3f}")
    print("\nVERDICT: signal real & correctly signed but r2 ~ 0.05 << 0.40 gate -> Coffee HELD.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
