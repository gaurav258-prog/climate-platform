"""Build the NACE Rev. 2 reference from Eurostat's official code list (SDMX codelist ESTAT/NACE_R2).

Writes data/reference/nace_rev2.csv — every section, division, group and class with its official title and parent —
the ONE place the platform learns which section a company's activity belongs to (services/reference/nace.py). Eurostat
codes carry the section letter (C, C24, C241, C2410); the file also gives the dotted form companies write (24, 24.1,
24.10). Aggregates (TOTAL, A-T, C10-C12 …) are left out. Re-run on a new NACE revision:
    python -m scripts.build_nace_reference
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import requests

URL = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/codelist/ESTAT/NACE_R2/latest?format=TSV&lang=en"
OUT = Path(__file__).resolve().parent.parent / "data" / "reference" / "nace_rev2.csv"
LEVEL = {0: "section", 2: "division", 3: "group", 4: "class"}


def build() -> int:
    rows = []
    for line in requests.get(URL, timeout=120).text.splitlines():
        code, _, label = line.partition("\t")
        m = re.fullmatch(r"([A-U])(\d{2}(\d{1,2})?)?", code.strip())
        if not m:
            continue
        sec, digits = m.group(1), m.group(2) or ""
        level = LEVEL.get(len(digits))
        if not level:
            continue
        dotted = digits[:2] + ("." + digits[2:] if len(digits) > 2 else "")
        parent = sec if len(digits) == 2 else (f"{sec}{digits[:-1]}" if digits else "")
        rows.append([code.strip(), sec, dotted, level, parent, label.strip()])
    if sum(1 for r in rows if r[3] == "section") != 21:
        raise SystemExit("expected the 21 NACE Rev. 2 sections — refusing to write")
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "section", "dotted", "level", "parent", "label"])
        w.writerows(rows)
    print(f"wrote {len(rows)} NACE Rev. 2 codes → {OUT}")
    return len(rows)


if __name__ == "__main__":
    build()
