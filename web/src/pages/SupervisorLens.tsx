import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft } from 'lucide-react'
import { api } from '../lib/api'
import { horizonLabel, scenarioLabel } from '../lib/hazards'
import { Card, PageHeader, StatGrid } from '../components/ui'

// The independent lens: the submitted template beside the same template rebuilt from the shadow book, cell by
// cell, with every gap split into scope / basis / scoring / unmatched (they add up exactly). A flag is a question.
interface Cell { key: string; geography: string; sector: string; submitted_gross: number | null; submitted_sensitive: number | null
  rebuilt_gross: number | null; rebuilt_sensitive: number | null; submitted_share_pct: number | null; rebuilt_share_pct: number | null
  coverage_pct: number | null; gap: { scope: number; coverage: number; basis: number; scoring: number; unmatched: number }; flag: string; reason: string }
interface Lens { status: string; message?: string; tier: number | null; precision: string; period_label: string; n_cells: number; n_flagged: number
  totals: { submitted: number; rebuilt: number; scope: number; coverage: number; basis: number; scoring: number; unmatched: number }; total_gap: number
  regulator_basis: { scenario: string; horizon: string }; bank_basis: { scenario: string; horizon: string; stated: boolean; method_note: string | null; separable: boolean; note: string | null }
  shadow_book: { n_rows: number; n_located: number; n_scored: number; location_precision: Record<string, number> }; cells: Cell[] }
const eur = (v: number | null | undefined) => v == null ? '—' : `${v < 0 ? '−' : ''}€${Math.abs(v) >= 1e9 ? (Math.abs(v) / 1e9).toFixed(2) + 'bn' : Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toFixed(1) + 'm' : (Math.abs(v) / 1e3).toFixed(0) + 'k'}`
const PART: Record<string, { label: string; color: string }> = {
  scope: { label: 'scope', color: '#7F77DD' }, coverage: { label: 'unlocated (unverifiable)', color: '#B4B2A9' }, basis: { label: 'basis', color: '#1D9E75' }, scoring: { label: 'scoring', color: '#D85A30' }, unmatched: { label: 'unmatched', color: '#888780' } }

function GapBar({ gap }: { gap: Cell['gap'] }) {
  const parts = Object.entries(gap).filter(([, v]) => v !== 0)
  const tot = parts.reduce((a, [, v]) => a + Math.abs(v), 0)
  if (!tot) return <span className="mono text-[11px] text-[var(--color-faint)]">no gap</span>
  return (
    <div className="flex h-2.5 w-full rounded overflow-hidden bg-[var(--color-bg-2)]" title={parts.map(([k, v]) => `${PART[k].label} ${eur(v)}`).join(' · ')}>
      {parts.map(([k, v]) => <div key={k} style={{ width: `${100 * Math.abs(v) / tot}%`, background: PART[k].color }} />)}
    </div>)
}

