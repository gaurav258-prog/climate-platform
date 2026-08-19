"""Build the (stocks, shock, price move) panel to test A(s) — all on ONE consistent calendar.

WHY THE FIRST ATTEMPT ONLY FOUND 4 POINTS. We mixed datasets with different calendars:
production from FAOSTAT (calendar years), stocks from USDA PSD (marketing years), prices as
calendar-year means. A crop-year shock was being compared to a calendar-year price move, so
most candidate observations either failed to line up or landed as noise. Four survivors is not
a panel; the original A(s) came from two anchors and we are not replacing it with four.

THE FIX. Take production, consumption AND stocks all from PSD — one dataset, one marketing-year
convention, already aligned — and average prices over each commodity's ACTUAL marketing-year
window. Then every term in
    A_implied = |price move| x |elasticity| / |world supply shock|
refers to the same 12 months.

MARKETING YEARS are documented per commodity below, not tuned. Picking the window that makes
the fit look good would be p-hacking, which is how we got here in the first place.

HONEST LIMITS THAT REMAIN (a bigger panel does not dissolve them):
  * PSD publishes no world row; we sum countries and exclude aggregate rows ('European Union'
    et al.) which would double-count their own members. PSD's own world totals are built on
    LOCAL marketing years per country, so a summed 'world year' is an approximation.
  * Prices respond to EXPECTATIONS. A shock is priced when the market LEARNS of it — often
    before the production figure exists. A same-window regression cannot see that, and it is
    the single biggest reason this relationship may look weak even when it is real.
  * |elasticity| is an assumed per-commodity constant and divides straight into A_implied.
  * A(s) and crop sensitivity are confounded in the product's chain; this panel only speaks to
    A(s), the market half.

    python -m scripts.build_amplification_panel
    python -m scripts.build_amplification_panel --min-shock 0.05
"""
from __future__ import annotations

import argparse
import collections
import csv
import io
import math
import os
import sys
import urllib.request
import zipfile

from sqlalchemy import text

from core.db.session import get_session

PSD_CACHE = "data/usda_psd/psd_alldata_csv.zip"
PSD_URL = "https://apps.fas.usda.gov/psdonline/downloads/psd_alldata_csv.zip"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}

# PSD commodity -> (our price series name, marketing-year START month, |elasticity|)
# Marketing years are the documented trade conventions. Elasticities are the same assumed
# constants the engine uses (sc_commodities.demand_elasticity), carried here explicitly so the
# panel is reproducible without a DB round-trip per row.
COMMODITIES = {
    "Coffee, Green":          ("Coffee",      10, 0.28),   # Oct-Sep
    "Wheat":                  ("Durum wheat",  6, 0.25),   # Jun-May
    "Corn":                   ("Maize",        9, 0.30),   # Sep-Aug
    "Rice, Milled":           ("Rice",         8, 0.20),   # Aug-Jul
    "Oilseed, Soybean":       ("Soybean",      9, 0.30),   # Sep-Aug
    "Oil, Palm":              ("Palm oil",    10, 0.30),   # Oct-Sep
    "Sugar, Centrifugal":     ("Sugar beet",  10, 0.20),   # Oct-Sep
    "Almonds, Shelled Basis": ("Almonds",      8, 0.35),   # Aug-Jul
    "Oil, Olive":             ("Olive oil",   10, 0.20),   # Oct-Sep
}
AGGREGATE_ROWS = {"European Union", "Other", "Unaccounted"}
ATTRS = {"Production", "Domestic Consumption", "Ending Stocks"}


