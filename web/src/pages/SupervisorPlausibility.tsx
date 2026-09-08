import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { api } from '../lib/api'
import { hazardLabel, horizonLabel, scenarioLabel } from '../lib/hazards'
import { Card, PageHeader, StatGrid } from '../components/ui'

// Tier 1: the submitted template judged against what the platform's own hazard layers say about each geography —
// no granular data needed. A cell is plausible when its sensitive share sits inside the spread of that share across
// the geography's regions. The band is location-only and says so. No reference → no verdict, never a guess.
interface Band { p10: number; p25: number; p50: number; p75: number; p90: number; share_sensitive_pct: number; n_cells: number; n_regions: number; hazard_mix: Record<string, number>; built_at: string }
interface Row { key: string; geography: string; sector: string; gross_carrying_amount_eur: number | null; sensitive_physical_eur: number | null; submitted_share_pct: number | null
  band: Band | null; verdict: 'plausible' | 'above_band' | 'below_band' | 'no_reference'; verdict_label: string; reason: string }
interface Resp { entity_org_id: string; period_label: string | null; source_file: string | null; stated_basis: { scenario: string; horizon: string } | null
  scenario: string; horizon: string; basis_note: string; bases_available: { scenario: string; horizon: string }[]
  rows: Row[]; counts: Record<Row['verdict'], number>; n_cells: number; coverage_value_pct: number | null; rule: string }
const eur = (v: number | null | undefined) => v == null ? '—' : v >= 1e9 ? `€${(v / 1e9).toFixed(2)}bn` : v >= 1e6 ? `€${(v / 1e6).toFixed(1)}m` : `€${(v / 1e3).toFixed(0)}k`
const VC: Record<Row['verdict'], string> = { plausible: 'var(--color-good)', above_band: 'var(--color-warn)', below_band: 'var(--color-warn)', no_reference: 'var(--color-faint)' }

function BandBar({ r }: { r: Row }) {
  if (!r.band) return <span className="mono text-[10.5px] text-[var(--color-faint)]">no reference</span>
  const b = r.band; const x = (v: number) => `${Math.max(0, Math.min(100, v))}%`
  return (
    <div className="relative h-4 w-40 rounded bg-[var(--color-bg-2)]" title={`regional spread p10 ${b.p10}% · median ${b.p50}% · p90 ${b.p90}% · ${b.n_regions} regions · ${b.n_cells.toLocaleString()} scored cells`}>
      <div className="absolute top-0 h-full rounded bg-[var(--color-sky)]/12" style={{ left: x(b.p10), width: `${Math.max(1, b.p90 - b.p10)}%` }} />
      <div className="absolute top-0 h-full rounded bg-[var(--color-sky)]/35" style={{ left: x(b.p25), width: `${Math.max(1, b.p75 - b.p25)}%` }} />
      <div className="absolute top-0 h-full w-px bg-[var(--color-sky)]" style={{ left: x(b.p50) }} />
      {r.submitted_share_pct != null && <div className="absolute top-[2px] h-3 w-[3px] rounded-sm" style={{ left: x(r.submitted_share_pct), background: VC[r.verdict] }} />}
    </div>
  )
}

