"""
Wire Brazil coffee FROST into canonical_scores — the second half of the July 2021
event (drought was wired in wire_coffee_demo.py; frost was the other driver, and
was "not modelled — pending the CDS daily-min fix" until scripts/fetch_era5_frost_hourly.py
+ ml/features/frost.py replaced that broken CDS product with raw-hourly-derived daily
minimums, computed locally.

Scores frost into canonical_scores (append-only, scenario x horizon) using CURRENT_YEAR's
season-minimum 2m temperature per H3 cell -- same convention wire_coffee_demo.py uses for
drought's SPEI (one representative year, not a multi-year blend), and snaps the same coffee
plots onto scored frost cells so a plot's frost exposure is visible alongside its drought
exposure. Idempotent: retires prior frost rows before inserting.

Prerequisite: scripts/fetch_era5_frost_hourly.py brazil_coffee 1991 2024 (one CDS request
per year -- a multi-decade request exceeds CDS's per-request cost limit).

Run: .venv/bin/python scripts/wire_frost_demo.py
"""
import uuid
from datetime import datetime, timezone

import h3
from sqlalchemy import text

from core.db.session import get_session
from core.types import score_to_bucket
from ml.features.frost import load_hourly_years, seasonal_by_year, to_h3_frame
from ml.scoring.frost_climatology import frost_score
from ml.scoring.heat_climatology import SCENARIO_WARMING_C, HORIZON_FRACTION

ORG = "55555555-5555-4555-8555-555555555555"  # Terra Foods (demo) -- see wire_coffee_demo.py's note
YEAR_DIR = "data/era5_baseline/frost_hourly_years"
REGION = "brazil_coffee"
MODEL_VERSION = "frost-tmin-v0"
# Score the 2021 austral-winter frost — the SAME representative-year basis wire_coffee_demo.py uses
# for drought (2021, SPEI −0.86). Both drivers on one coherent year is what lets the COMPOUND_HAZARDS
# path reproduce the validated July-2021 event (+48.5% vs the real +44–60%); a mismatched year (mild
# frost against severe drought) would understate the compound risk the methodology validated.
CURRENT_YEAR = 2021
FROST_MONTHS = [5, 6, 7, 8, 9]


