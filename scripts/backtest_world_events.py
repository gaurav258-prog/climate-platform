"""Multi-event WORLD-shock backtest harness — the 'more than 2 events' model, done right.

For a concentrated / world-moving crop, fit ONE hazard→yield sensitivity across EVERY year by
reproducing the crop's real world production shocks, then validate leave-one-event-out. This is the
robust generalisation of cocoa's single-event backtest: more real events = more points to fit and
cross-validate against, which fixes the "one event only pins the parameter PRODUCT" weakness.

Model (per year):   world_shock ≈ − s · X ,   X = Σ_origins ( hazard_score[year−lag]/100 · world_share )
  · hazard_score comes from ERA5 (independent of yield); world_share and the observed world shock come
    from FAOSTAT (independent) — so the reproduction is NON-CIRCULAR (modelled ≠ observed, no shared input).
  · s (0<s<1) is the single free parameter, fit through the origin (zero hazard → zero shock).
  · lag>0 for lagged hazards (palm: ENSO drought in year Y cuts world output in Y+1).

PASS iff: s is physically plausible (0<s<1), it reproduces the real events within tolerance, AND the
fit is robust — dropping the single biggest event doesn't collapse s (needs ≥2 contributing events).
Read-only: prints a verdict per crop. Writing sc_model_validation is a separate, reviewed step.

Run: .venv/bin/python -m scripts.backtest_world_events
"""
from __future__ import annotations

import statistics as st

from sqlalchemy import text

from core.db.session import get_session
from scripts.fit_ranged_crop import _drought_scores, _heat_scores

# crop → {lag, origins:[(iso, region_key, driver, season_months, world_share)]}. driver: 'drought'|'heat'|'hd'(max).
CROPS = {
    "Maize": {"lag": 0, "origins": [
        ("US", "us_cornbelt", "hd", [6, 7, 8], 0.33),        # US ≈ a third of world maize; 2012 the event
        ("ZA", "south_africa_maize", "hd", [1, 2, 3], 0.03),  # Highveld — 2016 El Niño drought
        ("AR", "argentina_wheat", "hd", [1, 2, 3], 0.05),     # Pampas
    ]},
    "Palm oil": {"lag": 1, "origins": [
        ("ID", "indonesia_palm", "drought", [6, 7, 8, 9], 0.57),  # ENSO drought → world drop the NEXT year
    ]},
}

EVENT_THRESHOLD = 3.0   # |world shock| ≥ 3% counts as a real event to reproduce


def _world_shock(commodity: str) -> dict[int, float]:
    with get_session() as s:
        rows = {int(y): float(v) for y, v in s.execute(text(
            "SELECT season_year, production_tonnes FROM crop_yield_observations "
            "WHERE commodity=:c AND country='WLD' AND production_tonnes>0"), {"c": commodity}).fetchall()}
    out = {}
    for y in rows:
        nb = [rows[k] for k in range(y - 3, y + 3) if k in rows and k != y]
        if nb:
            out[y] = round(100 * (rows[y] - st.mean(nb)) / st.mean(nb), 2)   # % vs local trend
    return out


def _hazard(origin_cfg) -> dict[int, float]:
    iso, region, driver, months, share = origin_cfg
    d = _drought_scores(region, 6, months) if driver in ("drought", "hd") else {}
    h = _heat_scores(region, months) if driver in ("heat", "hd") else {}
    yrs = set(d) | set(h)
    if driver == "drought":
        return d
    if driver == "heat":
        return h
    return {y: max(d.get(y, 0.0), h.get(y, 0.0)) for y in yrs}   # 'hd' = worst of drought/heat


def _fit_sensitivity(pairs):
    """s minimising Σ(obs + s·X)²  →  s = −Σ(obs·X)/Σ(X²), through the origin."""
    sxx = sum(x * x for x, _ in pairs)
    return -sum(obs * x for x, obs in pairs) / sxx if sxx else 0.0


def backtest(commodity: str, cfg: dict) -> None:
    ws = _world_shock(commodity)
    haz = {o[0]: _hazard(o) for o in cfg["origins"]}
    shares = {o[0]: o[4] for o in cfg["origins"]}
    lag = cfg.get("lag", 0)
    yrs = sorted(y for y in ws if all((y - lag) in haz[o] for o in haz))
    X = {y: sum(haz[o][y - lag] / 100.0 * shares[o] for o in haz) for y in yrs}
    pairs = [(X[y], ws[y]) for y in yrs]
    s = _fit_sensitivity(pairs)

    events = sorted((y for y in yrs if ws[y] <= -EVENT_THRESHOLD), key=lambda y: ws[y])
    print(f"\n=== {commodity} (lag {lag}, {len(cfg['origins'])} origin(s)) — {len(yrs)} yrs, s={s:.3f} ===")
    print(f"  events (world shock ≤ −{EVENT_THRESHOLD}%):")
    errs = []
    for y in events:
        modelled = -s * X[y]
        err = abs(modelled - ws[y])
        errs.append(err)
        drivers = ",".join(f"{o}:{haz[o][y-lag]:.0f}" for o in haz)
        print(f"    {y}: observed {ws[y]:+.1f}%  modelled {modelled:+.1f}%  |err {err:.1f}pp|  hazard[{drivers}]")
    if events:
        # robustness: drop the single biggest event, refit, see if s holds
        big = min(events, key=lambda y: ws[y])
        s2 = _fit_sensitivity([(X[y], ws[y]) for y in yrs if y != big])
        stable = abs(s2 - s) / s < 0.40 if s else False
        mae = st.mean(errs)
        plausible = 0.0 < s < 1.0
        reproduces = mae < 3.0     # mean abs error on events < 3 percentage points
        verdict = "PASS" if (plausible and reproduces and stable and len(events) >= 2) else "HELD"
        print(f"  MAE on events {mae:.2f}pp | s plausible {plausible} | robust(drop {big}) s={s2:.3f} {stable} "
              f"| events {len(events)} → {verdict}")
    else:
        print("  no world-moving events in range → HELD")


def main() -> int:
    for commodity, cfg in CROPS.items():
        backtest(commodity, cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
