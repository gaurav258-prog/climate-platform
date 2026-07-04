# Volcanic Hazard Methodology — proximal destruction + ashfall

Companion to `SUPPLY_CHAIN_IMPACT_FUNCTION_METHODOLOGY.md` (agriculture) and the banking
physical-risk model. Volcanic risk is the platform's second POINT-SOURCE hazard, after
seismic — physics-grounded (Bakun & Wentworth-style distance decay), not an ML model, for
the same reason seismic isn't: no real damage labels exist to train against, and the physics
is well-established and defensible on its own. **Governing rule, same as agriculture: we do
not ship a figure we cannot reproduce against a real event, and we disclose where a
calibration is approximate or where the schema doesn't yet support full precision.**

## 1. Two components, one hazard_type

`hazard_type='volcanic'` blends two internally-computed components (`ml/scoring/volcanic_physics.py`):

- **Proximal destruction** — lava flow, pyroclastic density current (PDC), lahar. Genuinely
  near-binary in reality (you're in the flow's path or you're not). Modelled as a steep
  exponential decay (`proximal_score`, power `p=3.5`) — ~100 inside the hazard-zone radius,
  sharp dropoff at the boundary, ~0 well beyond it.
- **Ashfall load** — the component that fits agriculture's existing gradual/probabilistic
  damage-function shape (`SUPPLY_CHAIN_IMPACT_FUNCTION_METHODOLOGY.md` §1.1). Modelled as an
  inverse-power distance decay (`ashfall_score`, power `q=1.5`), radius scaled by VEI.

Blended via `max(proximal, ashfall)` — not split into two `hazard_type` values the way
`heat_acute`/`heat_chronic` are, because proximal and ashfall share one event, one set of
downstream consumers, and are needed simultaneously at the same H3 cell. Splitting would force
every consumer (the banking `hazards` array, agriculture's worst-hazard-wins aggregation, UI
color/icon maps) to special-case "volcanic has two flavors." The component breakdown
(`proximal_score`, `ashfall_score`, `driver_dist_km`, `radii_source`) is still fully visible in
`canonical_scores.shap_factors`, so nothing is hidden — just not split at the vocabulary level.

**Known simplification, stated up front:** both components are radially symmetric. Real
ashfall is wind-direction-modulated; real PDC/lahar paths follow topography (valleys), not a
circle. This is a v0 approximation, the same caveat seismic's own IPE carries (a generic
attenuation curve, not a region-specific GMPE with site amplification).

## 2. Data sources

| Source | Role | Status |
|---|---|---|
| Smithsonian Global Volcanism Program (GVP), GeoServer WFS | Eruption/volcano catalog (VEI, dates, location) — the ground-truth catalog, analogous to EMSC/USGS for seismic | **Live, confirmed working, no auth** — `webservices.volcano.si.edu/geoserver/GVP-VOTW/wfs` (note: NOT `volcano.si.edu`, which Cloudflare-blocks; requires a browser-like User-Agent header, no API key) |
| NASA FIRMS (VIIRS), re-pointed at a volcano region | Supplementary thermal-unrest monitoring signal — **not an input to the volcanic score** | **Reused, not new** — `hazard_type` is now a constructor param on `NASAFIRMSAdapter` (default `WILDFIRE`); pointing it at `guatemala_volcanic` with `hazard_type=VOLCANIC` gives volcanic thermal detection at zero new integration cost |
| MIROVA (satellite radiative power, volcano-specific) | Considered as an alternative thermal source | **Blocked — no public API** (probed: 403, no documented REST endpoint). Not pursued; FIRMS substitutes. |
| USGS/PHIVOLCS/INSIVUMEH hazard-zone maps | Real proximal/ashfall radii per volcano | **No unified API** — published per-volcano as GIS/PDF products. Handled via the curated `volcanic_hazard_zones` table (below), same shape of limitation the seismic ESHM20 fallback already has. |

**Scope caveat on FIRMS:** `score_volcanic_event.py` and `volcanic_physics.py` never query
`satellite_observations` — the volcanic score is computed entirely from the GVP eruption catalog
and the curated `volcanic_hazard_zones` radii (proximal distance-decay + ashfall, §1/§3). FIRMS
thermal detections are ingested for operational monitoring dashboards only and do not feed the
score or the Fuego/Taal backtests. (Also fixed 2026-07-04: `Region.firms` was emitting the bbox
in a `W=...,S=...,E=...,N=...` format the FIRMS API rejected with HTTP 400 on every call —
corrected to plain `west,south,east,north`. Since FIRMS was never wired into scoring, this defect
had zero effect on any published volcanic score or backtest number; it only blocked the
monitoring feed and wildfire ingestion, which fail loudly via `sys.exit(1)`, not silently.)

