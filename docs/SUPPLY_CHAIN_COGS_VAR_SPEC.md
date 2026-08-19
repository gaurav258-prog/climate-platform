# Supply-Chain Climate VaR — "COGS-at-Risk" · Product Spec v0

## 1. Thesis (one paragraph)
Every climate-risk incumbent dollarises **damage to the assets a company owns** (S&P Climanomics
AAL, MSCI/Jupiter/XDI). We dollarise **climate-driven inflation and disruption in the goods a
company buys** — rolled up its bill of materials, off the same auditable per-location score that
already powers our banking loan-book VaR. Verdict from the competitive scan: the product is
**unbundled, not absent**. The four ingredients (per-location score · cost/stockout impact ·
procurement-graph roll-up · auditability) each exist in separate camps; nobody bundles them. The
moat is the **connective tissue**, which is three genuinely hard problems (§6). EUDR is a tailwind:
it forces every buyer of cocoa/coffee/soy/palm/cattle/rubber/wood to assemble plot-level supplier
geolocation by law (large operators 30 Dec 2025) — the exact data our model needs, built for us,
for free.

## 2. Buyer & wedge
- **Primary buyer:** procurement & risk leaders (CPO / Chief Procurement, Head of Sustainability,
  CFO) at **food & beverage manufacturers and CPGs** (chocolate, coffee, packaged foods) and
  **commodity traders/merchants**. They feel COGS shocks directly and must file CSRD + EUDR.
