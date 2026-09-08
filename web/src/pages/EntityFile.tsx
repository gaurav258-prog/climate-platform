import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft } from 'lucide-react'
import { api } from '../lib/api'
import { Card, PageHeader, StatGrid } from '../components/ui'
import { severityHex } from '../components/SiteMap'
import StageStrip, { type Step } from '../components/StageStrip'
import { horizonLabel, scenarioLabel, statusLabel } from '../lib/hazards'

// The entity file — what a line supervisor opens: identity, submissions, exposure (regional), peer position,
// what the entity lets me see, and my own access trail on it. Every field is computed by the same engine the
// entity's own pages use, under the regulator's basis (or one passed in), so the two sides never disagree.
interface Fw { framework: string; label: string; state: 'filed' | 'in_progress' | 'none'; status: string | null; period_label: string | null }
interface Pos { id: string; label: string; unit: string; direction?: string; value: number | null; flag: string; percentile: number | null
  distribution: { n: number; min?: number; p25?: number; median?: number; p75?: number; max?: number } }
interface FileResp {
  entity: { org_id: string; name: string; type: string; country: string; lei: string | null; legal_name: string | null }
  in_profile: boolean; sector: { label: string; book_noun: string; frameworks: string[]; region_unit: string } | null
  scenario: string; horizon: string
  submissions: { frameworks: Fw[]; filed: number; expected: number } | null
  book: { n_assets: number; value_eur: number; n_regions: number
    top_regions: { key: string; name: string; country: string | null; kind: string; n_sites: number; value_eur: number; max_score: number | null; worst_hazard: string | null }[]
    hazards: { hazard: string; n: number; value_eur: number }[] }
  peer_position: Pos[]; peers_in_sector: number | null; site_access: boolean
  my_recent_accesses: { action: string; at: string; detail: Record<string, unknown> }[]
}
const eur = (v: number | null | undefined) => v == null ? '—' : v >= 1e9 ? `€${(v / 1e9).toFixed(2)}bn` : v >= 1e6 ? `€${(v / 1e6).toFixed(1)}m` : `€${(v / 1e3).toFixed(0)}k`
const fmt = (p: Pos, v: number | null | undefined) => v == null ? '—' : p.unit === 'eur' ? eur(v) : `${v}%`
const FLAG: Record<string, { label: string; color: string }> = {
  act: { label: 'Act', color: 'var(--color-bad)' }, watch: { label: 'Watch', color: 'var(--color-warn)' },
  ok: { label: 'Within expectation', color: 'var(--color-good)' }, na: { label: 'n/a', color: 'var(--color-faint)' } }
const CHIP: Record<Fw['state'], string> = { filed: 'bg-[var(--color-good)]/15 text-[var(--color-good)]', in_progress: 'bg-[var(--color-warn)]/15 text-[var(--color-warn)]', none: 'bg-[var(--color-bg-2)] text-[var(--color-faint)]' }

