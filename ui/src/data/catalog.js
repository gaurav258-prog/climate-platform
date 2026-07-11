// The product taxonomy: Industry → Offering → Service → Process → Workflow.
// `workflow` names a built page component (see the registry in App.jsx). Personas
// carry entitlements — the catalog is filtered so a customer sees only what they
// license. Swap PERSONAS for real DB entitlements later without touching the UI.

export const CATALOG = {
  banking: {
    id: 'banking', label: 'Banking', icon: 'building-bank',
    blurb: 'Physical-climate risk for loan books and regulatory disclosure.',
    offerings: [
      {
        id: 'physical-risk', label: 'Physical risk', icon: 'shield-half',
        blurb: 'Where climate hazards hit the book — live, per asset.',
        services: [
          { id: 'command', label: 'Command center', icon: 'layout-dashboard', workflow: 'CommandCenter',
            blurb: 'Your loan book, right now.', processes: ['Sense', 'Score', 'Project', 'Act'] },
          { id: 'portfolio', label: 'Portfolio screening', icon: 'briefcase', workflow: 'Portfolio',
            blurb: 'Every asset ranked by projected risk.', processes: ['Ingest', 'Project', 'Rank', 'Review'] },
          { id: 'map', label: 'Risk map', icon: 'map-2', workflow: 'RiskMapBank',
            blurb: 'The book on the golden source.', processes: ['Locate', 'Project', 'Inspect'] },
          { id: 'signals', label: 'Early warning', icon: 'radio', workflow: 'Signals',
            blurb: 'Live events screened against the book.', processes: ['Monitor', 'Screen', 'Alert'] },
        ],
      },
      {
        id: 'reporting', label: 'Regulatory reporting', icon: 'file-report',
        blurb: 'Defensible disclosure from the projected book.',
        services: [
          { id: 'tcfd', label: 'TCFD / EU Taxonomy', icon: 'file-report', workflow: 'Reports',
            blurb: 'Physical risk, alignment, financed emissions.',
            processes: ['Scope', 'Project', 'Aggregate', 'Compile', 'Audit'] },
        ],
      },
      {
        id: 'trust', label: 'Trust & assurance', icon: 'certificate',
        blurb: 'Why every number is defensible.',
        services: [
          { id: 'models', label: 'Models & provenance', icon: 'stack-2', workflow: 'ModelsPage',
            blurb: 'Honest out-of-sample skill per hazard.', processes: ['Registry', 'Skill', 'Verify'] },
          { id: 'foundation', label: 'Data foundation', icon: 'database', workflow: 'PlatformOverviewPage',
            blurb: 'Live data → AI engine → golden source.', processes: ['Sense', 'Clean', 'Score'] },
          { id: 'methodology', label: 'Methodology', icon: 'scroll', workflow: 'MethodologyPage',
            blurb: 'How discount%, LTV and taxonomy are calculated — and their real regulatory basis.',
            processes: ['Discount', 'LTV', 'Taxonomy'] },
        ],
      },
    ],
  },

  agriculture: {
    id: 'agriculture', label: 'Agriculture & Food', icon: 'sprout',
    blurb: 'Climate risk in your supply chain — COGS-at-risk across the bill of materials.',
    offerings: [
      {
        id: 'supply-chain', label: 'Supply-chain risk', icon: 'package',
        blurb: 'Where climate hits cost-of-goods — per commodity, per sourcing plot.',
        services: [
          { id: 'cogs', label: 'COGS-at-risk', icon: 'layout-dashboard', workflow: 'CogsCommand',
            blurb: 'Your procurement book, projected.', processes: ['Sense', 'Score', 'Project', 'Act'] },
          { id: 'sourcing', label: 'Sourcing book', icon: 'file-search', workflow: 'SourcingBook',
            blurb: 'Every plot, scored per hazard.', processes: ['Map', 'Score', 'Sort'] },
          { id: 'risk-map', label: 'Risk map', icon: 'map-2', workflow: 'RiskMapSupply',
            blurb: 'Your sourcing plots on the hazard map.', processes: ['Locate', 'Project', 'Drill'] },
          { id: 'signals', label: 'Early warning', icon: 'radio', workflow: 'SupplySignals',
            blurb: 'Commodities heating up this season.', processes: ['Sense', 'Screen', 'Alert'] },
          { id: 'disclosure', label: 'Disclosure', icon: 'file-report', workflow: 'SupplyDisclosure',
            blurb: 'EUDR overlay + CSRD physical-risk pack.', processes: ['EUDR', 'CSRD', 'Export'] },
        ],
      },
      {
        id: 'trust', label: 'Trust & assurance', icon: 'certificate',
        blurb: 'Why every number is defensible.',
        services: [
          { id: 'models', label: 'Models & validation', icon: 'stack-2', workflow: 'SupplyModels',
            blurb: 'Event backtests + per-commodity calibration status.', processes: ['Backtest', 'Calibrate', 'Verify'] },
          { id: 'foundation', label: 'Data foundation', icon: 'database', workflow: 'PlatformOverviewPage',
            blurb: 'Live data → AI engine → golden source.', processes: ['Sense', 'Clean', 'Score'] },
        ],
      },
    ],
  },

  insurance: {
    id: 'insurance', label: 'Insurance', icon: 'umbrella',
    blurb: 'Underwriting and parametric triggers on the same golden source.',
    offerings: [
      {
        id: 'underwriting', label: 'Underwriting', icon: 'file-search',
        blurb: 'Price physical risk into the book.',
        services: [
          { id: 'pricing', label: 'Loss-curve pricing', icon: 'chart-line', workflow: 'LossCurvePricing',
            blurb: 'Expected loss and premium from the score.', processes: ['Project', 'Loss curve', 'Price'] },
        ],
      },
      {
        id: 'parametric', label: 'Parametric', icon: 'bolt',
        blurb: 'Event-triggered payouts.',
        services: [
          { id: 'triggers', label: 'Trigger monitoring', icon: 'radio', workflow: 'ParametricTriggers',
            blurb: 'Live events vs policy thresholds.', processes: ['Monitor', 'Match', 'Trigger'] },
        ],
      },
      {
        id: 'trust', label: 'Trust & assurance', icon: 'certificate',
        blurb: 'Why every number is defensible.',
        services: [
          { id: 'foundation', label: 'Data foundation', icon: 'database', workflow: 'PlatformOverviewPage',
            blurb: 'Live data → AI engine → golden source.', processes: ['Sense', 'Clean', 'Score'] },
        ],
      },
    ],
  },

  realestate: {
    id: 'realestate', label: 'Real Estate', icon: 'building',
    blurb: 'Climate risk in owned properties — NOI impact across the portfolio.',
    offerings: [
      {
        id: 'portfolio-risk', label: 'Portfolio risk', icon: 'shield-half',
        blurb: 'Where climate hits NOI — per property, per hazard.',
        services: [
          { id: 'impact', label: 'Portfolio & NOI impact', icon: 'layout-dashboard', workflow: 'RealEstatePortfolioImpact',
            blurb: 'Climate-adjusted value + NOI impact, per property.', processes: ['Ingest', 'Project', 'Impact', 'Disclose'] },
        ],
      },
      {
        id: 'trust', label: 'Trust & assurance', icon: 'certificate',
        blurb: 'Why every number is defensible.',
        services: [
          { id: 'foundation', label: 'Data foundation', icon: 'database', workflow: 'PlatformOverviewPage',
            blurb: 'Live data → AI engine → golden source.', processes: ['Sense', 'Clean', 'Score'] },
        ],
      },
    ],
  },

  assetmgmt: {
    id: 'assetmgmt', label: 'Asset Management', icon: 'trending-up',
    blurb: 'Portfolio climate VaR and screening on the same golden source.',
    offerings: [
      {
        id: 'portfolio-var', label: 'Portfolio VaR', icon: 'shield-half',
        blurb: 'Climate value-at-risk and screening, per holding.',
        services: [
          { id: 'var', label: 'Portfolio climate VaR', icon: 'layout-dashboard', workflow: 'AssetMgmtPortfolioVaR',
            blurb: 'Value-weighted climate risk across the holdings book.', processes: ['Ingest', 'Project', 'VaR', 'Screen'] },
        ],
      },
      {
        id: 'trust', label: 'Trust & assurance', icon: 'certificate',
        blurb: 'Why every number is defensible.',
        services: [
          { id: 'foundation', label: 'Data foundation', icon: 'database', workflow: 'PlatformOverviewPage',
            blurb: 'Live data → AI engine → golden source.', processes: ['Sense', 'Clean', 'Score'] },
        ],
      },
    ],
  },
}

