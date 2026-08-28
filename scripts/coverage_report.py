"""Print the coverage report — standing pre-scored layer + on-demand global reach.

    python -m scripts.coverage_report
"""
from __future__ import annotations

from core.db.session import get_session
from services.intelligence.coverage import coverage_report


def main() -> int:
    with get_session() as s:
        rep = coverage_report(s)
    st = rep["standing"]
    print("\nCoverage report")
    print("-" * 60)
    print(f"  Standing layer   : {st['n_hazards']} hazards · up to {st['n_cells_max_hazard']:,} cells "
          f"· H3 res {st['resolutions']}")
    print(f"  Scenarios/horizons: {len(st['scenarios'])} × {len(st['horizons'])}")
    print("  Per hazard:")
    for h in st["per_hazard"]:
        flag = "  ← thin" if h["cells"] < 1000 else ""
        print(f"     {h['hazard']:<15} {h['cells']:>8,} cells{flag}")
    od = rep["on_demand"]
    print(f"  On-demand        : {od['hazards_on_demand']} hazards, any address, global — {od['note']}")
    if st["thin_layers"]:
        print(f"  Deepen (thin)    : {', '.join(st['thin_layers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
