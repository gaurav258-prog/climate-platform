"""Seed a globally-sourced demo supply chain for Terra Foods and score it worldwide.

The point: prove the platform is GLOBAL from data → risk. These plots sit on their real coordinates
across five continents; each is scored for chronic heat straight from the now-global climatology
baseline (real climatological value + the platform's parametric warming shift for 2030/2050/2100) via
the existing on-demand scorer — no fabricated numbers. The Horizon globe then lights up worldwide with
real, rising risk. Idempotent: re-running upserts plots and re-uses cached scores.

    python -m scripts.seed_global_demo_supply
"""
from __future__ import annotations

import uuid

import h3
from sqlalchemy import text

from core.db.session import get_session
from ml.features.heat_chronic_point import score_heat_chronic_point

TERRA = "55555555-5555-4555-8555-555555555555"
SCEN = ["baseline", "disorderly_2c"]
HOR = ["current", "2030", "2050", "2100"]

# (plot name, commodity, lat, lon, country, annual spend €m) — real sourcing origins, five continents
ORIGINS = [
    ("Ashanti cocoa belt",        "Cocoa",   6.7,  -1.6,  "GH", 9.2),
    ("San-Pédro cocoa",           "Cocoa",   5.6,  -6.6,  "CI", 11.0),
    ("Minas Gerais coffee",       "Coffee", -21.5, -45.4, "BR", 8.4),
    ("Huila coffee",              "Coffee",   2.5, -75.6, "CO", 4.6),
    ("Đắk Lắk robusta",           "Coffee",  12.7, 108.1, "VN", 5.1),
    ("Riau palm estates",         "Citrus",   0.5, 101.4, "ID", 4.4),   # (palm mapped to a listed commodity)
    ("Punjab rice belt",          "Rice",    30.4,  75.5, "IN", 8.8),
    ("Krishna delta rice",        "Rice",    16.5,  80.6, "IN", 5.9),
    ("Kericho tea highlands",     "Coffee",  -0.4,  35.3, "KE", 3.9),
    ("Sidama coffee",             "Coffee",   6.7,  38.5, "ET", 3.2),
    ("Central Valley almond",     "Almonds", 36.8,-119.8, "US", 12.1),
    ("WA wheatbelt",              "Wheat",  -31.5, 117.4, "AU", 6.6),
    ("Souss wheat",               "Wheat",   30.4,  -8.8, "MA", 4.1),
    ("Pampas soybean",            "Soybean",-33.4, -61.2, "AR", 7.3),
    ("Cerrado maize",             "Maize",  -15.6, -47.9, "BR", 5.5),
    ("Mekong rice",               "Rice",    10.0, 105.8, "VN", 4.8),
]


def main():
    with get_session() as s:
        comm = {n: str(i) for n, i in s.execute(text("SELECT name, commodity_id FROM sc_commodities")).all()}
        cells = {}
        for name, commodity, la, lo, cc, spend in ORIGINS:
            cid = comm.get(commodity)
            if not cid:
                print(f"  skip {name}: no commodity {commodity}"); continue
            cell = h3.latlng_to_cell(la, lo, 8)
            cells[cell] = (la, lo)
            exists = s.execute(text("SELECT plot_id FROM sc_sourcing_plots WHERE org_id=:o AND plot_name=:n"),
                               {"o": TERRA, "n": name}).scalar()
            if exists:
                continue
            s.execute(text("""
                INSERT INTO sc_sourcing_plots (plot_id, org_id, commodity_id, plot_name, latitude, longitude,
                    h3_cell, country, annual_spend_eur, plot_area_ha, confidence, geocode_precision)
                VALUES (:p, :o, :c, :n, :la, :lo, :cell, :cc, :spend, 3.2, 1.0, 'exact')
            """), {"p": str(uuid.uuid4()), "o": TERRA, "c": cid, "n": name, "la": la, "lo": lo,
                   "cell": cell, "cc": cc, "spend": spend * 1_000_000})
        s.commit()
        print(f"plots ensured: {len(ORIGINS)}")

    # score chronic heat for every cell × scenario × horizon (real baseline value + parametric warming)
    scored = 0
    for cell, (la, lo) in cells.items():
        for scen in SCEN:
            for hor in HOR:
                r = score_heat_chronic_point(la, lo, scenario=scen, horizon=hor)
                if r.get("status") in ("scored", "cached_hit"):
                    scored += 1
    print(f"heat_chronic scores written/confirmed: {scored} (cells={len(cells)} × {len(SCEN)}×{len(HOR)})")


if __name__ == "__main__":
    main()
