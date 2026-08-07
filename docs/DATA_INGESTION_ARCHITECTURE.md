# Data Ingestion & Sourcing Architecture

*How every datapoint a regulator wants gets into Tellumen — where it comes from, how it enters, and how its
provenance is tracked. This is the functional architecture behind the filing-coverage map, the Data
Dictionary, and the customer data-onboarding guide.*

---

## 1. The two axes

Every regulatory datapoint is classified on two axes. The single source of truth is
[`services/governance/datapoint_catalog.py`](../services/governance/datapoint_catalog.py) (`CATALOG`).

### Source category — where the data originates

| Category | Meaning | Examples |
|---|---|---|
| **tellumen** | Our engine + authoritative feeds produce it (the moat: physical & nature risk) | value-at-risk, EAL, water-stress, deforestation, financed emissions |
| **egov** | A **free** government/agency dataset we self-integrate as a feed | WDPA/Natura 2000 biodiversity areas, EPC registers, emission factors, UNGC list |
| **evendor** | A **commercial** 3rd-party dataset the customer licenses (we connect) | issuer ESG/emissions, carbon-tool output, controversy screening |
| **customer** | Customer-proprietary — their systems, their judgement, their narrative | activity data, Taxonomy alignment determination, transition plan, EUDR legality |
| **none** | Not produced by this platform (a genuine gap) | carbon-price transition-risk modelling |

### Ingestion lane — how the value reaches a filing

| Lane | Your term | What happens | Built on |
|---|---|---|---|
| **compute** | — | Tellumen computes it from its own feeds/engine, no customer step | hazard engine + feed registry |
| **granular** | *inputted granular, processed by Tellumen* | Customer uploads raw records; our engine processes them into the value | self-service upload + token API + golden source |
| **provided** | *calculated on the customer/vendor side, given to us for recon* | A pre-calculated value comes in; we **reconcile** it against our own number + attest | vendor-ingest + cross-check + 4-eyes overrides |
| **report** | *needed only at the report level as final input* | A value/statement captured on the filing form (narrative, flag, final figure) | filing form + narratives editor + cell overrides |
| **none** | — | n/a (out-of-scope) | — |

The customer-facing **coverage bucket** is *derived* from the lane, so the catalog is the only place to edit
when sourcing changes:

```
compute / granular → "computed"      (produced from your data)
provided           → "integrated"    (needs your input / feed)
report             → "client"        (you author)
none               → "out_of_scope"  (not covered)
```

---

## 2. The three ingestion lanes (functional)

### Lane 1 — Granular → we process  *(EXISTS, extend)*
Customer's raw records in, our engine computes the metric out.
- **Surfaces:** per-vertical CSV/xlsx upload templates + the direct-integration API (`tlm_live_…` token) — one
  shared validated core, [`services/ingest/portfolio_ingest.py`](../services/ingest/portfolio_ingest.py).
- **Store (golden source):** `portfolio_entities` + `canonical_scores` (H3-indexed), read by the engine.
- **Validation:** required-field checks, skip-with-reason (never guess), coordinate-range + H3 geocode, audit row.
- **Extend for:** per-exposure Taxonomy alignment flags (the loan template already carries
  `minimum_safeguards_status`), measured water, any new raw input.

### Lane 2 — Pre-calculated → we reconcile  *(GENERIC-FIRST, new)*
A value already computed on the customer or vendor side comes in; Tellumen stores it with provenance and
**reconciles** it against its own computed value where one exists.
- **Pattern to generalise:** [`services/reference/vendor_ingest.py`](../services/reference/vendor_ingest.py)
  (column-mapping vendor profiles, `source='vendor'`, precedence **client › vendor › estimated**) +
  [`filing_crosscheck.py`](../services/governance/filing_crosscheck.py) (tolerance recon) +
  [`filing_overrides.py`](../services/governance/filing_overrides.py) (4-eyes, original-vs-proposed preserved).
- **New:** a datapoint-level *provided-value* store keyed by the catalog datapoint, a recon rule per datapoint
  (`recon_tol` in the catalog), a divergence flag, and a 4-eyes attest step. Vendor-agnostic first (accept a
  standard schema from any customer/vendor); named connectors (MSCI/ISS/carbon tools) slot in later.

### Lane 3 — Report-level final input  *(EXISTS in part, generalise)*
A value/statement needed only on the filing itself.
- **Built on:** [`filing_form.py`](../services/governance/filing_form.py) `build_form` (datapoint-by-key),
  the SFDR narratives editor, and cell-level overrides.