export const PERSONAS = [
  { id: 'meridian', name: 'Meridian Bank', icon: 'building-bank', industry: 'banking',
    entitlements: { offerings: ['physical-risk', 'reporting', 'trust'] } },
  { id: 'iberia', name: 'Iberia Mutual', icon: 'umbrella', industry: 'insurance',
    entitlements: { offerings: ['underwriting', 'parametric', 'trust'] } },
  { id: 'stellar', name: 'Stellar Logistics REIT', icon: 'building', industry: 'realestate',
    entitlements: { offerings: ['portfolio-risk', 'trust'] } },
  { id: 'nordkap', name: 'Nordkap Asset Management', icon: 'trending-up', industry: 'assetmgmt',
    entitlements: { offerings: ['portfolio-var', 'trust'] } },
]

// Entitlement-filtered view of a persona's industry (demo/marketing paths).
export function catalogFor(persona) {
  const ind = CATALOG[persona.industry]
  if (!ind) return null
  const allowed = new Set(persona.entitlements.offerings)
  return { ...ind, offerings: ind.offerings.filter(o => allowed.has(o.id)) }
}

// Map an organization type (from the backend) to a catalog industry.
const ORG_TYPE_TO_INDUSTRY = {
  bank: 'banking', insurer: 'insurance', insurance: 'insurance',
  manufacturer: 'agriculture', cpg: 'agriculture', food: 'agriculture',
  reit: 'realestate', real_estate: 'realestate', property_manager: 'realestate',
  asset_manager: 'assetmgmt', 'asset-manager': 'assetmgmt',
}

export function industryForOrg(org) {
  if (!org) return null
  return ORG_TYPE_TO_INDUSTRY[org.type] || org.type || null
}

// Entitlement-filtered catalog for a logged-in user. `auth` is the /me payload:
// { org:{type,...}, entitlements:[offering_id,...] }. This is the real path —
// industry comes from the org, offerings from DB entitlements.
export function catalogForAuth(auth) {
  if (!auth) return null
  const ind = CATALOG[industryForOrg(auth.org)]
  if (!ind) return null
  const allowed = new Set(auth.entitlements || [])
  return { ...ind, offerings: ind.offerings.filter(o => allowed.has(o.id)) }
}
