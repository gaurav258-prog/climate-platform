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

`services/intelligence/insurance_pricing.py` is the second sector. It was added
**without touching** `canonical_scores`, `core/types.py`, or
`asset_risk_projection.project()` — it imports them. The test
`test_bank_and_insurance_share_one_golden_source` runs banking and insurance over
the *same* canonical rows for the *same* cell and asserts neither mutates the
source. Adding a sector is additive; that is the architectural claim, enforced by
a test.
