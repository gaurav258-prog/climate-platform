import { useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, BookOpen, Database, Euro, Gauge, MapPin, Radio, type LucideIcon } from 'lucide-react'
import { api } from '../lib/api'
import { flow } from '../lib/money'
import { bucketLabel, hazardLabel, scenarioLabel } from '../lib/labels'
import { PageHeader, Card, Button } from '../components/ui'
import { StatusChip } from '../components/StatusChip'
import { HEADING, InfoButton, type Details, type Message } from '../components/Details'
import { Drawer } from '../components/Drawer'
import { CloseButton } from '../components/Dialog'
import SectionTabs, { DATA_TABS } from '../components/SectionTabs'
import SeasonalArrears from '../components/SeasonalArrears'
import PricePressure from '../components/PricePressure'

// How agriculture scores are produced, to the UI standard (2026-10-16): one flow on the main screen — what goes in,
// what scoring makes of the plots, the euros — read in one call from /v1/supply/foundation; the sources, the method
// and what every score keeps are one click away, under About our data.

type State = 'fresh' | 'due_soon' | 'overdue' | 'failed' | 'on_demand' | 'untracked'
type Band = 'L' | 'M' | 'H' | 'VH'
interface Source { code: string; message: Message; state: State; last_update: string | null; feeds: number }
interface HazardRow { hazard: string; plots: number; bands: Record<Band, number>; live_plots: number }
interface Scores { plots: number; crops: number; spend_eur: number; hazards: HazardRow[]; scenarios: string[]; years: string[]; cell_km2: number }
interface Money { spend_eur: number; volume_at_risk_eur: number; published_spend_eur: number; held_spend_eur: number; pending_spend_eur: number; crops: number; published_crops: number; held_crops: number; pending_crops: number }
interface Foundation { sources: Source[]; scores: Scores; money: Money }

