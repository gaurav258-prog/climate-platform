# Functional architecture — investor diagram

Single-slide functional picture of Tellumen: **one golden-source truth of the Earth**, run through the
operational loop (**Sense → Score → Project → Act**), gated by our honesty standard (**r² ≥ 0.40**), feeding
**two sides of one value chain** — *Operate* (run the business) and *Comply* (satisfy the law → the regulator).

Two colourways:
- `Tellumen-Functional-Architecture.pptx` — green/gold (climate-native, default).
- `Tellumen-Functional-Architecture-Blue.pptx` — two-shade blue (finance-audience alternate).

## Regenerate

`pptxgenjs` is used to build the deck. From this folder:

```bash
NODE_PATH="$(npm root -g)" node functional_architecture.js       # green → ../../Downloads or edit the output path in-file
NODE_PATH="$(npm root -g)" node functional_architecture_blue.js  # blue
```

The blue generator is the green one with a swapped palette (deep navy + steel-blue + cyan) and the
warm-hardcode residuals re-pointed to blue; keep the two in sync when editing layout.

## Grounding (every element is real)

- **Data-in (8 domains):** each is backed by a real ingestion adapter / scoring module in the codebase —
  `adapters/glofas.py` (flood), `adapters/sentinel1_sar.py` + `sentinel3_slstr.py` (radar/optical/thermal),
  `pollution_cams.py` (atmosphere), IBTrACS + `storm_physics.py` (storms), `seismic_physics.py` +
  `volcanic_physics.py` (geophysical), Hansen (deforestation), GLEIF/GEM/Climate TRACE (reference), plus ERA5.
  Mirrors the live golden-source registry in `services/data/feeds.py`.
- **"Near-real-time"** rests on the genuinely-NRT feeds (FIRMS ~3 h, GloFAS daily, Sentinel revisits,
  cyclone tracks per-event). ERA5 reanalysis lags ~5 days — it is the *standing climatology*, not real-time.
- **Honesty gate** is labelled **"our publish standard"** — *r²* is the universal statistic; the **≥ 0.40
  publish threshold is Tellumen's own governance constant**, not an industry benchmark.
- **Seismic & volcanic** are shown as production but labelled **geophysical** — the one hazard family NOT
  r²-calibrated (not climate-attributable). Including them positions Tellumen as physical / natural-catastrophe
  risk, a superset of climate risk.
