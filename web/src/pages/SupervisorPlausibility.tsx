import { useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Ruler } from 'lucide-react'
import { api, apiMessage } from '../lib/api'
import { money } from '../lib/money'
import { pressable } from '../lib/pressable'
import { SCENARIO_LABEL, horizonLabel } from '../lib/hazards'
import { Card, PageHeader, SectionHead, StatGrid } from '../components/ui'
import { StatusChip } from '../components/StatusChip'
import { HEADING, InfoButton, MessageLine, messageDetails, type Message } from '../components/Details'
import { BackToEntity, CheckSwitch, QUICK, RaiseLink, TWO_CHECKS, cellName, pct } from './supervisorAnalysis/checks'
import { BandBar, CellDialog, VERDICT, type Row, type Verdict } from './supervisorAnalysis/RangeCell'
import { AcrossYears, type Trend } from './supervisorAnalysis/AcrossYears'

// The quick check (the plausibility band), to the UI standard (2026-10-16): the entity's filed template judged with no
// granular data at all — each cell's share of sensitive exposure against the typical range for its country's regions.
// The main screen is the counts, one range bar per cell and a slope chart across years; the method, the percentiles
// and a cell's reference open one click away, in the server's catalogue words.
interface Resp {
  entity_name: string | null; period_label: string | null; status?: 'gap' | 'no_submission'; message?: Message
  scenario: string; horizon: string; basis_note: Message; bases_available: { scenario: string; horizon: string }[]
  at_risk_level: number; at_risk_level_from: 'submission' | 'entity_method'
  rows: Row[]; counts: Record<Verdict, number>; n_cells: number; coverage_value_pct: number | null; rule: Message
  exposure_measure: { label: string; n_cells_without_measure: number }
}

const ABOUT = [
  { heading: HEADING.shows, body: 'Each cell of the template the entity filed — its share of exposure sensitive to physical risk — against the typical range of that share across its country’s regions, read from the platform’s hazard scores at the same basis and threshold.' },
  { heading: HEADING.read, body: 'A share inside the range is within range. Above or below it is a question for the entity, not a finding: its exposure may sit in the riskiest or the safest regions, or its sensitivity may be overstated or understated.' },
  TWO_CHECKS,
  { heading: HEADING.sources, body: 'The template, as filed. The platform’s hazard scores of the land in each region of the country.' },
  { heading: HEADING.limits, body: 'The range depends on location only: the sector does not move it. A country with too few scored regions gets no range, and its cells are not judged; nothing is estimated in their place.' },
]
const FILTERS: (Verdict | 'all')[] = ['all', 'above_band', 'below_band', 'plausible', 'no_reference']

