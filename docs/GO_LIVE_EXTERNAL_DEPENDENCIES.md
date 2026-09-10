# Go-live — external dependencies tracker

**What this is:** the short list of things that stand between *built & verified in the product* and *live for a
paying customer's real filing*, where the remaining step is **external** — an artifact a third party must publish,
a credential/registration only the customer can obtain, or data we must be given. The **mechanism for each is
already built and tested**; this file exists so none of these is forgotten when the external piece lands.

Companion docs: agri last-mile detail is in [`AGRI_OPS_READINESS.md`](AGRI_OPS_READINESS.md). Every item below
degrades honestly in-product today (shows "pending" / "prepared" / withholds the figure) — nothing is faked.

_Last reviewed: 2026-09-03._

## Status at a glance

| # | Item | Area | Built (ready) | Blocking | Hand Tellumen → we finish it |
|---|------|------|---------------|----------|------------------------------|
| 1 | EFRAG ESRS Set 1 taxonomy element map | Agri / CSRD iXBRL | tagging + iXBRL/ESEF engine + validator + drop-in binding seam | EFRAG adoption (Omnibus timing) | the published element-name list → drop `config/efrag_esrs_binding.json` |
| 2 | EBA Pillar 3 ESG element map | Bank Pillar 3 XBRL | well-formed XBRL + drop-in binding seam, verified ITS refs | EBA taxonomy publication (P3DH) | the DPM element IDs → drop `config/eba_p3esg_binding.json` |
| 3 | EUDR operator registration + TRACES creds | Agri / EUDR submit | `prepared` mode + live config-flip | customer registration | sandbox creds + published DDS schema → we align + certify |
| 4 | Production geocoder provider + key | Agri (address→coords) | cache + QA + provider seam | provider choice + licence | provider + API key → we write the adapter |
| 5 | More crop calibration data | Agri model | fit + out-of-sample validate pipeline | real climate-attributable data | a crop×origin yield/climate series → we fit + validate |
| 6 | WDPA global protected-area layer | Agri / ESRS E4-5 | dataset-agnostic overlap engine + ingest script + E4 filing wiring | commercial data licence (IBAT) | an IBAT-licensed WDPA export → we load it, non-EU assets light up (no code change) |

---

## 1 · EFRAG ESRS Set 1 taxonomy element map  *(external artifact)*
- **Hook:** `config/efrag_esrs_binding.json` (override env `EFRAG_ESRS_BINDING`), consumed by
  `services/intelligence/esrs_taxonomy.py`. No file present → profile honestly reports
  `pending_adopted_taxonomy`, `bound=false` per concept; the `provisional` (`tesrs:`) profile works meanwhile.
- **Needed:** the adopted EFRAG ESRS Set 1 XBRL taxonomy element names (our concept key → official element ID).
- **Owner:** EFRAG publishes it; obtaining + dropping it in is us.
- **When it lands:** write the JSON, flip `efrag_set1` to bound, re-run `/esrs-pack.validate` (+ Arelle if installed). ~1h, no code change. **Do not invent element IDs.**

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

## 7 · Solvency II standard-formula EXACT zonal figure  *(ENGINE BUILT — remaining is per-country data)*
- **Status:** the **exact-zonal engine is built** (`services/governance/solvency2_natcat.py`, `_exact_zonal_loss`).
  It is the vendor-standard design: keyed off a **`cresta_zone`** field on each policy (added to the SoV upload +
  `ext_insurance.cresta_zone` column, migration `ext_ins_cresta_zone_20260906`) — because a Statement of Values
  normally already carries the CRESTA/postcode zone per risk. For any region whose Annex tables are loaded AND whose
  policies carry a zone, it computes `L_r = Q·sqrt(ΣΣ Corr(i,j)·W_i·SI_i·W_j·SI_j)` — the exact figure, with the
  Annex X risk weights and Annex XXIII-XXVI within-country diversification. No boundary geodata is needed on this
  path (the book carries the zone). Regions without loaded tables / zone tags use the country-level approximation.
