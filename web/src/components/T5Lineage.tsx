import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CheckCircle2, AlertTriangle, Route } from 'lucide-react'
import { api } from '../lib/api'
import { money } from '../lib/money'
import { Card, Lens, SectionHead } from './ui'
import { hazardLabel, modelLabel } from '../lib/hazards'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { Dialog } from './Dialog'
import { plural } from './intake/parts'

// Pillar 3 physical-risk exposures (Template 5, E105) traced cell by cell: pick a printed row for a column and a
// geography, and see the exposures it adds up — each with the hazards that make it sensitive at your threshold, as filed
// and as scored today. Read from the frozen filing; the printed value and the sum of its exposures sit side by side.
// The template's own numbering and title sit one click away.

interface Axis { id: string; label: string }
interface View { supported: boolean; framework?: string; msg?: Message; title: string; at_risk_level: number; currency: string; rows: Axis[]; columns: Axis[]; geographies: { code: string; label: string }[]; cells: Record<string, Record<string, Record<string, number | null>>> }
interface Hit { hazard: string; category: string; filed: { score: number | null; model_version: string | null }; granular: { risk_score: number | null; model_version: string | null } | null; drift: boolean }
interface Contributor { asset_id: string; asset_name: string; country: string | null; nace_code: string | null; amount?: number; weight?: number; maturity?: number; ifrs9_stage: string | null; hazards: Hit[] }
interface Trace { supported: boolean; msg?: Message; cell: { printed: number | null; from_contributors: number | null; ties: boolean; kind: string }; n_in_row: number; contributors: Contributor[]; drift_count: number; currency: string }

const short = (s: string) => s.split(' > ').slice(-1)[0]
const KIND: Record<string, string> = { chronic: 'chronic', acute: 'acute' }

export default function T5Lineage({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['lineage-t5', filingId], queryFn: () => api.get<View>(`/v1/filings/${filingId}/lineage/t5`) })
  const [row, setRow] = useState<Axis | null>(null)
  const [col, setCol] = useState<string>('h')
  const [geo, setGeo] = useState<string>('ALL')
  const v = q.data
  if (!v) return null
  if (!v.supported) return v.framework === 'bank_p3esg' && v.msg ? <MessageLine m={v.msg} className="px-1 text-[12.5px] text-[var(--color-mute)]" /> : null
  const val = (rid: string) => v.cells[geo]?.[rid]?.[col] ?? null
  const years = col === 'g'
  const fmt = (n: number | null) => n == null ? '—' : years ? `${n} years` : money(n, v.currency)
  const max = Math.max(1, ...v.rows.map(r => Math.abs(val(r.id) ?? 0)))
  const sel = 'bg-[var(--color-bg-2)] border border-[var(--color-line-2)] rounded-lg px-2 py-1 text-[12px] text-[var(--color-ink)] max-w-full'
  const column = v.columns.find(c => c.id === col)
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap px-1">
        <SectionHead icon={Route}>Exposures sensitive to physical risk</SectionHead>
        <InfoButton compact details={{ title: 'Exposures sensitive to physical risk', sections: [
          { heading: HEADING.shows, body: `${v.title}: each printed figure for the column and geography you choose. Select a row to see the exposures it adds up, and the hazards that make each one sensitive.` },
          { heading: HEADING.read, body: `An exposure counts as sensitive when a chronic or acute hazard at its location scores at or above your at-risk threshold (${v.at_risk_level}). The printed figure and the sum of its exposures are shown side by side; they must agree.` },
          { heading: HEADING.sources, body: 'The frozen filing: its banking book exposure by exposure, the template version it was prepared under and your stated threshold.' }] }} />
        <StatusChip tone="neutral" label={`Threshold ${v.at_risk_level}`} />
        <Lens kind="insight" className="ml-auto" />
      </div>
      <Card className="p-4 space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          <select aria-label="Figure" className={sel} value={col} onChange={e => setCol(e.target.value)}>
            {v.columns.map(c => <option key={c.id} value={c.id}>{short(c.label)}</option>)}
          </select>
          <select aria-label="Geography" className={sel} value={geo} onChange={e => setGeo(e.target.value)}>
            {v.geographies.map(g => <option key={g.code} value={g.code}>{g.label}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          {v.rows.map(x => {
            const n = val(x.id)
            return (
              <button key={x.id} onClick={() => setRow(x)}
                className="w-full flex items-center gap-2 text-left rounded-lg px-2 py-1.5 hover:bg-[var(--color-panel)] transition group">
                <span className="flex-1 min-w-0 text-[12.5px] text-[var(--color-ink)] truncate group-hover:text-[var(--color-sky)]">{x.label}</span>
                <span className="hidden sm:block w-28 h-1.5 rounded-full bg-[var(--color-line)] overflow-hidden shrink-0">
                  <span className="block h-full rounded-full bg-[var(--color-sky)]" style={{ width: `${n ? Math.max(2, (Math.abs(n) / max) * 100) : 0}%` }} />
                </span>
                <span className="tabular-nums text-[12px] text-[var(--color-mute)] w-24 text-right">{fmt(n)}</span>
              </button>)
          })}
        </div>
      </Card>
      {row && (
        <Dialog title={row.label} onClose={() => setRow(null)} className="sm:max-w-3xl">
          <CellTrace filingId={filingId} row={row.id} col={col} colLabel={column ? short(column.label) : ''} geo={geo} />
        </Dialog>)}
    </div>
  )
}