### A genuine GVP data-granularity finding

GVP's `Holocene_Eruptions` layer logs eruptive **episodes**, not daily-dated sub-events.
Fuego's entire 2002-present activity is ONE row (`Eruption_Number=10733`, VEI 3 max,
`StartDateYear=2002`, still ongoing). The catastrophic June 3, 2018 paroxysm — the actual
backtest event — is a sub-episode inside this long-running eruption, not a separately dated
GVP record. `scripts/score_volcanic_event.py` therefore carries the specific backtest date
(2018-06-03 for Fuego) as external, well-documented knowledge (`BACKTEST_EVENTS` dict), not
something read off the GVP catalog. Taal's January 2020 eruption, by contrast, IS a clean,
discrete GVP episode (`Eruption_Number=22344`, VEI 4, 2020-01-12 to 2020-01-22) — confirmed by
direct query, which is why it serves as the cleaner secondary backtest.

## 3. Curated hazard-zone radii

`volcanic_hazard_zones` (proximal + ashfall radius per volcano), sourced per-volcano since no
unified API exists:

| Volcano | Zone | Radius | Source |
|---|---|---|---|
| Fuego | proximal | 12.2 km | Naismith et al. 2019 JVGR + 2023 JVGR follow-up (Las Lajas channel PDC runout, peer-reviewed, deposit-mapped) |
| Fuego | ashfall | 45 km | INSIVUMEH (>40km ash advance) + GVP Bulletin (ashfall across all 22 departments, >60km at trace levels) — no isopach map exists for this event, so 45km is a mid-estimate, not a precise contour |
| Taal | proximal | 14 km | PHIVOLCS Alert Level 4 evacuation zone, Jan 12-17 2020 Eruption Update Bulletins (the actual crisis-footprint radius; the enforced post-crisis Permanent Danger Zone is a tighter 7km) |
| Taal | ashfall | 25 km | Balangue-Tarriela et al. 2022, *Bulletin of Volcanology* (peer-reviewed isopach map) — 25km approximates the 0.5cm isopach boundary (agriculturally/structurally meaningful load); trace ash (<1mm) reached Metro Manila ~60-70km, excluded as low-signal |

Volcanoes without a curated row fall back to `vei_to_zone_radii(vei)` — a rough VEI-scaled
default (order-of-magnitude, not a fitted curve), clearly flagged via `radii_source` in
`shap_factors` so it's always visible which volcanoes are on real published radii vs. an estimate.

## 4. Backtest targets

**Primary: Fuego 2018 (Guatemala).** Chosen for a dual banking+agriculture narrative:
proximal destruction (San Miguel Los Lotes) for banking, and a real coffee-growing origin
(Antigua/Alotenango, literally in Fuego's shadow — volcanic soil built this region's coffee
reputation and is also its tail risk) for agriculture.

**Secondary: Taal 2020 (Philippines).** Cleaner ashfall-only case (proximal destruction largely
confined to Taal Volcano Island) with a peer-reviewed isopach map — better for isolating the
ashfall coefficient without proximal-destruction confounding. Not wired into a demo plot
(Taal's Batangas/Cavite crop mix is vegetables/banana-dominant, coffee only 10.9% of DA's
damage figure) — kept as a documented, direction-only generalisation check.

### 4.1 Banking check — spatial discrimination (`scripts/backtest_volcanic.py`)

| Site | Distance from vent | Score | Driver | Real outcome |
|---|---|---|---|---|
| San Miguel Los Lotes | 7.2 km | 85.6 | **proximal** (85.6 vs ashfall 80.1) | Destroyed by pyroclastic density current |
| Antigua Guatemala | 18.5 km | 59.7 | ashfall (proximal only 1.4) | Received ashfall, not in the PDC's path |

**Verdict: correct.** The model attributes Los Lotes' destruction to the right mechanism
(proximal, not ashfall) and correctly scores Antigua lower and ashfall-driven — a real,
non-trivial spatial discrimination the same way seismic's IPE replaced a flat blanket score.

### 4.2 Agriculture check — Guatemala coffee vs Fuego 2018

