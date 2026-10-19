// The ESRS screens' words for their own codes (UI standard, 2026-10-16): a code never reaches a screen as-is.

// the undertaking's reporting role for the year (services/governance/csrd_roles.py ROLES)
export const ROLE: Record<string, string> = {
  individual: 'Individual statement', consolidated: 'Consolidated statement of a group',
  exempt_subsidiary: 'Exempt subsidiary', voluntary: 'Voluntary statement',
}
// where a figure comes from (services/governance/esrs_binding.py lanes)
export const LANE: Record<string, string> = { computed: 'Computed', derived: 'Derived', provided: 'You state it', same_as: 'Reported elsewhere' }
export const HORIZON: Record<string, string> = { short: 'Short term', medium: 'Medium term', long: 'Long term' }
// why an item is omitted (services/governance/esrs_document.py REASONS)
export const REASON: Record<string, string> = {
  not_material: 'Not material', condition_not_applicable: 'Its condition does not apply', phase_in: 'Phase-in',
}
// an item's state in the statement
export const ITEM: Record<string, { label: string; tone: 'good' | 'warn' | 'neutral' }> = {
  filled: { label: 'Reported', tone: 'good' }, omitted: { label: 'Omitted', tone: 'neutral' }, missing: { label: 'To do', tone: 'warn' },
}
// a figure's comparative (services/governance/esrs_comparatives.py statuses)
export const CMP: Record<string, { label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = {
  comparative: { label: 'Comparative', tone: 'good' }, revised: { label: 'Revised, explained', tone: 'good' },
  relief: { label: 'Not required', tone: 'neutral' }, impracticable: { label: 'Impracticable, stated', tone: 'neutral' },
  missing: { label: 'No comparative', tone: 'bad' }, reason_missing: { label: 'Reasons needed', tone: 'bad' },
  state_significance: { label: 'Significant?', tone: 'warn' },
}
// a unit as the reader says it (data/reference/esrs/concepts.json units)
export const UNIT: Record<string, string> = {
  monetary: 'amount', percent: '%', count: 'number', boolean: 'yes or no', tCO2eq: 't CO₂e', MWh: 'MWh', m3: 'm³', ha: 'ha',
  year: 'year', score: 'score', other: '', 'monetary/tCO2eq': 'per t CO₂e', 'MWh/monetary': 'MWh per unit of revenue',
  'tCO2eq/monetary': 't CO₂e per unit of revenue', 'm3/EURm': 'm³ per €m revenue',
}
export const unitWord = (u?: string | null) => (!u ? '' : UNIT[u] ?? u.replace(/tCO2eq/g, 't CO₂e').replace(/m3/g, 'm³'))
// the stated value's attestation (provided_datapoint status)
export const ATTEST: Record<string, { label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = {
  attested: { label: 'Attested', tone: 'good' }, pending: { label: 'Awaiting attestation', tone: 'warn' }, rejected: { label: 'Rejected', tone: 'bad' },
}

// who the undertaking is and its method first; the standards' own figures after
export const GROUPS: { label: string; about: string; match: (k: string) => boolean }[] = [
  { label: 'The undertaking', about: 'Its size, status and publication: the facts that decide whether a statement is required, its deadline and the phase-ins.', match: k => k.startsWith('csrd.') },
  { label: 'Method', about: 'The level at which a physical climate risk is material for the undertaking.', match: k => k.startsWith('esrs.method.') },
  { label: 'Financial statements', about: 'Totals the statement\'s shares are taken of: total assets, net revenue.', match: k => k.startsWith('fs.') },
  { label: 'Climate change', about: 'The figures of ESRS E1 you state.', match: k => k.startsWith('e1.') || k.startsWith('esrs2.') },
  { label: 'Water and marine resources', about: 'The figures of ESRS E3 you state.', match: k => k.startsWith('e3.') },
  { label: 'Biodiversity and ecosystems', about: 'The figures of ESRS E4 you state.', match: k => k.startsWith('e4.') },
  { label: 'Other figures', about: 'Figures the statement needs that belong to none of the groups above.', match: () => true },
]
// each figure in the first group that claims it — none is left out (web/tests/esrsFigures.test.ts)
export const groupOf = (key: string) => GROUPS.find(g => g.match(key))!.label
