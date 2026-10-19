import { useQuery } from '@tanstack/react-query'
import { useNavigate, Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell } from 'recharts'
import { Satellite, AlertTriangle, Percent, FileCheck2, Shuffle, ArrowRight } from 'lucide-react'
import { api } from '../lib/api'
import { Card, StatusPill, PageHeader, HeroBanner, SectionHead } from '../components/ui'
import { HEADING, InfoButton } from '../components/Details'
import { StatusChip } from '../components/StatusChip'
import Lineage from '../components/Lineage'
import RealizedExposure from '../components/RealizedExposure'
import ReportTabs from '../components/ReportTabs'
import { flow, flowValue, displaySymbol } from '../lib/money'

interface Disc {
  rollup: { volume_at_risk_eur: number; pct_cogs_at_risk: number; ingredient_spend_eur: number; total_cogs_eur: number }
  csrd: { commodity: string; volume_at_risk_eur: number | null; status: string; calibration: string | null; avg_hazard: number | null; spend_eur: number }[]
  eudr: { summary: { covered_plots: number; readings: Tally }; plots: EudrPlot[] }
  commodity_ids: Record<string, string>
}
interface Tally { plots: number; unread: number; no_loss_detected: number; loss_after_cutoff: number; not_assessable: number }
interface Reading { outcome: string; loss_ha: number | null; first_loss_year: number | null; reason: string | null; assessed_at: string }
interface EudrPlot {
  plot_id: string; plot: string; commodity: string; country: string | null; eudr_covered: boolean
  eudr_declared: string | null; reading: Reading | null
}

interface Resourcing {
  available: boolean; reallocation_cap_pct: number; total_current_cogs_at_risk_eur: number
  total_avoidable_eur: number; avoidable_pct_of_current: number; n_opportunities: number
  opportunities: { commodity: string; avoidable_eur: number; avoidable_pct: number; shift_spend_eur: number
    from_origin: string; from_yield_shock_pct: number; to_origin: string; to_yield_shock_pct: number }[]
  single_origin_commodities: { commodity: string; origin: string }[]
}


