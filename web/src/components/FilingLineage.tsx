import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Satellite, AlertTriangle, Route, Users } from 'lucide-react'
import { api } from '../lib/api'
import { money, balance } from '../lib/money'
import { Card, Lens, SectionHead } from './ui'
import { hazardLabel, sevColor, frameworkLabel, bucketLabel, modelLabel } from '../lib/hazards'
import { HBar } from './Charts'
import { HEADING, InfoButton, MessageLine, type Message } from './Details'
import { StatusChip } from './StatusChip'
import { Dialog } from './Dialog'
import LineageGraph from './LineageGraph'
import T5Lineage from './T5Lineage'
import { plural } from './intake/parts'

// From a filed figure to its source, inside the filing drawer: pick a hazard's exposure to see the assets it adds up,
// each asset's score as filed and as it stands today, and the feeds the score is computed from; from any asset, every
// other book and filing that uses the same place. Read from the frozen filing — a missing score shows as "—".

interface HazEntry { hazard: string; exposed_value_eur: number | null; n_exposed: number; max_score: number }
interface Source { key: string; name: string; maturity: string | null; status: string | null }
interface Granular { risk_score: number | null; model_version: string | null; data_vintage: string | null; scored_at: string | null; fingerprint: string | null; ci_lower: number | null; ci_upper: number | null }
interface Contributor { asset_id: string; asset_name: string; value_eur: number | null; h3_cell: string; country: string | null; filed: { score: number | null; bucket: string | null; model_version: string | null }; granular: Granular | null; drift: boolean }
interface Lineage { supported: boolean; msg?: Message; hazard: string; cell: { exposed_value_eur: number | null; n_exposed: number; max_score: number }; currency?: string; contributors: Contributor[]; sources: Source[]; drift_count: number }
interface UsedBy { vertical: string; book: string | null; framework: string | null; filing: { filing_id: string; status: string } | null; n: number; value_eur: number }
interface Upstream { h3_cell: string; hazards_scored_here: string[]; used_by: UsedBy[] }

const feedTone = (s: string | null) => s === 'fresh' || s === 'live' ? 'var(--color-good)' : s === 'overdue' || s === 'failed' ? 'var(--color-bad)' : s === 'due_soon' ? 'var(--color-warn)' : 'var(--color-slate)'
const ABOUT = [
  { heading: HEADING.shows, body: 'For each hazard this filing reports, the value exposed at or above your at-risk threshold. Select a hazard to trace it: the assets it adds up, each one’s score as filed and as it stands today, and the data feeds the score is computed from.' },
  { heading: HEADING.read, body: 'Bars are coloured by the highest score among the exposed assets. A score re-computed since on a newer model is flagged, never replaced: the filing keeps what it was frozen with.' },
  { heading: HEADING.sources, body: 'The frozen filing; today’s hazard scores for each asset’s location; the feed registry.' },
]