export default function SupervisorPlausibility() {
  const { orgId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const sc = params.get('scenario') ?? ''; const hz = params.get('horizon') ?? ''
  const q = useQuery({ queryKey: ['sup-plausibility', orgId, sc, hz], queryFn: () => api.get<Resp>(`/v1/supervisor/entity/${orgId}/plausibility${sc || hz ? `?${new URLSearchParams({ ...(sc ? { scenario: sc } : {}), ...(hz ? { horizon: hz } : {}) })}` : ''}`) })
  const [open, setOpen] = useState<string | null>(null)
  const d = q.data
  const setBasis = (s: string, h: string) => { const p = new URLSearchParams(params); p.set('scenario', s); p.set('horizon', h); setParams(p) }
  return (
    <div className="fadeup space-y-6">
      <Link to={`/supervised/${orgId}`} className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline"><ChevronLeft size={13} /> Entity file</Link>
      <PageHeader eyebrow="Plausibility band · Tier 1 · template only" title={d ? `Submitted template · ${d.period_label ?? ''}` : 'Submitted template'}
        lead={d ? `${d.basis_note} Basis ${scenarioLabel(d.scenario)} · ${horizonLabel(d.horizon)}${d.stated_basis ? ` (entity stated ${scenarioLabel(d.stated_basis.scenario)} · ${horizonLabel(d.stated_basis.horizon)})` : ''}. Each cell's sensitive share is judged against the spread of that share across the geography's regions, from the platform's own hazard layers. A verdict outside the band is a question for the entity, not a finding.` : 'Judging each submitted cell against the geography priors…'} />
      {q.isLoading ? <div className="py-10 text-center text-[var(--color-faint)] text-sm">judging each cell against its geography…</div>
        : !d ? <Card className="p-5 text-[13px] text-[var(--color-mute)]">No submitted template on file for this entity yet. <Link to={`/supervised/${orgId}/intake`} className="text-[var(--color-sky)] hover:underline">Ingest it →</Link></Card> : (<>
        <StatGrid cols={4} items={[
          { label: 'Plausible', value: String(d.counts.plausible), sub: `of ${d.n_cells} cells`, accent: 'var(--color-good)' },
          { label: 'High for the geography', value: String(d.counts.above_band), sub: 'sensitivity above the regional spread', accent: d.counts.above_band ? 'var(--color-warn)' : undefined },
          { label: 'Low for the geography', value: String(d.counts.below_band), sub: 'sensitivity below the regional spread', accent: d.counts.below_band ? 'var(--color-warn)' : undefined },
          { label: 'No reference', value: String(d.counts.no_reference), sub: d.coverage_value_pct != null ? `${d.coverage_value_pct}% of gross amount judged` : 'not enough scored land' },
        ]} />
        <Card className="p-5">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="text-[12px] text-[var(--color-mute)]">Basis</span>
            {d.bases_available.map(b => <button key={b.scenario + b.horizon} onClick={() => setBasis(b.scenario, b.horizon)} className={`mono text-[10.5px] px-2 py-1 rounded border ${b.scenario === d.scenario && b.horizon === d.horizon ? 'border-[var(--color-sky)] text-[var(--color-sky)]' : 'border-[var(--color-line)] text-[var(--color-mute)]'}`}>{scenarioLabel(b.scenario)} · {horizonLabel(b.horizon)}</button>)}
            <span className="mono text-[10.5px] text-[var(--color-faint)] ml-auto">band = p25–p75 of the regional share (faint: p10–p90) · marker = submitted share · line = median</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                <th className="font-normal py-2 pr-3">Cell</th><th className="font-normal pr-3 text-right">Gross</th><th className="font-normal pr-3 text-right">Submitted share</th>
                <th className="font-normal pr-3">Regional spread</th><th className="font-normal pr-3">Verdict</th><th className="font-normal">Why</th></tr></thead>
              <tbody>{d.rows.map(r => (<>
                <tr key={r.key} onClick={() => setOpen(open === r.key ? null : r.key)} className={`border-t border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-bg-2)] ${open === r.key ? 'bg-[var(--color-bg-2)]' : ''}`}>
                  <td className="py-1.5 pr-3 text-[var(--color-ink)] whitespace-nowrap"><ChevronRight size={12} className={`inline mr-1 text-[var(--color-faint)] transition-transform ${open === r.key ? 'rotate-90' : ''}`} />{r.geography} · {r.sector}</td>
                  <td className="pr-3 text-right mono text-[var(--color-mute)]">{eur(r.gross_carrying_amount_eur)}</td>
                  <td className="pr-3 text-right mono" style={{ color: VC[r.verdict] }}>{r.submitted_share_pct != null ? `${r.submitted_share_pct}%` : '—'}</td>
                  <td className="pr-3"><BandBar r={r} /></td>
                  <td className="pr-3"><span className="mono text-[10px] uppercase px-1.5 py-0.5 rounded" style={{ color: VC[r.verdict], background: `color-mix(in oklab, ${VC[r.verdict]} 15%, transparent)` }}>{r.verdict_label}</span></td>
                  <td className="text-[11.5px] text-[var(--color-mute)]">{r.reason}{(r.verdict === 'above_band' || r.verdict === 'below_band') && <> <Link onClick={e => e.stopPropagation()} to={`/supervisor/requests?new=1&entity=${orgId}&kind=information_request&geography=${encodeURIComponent(r.geography)}&sector=${encodeURIComponent(r.sector)}&title=${encodeURIComponent(`${r.geography} · ${r.sector}: ${r.verdict_label} — ${r.reason}`)}`} className="text-[var(--color-sky)] hover:underline whitespace-nowrap">raise with the entity →</Link></>}</td>
                </tr>
                {open === r.key && (
                  <tr key={r.key + '-d'}><td colSpan={6} className="p-0"><div className="px-6 py-3 bg-[var(--color-bg-2)] text-[12px] text-[var(--color-mute)] grid md:grid-cols-2 gap-4">
                    <div>
                      <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">As submitted by the entity</div>
                      Gross carrying amount <b className="text-[var(--color-ink)]">{eur(r.gross_carrying_amount_eur)}</b> · of which sensitive <b className="text-[var(--color-ink)]">{eur(r.sensitive_physical_eur)}</b>{r.submitted_share_pct != null ? ` · ${r.submitted_share_pct}%` : ''}
                      <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1">{d.period_label} · {d.source_file ?? 'submitted template'}</div>
                    </div>
                    <div>
                      <div className="mono text-[10px] uppercase tracking-wide text-[var(--color-faint)] mb-1">What the geography's own hazard layers say · {scenarioLabel(d.scenario)} · {horizonLabel(d.horizon)}</div>
                      {r.band ? (<>
                        {r.band.share_sensitive_pct}% of {r.band.n_cells.toLocaleString()} scored land cells in {r.geography} sit in High/Very high; across its {r.band.n_regions} regions that share runs from {r.band.p10}% (p10) through {r.band.p25}%–{r.band.p75}% (the band) around a median of {r.band.p50}% to {r.band.p90}% (p90).
                        {Object.keys(r.band.hazard_mix).length > 0 && <div className="mt-1">Behind the sensitive cells: {Object.entries(r.band.hazard_mix).map(([h, n]) => `${hazardLabel(h)} ${n.toLocaleString()}`).join(' · ')}</div>}
                        <div className="mono text-[10.5px] text-[var(--color-faint)] mt-1">priors built {r.band.built_at.slice(0, 10)} · location-only: the sector does not move the band</div>
                      </>) : 'Not enough scored land in this geography to form a band — no verdict is given.'}
                    </div>
                  </div></td></tr>)}
              </>))}</tbody>
            </table>
          </div>
          <div className="mt-3 text-[11.5px] text-[var(--color-faint)]">{d.rule}</div>
        </Card>
      </>)}
    </div>
  )
}
