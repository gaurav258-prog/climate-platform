import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowDownRight, AlertTriangle, CheckCircle2 } from 'lucide-react'
import { api } from '../lib/api'
import { money } from '../lib/money'
import { Card } from './ui'
import { hazardLabel } from '../lib/hazards'

// Pillar 3 Template 5 lineage (E105): pick a printed cell — row × column × geography — and see the exposures it sums,
// each with the hazards that make it sensitive at the stated level, down to the golden-source row. Read from the frozen
// filing; the printed value and the sum of its contributors are shown side by side.

interface Axis { id: string; label: string }
interface View { supported: boolean; framework?: string; message?: string; title: string; at_risk_level: number; currency: string; rows: Axis[]; columns: Axis[]; geographies: { code: string; label: string }[]; cells: Record<string, Record<string, Record<string, number | null>>> }
interface Hit { hazard: string; category: string; filed: { score: number | null; model_version: string | null }; granular: { risk_score: number | null; model_version: string | null } | null; drift: boolean }
interface Contributor { asset_id: string; asset_name: string; country: string | null; nace_code: string | null; amount?: number; weight?: number; maturity?: number; ifrs9_stage: string | null; hazards: Hit[] }
interface Trace { supported: boolean; message?: string; cell: { printed: number | null; from_contributors: number | null; ties: boolean; kind: string }; n_in_row: number; contributors: Contributor[]; drift_count: number; currency: string }

const short = (s: string) => s.split(' > ').slice(-1)[0]

export default function T5Lineage({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['lineage-t5', filingId], queryFn: () => api.get<View>(`/v1/filings/${filingId}/lineage/t5`) })
  const [row, setRow] = useState<string>('')
  const [col, setCol] = useState<string>('h')
  const [geo, setGeo] = useState<string>('ALL')
  const v = q.data
  if (!v) return null
  if (!v.supported) return v.framework === 'bank_p3esg' ? <div className="text-[12px] text-[var(--color-mute)]">{v.message}</div> : null
  const r = row || v.rows[0]?.id
  const val = (rid: string) => v.cells[geo]?.[rid]?.[col] ?? null
  const fmt = (n: number | null) => n == null ? '—' : col === 'g' ? `${n}y` : money(n, v.currency)
  const sel = 'bg-[var(--color-bg-2)] border border-[var(--color-line-2)] rounded-lg px-2 py-1 text-[12px] text-[var(--color-ink)]'
  return (
    <div className="space-y-3">
      <div className="mono text-[10px] uppercase tracking-widest text-[var(--color-faint)]">Template 5 · trace a printed cell to its exposures</div>
      <div className="flex flex-wrap gap-2 items-center">
        <select aria-label="Column" className={sel} value={col} onChange={e => setCol(e.target.value)}>
          {v.columns.map(c => <option key={c.id} value={c.id}>{c.id} · {short(c.label)}</option>)}
        </select>
        <select aria-label="Geography" className={sel} value={geo} onChange={e => setGeo(e.target.value)}>
          {v.geographies.map(g => <option key={g.code} value={g.code}>{g.label}</option>)}
        </select>
        <span className="mono text-[10px] text-[var(--color-faint)]">sensitive at score ≥ {v.at_risk_level}</span>
      </div>
      <Card className="p-0 overflow-hidden">
        {v.rows.map(x => (
          <div key={x.id} className="border-b border-[var(--color-line)] last:border-0">
            <button onClick={() => setRow(x.id)}
              className={`w-full px-4 py-2 flex items-center gap-3 text-left transition hover:bg-[var(--color-panel)] ${x.id === r ? 'bg-[var(--color-panel)]' : ''}`}>
              <span className="mono text-[10px] text-[var(--color-faint)] w-6">{x.id}</span>
              <span className="flex-1 text-[12.5px] text-[var(--color-ink)] truncate">{x.label}</span>
              <span className="mono text-[12px] tabular-nums text-[var(--color-mute)]">{fmt(val(x.id))}</span>
            </button>
            {x.id === r && <CellTrace filingId={filingId} row={x.id} col={col} geo={geo} />}
          </div>
        ))}
      </Card>
    </div>
  )
}

function CellTrace({ filingId, row, col, geo }: { filingId: string; row: string; col: string; geo: string }) {
  const q = useQuery({ queryKey: ['lineage-t5-cell', filingId, row, col, geo],
    queryFn: () => api.get<Trace>(`/v1/filings/${filingId}/lineage/t5/cell?row=${encodeURIComponent(row)}&column=${col}&geography=${encodeURIComponent(geo)}`) })
  const d = q.data
  if (q.isLoading) return <div className="px-4 py-3 text-[12px] text-[var(--color-faint)]">tracing…</div>
  if (!d) return <div className="px-4 py-3 text-[12px] text-[var(--color-bad)]">could not trace this cell</div>
  if (!d.supported) return <div className="px-4 py-3 text-[12px] text-[var(--color-mute)]">{d.message}</div>
  const avg = d.cell.kind === 'weighted_average'
  const show = (n: number | null) => n == null ? '—' : avg ? `${n}y` : money(n, d.currency)
  return (
    <div className="px-4 py-3 bg-[var(--color-panel)] space-y-2">
      <div className="flex flex-wrap items-center gap-3 text-[11.5px]">
        <span className="text-[var(--color-mute)]">printed <span className="mono text-[var(--color-ink)]">{show(d.cell.printed)}</span></span>
        <span className="text-[var(--color-mute)]">{avg ? 'weighted average of' : 'sum of'} {d.contributors.length} of {d.n_in_row} exposures in the row <span className="mono text-[var(--color-ink)]">{show(d.cell.from_contributors)}</span></span>
        {d.cell.ties
          ? <span className="inline-flex items-center gap-1 text-[var(--color-good)]"><CheckCircle2 size={12} /> ties</span>
          : <span className="inline-flex items-center gap-1 text-[var(--color-bad)]"><AlertTriangle size={12} /> does not tie</span>}
        {d.drift_count > 0 && <span className="inline-flex items-center gap-1 text-[var(--color-warn)]"><AlertTriangle size={12} /> {d.drift_count} hazard score{d.drift_count === 1 ? '' : 's'} since re-scored on a newer model</span>}
      </div>
      <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] flex items-center gap-1"><ArrowDownRight size={12} /> Exposures</div>
      {d.contributors.map(c => (
        <div key={c.asset_id} className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] p-2.5">
          <div className="flex items-center gap-2">
            <div className="flex-1 min-w-0 text-[12.5px] text-[var(--color-ink)] truncate">{c.asset_name}
              <span className="text-[var(--color-faint)]">{c.country ? ` · ${c.country}` : ''}{c.nace_code ? ` · NACE ${c.nace_code}` : ''}{c.ifrs9_stage ? ` · stage ${c.ifrs9_stage}` : ''}</span></div>
            <div className="mono text-[12px] tabular-nums text-[var(--color-mute)]">{avg ? `${c.maturity}y × ${money(c.weight ?? null, d.currency)}` : money(c.amount ?? null, d.currency)}</div>
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {c.hazards.map(h => (
              <span key={h.hazard} className="mono text-[10.5px] rounded-full border border-[var(--color-line-2)] px-2 py-0.5 text-[var(--color-mute)]"
                title={`golden source today: ${h.granular?.risk_score ?? '—'} (${h.granular?.model_version ?? '—'})`}>
                {hazardLabel(h.hazard)} · {h.category} · {h.filed.score ?? '—'}{h.drift ? ' · drift' : ''}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