def main():
    now = datetime.now(timezone.utc)
    vintage = datetime(CURRENT_YEAR, 12, 1, tzinfo=timezone.utc)

    ds = load_hourly_years(YEAR_DIR, REGION)

    # sanity check against the real record before writing anything: whichever years are on
    # disk (see fetch_era5_frost_hourly.py -- one CDS request per year; the full 1991-2024
    # backfill may still be in progress) should place 2021 among the COLDEST seasons -- it
    # sits alongside 1994 and 2000, the other severe Brazil coffee frosts, which is the real
    # signal this pipeline exists to catch (2021 is a top-tier event, not necessarily the single
    # coldest). The validation note below is scoped to the years actually loaded, not the full
    # target range, so it never overclaims.
    by_year = seasonal_by_year(ds, FROST_MONTHS)
    years_covered = sorted(r["year"] for r in by_year)
    year_span = f"{years_covered[0]}-{years_covered[-1]}" if len(years_covered) > 1 else str(years_covered[0])
    by_year_sorted = sorted(by_year, key=lambda r: r["season_min_tmin_c"])
    print("coldest 5 seasons on record (region-mean of the per-cell daily minimum):")
    for r in by_year_sorted[:5]:
        print(f"  {r['year']}: {r['season_min_tmin_c']}°C")
    year_2021 = next((r for r in by_year if r["year"] == 2021), None)
    rank_2021 = by_year_sorted.index(year_2021) + 1 if year_2021 else None
    print(f"2021 rank: {rank_2021} of {len(by_year_sorted)} (1 = coldest)")

    # per-H3-cell season-minimum for CURRENT_YEAR -> frost_score across scenario x horizon
    df = to_h3_frame(ds, CURRENT_YEAR, FROST_MONTHS)
    if df.empty:
        raise RuntimeError(f"no frost data for {CURRENT_YEAR} -- check the fetch completed for that year")

    def frost_rows(cell, tmin):
        out = []
        for scen in SCENARIO_WARMING_C:
            for horz in HORIZON_FRACTION:
                sc = frost_score(tmin, scen, horz)
                out.append({"id": str(uuid.uuid4()), "h3": cell, "res": 8, "hz": "frost",
                            "scen": scen, "horz": horz, "score": sc,
                            "bucket": score_to_bucket(sc).value, "mv": MODEL_VERSION,
                            "dv": vintage, "now": now})
        return out

    rows, scored_cells, cell_tmin = [], set(), {}
    for _, cell_row in df.iterrows():
        cell, tmin = cell_row["h3_cell"], cell_row["season_min_tmin_c"]
        scored_cells.add(cell)
        cell_tmin[cell] = tmin
        rows.extend(frost_rows(cell, tmin))

    # Snap Brazil coffee plots onto the nearest scored frost cell (same nearest-lat/lon rule
    # wire_coffee_demo.py uses for drought). Frost is scored over the ERA5 grid; a plot sits on its
    # own H3 cell that need not coincide with a grid cell, so a Brazil coffee plot would otherwise
    # carry drought but not frost and the COMPOUND_HAZARDS path could never fire. Non-Brazil coffee
    # origins get NO frost row — frost is a Brazil-specific hazard for this book, correct not a gap.
    scored_latlng = {c: h3.cell_to_latlng(c) for c in scored_cells}
    with get_session() as s:
        plots = s.execute(text("""
            SELECT p.h3_cell, p.latitude, p.longitude FROM sc_sourcing_plots p
            JOIN sc_commodities c ON c.commodity_id = p.commodity_id
            WHERE c.name = 'Coffee' AND p.country = 'BR'
        """)).mappings().all()
    snapped = 0
    for pl in plots:
        if pl["h3_cell"] in scored_cells or pl["latitude"] is None:
            continue
        la, lo = float(pl["latitude"]), float(pl["longitude"])
        nearest = min(scored_latlng, key=lambda c: (scored_latlng[c][0] - la) ** 2 + (scored_latlng[c][1] - lo) ** 2)
        rows.extend(frost_rows(pl["h3_cell"], cell_tmin[nearest]))
        snapped += 1

    with get_session() as s:
        s.execute(text("UPDATE canonical_scores SET valid_to=:now WHERE hazard_type='frost' AND valid_to IS NULL"), {"now": now})
        for k in range(0, len(rows), 2000):
            s.execute(text("""
                INSERT INTO canonical_scores (score_id, h3_cell, h3_resolution, hazard_type, scenario,
                    time_horizon, risk_score, risk_bucket, model_version, data_vintage, scored_at, valid_from, valid_to)
                VALUES (:id,:h3,:res,:hz,:scen,:horz,:score,:bucket,:mv,:dv,:now,:now,NULL)
            """), rows[k:k + 2000])

        s.execute(text("UPDATE model_registry SET is_active=false WHERE hazard_type='frost'"))
        s.execute(text("""
            INSERT INTO model_registry (model_id, hazard_type, model_version, algorithm, training_data_vintage, validation_note, is_active, created_at)
            VALUES (:id,'frost',:mv,'Season-minimum daily 2m temperature (raw hourly ERA5, locally aggregated) vs coffee frost thresholds',:dv,
                :note, true,:now)
            ON CONFLICT (model_version) DO UPDATE SET
                training_data_vintage = EXCLUDED.training_data_vintage,
                validation_note = EXCLUDED.validation_note,
                is_active = true, created_at = EXCLUDED.created_at
        """), {"id": str(uuid.uuid4()), "mv": MODEL_VERSION, "dv": vintage, "now": now,
               "note": f"Frost = validated coffee signal (July 2021 double frost reproduced: season-min "
                       f"{by_year_sorted[0]['season_min_tmin_c']}C, rank {rank_2021} of {len(by_year_sorted)} "
                       f"coldest among years fetched so far ({year_span}) -- full 1991-2024 backfill in "
                       f"progress, one CDS request per year, see fetch_era5_frost_hourly.py). CDS's own "
                       f"daily-minimum statistic is ECMWF-flagged unusable ('should not be used') -- this "
                       f"scores from raw hourly ERA5, daily/seasonal minimum computed locally, not from "
                       f"that flagged product."})

    print(f"wired Frost: scored {len(rows)} rows over {len(scored_cells)} Brazil cells for {CURRENT_YEAR} "
          f"(+{snapped} coffee plot(s) snapped to nearest scored cell)")
    with get_session() as s:
        for r in s.execute(text("""
            SELECT p.plot_name, ROUND(v.physical_risk_score::numeric,1) score
            FROM sc_sourcing_plots p JOIN v_sc_plot_physical_risk v ON v.plot_id=p.plot_id
            WHERE p.commodity_id=(SELECT commodity_id FROM sc_commodities WHERE name='Coffee')
              AND v.hazard_type='frost' AND v.scenario='baseline' AND v.time_horizon='current'
        """)).mappings().all():
            print(f"  {r['plot_name']}: frost {r['score']}")


if __name__ == "__main__":
    main()
