# Canonical Vocabulary

The single source of truth for every controlled term in the platform. Three
layers must agree:

| Layer | File | Role |
|-------|------|------|
| Python (ingestion, scoring) | `core/types.py` | **authoritative** — enums + normalizers |
| Database (Postgres) | migration `b7c1a2d3e4f5_vocabulary_constraints` | CHECK constraints generated from `core/types.py` |
| UI (JavaScript) | `ui/src/constants/vocabulary.js` | mirror of `core/types.py` |

> When you change a term in one layer, change it in all three. The Python enums
> are authoritative; the DB migration imports from them; the JS file is a hand-kept
> mirror with a parity test.

## Canonical values

| Concept | Canonical values |
|---------|------------------|
| **Hazard** | `flood`, `heat_acute`, `heat_chronic`, `wildfire`, `drought`, `storm`, `seismic` |
| **Scenario** (NGFS) | `baseline`, `orderly_1_5c`, `disorderly_2c`, `hot_house_3_5c` |
| **Time horizon** | `current`, `2030`, `2050`, `2100` |
| **Risk bucket** | `L` (0–25), `M` (25–50), `H` (50–75), `VH` (75–100) |
| **Risk nature** | `acute`, `chronic` |

## Why these choices

- **Scenarios use NGFS archetypes, not IPCC SSP labels.** NGFS is the framework
  referenced by TCFD, ECB and Basel III — the regulatory domain we serve. IPCC
  SSP labels (`1.5c`/`2c`/`4c`) and UI labels (`1.5C_Paris_Aligned`) map in as
  aliases. Note `4c → hot_house_3_5c`: these are the same "high warming, no
  transition" archetype; the exact temperature differs and is an accepted
  approximation at the vocabulary layer.
- **Time horizons are concrete years, not `short/medium/long_term`.** The bank
  SQL's vaguer labels normalize in (`short_term → 2030`, etc.).
- **Bare `heat` defaults to `heat_acute`.** Chronic heat must be stated explicitly.

## How to use

Never write a raw dialect string downstream. Normalize at the boundary:

```python
from core.types import normalize_hazard, normalize_scenario
hazard = normalize_hazard("Heat_Stress")        # HazardType.HEAT_ACUTE
scen   = normalize_scenario("1.5C_Paris_Aligned")  # RiskScenario.ORDERLY_1_5C
```

```js
import { normalizeHazard } from '@/constants/vocabulary'
const hazard = normalizeHazard('Heat_Stress')   // 'heat_acute'
```

Unknown values raise/throw — drift fails loudly instead of being written to the
golden source.

## Known follow-ups

- `heat_acute` / `heat_chronic` overlaps the `risk_nature` dimension
  (`acute`/`chronic`). A future cleanup could collapse heat to a single hazard
  distinguished by `risk_nature`. Deferred to avoid touching the heat feature
  store mid-unification.
- The bank SQL (`DATABASE_SCHEMA_REGULATORY_V2.sql`) still defines its own
  `climate_scenarios` rows. Folding that into the canonical vocabulary is part
  of reconciliation step #1 (wire bank vertical onto `canonical_scores`).
