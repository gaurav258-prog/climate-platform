import type { Message } from '../../components/Details'
import { balance, flow } from '../../lib/money'

// The KRI dashboard's data, as /v1/reg-tasks/kri sends it (services/governance/kri*.py). Every explanation is a catalogue
// message (about, needs, missing, filed); the numbers behind an indicator are its facts, each named by the server.

export type Status = 'ok' | 'amber' | 'red'
export type FactUnit = 'eur' | 'eur_flow' | 'pct' | 'num' | 'bps' | 'x' | 't' | 'text'
export interface Fact { key: string; label: string; value: number | string | null; unit: FactUnit }
export interface Kpi {
  key: string; label: string; value: number | null; fmt: 'eur' | 'pct' | 'num' | 'dec' | 'ha'; tone: string | null
  about: Message | null; needs: Message | null; missing: Message | null; gap: string | null; facts: Fact[]
  integrated?: boolean; kind?: 'computed' | 'integrated'; flow?: boolean
  status?: Status | null; amber?: number | null; red?: number | null; direction?: 'higher_worse' | 'lower_worse' | null; breached?: boolean
  reg?: string; reg_tier?: 'core' | 'support'; live_only?: boolean | null; filed?: Message
  group?: string; row?: { id: string; label: string }; column?: string; column_name?: string
}
export interface Regulator { authority: string; disclosure: string; legal_basis: string; form_url: string | null }
export interface Readiness { core: number; covered: number; integrated: string[]; gaps: string[] }
export interface Haz { hazard: string; value: number; score: number }
export interface HistFig { key: string; label: string; value: number | null; fmt: string; group?: string }
export interface Hist { label: string; filing_id: string | null; total_value: number | null; value_at_risk: number | null; pct_at_risk: number | null; figures?: HistFig[] }
export interface Basis { kpis: 'live'; message: Message; last_filed: { period_label: string; filing_id: string | null } | null }
export interface Undertaking { entity_id: string | null; name: string; role?: string }
export interface KriSet {
  framework: string; supported: boolean; label: string; kpis: Kpi[]; by_hazard: Haz[]; history: Hist[]; notice?: Message
  breaches?: number; scope?: Message; regulator?: Regulator; readiness?: Readiness; basis?: Basis
  undertaking?: Undertaking; undertakings?: Undertaking[]
}
export interface Framework { framework: string; label: string }

export const RAG: Record<Status, string> = { ok: 'var(--color-good)', amber: 'var(--color-warn)', red: 'var(--color-bad)' }
export const STATUS_WORD: Record<Status, string> = { ok: 'Within appetite', amber: 'Warning', red: 'Outside appetite' }
export const kindOf = (k: Kpi): 'computed' | 'integrated' => k.kind ?? (k.integrated ? 'integrated' : 'computed')

// a small or large plain number, to three significant figures where it has a fraction (0.000943 → 0.000943, 798.7 → 799)
const dec = (v: number) => Math.abs(v) >= 100 ? Math.round(v).toLocaleString('en-GB')
  : Number(v.toPrecision(3)).toLocaleString('en-GB', { maximumSignificantDigits: 3 })

export function value(k: Pick<Kpi, 'value' | 'fmt' | 'flow'>): string {
  const v = k.value
  if (v == null) return '—'
  if (k.fmt === 'eur') return k.flow ? flow(v) : balance(v)
  if (k.fmt === 'pct') return `${dec(v)}%`
  if (k.fmt === 'ha') return `${dec(v)} ha`
  if (k.fmt === 'dec') return dec(v)
  return Math.round(v).toLocaleString('en-GB')
}

export function factValue(f: Fact): string {
  const v = f.value
  if (v == null || v === '') return '—'
  if (typeof v === 'string') return v
  switch (f.unit) {
    case 'eur': return balance(v)
    case 'eur_flow': return flow(v)
    case 'pct': return `${dec(v)}%`
    case 'bps': return `${dec(v / 100)}%`
    case 'x': return `${dec(v)}×`
    case 't': return `${Math.round(v).toLocaleString('en-GB')} t`
    default: return dec(v)
  }
}

// an appetite level in the indicator's own unit (money bands are set in the engine's currency, euro)
export function level(k: Kpi, v: number | null | undefined): string {
  if (v == null) return '—'
  return k.fmt === 'eur' ? balance(v) : k.fmt === 'pct' ? `${dec(v)}%` : dec(v)
}

// the band in words, for the task a breach raises: '53.7% · warning at 15% · breach at 30%'
export function bandWords(k: Kpi): string {
  const parts = [value(k)]
  if (k.amber != null) parts.push(`warning at ${level(k, k.amber)}`)
  if (k.red != null) parts.push(`breach at ${level(k, k.red)}`)
  return parts.join(' · ')
}