- **Extend for:** a per-framework narrative / flag / final-figure capture (transition plan, alignment
  determination, governance statements) with `source` provenance.

---

## 3. Provenance model  *(EXISTS)*

Every value carries where it came from and when:
- **Scores:** `canonical_scores` — `model_version`, `model_id`, `data_vintage`, `scored_at`,
  `regulatory_fingerprint`, CI band, SHAP factors, `score_lane`.
- **Reference data:** `source` (`gleif|client|vendor|estimated|…`) + `data_vintage` + `estimation_method` on
  `issuers` / `securities` / `issuer_facilities` / `issuer_emissions`; append-only `reference_resolution_log`.
- **Feeds:** the in-code registry `services/data/feeds.py` (`FEEDS`) links each hazard to its source feeds
  (`HAZARD_FEEDS`); freshness/refresh tracked in append-only `feed_refresh_log`.
- **Freeze:** `report_snapshots` (WORM) — `payload_sha256` (re-verified on read) + `engine_versions`
  (impact/fit versions, feed maturity, feed freshness at freeze, code git-sha).
- **Lineage:** `filing_lineage.py` — filing cell → assets → `canonical_scores` → feeds, with model-version
  drift detection; and the reverse (H3 cell → holdings → filings).

The **source precedence** when the same datapoint arrives from more than one place: **customer (client) ›
vendor › global/estimated** — a customer-provided or reconciled value always wins over an estimate.

---

## 4. External data collection (source = egov / evendor)

New free-gov feeds are added to the feed registry the same way our hazard data flows in:
1. append a dict to `FEEDS` (`services/data/feeds.py`) with `key`, `category`, `cadence_days`, `maturity`;
2. add an adapter under `services/ingestion/adapters/` (or a reference loader under `scripts/` writing to
   `data/reference/*.csv` with `source` + `data_vintage`, like `build_country_intensities.py`);
3. wire `register_refresh_hook(key, fn)` for scheduled pulls; the Data Dictionary surfaces it automatically.

Priority order (each flips its catalog datapoint's source/lane): **protected-area biodiversity** (ESRS E4) →
**emission factors** (DEFRA/EPA/IPCC) → **EPC registers** (UK/IE) → **UNGC participants**. Commercial (evendor)
datasets — ESG/emissions, carbon-tool output, controversy screening — connect through the Lane-2 generic
provided-value ingestion, extended with named vendor profiles.

### Feed licensing (important)

Not every "free" dataset is free for a commercial product — each feed carries an `attribution` and its licence
position:

- **EEA Natura 2000 (EU)** — reusable, incl. commercially, under the EEA re-use policy **with acknowledgement**;
  attribution is surfaced in-product. This is our EU protected-area base.
- **OpenStreetMap (global)** — FREE and commercially usable under **ODbL** with attribution ("© OpenStreetMap
  contributors"); our free non-EU coverage layer where WDPA is licence-gated. Fetched per-country via the
  Overpass API (`scripts/ingest_osm_protected.py`). Community-sourced (uneven) — an honest **screening layer**,
  labelled as such, not an authoritative agency feed. ODbL share-alike bites only if the derived H3 database is
  *redistributed* (it isn't). The overlap query spans it alongside Natura 2000 automatically.
- **WDPA · WD-OECM · KBA (global)** — the **free Protected Planet download is NON-commercial only**. Commercial
  use (a for-profit product, or serving results to customers) requires a paid **IBAT licence**
  (ibat-alliance.org — UNEP-WCMC & IUCN / KBA Partnership), which is the standard channel for corporate/financial
  TNFD & ESRS E4 biodiversity screening and bundles all three. IBAT delivers GeoPackage/Shapefile (→ the
  multi-format file loader `scripts/ingest_natura2000.py`) and a token API. The overlap pipeline is
  source-agnostic, so switching from the free download to the licensed IBAT file/API is a **data + licence
  change, not a code change**. The Protected Planet token-API loader (`scripts/ingest_wdpa_api.py`) is for
  non-commercial evaluation only — the commercial global load runs the licensed IBAT file through the file loader.

---

## 5. Where this is documented

- **Functional architecture** — this document.
- **Data Dictionary** (in-product) — surfaces each datapoint's source-category + ingestion lane, read live
  from the catalog.
- **Customer-facing** — a per-sector data-onboarding guide (what you provide, in what form, which lane) +
  the filing-coverage panel showing each item's lane and how to provide it.
- **Change log** — `docs/SOFTWARE_DESCRIPTION.md`.
