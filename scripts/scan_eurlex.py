"""Run the live EUR-Lex (Cellar SPARQL) change scan and print a summary.

Usage: python scripts/scan_eurlex.py   (uses the app DB session). Safe to run repeatedly / on a schedule —
first run records baselines, later runs record only what moved.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db.config import SessionLocal  # noqa: E402
from services.regulatory_monitoring.eurlex_detector import scan, scan_relations  # noqa: E402


def main() -> None:
    with SessionLocal() as session:
        res = scan(session)
    print("EUR-Lex scan:")
    print(f"  checked   : {res['checked']}")
    print(f"  baselines : {res['baselines']}")
    print(f"  changed   : {res['changed']}")
    print(f"  unchanged : {res['unchanged']}")
    print(f"  errors    : {res['errors']}")
    with SessionLocal() as session:
        rel = scan_relations(session)
    print(f"  new amending / replacing acts: {rel['new_relations']}  (unreachable: {rel['errors']})")


if __name__ == "__main__":
    main()
