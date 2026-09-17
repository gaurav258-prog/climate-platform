# Soil degradation — source review (Trends.Earth vs Li et al. 2025 LPD)

**Question it answers:** the v2.87 backtest of `soil_degradation` against the Li et al. 2025 30 m Land
Productivity Dynamics (LPD) dataset came back rank ρ = **-0.17** (n=4,000, p<1e-27) — a real, wrong-signed
disagreement, not noise. This doc investigates *why*, whether Li et al. is actually the better source, and
what a swap would take. **No source swap or re-scoring was performed** — this is findings + recommendation
only.

## 1. What each source actually measures

| | Trends.Earth SDG 15.3.1 (current, production) | Li et al. 2025 LPD (validation target) |
|---|---|---|
| Institution | Conservation International, per UNCCD Good Practice Guidance — the **official SDG 15.3.1 reporting methodology**, used by ~200 countries for UN reporting | Academic (Scientific Data / Nature, peer-reviewed, Landsat/MODIS group) |
| Inputs | ESA-CCI land cover (~300 m), Trends.Earth land-productivity dynamics (MODIS, ~250 m), SoilGrids SOC (~250 m); 3 sub-indicators combined "one-out-all-out" | Landsat-8 + MODIS fused, FAO-WOCAT LPD methodology, single productivity-trend indicator |
| Effective resolution | ~250-300 m (coarsest of the three sub-indicators drives it) | 30 m — ~10x finer |
| Legend | -1 degraded / 0 stable / +1 improved (headline); productivity sub-band is 1-5 (declining..increasing) | 1-5 ordinal (1=declining/worst .. 5=increasing/best), no explicit "stable" separate from the scale |
| Time coverage | **Multiple bands, different windows** — see §3 | Single window, 2013-2022 |
| Regulatory standing | The UNCCD-recognized SDG 15.3.1 methodology — real weight for ESRS E3/E4 "aligned to official indicator" positioning | Not (yet) tied to an official regulatory reporting framework |

## 2. Ruled out first: is the validator's polarity wrong?

No. Traced line by line in `services/validation/validators/soil_degradation_lpd.py`:

- Li et al.'s legend is *health*-ordinal: 1 = declining (worst), 5 = increasing (best).
- The validator flips it with `degradation_severity = 6 - lpd_status`, so 1→5 (most severe) and 5→1 (least
  severe) — i.e. **higher = worse**.
