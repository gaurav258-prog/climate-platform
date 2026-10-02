"""Build data/reference/iso639.csv — the languages with an ISO 639-1 two-letter code, from the list published by the
ISO 639-2 Registration Authority (Library of Congress): alpha-3 (bibliographic / terminology), alpha-2, English name.

    venv/bin/python -m scripts.build_iso639
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import httpx

SOURCE = "https://www.loc.gov/standards/iso639-2/ISO-639-2_utf-8.txt"
OUT = Path(__file__).resolve().parents[1] / "data" / "reference" / "iso639.csv"


def main() -> None:
    r = httpx.get(SOURCE, timeout=60, follow_redirects=True)
    r.raise_for_status()
    rows = []
    for line in r.content.decode("utf-8-sig").splitlines():
        parts = line.split("|")
        if len(parts) == 5 and parts[2]:
            rows.append({"alpha2": parts[2], "alpha3_b": parts[0], "alpha3_t": parts[1] or parts[0], "name": parts[3],
                         "source": SOURCE, "retrieved": date.today().isoformat()})
    rows.sort(key=lambda x: x["alpha2"])
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} languages with an ISO 639-1 code → {OUT}")


if __name__ == "__main__":
    main()
