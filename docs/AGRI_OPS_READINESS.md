# Agriculture — operational readiness runbook

**Audience:** whoever takes a design-partner from "the demo works" to "our real CSRD/EUDR filing went out
on our numbers." **Question it answers:** what stands between *built* and *in production for a paying
customer's real, assured filing* — and who does each piece.

Everything in [AGRI_REGULATORY_SCOPE.md](AGRI_REGULATORY_SCOPE.md) is about *which* regulation is ours.
This is about the **non-code operational gaps** on the ones we own. Each item is one of:

- **READY** — works in production as-is.
- **GAP (us)** — code/integration work still on our side.
- **GAP (customer)** — a registration, credential or sign-off only the customer can do.

Honesty rule carries through: we never let a demo convenience read as production-ready. Where a step is
still manual or provisional, the product says so on the page, and so does this doc.

---

## 1. EUDR → TRACES submission

| | |
|---|---|
| **Status** | Tier 1 **READY**; Tier 2 client **READY (v1.48)** — prepared/dry-run by default, config-flip to live; only the operator registration + official field alignment remain external |
| **Built** | `assemble_dds()` produces a per-consignment Due Diligence Statement from the plot polygons + satellite forest-loss determinations, with blocker/readiness reasons; the operator can file it and key the reference back (Tier 1). **Tier 2** (`services/intelligence/traces_client.py`): `build_submission()` maps the DDS to a TRACES-shaped envelope; `submission_preview()` (`GET /v1/supply/eudr/submission-preview`) shows exactly what would be filed, no side effects; `submit_dds()` (`POST /v1/supply/eudr/submit`, audited) runs in **`prepared`** mode by default (builds + completeness-checks the envelope, files nothing) and flips to **`live`** only when `TRACES_MODE=live` + `TRACES_BASE_URL` + `TRACES_API_TOKEN` are set. A "Prepare TRACES submission" button sits on the Disclosure page beside the Tier-1 capture. |
| **Gap** | Two external items only: **(customer)** register as an EUDR operator in the EU Information System and provide API credentials; **(us, data-not-code)** align the envelope field names to the published EUDR IS / TRACES DDS schema (flagged in every response). Live mode without creds returns an explicit `not_configured` — never a fake success. |
| **Owner action** | Customer completes operator registration and shares sandbox/prod API access; we confirm the field mapping against the published schema and certify against the sandbox before prod. |
| **Do NOT** | Auto-submit before the customer has reviewed. EUDR liability sits with the operator; the human sign-off stays. |

## 2. XBRL / EFRAG taxonomy binding

| | |
|---|---|
| **Status** | **GAP (external artifact) — no ESRS XBRL is produced.** The ESRS statement exports JSON (2026-09-30). |
| **Built** | The statement itself, per undertaking and financial year, every figure keyed by a concept (`data/reference/esrs/concepts.json`) bound to the items each ESRS version prints — the layer an element binding will map from. |
| **Removed** | The provisional `tesrs:` tagging engine, its iXBRL/ESEF shaping and validator (`esrs_taxonomy.py`, `esrs_xbrl.py`, the `/esrs-pack.ixbrl` endpoints) were removed in E60, and the CSRD package's E1-9 XBRL in E66: they tagged the platform's own metrics under element names EFRAG never published — not a filing format. |
| **Gap** | EFRAG's taxonomy for the ESRS as amended (the Aug-2024 Set 1 taxonomy is being superseded; mandatory tagging is suspended until the ESEF RTS is updated — `docs/GO_LIVE_EXTERNAL_DEPENDENCIES.md` item 1). |
| **Owner action** | **(us)** When final: build the concept → element binding from the taxonomy package (each element verified in the XSD) and the iXBRL/ESEF export on it, tested with Arelle. |

## 3. Geocoder productionization

| | |
|---|---|
| **Status** | Caching + QA + provider seam **READY (v1.49)**; only pointing at a paid/self-hosted provider (an API key + URL) remains — a config change |
| **Built** | Address → coordinate resolution via **Nominatim** with a shared thread-safe rate limiter + street→city→country ladder, now wrapped by a **cache-aware, provider-swappable front door** (`services/geocoding/geocoder.py`): every resolved query is persisted in **`geocode_cache`** (keyed on provider + normalized query + limit) so repeated/bulk uploads hit Postgres, not the provider; each candidate carries a real **confidence + precision + `low_confidence`** flag (derived from Nominatim `importance`/`addresstype`, replacing the old flat 0.6), and the autocomplete **warns on a coarse (city/region/country-level) hit**. `GEOCODER_PROVIDER` selects the backend. |
| **Gap** | Only the last config step: point `GEOCODER_PROVIDER` + URL/key at a **self-hosted Nominatim or a paid geocoder** (Google/HERE/Mapbox) for a real SLA at volume. The cache, the QA flag and the swap seam are done. |
| **Owner action** | **(us/customer)** choose and configure the production provider; no code change. |
| **Positioning** | The *hazard* data stays direct from Europe's & America's satellites & agencies (Copernicus/ECMWF, NASA/USGS). Geocoding is a separate, swappable utility; upgrading it does not touch the golden source. |