export default function FilingLineage({ filingId }: { filingId: string }) {
  const q = useQuery({ queryKey: ['lineage-haz', filingId], queryFn: () => api.get<{ hazards: HazEntry[]; currency: string }>(`/v1/filings/${filingId}/lineage/hazards`) })
  const [open, setOpen] = useState<string | null>(null)
  const hazards = q.data?.hazards ?? []
  const ccy = q.data?.currency ?? 'EUR'   // filed cells are in the filing's own currency
  // a filing that froze no hazard cells: a Pillar 3 filing traces its Template 5 cells instead (E105)
  if (!hazards.length) return q.data ? <T5Lineage filingId={filingId} /> : null
  const charted = hazards.filter(h => (h.exposed_value_eur ?? 0) > 0)

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 flex-wrap px-1">
        <SectionHead icon={Route}>From a filed figure to its source</SectionHead>
        <InfoButton compact details={{ title: 'From a filed figure to its source', sections: ABOUT }} />
        <Lens kind="insight" className="ml-auto" />
      </div>
      <Card className="p-4 space-y-3">
        {charted.length > 0
          ? <HBar data={charted.map(h => ({ label: hazardLabel(h.hazard), value: h.exposed_value_eur ?? 0, color: sevColor(h.max_score), sub: plural(h.n_exposed, 'asset') }))}
              format={(n: number) => money(n, ccy)} onBar={i => setOpen(charted[i].hazard)} labelWidth="w-40" />
          : <div className="text-[12.5px] text-[var(--color-faint)]">No value is exposed at or above the threshold.</div>}
        <div className="flex flex-wrap gap-1.5">
          {hazards.filter(h => !(h.exposed_value_eur ?? 0)).map(h => (
            <button key={h.hazard} onClick={() => setOpen(h.hazard)} className="text-[11.5px] rounded-full border border-[var(--color-line-2)] px-2 py-0.5 text-[var(--color-mute)] hover:text-[var(--color-sky)]">
              {hazardLabel(h.hazard)} · none exposed</button>))}
        </div>
      </Card>
      {open && (
        <Dialog title={`${hazardLabel(open)} — from the figure to its source`} onClose={() => setOpen(null)} className="sm:max-w-3xl">
          <HazardTrace filingId={filingId} hazard={open} />
        </Dialog>)}
    </div>
  )
}

function HazardTrace({ filingId, hazard }: { filingId: string; hazard: string }) {
  const q = useQuery({ queryKey: ['lineage', filingId, hazard], queryFn: () => api.get<Lineage>(`/v1/filings/${filingId}/lineage?hazard=${hazard}`) })
  const [graph, setGraph] = useState(false)
  const d = q.data
  if (q.isLoading) return <div className="text-[12.5px] text-[var(--color-faint)]">Tracing…</div>
  if (!d) return <div className="text-[12.5px] text-[var(--color-bad)]">This figure could not be traced.</div>
  if (!d.supported) return d.msg ? <MessageLine m={d.msg} className="text-[12.5px] text-[var(--color-mute)]" /> : null
  const ccy = d.currency ?? 'EUR'
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="display text-[20px] tabular-nums">{money(d.cell.exposed_value_eur, ccy)}</span>
        <span className="text-[12px] text-[var(--color-mute)]">exposed · {plural(d.contributors.length, 'asset')}</span>
        {d.drift_count > 0 && <span className="inline-flex items-center gap-1">
          <StatusChip tone="warn" label={`${plural(d.drift_count, 'asset')} re-scored since`} />
          <InfoButton compact details={{ title: 'Re-scored since it was filed', sections: [
            { heading: HEADING.shows, body: 'These assets have been scored again on a newer model since the filing was frozen.' },
            { heading: HEADING.read, body: 'The filing keeps the scores it was frozen with. Restate it to bring the new scores in.' }] }} /></span>}
        <div className="ml-auto inline-flex rounded-lg border border-[var(--color-line-2)] overflow-hidden text-[11.5px]">
          <button onClick={() => setGraph(false)} aria-pressed={!graph} className={`px-2 py-0.5 ${!graph ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)]'}`}>List</button>
          <button onClick={() => setGraph(true)} aria-pressed={graph} className={`px-2 py-0.5 ${graph ? 'bg-[var(--color-bg-2)] text-[var(--color-ink)]' : 'text-[var(--color-faint)]'}`}>Graph</button>
        </div>
      </div>
      <div className="flex items-center gap-1.5 flex-wrap">
        <Satellite size={13} className="text-[var(--color-sky)]" />
        {d.sources.length === 0 && <span className="text-[11.5px] text-[var(--color-faint)]">No source feed named</span>}
        {d.sources.map(s => (
          <span key={s.key} className="inline-flex items-center gap-1.5 text-[11.5px] rounded-full border border-[var(--color-line-2)] px-2 py-0.5 text-[var(--color-mute)]">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: feedTone(s.status) }} />{s.name}</span>))}
      </div>
      {graph ? <LineageGraph hazardLabel={hazardLabel(d.hazard)} exposed={d.cell.exposed_value_eur} contributors={d.contributors} sources={d.sources} />
        : <div className="space-y-1.5 max-h-[55vh] overflow-y-auto">{d.contributors.map(c => <ContributorRow key={c.asset_id} c={c} ccy={ccy} />)}</div>}
    </div>
  )
}