const STATE: Record<State, { label: string; tone: 'good' | 'warn' | 'bad' | 'neutral' }> = {
  fresh: { label: 'Up to date', tone: 'good' }, due_soon: { label: 'Update due', tone: 'warn' },
  overdue: { label: 'Overdue', tone: 'bad' }, failed: { label: 'Last update failed', tone: 'bad' },
  on_demand: { label: 'Read at each check', tone: 'neutral' }, untracked: { label: 'No update recorded', tone: 'neutral' },
}
const TONE = { good: 'var(--color-good)', warn: 'var(--color-warn)', bad: 'var(--color-bad)', neutral: 'var(--color-slate)' }
const BANDS: { k: Band; color: string }[] = [
  { k: 'L', color: 'var(--color-faint)' }, { k: 'M', color: 'var(--scn-orderly)' },
  { k: 'H', color: 'var(--scn-disorderly)' }, { k: 'VH', color: 'var(--color-bad)' },
]
const day = (iso: string | null) => iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
const crops = (n: number) => `${n} ${n === 1 ? 'crop' : 'crops'}`
const list = (xs: string[]) => xs.length < 2 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`
const NUMBER = ['no', 'one', 'two', 'three', 'four', 'five', 'six']
const SOURCE_HEADING = { what: 'What it holds', why: 'What it is used for' } as const
// a source's server message (agri.data.source.*), under the headings a source reads by
const sourceDetails = (src: Source): Details => ({
  title: src.message.label,
  sections: (['what', 'why'] as const).filter(k => src.message.detail?.[k]).map(k => ({ heading: SOURCE_HEADING[k], body: src.message.detail![k] })),
})

const ABOUT = [
  { heading: HEADING.shows, body: 'How your sourcing plots and our climate, crop, forest and price data become a risk score for each plot, and then a euro figure for your sourcing book.' },
  { heading: HEADING.read, body: 'Read from left to right. Each plot is scored from 0 to 100 for each agriculture hazard; the bars show your plots by risk band. Each crop’s tested sensitivity then turns the scores into the volume at risk, priced at your spend.' },
  { heading: HEADING.sources, body: 'The climate, crop, forest and price sources, and how current each one is, are listed under About our data.' },
  { heading: HEADING.limits, body: 'A euro figure is published only for a crop whose model passed its test on past harvests. For every other crop the spend is shown and the euro withheld. Price pressure uses observed prices only; it is not a forecast.' },
]

export default function DataFoundation() {
  const q = useQuery({ queryKey: ['agri-foundation'], queryFn: () => api.get<Foundation>('/v1/supply/foundation') })
  const [about, setAbout] = useState(false)
  const d = q.data
  return (
    <div className="fadeup space-y-6">
      <SectionTabs tabs={DATA_TABS} />
      <PageHeader eyebrow="Agriculture · Data sources" title="How agriculture scores are produced" about={ABOUT}
        lead="Your plots and our data, turned into scores and euros."
        actions={<Button variant="ghost" onClick={() => setAbout(true)}><BookOpen size={14} className="inline -mt-0.5 mr-1" />About our data</Button>} />
      {q.isError ? <div className="text-[12.5px] text-[var(--color-warn)]">The figures could not be loaded. Try again shortly.</div>
        : !d ? <div className="text-[12.5px] text-[var(--color-faint)]">Loading…</div> : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1.2fr)_auto_minmax(0,1fr)] items-stretch">
            <Inputs d={d} onAbout={() => setAbout(true)} />
            <Arrow />
            <Scored s={d.scores} />
            <Arrow />
            <Euros m={d.money} />
          </div>
        )}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2 items-start">
        <PricePressure />
        <SeasonalArrears />
      </div>
      {about && d && <AboutData d={d} onClose={() => setAbout(false)} />}
    </div>
  )
}

function Arrow() {
  return <div className="flex items-center justify-center text-[var(--color-faint)]"><ArrowRight size={18} className="rotate-90 lg:rotate-0" /></div>
}

function Stage({ step, icon: Icon, title, children }: { step: string; icon: LucideIcon; title: string; children: ReactNode }) {
  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <span className="w-6 h-6 rounded-full grid place-items-center text-[11px] font-semibold bg-[var(--color-panel-2)] text-[var(--color-sky)]">{step}</span>
        <Icon size={15} className="text-[var(--color-sky)]" />
        <h2 className="text-[14px] font-semibold text-[var(--color-ink)] m-0">{title}</h2>
      </div>
      {children}
    </Card>
  )
}

function Inputs({ d, onAbout }: { d: Foundation; onAbout: () => void }) {
  const s = d.scores
  return (
    <Stage step="1" icon={MapPin} title="What goes in">
      <div>
        <div className="text-[12px] text-[var(--color-mute)]">Your sourcing plots</div>
        <div className="display text-[30px] leading-none tabular-nums mt-1">{s.plots.toLocaleString()}</div>
        <div className="text-[12px] text-[var(--color-faint)] mt-1 tabular-nums">{crops(s.crops)} · {flow(s.spend_eur)} a year</div>
      </div>
      <div>
        <div className="flex items-center gap-1.5 text-[12px] text-[var(--color-mute)] mb-2"><Database size={13} />Our data</div>
        <ul className="space-y-1.5 m-0 p-0 list-none">
          {d.sources.map(src => (
            <li key={src.code} className="flex items-center gap-2 text-[12.5px]">
              <span className="w-2 h-2 rounded-full shrink-0" title={STATE[src.state].label} style={{ background: TONE[STATE[src.state].tone] }} />
              <span className="text-[var(--color-ink)]">{src.message.label}</span>
              <InfoButton compact details={sourceDetails(src)} />
            </li>
          ))}
        </ul>
        <button type="button" onClick={onAbout} className="mt-2 text-[12px] text-[var(--color-sky)] hover:underline">How current each source is</button>
      </div>
    </Stage>
  )
}

function BandBar({ bands, of }: { bands: Record<Band, number>; of: number }) {
  return (
    <div className="h-2.5 rounded-full bg-[var(--color-panel-2)] flex overflow-hidden" role="img"
      aria-label={BANDS.map(b => `${bucketLabel(b.k)} ${bands[b.k]}`).join(', ')}>
      {BANDS.map(b => bands[b.k] > 0 && <div key={b.k} style={{ width: `${(bands[b.k] / Math.max(1, of)) * 100}%`, background: b.color }} title={`${bucketLabel(b.k)}: ${bands[b.k]}`} />)}
    </div>
  )
}

function Scored({ s }: { s: Scores }) {
  return (
    <Stage step="2" icon={Gauge} title="Scored for each hazard">
      {s.hazards.length === 0 ? <div className="text-[12.5px] text-[var(--color-faint)]">No plot is scored yet.</div> : (
        <div className="space-y-3">
          {s.hazards.map(h => (
            <div key={h.hazard}>
              <div className="flex items-baseline justify-between gap-2 text-[12.5px] mb-1">
                <span className="text-[var(--color-ink)]">{hazardLabel(h.hazard)}</span>
                <span className="flex items-center gap-2 text-[var(--color-faint)] tabular-nums">
                  {h.live_plots > 0 && <span className="inline-flex items-center gap-1 text-[var(--color-sky)]" title={`Live readings at ${h.live_plots} plots`}><Radio size={12} />Live</span>}
                  {h.plots} of {s.plots} plots
                </span>
              </div>
              <BandBar bands={h.bands} of={s.plots} />
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11.5px] text-[var(--color-mute)]">
        {BANDS.map(b => <span key={b.k} className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-sm" style={{ background: b.color }} />{bucketLabel(b.k)}</span>)}
      </div>
      {s.years.length > 0 && (
        <div className="mt-auto flex flex-wrap items-center gap-1.5 text-[12px] text-[var(--color-mute)]">
          Also scored for {s.years.join(' · ')}
          <InfoButton compact details={{ title: 'Climate scenarios', sections: [
            { heading: HEADING.shows, body: `Each plot is also scored for ${list(s.years)} under ${NUMBER[s.scenarios.length] ?? s.scenarios.length} climate scenarios: ${list(s.scenarios.map(scenarioLabel))}.` },
          ] }} />
        </div>
      )}
    </Stage>
  )
}

function Euros({ m }: { m: Money }) {
  const parts = [
    { k: 'published', label: `Published · ${crops(m.published_crops)}`, v: m.published_spend_eur, color: 'var(--color-good)' },
    { k: 'held', label: `Euro withheld · ${crops(m.held_crops)}`, v: m.held_spend_eur, color: 'var(--color-warn)' },
    { k: 'pending', label: `Not scored yet · ${crops(m.pending_crops)}`, v: m.pending_spend_eur, color: 'var(--color-slate)' },
  ].filter(p => p.v > 0)
  return (
    <Stage step="3" icon={Euro} title="In euros">
      <div>
        <div className="flex items-center gap-1.5 text-[12px] text-[var(--color-mute)]">Volume at risk today
          <InfoButton compact details={{ title: 'Volume at risk', sections: [
            { heading: HEADING.shows, body: 'The volume you pay for that the hazard scores say will not arrive, priced at your spend.' },
            { heading: HEADING.read, body: `It covers the ${flow(m.published_spend_eur)} of spend on crops whose model passed its test on past harvests.` },
          ] }} /></div>
        <div className="display text-[30px] leading-none tabular-nums mt-1">{flow(m.volume_at_risk_eur)}</div>
        <div className="text-[12px] text-[var(--color-faint)] mt-1 tabular-nums">on {flow(m.published_spend_eur)} of spend with a tested crop model</div>
      </div>
      <div>
        <div className="h-3 rounded-full bg-[var(--color-panel-2)] flex overflow-hidden" role="img" aria-label="Spend by what is published">
          {parts.map(p => <div key={p.k} style={{ width: `${(p.v / Math.max(1, m.spend_eur)) * 100}%`, background: p.color }} />)}
        </div>
        <ul className="mt-2 space-y-1 m-0 p-0 list-none">
          {parts.map(p => (
            <li key={p.k} className="flex items-center justify-between gap-3 text-[12px]">
              <span className="inline-flex items-center gap-1.5 text-[var(--color-mute)]"><span className="w-2 h-2 rounded-sm" style={{ background: p.color }} />{p.label}
                {p.k === 'held' && <InfoButton compact details={{ title: 'Euro withheld', sections: [
                  { heading: HEADING.shows, body: 'These crops are scored and their spend is mapped, but their model has not passed a test on past harvests at every origin you source them from, so no euro figure is published for them.' },
                  { heading: HEADING.read, body: 'Each crop’s test and its result open from See each crop.' },
                ] }} />}
              </span>
              <span className="tabular-nums text-[var(--color-ink)]">{flow(p.v)}</span>
            </li>
          ))}
        </ul>
      </div>
      <Link to="/cogs" className="mt-auto text-[12px] text-[var(--color-sky)] hover:underline">See each crop</Link>
    </Stage>
  )
}

function AboutData({ d, onClose }: { d: Foundation; onClose: () => void }) {
  const s = d.scores
  const h = (t: string) => <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] mt-6 mb-2">{t}</h4>
  const live = s.hazards.filter(x => x.live_plots > 0)
  const steps = [
    { t: 'Locate', b: `Each plot is placed in a hexagonal grid cell of about ${s.cell_km2} km² and takes the scores of its cell.` },
    { t: 'Score', b: `The cell is scored from 0 to 100 for ${list(s.hazards.map(x => hazardLabel(x.hazard).toLowerCase()))}: for today${s.years.length ? `, and for ${list(s.years)} under ${NUMBER[s.scenarios.length] ?? s.scenarios.length} climate scenarios` : ''}. Drought and soil water are read over the crop’s own growing season where it is known.` },
    { t: 'Price', b: 'Each crop’s tested sensitivity turns the score into lost volume, priced at your spend. A crop without a passed test keeps its spend on the page, and its euro is withheld.' },
  ]
  const keeps = [
    { t: 'Kept, never overwritten', b: 'A new score is added beside the one it replaces, and both stay on record with the dates they applied.' },
    { t: 'Traceable', b: 'Each score records the model that made it and the date of the data it was made from.' },
    ...(live.length ? [{ t: 'Live where available', b: `New observations update live readings: ${list(live.map(x => `${hazardLabel(x.hazard).toLowerCase()} at ${x.live_plots} of your plots`))}.` }] : []),
  ]
  return (
    <Drawer label="About our data" onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-center justify-between"><div className="text-[16px] font-semibold text-[var(--color-ink)]">About our data</div><CloseButton onClick={onClose} /></div>
      {h('Data sources')}
      <div className="space-y-3">
        {d.sources.map(src => (
          <div key={src.code} className="rounded-lg border border-[var(--color-line-2)] p-3">
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-[13px] font-semibold text-[var(--color-ink)]">{src.message.label}</span>
              <StatusChip label={STATE[src.state].label} tone={STATE[src.state].tone} />
            </div>
            <dl className="m-0 space-y-1.5 text-[13px] leading-relaxed">
              {sourceDetails(src).sections.map(x => (
                <div key={x.heading}><dt className="text-[11.5px] text-[var(--color-faint)]">{x.heading}</dt><dd className="m-0 text-[var(--color-ink)]">{x.body}</dd></div>
              ))}
            </dl>
            <div className="text-[11.5px] text-[var(--color-faint)] mt-2">Last updated {day(src.last_update)}</div>
          </div>
        ))}
      </div>
      {h('How a score is made')}
      <ol className="space-y-3 m-0 p-0 list-none">
        {steps.map((x, i) => (
          <li key={x.t} className="flex gap-3">
            <span className="w-6 h-6 shrink-0 rounded-full grid place-items-center text-[11px] font-semibold bg-[var(--color-panel-2)] text-[var(--color-sky)]">{i + 1}</span>
            <div><div className="text-[13px] font-semibold text-[var(--color-ink)]">{x.t}</div><div className="text-[13px] text-[var(--color-mute)] leading-relaxed">{x.b}</div></div>
          </li>
        ))}
      </ol>
      {h('What every score keeps')}
      <div className="space-y-2.5">
        {keeps.map(x => <div key={x.t}><div className="text-[13px] font-semibold text-[var(--color-ink)]">{x.t}</div><div className="text-[13px] text-[var(--color-mute)] leading-relaxed">{x.b}</div></div>)}
      </div>
    </Drawer>
  )
}
