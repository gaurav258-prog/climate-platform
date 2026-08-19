"""Calibrate NACE sector emission intensities from EXIOBASE 3 (open, Zenodo).

Emissions are estimated (when undisclosed) as sector-average carbon intensity ×
revenue. This script computes those intensities from real EXIOBASE data and writes
the provenanced data file data/reference/nace_emission_intensity.csv.

Method (output-weighted, so tiny-output sectors don't distort a division):
  1. From EXIOBASE 3 IOT_<year>_ixi (industry-by-industry), read impacts/S.txt
     (GHG GWP100 intensity, kg CO2eq per M.EUR output) and x.txt (industry output).
  2. For each EU region × EXIOBASE sector: emissions = S_ghg × output.
  3. Concord EXIOBASE's 163 industries to NACE rev.2 divisions.
  4. NACE intensity = Σ emissions ÷ Σ output over EU regions  (tCO2e per €M).

Only the two needed matrices (~23 MB) are pulled from the 755 MB archive via HTTP
range requests (remotezip) — no full download. Requires: pip install remotezip.

    python -m scripts.build_nace_intensities                 # download + compute
    python -m scripts.build_nace_intensities --local-dir DIR # use a pre-extracted EXIOBASE folder
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

YEAR = 2022
ZENODO_URL = f"https://zenodo.org/api/records/5589597/files/IOT_{YEAR}_ixi.zip/content"
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "nace_emission_intensity.csv"
GHG_ROW_PREFIX = "GHG emissions (GWP100)"

EU_REGIONS = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
              "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
              "SI", "ES", "SE"}


def _nace_division(sector: str) -> str | None:
    """Concord an EXIOBASE industry name to a NACE rev.2 division (2 digits)."""
    s = sector.lower()
    def has(*ks): return any(k in s for k in ks)
    if has("cultivation", "farming", "raw milk", "wool", "animal products", "manure", "meat animals"):
        return "01"
    if has("forestry"): return "02"
    if has("fishing"): return "03"
    if has("coal and lignite", "peat"): return "05"
    if has("crude petroleum", "natural gas extraction", "gaseous materials"): return "06"
    if has("mining of", "uranium and thorium"): return "07"   # metal ores
    if has("quarrying", "chemical and fertilizer minerals", "salt"): return "08"
    if has("beverages"): return "11"
    if has("tobacco"): return "12"
    if has("processing", "sugar refining", "processed rice", "manufacture of fish",
           "vegetable oils", "meat products"):
        return "10"                                            # food
    if has("textiles"): return "13"
    if has("wearing apparel"): return "14"
    if has("leather"): return "15"
    if has("wood"): return "16"
    if has("pulp", "paper"): return "17"
    if has("publishing, printing"): return "18"
    if has("coke oven", "petroleum refinery", "nuclear fuel"): return "19"
    if has("plastics, basic", "fertiliser", "chemicals nec"): return "20"
    if has("rubber and plastic products"): return "22"
    if has("glass", "ceramic", "bricks", "cement", "clinker", "non-metallic mineral"): return "23"
    if has("iron and steel", "precious metals production", "aluminium production",
           "zinc and tin production", "copper production", "non-ferrous metal production",
           "casting of metals"): return "24"
    if has("fabricated metal"): return "25"
    if has("office machinery", "computers", "radio, television", "medical, precision"): return "26"
    if has("electrical machinery"): return "27"
    if has("machinery and equipment n.e.c"): return "28"
    if has("motor vehicles"): return "29"
    if has("other transport equipment"): return "30"
    if has("furniture"): return "31"
    if has("electricity", "manufacture of gas", "steam and hot water"): return "35"
    if has("distribution of water"): return "36"
    if has("waste water treatment"): return "37"
    if has("incineration", "landfill", "biogasification", "composting", "recycling of waste", "bottles by direct reuse"):
        return "38"
    if has("construction"): return "41"
    if has("sale, maintenance, repair of motor"): return "45"
    if has("wholesale trade"): return "46"
    if has("retail trade", "retail sale of automotive"): return "47"
    if has("hotels and restaurants"): return "55"
    if has("railways", "other land transport", "pipelines"): return "49"
    if has("water transport"): return "50"
    if has("air transport"): return "51"
    if has("supporting and auxiliary transport"): return "52"
    if has("post and telecommunications"): return "61"
    if has("financial intermediation"): return "64"
    if has("insurance and pension"): return "65"
    if has("auxiliary to financial"): return "66"
    if has("real estate"): return "68"
    if has("renting of machinery"): return "77"
    if has("computer and related"): return "62"
    if has("research and development"): return "72"
    if has("other business activities"): return "70"
    if has("public administration"): return "84"
    if has("education"): return "85"
    if has("health and social"): return "86"
    if has("membership organisation"): return "94"
    if has("recreational, cultural"): return "93"
    if has("other service activities"): return "96"
    return None


def _extract(local_dir: Path | None) -> tuple[Path, Path]:
    if local_dir:
        return local_dir / "impacts" / "S.txt", local_dir / "x.txt"
    from remotezip import RemoteZip
    dest = Path("/tmp") / f"exiobase_{YEAR}"
    dest.mkdir(parents=True, exist_ok=True)
    with RemoteZip(ZENODO_URL) as z:
        for m in (f"IOT_{YEAR}_ixi/impacts/S.txt", f"IOT_{YEAR}_ixi/x.txt"):
            z.extract(m, dest)
    return dest / f"IOT_{YEAR}_ixi" / "impacts" / "S.txt", dest / f"IOT_{YEAR}_ixi" / "x.txt"


def build(local_dir: Path | None = None) -> int:
    s_path, x_path = _extract(local_dir)

    # output per (region, sector)
    output: dict[tuple[str, str], float] = {}
    with open(x_path, newline="", encoding="utf-8") as fh:
        rd = csv.reader(fh, delimiter="\t"); next(rd)
        for reg, sec, val in rd:
            output[(reg, sec)] = float(val or 0)

    # GHG intensity row (kg CO2eq / M.EUR) per (region, sector) column
    with open(s_path, newline="", encoding="utf-8") as fh:
        rd = csv.reader(fh, delimiter="\t")
        regions = next(rd)[1:]
        sectors = next(rd)[1:]
        ghg = next(r[1:] for r in rd if r[0].startswith(GHG_ROW_PREFIX))

    emis, out = defaultdict(float), defaultdict(float)
    unmapped = set()
    for reg, sec, s_val in zip(regions, sectors, ghg):
        if reg not in EU_REGIONS:
            continue
        nace = _nace_division(sec)
        if nace is None:
            unmapped.add(sec); continue
        x = output.get((reg, sec), 0.0)
        if x <= 0:
            continue
        emis[nace] += float(s_val or 0) * x   # kg CO2eq
        out[nace] += x                         # M.EUR

    rows = []
    for nace in sorted(out):
        if out[nace] <= 0:
            continue
        intensity = (emis[nace] / 1000.0) / out[nace]  # kg→t, per M.EUR
        rows.append((nace, round(intensity, 1)))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["nace_division", "intensity_tco2e_per_meur", "scope", "source"])
        for nace, intensity in rows:
            w.writerow([nace, intensity, "scope1_2",
                        f"EXIOBASE 3 IOT_{YEAR}_ixi (impacts/S GWP100, EU-region output-weighted)"])
    print(f"wrote {len(rows)} NACE divisions → {OUT}")
    if unmapped:
        print(f"note: {len(unmapped)} EXIOBASE sectors unmapped (e.g. {sorted(unmapped)[:3]})")
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--local-dir", type=Path, default=None,
                    help="a pre-extracted EXIOBASE IOT_<year>_ixi folder (skips download)")
    args = ap.parse_args()
    build(args.local_dir)


if __name__ == "__main__":
    main()
