# Supervision model — user groups, workflow, and the configuration that keeps it sector-agnostic

Agreed 2026-09-07. First customer class: **banking supervisor** (SSM / national competent authority). The same
model serves insurance, securities, real-estate and agri-food authorities by **configuration**
(`data/reference/supervision_profiles.json` + per-regulator `supervisor_settings`), never by sector-specific code.

## The supervisory cycle (mirrors the entity spine Sense → Assess → Decide → Disclose → Operate)

| # | Stage | What happens | Platform surface |
|---|---|---|---|
| 1 | Collect | filings arrive (Pillar 3 ESG, Solvency II QRT, SFDR, ESRS/XBRL, EUDR DDS) | Supervised population · intake register |
| 2 | Validate | completeness, plausibility, deadlines, taxonomy versions | Data & reporting view |
| 3 | Analyse | per entity and across the population: concentration by region / hazard / sector | Entity file · regional heat map · peer benchmark |
| 4 | Challenge | the institution's own numbers vs an independent view from the same authoritative feeds | Independent lens (next) |
| 5 | Engage | questions, information requests, site-level access on consent, findings | Requests & findings (next) |
| 6 | Report | SREP climate module inputs, thematic reviews, board dashboard | Head dashboard · exports |
| 7 | Follow up | remediation tracked to closure | Findings log (next) |

## User groups inside an authority (role templates, seeded per regulator org; RBAC rows, editable)

| Role | Stages | Needs |
|---|---|---|
| Line supervisor (JST) | 3, 5, 7 | one entity file: submissions, gaps, exposure profile, peer position, questions, site access, findings |
| Horizontal risk analyst | 3, 4, 6 | population concentration, hotspots, scenario shift, benchmark distributions, export |
| Data & reporting | 1, 2 | intake register, validation rules, plausibility flags, feedback to the entity |
| Policy & methodology | 4, 6 | methodology transparency, calibration evidence, model tiers, reproducibility |
| Inspector | 5, 7 | case file, site-level evidence (consent), evidence pack, remediation tracking |
| Head of division / board | 6 | coverage, systemic KPIs, escalations, decision trail |
| Platform admin | — | users, roles, SSO, audit, data-sharing agreements, retention |

## Hard rules (unchanged by any profile)

- The platform never holds or shows an entity's unreleased drafts.
- Site-level data is shown only while the supervised entity grants it; regional aggregates (NUTS-3 / CRESTA /
  hexagon) are the default entitlement — the unit filings use.
- Every cross-entity read is audited on the supervised entity's own log.
- Supervisory thresholds ("watch above 25 % of book at high risk") are profile defaults a regulator can
  override; they are expectations, not our judgement of the entity.

## What is configuration

| Concern | Where | Example |
|---|---|---|
| Customer class | `profiles` | `banking_supervisor` → sectors `[bank]` |
| Sector expectations | `sectors.<type>` | frameworks, regional unit, book noun, benchmark metrics + thresholds |
| Metric computation | `services/supervision/metrics.py` adapters keyed by `adapter` id, sector-agnostic (they read the cross-sector asset reader) | `portfolio.high_risk_share` |
| Roles | `roles` → seeded RBAC rows per regulator org | `risk_analyst` |
| Regulator overrides | `supervisor_settings` (DB, per org) | thresholds, default scenario/horizon, profile |

## Build order

1. Entity file + peer benchmarking (this iteration) — what a line supervisor opens every morning.
2. Independent lens: entity-reported vs platform-computed, per metric, with the delta explained.
3. Requests & findings workflow (regulator → entity, tracked to closure, both sides audited).
4. Supervisor-side intake validation and data-quality feedback.
5. Head dashboard falls out of 1 + 2.

## The independent lens — three precision tiers (built 2026-09-07: Tier 2)

| Tier | What the supervisor holds | What Tellumen computes | Precision stamped on every figure |
|---|---|---|---|
| 1 | the submitted template only | a plausibility band per cell from the regional hazard layers | regional band — a flag is a question |
| 2 | + its own granular data (AnaCredit-style: collateral NUTS-3 / postcode) | a SHADOW BOOK (`portfolio_entities`, `source='supervisor_shadow'`, `subject_org_id`) located by `services/geo/region_points` and run through the SAME portfolio engine; the template rebuilt bottom-up | region-resolved (NUTS-3); unlocated exposure shown as unverifiable |
| 3 | the entity on Tellumen, with consent | exact | point-resolved |

Intake (`/v1/supervisor/intake/{entity}/{submission|granular}` + `/validate`): column mapping to the canonical
fields the profile declares (`sectors.<type>.intake`), validate-before-save, provenance (file, sha256, who, when).
Lens (`/v1/supervisor/entity/{id}/lens`): cell by cell, the gap on "sensitive to physical risk" split into
scope · coverage (unlocated, unverifiable) · basis · scoring · unmatched — parts that add up exactly
(`services/supervision/lens.py`). If the shadow book has no scenario projections yet the basis term is declared
not separable, never a silent zero. The shadow book is the regulator's data: never visible to the entity.