- **Loaded today — all five major markets + Croatia:** **Germany** (windstorm/EQ/flood/hail, 95 postcode zones), **France** (all four + **subsidence**, 95 département zones — subsidence is now exact-zonal too), **Spain** (windstorm/hail, 50), **Italy** (EQ/flood/hail, 92 postcode zones incl. CAP 00), **UK** (windstorm/flood, 124 postcode-AREA letter zones), **Croatia** (EQ, 21 admin units) — in `data/reference/solvency2_zonal.json`. All extracted programmatically from the OJ PDF and validated (complete weights, symmetric, unit diagonal, weight-zone set == matrix-zone set, formula-reproduction tests). Zone ids are **labels** (numeric or letter), correlation is id-keyed. **One source-document defect handled honestly:** the printed OJ Annex XXIV UK flood table omits the SN (Swindon) column; it is reconstructed by symmetry from the printed SN row (the property the Article defines) and disclosed in the table's `source_note`.
- **Extraction recipe (reuse for the next country):** pdfplumber positional words grouped by y; the column-id header is a row of many integers (not a `ji` token); data rows are `int + many decimals`; stop at the next country's title row at ROW level (the next title can sit lower on the same page — a page-level stop silently drops the tail rows); Annex X weights use a sequential zone INDEX while the matrices use the Annex IX zone id — bridge via Annex IX (for postcode countries: index k = the k-th existing 2-digit postcode).
- **Remaining — per-country DATA (not blocked):** load each country's Annex IX zones + Annex X weights + Annex
  XXIII-XXVI zone-correlation into the same JSON shape. Priority is the **postcode-zoned majors DE/FR/ES/IT/UK**
  (where insurers' books and capital actually sit), extracted the same way from the OJ PDF we hold. Wide matrices
  (e.g. RO 41×41) span PDF pages in column-blocks and need block-aware parsing; that is transcription effort, not an
  external dependency.
- **Optional fallback (coordinate-only books):** a book with lat/lon but no `cresta_zone` can be zoned by
  point-in-polygon against boundary geodata (Eurostat NUTS for admin-unit countries — free; CRESTA/postcode layers
  for the rest). This is only needed when the insurer did NOT provide the zone; the primary path does not require it.
- **Needed for the exact figure:** the per-zone risk weights (**Annex X**) and the intra-country zone-correlation
  matrices (**Annex XXII windstorm / XXIII earthquake / XXIV flood / XXV hail / XXVI subsidence**) — all in the OJ,
  transcribable — PLUS the blocker: **Annex IX** defines the zones by **postcode area / administrative unit**, so
  assigning each insured location to its EIOPA zone needs **postcode / admin boundary geodata** (per country) to
  resolve a lat/lon → zone. That boundary geodata is the external dependency; without it, sum-insured-by-zone
  cannot be computed and the exact zonal formula cannot run (faking zone assignments is not an option).
- **The zones (confirmed):** EIOPA uses **CRESTA-2010** zones, mostly **2-digit postcode areas** (e.g. Romania has
  47 zones = 2-digit postcode areas), a few countries by **administrative unit**. The zone→geography mapping (which
  postcode / admin unit is which zone) is **Annex IX** of Del. Reg. 2015/35 — free, in the OJ PDF we already hold
  (`data/eiopa/delreg_2015_35_original.pdf`). What is missing is only the **polygons** to turn a lat/lon into a
  2-digit postcode / admin unit.
- **Concrete boundary-geodata sources (the external piece):**
  - **Admin-unit countries (BG, HR, HU, RO) — FREE, do first:** Eurostat **GISCO NUTS** boundaries
    (`https://ec.europa.eu/eurostat/web/gisco/geodata/statistical-units/territorial-units-statistics`), open with
    attribution — their counties map straight onto the Annex IX admin-unit zones. Zero licence, closeable immediately.
  - **Postcode countries (the majority: AT BE CH CZ DE DK ES FR IE IT NL NO PL SE UK) — 2-digit postcode polygons:**
    free national/open sources where they exist — **UK ONS** postcode boundaries (Open Government Licence),
    **DE/NL/etc.** OSM-derived 2-digit-postcode (PLZ) polygons (e.g. `suche-postleitzahl.org`/OSM, open) — and for
    a single clean pan-EU layer, the **CRESTA** zone GIS layers (`cresta.org`, the reference the regulation is built
    on): low-resolution CRESTA is free, the high-resolution (2-digit) layer is CRESTA-membership / licensed.
- **Owner:** boundary geodata is external (Eurostat NUTS is free; postcode polygons free where published, else a
  CRESTA/commercial layer). Transcribing Annex X weights + Annex XXII-XXVI zone-correlation, the point-in-polygon
  lat/lon→zone lookup, and the zonal aggregation are us.
- **When it lands (phased):** (1) load Eurostat NUTS → exact zonal figure for the admin-unit countries now, free;
  (2) add free national postcode polygons (UK, DE, NL…) country-by-country; (3) a licensed CRESTA/commercial layer
  closes the remainder. Each phase replaces the country-level approximation with the exact zonal SCR for those
  countries (typically LOWER — it takes within-country diversification credit). Until then the country-level figure
  is a documented, cited approximation, disclosed on the Solvency page and in the S.26.01 filing.

## Copernicus EGMS (European Ground Motion Service) account

Needed to download InSAR ground-motion products (the observed target that would let the subsidence channel be backtested properly; GNSS velocities only reach rank correlation 0.21). Free registration at egms.land.copernicus.eu; download is token-gated. Added 2026-09-10.