function ContributorRow({ c, ccy }: { c: Contributor; ccy: string }) {
  const [reuse, setReuse] = useState(false)
  const g = c.granular
  const tech = [
    { heading: 'Model', body: `${modelLabel(g?.model_version)} today; ${modelLabel(c.filed.model_version)} when filed` },
    { heading: 'Data vintage', body: g?.data_vintage ? g.data_vintage.slice(0, 10) : '—' },
    ...(g?.ci_lower != null ? [{ heading: 'Score band', body: `${g.ci_lower} to ${g.ci_upper}` }] : []),
    ...(g?.fingerprint ? [{ heading: 'Score fingerprint', body: g.fingerprint }] : []),
  ]
  return (
    <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-bg-2)] px-3 py-2 flex items-center gap-3 flex-wrap">
      <div className="min-w-0 flex-1">
        <div className="text-[12.5px] text-[var(--color-ink)] truncate">{c.asset_name}{c.country ? <span className="text-[var(--color-faint)]"> · {c.country}</span> : null}</div>
        <div className="flex items-center gap-1.5 mt-0.5 text-[11.5px] text-[var(--color-mute)]">
          <span>Filed {c.filed.score ?? '—'}{c.filed.bucket ? ` (${bucketLabel(c.filed.bucket)})` : ''}</span>
          <span className="text-[var(--color-faint)]">·</span>
          <span style={{ color: c.drift ? 'var(--color-warn)' : undefined }}>today {g?.risk_score ?? '—'}</span>
          <InfoButton compact details={{ title: c.asset_name, sections: tech }} />
        </div>
      </div>
      <button onClick={() => setReuse(true)} className="inline-flex items-center gap-1 text-[11.5px] text-[var(--color-sky)] hover:underline"><Users size={12} /> Who else uses this place</button>
      <div className="tabular-nums text-[12.5px] text-[var(--color-ink)] w-24 text-right">{money(c.value_eur, ccy)}</div>
      {reuse && <Dialog title={`Who else uses ${c.asset_name}’s place`} onClose={() => setReuse(false)} ><ReverseTrace h3={c.h3_cell} /></Dialog>}
    </div>
  )
}

function ReverseTrace({ h3 }: { h3: string }) {
  const q = useQuery({ queryKey: ['upstream', h3], queryFn: () => api.get<Upstream>(`/v1/lineage/cell/${h3}`) })
  const d = q.data
  if (q.isLoading) return <div className="text-[12.5px] text-[var(--color-faint)]">Tracing…</div>
  if (!d) return null
  return (
    <div className="space-y-3 text-[12.5px]">
      <div className="flex flex-wrap gap-1.5">
        {d.hazards_scored_here.map(h => <span key={h} className="rounded-full border border-[var(--color-line-2)] px-2 py-0.5 text-[11.5px] text-[var(--color-mute)]">{hazardLabel(h)}</span>)}
      </div>
      <div className="divide-y divide-[var(--color-line)] border-y border-[var(--color-line)]">
        {d.used_by.map((u, i) => (
          <div key={i} className="py-2 flex items-center gap-2 flex-wrap">
            <span className="text-[var(--color-ink)]">{u.book ?? 'Another book'}</span>
            <span className="text-[var(--color-mute)]">{plural(u.n, 'holding')} · {balance(u.value_eur)}</span>
            {u.filing && <span className="ml-auto inline-flex items-center gap-1.5 text-[11.5px] text-[var(--color-mute)]">{frameworkLabel(u.framework)} <StatusChip value={u.filing.status} /></span>}
          </div>))}
      </div>
      {d.used_by.length === 0 && <div className="text-[var(--color-faint)] inline-flex items-center gap-1.5"><AlertTriangle size={12} /> No holding found at this place.</div>}
    </div>
  )
}