- **Beachhead commodity:** **cocoa** (and coffee as second). Concrete, vivid, EUDR-covered, and
  recently tripled in price (2023–24) on West-African weather + disease — a live, painful,
  climate-driven COGS event. Geographically concentrated (Ghana + Côte d'Ivoire ≈ 60% of supply),
  so a small demo graph tells a true story.
- **Land-and-expand:** enter on the EUDR data the customer already holds → add forward
  climate-viability → expand to full COGS-at-risk across the ingredient book → CSRD disclosure.

## 3. The data model — the procurement graph
Mirrors the banking model exactly (an org's exposure sits in H3 cells that carry canonical
scores); the "portfolio" is a **procurement book** instead of a loan book.

```
organizations (existing)
  └─ products / SKUs            (org's finished goods; annual volume, revenue)
       └─ bom_lines             (SKU → ingredient, quantity, COST SHARE %)   ← the roll-up weights
            └─ commodities      (cocoa, coffee, wheat, palm… + price elasticity params)
                 └─ suppliers   (org's supplier for that commodity; tier)
                      └─ sourcing_plots   (supplier × commodity → H3 cell / GeoJSON,
                                            annual_spend_eur, volume_share, EUDR status)
                                 └─ canonical_scores  (EXISTING golden source:
                                                       per-hazard score × scenario × horizon, by H3)
```

**New tables** (mirror `bank_assets` / seeded like `seed_demo_loanbook.py`):
- `sc_products(product_id, org_id, name, category, annual_units, annual_revenue_eur)`
- `sc_commodities(commodity_id, name, hs_code, eudr_covered bool, price_elasticity, …)`
- `sc_bom_lines(product_id, commodity_id, qty_per_unit, cost_share_pct)` — Σ cost_share per product ≤ 1
- `sc_suppliers(supplier_id, org_id, name, commodity_id, tier, country)`
- `sc_sourcing_plots(plot_id, org_id, supplier_id, commodity_id, h3_cell, geojson,
   annual_spend_eur, volume_share, eudr_status, eudr_geolocated_at)`
- View `v_sc_plot_physical_risk` — the supply analogue of `v_bank_asset_physical_risk`:
  `sc_sourcing_plots ⋈ canonical_scores ON h3_cell` → per-plot hazard score × scenario × horizon
  + model_version + scored_at (provenance).

The plot geometry is **exactly the GeoJSON EUDR forces companies to file into EU TRACES** — we
ingest it rather than collect it.

## 4. The impact functions — hazard → COGS  (the novel core)
This is what nobody has productized. Two distinct outputs per plot, per scenario×horizon:

**(A) Cost-at-risk** — climate → input-cost inflation:
```
hazard_score(plot, hazard, scenario, horizon)          # 0–100, from canonical_scores
   → yield_shock(commodity, hazard)                     # crop damage function: score → % production loss
   → price_response = yield_shock × price_elasticity    # commodity supply→price elasticity (inelastic = big)
   → ingredient_cost_inflation_€ = price_response × annual_spend_on_that_ingredient
```
Roll UP the graph: sum ingredient inflation × `cost_share` to the SKU, then across SKUs to a
**portfolio COGS-at-risk (€ and % of COGS)**.

**(B) Continuity-at-risk** — climate → supply disruption:
```
stockout_probability(plot) = f(hazard_score, single-source concentration, lead time)
volume_at_risk = Σ volume_share of plots above a disruption threshold
```

**Honesty (this is the credibility bar vs S&P's 250+ published functions):**
- v0 functions come from **published crop damage curves + commodity price elasticities** (FAO,
  USDA, peer-reviewed), **versioned and auditable** — every COGS-at-risk figure carries the impact
  function id + data vintage, exactly like our model provenance today.
- **Validation = backtest against known climate-driven price shocks**: cocoa 2023–24 (West-Africa
  heat/rain), coffee 2021 (Brazil frost/drought), wheat 2022. If our function, fed the hazard
  scores for those regions/years, reproduces the direction and rough magnitude of the realised
  price move, we publish that skill (and where it misses). Same LOEO/forecast-vs-reality ethos as
  the flood/seismic work. We do **not** ship a dollar figure we can't backtest.

## 5. Output — "COGS-at-Risk"
- **Portfolio view:** total procurement spend; **COGS-at-risk € and %** under the selected
  scenario × horizon; top exposed ingredients / suppliers / sourcing regions; single-point-of-
  failure concentration; **EUDR-compliance overlay** (deforestation-free ✓ **and** climate-viable?).
- **Drill-through** (reuse the AssetDrawer pattern): SKU → ingredient → supplier → plot → the exact
  per-hazard climate score + model_version + data vintage + the impact-function version that turned
  it into euros. Fully traceable — the thing a CFO signs under CSRD.
- **Scenario × horizon selector:** reuse the existing ContextBar (baseline / 1.5° / 2° / hot-house
  × current / 2030 / 2050 / 2100).

## 6. The moat (three hard, ownable problems — not the slogan)
1. **Hazard → price/availability impact functions** (not hazard → asset damage). Everyone owns the
   latter; almost nobody productizes the former.
2. **BOM → supplier-plot plumbing** — mapping a buyer's bill of materials to upstream third-party
   plots. SCAIR proves it's buildable (business-interruption VaR up a BOM); **EUDR now generates
   the plot geolocation industry-wide**, removing the historic blocker.
3. **Auditability** — one score defensible under CSRD, with published methodology. S&P's
   credibility here is the bar to clear; our append-only golden source + provenance chain is the
   answer.

## 7. Reuse of the banking VaR engine (do NOT rebuild)
| Banking (built) | Supply-chain (new) |
|---|---|
| `bank_assets` (assets in H3 cells) | `sc_sourcing_plots` (supply in H3 cells) |
| `asset_value_eur` | `annual_spend_eur` (per ingredient/plot) |
| `v_bank_asset_physical_risk` | `v_sc_plot_physical_risk` |
| `services/intelligence/asset_risk_projection.py::project_org_assets` | `project_org_supply` (same shape) |
| Portfolio value-at-risk (value in H+VH) | **COGS-at-risk** (spend × cost-inflation function) |
| `AssetDrawer` (asset → hazard → provenance) | `PlotDrawer` (plot → hazard → impact fn → provenance) |
| `Reports.jsx` TCFD/EU-Tax pack | CSRD + EUDR disclosure pack |
| `project_scenarios.py` scenario×horizon | reused **unchanged** |
| ContextBar / RiskAtom coherence spine | reused **unchanged** |
The scenario×horizon projection, the golden source, the H3 join, and the whole coherence spine are
reused as-is. The genuinely new code is: the procurement-graph tables + the **impact-function
layer** (§4) + a Supply-chain workspace in the catalog (it's a new Industry/Offering, entitlement-
gated like Banking/Insurance).

## 8. Honest foundation dependency
Agriculture's dominant hazards are **drought, heat, excess rain/frost** — flood/wildfire/seismic
are live but `drought`/`heat_acute` are registry-only, not yet LOEO-validated. **Maturing drought +
heat scoring for the beachhead sourcing geographies (West Africa cocoa, Brazil/Vietnam coffee) is
the real Phase 0** — no COGS-at-risk number is credible without it. This is foundation, not a skip.

## 9. Phased build
- **Phase 0 — Foundation:** mature drought + heat scoring for the cocoa/coffee sourcing regions;
  pick 1–2 commodities. (Prereq; gated by data + validation.)
- **Phase 1 — Procurement graph + demo:** the `sc_*` tables + view + a `seed_demo_supply.py`
  (a demo CPG: a handful of SKUs, a BOM, suppliers, cocoa/coffee plots placed in scored H3 cells,
  some EUDR-compliant) — mirrors `seed_demo_loanbook.py`. Proves the join and roll-up.
- **Phase 2 — Impact functions v0 + COGS-at-risk:** the hazard→yield→price→cost functions
  (versioned), `project_org_supply`, `/v1/supply/portfolio|summary|plot` API, and the Supply-chain
  workspace UI (portfolio COGS-at-risk + drill-through), scenario×horizon reused. **Backtest cocoa
  2023–24 / coffee 2021** and publish the skill.
- **Phase 3 — EUDR + CSRD pack:** ingest EUDR GeoJSON as plot geometry; the compliance overlay
  ("deforestation-free ✓ and climate-viable?"); CSRD/EUDR disclosure export.

## 10. Risks & open questions
- **Impact-function science is the hardest part** and the moat — must be backtested, not asserted.
- **Buyer supplies the BOM/supplier data** (proprietary) — but EUDR now forces them to hold the
  plot geolocation, which is the painful 80%.
- **Access to the CPO/CFO buyer** is a go-to-market risk independent of the tech.
- **Nearest watchers:** ClimateAi (owns the CPG wedge + intent, ships forecasts not COGS VaR),
  SCAIR (owns BOM VaR structure, business-interruption not cost, not climate-native), IBM EIS
  (owns all ingredients across siloed modules). Move faster than IBM bridging its modules.
```
```
