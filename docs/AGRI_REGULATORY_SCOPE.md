# Agriculture — regulatory scope: what we own, integrate, and decline

**Audience:** product + investor conversations. **Question it answers:** an EU food/agri/consumer-goods
customer must file a lot of sustainability + supply-chain regulation. Which of it is *ours* to build,
which do we *plug into*, and which do we deliberately *not* build — and why.

## The dividing line: the data engine, not the regulation

CSRD/ESRS *looks* like one thing (a single sustainability statement, one XBRL taxonomy, assured as a
whole), but it is assembled from radically different data domains. Our moat is a specific one:
**satellite + hazard + per-plot geolocation + calibrated crop-yield/asset physical risk + deforestation.**

The rule we follow: **own what shares that engine; integrate or decline what does not.** Trying to *be*
the whole sustainability suite would put us head-on with 50 funded incumbents on commoditized,
lower-margin data plumbing where we have no edge. Being the best specialist for the hard physical part —
and slotting into whatever reporting suite the customer already runs — is the sharper, more defensible play.

## The map

| Regime | Frequency / format | Our stance | Why |
|---|---|---|---|
| **EUDR** (deforestation DDS → TRACES) | Per consignment; electronic DDS + plot geolocation | **OWN — built** | Needs exactly our data (satellite forest-loss, per-plot polygons). Nobody does it better from the risk side. |
| **CSRD / ESRS E1 — climate, PHYSICAL risk** (E1-9 anticipated financial effects) | Annual; XBRL-tagged; assured | **OWN — built** | Quantified €-at-risk from hazard→asset/yield. Generic CSRD tools hand-wave this; we do it properly. |
| **ESRS E3 — water** (water stress on sites/sourcing) | Annual; part of the statement | **OWN — building** | Water stress is already a hazard we score; same engine. |
| **ESRS E4 — biodiversity** (deforestation, land in/near sensitive areas) | Annual; part of the statement | **OWN — building** | EUDR determinations already give the deforestation datapoints. |
| **EU Taxonomy — climate-ADAPTATION KPIs** (Art. 8) | Annual; prescribed KPI tables, XBRL | **OWN — planned** | Adaptation eligibility/alignment is fed by our physical-risk data. |
| **CSRD / ESRS E1 — GHG accounting** (Scope 1/2/3) | Annual; part of the statement | **INTEGRATE — do NOT build** | Carbon accounting is a crowded, commoditized market (Watershed, Persefoni, Sweep, SAP…). No satellite edge, low margin. Partner / import. |
| **ESRS E2 pollution, E5 circular economy** | Annual | **INTEGRATE / DECLINE** | Not our data domain. |
| **ESRS S1–S4 social, G1 governance** | Annual | **DECLINE** | HR / policy / survey data. Different competency entirely. |
| **CSDDD** (value-chain due diligence + climate transition plan) | Ongoing; supervisory + civil liability | **PARTIAL / FUTURE** | Our adaptation + physical-risk feed the transition-plan narrative; the DD obligations themselves are not a report we generate. |
| **National laws** (German LkSG, French Devoir de Vigilance) | Annual to national bodies | **DECLINE** | Human-rights-heavy; being folded into CSDDD. |
| **SFDR / SFDR Art 8-9** | — | **N/A for agri** | Financial-sector regimes (asset managers, banks). We built these for the *finance* verticals, not for a food company. |

## The bundle that makes sense for us: "Climate & Nature"

The ESRS topics that share our engine form one coherent, ownable package:

> **E1 climate (physical) + climate adaptation + E3 water + E4 biodiversity/deforestation + EUDR +
> EU Taxonomy climate-adaptation KPIs.**

We deliver this as a **filing-grade, importable component** (structured datapoints + provenance,
machine-readable, moving toward XBRL/ESEF tagging) that plugs into the customer's overall CSRD statement —
*not* a replacement for their whole sustainability suite.

Everything outside that box (GHG accounting, pollution, circular economy, social, governance) is
**separate by design.** Saying that boundary out loud is part of the honesty pitch: *we do physical
climate + nature risk properly, and we don't pretend to do your carbon accounting or HR reporting.*

## Honesty / timing caveats (do not hardcode)

- **EU Omnibus "stop-the-clock"** is actively reshaping this: CSRD waves 2–3 pushed back ~2 years and
  scope narrowing (thresholds toward ~1,000 employees); CSDDD application delayed ~1 year; EUDR
  application delayed ~12 months with continued simplification pressure. **Treat all deadlines and
  thresholds as configurable**, never fixed constants.
- A euro is only ever published where the hazard→yield/asset chain is validated (r² ≥ 0.40); otherwise
  exposure is mapped and the € withheld. This honesty gate carries all the way into every disclosure
  datapoint we emit.

## Build status (2026-07-30)

- ✅ EUDR (determination + DDS + TRACES reference capture)
- ✅ CSRD / ESRS **E1 physical risk** (own operations + sourcing; JSON + Excel)
- 🔨 ESRS **E3 water** + **E4 biodiversity/deforestation** datapoint sections → the Climate & Nature pack
- ⏭ EU Taxonomy climate-adaptation KPIs; XBRL/ESEF tagging; configurable timing/thresholds
- ⛔ (by design) GHG accounting, pollution, circular economy, social, governance