def _psd() -> zipfile.ZipFile:
    if not os.path.exists(PSD_CACHE):
        os.makedirs(os.path.dirname(PSD_CACHE), exist_ok=True)
        print(f"downloading {PSD_URL} …", flush=True)
        d = urllib.request.urlopen(urllib.request.Request(PSD_URL, headers=UA), timeout=600).read()
        open(PSD_CACHE, "wb").write(d)
    return zipfile.ZipFile(PSD_CACHE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-shock", type=float, default=0.03,
                    help="minimum world supply contraction to count as an event")
    args = ap.parse_args()

    # ── PSD: production / consumption / ending stocks, summed to world, per marketing year ──
    world = collections.defaultdict(lambda: collections.defaultdict(float))
    z = _psd()
    with z.open("psd_alldata.csv") as f:
        r = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig", errors="replace"))
        for row in r:
            spec = COMMODITIES.get(row["Commodity_Description"])
            if not spec or row["Country_Name"] in AGGREGATE_ROWS:
                continue
            a = row["Attribute_Description"]
            if a not in ATTRS:
                continue
            try:
                v = float(row["Value"] or 0)
            except ValueError:
                continue
            world[(spec[0], int(row["Market_Year"]))][a] += v

    # ── prices, averaged over each commodity's own marketing-year window ──
    with get_session() as s:
        px = collections.defaultdict(dict)
        for c, y, m, p in s.execute(text(
            "SELECT commodity, year, month, price FROM sc_commodity_prices "
            "WHERE source='World Bank Pink Sheet'")).fetchall():
            px[c][(y, m)] = float(p)

    def my_price(name: str, start_month: int, year: int):
        """Mean price over the marketing year beginning `start_month` of `year`."""
        vals = []
        for i in range(12):
            m = start_month + i
            y = year + (m - 1) // 12
            m = ((m - 1) % 12) + 1
            v = px[name].get((y, m))
            if v is None:
                return None
            vals.append(v)
        return sum(vals) / 12

    print(f"{'crop':11s}{'MY':>6s}{'stk%':>7s}{'shock%':>8s}{'price%':>8s}{'A_impl':>8s}")
    print("-" * 48)
    pts, rows_out = [], []
    for (name, start_m, el) in sorted(set(COMMODITIES.values())):
        years = sorted(y for (n, y) in world if n == name)
        for y in years:
            d, dprev = world.get((name, y), {}), world.get((name, y - 1), {})
            prod, prod0 = d.get("Production"), dprev.get("Production")
            cons, stk = d.get("Domestic Consumption"), d.get("Ending Stocks")
            if not (prod and prod0 and cons and stk):
                continue
            shock = (prod - prod0) / prod0
            if shock > -args.min_shock:
                continue
            p1, p0 = my_price(name, start_m, y), my_price(name, start_m, y - 1)
            if p0 is None or p1 is None:
                continue
            move = (p1 - p0) / p0
            if move <= 0:
                continue            # a contraction that did not raise price says nothing about A
            stu = stk / cons * 100
            a = move * el / abs(shock)
            pts.append((stu, a))
            rows_out.append((name, y, stu, shock * 100, move * 100, a))
            print(f"{name:11s}{y:>6d}{stu:>7.1f}{shock*100:>8.1f}{move*100:>8.1f}{a:>8.2f}")

    print(f"\n{len(pts)} observations (was 4 on the mixed-calendar panel)")
    by_crop = collections.Counter(r[0] for r in rows_out)
    print("  per crop: " + ", ".join(f"{c}:{n}" for c, n in sorted(by_crop.items())))

    if len(pts) < 8:
        print("\nSTILL TOO FEW TO FIT. A(s) stays UNVALIDATED — we do not fit a curve on a handful "
              "of points, which is exactly how the current one went wrong.")
        return 0

    xs = [math.log(34.7 / s_) for s_, _ in pts]
    ys = [math.log(a) for _, a in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    exp_hat = sxy / sxx
    r = sxy / math.sqrt(sxx * syy)
    print(f"\n  empirical exponent = {exp_hat:.2f}   (model hardcodes 3.62)")
    print(f"  correlation r      = {r:.3f}   r^2 = {r*r:.3f}")
    print(f"  => stocks explain {r*r*100:.0f}% of the variation in amplification")
    if abs(r) < 0.4:
        print("\n  VERDICT: even on a proper panel, stocks-to-use does NOT explain the price "
              "response. The curve is not merely mis-fitted — the RELATIONSHIP is not there in "
              "the data. Price is driven by what the market EXPECTS, not by measured stocks.")
    else:
        print(f"\n  VERDICT: a real relationship. Refit A(s) = (34.7/s)^{exp_hat:.2f} and re-fit "
              "every crop sensitivity that was fitted against the old curve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
