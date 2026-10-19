import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronRight, ArrowDown, ArrowUp, Satellite, Sprout, MapPin, Gauge, FileBarChart } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import { flow } from '../lib/money'
import { hazardLabel } from '../lib/hazards'
import { SectionHead, StatusPill } from './ui'
import { HEADING, InfoButton } from './Details'

// From the disclosed figure down to the satellite feed, and from one plot back up: volume at risk → each commodity →
// its sourcing plots → the plot's hazard score → the feeds that score is computed from (the feed registry, read through
// the data dictionary) and, for an EUDR plot, its satellite reading. Every figure and name is read from data.

interface Commodity { commodity: string; volume_at_risk_eur: number | null; top_hazard: string | null; yield_shock_pct: number | null }
interface Summary { rollup: { volume_at_risk_eur: number }; commodities: Commodity[] }
interface Plot { plot_id: string; commodity: string; plot_name: string; country: string | null; spend_eur: number; top_hazard: string | null; hazard_score: number | null; reading: { outcome: string } | null }
interface Portfolio { plots: Plot[] }
interface Feed { name: string; maturity: string | null; status: string | null }
interface Dictionary { fields: { field: string; source_feeds: Feed[] }[] }

const ABOUT = [
  { heading: HEADING.shows, body: 'How the volume at risk you disclose is built: each commodity’s share, the sourcing plots behind it with what you spend there, each plot’s hazard score, and the data feeds that score is computed from.' },
  { heading: HEADING.read, body: 'From the report down: open a commodity, then a plot, to reach its feeds. From a plot up: pick one plot and follow its data step by step to the disclosed figure.' },
  { heading: HEADING.sources, body: 'Your sourcing book and spend; the hazard scores for each plot’s location; the feed registry for which feeds each hazard is computed from; for EUDR plots, the satellite reading of tree cover since the end of 2020.' },
  { heading: HEADING.limits, body: 'Volume at risk is each commodity’s yield shock applied to what you spend on it, with no price forecast in it. A commodity whose figure is held back shows no volume here.' },
]
const feedTone = (f: Feed) => f.status === 'overdue' || f.status === 'failed' ? 'var(--color-bad)' : f.status === 'due_soon' ? 'var(--color-warn)'
  : f.status === 'fresh' || f.maturity === 'live' ? 'var(--color-good)' : 'var(--color-slate)'

export default function Lineage() {
  const [dir, setDir] = useState<'down' | 'up'>('down')
  const [plotId, setPlotId] = useState<string>('')
  const sumQ = useQuery({ queryKey: ['summary'], queryFn: () => api.get<Summary>('/v1/supply/summary') })
  const pfQ = useQuery({ queryKey: ['portfolio'], queryFn: () => api.get<Portfolio>('/v1/supply/portfolio') })
  const ddQ = useQuery({ queryKey: ['data-dictionary'], queryFn: () => api.get<Dictionary>('/v1/meta/data-dictionary') })
  // the feeds each hazard is computed from (null while the dictionary loads: "loading", never "none")
  const feeds = useMemo(() => ddQ.data ? Object.fromEntries(ddQ.data.fields.map(f => [f.field, f.source_feeds])) as Record<string, Feed[]> : null, [ddQ.data])
  const plots = pfQ.data?.plots ?? []
  const sum = sumQ.data
  const selected = plots.find(p => p.plot_id === plotId) ?? plots[0]

  const tab = (d: 'down' | 'up', Icon: typeof ArrowDown, label: string) => (
    <button onClick={() => setDir(d)} aria-pressed={dir === d}
      className={clsx('flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[12px] transition', dir === d ? 'bg-[var(--color-panel-2)] text-[var(--color-ink)]' : 'text-[var(--color-mute)]')}>
      <Icon size={13} /> {label}</button>)

  return (
    <div className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-bg-2)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-2">
          <SectionHead icon={Satellite}>From the figure to the feed</SectionHead>
          <InfoButton compact details={{ title: 'From the figure to the feed', sections: ABOUT }} />
        </div>
        <div className="flex gap-1 card p-1">{tab('down', ArrowDown, 'From the report')}{tab('up', ArrowUp, 'From a plot')}</div>
      </div>

      {(sumQ.isLoading || pfQ.isLoading) ? <div className="py-10 text-center text-[var(--color-faint)] text-sm">Loading…</div>
        : !sum ? null
        : dir === 'down' ? <TopDown sum={sum} plots={plots} feeds={feeds} />
        : selected ? (
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-[12px] text-[var(--color-mute)]">Plot
              <select value={selected.plot_id} onChange={e => setPlotId(e.target.value)}
                className="bg-[var(--color-panel)] border border-[var(--color-line)] rounded-lg px-3 py-1.5 text-[13px] text-[var(--color-ink)] outline-none focus:border-[var(--color-sky)]">
                {plots.map(p => <option key={p.plot_id} value={p.plot_id}>{p.plot_name}</option>)}
              </select></label>
            <Chain plot={selected} sum={sum} feeds={feeds ? feeds[selected.top_hazard ?? ''] ?? [] : null} />
          </div>)
        : <div className="text-[12.5px] text-[var(--color-faint)]">No sourcing plots yet.</div>}
    </div>
  )
}