export default function EntityFile() {
  const { orgId = '' } = useParams()
  const q = useQuery({ queryKey: ['entity-file', orgId], queryFn: () => api.get<FileResp>(`/v1/supervisor/entity/${orgId}/file`) })
  const wf = useQuery({ queryKey: ['supervisor-workflow'], queryFn: () => api.get<{ entities: { org_id: string; steps: Step[]; stage: string; next: { label: string; to: string } }[] }>('/v1/supervisor/population/workflow') })
  const mine = wf.data?.entities.find(e => e.org_id === orgId)
  const d = q.data
  if (q.isLoading) return <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">opening the entity file…</div>
  if (!d) return <div className="h-[60vh] grid place-items-center text-[var(--color-bad)] text-sm">Could not open this entity — it may be outside your supervised population.</div>
  const sub = d.submissions
  return (
    <div className="fadeup space-y-6">
      <Link to="/supervised" className="inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline"><ChevronLeft size={13} /> Supervised population</Link>
      <PageHeader eyebrow={`Entity file · ${d.sector?.label ?? d.entity.type} · ${d.entity.country}`} title={d.entity.name}
        lead={`${d.entity.legal_name ?? ''}${d.entity.lei ? ` · LEI ${d.entity.lei}` : ''} — basis ${scenarioLabel(d.scenario)} · ${horizonLabel(d.horizon)}. Every figure is the entity's own engine result; opening this file is written to the entity's audit trail.`} />
      <Card className="p-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          {mine ? <StageStrip steps={mine.steps} /> : <span className="text-[12px] text-[var(--color-faint)]">assessing this entity's position in the process…</span>}
          {mine && <Link to={mine.next.to} className="text-[12.5px] font-medium text-[var(--color-sky)] hover:underline whitespace-nowrap">Next: {mine.next.label} →</Link>}
        </div>
        <div className="flex gap-4 text-[12px] mt-3">
          <Link to={`/supervised/${orgId}/intake`} className="text-[var(--color-sky)] hover:underline">Intake →</Link>
          <Link to={`/supervised/${orgId}/plausibility`} className="text-[var(--color-sky)] hover:underline">Plausibility band (Tier 1) →</Link>
          <Link to={`/supervised/${orgId}/lens`} className="text-[var(--color-sky)] hover:underline">Independent lens (Tier 2) →</Link>
        </div>
      </Card>
      {!d.in_profile && <Card className="p-4 text-[12.5px] text-[var(--color-warn)]">This entity's sector is outside your supervision profile — exposure is shown, peer benchmarking is not.</Card>}

      <StatGrid cols={4} items={[
        { label: d.sector?.book_noun ?? 'assets', value: d.book.n_assets.toLocaleString(), sub: eur(d.book.value_eur) },
        { label: 'Submissions', value: sub ? `${sub.filed}/${sub.expected}` : '—', sub: 'framework-periods filed' },
        { label: 'Regions with exposure', value: String(d.book.n_regions), sub: d.sector?.region_unit === 'nuts3' ? 'NUTS-3 · hexagons outside EU' : '' },
        { label: 'Site-level access', value: d.site_access ? 'Granted' : 'Not granted', accent: d.site_access ? 'var(--color-good)' : 'var(--color-faint)', sub: d.site_access ? 'individual sites visible' : 'regional aggregates only' },
      ]} />

      {sub && (
        <Card className="p-5">
          <div className="text-[14px] font-semibold mb-2">Submissions</div>
          <div className="flex flex-wrap gap-2">
            {sub.frameworks.map(f => <span key={f.framework} className={`mono text-[10.5px] px-2 py-1 rounded ${CHIP[f.state]}`}
              title={f.status ? `${statusLabel(f.status)}${f.period_label ? ' · ' + f.period_label : ''}` : 'no filing on record'}>{f.label}: {f.state === 'filed' ? 'Filed' : f.state === 'in_progress' ? 'In progress' : 'Not filed'}</span>)}
          </div>
        </Card>
      )}

      {d.peer_position.length > 0 && (
        <Card className="p-5">
          <div className="flex items-baseline justify-between flex-wrap gap-2 mb-1">
            <div className="text-[14px] font-semibold">Peer position</div>
            <div className="mono text-[11px] text-[var(--color-faint)]">among {d.peers_in_sector} supervised {d.sector?.label.toLowerCase()} · thresholds are your profile's expectations</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-[12.5px]">
              <thead><tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                <th className="font-normal py-2 pr-3">Metric</th><th className="font-normal pr-3 text-right">This entity</th><th className="font-normal pr-3 text-right">Peer median</th>
                <th className="font-normal pr-3 text-right">Peer range</th><th className="font-normal pr-3 text-right">Percentile</th><th className="font-normal">Flag</th></tr></thead>
              <tbody>{d.peer_position.map(p => (
                <tr key={p.id} className="border-t border-[var(--color-line)]">
                  <td className="py-2 pr-3 text-[var(--color-ink)]">{p.label}</td>
                  <td className="pr-3 text-right mono">{fmt(p, p.value)}</td>
                  <td className="pr-3 text-right mono text-[var(--color-mute)]">{fmt(p, p.distribution.median)}</td>
                  <td className="pr-3 text-right mono text-[var(--color-faint)]">{p.distribution.n > 1 ? `${fmt(p, p.distribution.min)} – ${fmt(p, p.distribution.max)}` : 'no peers yet'}</td>
                  <td className="pr-3 text-right mono text-[var(--color-mute)]">{p.percentile != null && p.distribution.n > 1 ? `${p.percentile}th` : '—'}</td>
                  <td><span className="mono text-[11px]" style={{ color: FLAG[p.flag].color }}>{FLAG[p.flag].label}</span></td>
                </tr>))}</tbody>
            </table>
          </div>
        </Card>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        <Card className="p-5">
          <div className="text-[14px] font-semibold mb-2">Where the book sits <span className="mono text-[10.5px] text-[var(--color-faint)] font-normal">· top regions</span></div>
          <div className="divide-y divide-[var(--color-line)]">{d.book.top_regions.map(r => (
            <div key={r.key} className="py-1.5 flex items-center justify-between gap-3 text-[12.5px]">
              <span className="min-w-0 truncate text-[var(--color-ink)]">{r.name}{r.country ? <span className="text-[var(--color-faint)]"> · {r.country}</span> : null}{r.kind === 'h3' ? <span className="mono text-[10px] text-[var(--color-faint)]"> grid cell</span> : null}</span>
              <span className="mono text-[11.5px] text-[var(--color-mute)] shrink-0">{r.n_sites} · {eur(r.value_eur)}</span>
              <span className="mono text-[11.5px] shrink-0 w-24 text-right" style={{ color: severityHex(r.max_score) }}>{r.max_score != null ? `${Math.round(r.max_score)}/100 · ${(r.worst_hazard ?? '').replace(/_/g, ' ')}` : 'unscored'}</span>
            </div>))}</div>
        </Card>
        <Card className="p-5">
          <div className="text-[14px] font-semibold mb-2">Headline hazards <span className="mono text-[10.5px] text-[var(--color-faint)] font-normal">· value whose biggest threat is each hazard</span></div>
          <div className="divide-y divide-[var(--color-line)]">{d.book.hazards.map(h => (
            <div key={h.hazard} className="py-1.5 flex items-center justify-between text-[12.5px]">
              <span className="text-[var(--color-ink)]">{h.hazard.replace(/_/g, ' ')}</span>
              <span className="mono text-[11.5px] text-[var(--color-mute)]">{h.n} · {eur(h.value_eur)}</span>
            </div>))}</div>
        </Card>
      </div>

      <Card className="p-5">
        <div className="text-[14px] font-semibold mb-2">My recent access to this entity <span className="mono text-[10.5px] text-[var(--color-faint)] font-normal">· visible to the entity too</span></div>
        <div className="divide-y divide-[var(--color-line)]">{d.my_recent_accesses.map((a, i) => (
          <div key={i} className="py-1.5 flex items-center justify-between mono text-[11px]"><span className="text-[var(--color-mute)]">{a.action}</span><span className="text-[var(--color-faint)]">{a.at.slice(0, 16).replace('T', ' ')}</span></div>))}</div>
      </Card>
    </div>
  )
}