export default function SupervisorPlausibility() {
  const { orgId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const sc = params.get('scenario') ?? '', hz = params.get('horizon') ?? ''
  const q = useQuery({
    queryKey: ['sup-plausibility', orgId, sc, hz], retry: false,
    queryFn: () => api.get<Resp>(`/v1/supervisor/entity/${orgId}/plausibility${sc || hz ? `?${new URLSearchParams({ ...(sc ? { scenario: sc } : {}), ...(hz ? { horizon: hz } : {}) })}` : ''}`),
  })
  const tr = useQuery({ queryKey: ['sup-trend-entity', orgId], queryFn: () => api.get<Trend>(`/v1/supervisor/entity/${orgId}/trend`) })
  const [filter, setFilter] = useState<Verdict | 'all'>('all')
  const [open, setOpen] = useState<Row | null>(null)
  const d = q.data
  const rows = useMemo(() => (d?.rows ?? []).filter(r => filter === 'all' || r.verdict === filter), [d, filter])
  const setBasis = (s: string, h: string) => { const p = new URLSearchParams(params); p.set('scenario', s); p.set('horizon', h); setParams(p) }
  const header = (
    <PageHeader eyebrow={QUICK} title={d?.entity_name ?? 'Supervised entity'} lead="Each filed cell against the typical range for its country’s regions."
      about={ABOUT} actions={<CheckSwitch orgId={orgId} current="quick" />}>
      {d && !d.status && (
        <div className="flex flex-wrap gap-1.5 mt-3">
          {d.period_label && <StatusChip tone="neutral" label={d.period_label} />}
          <StatusChip tone="neutral" label={`Measured on ${d.exposure_measure.label.toLowerCase()}`} />
          <StatusChip tone="neutral" label={`Entity’s threshold ${d.at_risk_level} · ${d.at_risk_level_from === 'submission' ? 'stated with its template' : 'from its methodology'}`} />
        </div>)}
    </PageHeader>)
  if (q.isLoading) return <Shell orgId={orgId} header={header}><div className="py-10 text-center text-[var(--color-faint)] text-sm">Checking each cell against its region…</div></Shell>
  if (!d) return <Shell orgId={orgId} header={header}><Card className="p-6 text-[13px] text-[var(--color-bad)]">{apiMessage(q.error, 'The quick check could not be opened.')}</Card></Shell>
  if (d.status === 'no_submission') return (
    <Shell orgId={orgId} header={header}>
      <Card className="p-6 flex flex-wrap items-center gap-4 text-[13.5px]">
        {d.message && <MessageLine m={d.message} className="text-[var(--color-ink)]" />}
        <Link to={`/supervised/${orgId}/intake`} className="text-[12.5px] text-[var(--color-sky)] hover:underline">Open Intake</Link>
      </Card>
    </Shell>)
  if (d.status === 'gap') return <Shell orgId={orgId} header={header}><Card className="p-5 text-[13px] text-[var(--color-warn)]">{d.message && <MessageLine m={d.message} />}</Card></Shell>
  const c = d.counts
  const scenarios = [...new Set(d.bases_available.map(b => b.scenario))], horizons = [...new Set(d.bases_available.map(b => b.horizon))]
  const select = 'rounded-lg border border-[var(--color-line-2)] bg-[var(--color-panel)] px-2.5 py-1.5 text-[12.5px] text-[var(--color-ink)]'
  return (
    <Shell orgId={orgId} header={header}>
      <div className="flex flex-wrap items-center gap-3">
        <select value={d.scenario} onChange={e => setBasis(e.target.value, d.horizon)} aria-label="Scenario" className={select}>
          {scenarios.map(s => <option key={s} value={s}>{SCENARIO_LABEL[s] ?? 'Scenario'}</option>)}
        </select>
        <select value={d.horizon} onChange={e => setBasis(d.scenario, e.target.value)} aria-label="Year" className={select}>
          {horizons.map(h => <option key={h} value={h}>{horizonLabel(h)}</option>)}
        </select>
        <span className="text-[12.5px] text-[var(--color-mute)]"><MessageLine m={d.basis_note} /></span>
      </div>
      <StatGrid cols={4} items={[
        { label: VERDICT.above_band.label, value: String(c.above_band), sub: `of ${d.n_cells} cells`, accent: c.above_band ? VERDICT.above_band.color : undefined },
        { label: VERDICT.below_band.label, value: String(c.below_band), sub: `of ${d.n_cells} cells`, accent: c.below_band ? VERDICT.below_band.color : undefined },
        { label: VERDICT.plausible.label, value: String(c.plausible), sub: `of ${d.n_cells} cells`, accent: VERDICT.plausible.color },
        { label: VERDICT.no_reference.label, value: String(c.no_reference), sub: d.coverage_value_pct != null ? `${pct(d.coverage_value_pct)} of the amount judged` : undefined },
      ]} />
      <Card className="p-5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4">
          <SectionHead icon={Ruler}>Each cell against its regional range</SectionHead>
          <InfoButton compact details={{ title: 'Each cell against its regional range', sections: [
            { heading: HEADING.read, body: 'The bar is the range of the share across the country’s regions: the darker part is the typical range, the middle half of the regions (25th to 75th percentile); the lighter part the wider range (10th to 90th); the thin line the middle region (median). The marker is the share the entity filed, coloured by the result. Select a cell for its reference.' },
            ...messageDetails(d.rule).sections,
          ] }} />
          <div className="ml-auto flex flex-wrap gap-1">
            {FILTERS.map(f => (
              <button key={f} type="button" onClick={() => setFilter(f)} aria-pressed={filter === f}
                className={`px-2.5 py-1 text-[11.5px] rounded-full border ${filter === f ? 'border-[var(--color-sky)] text-[var(--color-ink)]' : 'border-[var(--color-line-2)] text-[var(--color-mute)]'}`}>
                {f === 'all' ? `All ${d.n_cells}` : `${VERDICT[f].label} ${c[f]}`}
              </button>))}
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px] tabular-nums">
            <thead><tr className="text-left text-[var(--color-mute)] border-b border-[var(--color-line)]">
              <th className="py-1.5 pr-3 font-medium">Cell</th><th className="pr-3 font-medium text-right">{d.exposure_measure.label}</th>
              <th className="pr-3 font-medium text-right">Filed share</th><th className="pr-3 font-medium">Regional range</th><th className="pr-3 font-medium">Result</th><th />
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.key} {...pressable(() => setOpen(r), { row: true })} className="border-b border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-panel-2)]">
                  <td className="py-1.5 pr-3 text-[var(--color-ink)] max-w-[16rem] truncate" title={cellName(r)}>{cellName(r)}</td>
                  <td className="pr-3 text-right text-[var(--color-mute)]">{money(r.exposure_eur, 'EUR')}</td>
                  <td className="pr-3 text-right" style={{ color: VERDICT[r.verdict].color }}>{pct(r.submitted_share_pct)}</td>
                  <td className="pr-3"><BandBar r={r} /></td>
                  <td className="pr-3"><StatusChip tone={VERDICT[r.verdict].tone} label={r.verdict_label} /></td>
                  <td className="text-right">{(r.verdict === 'above_band' || r.verdict === 'below_band') && <RaiseLink orgId={orgId} cell={r} why={r.reason.label} short />}</td>
                </tr>))}
            </tbody>
          </table>
          {rows.length === 0 && <div className="text-[12.5px] text-[var(--color-faint)] py-6 text-center">No cells with this result.</div>}
        </div>
      </Card>
      {tr.data && tr.data.periods.length > 0 && <AcrossYears t={tr.data} />}
      {open && <CellDialog r={open} orgId={orgId} measure={d.exposure_measure.label} onClose={() => setOpen(null)} />}
    </Shell>
  )
}

function Shell({ orgId, header, children }: { orgId: string; header: React.ReactNode; children: React.ReactNode }) {
  return <div className="fadeup space-y-6"><BackToEntity orgId={orgId} />{header}{children}</div>
}