**The honest limitation, stated plainly:** `sc_commodities.name` is UNIQUE — "Coffee" is ONE
global commodity shared across origins (Brazil, Vietnam, now Guatemala), the same way it
already spans Brazil+Vietnam. Brazil's calibration (`sensitivity=0.45`, `global_share=0.35`,
fit to the 2021 drought event) is the only calibrated coefficient the schema has for Coffee.
Adding Guatemala's volcanic-ashfall hazard under the same commodity means the **live product**
prices Guatemala's hazard using Brazil's world share (0.35) — a real, disclosed mismatch, since
Guatemala's actual world coffee share is roughly 2.3% (ICO/USDA order-of-magnitude), about 15x
smaller. There is no per-origin or per-mechanism override in the current schema.

`scripts/backtest_volcanic.py` therefore reports TWO numbers, not one:

| | global_share used | yield-shock | price-move | €COGS-at-risk (P50) |
|---|---|---|---|---|
| (a) Live model (borrows Brazil's share) | 0.35 | 36.4% | 27.2% | €1.11m |
| (b) Origin-specific (Guatemala's real share) | 0.023 | 36.4% | 1.8% | €0.22m |

**Real anchor (Anacafé):** ~0.9% of Guatemala's *national* coffee production lost — a
country-wide average diluted across origins far from Fuego (Huehuetenango, Cobán, etc.), not a
local Antigua-only figure. The fairer comparison is (b)'s local yield-shock (36.4% at the
Alotenango plot specifically, which sits ~8km from the vent) against a *local* Antigua-region
loss figure — which we do not have; Anacafé's number is national. **Real anchor (MAGA):** ~$12.3m
total agricultural loss across 13,611 ha in Sacatepéquez/Chimaltenango/Escuintla — corn,
vegetables and fruit dominant, coffee only a minor share of this total, so it's an
order-of-magnitude cross-check, not a coffee-specific figure either.

**Verdict:** directionally sound (real hazard proximity → real elevated local yield-shock), but
not independently calibrated against a matching local anchor. **Guatemala's plot is therefore
NOT added to `BACKTESTED`** — Coffee stays backtested on Brazil's validated drought calibration,
and Guatemala's contribution is disclosed as `indicative`, consistent with the platform's rule
that unvalidated € is never silently blended with validated €.

### 4.3 Taal 2020 — secondary, direction only

Philippine DA: PHP 3.06bn total agricultural damage, 15,790 ha, CALABARZON region; coffee =
10.9% of that ≈ PHP 333.5m (~US$6.5m). Not wired into a demo plot — kept as a documented
secondary target should a future session want to extend the ashfall calibration.

## 5. Known limitations (stated up front, same convention as the agriculture doc's §5)

- **Radially symmetric ashfall and proximal zones** — real ashfall is wind-direction-modulated;
  real PDC/lahar paths follow valleys. A v0 approximation, not a directional claim.
- **VEI-scaled default radii** for any volcano without a curated `volcanic_hazard_zones` row —
  an order-of-magnitude fallback, not a substitute for a published hazard map.
- **Scenario-invariant scoring** — unlike heat/drought, volcanic scores do not vary by NGFS
  warming scenario (an eruption's VEI/distance physics isn't warming-sensitive the way a
  temperature threshold is). Matches seismic's own precedent (also scenario-invariant). A demo
  plot may show "pending" under scenario/horizon combinations beyond baseline/current as a
  result — an honest reflection of the physics, not a data gap.
- **Shared-commodity sensitivity/global_share** (§4.2) — the single biggest disclosed gap.
  Resolving it properly would need a schema change (per-origin or per-mechanism calibration
  override on `sc_commodities`/`sc_sourcing_plots`), out of scope for this pass.
- **GVP eruption-episode granularity** (§2) — coarse start/end dates for long-running eruptions
  like Fuego; the specific backtest date is carried as external knowledge, not read from GVP.
- **No unified global hazard-zone API** — curated per-volcano, not live-fetched at scale. Fine
  for the two backtest volcanoes here; would become a real blocker if scope ever expanded to
  "score all ~1,500 Holocene volcanoes."

## 6. Files

- `ml/scoring/volcanic_physics.py` — the physics (proximal/ashfall/blend/VEI-scaled defaults).
- `scripts/ingest_gvp_volcanic.py` — GVP WFS → `volcanic_events`.
- `scripts/score_volcanic_event.py` — physics → `canonical_scores` (`hazard_type='volcanic'`),
  mirrors `scripts/score_seismic_event.py`.
- `scripts/wire_guatemala_volcanic_demo.py` — Guatemala coffee plot under the existing Coffee commodity.
- `scripts/backtest_volcanic.py` — the checks in §4.1/§4.2 above.
- `scripts/record_ag_validation.py` — persists the Fuego 2018 result into `sc_model_validation`
  (surfaced on the Models & validation page).