function Share({ share, tone }: { share: number; tone: string }) {
  return (
    <span className="hidden sm:block w-24 h-1.5 rounded-full bg-[var(--color-line)] overflow-hidden shrink-0" role="img" aria-label={`${Math.round(share * 100)}%`}>
      <span className="block h-full rounded-full" style={{ width: `${Math.max(2, share * 100)}%`, background: tone }} />
    </span>)
}

function TopDown({ sum, plots, feeds }: { sum: Summary; plots: Plot[]; feeds: Record<string, Feed[]> | null }) {
  const [open, setOpen] = useState<string | null>(null)
  const [plotOpen, setPlotOpen] = useState<string | null>(null)
  const total = sum.rollup.volume_at_risk_eur
  const rows = sum.commodities.filter(c => (c.volume_at_risk_eur ?? 0) > 0).sort((a, b) => (b.volume_at_risk_eur ?? 0) - (a.volume_at_risk_eur ?? 0))
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] px-3 py-2.5">
        <FileBarChart size={15} className="text-[var(--color-sky)]" />
        <span className="text-[13px] text-[var(--color-ink)]">Volume at risk</span>
        <span className="ml-auto display text-[18px] tabular-nums text-[var(--color-ink)]">{flow(total)}</span>
      </div>
      {rows.length === 0 && <div className="ml-3 pl-3 py-1.5 text-[12.5px] text-[var(--color-faint)]">No commodity has a published volume at risk yet.</div>}
      <div className="ml-3 border-l border-[var(--color-line)] pl-3 space-y-1">
        {rows.map(c => {
          const cv = c.volume_at_risk_eur ?? 0
          const cplots = plots.filter(p => p.commodity === c.commodity)
          const spend = cplots.reduce((a, p) => a + (p.spend_eur ?? 0), 0)
          const isOpen = open === c.commodity
          return (
            <div key={c.commodity}>
              <button onClick={() => setOpen(isOpen ? null : c.commodity)} aria-expanded={isOpen}
                className="w-full flex items-center gap-2 text-left py-1.5 px-2 rounded-lg hover:bg-[var(--color-panel-2)] transition">
                <ChevronRight size={13} className="text-[var(--color-faint)] transition-transform shrink-0" style={{ transform: isOpen ? 'rotate(90deg)' : 'none' }} />
                <Sprout size={13} className="text-[var(--color-warn)] shrink-0" />
                <span className="text-[13px] text-[var(--color-ink)] truncate">{c.commodity}</span>
                {c.top_hazard && <span className="text-[11.5px] text-[var(--color-faint)] truncate hidden md:inline">{hazardLabel(c.top_hazard)}</span>}
                <span className="ml-auto flex items-center gap-3 shrink-0">
                  <Share share={total ? cv / total : 0} tone="var(--color-warn)" />
                  <span className="tabular-nums text-[12.5px] text-[var(--color-ink)] w-20 text-right">{flow(cv)}</span>
                </span>
              </button>
              {isOpen && (
                <div className="ml-5 border-l border-[var(--color-line)] pl-3 space-y-0.5">
                  {cplots.map(p => {
                    const pOpen = plotOpen === p.plot_id
                    return (
                      <div key={p.plot_id}>
                        <button onClick={() => setPlotOpen(pOpen ? null : p.plot_id)} aria-expanded={pOpen}
                          className="w-full flex items-center gap-2 text-left py-1.5 px-2 rounded-lg hover:bg-[var(--color-panel-2)] transition">
                          <ChevronRight size={12} className="text-[var(--color-faint)] transition-transform shrink-0" style={{ transform: pOpen ? 'rotate(90deg)' : 'none' }} />
                          <MapPin size={12} className="text-[var(--color-ink)] shrink-0" />
                          <span className="text-[12.5px] text-[var(--color-ink)] truncate">{p.plot_name}</span>
                          {p.country && <span className="text-[11.5px] text-[var(--color-faint)]">{p.country}</span>}
                          <span className="ml-auto flex items-center gap-3 shrink-0">
                            <Share share={spend ? (p.spend_eur ?? 0) / spend : 0} tone="var(--color-sky)" />
                            <span className="tabular-nums text-[12px] text-[var(--color-mute)] w-20 text-right">{flow(p.spend_eur)}</span>
                          </span>
                        </button>
                        {pOpen && <Leaf plot={p} feeds={feeds ? feeds[p.top_hazard ?? ''] ?? [] : null} />}
                      </div>)
                  })}
                </div>)}
            </div>)
        })}
      </div>
    </div>
  )
}

