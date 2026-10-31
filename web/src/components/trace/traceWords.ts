// The words of a figure's trace (/v1/filings/{id}/trace, services/governance/figure_trace.py): what each node is called on
// the graph — short, plain, no citation — and what its pop-up says, one section per fact, the law quoted there only.
// The server sends facts under machine keys and catalogue messages; nothing here is a server sentence printed raw.
import { hazardLabel, modelLabel } from '../../lib/hazards'
import { money } from '../../lib/money'
import type { Message } from '../Details'
import { fmtDate } from '../filing/words'

export type Tone = 'good' | 'warn' | 'out'
export interface TraceNode {
  id: string; layer: string; kind: string; label: string | null; facts?: Record<string, any>; tone?: Tone
  msgs?: Message[]; quote?: { text: string; ref: string | null; found_in: string | null; found_in_title?: string | null }; group?: string
}
export interface Section { heading: string; body: string | string[] }

export const LAYER: Record<string, string> = {
  law: 'The law', spec: 'Specification', cell: 'The figure', basis: 'How it was computed', book: 'The book', source: 'What it read',
}
export const PERIL: Record<string, string> = {
  windstorm: 'Windstorm', earthquake: 'Earthquake', flood: 'Flood', hail: 'Hail', subsidence: 'Subsidence',
}
const FILLED: Record<string, string> = { computed: 'Computed by Tellumen', input: 'You provide', 'n/a': 'Not applicable' }
const CONSOLIDATED: Record<string, string> = { full: 'In full', proportional: 'By the share held', equity: 'By the equity method' }
const RUN: Record<string, string> = { pass: 'All checks passed', warn: 'Passed, with points to look at' }
const METHOD: Record<string, string> = { method_1: 'Method 1', method_2: 'Method 2' }
const FEED: Record<string, string> = {
  fresh: 'Up to date', live: 'Live', due_soon: 'Due for refresh', overdue: 'Overdue', failed: 'Last refresh failed', untracked: 'No refresh recorded',
}

const day = (s?: string | null) => (s ? fmtDate(s) : '—')
const pct = (x?: number | null, dp = 0) => (x == null ? '—' : `${(x * 100).toFixed(dp)}%`)
const yes = (b?: boolean | null, y = 'Yes', n = 'No') => (b == null ? 'Not known' : b ? y : n)
const f = (n: TraceNode) => n.facts ?? {}

// The value a cell prints, as the form shows it: an amount, a charge factor, or the text it holds (a scenario, options).
export function cellValue(facts: Record<string, any>): string {
  const v = facts.value
  if (v == null) return '—'
  if (facts.value_kind === 'ratio' && typeof v === 'number') return `${(v * 100).toFixed(4)}%`
  if (facts.value_kind === 'years' && typeof v === 'number') return `${v} years`
  if (typeof v === 'number') return money(v, facts.currency)
  return String(v)
}

// A stated value as it reads: an amount in its currency, a score out of 100, or the value with its unit.
function statedValue(x: Record<string, any>, full = false): string {
  if (x.value == null) return '—'
  if (typeof x.value === 'number' && (x.currency || x.unit === 'EUR')) return money(x.value, x.currency || 'EUR', { full })
  if (x.unit === 'score') return `${x.value} of 100`
  if (x.unit === '%') return `${x.value}%`
  if (x.unit === 'count') return String(x.value)
  return `${x.value}${x.unit ? ` ${x.unit}` : ''}`
}

// A statement's name on the graph: the part after a shared lead ('Reinsurance in force — quota share ceded (%)' →
// 'Quota share ceded (%)'); the whole name is in its pop-up.
const shortName = (s: string) => {
  const tail = s.includes(' — ') ? s.split(' — ').pop()! : s
  return tail ? tail[0].toUpperCase() + tail.slice(1) : s
}