function CellTrace({ filingId, row, col, colLabel, geo }: { filingId: string; row: string; col: string; colLabel: string; geo: string }) {
  const q = useQuery({ queryKey: ['lineage-t5-cell', filingId, row, col, geo],
    queryFn: () => api.get<Trace>(`/v1/filings/${filingId}/lineage/t5/cell?row=${encodeURIComponent(row)}&column=${col}&geography=${encodeURIComponent(geo)}`) })
  const d = q.data
  if (q.isLoading) return <div className="text-[12.5px] text-[var(--color-faint)]">Tracing…</div>
  if (!d) return <div className="text-[12.5px] text-[var(--color-bad)]">This figure could not be traced.</div>
  if (!d.supported) return d.msg ? <MessageLine m={d.msg} className="text-[12.5px] text-[var(--color-mute)]" /> : null
  const avg = d.cell.kind === 'weighted_average'
  const show = (n: number | null) => n == null ? '—' : avg ? `${n} years` : money(n, d.currency)
  return (
    <div className="space-y-3">
      <div className="text-[12px] text-[var(--color-mute)]">{colLabel}</div>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[12px] text-[var(--color-mute)]">Printed <span className="display text-[18px] tabular-nums text-[var(--color-ink)] ml-1">{show(d.cell.printed)}</span></span>
        <span className="text-[12px] text-[var(--color-mute)]">{avg ? 'Weighted average of' : 'Sum of'} {plural(d.contributors.length, 'exposure')} <span className="display text-[18px] tabular-nums text-[var(--color-ink)] ml-1">{show(d.cell.from_contributors)}</span></span>
        {d.cell.ties ? <span className="inline-flex items-center gap-1 text-[12px] text-[var(--color-good)]"><CheckCircle2 size={13} /> Ties</span>
          : <span className="inline-flex items-center gap-1 text-[12px] text-[var(--color-bad)]"><AlertTriangle size={13} /> Does not tie</span>}
        {d.drift_count > 0 && <StatusChip tone="warn" label={`${plural(d.drift_count, 'score')} re-computed since`} />}
        <span className="text-[11.5px] text-[var(--color-faint)] ml-auto">{plural(d.n_in_row, 'exposure')} in the row</span>
      </div>
      <div className="space-y-1.5 max-h-[55vh] overflow-y-auto">
        {d.contributors.map(c => (
          <div key={c.asset_id} className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-3 py-2">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="min-w-0 flex-1 text-[12.5px] text-[var(--color-ink)] truncate">{c.asset_name}{c.country ? <span className="text-[var(--color-faint)]"> · {c.country}</span> : null}</span>
              {c.ifrs9_stage && <StatusChip tone="neutral" label={`Stage ${c.ifrs9_stage}`} />}
              <InfoButton compact details={{ title: c.asset_name, sections: [
                ...(c.nace_code ? [{ heading: 'Activity (NACE)', body: c.nace_code }] : []),
                ...c.hazards.map(h => ({ heading: hazardLabel(h.hazard), body: `Filed ${h.filed.score ?? '—'} (${modelLabel(h.filed.model_version)}); today ${h.granular?.risk_score ?? '—'} (${modelLabel(h.granular?.model_version)}).` }))] }} />
              <span className="tabular-nums text-[12.5px] text-[var(--color-ink)]">{avg ? `${c.maturity} years × ${money(c.weight ?? null, d.currency)}` : money(c.amount ?? null, d.currency)}</span>
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {c.hazards.map(h => (
                <span key={h.hazard} className="text-[11px] rounded-full border px-2 py-0.5"
                  style={{ borderColor: h.drift ? 'var(--color-warn)' : 'var(--color-line-2)', color: h.drift ? 'var(--color-warn)' : 'var(--color-mute)' }}>
                  {hazardLabel(h.hazard)} · {KIND[h.category] ?? 'hazard'} · {h.filed.score ?? '—'}
                </span>))}
            </div>
          </div>))}
      </div>
    </div>
  )
}