## 4. Assurance evidence pack

| | |
|---|---|
| **Status** | **READY (v1.47)** — primitives *and* the packaged auditor bundle |
| **Why** | CSRD requires **limited assurance** now (moving toward reasonable). The assurer will ask *how* each number was produced and *who could change it*. |
| **Built** | We already hold every primitive an auditor asks for: the **model-validation / backtest record** (per crop × origin, with r² and the retired-price-claim honesty note), the **`access_audit_log`** (who did what, when), **4-eyes approvals** on material edits and deletes, **provenance** on every reference table, the **honesty gate** (€ withheld where the hazard→yield chain doesn't clear r²≥0.40), and now **immutable report snapshots** — the exact bytes as filed, on a frozen basis. |
| **Built** | `services/governance/assurance_pack.py` → `GET /v1/supply/report-snapshots/{id}/assurance-pack` returns a **ZIP** keyed to a frozen snapshot: `manifest.json` (each artifact SHA-256-hashed, tamper-evident), `methodology.md` (how figures are produced + the r²≥0.40 honesty gate + the controls), the frozen `report.json`, the `validation_record.json` (backtests incl. the retired price claim), `audit_trail.json`, `approvals_4eyes.json`, and `provenance.json`. Download button on each frozen version in the ESRS **Filed versions** panel; the export is itself audited. |
| **Remaining** | Optional polish only: a data-lineage graph and a rendered PDF cover. The evidence itself is complete. |

## 5. Golden-source refresh cadence

| | |
|---|---|
| **Status** | Registry + freshness tracking + change log **READY (v1.49)**; the scheduled data pulls + cadence sign-off remain external |
| **Why** | A filing is only as current as the feeds under it. Each source refreshes on its own clock; a re-score and (if a snapshot's basis is affected) a re-freeze must follow, with a change log. |
| **Built** | `services/data/feeds.py` — a **feed registry** (Copernicus/ECMWF, NASA/USGS, Hansen GFC, GLEIF, Climate TRACE, GEM) each with a cadence and an **`invalidates_basis`** flag; `feed_freshness()` computes **fresh / due_soon / overdue / untracked** against the append-only **`feed_refresh_log`**; `record_refresh()` stamps the log (audited). `GET /v1/admin/data-feeds` + `POST /v1/admin/data-feeds/{key}/refresh`; a **Golden-source freshness** panel in the Control Center (status dots + "scores" tag on basis-invalidating feeds + Record-refresh). |
| **Gap** | The actual **data pulls stay scheduled/external** (this is the tracking + staleness signal, not the ingestion job), and the customer **signs off the cadence**. Recording a refresh logs it and can trigger a re-score; it does not itself fetch data — honest about the boundary. |
| **Standing** | The score lane invariant holds through refreshes: a live nowcast never retires a calibrated standing climatology, and `canonical_scores` stays append-only. |

---

## One-screen status

| Gap | Status | Blocking who |
|---|---|---|
| EUDR Tier-1 DDS (manual reference-number entry) | READY | — |
| EUDR Tier-2 client (prepared mode; live via config) | READY | live needs customer registration + field alignment |
| ESRS statement per undertaking (JSON export) | READY | — |
| ESRS XBRL / iXBRL (binding + export) | GAP | EFRAG's taxonomy for the ESRS as amended; then we build it |
| Geocoder cache + confidence/QA + provider seam | READY | — |
| Geocoder pointed at a paid/self-host provider (SLA) | GAP | config (API key + URL) |
| Assurance primitives (validation, audit, 4-eyes, provenance, snapshots) | READY | — |
| Assurance evidence-pack export (hashed ZIP, per snapshot) | READY | — |
| Golden-source freshness registry + tracking + change log | READY | — |
| Golden-source scheduled pulls + cadence sign-off | GAP | scheduled jobs + customer sign-off |

**Reading this to a design partner (updated through v1.49):** everything that produces a *number* is
production-grade, the **filing last-mile is built** except ESRS XBRL (the statement exports JSON until EFRAG's taxonomy is final; assurance pack,
TRACES Tier-2 client), and the **two ops disciplines are now built too** — the geocoder has a cache +
confidence QA + a provider seam, and the golden source has a freshness registry + change log. What remains
is *external / config*: the customer's EUDR operator registration, the official TRACES field confirmation, a
production geocoder key/URL, and the scheduled data pulls + cadence sign-off — plus one build that waits on an external
artifact: the ESRS XBRL binding and export, once EFRAG's taxonomy for the ESRS as amended is final (2026-09-30).
