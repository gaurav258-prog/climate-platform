# Multi-Sector by Design

The platform produces one sector-agnostic golden source — `canonical_scores`
(a 0–100 risk score per H3 cell × hazard × scenario × horizon). Every sector is
a **pure layer on top of it**: it reads canonical scores by H3 cell, applies its
own domain math, and changes nothing shared.

```
                         canonical_scores  (golden source, H3-keyed)
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                          ▼
   BANKING                   INSURANCE                  (next sector)
   TCFD materiality,         expected annual loss,      its own math
   stranded assets           technical premium
        │                         │
   asset_risk_projection.project()  ← SHARED substrate (one projection)
```

## The contract for a new sector

1. **Locate assets on H3.** A bank asset, an insured location, a farm plot —
   all reduce to "a located thing with an `h3_cell`."
2. **Project, don't store.** Use `asset_risk_projection.project()` (or the
   `/v1/scores/cell/{h3}` endpoint) to read the canonical score. Never keep a
   private copy of the risk number.
3. **Speak the canonical vocabulary** (`core/types.py`) — hazards, scenarios,
   buckets. Normalize any sector dialect on the way in.
4. **Honesty rule.** A location with no canonical score gets no fabricated
   output — propagate `no_canonical_score`, never a default value.
5. **Add only your math.** Sector logic is a pure function over the projected
   score (materiality %, premium, yield-at-risk…).

If a new sector forces a change to `canonical_scores`, the vocabulary, or the
projection, the design has been violated — that change belongs in the platform,
not the sector.

## Proof

Every sector — banking, real estate, asset management, insurance — reads the
golden source through one engine, `services/portfolio_engine.py`
(`fetch_entities_with_risk`), and none writes to `canonical_scores`. A sector adds
its own book and its own money figures (`ml/scoring/insurance_pricing.py` for the
insurer, `ml/scoring/realestate_impact.py` for real estate, …) on the institution's
stated method (`services/money/params.py`, E69); adding a sector is additive. (The
earlier proof test ran against `services/intelligence/insurance_pricing.py`, a
placeholder loss curve removed on 2026-09-30.)