export default function Disclosure() {
  const nav = useNavigate()
  const disc = useQuery({ queryKey: ['disclosure'], queryFn: () => api.get<Disc>('/v1/supply/disclosure') })
  const rs = useQuery({ queryKey: ['resourcing'], queryFn: () => api.get<Resourcing>('/v1/supply/resourcing') })

  if (disc.isLoading) return <Center>loading disclosure…</Center>
  if (disc.error || !disc.data) return <Center>We couldn't load this data. Please retry, or contact support if it persists.</Center>
  const d = disc.data
  const t = d.eudr.summary.readings
  const covered = d.eudr.plots.filter(p => p.eudr_covered)
  const chart = d.csrd.filter(c => (c.volume_at_risk_eur ?? 0) > 0).map(c => ({ name: c.commodity, v: flowValue(c.volume_at_risk_eur ?? 0) / 1e6 }))  // annual COGS-at-risk: a flow, average rate

  return (
    <div className="fadeup space-y-7">
      <ReportTabs />
      <PageHeader eyebrow="Agriculture · Disclosure"
        title="Supply disclosure"
        lead="Volume at risk, and each plot's satellite reading."
        about={[
          { heading: HEADING.shows, body: 'The physical volume at risk in your sourcing book, by commodity, and what the forest dataset shows inside each plot covered by the EU Deforestation Regulation.' },
          { heading: HEADING.read, body: 'A satellite reading is a risk your assessment weighs, never a verdict. Statements are prepared per shipment on the EUDR page.' },
        ]} />

      {/* stat row — lead with the answer */}
      <HeroBanner
        eyebrow="Supply disclosure"
        title={t.plots === 0 ? 'No EUDR plots in this book.'
          : t.unread === 0 ? `All ${t.plots} EUDR plots have a current satellite reading.`
          : `${t.plots - t.unread} of ${t.plots} EUDR plots have a current satellite reading.`}
        lead="Volume at risk from your sourcing book, and what the forest dataset shows inside each plot."
        stat={[
          { label: 'Volume at risk (physical)', value: flow(d.rollup.volume_at_risk_eur), icon: AlertTriangle, tone: '#E8853C' },
          { label: 'of COGS', value: `${(d.rollup.pct_cogs_at_risk ?? 0).toFixed(2)}%`, icon: Percent, tone: 'var(--color-sky)' },
          { label: 'EUDR plots', value: t.plots, icon: Satellite, tone: 'var(--color-sky)' },
          { label: 'Loss after 2020 read', value: t.loss_after_cutoff, icon: AlertTriangle, tone: '#E8853C' },
        ]} />

      {/* realized exposure — the real yield shocks that have ALREADY hit this buyer's origins (observed hook) */}
      <RealizedExposure />

      {/* re-sourcing / origin substitution — cut COGS-at-risk by shifting to a lower-risk origin you already source */}
      <ResourcingCard rs={rs.data} />

      {/* chart + eudr run */}
      <div className="grid lg:grid-cols-[1.3fr_1fr] gap-4">
        <Card className="p-5">
          <SectionHead hint={`${displaySymbol().trim()}m, physical`} className="mb-3">Volume-at-risk by commodity</SectionHead>
          <div className="h-[240px]">
            {chart.length === 0 ? <Empty>No figures published yet — the commodities are still being validated.</Empty> :
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chart} margin={{ left: -18, right: 8, top: 6 }}>
                  <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={{ stroke: '#1e2a40' }} tickLine={false} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <Tooltip cursor={{ fill: '#16223a55' }} contentStyle={{ background: '#111a2c', border: '1px solid #1e2a40', borderRadius: 10, fontSize: 12 }}
                    formatter={(v) => [`${displaySymbol()}${Number(v).toFixed(2)}m`, 'at risk']} />
                  <Bar dataKey="v" radius={[5, 5, 0, 0]} className="cursor-pointer"
                    onClick={(bar) => { const name = (bar as { name?: string; payload?: { name?: string } }).name ?? (bar as { payload?: { name?: string } }).payload?.name; const cid = name ? d.commodity_ids?.[name] : undefined; if (cid) nav(`/detail/commodity/${cid}`) }}>
                    {chart.map((_, i) => <Cell key={i} fill="#38bdf8" />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>}
          </div>
        </Card>

        <Card className="p-5 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <SectionHead icon={Satellite}>EUDR plot readings</SectionHead>
            <InfoButton compact details={{ title: 'EUDR plot readings', sections: [
              { heading: HEADING.shows, body: 'What the forest dataset shows inside each plot after the cut-off date of 31 December 2020.' },
              { heading: HEADING.read, body: 'Tree-cover loss is a risk your assessment weighs; the dataset shows neither land use nor tree height.' },
              { heading: 'Legal basis', body: 'Regulation (EU) 2023/1115: Article 2(13) (the cut-off date) and Article 10 (risk assessment).' }] }} />
          </div>
          
          <div className="grid grid-cols-2 gap-2 mb-4">
            <Mini n={t.no_loss_detected} label="no loss read" tone="good" />
            <Mini n={t.loss_after_cutoff} label="loss after 2020" tone="warn" />
            <Mini n={t.not_assessable} label="not assessable" tone="slate" />
            <Mini n={t.unread} label="not read" tone="slate" />
          </div>
          <Link to="/eudr" className="mt-auto inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium btn-accent bg-[var(--color-sky)] text-[var(--color-on-accent)] hover:bg-[var(--color-blue)]">
            <FileCheck2 size={15} /> Read plots &amp; prepare statements
          </Link>
        </Card>
      </div>

      {/* per-plot: declared vs computed */}
      <Card className="p-5">
        <SectionHead className="mb-3">Per plot — declared vs. the satellite reading</SectionHead>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-[var(--color-faint)] mono text-[10px] uppercase tracking-wide text-left">
                <th className="font-normal py-2 pr-3">Plot</th><th className="font-normal pr-3">Commodity</th>
                <th className="font-normal pr-3">Country</th><th className="font-normal pr-3">Declared</th>
                <th className="font-normal pr-3">Reading</th><th className="font-normal">What was read</th>
              </tr>
            </thead>
            <tbody>
              {covered.map(p => (
                <tr key={p.plot_id} className="border-t border-[var(--color-line)]">
                  <td className="py-2.5 pr-3"><Link to={`/detail/plot/${p.plot_id}`} className="text-[var(--color-ink)] hover:text-[var(--color-sky)] hover:underline">{p.plot}</Link></td>
                  <td className="pr-3 text-[var(--color-mute)]">{p.commodity}</td>
                  <td className="pr-3 mono text-[12px] text-[var(--color-mute)]">{p.country ?? '—'}</td>
                  <td className="pr-3"><StatusChip tone={p.eudr_declared === 'compliant' ? 'good' : 'neutral'} label={DECLARED[p.eudr_declared ?? ''] ?? 'Not declared'} /></td>
                  <td className="pr-3"><StatusPill status={p.reading?.outcome ?? 'unread'} /></td>
                  <td className="text-[12px] text-[var(--color-mute)]"><span className="inline-flex items-center gap-1">{readingNote(p.reading)}
                    {p.reading?.outcome === 'not_assessable' && p.reading.reason && <InfoButton compact details={{ title: 'Why it could not be read', sections: [{ heading: HEADING.limits, body: p.reading.reason }] }} />}</span></td>
                </tr>
              ))}
              {covered.length === 0 && <tr><td colSpan={6} className="py-6 text-center text-[var(--color-faint)]">No EUDR-covered plots in this book.</td></tr>}
            </tbody>
          </table>
        </div>
      </Card>

      {/* lineage */}
      <Lineage />
    </div>
  )
}

// what the plot's declaration says (sc_sourcing_plots eudr_status, the customer's own flag)
const DECLARED: Record<string, string> = { compliant: 'Declared compliant', unknown: 'Not declared' }
const day = (s: string) => new Date(s).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })

