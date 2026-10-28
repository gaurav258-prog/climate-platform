# Go-live — external dependencies tracker

**What this is:** the short list of things that stand between *built & verified in the product* and *live for a
paying customer's real filing*, where the remaining step is **external** — an artifact a third party must publish,
a credential/registration only the customer can obtain, or data we must be given. The **mechanism for each is
already built and tested**; this file exists so none of these is forgotten when the external piece lands.

Companion docs: agri last-mile detail is in [`AGRI_OPS_READINESS.md`](AGRI_OPS_READINESS.md). Every item below
degrades honestly in-product today (shows "pending" / "prepared" / withholds the figure) — nothing is faked.

_Last reviewed: 2026-10-23 (XBRL items 1, 2, 16, 17 re-checked against the publishers' latest packages)._

## Status at a glance

| # | Item | Area | Built (ready) | Blocking | Hand Tellumen → we finish it |
|---|------|------|---------------|----------|------------------------------|
| 9 | EBA Template 3 "Chemicals" NACE code list | Bank Pillar 3 Template 3 | full official crosswalk built for the other 7 sectors (extracted + OCR'd from the real Annex XL table) + a disclosed fallback for Chemicals | **EBA itself has not published it** — confirmed via their own Q&A (not a research gap) | EBA publishes the NACE list (next DPM release) → replace the division-20 fallback in `transition_alignment.py` |
| 10 | NACE Rev. 2.1 transition (Template 3 only — Templates 1/5 already handled) | Bank Pillar 3, all templates using NACE | Templates 1/5 read NACE at section level (stable across the revision per JBRC's own advice); Template 3's crosswalk is fine-grained class/group level | EBA/JBRC guidance for Template 3 specifically not yet published as of the June-2025 JBRC advice | EBA/JBRC publish a Rev-2.1 equivalent of the Annex XL crosswalk → rebuild `_ANNEX_XL_NACE_CROSSWALK` against it |
| 1 | EFRAG ESRS taxonomy element map | Agri / CSRD iXBRL | the ESRS statement per undertaking and year, each figure keyed by concept (`data/reference/esrs/concepts.json`); **JSON export only — no ESRS XBRL** (the provisional engine was removed, E60/E66) | EFRAG's taxonomy for the revised ESRS (Delegated Reg. 2026/1563) is a **draft** in consultation until 11 Nov 2026, final due to ESMA and the Commission by end-2026; EFRAG says it 'replaces' the Aug-2024 set and that tagging is 'not yet mandatory'. Product owner, 2026-10-23: keep the gap until the final (do not bind the Aug-2024 set) | EFRAG's final revised-ESRS taxonomy → we bind the concepts to its elements per ESRS version, verified against the package, and build the iXBRL export on it |
| 2 | EBA Pillar 3 ESG taxonomy (P3DH DPM) | Bank Pillar 3 data hub (xBRL-CSV) | **Built 2026-10-23.** Every Template 1–10 cell bound to its EBA datapoint, read from the EBA's 4.2 package (module ESGDIS 2.1.0, reference dates from 31 Mar 2026): 2,564 cells + the open tables' columns and code lists, 0 EBA datapoints unbound (`data/reference/eba/p3esg_xbrlcsv.4.2.json`, `scripts/build_eba_p3esg_map.py`). Export `xbrlcsv` builds EBA's report package from the frozen filing (`services/governance/p3esg_xbrlcsv.py`); validated with Arelle on the EBA's taxonomy and on EBA Filing Rules v5.8 (`scripts/validate_p3esg_xbrlcsv.py`, CI job `xbrl-validation`) | EBA's 4.4 module (12 Oct 2026) follows the amending ITS, still a final draft; EBA switches off all its ESGDIS rules (Template 2 column p bound since the EBA's Q&A 2022_6625 states its denominator, E341) | adoption of the amending ITS → capture it on the change route and bind the 4.4 module the same way |
| 3 | EUDR information-system registration + interface spec | Agri / EUDR statements | filing lifecycle built; reference recorded by hand | customer registration (EU Login) | published interface spec + test access → we map + certify |
| 4 | Production geocoder provider + key | Agri (address→coords) | cache + QA + provider seam | provider choice + licence | provider + API key → we write the adapter |
| 5 | More crop calibration data | Agri model | fit + out-of-sample validate pipeline | real climate-attributable data | a crop×origin yield/climate series → we fit + validate |
| 6 | WDPA global protected-area layer | ESRS E4 (support for the undertaking's site count) | the ESRS statement lists own sites inside a listed layer (`esrs_statement._sensitive`, `data/reference/esrs/biodiversity_sensitive.json`) + ingest script | commercial data licence (IBAT) | an IBAT-licensed WDPA export → we load it and list it with the ESRS kind it is (quoted); non-EU sites are then assessed (no code change) |
| 7 | **GEM Global Exposure Model commercial licence** | Exposure / hazard→loss | not used: GHSL (CC BY 4.0) is the exposure source; GEM was never downloaded (`data/exposure_val/MANIFEST.md`) | CC BY-NC-SA 4.0 forbids commercial use + share-alike; **must be resolved before go-live / first customer** if GEM is ever used | licence request to licensing@globalquakemodel.org (commercial + 1 km disaggregation) → until granted, GEM stays out of every customer-facing output |
| 8 | OpenFEMA NFIP attribution + counsel confirmation | Validation evidence (`loss_us_nfip_flood`) | terms read 2026-09-20: commercial use allowed; disclaimer + citation required (in validator docstring) | counsel to confirm reading before quoting NFIP numbers to customers | add "not endorsed by FEMA" disclaimer + dataset/version/date citation wherever the NFIP result is shown |
| 11 | **Malware scanner (ClamAV daemon)** for customer data intake | All sectors — data intake | scanner client (`services/intake/malware.py`, clamd INSTREAM, tested against a protocol-faithful fake), policy: required everywhere except development; without a scanner a batch is **held**, not processed | a running `clamd` with signature updates (`freshclam`) in each deployment | set `CLAMD_HOST`/`CLAMD_PORT` (or `CLAMD_SOCKET`) → held batches can be released with `POST /v1/intake/batches/{id}/rescan` |
| 12 | **Object storage for received customer files** | All sectors — data intake | write-once, content-addressed store with a local-directory backend (`services/intake/storage.py`); asking for any other backend fails loudly | an S3-compatible bucket (versioning + object lock, encryption at rest, region per data-residency) per deployment | bucket + credentials → we add the object-store backend behind the same `put`/`get` |
| 13 | **SFTP server for drop-folder channels** | All sectors — data intake | drop-folder channels behind an inbox storage interface (`services/intake/inbox.py`, local backend), sweep every 5 min through the full intake pipeline with one pick-up per folder at a time, processed/ and refused/ (with reason) filing, SFTP key registration + `authorized_keys` rendering, admin UI (`services/intake/{dropfolder,inbox,sftp_keys}.py`, `/v1/intake/channels`, `/v1/intake/sftp-keys`) | an SFTP endpoint per deployment (OpenSSH chroot or a managed service such as AWS Transfer Family), one login per organisation, key-based, chrooted to `INTAKE_DROP_DIR/<org_id>` | point the server at `INTAKE_DROP_DIR` (or, with a bucket, add the object-store inbox backend) and load each organisation's `authorized_keys()` → customer systems write to `/<template>/incoming` |
| 14 | **Production Kubernetes cluster** | All sectors — deployment | CI builds, tests and pushes the image (`ghcr.io/<owner>/climate-platform:<sha>`, Python 3.14) on every push to main; the deploy job applies `infra/k8s/*` and waits for the rollout, and skips with a notice while no cluster is connected (error log E26) | a cluster (namespace `climate-platform`), its secrets pre-created (`infra/k8s/secret.yaml`), and the GitHub `production` environment approval gate | set the repository secret `KUBECONFIG` (base64 kubeconfig) → the next push to main deploys |
| 15 | S.27.01.01 rows added from 2027 (EIOPA taxonomy 2.10.0) | Insurer Solvency II | 2027 calculation; form names regions without a row; 2027 XBRL refused with the rows named (a group's S.27.01.04 likewise: 2.10.0 adds the same rows to it) | the amending ITS / legal act not yet identified (Cellar: none, 2026-09-30) | the act → new spec version on the change route, `s2701.REGION_ROW` extended |
| 16 | EIOPA XBRL validation files | Insurer Solvency II XBRL | **Closed 2026-10-23.** EIOPA's latest packages pinned (address, size, SHA-256) in `data/reference/eiopa/s2701_xbrl.<version>.json`: 2.8.2 NACE 2.1 hotfix (to Q4/Annual 2026) with EIOPA's deactivation list of 3 Jun 2026, and 2.10.0 (from Q1 2027); both cell maps re-checked against them (710/710 cells, 0 differences). A group's S.27.01.04 (annual group entry point arg) mapped the same way in `s2704_xbrl.<version>.json` (710/710, 0 disagreements), with EIOPA's list for the group entry point (3 Jun 2026, 17 rules) pinned (E342). `scripts/validate_s2701_xbrl.py` runs EIOPA's rules with the functions taken from EIOPA's own package; CI job `xbrl-validation` fetches the pinned files (`scripts/fetch_xbrl_packages.py`, cached), validates a solo and a group instance, and fails if they are missing (E338) | none — EIOPA publishes the files; CI fetches them as pinned | — |
| 17 | Official SFDR PAI XBRL taxonomy | Asset manager SFDR PAI XBRL / iXBRL | the PAI statement per fund and entity (RTS Table 1), exported as JSON and a workbook; **no SFDR XBRL** — the instance and Inline XBRL under a Tellumen-made namespace were removed (E113, as E60/E95/E104); filings of every date are refused the format (409), the fund routes answer 410 | **none is published (checked 2026-10-23):** the ESAs' 2023 draft RTS that would have required Inline XBRL was not adopted (Cellar: RTS 2022/1288 amended only by 2023/363), no SFDR taxonomy exists, and SFDR itself is under Level 1 review (ESMA, 28 Sep 2026) | an official taxonomy package → we bind each Table 1 indicator to its element (verified against the package), validate, and offer the format again |
| 18 | Coastal flood inundation maps (WRI Aqueduct Floods, coastal) — **RESOLVED 2026-10-23** | Loss engine — coastal flood losses, all sectors | coastal flood is a peril of the loss engine: WRI's coastal maps (with subsidence; present day and RCP4.5/8.5 2030/2050/2080 at the 5th, 50th and 95th percentile of sea-level rise; 9 return periods) registered as `aqueduct_coastal_flood`, read through the adopted depth curves (the JRC curves, on WRI's own statement), on the one warming timeline | — (WRI's host answers again at the same address, all 410 coastal files, re-uploaded 2026-03-27) | open: coastal defences (item 19); a test on observed coastal losses before any coastal figure leaves 'untested' |
| 19 | Building-level flood loss records for the European damage curves | Loss engine — flood figures in Europe, all sectors | the curve test machinery (`services/loss/published_test.py`: event totals of Σ curve ratio × building value against recorded damage, under `data/reference/loss_protocol.json`); the European curves stay held on the regional HANZE test (2026-10-20), which cannot judge a curve | no openly licensed European record gives, per building, the water depth, the damage in money and the building's value (search of 2026-10-23): the holders that have them license them for research only or on request | a data-use agreement that allows commercial use and publishing the test's result → we register the test before reading the damage, run it, and the curves' standings follow |
| 20 | Coastal flood protection standards — **BUILT for Europe 2026-10-23** | Loss engine — defended coastal flood losses | COASTPROS-EU (Zenodo 10.5281/zenodo.15024139, CC BY 4.0; 148 coastal NUTS2 regions, 24 countries) registered as protection layer `coastpros_eu` and applied with the river-flood rule; its text read 'clean entries only' (decided): a level, or a range giving a defended range | outside Europe's listed coastal regions, and where a region states a list, a condition or no level, protection stays unknown (undefended, labelled) | a global coastal protection-standards dataset → the same registration |
| 21 | Global Energy Monitor trackers (plants with owners and capacity) | Issuer sites — power, steel, cement, mines | issuer sites from Climate TRACE (owner LEI) and the EEA register (reviewed names) — `issuer_facilities.match_basis` | globalenergymonitor.org answered HTTP 520 all of 2026-10-23, and its downloads sit behind a form with a human check | the tracker files (CC BY 4.0 per GEM) → we join them by GEM entity id to GLEIF's GEM→LEI mapping |
| 22 | Observed European windstorm losses for the windstorm curve | Loss engine — European windstorm figures, all sectors | European windstorm is a loss peril (PRIMAVERA gust maps through the Prahl et al. 2015 curve for German homes); every figure 'untested' (`data/reference/loss_protocol.json` europe_windstorm_test) | no open, commercially usable record pairs observed storm losses with insured values at a unit whose gust can be read (search of 2026-10-25) | a data-use agreement that allows commercial use and publishing the result (GDV district data, PERILS zone data, or a building insurer's claims) → register the test before the losses are read, run it, record the result on the curve |
| 23 | **PRIMAVERA windstorm event set — licence to confirm with the Met Office** | Loss engine — European windstorm figures, all sectors | the gust maps (`primavera_windstorm_gust`) built under the record's licence, Open Government Licence v3.0, with its attribution; each run's file licence attribute recorded with the build (`data/reference/supply_datasets.json` primavera_windstorm_compact) | the footprint files carry their source models' CMIP6 attributes: CC BY-SA 4.0 (CMCC, EC-Earth, Met Office, MPI-M runs) and CC BY-NC-SA 4.0 — non-commercial — for the two CNRM-CERFACS runs (128 of 1,332 winters); both differ from the record's licence | the Met Office's written confirmation (contact named in the documentation) that OGL v3.0 governs the event set → windstorm figures may reach customers; until then they stay on the platform's own screens |

---

## 1 · EFRAG ESRS taxonomy element map  *(external artifact — the revised-ESRS taxonomy is a draft)*
- **Re-checked 2026-10-23 (EFRAG's own pages):**
  - Final: the **ESRS Set 1 XBRL Taxonomy** of 30 Aug 2024 (`xbrl.efrag.org/downloads/ESRS-Set1-XBRL-Taxonomy.zip`,
    1.9 MB) — for ESRS Set 1 ('which the EC adopted on 31 July 2023').
  - Draft: EFRAG's **Draft XBRL Taxonomy for the Revised ESRS** (17 Sep 2026, entry point
    `xbrl.efrag.org/taxonomy/esrs/2026-08-30/esrs.xsd`). EFRAG: "The Draft XBRL Taxonomy replaces the taxonomy released
    by EFRAG in August 2024"; the consultation closes 11 Nov 2026; "EFRAG intends to submit the final XBRL Taxonomy to
    ESMA and the European Commission by the end of 2026"; "Digital tagging of ESRS disclosures is not yet mandatory".
    ([EFRAG news, 17 Sep 2026](https://www.efrag.org/en/news-and-calendar/news/efrag-releases-draft-esrs-xbrl-taxonomy-for-the-revised-esrs-and-launches-public-consultation))
  - Licence: EFRAG's website disclaimer states reuse of its content "is prohibited without the prior written permission
    of EFRAG"; the package's own terms were not read (nothing downloaded).
- **Decided by the product owner, 2026-10-23 (decision tree in the XBRL session):** keep the named gap until EFRAG's final
  revised-ESRS taxonomy — do not bind the Aug-2024 set to the versions it covers (2023/2772; as amended by 2025/1416).
  Reasons on the record: tagging is not mandatory, EFRAG says the 2024 set is being replaced, and the licence wording is
  unclear. Re-check when EFRAG delivers the final (end-2026); then ask before downloading, read the package's licence,
  bind per ESRS version (the platform carries three: `esrs_fy2026_version`), validate with Arelle.
- **Hook (2026-09-30):** none yet, by design. The provisional `tesrs:` profile, `services/intelligence/esrs_taxonomy.py`,
  `esrs_xbrl.py` and `config/efrag_esrs_binding.json` were **removed** (E60), and the CSRD package's XBRL with invented
  element names retired (E66): an XBRL file under names EFRAG never published is not a filing. The ESRS statement
  exports JSON; every figure is a concept of `data/reference/esrs/concepts.json`, bound per version to the items the
  regulation prints — the binding to EFRAG elements will be one more mapping on those concepts.
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
- **When it lands:** build the concept → element binding from the taxonomy package (each element verified in the XSD),
  per ESRS version, and the iXBRL/ESEF export on it, tested with Arelle. The history above (16 CONCEPTS, `tesrs:`) is
  kept as the record of why the provisional profile was never a filing format. **Do not invent element IDs.**

## 2 · EBA Pillar 3 ESG taxonomy (P3DH DPM)  *(BUILT 2026-10-23 on the EBA's 4.2 package)*
- **What the EBA publishes (checked 2026-10-23):** reporting framework 4.2's taxonomy package (13 Jan 2026) carries the
  Pillar 3 data hub's ESG disclosure module ESGDIS 2.1.0 for Implementing Regulation (EU) 2024/3172 — its metadata states
  'FromReferenceDate 2026-03-31' and no end date. Framework 4.4 (final technical package, 12 Oct 2026) carries the ESG
  disclosures of the EBA's 'final draft amending Pillar 3 Implementing Technical Standards' (first reference date
  12/2026), which the Commission has not adopted — not bound (the platform runs the adopted text). Implementing
  Regulation (EU) 2026/722 (in force 16 Apr 2026) amends 2024/3172 for institutions' use of the EBA single access point.
- **Binding (data model):** `scripts/build_eba_p3esg_map.py` reads every datapoint's cell code from the EBA's table
  metadata and its row and column from the EBA's own labels, bound to the ITS cells of the spec
  (`data/reference/regspec/bank_p3esg/its_2024_3172.json`): 2,564 cells, the open tables' columns (Templates 3, 5 row
  13, 10) and their code-list members (IEA sector, NACE, instrument, counterparty), 0 EBA datapoints unbound. Every
  difference is recorded in `data/reference/eba/p3esg_xbrlcsv.4.2.json` 'differences': ITS cells with no datapoint (the
  greyed ones), EBA labels whose number differs from the ITS ('0.1 GAR', a 'qe.' for column ae), and Template 10's two
  'Other counterparties' rows bound by elimination.
- **Templates rebuilt to their instructions on the way (E339, decided 2026-10-23):** Template 3 is one row per IEA
  sector × Annex XL NACE code × metric (Annex XL point 4(e)); Template 5 row 13 is broken down by NACE section; the
  Annex XL crosswalk now equals the EBA's machine-readable list code for code (08.11, not 81.1).
- **Export:** format `xbrlcsv` (`services/governance/p3esg_xbrlcsv.py`, from the frozen filing): EBA file name, report
  package, parameters, a filing indicator for each of the 13 templates, one CSV per table. Refused, with the reason: a
  reference date before 31 Mar 2026; a whole-organisation filing (the data hub names a report individual or
  consolidated); an entity without its own LEI.
- **Validation:** `scripts/validate_p3esg_xbrlcsv.py` — Arelle on the EBA's Dictionary, Frameworks and latest rule set
  (SET 4.3.0.1, 14 Sep 2026), with the Eurofiling base files the EBA's entry point imports taken from EIOPA's pinned
  package (the EBA's package does not carry them); plus the EBA Filing Rules v5.8 for xBRL-CSV. The EBA's severity sets
  switch off all 2,743 ESGDIS assertions (as for every Pillar 3 disclosure module), so validation is the taxonomy's
  (datapoint, type, dimensions, code lists) and the filing rules'. Proven both ways: the package passes; a wrong amount
  or a NACE code outside the EBA's list fails.
- **Settled by the EBA's Q&A (checked 2026-10-23, the standing check for every regulatory reading; E341):** Template 2
  column p is 'the percentage of the exposures without EPC label of the collateral for which the institution is providing
  EP estimates' (Q&A 2022_6625, final, 17 Feb 2023), so column a = columns b-g + o × (1 − p): the platform computes it so
  (blank where an EP score does not say whether it is estimated), prints it as a percentage and the file carries it
  (pi977). ITS 2024/3172 keeps the 2022/2453 wording the Q&A answers. Template 3 column e is 'the nominal value' of the
  metric at its latest reference date (Q&A 2023_6859, final, 15 Dec 2023): the file (ri956) and the form carry the value
  at its year. Every reading in data/reference/eba/p3esg_xbrlcsv.4.2.json records the Q&As found (id, status, date, the
  EBA's words) or 'none found'.
- **Recorded, not open:** the EBA's checks that a Template 3 distance be zero or more were questioned twice and rejected
  as 'already identified and will be considered for the forthcoming release' (Q&As 2024_7100, 2024_7254); the platform
  writes the ITS formula's signed result, and release 4.2 switches those checks off. A blank cell has no fact, and the
  EBA's filing rule 1.7 lets its checks read it as zero in a template indicated as reported (no Pillar 3 Q&A found on
  blank cells). The accompanying narrative (K_00.03) is indicated as not reported: the platform holds no narrative per
  template.
- **When the amending ITS is adopted:** capture it on the change route, rebuild the binding from the EBA's 4.4 package
  (`scripts/build_eba_p3esg_map.py`) and pin it; the module is chosen by reference date.

## 3 · EUDR information system: registration + machine interface  *(customer, then us)*
- **Built (E108):** each shipment's due diligence statement is a filing (`services/eudr/filing.py`): prepared from the
  shipment once every blocking check passes, four eyes, attested, submitted; the reference and verification numbers
  the information system returns are recorded (`information_system` / `manual_entry` / `contingency`), then the
  72-hour amend / withdraw window and its closing events (IR 2024/3084 Art. 5) and an authority's rejection (Art. 8).
- **Not built — the live send.** The texts in the store (Regulation 2023/1115, IR 2024/3084 as amended) set what the
  system does, not its machine interface; no official interface specification is held. The earlier client
  (`traces_client.py`) used an invented request shape and was removed (E108). Until the specification is held, the
  operator submits the frozen statement in the information system and records the reference here.
- **Needed — customer:** register in the information system through EU Login (IR 2024/3084 Art. 3(c)).
- **Needed — us:** the Commission's published interface specification and test access; map the frozen statement
  (Annex II) to it field by field from the specification, then certify on the test system. Human sign-off before
  submission stays (the operator carries the liability).

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
- **Hook:** `services/governance/esrs_statement.py` (`_sensitive`) — the ESRS statement lists the undertaking's own
  sites whose H3 cell lies **inside** a loaded layer of a kind the ESRS glossary lists
  (`data/reference/esrs/biodiversity_sensitive.json`: a dataset counts only when `listed`, with the kind it is);
  support for the undertaking's own E4 figure (E4 counts the sites it negatively affects — its determination), shown
  on the ESRS statement page and as a support KRI. Never 'near' (the text gives no measure); the kinds not yet loaded
  are named as not assessed.
- **Loaded today:** `natura2000` (EU-27, 405,872 cells, listed) + `osm` (community, 54,818 cells — not a kind ESRS
  lists, so not counted). Sites outside the EU are disclosed as **not assessed**, never as "not in an area".
- **Needed:** the authoritative global layer — **WDPA** (World Database on Protected Areas). The free
  Protected Planet API (`scripts/ingest_wdpa_api.py`, `--token $PP_TOKEN`) is **non-commercial licence only**;
  a paying customer's filing needs a **commercial WDPA export via IBAT**, loaded through the file path
  (`scripts/ingest_natura2000.py`-style loader, tagged `--dataset wdpa`).
- **Owner:** licence is external (IBAT); obtaining + loading it is us — one ingest run and one reference-data row, no code change.
- **When it lands:** run the loader and add `wdpa` to `biodiversity_sensitive.json` with the ESRS kind it is (quoted);
  non-EU sites then report whether they lie inside a listed area. **Do not load the non-commercial API export into a
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
- EIOPA's Solvency II taxonomy 2.10.0 (published 3 July 2026, applicable from Q1 2027) adds rows to S.27.01.01 (and the
  same rows to a group's S.27.01.04, `s2704_xbrl.2.10.0.json`) for the
  regions Delegated Regulation 2026/269 introduces: flood DK, FI, LU, NL, NO, IE, SE (R1291–R1385), hail PL (R1702),
  subsidence BE and France (R1945–R1946) — `data/reference/eiopa/s2701_xbrl.2.10.0.json`. ITS 2023/894 as captured
  (spec `sii_qrt_natcat/its_2023_894`) has no such rows and the EU Cellar shows no amending act (checked 2026-09-30).
- **Built:** the 2027 calculation (2026/269); the form names every region without a row; the XBRL export for a 2027
  reference date refuses with the missing rows named, rather than report totals the rows don't add up to.
- **Needed:** the amending implementing act (or EIOPA's published ITS) → capture it on the change route as a new
  version of `sii_qrt_natcat`, extend `s2701.REGION_ROW`, sign off.

## 16 · EIOPA XBRL validation files  *(CLOSED 2026-10-23 — EIOPA's latest packages pinned and fetched by CI)*
- **Which package for which date (EIOPA's page, 2026-10-23):** "2.8.2 … is applicable from the Q42024 / annual 2024
  reference periods until Q4/Annual 2026 included"; its *Optional NACE 2.1 Hotfix* (30 Jun 2025) is the latest package
  for those dates — "this hotfix maintains the same schemas and entry points as the current system", "The update is
  instance backwards compatible"; "2.10.0 release will be applicable from Q1/2027 reporting reference period"
  (published 3 Jul 2026). **2.9.0 is not Solvency II** — it is EIOPA's Pension Funds taxonomy.
- **Pinned** in `data/reference/eiopa/s2701_xbrl.<version>.json` ('package', 'deactivations', 'verified'): file, address,
  size, SHA-256, EIOPA's licence (v1.4 of 07/10/2025 — commercial use and distribution allowed, naming EIOPA as owner
  and its download page). 2.8.2 also pins EIOPA's current deactivation list for the annual solo entry point
  (`deactivations/282/ars-ignore-val.xml`, 3 Jun 2026, 30 rules): the package's own copy, frozen at release, switches
  nothing off. Both cell maps were rebuilt from the packages (`scripts/build_eiopa_s2701_map.py`): 710 of 710 cells,
  0 differences.
- **Groups (E342, 2026-10-23):** EIOPA's annual group entry point (`mod/arg.xsd`, "Annual Solvency II reporting Group")
  carries S.27.01.04, not S.27.01.01; each of its cells is the solo data point with two more members — "Method of
  consolidation" = "Accounting consolidation-based method [method 1 and part of combination of methods 1 and 2]" and
  "Entities under consolidation" = "Insurance/reinsurance sector". Mapped in `s2704_xbrl.<version>.json` (710 of 710,
  0 disagreements with the annotated templates). EIOPA's current deactivation list for arg is pinned for 2.8.2
  (`deactivations/282/arg-ignore-val.xml`, 12,674 bytes, 3 Jun 2026, 17 rules; downloaded with the product owner's
  approval of 2026-10-23); for 2.10.0 none is published apart (404, 2026-10-23), the package's own copy (4 rules)
  applies. A group instance (a combination of methods: the method-1 part) passes on 2.8.2: no instance error, 21 rules
  evaluated, all in scope pass, BV264_1-2 needs the other sub-modules.
- **Validation:** `scripts/validate_s2701_xbrl.py` picks the package by the instance's entry point, refuses a file whose
  checksum is not the pinned one, links Eurofiling's function implementations from EIOPA's own package (iaf, math,
  isin-check, custom-margin, extra-functions — EIOPA's rules call them; no separate Eurofiling download) and EIOPA's
  deactivation list. Result on the 2.8.2 hotfix (2026-10-23): no instance error; 21 EIOPA rules evaluated on the
  engine-built instance (15 on the end-to-end filing), all pass except BV264, which needs the undertaking's man-made /
  other catastrophe sub-modules from its own package.
- **How CI gets it:** job `xbrl-validation` (`.github/workflows/ci.yml`) runs `scripts/fetch_xbrl_packages.py` — HEAD
  first, the pinned size and SHA-256 or refused, nothing else fetched — caches `.xbrl-packages/`, and runs
  `tests/unit/test_xbrl_packages.py` with `XBRL_VALIDATION_REQUIRED=1` (a missing package fails the job; the image build
  waits on it). Locally: `XBRL_PACKAGES_DIR=<dir> venv/bin/python -m scripts.fetch_xbrl_packages`, then the end-to-end
  test validates when `XBRL_PACKAGES_DIR` is set. The 2.10.0 validation runs once item 15 closes (a 2027 export is
  refused until then).

## 17 · Official SFDR PAI XBRL taxonomy  *(external artifact — none held)*
- **State (E113, 2026-10-02):** there is **no SFDR PAI XBRL or Inline XBRL export**. The earlier export
  (`ml/regulatory/sfdr_xbrl.py`, since v1.21, now removed) wrote instances under a Tellumen-made namespace
  (`https://taxonomy.tellumen.eu/sfdr/pai/2022`, schema `pai.xsd`) with element names and units of our own naming,
  labelled a placeholder to be swapped for an official taxonomy. An instance under invented element names is not a
  filing, so it was removed, as the ESRS (E60), EU Taxonomy (E95) and Pillar 3 (E104) XBRL were: `sfdr_pai` exports
  JSON and the workbook (`filings.EXPORT_FORMATS`); an `xbrl` or `ixbrl` request for a filing of any date is refused
  (409); `/v1/funds/{id}/sfdr-statement.xbrl`, `.ixbrl` and `/v1/entity/sfdr-statement.xbrl` answer 410 with the
  reason. Guard: `tests/integration/test_filing_export.py` (no `taxonomy.tellumen.eu` anywhere in services, api, ml).
- **What the regulation asks today:** RTS 2022/1288 Art. 4 — the participant "shall publish on their website" the
  statement (quoted in `data/reference/regspec/sfdr_pai/rts_2022_1288.json`); the workbook carries the Table 1 columns.
- **Re-checked 2026-10-23 — none is published:**
  - The ESAs' Final Report on draft RTS (JC 2023 55, 30 Nov 2023) proposed: "Financial market participants shall
    prepare the information required by this Regulation in XHTML format and shall mark up the information contained
    therein using the XBRL markup language" — a draft that names no taxonomy.
  - It was not adopted: the EU's Cellar register lists one act amending Delegated Regulation 2022/1288 — Delegated
    Regulation 2023/363 (in force 20 Feb 2023), which is about taxonomy-aligned investment disclosures, not XBRL.
  - SFDR itself is under review: "Pending the outcome of the Level 1 negotiations on the Sustainable Finance Disclosure
    Regulation (SFDR), ESMA, together with the EBA and EIOPA, will start preparing for potential technical input"
    (ESMA22-1669215091-6873, 28 Sep 2026); "The SFDR proposal already includes an amended timeline for the submission
    of information to ESAP" (same, §71).
- **Needed:** an official SFDR PAI XBRL taxonomy package — not published.
- **When it lands:** bind each Table 1 indicator of the governing specification (`data/reference/regspec/sfdr_pai`) to
  its element, every element verified against the taxonomy package (not a PDF), validate the instance with the
  publisher's rules, then offer the format again. **Do not invent element IDs.**

## 18 · Coastal flood inundation maps — WRI Aqueduct Floods  *(RESOLVED 2026-10-23)*
- **State (2026-10-23):** WRI's host answers again at the same address (`https://aqueduct.wridata.org/AqueductFloods20/<file>`, all 410 `inuncoast_*` files, re-uploaded 2026-03-27); the old S3 path still answers 404. Fetched with the product owner's approval (2026-10-23): with subsidence, the present day and RCP4.5/RCP8.5 for 2030, 2050 and 2080 at the 5th, 50th and 95th percentile of sea-level rise, nine return periods (2–1,000 years) — 171 files, 8.07 GB, each checksummed (`scripts/fetch_aqueduct_coastal.py`, `data/reference/supply_datasets.json` aqueduct_floods_coastal).
- **Built:** layer `aqueduct_coastal_flood` (`data/reference/hazard_intensity_layers.json`) — the sea (the maps' no-data) is outside the map, never dry; coastal flood is a peril of the loss engine (`services/loss/engine.LAYERS`), read through the adopted depth curves (the JRC curves serve coastal flood on WRI's own statement, `also_perils`; a coastal figure is untested — the curves' test was run on river floods); undefended and labelled so; projected on the one timeline (`services/loss/projection.py`; central the 50th percentile, range the 5th–95th).
- **Open:** coastal defences (item 20); a pre-registered test on observed coastal losses (NOAA Storm Events 'Storm Surge/Tide', held) before any coastal figure is published.

## 19 · Building-level flood loss records for the European damage curves  *(external data — licence on request only)*
- **State (2026-10-23):** the European Huizinga (2017) flood curves are held: their only test, on HANZE's regional losses (2026-10-20), ranks regions almost alike for every curve and cannot judge one. A curve's level is judged only by records giving, per building, the water depth, the damage in money and the building's value. The search of 2026-10-23 (landing pages, licences and data dictionaries; product owner's request) found none under an open licence in Europe.
- **Where the records are, and on what terms:** HOWAS 21 (GFZ Potsdam; about 8,300 German and Austrian objects with depth, loss, value and loss ratio) — registration and a signed contract, Group II scientific or non-commercial only, and 'It is not allowed to publish data sets (in whole or in part)'; Secchia 2014 (1,330 buildings, Carisi et al. 2018) 'not publicly accessible for privacy reasons'; Adda 2002, Bacchiglione 2010 and Secchia 2014 (1,158 buildings, Amadio et al. 2019) 'available upon request'; Lodi 2002 (345, Molinari et al. 2020) compensation forms 'confidential'; Limburg 2021 households (4TU.ResearchData 10.4121/21603348) under a 'Restrictive Licence'; Vesdre 2021 (420) and the 2021 Rhineland-Palatinate / North Rhine-Westphalia surveys (277 + 332) on request; Wallonia's Disaster Fund claims (about 27,000) shared only in aggregate.
- **Open, but not enough:** Marche 2022 (Zenodo 10.5281/zenodo.17457884, CC BY 4.0, 256 buildings with depth) records damage as areas, counts and repair type — its only money is clean-up cost ('Only two values have been recorded, equal to 45 and 35000' for homes) and no building value (data dictionaries read 2026-10-23); Paprotny et al. 2021 (figshare 10.6084/m9.figshare.12045345, CC BY 4.0) has German household loss and value but no depth; Copernicus EMS grading, the Ahr 2021 grades and Braunsbach 2016 give damage grades, not money — a ranking by depth is the same for every rising curve, so grades cannot judge one.
- **When it lands:** a data-use agreement that allows commercial use and publishing the result → register the test in `loss_protocol.json` before the damage is read (as `published_curve_test_commercial`), run it per curve, record each result on the curve; standings follow (`services.loss.engine.standing`).

## 20 · Coastal flood protection standards  *(BUILT for Europe 2026-10-23)*
- **Built:** COASTPROS-EU (Zenodo record 15024139, CC BY 4.0, published 2025-03-14; `scripts/fetch_coastpros.py`, MD5 = the record) registered as `coastpros_eu` (`data/reference/hazard_intensity_layers.json` protection_layers): the coastal NUTS2 region holding a location, its 'SUMMARY RETURN PERIOD' read by the product owner's rule of 2026-10-23 — a single number is the level; a plain range a–b gives a defended range (low with defences at the upper level, high at the lower), no central figure; a list, a condition or a note: protection unknown. Applied with the registered rule (loss_protocol flood_protection), on WRI's statement that its protection standards cover 'both riverine and coastal floods'. Demo REIT Randstad Offices: €68.1m a year undefended → €46k–€139k defended on 65 of 77 properties; 12 protection unknown.
- **Open:** outside Europe's listed coastal regions, and in the 39 regions whose entry is not a level or is empty, protection is unknown; a defended projection stays a named gap (as for river flood).

## 21 · Global Energy Monitor trackers  *(external — site down, form download)*
- **State (2026-10-23):** every globalenergymonitor.org address answered HTTP 520; the trackers' downloads sit behind a form with a human check. GLEIF publishes a GEM entity id → LEI mapping (`LEI-GEM-<date>.zip`), so tracker plants could be tied to issuers by LEI as Climate TRACE's are.
- **When it lands:** the tracker files (licence to read from GEM's own page first) → join by GEM entity id → GLEIF LEI → issuer; weight not stated, as every register site.

## 22 · Observed European windstorm losses  *(external data — licensed or not released)*
- **State (2026-10-25):** European windstorm is a loss peril of its own (the product owner's decisions of 2026-10-25): each winter storm's highest 3-second gust from the PRIMAVERA event set (Zenodo 10.5281/zenodo.6492182), read by return period as the cyclone maps are, through the Prahl et al. (2015) curve for residential buildings in Germany. Every figure is 'untested': no record could be found to test the curve on.
- **Where the records are, and on what terms (search of 2026-10-25):** GDV's district-by-day losses and insured values (the data the curve was calibrated on, 1997–2007) were provided to the authors, not released; GDV's public statistics give storm and hail as one figure by state and year, and its terms do not allow economic use of the material as such; Spain's Consorcio de Compensación de Seguros pays wind only above 120 km/h gusts (135 km/h before 2011), publishes insured capital for 2025 only and does not allow third parties to market its content; Swiss cantonal building insurers give storm loss and insured capital by canton and year (several storms mixed, terms not stated); PERILS' loss and exposure by CRESTA zone are licensed only ('illegal and expressly forbidden' otherwise); EM-DAT needs a paid licence for commercial use.
- **When it lands:** a data-use agreement that allows commercial use and publishing the result → register the test in `loss_protocol.json` before the losses are read (as `published_curve_test_commercial`), run it, record the result on the curve; standings follow (`services.loss.engine.standing`).

## 23 · PRIMAVERA windstorm event set — licence to confirm  *(external — the publisher's confirmation)*
- **State (2026-10-25):** the event set's record (Zenodo 10.5281/zenodo.6492182) states 'ogl-uk-3.0', and its documentation: 'Users of the event set must agree to the terms and conditions in the Open Government Licence v3.0', with a set attribution sentence (shown on the loss screen). Each footprint file also carries its source model's CMIP6 'license' attribute (read from the files at the build of 2026-10-25, every run's recorded in `data/reference/supply_datasets.json` primavera_windstorm_compact): CMCC, EC-Earth-Consortium, MOHC (Met Office) and MPI-M — 'Creative Commons Attribution-ShareAlike 4.0 International License'; CNRM-CERFACS (CNRM-CM6-1 and CNRM-CM6-1-HR, 128 of the 1,332 winters) — 'Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License'.
- **Decided (product owner, 2026-10-25):** build now; confirm with the Met Office before any customer use.
- **When it lands:** the publisher's written confirmation that OGL v3.0 governs the event set as published → recorded on the event set (`data/reference/event_sets.json` licence_basis) and this item closed; otherwise the figures stay off customer outputs and the licence is settled with each model's institution (for CNRM-CERFACS's non-commercial attribute, or the set rebuilt without its two runs — a product owner's decision).

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
