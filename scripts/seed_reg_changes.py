"""Seed the Regulatory-changes pipeline with demo entries that are IN Tellumen's scope only.

Tellumen covers physical / nature climate reporting — SFDR, TCFD/IFRS S2, EU Taxonomy (climate adaptation),
CSRD/ESRS E1·E3·E4, EUDR. Prudential frameworks (COREP/FINREP/etc.) are OUT of scope and must never appear —
this script removes any such rows and fills the six-stage pipeline with real, in-scope examples.

Idempotent: deletes out-of-scope rows, inserts each in-scope row only if its title isn't already present.

    python -m scripts.seed_reg_changes
"""
from __future__ import annotations

from sqlalchemy import text

from core.db.session import get_session

MERIDIAN = "11111111-1111-4111-8111-111111111111"

# out-of-scope frameworks that must never appear on the board
OUT_OF_SCOPE = ("COREP", "FINREP", "AnaCredit", "MREL", "Basel")

# earlier ad-hoc demo rows (in-scope but superseded by the canonical set below) — removed so the board shows
# exactly one clean, reproducible set rather than duplicates.
LEGACY_TITLES = (
    "CSRD ESRS E1 — Omnibus materiality clarifications",
    "SFDR RTS — PAI indicator formula fix (PAI 4)",
    "EU Taxonomy — new DNSH screening criteria",
)

# platform-wide (org_id NULL) — a rule change Tellumen absorbs for every tenant, one per stage
PLATFORM = [
    ("EFRAG ESRS E1 — transition-plan disclosure update", "CSRD/ESRS", "identified",
     "EFRAG guidance refines the transition-plan datapoints under ESRS E1.", "ESRS E1 §14–16",
     "Extend the E1 assembler with the new transition-plan fields.", None),
    ("SFDR RTS review — revised PAI methodology (consultation)", "SFDR", "analysis",
     "ESA consultation proposes changes to several mandatory PAI indicators.", "ESA SFDR RTS review 2026",
     "Assess impact on the PAI statement builder + voluntary-PAI catalog.", "2026-12-31"),
    ("EU Taxonomy — updated climate-adaptation DNSH criteria", "EU Taxonomy", "scheduled",
     "Revised technical screening criteria for adaptation Do-No-Significant-Harm.", "Climate Delegated Act",
     "Re-map the taxonomy-alignment + DNSH-adaptation diagnostic.", "2026-06-30"),
    ("EUDR — TRACES DDS schema update", "EUDR", "in_dev",
     "Updated Due-Diligence-Statement schema for TRACES submission.", "EUDR TRACES DDS v1.x",
     "Update the DDS assembler to the new schema.", "2026-06-30"),
    ("IFRS S2 / TCFD — scenario-analysis disclosure alignment", "TCFD / IFRS S2", "testing",
     "Align the forward scenario-analysis outputs to IFRS S2 wording.", "IFRS S2",
     "Wording + datapoint alignment in the disclosure pack.", None),
    ("CSRD ESRS E1 — PCAF financed-emissions datapoint mapping", "CSRD/ESRS", "released",
     "Financed-emissions (PCAF) datapoints mapped into the ESRS E1 pack.", "ESRS E1 / PCAF",
     "Shipped — E1 now carries the PCAF financed-emissions datapoints.", None),
]

# one tenant-owned (org-scoped) example — a client's OWN adaptation item Tellumen surfaces but the bank owns
TENANT = [
    (MERIDIAN, "Adopt updated SFDR PAI narrative templates", "SFDR", "scheduled", "tenant",
     "Refresh our SFDR narrative templates to the latest RTS wording.", "internal", "2026-09-30"),
]


def main():
    with get_session() as s:
        # 1) purge anything out of scope
        removed = 0
        for fw in OUT_OF_SCOPE:
            removed += s.execute(text("DELETE FROM regulatory_change WHERE framework ILIKE :p OR title ILIKE :p"),
                                 {"p": f"%{fw}%"}).rowcount
        for t in LEGACY_TITLES:
            removed += s.execute(text("DELETE FROM regulatory_change WHERE title = :t"), {"t": t}).rowcount
        print(f"removed {removed} out-of-scope / superseded row(s)")

        # 2) platform-wide in-scope set (insert if the title isn't already present)
        for title, fw, stage, summary, citation, impact, eff in PLATFORM:
            exists = s.execute(text("SELECT 1 FROM regulatory_change WHERE org_id IS NULL AND title = :t"), {"t": title}).first()
            if exists:
                continue
            s.execute(text("""
                INSERT INTO regulatory_change (org_id, title, framework, summary, citation, stage, owner, impact, effective_date)
                VALUES (NULL, :t, :fw, :sm, :ci, :st, 'platform', :im, :eff)
            """), {"t": title, "fw": fw, "sm": summary, "ci": citation, "st": stage, "im": impact, "eff": eff})
            print(f"  + platform [{stage}] {title}")

        # 3) tenant-owned example
        for org, title, fw, stage, owner, summary, citation, eff in TENANT:
            exists = s.execute(text("SELECT 1 FROM regulatory_change WHERE org_id = :o AND title = :t"), {"o": org, "t": title}).first()
            if exists:
                continue
            s.execute(text("""
                INSERT INTO regulatory_change (org_id, title, framework, summary, citation, stage, owner, effective_date)
                VALUES (:o, :t, :fw, :sm, :ci, :st, :ow, :eff)
            """), {"o": org, "t": title, "fw": fw, "sm": summary, "ci": citation, "st": stage, "ow": owner, "eff": eff})
            print(f"  + tenant   [{stage}] {title}")


if __name__ == "__main__":
    main()