// A plot's hazard score and where it comes from.
function Leaf({ plot, feeds }: { plot: Plot; feeds: Feed[] | null }) {
  return (
    <div className="ml-6 my-1.5 rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] p-2.5 space-y-2 text-[12px]">
      <div className="flex items-center gap-2 flex-wrap">
        <Gauge size={13} className="text-[var(--color-good)]" />
        <span className="text-[var(--color-mute)]">{plot.top_hazard ? hazardLabel(plot.top_hazard) : 'No hazard scored'}</span>
        {plot.hazard_score != null && <span className="tabular-nums text-[var(--color-ink)]">score {plot.hazard_score.toFixed(0)}</span>}
        {plot.reading && <span className="ml-auto"><StatusPill status={plot.reading.outcome} /></span>}
      </div>
      <Feeds feeds={feeds} />
    </div>
  )
}

function Feeds({ feeds }: { feeds: Feed[] | null }) {
  if (!feeds) return <div className="text-[var(--color-faint)]">Loading the feeds…</div>
  if (!feeds.length) return <div className="text-[var(--color-faint)]">No source feed named for this hazard</div>
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <Satellite size={12} className="text-[var(--color-sky)]" />
      {feeds.map(f => (
        <span key={f.name} className="inline-flex items-center gap-1.5 text-[11.5px] rounded-full border border-[var(--color-line-2)] px-2 py-0.5 text-[var(--color-mute)]">
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: feedTone(f) }} />{f.name}</span>))}
    </div>
  )
}

// One plot traced up: its feeds → its hazard score → the plot and its spend → the commodity's volume at risk → the figure.
function Chain({ plot, sum, feeds }: { plot: Plot; sum: Summary; feeds: Feed[] | null }) {
  const com = sum.commodities.find(c => c.commodity === plot.commodity)
  const steps = [
    { icon: Satellite, tone: 'var(--color-blue)', title: 'Data feeds', body: <Feeds feeds={feeds} /> },
    { icon: Gauge, tone: 'var(--color-good)', title: plot.top_hazard ? hazardLabel(plot.top_hazard) : 'Hazard score',
      value: plot.hazard_score != null ? `score ${plot.hazard_score.toFixed(0)}` : '—',
      body: plot.reading ? <StatusPill status={plot.reading.outcome} /> : null },
    { icon: MapPin, tone: 'var(--color-ink)', title: plot.plot_name, value: flow(plot.spend_eur), body: plot.country ? <span className="text-[var(--color-faint)]">{plot.country}</span> : null },
    { icon: Sprout, tone: 'var(--color-warn)', title: plot.commodity, value: flow(com?.volume_at_risk_eur ?? null) },
    { icon: FileBarChart, tone: 'var(--color-sky)', title: 'Volume at risk', value: flow(sum.rollup.volume_at_risk_eur) },
  ]
  return (
    <div>
      {steps.map((s, i) => (
        <div key={i} className="flex items-stretch gap-3">
          <div className="flex flex-col items-center">
            <span className="mt-3 inline-flex items-center justify-center w-6 h-6 rounded-full" style={{ background: `color-mix(in oklab, ${s.tone} 16%, transparent)`, color: s.tone }}><s.icon size={13} /></span>
            {i < steps.length - 1 && <span className="w-px flex-1 bg-[var(--color-line-2)]" />}
          </div>
          <div className="flex-1 card p-3 mb-2 space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-[13px] text-[var(--color-ink)]">{s.title}</span>
              {s.value && <span className="ml-auto tabular-nums text-[12.5px] text-[var(--color-ink)]">{s.value}</span>}
            </div>
            {s.body && <div className="text-[12px]">{s.body}</div>}
          </div>
        </div>))}
    </div>
  )
}
