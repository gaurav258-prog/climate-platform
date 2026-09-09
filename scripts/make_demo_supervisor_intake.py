"""Demo material for the Tier-2 lens: what a banking supervisor would hold about Meridian WITHOUT Meridian using
Tellumen — (1) an AnaCredit-style loan-level extract with the collateral REGION (NUTS-3 / postcode, no coordinates)
and (2) the Pillar 3 Template 5 the bank submitted (country × NACE section cells) — derived from the demo bank's
own book so the lens has something real to compare. Writes data/acceptance/demo_supervisor/*.csv.
Usage: PYTHONPATH=. .venv/bin/python scripts/make_demo_supervisor_intake.py
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

from core.db.session import get_session
from services.geo.org_assets import org_asset_points
from services.geo.regions import region_for
from services.governance.pillar3_templates import _section

MERIDIAN = "11111111-1111-4111-8111-111111111111"
OUT = Path("data/acceptance/demo_supervisor")
BANK_BASIS = ("disorderly_2c", "2030")      # the basis the bank states in its narrative (≠ the supervisor's default)


def main(period: str = "FY2025", scale: float = 1.0, sensitivity_scale: float = 1.0) -> int:
    """period/scale: a second period (e.g. FY2024 at 0.92 × gross, 0.85 × sensitive) so trend views have two points."""
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    with get_session() as s:
        pts = org_asset_points(s, MERIDIAN, "baseline", "current")
        bank_view = {p["id"]: p for p in org_asset_points(s, MERIDIAN, *BANK_BASIS)}
    # (1) AnaCredit-style extract: collateral region from the asset's true location; ~8% carry only the country
    with (OUT / "meridian_anacredit_extract.csv").open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Instrument ID", "Debtor name", "NACE", "Outstanding nominal amount", "Final maturity", "Protection country", "Protection NUTS3"])
        for i, p in enumerate(pts):
            reg = region_for(p["lat"], p["lon"]) if p.get("lat") is not None else None
            nuts = reg["key"] if reg and reg["kind"] == "nuts3" and rng.random() > 0.08 else ""
            w.writerow([f"INS-{i+1:05d}", p["name"], p.get("nace_code") or "", f"{p['value_eur']:.2f}", f"20{rng.randint(27, 40)}-06-30", (p.get("country") or "ES"), nuts])
    # (2) the bank's submitted Template 5 under ITS basis: country × NACE section, sensitive = High/Very-high headline;
    #     the bank also 'forgot' one small country (scope) — a realistic gap for the lens to sort
    from core.types import score_to_bucket
    cells: dict = {}
    for p in pts:
        b = bank_view.get(p["id"], p)
        geo, sec = (p.get("country") or "ES"), _section(p.get("nace_code") or p.get("sector"))
        if geo == "HU":
            continue
        c = cells.setdefault((geo, sec), [0.0, 0.0])
        c[0] += p["value_eur"] * scale
        if b.get("score") is not None and score_to_bucket(float(b["score"])).value in ("H", "VH"):
            c[1] += p["value_eur"] * scale * sensitivity_scale
    name = "meridian_pillar3_template5_submitted.csv" if period == "FY2025" else f"meridian_pillar3_template5_submitted_{period}.csv"
    with (OUT / name).open("w", newline="") as f:
        w = csv.writer(f); w.writerow(["Geography", "Sector", "Gross carrying amount", "of which sensitive to physical risk"])
        for (g, sec), (gross, sens) in sorted(cells.items()):
            w.writerow([g, sec, f"{gross:.2f}", f"{sens:.2f}"])
    print(f"wrote {OUT}: {len(pts)} loan rows, {len(cells)} template cells; bank basis {BANK_BASIS}")
    return 0


if __name__ == "__main__":
    import sys
    args = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    raise SystemExit(main(args.get("period", "FY2025"), float(args.get("scale", 1.0)), float(args.get("sensitivity_scale", 1.0))))
