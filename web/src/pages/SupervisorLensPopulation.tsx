import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { Card, PageHeader, StatGrid } from '../components/ui'

// Population view of the independent lens: who sits far from the rebuilt figure. Each row is one entity's
// submitted-vs-rebuilt total; open the row for the cell view. Entities without an ingested submission say so.
interface Row { org_id: string; name: string; type: string; status: 'ok' | 'no_submission' | 'no_shadow_book' | 'out_of_profile'; period_label?: string
  n_cells?: number; n_flagged?: number; totals?: { submitted: number; rebuilt: number; scope: number; coverage: number; basis: number; scoring: number; unmatched: number }
  total_gap?: number; gap_pct?: number | null; precision?: string; basis_separable?: boolean; coverage_pct?: number | null }
interface Resp { scenario: string; horizon: string; entities: Row[]; n_with_lens: number }
const eur = (v: number | null | undefined) => v == null ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v) >= 1e9 ? (Math.abs(v) / 1e9).toFixed(2) + 'bn' : Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toFixed(1) + 'm' : (Math.abs(v) / 1e3).toFixed(0) + 'k'}`
const STATUS: Record<Row['status'], string> = { ok: '', no_submission: 'no submitted template ingested', no_shadow_book: 'no granular data ingested', out_of_profile: 'sector outside your profile' }

export default function SupervisorLensPopulation() {
  const q = useQuery({ queryKey: ['sup-lens-pop'], queryFn: () => api.get<Resp>('/v1/supervisor/lens') })
  const d = q.data
  return (
    <div className="fadeup space-y-6">
      <PageHeader eyebrow="Independent lens" title="Submitted versus rebuilt, across the population"
        lead={`Each entity's filed figure beside the same figure rebuilt independently from your own granular data${d ? ` under ${d.scenario} · ${d.horizon}` : ''}. Sorted by the size of the gap. A flag is a question, never a finding.`} />
      {q.isLoading ? <div className="py-10 text-center text-[var(--color-faint)] text-sm">rebuilding every entity's template…</div> : !d ? <div className="text-[13px] text-[var(--color-bad)]">Could not load the lens.</div> : (<>
        <StatGrid cols={3} items={[
          { label: 'Entities with a lens', value: `${d.n_with_lens} / ${d.entities.length}`, sub: 'submission + granular data ingested' },
          { label: 'Largest gap', value: d.entities[0]?.gap_pct != null ? `${d.entities[0].gap_pct}%` : '—', sub: d.entities[0]?.gap_pct != null ? d.entities[0].name : 'nothing to compare yet' },
          { label: 'Questions raised', value: String(d.entities.reduce((a, e) => a + (e.n_flagged ?? 0), 0)), sub: 'flagged cells across the population' },
        ]} />
        <Card className="p-5">
          <div className="overflow-x-auto"><table className="w-full text-[12.5px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
              <th className="font-normal py-2 pr-3">Entity</th><th className="font-normal pr-3">Period</th><th className="font-normal pr-3 text-right">Submitted</th><th className="font-normal pr-3 text-right">Rebuilt</th>
              <th className="font-normal pr-3 text-right">Gap</th><th className="font-normal pr-3 text-right">Cells flagged</th><th className="font-normal pr-3 text-right">Located</th><th className="font-normal">Precision</th></tr></thead>
            <tbody>{d.entities.map(e => (
              <tr key={e.org_id} className="border-t border-[var(--color-line)]">
                <td className="py-2 pr-3"><Link to={`/supervised/${e.org_id}/lens`} className="text-[var(--color-sky)] hover:underline">{e.name}</Link>{e.status !== 'ok' && <span className="mono text-[10.5px] text-[var(--color-faint)] ml-2">{STATUS[e.status]}</span>}</td>
                <td className="pr-3 mono text-[11px] text-[var(--color-faint)]">{e.period_label ?? '—'}</td>
                <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(e.totals?.submitted)}</td>
                <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(e.totals?.rebuilt)}</td>
                <td className="pr-3 text-right mono" style={{ color: e.gap_pct != null && Math.abs(e.gap_pct) >= 10 ? 'var(--color-warn)' : 'var(--color-mute)' }}>{e.gap_pct != null ? `${e.gap_pct}%` : '—'}</td>
                <td className="pr-3 text-right mono text-[var(--color-mute)]">{e.n_flagged != null ? `${e.n_flagged} / ${e.n_cells}` : '—'}</td>
                <td className="pr-3 text-right mono text-[var(--color-faint)]">{e.coverage_pct != null ? `${e.coverage_pct}%` : '—'}</td>
                <td className="mono text-[10.5px] text-[var(--color-faint)]">{e.precision ?? ''}{e.basis_separable === false ? ' · basis not separable' : ''}</td>
              </tr>))}</tbody></table></div>
        </Card>
      </>)}
    </div>
  )
}