// The node's name on the graph.
export function title(n: TraceNode): string {
  const x = f(n)
  switch (n.kind) {
    case 'act': return x.role === 'formula' ? 'The formula' : 'The reporting templates'
    case 'spec': return 'Specification'
    case 'instruction': return 'Instruction for this cell'
    case 'cell': return n.label ?? 'This figure'
    case 'formula': return 'Standard formula'
    case 'statement': return n.label ? shortName(n.label) : (n.id === 'stmt-treaty' ? 'Reinsurance treaty' : 'Your statement')
    case 'method': return n.label ?? 'Undertaking'
    case 'undertaking': return n.label ?? 'Undertaking'
    case 'policy': return n.label ?? 'Policy'
    case 'more': return `${x.hidden} more`
    case 'run': return 'The book as read'
    case 'batch': return 'Last data file'
    case 'tables': return 'Formula tables'
    case 'rule': return 'How the cell is computed'
    case 'exposure': return n.label ?? 'Exposure'
    case 'score': return hazardLabel(x.hazard)
    case 'feed': return n.label ?? 'Data feed'
    default: return n.label ?? '—'
  }
}

// The node's one short line under its name.
export function sub(n: TraceNode): string {
  const x = f(n), ccy = x.currency
  const msg = n.msgs?.[0]?.label
  switch (n.kind) {
    case 'act': return n.quote?.found_in || x.text_held ? 'Official text held' : 'Official text not held'
    case 'spec': return x.changed_since ? 'Changed since this report' : x.approved ? (x.one_person ? 'Signed by one person' : 'Signed by two people') : 'Not signed'
    case 'instruction': return n.quote?.found_in ? 'Quoted word for word' : 'Quote not found'
    case 'cell': return `${x.column_label ?? ''} · ${cellValue(x)}`
    case 'formula': {
      if (x.region_name) return `${PERIL[x.peril] ?? ''} · ${x.n_policies ?? 0} policies`
      if (x.peril) return `${PERIL[x.peril] ?? ''} · ${x.n_regions != null ? `${x.n_regions} regions` : 'other regions'}`
      return msg ?? 'All perils'
    }
    case 'statement': return msg ?? statedValue(x)
    case 'method': return msg ?? (x.method ?? 'Not stated').split(' — ')[0]
    case 'undertaking': return n.tone === 'out' ? (msg ?? 'Left out') : `${x.n_policies ?? 0} policies · ${money(x.sum_insured, ccy)}`
    case 'policy': return `${money(x.sum_insured, ccy)}${x.country ? ` · ${x.country}` : ''}`
    case 'more': return 'Show more'
    case 'run': return msg ?? `${(x.books ?? [])[0]?.n_assets ?? '—'} records read`
    case 'batch': return msg ?? `Landed ${day(x.imported_at)}`
    case 'tables': return 'Official tables'
    case 'rule': return msg ?? (x.kind === 'weighted_average' ? 'Average maturity' : `Sum of ${x.n_contributors ?? 0} exposures`)
    case 'exposure': return `${x.amount != null ? money(x.amount, ccy) : `${x.maturity ?? '—'} years`}${x.country ? ` · ${x.country}` : ''}`
    case 'score': return `Scores · ${x.drift ? `${x.drift} re-scored since` : `${x.n_exposures ?? 0} exposures`}`
    case 'feed': return `${FEED[x.status] ?? 'Status not known'}${x.last_refresh ? ` · ${day(x.last_refresh)}` : ''}`
    default: return msg ?? ''
  }
}

