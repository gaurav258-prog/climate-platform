"""Build the NACE sector emission-intensity table for emissions estimation.

Emissions are estimated (when undisclosed) as sector-average carbon intensity ×
revenue. The intensities belong in a cited, versioned data file, not in code —
this script owns data/reference/nace_emission_intensity.csv.

Production source: EXIOBASE 3 (open, Zenodo). The calibration pipeline is:
  1. Download an EXIOBASE 3 MRIO year (industry-by-industry, e.g. IOT_2022_ixi)
     from https://doi.org/10.5281/zenodo.5589597 (~hundreds of MB zipped).
  2. Take the GHG stressor (CO2/GHG total emissions) per EXIOBASE sector and the
     sector gross output; intensity = emissions ÷ output (tCO2e per €M).
  3. Concord EXIOBASE's 163 sectors to NACE rev.2 divisions (2-digit) with a
     standard correspondence table, aggregating output-weighted.
  4. Write nace_division, intensity_tco2e_per_meur, scope, source, vintage.

The heavy MRIO processing is intentionally not run inline here (multi-hundred-MB
download + pymrio). Until it is, the CSV holds interim sector averages, clearly
flagged in the `source` column — never presented as EXIOBASE-final. Running this
script without EXIOBASE preserves the existing CSV and prints how to calibrate.
"""
from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "nace_emission_intensity.csv"


def main() -> None:
    if OUT.exists():
        n = sum(1 for _ in OUT.open()) - 1
        print(f"{OUT} exists with {n} divisions (interim sector averages).")
    else:
        print(f"{OUT} missing — the estimator falls back to its embedded table.")
    print("To calibrate against EXIOBASE 3: install pymrio, download an MRIO year "
          "(Zenodo 10.5281/zenodo.5589597), compute emissions ÷ output per sector, "
          "concord to NACE divisions, and overwrite the CSV. See module docstring.")


if __name__ == "__main__":
    main()
