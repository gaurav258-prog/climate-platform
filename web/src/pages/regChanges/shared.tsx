import type { ReactNode } from 'react'
import { InfoButton, type DetailSection, type Message } from '../../components/Details'

// The Regulatory outlook's data, as the server sends it (services/governance/reg_outlook.py, reg_versions.py,
// reg_alerts.py, services/regulatory_monitoring/early_signals.py): facts, names, and catalogue messages for every
// explanation (core/messages.py). Nothing here is typed in: every figure and date is read from these.

export type Phase = 'in_force' | 'dated' | 'undated'
export interface InForce { framework: string; name: string; authority: string | null; frequency: string | null; requires: string; citation: string | null; url: string | null }
export interface Field { field: string; guidance: string | null; status: 'have' | 'partial' | 'needed'; held: number | null; total: number | null; message: Message }
export interface DataSummary { have: number; partial: number; needed: number; total: number }
export interface Impact { deadline?: { date: string; days: number; band: string }; scope?: { n: number; label: string } }
export interface DraftCounts { added: number; removed: number; changed: number; unchanged: number; rows_added: number; rows_removed: number }
export interface Coming {
  framework: string | null; title: string; name: string | null; date: string | null; days: number | null; phase: Phase; phase_message: Message
  date_fixed: boolean; when: string | null; whats_changing: string | null; prepare: string | null; data_tbc: string | null
  data_message?: Message; message?: Message | null; draft?: DraftCounts | null; would_apply_from?: string | null
  citation: string | null; url: string | null; source: 'curated' | 'draft' | 'detected'; status?: string; detected_at?: string
  verified?: Message; verified_date?: string; date_moved?: boolean; data_fields: Field[]; data_summary?: DataSummary; impact?: Impact
}
export interface Outlook {
  in_force: InForce[]; coming: Coming[]; checked_at: string | null
  summary: { n_in_force: number; n_coming: number; n_ahead: number; n_took_effect: number; n_prepare: number; n_dated: number; n_detected: number; n_verified: number }
}
export interface RelAct { celex: string; title: string; since: string | null; relation?: string; relation_label?: string }
export interface Act {
  celex: string; title: string; role: string; role_label: string; in_force: boolean; in_force_since: string | null; next_effective: string | null
  future: string[]; url: string; live: boolean; not_read: Message | null; ends: string | null; replaced_by: RelAct[]; amendments: RelAct[]
}
export interface FwVersion { framework: string; name: string; authority: string | null; current_since: string | null; amended_by: number; upcoming_effective: string | null; acts: Act[]; checked_at: string | null }
export interface Versions { frameworks: FwVersion[]; checked_at: string | null; checked: Message | null; summary: { n: number; n_upcoming: number } }
export interface Signal {
  signal_id: string; authority: string; jurisdiction: string; jurisdiction_name: string; url: string; title: string; summary: string | null
  published_at: string | null; topics: string[]; status: string; standing: Message; confirmed_title: string | null
}
export interface Signals { signals: Signal[]; jurisdictions: string[]; places: string[]; message: Message }
export interface RegAlert { alert_key: string; framework: string | null; name: string; kind: string; effective_date: string | null; days: number | null; message: Message; task_id: string | null; raised_at: string | null }

// A date as the reader writes it: 30 Dec 2026.
export const day = (s: string | null | undefined) => s ? new Date(`${s.slice(0, 10)}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
export const num = (n: number) => n.toLocaleString('en-GB')
export const plural = (n: number, one: string, many = `${one}s`) => `${num(n)} ${n === 1 ? one : many}`

// Urgency of a change by the days to its date (the bands of services/governance/reg_impact.py).
export function urgency(c: Pick<Coming, 'phase' | 'days'>): { label: string; color: string } {
  if (c.phase === 'in_force') return { label: 'In force', color: 'var(--color-good)' }
  if (c.phase === 'undated' || c.days == null) return { label: 'Date not set', color: 'var(--color-slate)' }
  const color = c.days <= 90 ? 'var(--color-bad)' : c.days <= 365 ? 'var(--color-warn)' : 'var(--color-sky)'
  return { label: c.days === 0 ? 'Today' : plural(c.days, 'day'), color }
}

// The urgency chip: days to go (or In force / Date not set), in the urgency's colour — StatusChip's shape.
export function UrgencyChip({ c }: { c: Pick<Coming, 'phase' | 'days'> }) {
  const u = urgency(c)
  return (
    <span className="inline-flex items-center gap-1.5 text-[11.5px] font-medium px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ color: u.color, background: `color-mix(in oklab, ${u.color} 13%, transparent)` }}>
      <span className="w-1.5 h-1.5 rounded-full" style={{ background: u.color }} />{u.label}
    </span>
  )
}

// A titled block inside a drawer, with its explanation one click away.
export function Block({ title, info, aside, children }: { title: string; info?: DetailSection[]; aside?: ReactNode; children: ReactNode }) {
  return (
    <section>
      <div className="flex items-center gap-1.5 mb-2">
        <h4 className="text-[13px] font-semibold text-[var(--color-ink)] m-0">{title}</h4>
        {info && <InfoButton compact details={{ title, sections: info }} />}
        {aside && <span className="ml-auto">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

// A 100% bar of parts, each coloured, with the counts on hover.
export function PartsBar({ parts, height = 8, label }: { parts: { label: string; n: number; color: string }[]; height?: number; label?: string }) {
  const shown = parts.filter(p => p.n > 0)
  const total = shown.reduce((a, p) => a + p.n, 0)
  return (
    <div className="flex w-full overflow-hidden rounded-full bg-[var(--color-panel-2)]" style={{ height }} role="img"
      aria-label={label ?? (shown.map(p => `${p.label} ${num(p.n)}`).join(', ') || 'None')}>
      {shown.map(p => <div key={p.label} title={`${p.label}: ${num(p.n)}`} style={{ width: `${(p.n / total) * 100}%`, background: p.color, minWidth: 3 }} />)}
    </div>
  )
}

export function Swatches({ parts }: { parts: { label: string; color: string }[] }) {
  return <div className="flex flex-wrap gap-x-3 gap-y-1">{parts.map(p => <span key={p.label} className="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: p.color }} />{p.label}</span>)}</div>
}

// Field readiness colours: held, partly held, to provide.
export const HELD = {
  have: { label: 'You hold', color: 'var(--color-good)' },
  partial: { label: 'Partly held', color: 'var(--color-warn)' },
  needed: { label: 'To provide', color: 'var(--color-slate)' },
} as const
