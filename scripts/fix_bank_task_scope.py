"""Rewrite the demo bank's out-of-scope prudential (COREP) workflow tasks into in-scope climate-reporting
tasks. Tellumen files climate/physical-risk disclosures (TCFD · EU-Taxonomy Art.8 · PCAF), NOT prudential
COREP returns, so the demo Kanban should not show Credit-Risk SA/A-IRB, Market-Risk templates, C 04.00
Memorandum items or CR-KRI tasks. This maps each flagged task to a climate-reporting equivalent in place,
preserving its column, position and history. Idempotent: it only touches rows whose title still matches the
old prudential wording.
"""
from __future__ import annotations

from sqlalchemy import text

from core.db.session import SessionLocal

# old (prudential) title  ->  (new title, new description) in-scope for a climate disclosure
REWRITES = {
    "Finalise COREP validation exceptions": (
        "Resolve open validation exceptions on the TCFD / EU-Taxonomy filing",
        "Clear the blocking validation findings on the climate disclosure before it goes for approval.",
    ),
    "Import Source Data File — Market Risk templates": (
        "Import loan-book exposure file (counterparty, NACE, collateral location)",
        "Load the exposure book that the physical-risk scoring and EU-Taxonomy eligibility run against.",
    ),
    "Perform manual adjustments on Template C 04.00 — Memorandum items": (
        "Assign EU-Taxonomy eligibility flags to exposures",
        "Tag exposures for EU-Taxonomy Article 8 eligibility to complete the Green Asset Ratio inputs.",
    ),
    "Import Source Data File — Credit Risk (SA / A-IRB / F-IRB)": (
        "Compile PCAF financed-emissions inputs (issuer Scope 1–3)",
        "Gather issuer emissions and attribution data for the PCAF financed-emissions disclosure.",
    ),
    "Analyze evolution of CR KRIs between current and previous report": (
        "Review physical-risk scoring coverage — unscored exposures",
        "Check the assets excluded from exposure for missing data before the coverage is disclosed.",
    ),
}


def run() -> None:
    s = SessionLocal()
    try:
        n = 0
        for old, (new_title, new_desc) in REWRITES.items():
            res = s.execute(text("""
                UPDATE regulatory_task SET title = :nt, description = :nd
                WHERE title = :ot
                  AND org_id IN (SELECT org_id FROM organizations WHERE type IN ('bank','insurer','asset_manager','reit'))
            """), {"nt": new_title, "nd": new_desc, "ot": old})
            if res.rowcount:
                print(f"  rewrote {res.rowcount}× · {old!r} -> {new_title!r}")
                n += res.rowcount
        s.commit()
        print(f"done · {n} task(s) rescoped" if n else "nothing to rewrite (already in scope)")
    finally:
        s.close()


if __name__ == "__main__":
    run()
