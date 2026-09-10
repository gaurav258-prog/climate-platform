# Regulator module — status at close (10 September 2026)

The supervisory module is closed as a coherent, production-shaped release. Everything below the line "Built" is merged on `main`, verified end to end (bank + insurer, two runs, eight-thread load) and described version by version in `SOFTWARE_DESCRIPTION.md` (v2.55–v2.70). The "Remaining" list is what we consciously left for a later pass, so the module can be reopened without rediscovery.

## Built
- **Foundation as configuration:** supervision profiles (roles, scope assigned/population, sectors, stages, intake), one supervisory body per sector, assignments, scope with acknowledgement and site-access consent, `supervisor.*` permissions; the same engine as the regulated side (one-engine parity).
- **Population and analytics:** population with workflow stages, exposure map (NUTS-3 / H3, cells clipped to land), peer benchmark, scenario-shift analytics, trend, timeliness, anchor coverage, evidence packs (PDF + canonical JSON, hashed) and population export.
- **Independent lens (Tier 2) and plausibility band (Tier 1):** intake of the submitted template and granular extract for **banking** and **insurance** on the same canonical field ids; rebuild from the shadow book on the subject's own engine; four-part gap; cell drill-down; geography priors rebuilt daily.
- **Mandate registry:** nine mandates with curated article excerpts, EUR-Lex links, applicability criteria and tiers, deliverable/channel/due rule, versions with acknowledgement, change detection; supervisor-set deadlines with automatic follow-up; "what applies to you and why" on the entity side.
- **Engagement:** requests and findings with formal correspondence (reference numbers, legal basis, response period, signatory, hashed letter, receipt), the respondent portal for entities not on Tellumen, transmission adapters with receipts, governed remittance of case files (scoped, watermarked, expiring, revocable, logged both sides).
- **Governance layer shared with the regulated side:** board pack with named step-up attestation, reporting control register, model-risk register, auditor role and assurance share, appetite versioning, change→impact links, third-party exposure.
- **Honesty foundation:** hazard relevance registry (only intensity scales may headline; crop, susceptibility, variability and nowcast scales never), severe-convective damage anchoring, cold-wave channel.

## Remaining (reopen here)
1. **Tier-2 intake specs for the markets and agri-food supervisors** (asset manager / REIT holdings template; agri-food sourcing-plot template). The lens is sector-agnostic; only the two specs and demo files are missing. Lens links are hidden for those sectors until configured.
2. **Real portal adapters** (EBA reporting portal, EIOPA Solvency II portal, OAM/ESEF): the adapter frame, credential vault and receipt flow exist; the live protocol per portal needs credentials and a sandbox.
3. **Requests SLA metrics** (time to acknowledge, time to respond, overdue ageing per authority) and an **obligations calendar per authority**.
4. **Worker liveness surfaced in the UI:** a queued transmission whose worker is stale shows "queued" indefinitely; add a heartbeat and an honest "worker unavailable" state.
5. **Pending appetite approvals when the policy is switched off** remain decidable but are not flagged; auto-flag or auto-cancel.
6. **Soil-degradation raster materialised locally** (5.3 GB UNCCD COG; `scripts/fetch_soil_degradation.py`) so background scoring stops depending on a slow remote read.
7. **Insurer plausibility priors:** priors are population-wide on the buildings relevance; an insurer-specific prior (sum insured rather than carrying amount) would sharpen the band.

## How to reopen
Branch from `main`, read `SOFTWARE_DESCRIPTION.md` v2.55–v2.70 and the memory notes `project_climate_platform_supervision_model`, `project_climate_platform_grc_spine`, `project_climate_platform_hazard_relevance`; run the end-to-end script under the session scratchpad (`e2e/e2e_grc.py`) against a fresh API before changing anything.
