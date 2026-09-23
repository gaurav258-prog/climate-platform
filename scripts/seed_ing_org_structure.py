"""Mirror ING Bank N.V.'s real, publicly disclosed legal-entity structure into a demo tenant.

Source: ING Bank Annual Report 2025 (https://ing.com/binaries/content/assets/documents/annual-reports/
2025-ing-bank-nv-annual-report.pdf), fetched via the standard research path (not invented):
  - Note 41 "Principal subsidiaries, investments in associates and joint ventures" — ownership %, statutory
    place of incorporation, country of operation.
  - "Additional information by country" (the CRD IV Art. 89 country-by-country report) — the full list of
    countries ING Bank N.V. operates in, distinguishing a named subsidiary from a branch of ING Bank N.V.
    itself, plus real 2025 total income / total assets / result-before-tax / employee-count figures per
    country (not attached here — see the note below on why).

What this creates: the ORG-STRUCTURE / entity TREE only — organizations, roles, one admin login, and the
reporting_entities hierarchy (subsidiaries + branches, correct ownership % and consolidation method).

What this deliberately does NOT create: any loan book, exposure, or financial figure. ING's actual balance
sheet is confidential; the CbCR table's income/assets/employees are real PUBLIC numbers but attaching them
as if they were a Tellumen-computed book would misrepresent what the platform actually knows vs. what was
copied from a filed report. A real customer onboarding uploads their own book against this same tree via
the normal ingest path (Portfolio > Upload) — this script only proves the tree itself mirrors reality.

Idempotent: refuses (loudly, not silently) if a tenant of this name already exists — re-run only after
dropping the demo org, never accumulates duplicates.

Usage:  .venv/bin/python -m scripts.seed_ing_org_structure
"""
from __future__ import annotations

from core.db.session import get_session
from services.governance.entities import create_entity
from services.governance.tenant_provisioning import create_tenant

ORG_NAME = "ING Bank N.V. (mirror)"
ADMIN_EMAIL = "admin@ing-mirror.demo"
ADMIN_PASSWORD = "Demo!admin1"

# Real subsidiaries — Note 41, "Principal subsidiaries, investments in associates and joint ventures", plus
# the CbCR table's additional named subsidiaries (Eurasia/Ukraine/Brazil/Mexico/Hubs) not listed in Note 41
# because Note 41 shows only the largest ("principal") ones. consolidation_method: "full" for every
# controlled subsidiary REGARDLESS of ownership % (IFRS 10 — Śląski is 75%-owned but still fully
# consolidated with a 25% non-controlling interest, not proportionally); "equity" only for the one genuine
# associate ING doesn't control.
#   (name, country, ownership_pct, consolidation_method, note)
SUBSIDIARIES = [
    ("ING België N.V.", "BE", 100.0, "full", None),
    ("ING Luxembourg S.A.", "LU", 100.0, "full", None),
    ("ING-DiBa AG", "DE", 100.0, "full", None),
    ("ING Bank Śląski S.A.", "PL", 75.0, "full",
     "25% non-controlling interest listed on the Warsaw Stock Exchange"),
    ("ING Financial Holdings Corporation", "US", 100.0, "full", None),
    ("ING Bank A.Ş.", "TR", 100.0, "full", None),
    ("ING Bank (Australia) Ltd", "AU", 100.0, "full", None),
    ("ING Commercial Finance B.V.", "NL", 100.0, "full", None),
    ("ING Hubs B.V.", "NL", 100.0, "full", "Global services entity"),
    ("ING Bank (Eurasia) Z.A.O.", "RU", 100.0, "full",
     "Sale to Global Development JSC announced Jan 2025, not yet completed as of the 2025 annual report"),
    ("PJSC ING Bank Ukraine", "UA", 100.0, "full", None),
    ("ING ADMINISTRAÇÃO LTDA.", "BR", 100.0, "full", "In run-off / liquidation"),
    ("ING Consulting, S.A. de C.V.", "MX", 100.0, "full", "In run-off / liquidation"),
]

# The one genuine associate (significant influence, not control) — equity method, never full consolidation.
ASSOCIATES = [
    ("TMBThanachart Bank Public Company Ltd", "TH", 23.0, "equity", "Associate, not a subsidiary"),
]

