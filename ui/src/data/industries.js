/**
 * Industry modules — one per sector we target.
 *
 * Every module is the same three moves: locate the customer's assets on the H3
 * grid, project the canonical score for each, then apply sector-specific math.
 * Only the last step differs. `status: 'built'` modules are wired to live
 * canonical_scores; 'roadmap' modules share the identical engine and are a thin
 * layer away.
 */

export const PROCESSING_CHAIN = [
  { stage: 'Ingest', detail: 'Satellite + reanalysis feeds', table: 'satellite_observations' },
  { stage: 'Feature', detail: 'Per-hazard feature stores', table: 'ml_features_*' },
  { stage: 'Score', detail: 'Ensemble model → 0–100 risk', table: 'canonical_scores' },
  { stage: 'Project', detail: 'Score onto located assets by H3', table: 'asset_risk_projection' },
  { stage: 'Output', detail: 'Sector-specific calculation', table: 'sector service' },
]

export const INDUSTRIES = [
  {
    id: 'banking',
    name: 'Banking',
    icon: 'landmark',
    status: 'built',
    liveHazard: 'flood',
    tagline: 'Physical climate risk for loan books and regulatory disclosure.',
    valueStory:
      'Banks must disclose physical climate risk (TCFD, EU Taxonomy, SEC) and hold capital against it. We turn each financed asset’s location into a defensible, audited risk score — so materiality, stranded-asset exposure and scenario NPV come from one golden source, not a spreadsheet of assumptions.',
    valuePoints: [
      'Defensible disclosure: every number traces to a model version and data vintage',
      'Stranded-asset and scenario NPV from real hazard scores, not guesses',
      'One source feeds TCFD, EU Taxonomy and SEC outputs',
    ],
    functionalities: [
      'Asset-level physical risk by H3 cell, per hazard and scenario',
      'Portfolio materiality and assets-requiring-disclosure',
      'Stranded-asset exposure under 1.5°C / 2°C / hot-house pathways',
      'TCFD disclosure pack and audit trail (regulatory_fingerprint)',
    ],
    workflow: [
      { step: 'Register loan book on the H3 grid', ref: 'bank_assets / customer_locations' },
      { step: 'Project the canonical score for each asset', ref: 'asset_risk_projection · v_bank_asset_physical_risk' },
      { step: 'Compute materiality, stranded assets, scenario NPV', ref: 'DataProcessor / TCFD generator' },
      { step: 'Emit disclosure pack with model + vintage stamped', ref: 'regulatory_packages' },
    ],
    consumes: 'flood, heat, drought, storm, wildfire',
    output: 'TCFD materiality · stranded-asset exposure · disclosure pack',
  },
  {
    id: 'insurance',
    name: 'Insurance',
    icon: 'umbrella',
    status: 'built',
    liveHazard: 'flood',
    tagline: 'Underwriting and pricing from real hazard scores.',
    valueStory:
      'Underwriters price risk they can’t see at the granularity they need. We give every insured location a calibrated hazard score, turning it into an expected annual loss and a technical premium — and the same score drives parametric triggers, so payouts settle on an objective number.',
    valuePoints: [
      'Location-level pricing instead of postcode averages',
      'Expected annual loss and technical premium from one calibrated curve',
      'Parametric triggers fire on the same objective score',
    ],
    functionalities: [
      'Annual loss probability, expected annual loss, technical premium per location',
      'Portfolio roll-up: total sum at risk, EAL, premium, coverage gaps',
      'Parametric contract triggers on score thresholds',
      'Loss curve calibratable from realized outcomes (OutcomeFeedback)',
    ],
    workflow: [
      { step: 'Place insured locations on the H3 grid', ref: 'customer_locations' },
      { step: 'Project the canonical score for each', ref: 'asset_risk_projection.project()' },
      { step: 'Apply the loss curve → EAL → technical premium', ref: 'insurance_pricing' },
      { step: 'Arm parametric triggers on score thresholds', ref: 'parametric_contracts · trigger_events' },
    ],
    consumes: 'flood, wildfire, storm, heat',
    output: 'expected annual loss · technical premium · parametric trigger',
  },
  {
    id: 'agriculture',
    name: 'Agriculture',
    icon: 'sprout',
    status: 'built',
    liveHazard: 'drought',
    tagline: 'Crop yield-at-risk from drought and heat stress.',
    valueStory:
      'Yield loss is multi-hazard and crop-specific. We combine drought and heat scores per parcel with a crop-sensitivity model to produce tonnes and revenue at risk — for lenders, insurers, traders and co-ops exposed to the harvest.',
    valuePoints: [
      'Multi-hazard: drought and heat combined per parcel',
      'Crop-specific sensitivity (maize, wheat, soy, rice…)',
      'Tonnes and revenue at risk, ready for finance and trading',
    ],
    functionalities: [
      'Parcel-level yield-loss fraction from combined drought + heat',
      'Expected yield loss (t) and revenue at risk per parcel',
      'Portfolio roll-up across a book of parcels',
      'Crop sensitivities calibratable from realized yield outcomes',
    ],
    workflow: [
      { step: 'Place farm parcels on the H3 grid', ref: 'customer_locations (crop, hectares)' },
      { step: 'Project drought + heat canonical scores', ref: 'asset_risk_projection.project()' },
      { step: 'Combine by crop sensitivity → yield-loss fraction', ref: 'agriculture_yield_risk' },
      { step: 'Translate to tonnes + revenue at risk', ref: 'portfolio_summary' },
    ],
    consumes: 'drought, heat',
    output: 'yield-loss fraction · tonnes at risk · revenue at risk',
    note: 'Engine is live; awaiting drought scores (drought model + ETL) to light up real numbers.',
  },
  {
    id: 'reinsurance',
    name: 'Reinsurance',
    icon: 'layers',
    status: 'roadmap',
    tagline: 'Portfolio tail aggregation and parametric structuring.',
    valueStory:
      'Reinsurers price the tail of someone else’s book. The platform already has the parametric primitives; reinsurance aggregates cedent exposures across H3 cells into portfolio tail risk and structures cat bonds on the same objective scores.',
    valuePoints: [
      'Aggregate many cedent books into one tail view',
      'Cat-bond structuring on objective, auditable triggers',
      'Same golden source the cedents price on',
    ],
    functionalities: [
      'Portfolio tail (PML / occurrence) aggregation across cells',
      'Correlation across hazards and geographies',
      'Parametric cat-bond trigger design',
    ],
    workflow: [
      { step: 'Aggregate cedent exposures by H3 cell', ref: 'customer_locations · parametric_contracts' },
      { step: 'Project canonical scores across the book', ref: 'asset_risk_projection' },
      { step: 'Roll up to portfolio tail + structure triggers', ref: 'reinsurance layer (next)' },
    ],
    consumes: 'all hazards',
    output: 'portfolio tail · cat-bond triggers',
  },
  {
    id: 'asset-management',
    name: 'Asset Management',
    icon: 'trending-up',
    status: 'built',
    liveHazard: 'flood',
    tagline: 'Portfolio climate VaR and screening — zero new scoring code.',
    valueStory:
      'Investors need climate risk at portfolio level. We locate each holding at a representative site, project the canonical score, and reuse banking’s existing risk-bucket discount schedule as a value-weighted portfolio climate exposure — the sharpest proof yet that this is one engine, not five products.',
    valuePoints: [
      'Climate VaR% reuses the exact same discount schedule as banking and real estate',
      'Screening flags holdings at High/Very High risk — a simple, defensible rule',
      'EU Taxonomy eligibility per holding when a NACE code is supplied',
    ],
    functionalities: [
      'Portfolio-level climate VaR (€ and % of AUM), value-weighted across holdings',
      'Holding-level screening flags at High/Very High risk',
      'Portfolio rollup by hazard and geography; EU Taxonomy eligibility per holding',
    ],
    workflow: [
      { step: 'Upload a holdings book (name, position value, location)', ref: 'assetmgmt_holdings' },
      { step: 'Project the canonical score for each holding', ref: 'v_assetmgmt_holding_physical_risk' },
      { step: 'Apply the discount schedule as portfolio climate VaR', ref: 'valuation_discount.py (reused)' },
      { step: 'Screen High/Very High holdings, classify Taxonomy status', ref: 'eu_taxonomy_classifier.py (reused)' },
    ],
    consumes: 'flood, heat, storm, wildfire, drought',
    output: 'portfolio climate VaR · screening flags · taxonomy status',
  },
  {
    id: 'real-estate',
    name: 'Real Estate',
    icon: 'building',
    status: 'built',
    liveHazard: 'flood',
    tagline: 'Climate-adjusted valuation and NOI impact for owned property.',
    valueStory:
      'An owned property is a loan-book asset with no loan attached. We reuse banking’s haircut engine directly for the climate-adjusted value, and insurance’s pricing chain to estimate what the property would cost to insure at its hazard exposure — expressed as a share of net operating income, the number acquisitions and asset-management teams actually price against.',
    valuePoints: [
      'Climate-adjusted valuation reuses the same haircut engine as banking',
      'NOI-impact % reuses insurance’s real pricing chain, not a new model',
      'EU Taxonomy status (Annex I §7.7) and CSRD/GRESB-relevant exposure data, honestly scoped',
    ],
    functionalities: [
      'Property-level score per hazard and scenario',
      'Climate-adjusted valuation (recommended discount by risk bucket)',
      'NOI-impact %: expected insurance cost as a share of net operating income',
      'Portfolio rollup by hazard and geography; EU Taxonomy eligibility per property',
    ],
    workflow: [
      { step: 'Upload a property schedule (address, value, annual NOI)', ref: 'realestate_properties' },
      { step: 'Project the canonical score for each property', ref: 'v_realestate_property_physical_risk' },
      { step: 'Climate-adjust the value + estimate NOI impact', ref: 'valuation_discount.py · realestate_impact.py' },
      { step: 'Classify EU Taxonomy eligibility, roll up by hazard', ref: 'eu_taxonomy_classifier.py' },
    ],
    consumes: 'flood, heat, storm, wildfire, drought',
    output: 'climate-adjusted value · NOI-impact % · taxonomy status',
  },
  {
    id: 'supply-chain',
    name: 'Supply Chain',
    icon: 'truck',
    status: 'roadmap',
    tagline: 'Facility and supplier business-interruption exposure.',
    valueStory:
      'A facility or supplier is a located asset. The projection surfaces which nodes sit in elevated hazard cells, translating to business-interruption exposure and continuity planning.',
    valuePoints: [
      'Map every facility / supplier to its hazard score',
      'Business-interruption exposure by node',
      'Continuity prioritization',
    ],
    functionalities: [
      'Node-level hazard exposure',
      'Business-interruption estimate',
      'Single-point-of-failure flags',
    ],
    workflow: [
      { step: 'Map facilities / suppliers to H3', ref: 'customer_locations' },
      { step: 'Project canonical scores', ref: 'asset_risk_projection' },
      { step: 'Estimate BI exposure + flag SPOFs', ref: 'supply-chain layer (next)' },
    ],
    consumes: 'flood, storm, heat, wildfire',
    output: 'business-interruption exposure',
  },
  {
    id: 'public-sector',
    name: 'Public Sector',
    icon: 'building-community',
    status: 'roadmap',
    tagline: 'Vulnerability mapping and adaptation budgeting.',
    valueStory:
      'Governments allocate scarce adaptation budgets. Population and infrastructure are located assets; the projection produces a vulnerability map that ranks where every euro of resilience spend goes furthest.',
    valuePoints: [
      'Vulnerability map by area and hazard',
      'Adaptation budget prioritization',
      'Same auditable scores used by regulated finance',
    ],
    functionalities: [
      'Area-level vulnerability index',
      'Population / infrastructure exposure',
      'Adaptation spend ranking',
    ],
    workflow: [
      { step: 'Aggregate population / infrastructure by H3', ref: 'customer_locations' },
      { step: 'Project canonical scores', ref: 'asset_risk_projection' },
      { step: 'Rank adaptation spend by risk reduction', ref: 'public-sector layer (next)' },
    ],
    consumes: 'all hazards',
    output: 'vulnerability map · adaptation budget ranking',
  },
]

export const INDUSTRY_BY_ID = Object.fromEntries(INDUSTRIES.map(i => [i.id, i]))
