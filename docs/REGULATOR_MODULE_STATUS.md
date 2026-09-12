# Regulator module — status (updated 12 September 2026)

The supervisory module is closed as a coherent, production-shaped release. Everything below the line "Built" is merged on `main`, verified end to end (bank + insurer, two runs, eight-thread load) and described version by version in `SOFTWARE_DESCRIPTION.md` (v2.55–v2.70). The "Remaining" list is what we consciously left for a later pass, so the module can be reopened without rediscovery.

## Built
- **Foundation as configuration:** supervision profiles (roles, scope assigned/population, sectors, stages, intake), one supervisory body per sector, assignments, scope with acknowledgement and site-access consent, `supervisor.*` permissions; the same engine as the regulated side (one-engine parity).
- **Population and analytics:** population with workflow stages, exposure map (NUTS-3 / H3, cells clipped to land), peer benchmark, scenario-shift analytics, trend, timeliness, anchor coverage, evidence packs (PDF + canonical JSON, hashed) and population export.
- **Independent lens (Tier 2) and plausibility band (Tier 1):** intake of the submitted template and granular extract for **banking** and **insurance** on the same canonical field ids; rebuild from the shadow book on the subject's own engine; four-part gap; cell drill-down; geography priors rebuilt daily.
- **Mandate registry:** nine mandates with curated article excerpts, EUR-Lex links, applicability criteria and tiers, deliverable/channel/due rule, versions with acknowledgement, change detection; supervisor-set deadlines with automatic follow-up; "what applies to you and why" on the entity side.
- **Engagement:** requests and findings with formal correspondence (reference numbers, legal basis, response period, signatory, hashed letter, receipt), the respondent portal for entities not on Tellumen, transmission adapters with receipts, governed remittance of case files (scoped, watermarked, expiring, revocable, logged both sides).
- **Governance layer shared with the regulated side:** board pack with named step-up attestation, reporting control register, model-risk register, auditor role and assurance share, appetite versioning, change→impact links, third-party exposure.
- **Honesty foundation:** hazard relevance registry (only intensity scales may headline; crop, susceptibility, variability and nowcast scales never), severe-convective damage anchoring, cold-wave channel.

## Closed since 10 September

Six of the seven parked items are done, built by five parallel agent passes under the honesty rules, verified end to end against the live API:

1. **Tier-2 intake specs for markets and agri-food** — asset-manager/REIT and agri-food (manufacturer) sourcing-plot templates, same canonical ids as banking/insurer. Agri-food needed a real foundation fix: agriculture has no `portfolio_entities` row by design, so the shadow book now writes to `sc_sourcing_plots` (migration `agrifood_shadow_book_20260912`), with EUDR lat/lon point-resolved ahead of region fallback. All three sectors' lenses verified live (Nordkap 59 cells, Stellar 55, Oranje 749 scored).
2. **Requests SLA metrics and an obligations calendar per authority** — time to acknowledge/respond/close and overdue ageing, computed from real timestamps (`responded_at` added, migration `requests_sla_20260912`); calendar reuses the mandate registry's deliverable/due rules. `GET /v1/supervisor/engagement/sla`, `GET /v1/supervisor/obligations/calendar`.
3. **Worker liveness** — a heartbeat daemon thread per Celery worker (`worker_heartbeat_20260912`), stale after 90 s (3× the 30 s interval); a queued transmission whose worker died now reads "worker unavailable — queued since …" instead of a bare "queued", verified by killing and restarting the live worker.
4. **Pending appetite approvals when the policy is switched off** — auto-withdrawn (not auto-applied: applying on the switch could be a silent maker=checker violation), `withdrawn_cause` on the request and in the audit log, one mechanism covering every governed action (`approvals_policy_off_20260912`).
5. **Insurer-specific plausibility prior** — the Tier-1 band now weights by the sector's own exposure measure from its profile (sum insured for insurers, gross carrying amount for banks), never hard-coded; banking regression confirmed unchanged.

Open follow-up from item 1: the agri-food shadow book's cross-sector comparison reads the buildings headline-relevance path (matching how banking/insurance shadow books already work), not the agriculture one — worth revisiting if it matters for agri-food specifically.

## Remaining (reopen here)
1. **Real portal adapters** (EBA reporting portal, EIOPA Solvency II portal, OAM/ESEF): the adapter frame, credential vault and receipt flow exist; the live protocol per portal needs credentials and a sandbox.
2. **Soil-degradation raster materialised locally** (5.3 GB UNCCD COG; `scripts/fetch_soil_degradation.py`) so background scoring stops depending on a slow remote read.
## How to reopen
Branch from `main`, read `SOFTWARE_DESCRIPTION.md` v2.55–v2.70 and the memory notes `project_climate_platform_supervision_model`, `project_climate_platform_grc_spine`, `project_climate_platform_hazard_relevance`; run the end-to-end script under the session scratchpad (`e2e/e2e_grc.py`) against a fresh API before changing anything.