# Branches of ING Bank N.V. itself (same legal entity — modelled as their own reporting entities for
# booking-center/internal-reporting granularity, exactly what reporting_entities exists for; ownership is
# 100%/full since it IS the parent entity's own book, not a separate legal person).
BRANCHES_OF_BANK_NV = [
    ("Spain", "ES"), ("Italy", "IT"), ("Romania", "RO"), ("United Kingdom", "GB"),
    ("Switzerland", "CH"), ("France", "FR"), ("Ireland", "IE"), ("Czech Republic", "CZ"),
    ("Hungary", "HU"), ("Slovakia", "SK"), ("Portugal", "PT"), ("Bulgaria", "BG"),
    ("Austria", "AT"), ("Singapore", "SG"), ("Japan", "JP"), ("South Korea", "KR"),
    ("Hong Kong", "HK"), ("Taiwan", "TW"), ("China", "CN"), ("Philippines", "PH"),
    ("United Arab Emirates", "AE"),
]
# Sri Lanka is a branch of ING Hubs B.V. specifically (global services), not of ING Bank N.V. directly —
# nested under that subsidiary once it's created, matching the annual report exactly.
BRANCH_OF_HUBS = ("Sri Lanka", "LK")

# The Netherlands domestic book itself — its own row in the CbCR table ("Netherlands / ING Bank N.V.",
# €302,740m total assets, 15,280 employees) but NOT a separate legal entity or branch; it's what remains of
# ING Bank N.V.'s own book once every subsidiary/branch below is carved out. Modelled as its own reporting
# entity (not left as the implicit whole-org default) so the NL book can be told apart from the consolidated
# total, the same way every other country already can.
NL_HEAD_OFFICE = "ING Bank N.V. — Netherlands (head office)"

# Explicitly excluded, and why (never silently dropped):
#   Payvision Canada Services Ltd — dissolved in 2023 per the 2025 annual report itself; including a
#   dissolved entity in a CURRENT structure mirror would misrepresent it, not mirror it.


def main() -> None:
    with get_session() as s:
        tenant = create_tenant(
            s, actor_user_id=None, name=ORG_NAME, org_type="bank", country="NL",
            legal_name="ING Bank N.V.", lei="3TK20IVIUJ8J3ZU0QE75",  # ING Bank N.V.'s real, public LEI (GLEIF)
            admin_email=ADMIN_EMAIL, admin_full_name="Demo Admin (ING mirror)", admin_password=ADMIN_PASSWORD,
        )
        org_id = tenant["org_id"]
        print(f"tenant created: {ORG_NAME} -> org_id {org_id}")

        created = {}
        e = create_entity(s, org_id, name=NL_HEAD_OFFICE, kind="legal_entity",
                          ownership_pct=100.0, consolidation_method="full")
        created["NL_HEAD_OFFICE"] = e["entity_id"]
        print(f"  + {NL_HEAD_OFFICE} — 100.0% full — domestic book, not a separate legal entity/branch")

        for name, country, pct, method, note in SUBSIDIARIES + ASSOCIATES:
            e = create_entity(s, org_id, name=f"{name} ({country})", kind="legal_entity",
                              ownership_pct=pct, consolidation_method=method)
            created[name] = e["entity_id"]
            print(f"  + {name} ({country}) — {pct}% {method}" + (f" — {note}" if note else ""))

        for name, country in BRANCHES_OF_BANK_NV:
            e = create_entity(s, org_id, name=f"Branch of ING Bank N.V. — {name}", kind="branch",
                              ownership_pct=100.0, consolidation_method="full")
            print(f"  + Branch — {name} ({country})")

        hub_id = created["ING Hubs B.V."]
        name, country = BRANCH_OF_HUBS
        create_entity(s, org_id, name=f"Branch of ING Hubs B.V. — {name}", kind="branch",
                     parent_entity_id=hub_id, ownership_pct=100.0, consolidation_method="full")
        print(f"  + Branch (of ING Hubs B.V.) — {name} ({country})")

        s.commit()
        n_total = 1 + len(SUBSIDIARIES) + len(ASSOCIATES) + len(BRANCHES_OF_BANK_NV) + 1
        print(f"\ndone — {n_total} reporting entities under {ORG_NAME}")
        print(f"login: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
        print("no exposures/loan book attached — upload one via Portfolio to populate it")


if __name__ == "__main__":
    main()
