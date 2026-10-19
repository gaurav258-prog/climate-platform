// Customer words for the codes the calendar, the control register, the third-party register and the site and plot
// pages print (UI standard, 2026-10-16): a code never reaches a screen as-is. Each list mirrors the server's own —
// named beside it — and web/tests/codeWords.test.ts fails when the server gains a code these words do not cover.

// how often a filing is due: the catalogue's names.frequency (data/reference/messages.en.json); an obligation whose
// frequency is already written in words ('on change') reads as it is
export const FREQUENCY: Record<string, string> = {
  annual: 'Annual', semiannual: 'Half-yearly', adhoc: 'On each event', 'at least every two years': 'At least every two years',
}
export const frequencyWord = (f?: string | null): string | null =>
  !f ? null : FREQUENCY[f] ?? (/^[a-z]+(?:_[a-z]+)+$/.test(f) ? null : f[0].toUpperCase() + f.slice(1))

// a supervised entity's flag against the supervisor's expectations: the catalogue's names.peer_flag
export const PEER_FLAG: Record<string, string> = { act: 'Act', watch: 'Watch', ok: 'Within expectation', na: 'Not judged' }

// the filings a supervision profile expects of a sector (data/reference/supervision_profiles.json sectors.*.frameworks),
// named as the mandate register names the deliverable (data/reference/regulatory_mandates.json)
export const PROFILE_FRAMEWORK: Record<string, string> = {
  pillar3_esg: 'Pillar 3 disclosure of ESG risks', eba_climate_stress: 'EBA climate stress test',
  csrd_esrs: 'CSRD sustainability statement (ESRS)', eu_taxonomy_art8: 'EU Taxonomy Article 8 disclosures',
  eudr: 'EUDR due diligence statement', orsa_climate: 'Climate change scenario analysis in the ORSA',
  sfdr: 'SFDR disclosures', solvency2_qrt: 'Solvency II quantitative reporting',
}

// what a calendar entry is (services/governance/reg_calendar.py kind)
export const CALENDAR_KIND: Record<string, string> = { obligation: 'Filing deadline', task: 'Task due', reg_change: 'Rule change' }

// an operating site's type and a plot's declared water management (services/ingest/fields.py VOCAB site_type, irrigation)
export const SITE_TYPE: Record<string, string> = {
  hq: 'Head office', factory: 'Factory', warehouse: 'Warehouse', distribution_centre: 'Distribution centre', office: 'Office', other: 'Other site',
}
export const IRRIGATION: Record<string, string> = { irrigated: 'Irrigated', rain_fed: 'Rain-fed', mixed: 'Irrigated and rain-fed' }
// what a plot's own EUDR declaration says (sc_sourcing_plots eudr_status — the customer's flag, not a reading)
export const EUDR_DECLARED: Record<string, string> = { compliant: 'Declared compliant', unknown: 'Not declared' }

// a reporting control's type and what started its last test (data/reference/reporting_controls.json type;
// services/governance/controls.py test_all trigger)
export const CONTROL_TYPE: Record<string, string> = { preventive: 'Preventive', detective: 'Detective' }
export const CONTROL_TRIGGER: Record<string, string> = { manual: 'on request', sweep: 'in the daily check' }

// a third party's criticality and how precisely its address was located (services/intelligence/third_parties.py
// CRITICALITY; services/geocoding/nominatim.py precision buckets, 'exact' for stated coordinates)
export const CRITICALITY: Record<string, string> = { critical: 'Critical', important: 'Important', standard: 'Standard' }
export const PRECISION: Record<string, string> = {
  exact: 'Exact coordinates', address: 'Located to the address', street: 'Located to the street', city: 'Located to the town',
  place: 'Located to the place', region: 'Located to the region only', country: 'Located to the country only',
}

// a country's English name from its two-letter code (a place already written as a name reads as it is); the code
// itself only when the browser has no name for it
let regions: Intl.DisplayNames | null | undefined
export function countryName(code?: string | null): string | null {
  const c = code?.trim()
  if (!c) return null
  if (!/^[A-Za-z]{2}$/.test(c)) return c
  if (regions === undefined) regions = typeof Intl !== 'undefined' && 'DisplayNames' in Intl ? new Intl.DisplayNames(['en'], { type: 'region' }) : null
  try { return regions?.of(c.toUpperCase()) ?? c } catch { return c }
}

// where an exposure is: its region and its country, each in words, the same place never twice ('EU, EU' → 'European Union')
export function placeLine(region?: string | null, country?: string | null): string {
  const parts = [countryName(region), countryName(country)].filter((x): x is string => !!x)
  return [...new Set(parts)].join(', ') || '—'
}

// a share as a percentage, at most one decimal place — a median of rounded shares is a float (33.599999999999994)
export const percent = (v: number | null | undefined): string =>
  v == null || !Number.isFinite(v) ? '—' : `${Number(v.toFixed(1)).toLocaleString('en-GB')}%`
