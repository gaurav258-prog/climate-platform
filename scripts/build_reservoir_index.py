"""Compress the MITECO reservoir MDB into a compact per-basin monthly fill index.

The raw BD-Embalses.mdb (213MB, weekly readings 1988-2026 for every Spanish reservoir >5hm3) is
NOT committed. This distils it to data/reservoirs/basin_reservoir_index.csv — for each hydrographic
demarcation (AMBITO) and each year-month, the demarcation-wide FILL RATIO = sum(current water) /
sum(total capacity), 0..1. That ratio is the physical irrigation buffer a crop draws on: full
reservoirs in early summer mean water is there; depleted reservoirs mean restrictions. Spanish
decimals use a comma; FECHA is MM/DD/YY. Reads embalses_iso.csv (mdb-export of the one table).
"""
from __future__ import annotations
import csv, sys
from collections import defaultdict

SRC = "data/reservoirs/embalses.csv"
OUT = "data/reservoirs/basin_reservoir_index.csv"


def _num(s):
    s = (s or "").strip().strip('"').replace(".", "").replace(",", ".")  # es: '1.234,56' -> '1234.56'
    try:
        return float(s)
    except ValueError:
        return None


def main() -> int:
    # (basin, year, month) -> [sum_actual, sum_total]
    agg = defaultdict(lambda: [0.0, 0.0])
    n = 0
    with open(SRC, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            tot, act = _num(r["AGUA_TOTAL"]), _num(r["AGUA_ACTUAL"])
            if tot is None or act is None or tot <= 0:
                continue
            d = r["FECHA"].strip().strip('"').split()[0]  # MM/DD/YY
            try:
                mm, _dd, yy = d.split("/")
            except ValueError:
                continue
            month = int(mm)
            year = int(yy)
            year += 1900 if year >= 80 else 2000
            k = (r["AMBITO_NOMBRE"], year, month)
            agg[k][0] += act
            agg[k][1] += tot
            n += 1
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["basin", "year", "month", "fill_ratio", "stored_hm3", "capacity_hm3"])
        for (basin, year, month), (act, tot) in sorted(agg.items()):
            w.writerow([basin, year, month, round(act / tot, 4), round(act, 1), round(tot, 1)])
    print(f"read {n} rows -> {len(agg)} basin-months -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
