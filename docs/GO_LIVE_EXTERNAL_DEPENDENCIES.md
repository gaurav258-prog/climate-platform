# Go-live — external dependencies tracker

**What this is:** the short list of things that stand between *built & verified in the product* and *live for a
paying customer's real filing*, where the remaining step is **external** — an artifact a third party must publish,
a credential/registration only the customer can obtain, or data we must be given. The **mechanism for each is
already built and tested**; this file exists so none of these is forgotten when the external piece lands.

Companion docs: agri last-mile detail is in [`AGRI_OPS_READINESS.md`](AGRI_OPS_READINESS.md). Every item below
degrades honestly in-product today (shows "pending" / "prepared" / withholds the figure) — nothing is faked.

_Last reviewed: 2026-09-25._

## Status at a glance

| # | Item | Area | Built (ready) | Blocking | Hand Tellumen → we finish it |
|---|------|------|---------------|----------|------------------------------|
| 9 | EBA Template 3 "Chemicals" NACE code list | Bank Pillar 3 Template 3 | full official crosswalk built for the other 7 sectors (extracted + OCR'd from the real Annex XL table) + a disclosed fallback for Chemicals | **EBA itself has not published it** — confirmed via their own Q&A (not a research gap) | EBA publishes the NACE list (next DPM release) → replace the division-20 fallback in `transition_alignment.py` |
| 10 | NACE Rev. 2.1 transition (Template 3 only — Templates 1/5 already handled) | Bank Pillar 3, all templates using NACE | Templates 1/5 read NACE at section level (stable across the revision per JBRC's own advice); Template 3's crosswalk is fine-grained class/group level | EBA/JBRC guidance for Template 3 specifically not yet published as of the June-2025 JBRC advice | EBA/JBRC publish a Rev-2.1 equivalent of the Annex XL crosswalk → rebuild `_ANNEX_XL_NACE_CROSSWALK` against it |
| 1 | EFRAG ESRS Set 1 taxonomy element map | Agri / CSRD iXBRL | tagging + iXBRL/ESEF engine + validator + drop-in binding seam | running `PROVISIONAL` by design (no adopted map to fall back to — Aug-2024 is being superseded by the revised-ESRS taxonomy, draft, SRB 29-Jul-2026; mandatory tagging itself is directive-suspended until ESEF RTS updates) | the finalized revised-ESRS element-name list, verified against the real XSD taxonomy package → drop `config/efrag_esrs_binding.json` |
| 2 | EBA Pillar 3 ESG element map | Bank Pillar 3 XBRL | well-formed XBRL + drop-in binding seam, verified ITS refs | EBA taxonomy publication (P3DH) | the DPM element IDs → drop `config/eba_p3esg_binding.json` |
| 3 | EUDR operator registration + TRACES creds | Agri / EUDR submit | `prepared` mode + live config-flip | customer registration | sandbox creds + published DDS schema → we align + certify |
| 4 | Production geocoder provider + key | Agri (address→coords) | cache + QA + provider seam | provider choice + licence | provider + API key → we write the adapter |
| 5 | More crop calibration data | Agri model | fit + out-of-sample validate pipeline | real climate-attributable data | a crop×origin yield/climate series → we fit + validate |
| 6 | WDPA global protected-area layer | Agri / ESRS E4-5 | dataset-agnostic overlap engine + ingest script + E4 filing wiring | commercial data licence (IBAT) | an IBAT-licensed WDPA export → we load it, non-EU assets light up (no code change) |
| 7 | **GEM Global Exposure Model commercial licence** | Exposure / hazard→loss | not used: GHSL (CC BY 4.0) is the exposure source; GEM was never downloaded (`data/exposure_val/MANIFEST.md`) | CC BY-NC-SA 4.0 forbids commercial use + share-alike; **must be resolved before go-live / first customer** if GEM is ever used | licence request to licensing@globalquakemodel.org (commercial + 1 km disaggregation) → until granted, GEM stays out of every customer-facing output |
| 8 | OpenFEMA NFIP attribution + counsel confirmation | Validation evidence (`loss_us_nfip_flood`) | terms read 2026-09-20: commercial use allowed; disclaimer + citation required (in validator docstring) | counsel to confirm reading before quoting NFIP numbers to customers | add "not endorsed by FEMA" disclaimer + dataset/version/date citation wherever the NFIP result is shown |
| 11 | **Malware scanner (ClamAV daemon)** for customer data intake | All sectors — data intake | scanner client (`services/intake/malware.py`, clamd INSTREAM, tested against a protocol-faithful fake), policy: required everywhere except development; without a scanner a batch is **held**, not processed | a running `clamd` with signature updates (`freshclam`) in each deployment | set `CLAMD_HOST`/`CLAMD_PORT` (or `CLAMD_SOCKET`) → held batches can be released with `POST /v1/intake/batches/{id}/rescan` |
| 12 | **Object storage for received customer files** | All sectors — data intake | write-once, content-addressed store with a local-directory backend (`services/intake/storage.py`); asking for any other backend fails loudly | an S3-compatible bucket (versioning + object lock, encryption at rest, region per data-residency) per deployment | bucket + credentials → we add the object-store backend behind the same `put`/`get` |
| 13 | **SFTP server for drop-folder channels** | All sectors — data intake | drop-folder channels behind an inbox storage interface (`services/intake/inbox.py`, local backend), sweep every 5 min through the full intake pipeline with one pick-up per folder at a time, processed/ and refused/ (with reason) filing, SFTP key registration + `authorized_keys` rendering, admin UI (`services/intake/{dropfolder,inbox,sftp_keys}.py`, `/v1/intake/channels`, `/v1/intake/sftp-keys`) | an SFTP endpoint per deployment (OpenSSH chroot or a managed service such as AWS Transfer Family), one login per organisation, key-based, chrooted to `INTAKE_DROP_DIR/<org_id>` | point the server at `INTAKE_DROP_DIR` (or, with a bucket, add the object-store inbox backend) and load each organisation's `authorized_keys()` → customer systems write to `/<template>/incoming` |
| 14 | **Production Kubernetes cluster** | All sectors — deployment | CI builds, tests and pushes the image (`ghcr.io/<owner>/climate-platform:<sha>`, Python 3.14) on every push to main; the deploy job applies `infra/k8s/*` and waits for the rollout, and skips with a notice while no cluster is connected (error log E26) | a cluster (namespace `climate-platform`), its secrets pre-created (`infra/k8s/secret.yaml`), and the GitHub `production` environment approval gate | set the repository secret `KUBECONFIG` (base64 kubeconfig) → the next push to main deploys |
| 15 | S.27.01.01 rows added from 2027 (EIOPA taxonomy 2.10.0) | Insurer Solvency II | 2027 calculation; form names regions without a row; 2027 XBRL refused with the rows named | the amending ITS / legal act not yet identified (Cellar: none, 2026-09-30) | the act → new spec version on the change route, `s2701.REGION_ROW` extended |
| 16 | EIOPA XBRL validation files | Insurer Solvency II XBRL | Arelle validation with EIOPA's rules (`scripts/validate_s2701_xbrl.py`), run by the E2E test when present | EIOPA / Eurofiling files are not redistributed in the repository | set `EIOPA_XBRL_PACKAGE` and `EIOPA_IAF_FILE` in CI |

---

## 1 · EFRAG ESRS Set 1 taxonomy element map  *(external artifact — mid-replacement, not simply "not yet published")*
- **Hook:** `config/efrag_esrs_binding.json` (override env `EFRAG_ESRS_BINDING`), consumed by
  `services/intelligence/esrs_taxonomy.py`. No file present → profile honestly reports
  `pending_adopted_taxonomy`, `bound=false` per concept; the `provisional` (`tesrs:`) profile works meanwhile.
- **Re-checked 2026-09-22 — status is more nuanced than "EFRAG hasn't published it":**
  - EFRAG DID publish a final **ESRS Set 1 XBRL taxonomy in August 2024** ([press release](https://www.efrag.org/en/news-and-calendar/news/efrag-publishes-the-esrs-set-1-xbrl-taxonomy),
    approved by SR TEG/SRB 16–17 July 2024). A real, usable element-ID map exists.
  - **But it's mid-replacement.** The ESRS standards themselves were revised on **3 July 2026** (Omnibus
    simplification), EC-adopted and awaiting Official Journal publication after the scrutiny period. EFRAG is
    now drafting a *new* taxonomy for the revised standard — discussed at the SRB meeting **29 July 2026**,
    still in draft as of this review ([EFRAG Knowledge Hub notice](https://www.efrag.org/en/news-and-calendar/news/efrag-esrs-knowledge-hub-2026-revised-esrs-and-voluntary-standard-interactive-document-set-now)).
  - **Mandatory tagging is directive-suspended anyway.** Directive (EU) 2026/470 (in force 18 March 2026)
    suspends mandatory XBRL tagging of CSRD sustainability reports until the ESEF Delegated Regulation
    (2019/815) is updated to reference whichever taxonomy ends up final.
- **Why we're not binding the Aug-2024 map now:** it would wire the platform against an element set that's
  actively being superseded, for a mandate that's currently suspended — a stopgap that would need redoing,
  not a real close. Waiting for the revised-ESRS taxonomy to firm up (post 29-Jul-2026 SRB discussion) is the
  root-cause fix, not the Aug-2024 map.
- **Checked 2026-09-22 whether the Aug-2024 map could be dropped in now anyway (per the standing rule: run
  the currently-adopted version until a new one is officially announced, don't hold out for a future one).**
  It doesn't actually apply here — that rule picks between two REAL, adopted regulatory versions (e.g. ITS
  2022/2453 vs. the still-pending EBA/ITS/2026/02). Here, "the old" isn't a second adopted taxonomy; it's our
  own `PROVISIONAL` `tesrs:` profile, which is exactly what's already active and already the correct thing to
  run — there's no adopted EFRAG map to fall back to, only a real-but-being-superseded one (Aug-2024) and a
  not-yet-final one (2026 draft). The published Aug-2024 taxonomy's element definitions also live in the
  actual XBRL taxonomy package (XSD/linkbase files), not the (scanned, non-machine-readable) explanatory
  note PDF — so even binding it properly would mean downloading and parsing that package, not a 1-hour JSON
  edit as originally scoped. And most of our 16 CONCEPTS (`SourcingCOGSAtRiskPublished`,
  `ExposureMappedWithheld`, EUDR/protected-area counts, …) are Tellumen's own derived metrics, not standard
  mandatory ESRS datapoints — they were never going to have an official 1:1 element regardless of which
  taxonomy version ships. **Decision: keep running `PROVISIONAL` (the current, correct default) rather than
  bind a map that's both incomplete-by-nature and about to be superseded** — this is what "keep the old until
  the new is confirmed" means in practice here, not "bind Aug-2024 as a stopgap."
- **Needed:** the finalized **revised-ESRS** XBRL taxonomy element names (our concept key → official element
  ID, verified against the real XSD/linkbase taxonomy package, not the PDF) — for whichever of our concepts
  turn out to have genuine standard-datapoint equivalents; the rest correctly stay under `tesrs:` regardless.
- **Owner:** EFRAG publishes it; obtaining + dropping it in is us.
- **When it lands:** write the JSON, flip `efrag_set1` to bound, re-run `/esrs-pack.validate` (+ Arelle if
  installed). No code change. **Do not invent element IDs.**

## 2 · EBA Pillar 3 ESG element map  *(external artifact — EBA taxonomy pending)*
- **Hook:** `config/eba_p3esg_binding.json` (override env `EBA_P3ESG_BINDING`), consumed by
  `_load_p3_binding()` in `services/governance/filing_export.py`. No real map present → the export
  emits well-formed, fully tagged XBRL under the provisional namespace `_P3_NS =
  https://taxonomy.tellumen.eu/p3esg/2024` and self-documents that state; `p3esg_binding_status()`
  reports `pending_eba_taxonomy`. All 13 facts are scaffolded with their **verified ITS 2022/2453
  (Annex XXXIX/XL) template + column reference** — only the machine element id is pending.
- **Needed:** the official EBA element ids/namespace. The EBA will develop the DPM and XBRL taxonomy
  for the **Pillar 3 Data Hub (P3DH)**; the disclosure ITS was amended Jun-2026 (EBA/ITS/2026/02),
  reference date 31 Dec 2026 (31 Dec 2027 for small & non-complex institutions). It is **not yet published**.
- **Owner:** EBA publishes it; obtaining + dropping it in is us.
- **When it lands:** set `namespace` + each `element` in the JSON, re-verify the instance. ~1h, no code
  change (a simulated real map already flips all 13 facts to bound). **Do not invent element IDs.**

## 3 · EUDR operator registration + TRACES credentials  *(customer, then us)*
- **Hook:** `services/intelligence/traces_client.py` — `submission_preview()` + `submit_dds()` run in
  **`prepared`** mode (build + completeness-check the envelope, file nothing). Live flips on
  `TRACES_MODE=live` + `TRACES_BASE_URL` + `TRACES_API_TOKEN` (missing creds → explicit `not_configured`, never a fake success).
- **Needed — customer:** register as an **EUDR operator** in the EU Information System; obtain sandbox + prod API credentials.
- **Needed — us (data-not-code):** align the envelope field names to the published EUDR-IS / TRACES DDS schema; certify against sandbox before prod.
- **When it lands:** map fields against the published schema now if available; certify on sandbox creds; then flip live. Human sign-off before submit stays (operator carries EUDR liability).

## 4 · Production geocoder provider + key  *(customer picks, us adapts)*
- **Hook:** `services/geocoding/geocoder.py` — cache + confidence/QA + `GEOCODER_PROVIDER` seam. Only `nominatim` adapter implemented today.
- **Needed:** choose a production provider (self-hosted Nominatim, or Google / HERE / Mapbox) + URL/API key.
- **Owner:** customer/ops chooses + funds; us writes the adapter (seam is ready).
- **When it lands:** write the provider adapter, set `GEOCODER_PROVIDER` + creds. Hazard data is unaffected — geocoding is a separate utility.

## 5 · More crop calibration data  *(external data, then us)*
- **Hook:** `scripts/fit_ranged_crop.py` + `scripts/backtest_*.py`; publish gate `RANGED_PUBLISH_FLOOR = 0.40`
  (`services/intelligence/supply_cogs.py`). A crop×origin publishes a firm € only where its hazard→yield fit clears
  **r²≥0.40 out-of-sample**; otherwise exposure is mapped and the € withheld (honesty gate). Olive-drought (r²=0.51),
  cocoa, coffee are calibrated; others use disclosed v0 defaults.
- **Needed:** real **climate-attributable** yield/loss history per crop × origin (FAO / national ag-stats /
  customer outcome data) — must be a climate-attributable target (a cyclical crop can't be validated against a raw world shock).
- **Owner:** data sourcing is external; us runs the fit + out-of-sample validation.
- **When it lands:** fit + validate; it either calibrates (tier lights up) or is honestly held. Withholding is the design, not a defect.

## 6 · WDPA global protected-area layer  *(external data + licence, then us)*
- **Hook:** `services/intelligence/protected_area.py` — `protected_area_exposure()` is a dataset-agnostic
  H3-cell membership test against `protected_h3_cell`; it de-dups across datasets and reports per-dataset
  cell counts, so **any** loaded protected-area layer lights up with zero code change. Wired into the ESRS
  **E4-5** filing (`services/intelligence/esrs_nature.py:biodiversity_topic`), tagged in the XBRL/iXBRL export
  (4 E4-5 concepts), and surfaced on the ESRS pack UI with an honest per-dataset coverage note.
- **Loaded today:** `natura2000` (EU-27, 405,872 cells) + `osm` (community, 54,818 cells). Overlap outside the
  EU is disclosed as a **coverage gap**, never as "no overlap".
- **Needed:** the authoritative global layer — **WDPA** (World Database on Protected Areas). The free
  Protected Planet API (`scripts/ingest_wdpa_api.py`, `--token $PP_TOKEN`) is **non-commercial licence only**;
  a paying customer's filing needs a **commercial WDPA export via IBAT**, loaded through the file path
  (`scripts/ingest_natura2000.py`-style loader, tagged `--dataset wdpa`).
- **Owner:** licence is external (IBAT); obtaining + loading it is us — one ingest run, no code change.
- **When it lands:** run the loader; non-EU sites/plots start reporting protected-area overlap and the
  coverage note flips to "backed by the WDPA global layer". **Do not load the non-commercial API export into a
  paying customer's tenant.**

## 7 · Solvency II standard-formula EXACT zonal figure  *(BUILT — needs only the insurer's postal codes)*
- **Status (2026-09-30):** every zoned region of Annexes V–VIII (58 regions; 66 from 2027) is loaded with its Annex X
  weights and Annex XXII–XXVI correlations (`data/reference/solvency2_zonal[.2027].json`), and Annex IX is a postal-code
  map per region and peril (`solvency2_annex_ix[.2027].json`). A risk is placed in its zone from the **postal code on
  the Statement of Values** (`portfolio_entities.postal_code`) — no boundary geodata, no CRESTA layer. A risk without a
  postal code, or in a region Annex IX zones by administrative unit (BG, CR, HU, RO before 2027, SE) or by codes that
  are not postcodes (CH, IE), is charged on the Art. 90b grouping of its region's zones (highest weight — an upper
  bound), shown per region, and reported on S.27.01.01 R0002.
- **Remaining (customer data, not an external dependency):** postal codes on each insurer's Statement of Values. For
  the administrative-unit regions, the unit (county) per risk would place those too — optional, the Art. 90b figure is
  prudent.

## 15 · S.27.01.01 from 2027 — EIOPA taxonomy 2.10.0 adds rows  *(external — legal act not yet identified)*
- EIOPA's Solvency II taxonomy 2.10.0 (published 3 July 2026, applicable from Q1 2027) adds rows to S.27.01.01 for the
  regions Delegated Regulation 2026/269 introduces: flood DK, FI, LU, NL, NO, IE, SE (R1291–R1385), hail PL (R1702),
  subsidence BE and France (R1945–R1946) — `data/reference/eiopa/s2701_xbrl.2.10.0.json`. ITS 2023/894 as captured
  (spec `sii_qrt_natcat/its_2023_894`) has no such rows and the EU Cellar shows no amending act (checked 2026-09-30).
- **Built:** the 2027 calculation (2026/269); the form names every region without a row; the XBRL export for a 2027
  reference date refuses with the missing rows named, rather than report totals the rows don't add up to.
- **Needed:** the amending implementing act (or EIOPA's published ITS) → capture it on the change route as a new
  version of `sii_qrt_natcat`, extend `s2701.REGION_ROW`, sign off.

## 16 · EIOPA XBRL validation files  *(external files, not redistributed — needed where validation runs)*
- `scripts/validate_s2701_xbrl.py` validates an S.27.01.01 instance with Arelle against EIOPA's taxonomy and EIOPA's
  own validation rules (15 rules apply to the end-to-end filing; all pass except BV264, which needs the undertaking's
  man-made / other catastrophe sub-modules from its own package).
- **Needs:** `EIOPA_XBRL_PACKAGE` = EIOPA_SolvencyII_XBRL_Taxonomy_2.8.2_Final_with_external_files.zip
  (dev.eiopa.europa.eu) and `EIOPA_IAF_FILE` = interval-arithmetics.xml (www.eurofiling.info/eu/fr/xbrl/func/). The
  end-to-end test runs the validation when both are set and skips that step otherwise → set both in CI.

## Copernicus EGMS (European Ground Motion Service) account

Needed to download InSAR ground-motion products (the observed target that would let the subsidence channel be backtested properly; GNSS velocities only reach rank correlation 0.21). Free registration at egms.land.copernicus.eu; download is token-gated. Added 2026-09-10.

## 9 · EBA Template 3 "Chemicals" NACE code list  *(external — genuinely not yet published by EBA)*
- **Status, confirmed by EBA's own Q&A process, not a research gap on our side:**
  - [EBA Q&A 2024_7085](https://www.eba.europa.eu/single-rule-book-qa/qna/view/publicId/2024_7085) —
    someone asked whether "Chemicals" should be removed from Template 3 or the code list updated to include
    it. EBA's verbatim answer: *"institutions shall present also IEA sector Chemicals as one of the rows for
    Template 3. The related DPM will be amended accordingly with the next reporting framework release."* —
    confirms Chemicals IS a mandatory row, but gives no NACE codes.
  - [EBA Q&A 2025_7451](https://www.eba.europa.eu/single-rule-book-qa/qna/view/publicId/2025_7451) — someone
    then asked exactly which NACE codes apply to Chemicals. **EBA rejected the question outright**: *"This
    question has been rejected because the matter it refers to has already been identified and will be
    considered for the forthcoming version of the Reporting framework."* As of today, no EBA publication
    anywhere specifies Chemicals' NACE codes — every other Template-3 sector's list is published (extracted
    and verified directly from the Official Journal document, `services/governance/transition_alignment.py`),
    Chemicals' column is genuinely, officially blank.
- **What's built:** the other 7 sectors' crosswalks are the real, OCR'd Annex XL table, verified against NACE
  Rev. 2 (Reg. (EC) 1893/2006). Chemicals uses NACE division 20 ("manufacture of chemicals and chemical
  products") as a disclosed, reasonable placeholder — this is the best any institution can do until EBA
  publishes its own list, not a shortcut on our part.
- **When it lands:** EBA's "next reporting framework release" ships the DPM update — watch
  eba.europa.eu/risk-and-data-analysis/reporting/reporting-frameworks for the release that finally includes
  Chemicals' code list, then replace the `digits[:2] == "20"` fallback in `_iea_sector()` with the real list.
- **Re-checked 2026-09-22 — still genuinely unpublished, now under a new template name.** EBA's Final Report
  on the amended ESG disclosure ITS ([EBA/ITS/2026/02](https://www.eba.europa.eu/sites/default/files/2026-06/96e1c806-c918-460c-bc8b-4e547b0d85e6/Final%20report%20on%20Draft%20ITS%20on%20amended%20disclosure%20requirements%20for%20ESG%20risks,%20equity%20exposures%20and%20aggregate%20exposure%20to%20shadow%20banking%20entities.pdf),
  22 June 2026) renames the old Template 3 to **EU CRFR4** and explicitly confirms the same gap in the new
  wording: "IEA Sector named 'Chemicals' is not included in the EBA 3.3 list of values" — 8 mandatory
  sectors specified vs. 7 in the actual DPM list-of-values, the same shortfall as Q&A 2024_7085/2025_7451.
  Reference date for the new ITS is confirmed as **December 2026**. No new sector-code list published.

## 10 · NACE Rev. 2.1 transition — Template 3 not yet addressed  *(external, timely — monitor)*
- **What changed:** the EBA and ECB confirmed (Joint Bank Reporting Committee advice, June 2025) that EU
  supervisory/statistical/disclosure reporting must move to the revised **NACE Rev. 2.1** classification for
  any reporting period from **1 January 2026** — which has already passed as of this doc's last review.
- **Checked directly against the JBRC advice document itself** (not a summary): its detailed scope annex
  names exactly **Pillar 3 ESG Template 1** (transition risk, credit quality by sector) and **Template 5**
  (physical risk exposures) as in-scope, plus FINREP F 06.01/F 20.07.1 and the NPL CQ5 template. **Template 3
  is not mentioned anywhere in the document** — its Annex XL crosswalk transition to Rev. 2.1 has not been
  addressed by EBA/JBRC at all as of the June-2025 advice.
- **Why Templates 1/5 are less exposed today:** they classify counterparties at the NACE **section** level
  (letters A-U, `_section()` in `pillar3_templates.py`), and the JBRC advice itself says the transition is
  "reported on a 1-to-1 basis to the existing related labels — only changes in the wording of a few labels
  are needed" at that level, i.e. the section-letter structure Templates 1/5 use isn't being restructured.
  Template 3's crosswalk operates at the fine-grained NACE **class/group** level, which IS where Rev. 2.1
  renumbers things — so it's the one genuinely exposed until EBA publishes a Rev.-2.1-native version of the
  Annex XL table (which may well ship in the same "next reporting framework release" as the Chemicals fix
  above, since both are DPM-release-gated).
- **When it lands:** watch for the EBA reporting-framework release that ships a NACE-2.1-native Template 3
  instruction; until then, `_ANNEX_XL_NACE_CROSSWALK` stays on the verified Rev. 2 codes, which remains the
  only published version to build against.
- **Re-checked 2026-09-22 — real movement, but the binding text still isn't public.** The same June-2026 EBA
  Final Report (EBA/ITS/2026/02) confirms Template 3/EU CRFR4's sector breakdown is being expanded with
  additional carbon-intensive sub-industries — explicitly naming "certain carbon chemicals" alongside oil &
  gas, automotive segments, and steel — and states "a minimum list of sectors is provided in the instructions
  together with a mapping with NACE sectors." That mapping table is NOT reproduced in this Final Report
  (which is the consultation-feedback document, not the binding Annex) — the actual binding Annex I/II text
  publishes once the Commission formally adopts the ITS via the Official Journal, which had not happened as
  of this report. Confirmed the reference date: institutions report under this ITS from **December 2026**.
- **Code renamed to match 2026-09-22** (see `services/governance/transition_alignment.py`, `filing_annex.py`,
  `kri.py`, `kri_regmap.py`, `datapoint_catalog.py`, `api/routers/bank.py`): Template 3 is now referenced as
  "Template 3 / EU CRFR4 (pending adoption)" everywhere it appears, since EBA/ITS/2026/02 renames (not
  deletes) it. **Template 4 (top-20 carbon-intensive firms) is DELETED outright, not renamed** — the EBA's
  own stated reasoning is limited prudential relevance, methodological divergence, and overlap with EU
  CRFR1 — code comments now say so explicitly. Neither is removed from the platform yet: ITS 2022/2453
  remains the current, in-force regulation, and both templates stay live under their current names until the
  amended ITS is formally adopted — we always run the adopted version, never a still-pending "Final Report".
- **GAR/BTAR (Templates 6–9) confirmed DELETED, with a clear rationale — not just removed, actively
  duplicative.** The same Final Report says the majority of respondents recommended deleting the ITS's
  cross-references to the Taxonomy Regulation's own GAR templates (Del. Reg. (EU) 2021/2178, Annex VI)
  specifically BECAUSE they duplicated that disclosure, and the EBA agreed. Template 10 (mitigating actions)
  is broadened to cover all climate-risk-mitigating exposures, taxonomy-aligned or not, as a partial
  replacement. **This affects our own Pillar 3 bundle**: `filing_annex.py`'s banking-book Pillar 3 section
  currently presents GAR (Templates 6–8) and BTAR (Template 9) AS PART of the ITS 2022/2453 submission,
  duplicating the platform's own separate, correct Taxonomy Annex VI section (`_taxonomy_art8_annex_vi()`).
  Once the amended ITS is adopted, GAR/BTAR should be dropped from the Pillar 3 bundle entirely and left
  solely in the Annex VI section, matching what the EBA itself concluded — flagged in code comments at both
  sites, not yet changed since ITS 2022/2453 still asks for them today.
- **When the binding text lands:** replace `_ANNEX_XL_NACE_CROSSWALK` with the EU CRFR4 NACE-2.1-native
  mapping, drop Template 4 and the GAR/BTAR duplication from the Pillar 3 bundle, once the Commission
  Implementing Regulation is published in the Official Journal (watch eur-lex.europa.eu via
  `scripts/fetch_eu_regulation.sh` for the CELEX once assigned) — this closes #9 and #10 together, since
  both are gated on the same publication.
