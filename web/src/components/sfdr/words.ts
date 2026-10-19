// The fund and SFDR screens' words for their own codes (UI standard, 2026-10-16): a code never reaches a screen as-is.
// Server explanations come as catalogue messages (services/fund_messages.py); these are the names of fixed choices.
import { TONE } from './visuals'

// the product categories SFDR sorts funds into — names customers use (the guard's CATEGORY), not citations
export const ARTICLE: Record<string, { label: string; long: string; tone: string }> = {
  article_9: { label: 'Article 9', long: 'Article 9 — a sustainable investment objective', tone: 'var(--color-good)' },
  article_8: { label: 'Article 8', long: 'Article 8 — promotes environmental or social characteristics', tone: 'var(--color-sky)' },
  article_6: { label: 'Article 6', long: 'Article 6 — no sustainability promotion', tone: 'var(--color-slate)' },
}

export const FUND_TYPE: Record<string, string> = {
  fund: 'Fund', sub_portfolio: 'Sub-portfolio', mandate: 'Mandate', fund_of_funds: 'Fund of funds',
}

// how far an indicator is computed (ml/regulatory/sfdr_pai.py method)
export const METHOD: Record<string, { label: string; tone: string }> = {
  computed: { label: 'Computed', tone: TONE.good }, partial: { label: 'Partial', tone: TONE.warn },
  estimated: { label: 'Estimated', tone: TONE.sky }, not_available: { label: 'Not available', tone: TONE.bad },
  not_applicable: { label: 'Does not apply', tone: TONE.faint },
}

// a risk score out of 100, coloured by its band
export const scoreTone = (s?: number | null) =>
  s == null ? 'var(--color-faint)' : s < 28 ? 'var(--color-good)' : s < 50 ? '#e8b24c' : s < 75 ? '#f0a860' : 'var(--color-bad)'

// the uses an EET file serves (services/eet/fields.py USES)
export const EET_USE: { k: string; label: string }[] = [
  { k: 'entity', label: 'Adverse impacts statement' }, { k: 'periodic', label: 'Periodic document' },
  { k: 'precontractual', label: 'Pre-contractual document' }, { k: 'mifid', label: 'Investment advice' },
  { k: 'idd', label: 'Insurance distribution' },
]

// the issuer data an organisation can hold of its own (services/issuer_client_data.py STORES)
export const OWN_DATA: Record<string, string> = {
  issuer_emissions: 'emissions', issuer_esg_metrics: 'ESG figures', issuer_taxonomy_kpi: 'Taxonomy figures',
  issuer_voluntary_pai: 'additional indicator values', issuer_data_confirmations: 'confirmed figures',
}

// the SFDR product documents (services/governance/sfdr_answers.py DOCUMENTS)
export const DOCUMENT = { precontractual: 'Pre-contractual', periodic: 'Periodic' } as const

// a risk band (canonical_scores risk_bucket)
export const BAND: Record<string, string> = { VH: 'Severe', H: 'High', M: 'Elevated', L: 'Low' }

export const fmtDate = (s?: string | null) => (s ? new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }) : '—')
