"""Test A(s) — the price-amplification curve — against the real price/stocks/production panel.

WHAT A(s) IS AND WHY IT MATTERS MOST. The chain is
    price_move = A(stocks_to_use) x world_supply_shock / |elasticity|
A(s) is the term that decides whether a 9% crop loss moves price 20% or 200%. It is the most
leveraged parameter in the product, and it multiplies every euro we publish.

WHAT IT WAS. A(s) = (34.7/s)^3.62, capped [0.3, 6.0] — a curve fitted through exactly TWO
points, and flagged in the code as "a DIRECTION, not a calibrated curve":
    cocoa 2023/24 : stocks 26.4% -> A 2.69   (ICCO, hand-entered)
    coffee 2021   : stocks 40%   -> A 0.60   (hand-entered)
We proved on 2026-07-16 that coffee's real 2021 stocks-to-use was 14.2% (USDA PSD), not 40%.
So one of the two anchors is fabricated and the curve's SHAPE rests on it.

WHAT THIS SCRIPT DOES. Now that prices (World Bank Pink Sheet), stocks (USDA PSD) and world
production (FAOSTAT) are all ingested, invert the chain on every crop-year with a real supply
contraction and a real price response:
    A_implied = |price move| x |elasticity| / |world supply shock|
and regress log A_implied on log(34.7/s) to recover the exponent empirically.

RESULT (2026-07-16, 15 usable crop-years): empirical exponent 0.24 vs the hardcoded 3.62,
correlation r = 0.178. At low stocks the curve returns its 6.0 cap where the data implies
0.10-1.69. The curve is not supported.

HONEST LIMITS OF THIS TEST — it is evidence the curve is wrong, not yet a replacement:
  * Coverage is thin and coffee-dominated: only crops with price AND stocks AND world
    production overlap qualify, and PSD's pre-2000 coffee stocks (implying 100%+ stocks-to-use)
    look like a different stock definition and are almost certainly not comparable.
  * CONVENTION MISMATCH: prices here are calendar-year means while supply shocks are FAO
    calendar years; the trade runs on crop years. That noise is real and inflates scatter.
  * Prices respond to EXPECTATIONS, not realised production — a shock is often priced before
    it is measured, which a same-year regression cannot see.
  * |elasticity| is itself an assumed per-commodity constant, and it divides straight into
    A_implied, so its error lands here.
  * A and the crop sensitivity are CONFOUNDED: with one event you can fit sens GIVEN A, but
    you cannot identify them separately. Cocoa's re-fit (sens 0.1995) was fitted at A(26.4)=2.69
    and reproduces its event — but the split between "the crop is sensitive" and "the market
    amplifies" is not identified from a single event.

    python -m scripts.fit_amplification_curve
"""
from __future__ import annotations

import collections
import math
import sys

from sqlalchemy import text

from core.db.session import get_session

CURVE_K, CURVE_EXP, CAP = 34.7, 3.62, (0.3, 6.0)
MIN_SHOCK = 0.03          # need a real contraction, not noise
PLAUSIBLE_STOCKS = 120.0  # above this the stock definition is not comparable (see docstring)


def curve(s: float) -> float:
    return max(CAP[0], min(CAP[1], (CURVE_K / s) ** CURVE_EXP))


def main() -> int:
    with get_session() as s:
        el = {n: abs(float(e)) for n, e in s.execute(text(
            "SELECT name, demand_elasticity FROM sc_commodities WHERE demand_elasticity IS NOT NULL"
        )).fetchall()}
        px = collections.defaultdict(dict)
        for c, y, m, p in s.execute(text(
            "SELECT commodity, year, month, price FROM sc_commodity_prices "
            "WHERE source='World Bank Pink Sheet'")).fetchall():
            px[c][(y, m)] = float(p)
        stk = {(c, y): float(v) for c, y, v in s.execute(text(
            "SELECT commodity, market_year, stocks_to_use_pct FROM sc_commodity_stocks")).fetchall()}
        prod = collections.defaultdict(dict)
        for c, y, v in s.execute(text(
            "SELECT commodity, season_year, production_tonnes FROM crop_yield_observations "
            "WHERE country='WLD' AND source='FAOSTAT QCL bulk' AND production_tonnes>0")).fetchall():
            prod[c][int(y)] = float(v)

    def year_price(c, y):
        v = [px[c][(y, m)] for m in range(1, 13) if (y, m) in px[c]]
        return sum(v) / len(v) if len(v) == 12 else None

    print("A_implied = |price move| x |elasticity| / |world supply shock|")
    print(f"{'crop':11s}{'yr':>6s}{'stk%':>7s}{'shock%':>8s}{'price%':>8s}{'A_impl':>8s}{'A_curve':>8s}")
    print("-" * 56)
    pts = []
    for c in sorted(prod):
        if c not in el:
            continue
        for y in sorted(prod[c]):
            if (y - 1) not in prod[c] or (c, y) not in stk:
                continue
            shock = (prod[c][y] - prod[c][y - 1]) / prod[c][y - 1]
            if shock > -MIN_SHOCK:
                continue
            p0, p1 = year_price(c, y - 1), year_price(c, y)
            if p0 is None or p1 is None:
                continue
            move = (p1 - p0) / p0
            if move <= 0:
                continue
            s_ = stk[(c, y)]
            if s_ > PLAUSIBLE_STOCKS:
                continue
            a = move * el[c] / abs(shock)
            pts.append((s_, a))
            print(f"{c:11s}{y:>6d}{s_:>7.1f}{shock*100:>8.1f}{move*100:>8.1f}{a:>8.2f}{curve(s_):>8.2f}")

    print(f"\n{len(pts)} usable observations (stocks <= {PLAUSIBLE_STOCKS:.0f}%)")
    # A curve fitted on a handful of points is exactly the sin we are trying to correct: the
    # original A(s) came from TWO anchors, one of which turned out to be fabricated. We do not
    # replace it with a four-point fit and call that progress.
    MIN_FIT = 8
    if len(pts) < MIN_FIT:
        print(f"NOT ENOUGH DATA TO FIT ({len(pts)} < {MIN_FIT}). The curve stays UNVALIDATED — "
              "which is the finding. Replacing a 2-point curve with a 4-point curve would be "
              "the same mistake wearing a lab coat.")

    xs = [math.log(CURVE_K / s_) for s_, _ in pts]
    ys = [math.log(a) for _, a in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    exp_hat = sxy / sxx if sxx else float("nan")
    r = sxy / math.sqrt(sxx * syy) if sxx and syy else float("nan")
    print(f"  empirical exponent = {exp_hat:.2f}   (the model hardcodes {CURVE_EXP})")
    print(f"  correlation r      = {r:.3f}")
    print()
    if abs(r) < 0.4:
        print("VERDICT: the panel shows no usable stocks -> amplification relationship. The "
              "hardcoded curve is NOT supported by the data. See the module docstring for what "
              "this test can and cannot conclude — it is evidence the curve is wrong, not yet a "
              "replacement for it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