// The node's pop-up: what it is, fact by fact, with any message and the law as quoted.
export function details(n: TraceNode): Section[] {
  const x = f(n), ccy = x.currency
  const m = (v: unknown) => (typeof v === 'number' ? money(v, ccy, { full: true }) : '—')
  const out: Section[] = []
  const add = (heading: string, body: unknown) => {
    if (body == null || body === '' || (Array.isArray(body) && !body.length)) return
    out.push({ heading, body: Array.isArray(body) ? body.map(String) : String(body) })
  }
  switch (n.kind) {
    case 'act':
      add('The act', n.label)
      add('Legal basis', x.article)
      add('Templates', x.templates_in)
      add('Instructions', x.instructions_in)
      add('Official reference', x.official_reference ?? x.held_as)
      add('Official text', x.source)
      add('In force', x.applies_from ? `From ${day(x.applies_from)}${x.applies_until ? ` to ${day(x.applies_until)}` : ''}` : null)
      add('Official text held', yes(x.text_held))
      break
    case 'spec':
      add('Version', x.version)
      add('Since this report was frozen', x.changed_since == null ? 'Not known' : x.changed_since ? 'Changed' : 'Unchanged')
      add('In force from', x.applies_from ? day(x.applies_from) : null)
      add('Signed off', (x.signed ?? []).map((s: any) => `${s.role === 'engineering' ? 'Engineering review' : s.role === 'regulatory' ? 'Regulatory review' : s.role} · ${s.by} · ${day(s.at)}`))
      if (x.one_person) add('Not a four-eyes review', 'One person signed both reviews.')
      add('Fingerprint of the file', x.fingerprint)
      add('Readings the specification declares', (x.readings ?? []).map((r: any) => `${r.subject}: ${r.reading}`))
      break
    case 'instruction':
      add('Where', x.printed_ref && x.printed_ref !== x.ref ? `${x.ref} (printed ${x.printed_ref})` : x.ref)
      add('Item', n.label)
      break
    case 'cell':
      add('Template', x.template)
      add('Row', `${x.row} · ${x.row_label}`)
      add('Column', `${x.column} · ${x.column_label}`)
      add('Block', x.section)
      add('As filed', cellValue(x))
      add('How the row is filled', FILLED[x.row_source] ?? null)
      add('How the column is filled', FILLED[x.column_source] ?? null)
      add('Geography', x.geography)
      add('Reporting period', x.period ? `${day(x.period.start)} to ${day(x.period.end)} · ${x.period.words}` : null)
      if (x.tie?.printed_exposure !== undefined) add('Adds up', `${x.tie.traced_n} policies placed here add up to ${money(x.tie.traced_exposure, ccy, { full: true })}; the form prints ${money(x.tie.printed_exposure, ccy, { full: true })} for ${x.tie.printed_n}.`)
      else if (x.tie) add('Adds up', x.tie.kind === 'weighted_average'
        ? `The ${x.tie.traced_n} exposures counted average ${x.tie.traced ?? '—'} years; the form prints ${x.tie.printed ?? '—'}.`
        : `The ${x.tie.traced_n} exposures counted add up to ${money(x.tie.traced, ccy, { full: true })}; the form prints ${money(x.tie.printed, ccy, { full: true })}.`)
      break
    case 'formula':
      add('Formula', x.version)
      add('Reference date', x.reference_date ? day(x.reference_date) : null)
      add('Legal basis', x.citation)
      add('Region', x.region_name)
      add('Policies', x.n_policies)
      add('Exposure', x.exposure_eur != null ? m(x.exposure_eur) : null)
      add('Specified gross loss', x.specified_gross_loss_eur != null ? m(x.specified_gross_loss_eur) : null)
      add('Charge factor', x.charge_factor != null ? `${(x.charge_factor * 100).toFixed(4)}%` : null)
      add('Scenario', x.scenario)
      add('Premiums to be earned', x.premium_eur != null ? m(x.premium_eur) : null)
      add('Diversification of the premiums', x.div)
      add('Regions', x.n_regions)
      add('Before risk mitigation', x.before_eur != null ? m(x.before_eur) : x.all_before_eur != null ? m(x.all_before_eur) : null)
      add('Risk mitigation', x.mitigation_eur != null ? m(x.mitigation_eur) : null)
      add('Reinstatement premiums', x.reinstatement_eur != null ? m(x.reinstatement_eur) : null)
      add('After risk mitigation', x.after_eur != null ? m(x.after_eur) : null)
      add('Diversification', x.diversification_before_eur != null ? `${m(-x.diversification_before_eur)} before, ${m(-(x.diversification_after_eur ?? 0))} after risk mitigation` : null)
      add('By peril, after risk mitigation', x.by_peril_eur ? Object.entries(x.by_peril_eur).map(([p, v]) => `${PERIL[p] ?? p}: ${m(v)}`) : null)
      add('Grouped regions', (x.grouped ?? []).filter((g: any) => g.regions.length).map((g: any) => `${PERIL[g.peril] ?? g.peril}: ${g.regions.join(', ')}`))
      add('Declared readings', (x.readings ?? []).map((r: any) => `${r.subject}: ${r.reading}`))
      break
    case 'statement':
      add('Statement', n.label)
      add('Value', x.value == null ? null : statedValue(x, true))
      if (!n.msgs?.length) add('Attested by', x.attested_by ?? 'Not recorded with this report')
      add('Attested on', x.attested_at ? day(x.attested_at) : null)
      add('Provided by', x.provider)
      add('For the period ending', x.period_end ? day(x.period_end) : null)
      break
    case 'method':
      add('Method', x.method)
      add('Attested by', x.attested_by)
      add('Attested on', x.attested_at ? day(x.attested_at) : null)
      break
    case 'undertaking':
      add('Method', METHOD[x.method] ?? (x.method ? null : 'Not stated'))
      add('Consolidated', x.consolidation_method ? `${CONSOLIDATED[x.consolidation_method] ?? '—'}${x.consolidation_method === 'proportional' && x.ownership_pct != null ? ` (${x.ownership_pct}%)` : ''}` : null)
      add('Share in this report', x.weight != null ? pct(x.weight) : null)
      add('Policies in this figure', x.n_policies)
      add('Sum insured in this figure', x.sum_insured != null ? m(x.sum_insured) : null)
      add('Policies left out', x.n_policies_left_out)
      break
    case 'policy':
      add('Undertaking', x.undertaking)
      add('Country', x.country)
      add('Postal code', x.postal_code ?? 'Not given')
      add('Zone', x.zone ?? 'Not placed in a zone')
      add('Sum insured in this report', x.sum_insured != null ? m(x.sum_insured) : null)
      break
    case 'run':
      add('Read on', x.run_at ? day(x.run_at) : null)
      add('Checks', RUN[x.status] ?? null)
      add('Books read', (x.books ?? []).map((b: any) => `${b.label}: ${b.n_assets} records, ${money(b.total_value_eur, 'EUR', { full: true })}${b.fingerprint ? ` · fingerprint ${b.fingerprint}` : ''}`))
      add('Fingerprint of everything read', x.fingerprint)
      add('Differences with your values still open', x.open_differences)
      break
    case 'batch':
      add('Data file', x.template)
      add('Landed on', x.imported_at ? day(x.imported_at) : null)
      break
    case 'tables':
      add('Version', x.version)
      add('Checked against', x.source)
      break
    case 'rule':
      add('Computed as', x.kind === 'weighted_average' ? 'The average maturity of the exposures counted, weighted by their gross carrying amount' : 'The sum of the gross carrying amounts of the exposures counted')
      add('Exposures counted', x.n_contributors)
      add('Exposures in the row', x.n_in_row)
      add('Your at-risk threshold', x.at_risk_level != null ? `${x.at_risk_level} of 100` : 'Not stated')
      break
    case 'exposure':
      add('Counted in this cell', x.amount != null ? m(x.amount) : x.maturity != null ? `${x.maturity} years, weighted by ${m(x.weight)}` : null)
      add('Gross carrying amount', x.gross_carrying_amount != null ? m(x.gross_carrying_amount) : null)
      add('Country', x.country)
      add('Sector code', x.nace_code)
      add('IFRS 9 stage', x.ifrs9_stage)
      add('Hazards that make it sensitive', (x.hazards ?? []).map((h: any) => `${hazardLabel(h.hazard)}: score ${h.score ?? '—'} as filed${h.drift ? ', re-scored on a newer model since' : ''}`))
      break
    case 'score':
      add('Hazard', hazardLabel(x.hazard))
      add('Exposures it makes sensitive here', x.n_exposures)
      add('Model as filed', (x.models ?? []).map((v: string) => modelLabel(v)))
      add('Re-scored on a newer model since', x.drift ? `${x.drift} exposures: the filing keeps the scores it was frozen with` : 'None')
      break
    case 'feed':
      add('Feed', n.label)
      add('Status', FEED[x.status] ?? 'Not known')
      add('Last updated', x.last_refresh ? day(x.last_refresh) : null)
      break
  }
  for (const msg of n.msgs ?? []) {                // a catalogue message: its label, then why and what to do, each headed
    const d = msg.detail ?? {}
    add(msg.label, d.what ?? '')
    add('Why', d.why)
    add('What you can do', d.next)
  }
  return out
}
