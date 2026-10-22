"""Fetch the IPCC AR6 assessed global warming the platform's one timeline reads (the product owner's approval of
2026-10-22): IPCC AR6 WG1 Summary for Policymakers, data for Figure SPM.8 (v20210809), panel (a) — global surface air
temperature change per pathway, with its very likely range — and the record's readme and licence. CEDA,
doi:10.5285/98af2184e13e4b91893ab72f301790db, CC-BY 4.0.

Exactly these files, each checked against the size the archive lists; one that differs is refused and removed. They
are small and openly licensed, so they are kept as committed reference data (data/reference/climate/sources/ar6_spm8,
attribution in data/reference/climate/warming_axis.json), each with its SHA-256 — the axis refuses a file that differs.

    venv/bin/python -m scripts.fetch_ar6_gsat
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.download import download

BASE = "https://dap.ceda.ac.uk/badc/ar6_wg1/data/spm/spm_08/v20210809/"
FILES = {"panel_a/tas_global_Historical.csv": 2330, "panel_a/tas_global_SSP1_1_9.csv": 6137,
         "panel_a/tas_global_SSP1_2_6.csv": 6137, "panel_a/tas_global_SSP2_4_5.csv": 6137,
         "panel_a/tas_global_SSP3_7_0.csv": 6137, "panel_a/tas_global_SSP5_8_5.csv": 6137,
         "00README_catalogue_and_licence.txt": 854, "License.txt": 1038, "Readme_for_figure_SPM8.txt": 15618}
OUT = Path(__file__).resolve().parents[1] / "data" / "reference" / "climate" / "sources" / "ar6_spm8"


def main() -> int:
    got, failed = {}, []
    for rel, size in FILES.items():
        out = OUT / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        status = download(BASE + rel, out, size)
        if status.startswith("failed"):
            failed.append(rel)
            got[rel] = status
            continue
        got[rel] = {"status": status, "bytes": size, "sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
        print(f"  {rel}: {status}")
    (OUT / "provenance.json").write_text(json.dumps({
        "dataset": "IPCC AR6 WG1 SPM Figure SPM.8 data (v20210809), panel (a)", "archive": "CEDA",
        "doi": "10.5285/98af2184e13e4b91893ab72f301790db", "licence": "CC-BY 4.0", "base_url": BASE,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": got}, indent=1))
    print({"fetched": len(FILES) - len(failed), "failed": failed})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