export default function SupervisorLens() {
  const { orgId = '' } = useParams()
  const q = useQuery({ queryKey: ['sup-lens', orgId], queryFn: () => api.get<Lens>(`/v1/supervisor/entity/${orgId}/lens`) })
  const d = q.data
  if (q.isLoading) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">rebuilding the template independently…</div>
  if (!d) return <div className="h-[60vh] grid place-items-center text-[var(--color-bad)] text-sm">Could not open the lens.</div>
  if (d.status === 'no_submission') return (
    <div className="fadeup space-y-4"><Link to={`/supervised/${orgId}`} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline"><ChevronLeft size={13} /> Entity file</Link>
      <Card className="p-6 text-[13px] text-[var(--color-mute)]">{d.message} <Link to={`/supervised/${orgId}/intake`} className="text-[var(--color-sky)] hover:underline">Go to intake →</Link></Card></div>)
  const t = d.totals
  return (
    <div className="fadeup space-y-6">
      <Link to={`/supervised/${orgId}`} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline"><ChevronLeft size={13} /> Entity file</Link>
      <PageHeader eyebrow={`Independent lens · Tier ${d.tier} · ${d.precision}`} title={`Submitted vs rebuilt · ${d.period_label}`}
        lead={`Your basis ${scenarioLabel(d.regulator_basis.scenario)} · ${horizonLabel(d.regulator_basis.horizon)}${d.bank_basis.stated ? `; the entity states ${scenarioLabel(d.bank_basis.scenario)} · ${horizonLabel(d.bank_basis.horizon)}` : '; the entity stated no basis'}. Rebuilt from ${d.shadow_book.n_rows.toLocaleString()} granular rows, ${d.shadow_book.n_located.toLocaleString()} region-located, ${d.shadow_book.n_scored.toLocaleString()} scored. A flag is a question, not a finding.`} />
      {d.status === 'no_shadow_book' && <Card className="p-4 text-[12.5px] text-[var(--color-warn)]">{d.message}</Card>}
      {d.bank_basis.note && <Card className="p-4 text-[12.5px] text-[var(--color-mute)]">Basis: {d.bank_basis.note}.</Card>}
      <StatGrid cols={4} items={[
        { label: 'Sensitive · submitted', value: eur(t.submitted) },
        { label: 'Sensitive · rebuilt', value: eur(t.rebuilt), sub: `gap ${eur(d.total_gap)}` },
        { label: 'Cells flagged', value: `${d.n_flagged} / ${d.n_cells}`, accent: d.n_flagged ? 'var(--color-warn)' : 'var(--color-good)', sub: '≥ 10 pp share difference or unmatched' },
        { label: 'Gap by reason', value: `${Math.round(100 * Math.abs(t.scoring) / Math.max(1, Math.abs(t.scope) + Math.abs(t.coverage) + Math.abs(t.basis) + Math.abs(t.scoring) + Math.abs(t.unmatched)))}% scoring`, sub: `scope ${eur(t.scope)} · unlocated ${eur(t.coverage)} · basis ${eur(t.basis)} · unmatched ${eur(t.unmatched)}` },
      ]} />
      <Card className="p-5">
        <div className="flex items-center gap-4 mb-3 mono text-[10.5px] text-[var(--color-faint)]">
          {Object.entries(PART).map(([k, p]) => <span key={k} className="inline-flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm inline-block" style={{ background: p.color }} />{p.label}</span>)}
          <span>· share = sensitive ÷ gross · coverage = rows with a resolved region</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
              <th className="font-normal py-2 pr-3">Cell</th><th className="font-normal pr-3 text-right">Submitted gross</th><th className="font-normal pr-3 text-right">Submitted share</th>
              <th className="font-normal pr-3 text-right">Rebuilt gross</th><th className="font-normal pr-3 text-right">Rebuilt share</th><th className="font-normal pr-3 text-right">Coverage</th>
              <th className="font-normal pr-3 w-40">Gap split</th><th className="font-normal">Question</th></tr></thead>
            <tbody>{d.cells.map(c => (
              <tr key={c.key} className="border-t border-[var(--color-line)]">
                <td className="py-1.5 pr-3 text-[var(--color-ink)] whitespace-nowrap">{c.geography} · {c.sector}</td>
                <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(c.submitted_gross)}</td>
                <td className="pr-3 text-right mono text-[var(--color-mute)]">{c.submitted_share_pct != null ? `${c.submitted_share_pct}%` : '—'}</td>
                <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(c.rebuilt_gross)}</td>
                <td className="pr-3 text-right mono" style={{ color: c.flag === 'question' ? 'var(--color-warn)' : 'var(--color-mute)' }}>{c.rebuilt_share_pct != null ? `${c.rebuilt_share_pct}%` : '—'}</td>
                <td className="pr-3 text-right mono text-[var(--color-faint)]">{c.coverage_pct != null ? `${c.coverage_pct}%` : '—'}</td>
                <td className="pr-3"><GapBar gap={c.gap} /></td>
                <td className="text-[11.5px] text-[var(--color-mute)]">{c.flag === 'question' ? c.reason : ''}</td>
              </tr>))}</tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