function readingNote(r: Reading | null): string {
  if (!r) return 'Not read for its current outline'
  if (r.outcome === 'loss_after_cutoff') return `Loss first seen ${r.first_loss_year ?? '—'} · ${r.loss_ha ?? 0} ha · read ${day(r.assessed_at)}`
  if (r.outcome === 'not_assessable') return 'Could not be read'
  return `No loss after 2020 · read ${day(r.assessed_at)}`
}

function Mini({ n, label, tone }: { n: number; label: string; tone: 'good' | 'bad' | 'warn' | 'slate' }) {
  const c = { good: 'var(--color-good)', bad: 'var(--color-bad)', warn: 'var(--color-warn)', slate: 'var(--color-slate)' }[tone]
  return (
    <div className="rounded-lg border border-[var(--color-line)] px-3 py-2">
      <div className="text-lg font-semibold" style={{ color: c }}>{n}</div>
      <div className="text-[10.5px] text-[var(--color-mute)]">{label}</div>
    </div>
  )
}
const Center = ({ children }: { children: React.ReactNode }) => <div className="h-[60vh] grid place-items-center text-[var(--color-faint)] text-sm">{children}</div>
const Empty = ({ children }: { children: React.ReactNode }) => <div className="h-full grid place-items-center text-[var(--color-faint)] text-[12px]">{children}</div>

function ResourcingCard({ rs }: { rs?: Resourcing }) {
  if (!rs || !rs.available || (rs.n_opportunities === 0 && rs.single_origin_commodities.length === 0)) return null
  const max = Math.max(1, ...rs.opportunities.map(o => o.avoidable_eur))
  return (
    <Card className="p-5 space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <SectionHead icon={Shuffle}>Re-sourcing opportunities</SectionHead>
        <InfoButton compact details={{ title: 'Re-sourcing opportunities', sections: [
          { heading: HEADING.shows, body: 'How much of the volume at risk you could avoid by shifting spend to a lower-risk origin you already source from.' },
          { heading: HEADING.read, body: `Each commodity shifts at most ${rs.reallocation_cap_pct}% of its spend from its highest-risk to its lowest-risk existing origin; the avoided volume at risk is the shift times the gap between their yield shocks.` },
          { heading: HEADING.limits, body: 'Only origins you already source from. A single-origin commodity is flagged, never given an alternative we would have to invent.' }] }} />
        {rs.total_avoidable_eur > 0 && <StatusChip tone="good" label={`Up to ${flow(rs.total_avoidable_eur)} avoidable · ${rs.avoidable_pct_of_current}%`} />}
      </div>
      {rs.opportunities.length > 0 ? (
        <div className="divide-y divide-[var(--color-line)] border-t border-[var(--color-line)]">
          {rs.opportunities.map(o => (
            <div key={o.commodity} className="grid grid-cols-1 md:grid-cols-[7rem_1fr_9rem] items-center gap-x-4 gap-y-1 py-2 text-[12.5px]">
              <span className="font-medium text-[var(--color-ink)]">{o.commodity}</span>
              <span className="flex flex-wrap items-center gap-1.5 text-[var(--color-mute)]">
                <StatusChip tone="bad" label={`${o.from_origin} · ${o.from_yield_shock_pct}% shock`} />
                <ArrowRight size={13} className="text-[var(--color-faint)]" />
                <StatusChip tone="good" label={`${o.to_origin} · ${o.to_yield_shock_pct}%`} />
                <span className="text-[11.5px] text-[var(--color-faint)]">shift {flow(o.shift_spend_eur)}</span>
              </span>
              <span className="flex items-center gap-2 md:justify-end">
                <span className="h-1.5 rounded-full" style={{ width: `${Math.max(6, (o.avoidable_eur / max) * 64)}px`, background: 'var(--color-good)' }} />
                <span className="tabular-nums text-[var(--color-good)]">{flow(o.avoidable_eur)}</span>
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-[12.5px] text-[var(--color-mute)]">No shift within the origins you already source from.</div>
      )}
      {rs.single_origin_commodities.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-[var(--color-faint)]">
          <span>Single origin</span>
          <InfoButton compact details={{ title: 'Single origin', sections: [{ heading: HEADING.read, body: 'These commodities come from one region only: diversifying them needs a new supplier region.' }] }} />
          {rs.single_origin_commodities.map(c => <StatusChip key={c.commodity} tone="warn" label={`${c.commodity} · ${c.origin}`} />)}
        </div>
      )}
    </Card>
  )
}