- Our channel's score (`ml/scoring/soil_degradation_point.py`) is `100 × fraction of neighbourhood pixels at
  Trends.Earth status -1 (degraded)` — also **higher = worse**.
- Both sides run the same direction before the rank test. Confirmed by direct pixel inspection against the
  authoritative Zenodo 17079487 band-coding table (fetched live, not from memory): band-1 value `-1` =
  "Degradation", `0` = "No change", `1` = "Improvement" — matches the docstring and the flip exactly.

**Polarity is correct. Not a validator bug.**

## 3. The real confound: our channel reads a stale, fixed baseline

`ml/scoring/soil_degradation_point.py` hardcodes `_STATUS_BAND = 1`. Per the Zenodo 17079487 metadata (fetched
directly, confirmed against actual pixel values — see below), that COG has **14 bands across three windows**,
not one:

| Band | Content | Window |
|---|---|---|
| 1 | SDG 15.3.1 combined status (**what we read, always**) | **2000-2015 baseline** |
| 5 | SDG 15.3.1 combined status | 2004-2019 |
| 9 | Status in 2019 vs baseline | — |
| **10** | SDG 15.3.1 combined status | **2008-2023** |
| 14 | Status in 2023 vs baseline | — |

Band 1 — the only band our scorer or validator ever reads, local or remote — is frozen to a **2000-2015
baseline**, now 11-26 years stale. Li et al.'s window is 2013-2022. Overlap with band 1 is only ~2 years
(2013-2015); overlap with band 10 (2008-2023) is ~9 of Li's 10 years.

A single sample pixel (Iberia, ~44.86°N 10.22°W) makes the mechanism concrete: band 1 (2000-2015) = `0`
(stable), but band 5 (2004-2019) = `-1` (degraded), band 10 (2008-2023) = `-1` (degraded), and the
status-vs-baseline bands (9, 14) both read `2` ("Degradation, recent"). This location was stable through 2015
and degraded afterward — exactly the kind of point where a 2013-2022 target and a 2000-2015 baseline would
disagree, with no product being "wrong."

### Diagnostic re-run (exploratory — not a change to the registered validator or production)

Same 4,000-cell sample, same neighbourhood-fraction methodology, reading a different band directly from the
local COG instead of the production (band-1) score:

| Band read as "predicted" | Window | Spearman ρ | Bands monotone? |
|---|---|---|---|
| 1 (current production/validator) | 2000-2015 | **-0.17** | No |
| 5 | 2004-2019 | -0.06 | — |
| **10** | **2008-2023** | **+0.25** | **Yes** (2.97 → 3.28 → 3.51 → 4.10) |

Reading the temporally-aligned band **flips the sign** and restores monotonicity, but the corrected ρ (0.25)
still sits below the 0.35 CALIBRATED gate. So: **most of the "wrong-signed" disagreement is a baseline-vintage
artifact, not the two products disagreeing about current land condition** — but even correcting for it, there
is not yet enough skill to call this CALIBRATED.

This diagnostic reads band 10 directly from the raster; it does **not** reflect what `canonical_scores`
currently holds (which is band-1-derived). Per the honesty rule, the registered validator was **left
unchanged** — it correctly measures what production actually serves. Promoting the band-10 number into the
official ledger would misrepresent what customers currently see.

## 4. Recommendation

**Keep Trends.Earth as the production source for now. Do not swap to Li et al.** Reasoning:

1. **Not a data-quality verdict against Li et al.** — the disagreement is substantially explained by comparing
   a stale baseline to a recent target, not by Li et al. being wrong. There is no basis here to call Li et al.
   the "more trustworthy" source; band-10 diagnostic evidence is still weak-positive at best.
2. **Regulatory alignment still favors Trends.Earth.** For ESRS E3/E4 positioning, "computed via the
   UNCCD-recognized SDG 15.3.1 methodology" carries real defensibility that a resolution advantage doesn't
   outweigh on its own — especially since the resolution advantage didn't translate into a passing backtest
   even in Li et al.'s favor.
3. **Coverage gap.** Li et al. tiles on disk only cover the Mediterranean basin; a real swap needs global
   tiles, which is its own acquisition project.
4. **Need a third, independently-dated target to break the tie.** Neither product has proven itself against a
   held-out ground truth here — we've only shown the two disagree, and partly explained why. A field-validated
   degradation product (or a second remote-sensing product with a modern, matching window) would let us judge
   both against a common referee instead of against each other.

### Separate, smaller recommendation worth tracking on its own

Independent of the Li et al. question: **production reads a fixed 2000-2015 baseline (band 1) for a "current"
risk score, which is now materially stale.** Switching the live scorer to band 10 (2008-2023, refreshed roughly
every UNCCD reporting cycle) or band 14 (2023-vs-baseline status) would make the *current* channel reflect
actual current land condition instead of a quarter-century-old baseline — independent of any Li et al. decision.
This was **not** done in this session (it changes what every existing `canonical_scores` row for
`soil_degradation` means and would need re-scoring), but it is lower-risk than a full source swap since it
stays within the same COG/product and would likely also improve, not just the Li et al. correlation, but the
substantive accuracy of what's being reported as "now."

### If a swap is later decided

- **Re-scoring scope:** every standing `soil_degradation` cell in `canonical_scores` (band-1-derived, screening
  tier — check current row count before committing to a re-score budget).
- **Global tiles:** Li et al.'s Mediterranean-only tiles would need to be extended to global coverage (or the
  swap scoped explicitly to "Mediterranean only, screening tier elsewhere" — disclosed, not silent).
- **Parallel-score option:** land the Li et al. channel as a second, explicitly `provisional` lane
  (`score_lane`) validated independently, while Trends.Earth stays the disclosed production lane — lets the two
  be compared on live traffic before any cutover, and avoids a hard, all-or-nothing swap.
- **Re-validate from scratch** — a genuine swap needs its own independent target (can't reuse Li et al. as
  both the new production source and its own validation target).

## 5. Bottom line

- Polarity: **correct, not a bug.**
- Time-window mismatch: **real and substantial** — explains the sign flip (band-10 diagnostic: -0.17 → +0.25),
  but the corrected number still misses the 0.35 gate.
- Tier: **unchanged — SCREENING, tested_negative.** No genuine bug-fix result cleared the gate, so
  `core/hazard_taxonomy.py` and `CALIBRATED_VALIDATION` were **not** touched, per the no-fabricated-pass rule.
- Source swap: **not recommended today** — need a third, time-aligned independent target to actually judge
  Trends.Earth vs Li et al. on the merits, rather than judging them against each other.
