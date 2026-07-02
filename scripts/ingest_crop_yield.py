"""
Ingest crop-yield ground truth (the agriculture AI layer's labels).

Two sources, in priority order per (commodity, country, season):
  1. FAOSTAT QCL API (live, authoritative) — production/area/yield. Best-effort: the
     endpoint is sometimes unreachable from restricted networks; failures are caught.
  2. A CURATED, SOURCED seed of the key cocoa/coffee anchors (ICCO / ICO figures),
     including the cocoa 2023/24 shock, so the backtest has real labels even offline.

Writes crop_yield_observations and derives yoy_change_pct within each (commodity,country)
series. Idempotent (UNIQUE key upsert). Run: .venv/bin/python scripts/ingest_crop_yield.py
"""
import json
import urllib.request

from sqlalchemy import text

from core.db.session import get_session

# ── FAOSTAT QCL (live, best-effort) ──────────────────────────────────────────
# area codes (FAO): Ghana 81, Côte d'Ivoire 107, Nigeria 159, Cameroon 32, Brazil 21.
# item codes: cocoa beans 661, coffee green 656.  element: production 5510 (t).
FAOSTAT = "https://fenixservices.fao.org/faostat/api/v1/en/data/QCL"
FAO_AREAS = {"81": "GH", "107": "CI", "159": "NG", "32": "CM", "21": "BR"}
FAO_ITEMS = {"661": "cocoa", "656": "coffee_green"}


def fetch_faostat(years="2015:2024", timeout=25):
    """Return list of (commodity, iso2, season_year, production_tonnes, source) or []."""
    out = []
    ua = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    q = (f"{FAOSTAT}?area={','.join(FAO_AREAS)}&item={','.join(FAO_ITEMS)}"
         f"&element=5510&year={years}&output_type=objects")
    try:
        d = json.load(urllib.request.urlopen(urllib.request.Request(q, headers=ua), timeout=timeout))
        for r in d.get("data", []):
            iso = FAO_AREAS.get(str(r.get("Area Code")))
            com = FAO_ITEMS.get(str(r.get("Item Code")))
            if not iso or not com or r.get("Value") in (None, ""):
                continue
            out.append((com, iso, int(r["Year"]), float(r["Value"]), "FAOSTAT QCL"))
        print(f"  FAOSTAT: {len(out)} rows")
    except Exception as e:
        print(f"  FAOSTAT unavailable ({type(e).__name__}) — using curated seed only")
    return out


# ── Curated seed (published anchors; verify vs FAOSTAT when reachable) ────────
# production in TONNES, season_year = crop-year end. Sources in the `source` string.
# The cocoa 2023/24 collapse is the flagship backtest target.
CURATED = [
    # World cocoa (ICCO bulletins). 2023/24 = 4.368 Mt, −12.9% YoY.
    ("cocoa", "WLD", 2022, 4_820_000, "ICCO", "2021/22"),
    ("cocoa", "WLD", 2023, 5_010_000, "ICCO", "2022/23"),
    ("cocoa", "WLD", 2024, 4_368_000, "ICCO Nov-2025 bulletin", "2023/24 — −12.9% YoY, 45-yr-low stocks"),
    ("cocoa", "WLD", 2025, 4_840_000, "ICCO 2024/25 est.", "2024/25 rebound / surplus returns"),
    # Côte d'Ivoire (≈40% of world). 2022/23 ≈ 2.3 Mt; 2023/24 ≈ −24%.
    ("cocoa", "CI", 2022, 2_200_000, "ICCO/USDA FAS", "2021/22"),
    ("cocoa", "CI", 2023, 2_300_000, "ICCO/USDA FAS", "2022/23"),
    ("cocoa", "CI", 2024, 1_750_000, "USDA FAS / press", "2023/24 — ≈−24%"),
    # Ghana. 2023/24 ≈ 40% below the 820kt target ≈ 0.5 Mt.
    ("cocoa", "GH", 2022, 690_000, "COCOBOD/USDA FAS", "2021/22"),
    ("cocoa", "GH", 2023, 680_000, "COCOBOD/USDA FAS", "2022/23"),
    ("cocoa", "GH", 2024, 500_000, "COCOBOD/press", "2023/24 — ≈40% below target"),
    # Brazil coffee (all, ~60kg bags→tonnes). 2021 drought, Jul-2021 frost hit 2022 crop.
    ("coffee_green", "BR", 2020, 3_780_000, "ICO/USDA approx", "on-year"),
    ("coffee_green", "BR", 2021, 3_300_000, "ICO/USDA approx", "drought"),
    ("coffee_green", "BR", 2022, 3_020_000, "ICO/USDA approx", "post-frost off-year"),
]


def main():
    live = fetch_faostat()
    rows = [(c, iso, yr, prod, src, None) for (c, iso, yr, prod, src) in live] + \
           [(c, iso, yr, prod, src, note) for (c, iso, yr, prod, src, note) in CURATED]

    with get_session() as s:
        for com, iso, yr, prod, src, note in rows:
            s.execute(text("""
                INSERT INTO crop_yield_observations (commodity, country, season_year, production_tonnes, source, note)
                VALUES (:c,:i,:y,:p,:s,:n)
                ON CONFLICT (commodity, country, season_year, source)
                DO UPDATE SET production_tonnes=EXCLUDED.production_tonnes, note=EXCLUDED.note, ingested_at=now()
            """), {"c": com, "i": iso, "y": yr, "p": prod, "s": src, "n": note})

        # derive YoY change within each (commodity, country) series (prefer FAOSTAT, else any)
        s.execute(text("""
            WITH ordered AS (
                SELECT obs_id, commodity, country, season_year, production_tonnes,
                       LAG(production_tonnes) OVER (PARTITION BY commodity, country ORDER BY season_year) AS prev
                FROM crop_yield_observations
            )
            UPDATE crop_yield_observations t
            SET yoy_change_pct = round((100.0 * (o.production_tonnes - o.prev) / NULLIF(o.prev,0))::numeric, 1)
            FROM ordered o WHERE o.obs_id = t.obs_id AND o.prev IS NOT NULL
        """))

        n = s.execute(text("SELECT count(*) FROM crop_yield_observations")).scalar()
        print(f"seeded crop_yield_observations: {n} rows ({len(CURATED)} curated + {len(live)} FAOSTAT)")
        print("  flagship label — world cocoa YoY:")
        for r in s.execute(text("""
            SELECT season_year, production_tonnes, yoy_change_pct
            FROM crop_yield_observations WHERE commodity='cocoa' AND country='WLD' ORDER BY season_year
        """)).mappings().all():
            yoy = f"{float(r['yoy_change_pct']):+.1f}%" if r['yoy_change_pct'] is not None else "  —"
            print(f"    {r['season_year']}  {float(r['production_tonnes'])/1e6:.3f} Mt   YoY {yoy}")


if __name__ == "__main__":
    main()
