# Go-live — external dependencies tracker

**What this is:** the short list of things that stand between *built & verified in the product* and *live for a
paying customer's real filing*, where the remaining step is **external** — an artifact a third party must publish,
a credential/registration only the customer can obtain, or data we must be given. The **mechanism for each is
already built and tested**; this file exists so none of these is forgotten when the external piece lands.

Companion docs: agri last-mile detail is in [`AGRI_OPS_READINESS.md`](AGRI_OPS_READINESS.md). Every item below
degrades honestly in-product today (shows "pending" / "prepared" / withholds the figure) — nothing is faked.

_Last reviewed: 2026-08-13._

## Status at a glance

| # | Item | Area | Built (ready) | Blocking | Hand Tellumen → we finish it |
|---|------|------|---------------|----------|------------------------------|
| 1 | EFRAG ESRS Set 1 taxonomy element map | Agri / CSRD iXBRL | tagging + iXBRL/ESEF engine + validator | EFRAG adoption (Omnibus timing) | the published element-name list → we write the binding JSON |
| 2 | EBA DPM element map | Bank Pillar 3 XBRL | well-formed XBRL, provisional namespace | none (EBA DPM is published) | the DPM element IDs → we swap the namespace |
| 3 | EUDR operator registration + TRACES creds | Agri / EUDR submit | `prepared` mode + live config-flip | customer registration | sandbox creds + published DDS schema → we align + certify |
| 4 | Production geocoder provider + key | Agri (address→coords) | cache + QA + provider seam | provider choice + licence | provider + API key → we write the adapter |
| 5 | More crop calibration data | Agri model | fit + out-of-sample validate pipeline | real climate-attributable data | a crop×origin yield/climate series → we fit + validate |

---

## 1 · EFRAG ESRS Set 1 taxonomy element map  *(external artifact)*
- **Hook:** `config/efrag_esrs_binding.json` (override env `EFRAG_ESRS_BINDING`), consumed by
  `services/intelligence/esrs_taxonomy.py`. No file present → profile honestly reports
  `pending_adopted_taxonomy`, `bound=false` per concept; the `provisional` (`tesrs:`) profile works meanwhile.
- **Needed:** the adopted EFRAG ESRS Set 1 XBRL taxonomy element names (our concept key → official element ID).
- **Owner:** EFRAG publishes it; obtaining + dropping it in is us.
- **When it lands:** write the JSON, flip `efrag_set1` to bound, re-run `/esrs-pack.validate` (+ Arelle if installed). ~1h, no code change. **Do not invent element IDs.**

## 2 · EBA DPM element map  *(us, needs published DPM)*
- **Hook:** bank Pillar 3 XBRL export uses a provisional namespace `_P3_NS =
  https://taxonomy.tellumen.eu/p3esg/2024` in `services/governance/filing_export.py`. Concept QNames are
  self-describing and mappable to the official **EBA DPM** element IDs for the ITS 2022/2453 templates.
- **Needed:** the EBA DPM element IDs for the Pillar 3 ESG templates (the DPM *is* published).
- **Owner:** us — obtain/confirm the DPM element list, then map (optionally add a binding-config seam mirroring ESRS).
- **When it lands:** swap the namespace / add the element IDs; re-verify the instance. **Map, don't guess.**

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
