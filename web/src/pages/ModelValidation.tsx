import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Activity, BookOpen, ChevronRight, LayoutGrid, Sprout } from 'lucide-react'
import { api } from '../lib/api'
import { bucketLabel, hazardLabel } from '../lib/labels'
import { pressable } from '../lib/pressable'
import { PageHeader, Card, StatGrid, SectionHead, Button } from '../components/ui'
import { StatusChip } from '../components/StatusChip'
import { Dialog, CloseButton } from '../components/Dialog'
import { Drawer } from '../components/Drawer'
import { DetailsBody, HEADING, InfoButton, MessageLine, messageDetails, type DetailSection, type Details, type Message } from '../components/Details'
import ReviewTabs from '../components/ReviewTabs'

// Model validation, to the UI standard (2026-10-16): each hazard score against what was observed — the event record
// for earthquakes and tropical cyclones, past harvests for crops, and every hazard's tests on the validation record —
// as charts and a matrix, read in one call from /v1/realized-exposure/model-validation. The method, the statistics and
// the record are one click away (Method and record); the server sends numbers, names and message codes.

type Band = 'VH' | 'H' | 'M' | 'L'
type Tone = 'good' | 'warn' | 'bad' | 'neutral'
interface Sample { h3_cell: string; lat: number; lon: number; score: number; observed_events: number }
interface BandRow { band: Band; n_cells: number; mean_events: number | null; pct_with_event: number | null; samples: Sample[] }
interface Checked {
  available: true; peril: string; name: string; source: string; near_field_km: number; n_cells_scored: number; n_events_observed: number
  first_year: number | null; last_year: number | null; spearman: number | null; auc: number | null; auc_withheld: boolean
  passed: boolean; gate_spearman: number; bands: BandRow[]; message: Message
}
type Peril = Checked | { available: false; peril: string; message: Message }
interface Fit {
  region: string; region_name: string | null; origin_name: string | null; crop: string | null; hazard_driver: string
  r2_oos: number; n_years: number | null; passed: boolean
  challenger: { challenger_r2_oos: number | null; verdict: string | null; corroborates_publish: boolean | null } | null
}
interface CropEvent { event: string; observed_shock_pct: number | null; model_shock_pct: number | null; passed: boolean }
interface Harvest {
  available: boolean; gate_r2_oos: number; n_fits: number; n_pass: number; years_min: number | null; years_max: number | null
  by_hazard: { hazard: string; fits: number; passed: number }[]; fits: Fit[]; events: CropEvent[]
}
type Design = 'same_record' | 'held_out' | 'independent' | 'harvests' | 'events'
type Tier = 'calibrated' | 'screening' | 'by_nature' | 'reference' | 'roadmap'
interface Cell { runs: number; passed: number; records: number; last: string }
interface Row { id: string; name: string; family_name: string; tier: Tier; tier_name: string; tier_message: Message; tests: Partial<Record<Design, Cell>> }
interface Summary { hazards: number; validated: number; tested: number; runs: number; passed: number; all_hazards_runs: number; first: string | null; last: string | null }
interface Coverage { designs: Design[]; rows: Row[]; summary: Summary }
interface Resp { perils: Peril[]; economic: Harvest; coverage: Coverage }

const BAND_COLOR: Record<Band, string> = { VH: 'var(--color-bad)', H: 'var(--scn-disorderly)', M: 'var(--scn-orderly)', L: 'var(--color-faint)' }
const DESIGN: Record<Design, { label: string; what: string }> = {
  same_record: { label: 'Same record', what: 'Tested against the observed record the score is built from: a check that the score is faithful to it, not that it predicts.' },
  held_out: { label: 'Held out in time', what: 'The score is rebuilt from earlier years only, then tested on what was observed in the years after.' },
  independent: { label: 'Independent record', what: 'Tested against an observed record that never enters the score: weather stations, mapped events, measured ground motion or losses.' },
  harvests: { label: 'Past harvests', what: 'Tested against observed crop yields in past seasons.' },
  events: { label: 'Named events', what: 'Real disasters replayed: the modelled production loss against the loss recorded.' },
}
// a tier's colour; its words (label and meaning) are the catalogue's coverage.tier.* — the Coverage page's own
const TIER_TONE: Record<Tier, Tone> = { calibrated: 'good', screening: 'warn', by_nature: 'neutral', reference: 'neutral', roadmap: 'neutral' }
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
const fmt2 = (n: number | null | undefined) => n == null ? '—' : n.toFixed(2)
const day = (iso: string | null) => iso ? new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) : '—'
const compact = (n: number) => n >= 10000 ? `${(n / 1000).toFixed(1)}k` : n.toLocaleString()
const span = (a: number | null, b: number | null) => a == null || b == null ? '—' : a === b ? `${a}` : `${a}–${b}`

const ABOUT = [
  { heading: HEADING.shows, body: 'How closely each hazard score matches what was observed: earthquakes and tropical cyclones against their event records, crop scores against past harvests, and every hazard’s tests on the validation record.' },
  { heading: HEADING.read, body: 'Green marks a result that clears its bar. A crop euro figure is published only where the score explains at least 40% of past yield swings; the other crops are held back. The table counts each hazard’s tests by design: tests that clear the bar, of all tests run.' },
  { heading: HEADING.sources, body: 'USGS earthquake catalogue; IBTrACS tropical-cyclone tracks; crop yields from FAOSTAT and Eurostat; the validation record of every test run on the platform. Each hazard’s standing comes from the platform’s hazard register.' },
  { heading: HEADING.limits, body: 'The event-record check is a consistency check: those scores are built from the same records, so it shows that a score is faithful to the record, not that it predicts. The table shows only the tests held on the validation record.' },
]

export default function ModelValidation() {
  const q = useQuery({ queryKey: ['model-validation'], queryFn: () => api.get<Resp>('/v1/realized-exposure/model-validation') })
  const [method, setMethod] = useState(false)
  const [row, setRow] = useState<Row | null>(null)
  const d = q.data
  const s = d?.coverage.summary
  return (
    <div className="fadeup space-y-6">
      <ReviewTabs />
      <PageHeader eyebrow="Assess · Model validation" title="Does the score hold up against what happened?" about={ABOUT}
        lead="Each hazard score, tested against observed events and harvests."
        actions={<Button variant="ghost" onClick={() => setMethod(true)}><BookOpen size={14} className="inline -mt-0.5 mr-1" />Method and record</Button>} />
      {q.isError ? <div className="text-[12.5px] text-[var(--color-warn)]">The results could not be loaded. Try again shortly.</div>
        : !d || !s ? <div className="text-[12.5px] text-[var(--color-faint)]">Running the checks…</div> : (<>
          <StatGrid cols={4} items={[
            { label: 'Hazards validated', value: `${s.validated} of ${s.hazards}`, sub: 'on the hazard register' },
            { label: 'Hazards tested', value: `${s.tested} of ${s.hazards}`, sub: 'on the validation record' },
            { label: 'Tests on record', value: s.runs.toLocaleString(), sub: `since ${day(s.first)}` },
            ...(d.economic.available ? [{ label: 'Crop euros published', value: `${d.economic.n_pass} of ${d.economic.n_fits}`, sub: 'crop and region tests' }] : []),
          ]} />
          <section className="space-y-3">
            <SectionHead icon={Activity}>Against the event record</SectionHead>
            <div className="grid gap-4 lg:grid-cols-2 items-start">
              {d.perils.map(p => p.available ? <RecordCard key={p.peril} p={p} />
                : <Card key={p.peril} className="p-5 text-[12.5px] text-[var(--color-mute)]"><MessageLine m={p.message} /></Card>)}
            </div>
          </section>
          {d.economic.available && (
            <section className="space-y-3">
              <SectionHead icon={Sprout}>Against past harvests</SectionHead>
              <HarvestCard e={d.economic} />
            </section>
          )}
          <section className="space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <SectionHead icon={LayoutGrid}>Every hazard</SectionHead>
              <InfoButton compact details={MATRIX_DETAILS} />
              <Link to="/coverage" className="ml-auto inline-flex items-center gap-1 text-[12px] text-[var(--color-sky)] hover:underline">Coverage by hazard<ChevronRight size={13} /></Link>
            </div>
            <Card className="p-0 overflow-hidden"><Matrix c={d.coverage} onRow={setRow} /></Card>
          </section>
        </>)}
      {method && d && <MethodDrawer d={d} onClose={() => setMethod(false)} />}
      {row && d && <HazardDetail r={row} designs={d.coverage.designs} onClose={() => setRow(null)} />}
    </div>
  )
}

function recordDetails(p: Checked): Details {
  const events = `${p.name}s`
  return {
    title: `${cap(events)} against their record`, sections: [
      { heading: HEADING.shows, body: `Every scored place is matched with the ${events} recorded within ${p.near_field_km} km of it, a distance sized to the hazard’s physical reach. Each event counts once per place.` },
      { heading: HEADING.read, body: `Ranking agreement (Spearman’s ρ) runs from −1 to 1: how closely the order of places by score follows their order by observed count. The check needs ${fmt2(p.gate_spearman)} or more, and a count that rises from one score band to the next. Hit separation (AUC) is the chance that a place with an event scored higher than a place without one; 0.5 is chance.` },
      { heading: HEADING.sources, body: `${p.source}, ${span(p.first_year, p.last_year)}: ${p.n_events_observed.toLocaleString()} events.` },
      { heading: HEADING.limits, body: `The score is built from the same record, so this shows that it is faithful to the record, not that it predicts.${p.auc_withheld ? ` Hit separation is not shown: ${events} reach nearly every place within ${p.near_field_km} km, so it would read close to 1 for any score.` : ''}` },
    ],
  }
}

function RecordCard({ p }: { p: Checked }) {
  const [examples, setExamples] = useState(false)
  const max = Math.max(0.01, ...p.bands.map(b => b.mean_events ?? 0))
  const top = p.bands.find(b => b.n_cells > 0)
  const events = `${p.name}s`
  return (
    <Card className="p-5 flex flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="display text-[19px] font-semibold text-[var(--color-ink)] m-0">{cap(events)}</h3>
          <div className="text-[12px] text-[var(--color-mute)] tabular-nums mt-0.5">{p.n_cells_scored.toLocaleString()} places · {span(p.first_year, p.last_year)}</div>
        </div>
        <span className="inline-flex items-center gap-1.5">
          <StatusChip label={p.message.label} tone={p.passed ? 'good' : 'warn'} />
          <InfoButton compact details={messageDetails(p.message)} />
        </span>
      </div>
      <div>
        <div className="grid grid-cols-[4.5rem_minmax(0,1fr)_3rem_3rem] gap-x-3 text-[11px] text-[var(--color-faint)] mb-1.5">
          <span>Score band</span><span>{cap(events)} per place</span><span className="text-right">Mean</span><span className="text-right">Hit</span>
        </div>
        <div className="space-y-1.5">
          {p.bands.map(b => (
            <div key={b.band} className="grid grid-cols-[4.5rem_minmax(0,1fr)_3rem_3rem] items-center gap-x-3 text-[12.5px] tabular-nums">
              <span className="text-[var(--color-mute)]">{bucketLabel(b.band)}</span>
              <div className="h-5 rounded bg-[var(--color-panel-2)] relative overflow-hidden">
                {b.n_cells > 0
                  ? <div className="absolute inset-y-0 left-0 rounded" style={{ width: `${Math.max(1.5, (100 * (b.mean_events ?? 0)) / max)}%`, background: BAND_COLOR[b.band] }} />
                  : <span className="absolute inset-0 flex items-center px-2 text-[11px] text-[var(--color-faint)]">No places</span>}
              </div>
              <span className="text-right text-[var(--color-ink)]">{b.n_cells ? b.mean_events : '—'}</span>
              <span className="text-right text-[var(--color-mute)]">{b.n_cells ? `${b.pct_with_event}%` : '—'}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 pt-3 border-t border-[var(--color-line)] text-[12px] text-[var(--color-mute)]">
        <span>Ranking agreement <b className="text-[var(--color-ink)] tabular-nums">{fmt2(p.spearman)}</b></span>
        <span>Hit separation <b className="text-[var(--color-ink)] tabular-nums">{p.auc_withheld ? 'not shown' : fmt2(p.auc)}</b></span>
        <InfoButton compact details={recordDetails(p)} />
        {top && top.samples.length > 0 && (
          <button type="button" onClick={() => setExamples(true)} className="ml-auto inline-flex items-center gap-1 text-[var(--color-sky)] hover:underline">Example places<ChevronRight size={13} /></button>
        )}
      </div>
      {examples && top && (
        <Dialog title={`Example places · ${bucketLabel(top.band)}`} onClose={() => setExamples(false)} className="max-w-lg">
          <table className="w-full text-[12.5px] tabular-nums">
            <thead><tr className="text-left text-[var(--color-mute)] border-b border-[var(--color-line)]">
              <th className="py-1.5 font-medium">Place</th><th className="font-medium text-right">Score</th><th className="font-medium text-right">{cap(events)} within {p.near_field_km} km</th>
            </tr></thead>
            <tbody>
              {top.samples.map(x => (
                <tr key={x.h3_cell} className="border-b border-[var(--color-line)]">
                  <td className="py-1.5 text-[var(--color-mute)]">{x.lat.toFixed(2)}, {x.lon.toFixed(2)}</td>
                  <td className="text-right">{x.score}</td>
                  <td className="text-right" style={{ color: x.observed_events > 0 ? 'var(--color-good)' : 'var(--color-warn)' }}>{x.observed_events}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Dialog>
      )}
    </Card>
  )
}

const harvestDetails = (e: Harvest): Details => ({
  title: 'Crop scores against past harvests', sections: [
    { heading: HEADING.shows, body: `Each crop’s hazard score in each growing region, tested against ${span(e.years_min, e.years_max)} years of observed yield. Each year is predicted without that year’s own harvest, so the test is out of sample. Yield never feeds the score.` },
    { heading: HEADING.read, body: `The bar is the share explained (out-of-sample r², Nash–Sutcliffe): the share of year-to-year yield swings the score explains. It can fall below zero when the score predicts worse than the average year. A euro figure is published only at ${fmt2(e.gate_r2_oos)} or more, the line on each bar. The blue tick is an independent second method (isotonic regression) tested the same way: Confirmed means it also clears the bar, Shape confirmed that it follows the same shape below the bar.` },
    { heading: HEADING.sources, body: 'Crop yields from FAOSTAT and Eurostat. The second method’s results are read from the validation record.' },
    { heading: HEADING.limits, body: 'A crop below the bar keeps its spend on the page, and its euro is withheld. Named events replay real crop disasters; an event without a clean recorded or modelled figure is shown as such, never estimated.' },
  ],
})

function FitRow({ f, gate }: { f: Fit; gate: number }) {
  const ch = f.challenger
  const c2 = ch?.challenger_r2_oos
  const place = f.region_name ?? f.origin_name ?? 'Region not named'
  const second = !f.passed || !ch ? null : ch.corroborates_publish ? { label: 'Confirmed', tone: 'good' as const }
    : ch.verdict === 'diverge' ? { label: 'Disputed', tone: 'warn' as const } : { label: 'Shape confirmed', tone: 'neutral' as const }
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-1 text-[12.5px]">
      <span className="w-full sm:w-64 truncate" title={place}>
        <span className="text-[var(--color-ink)]">{f.crop ?? hazardLabel(f.hazard_driver)}</span><span className="text-[var(--color-faint)]"> · {place}</span>
      </span>
      <div className="flex-1 min-w-[120px] h-4 rounded bg-[var(--color-panel-2)] relative">
        <div className="absolute inset-y-0 left-0 rounded" style={{ width: `${Math.max(1, 100 * Math.max(0, f.r2_oos))}%`, background: f.passed ? 'var(--color-good)' : 'var(--color-slate)' }} />
        <div className="absolute -top-0.5 -bottom-0.5 w-px bg-[var(--color-ink)] opacity-60" style={{ left: `${100 * gate}%` }} aria-hidden="true" />
        {c2 != null && <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-[3px] h-5 rounded-sm bg-[var(--color-sky)]" style={{ left: `${Math.max(0, Math.min(100, 100 * c2))}%` }} title={`Second method: ${c2.toFixed(2)}`} />}
      </div>
      <span className="w-11 text-right tabular-nums font-semibold" style={{ color: f.passed ? 'var(--color-good)' : 'var(--color-mute)' }}>{f.r2_oos.toFixed(2)}</span>
      <span className="w-28 text-right">{second && <StatusChip label={second.label} tone={second.tone} />}</span>
    </div>
  )
}

function eventChip(ev: CropEvent): { label: string; tone: Tone } {
  if (ev.model_shock_pct == null && ev.observed_shock_pct == null) return { label: 'No figures to compare', tone: 'neutral' }
  if (ev.model_shock_pct == null) return { label: 'No model figure', tone: 'neutral' }
  if (ev.observed_shock_pct == null) return { label: 'No recorded figure', tone: 'neutral' }
  return ev.passed ? { label: 'Reproduced', tone: 'good' } : { label: 'Not reproduced', tone: 'warn' }
}

function HarvestCard({ e }: { e: Harvest }) {
  const [held, setHeld] = useState(false)
  const pass = e.fits.filter(f => f.passed)
  const below = e.fits.filter(f => !f.passed)
  return (
    <Card className="p-5 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusChip label={`${e.n_pass} of ${e.n_fits} published`} tone={e.n_pass ? 'good' : 'neutral'} />
        {e.by_hazard.map(h => <StatusChip key={h.hazard} label={`${hazardLabel(h.hazard)} · ${h.passed} of ${h.fits}`} tone="neutral" />)}
        <span className="ml-auto text-[12px] text-[var(--color-faint)] tabular-nums">{span(e.years_min, e.years_max)} years of harvests</span>
      </div>
      <div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11.5px] text-[var(--color-mute)] mb-2">
          <span className="inline-flex items-center gap-1.5"><span className="w-3 h-2 rounded-sm bg-[var(--color-good)]" />Share explained</span>
          <span className="inline-flex items-center gap-1.5"><span className="w-px h-3 bg-[var(--color-ink)] opacity-60" />Publish bar {fmt2(e.gate_r2_oos)}</span>
          <span className="inline-flex items-center gap-1.5"><span className="w-[3px] h-3 rounded-sm bg-[var(--color-sky)]" />Second method</span>
          <InfoButton compact details={harvestDetails(e)} />
        </div>
        {pass.map(f => <FitRow key={`${f.region}:${f.hazard_driver}`} f={f} gate={e.gate_r2_oos} />)}
        {below.length > 0 && (
          <button type="button" onClick={() => setHeld(h => !h)} aria-expanded={held} className="mt-2 inline-flex items-center gap-1 text-[12.5px] text-[var(--color-mute)] hover:text-[var(--color-ink)]">
            <ChevronRight size={14} className={held ? 'rotate-90 transition' : 'transition'} />{below.length} below the bar, euro withheld
          </button>
        )}
        {held && <div className="mt-1 opacity-85">{below.map(f => <FitRow key={`${f.region}:${f.hazard_driver}`} f={f} gate={e.gate_r2_oos} />)}</div>}
      </div>
      {e.events.length > 0 && (
        <div className="pt-4 border-t border-[var(--color-line)]">
          <div className="text-[13px] font-semibold text-[var(--color-ink)] mb-2">Named events</div>
          <div className="space-y-1.5">
            {e.events.map(ev => {
              const c = eventChip(ev)
              return (
                <div key={ev.event} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12.5px]">
                  <span className="text-[var(--color-ink)]">{ev.event}</span>
                  <span className="flex-1" />
                  {ev.model_shock_pct != null && ev.observed_shock_pct != null && (
                    <span className="tabular-nums text-[var(--color-mute)]">Model {ev.model_shock_pct.toFixed(1)}% · Recorded {ev.observed_shock_pct.toFixed(1)}%</span>
                  )}
                  <StatusChip label={c.label} tone={c.tone} />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </Card>
  )
}

const MATRIX_DETAILS: Details = {
  title: 'Every hazard', sections: [
    { heading: HEADING.shows, body: 'Each hazard on the platform’s register, with its standing and the tests the validation record holds for it, by how each test was designed.' },
    { heading: HEADING.read, body: <ul className="m-0 pl-4 space-y-1">{(Object.keys(DESIGN) as Design[]).map(k => <li key={k}><b>{DESIGN[k].label}</b>: {DESIGN[k].what}</li>)}</ul> },
    { heading: HEADING.limits, body: 'A cell reads tests that clear their bar, of all tests run; green where at least one clears it. A dot means no test of that design is on record. Select a hazard for its standing and its tests.' },
  ],
}

function CellChip({ c }: { c?: Cell }) {
  if (!c) return <span className="text-[var(--color-faint)]" aria-label="No test">·</span>
  const tone = c.passed > 0 ? 'var(--color-good)' : 'var(--color-slate)'
  return (
    <span className="inline-block min-w-[3.25rem] rounded-full px-2 py-0.5 text-[11.5px] font-medium tabular-nums"
      style={{ color: tone, background: `color-mix(in oklab, ${tone} 13%, transparent)` }}>{compact(c.passed)}/{compact(c.runs)}</span>
  )
}

function Matrix({ c, onRow }: { c: Coverage; onRow: (r: Row) => void }) {
  const groups: { label: string; rows: Row[] }[] = []
  for (const r of c.rows) {
    const g = groups.find(x => x.label === r.family_name)
    if (g) g.rows.push(r)
    else groups.push({ label: r.family_name, rows: [r] })
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12.5px]" style={{ minWidth: 760 }}>
        <thead>
          <tr className="text-left text-[var(--color-mute)] border-b border-[var(--color-line)]">
            <th className="py-2 pl-4 pr-3 font-medium">Hazard</th>
            <th className="pr-3 font-medium">Standing</th>
            {c.designs.map(dz => <th key={dz} className="px-2 font-medium text-center">{DESIGN[dz].label}</th>)}
          </tr>
        </thead>
        <tbody>
          {groups.map(g => (
            <Fragment key={g.label}>
              <tr><td colSpan={2 + c.designs.length} className="pt-3 pb-1 pl-4 text-[11px] font-semibold uppercase tracking-[0.08em] text-[var(--color-faint)]">{g.label}</td></tr>
              {g.rows.map(r => (
                <tr key={r.id} {...pressable(() => onRow(r), { row: true })} className="border-b border-[var(--color-line)] cursor-pointer hover:bg-[var(--color-panel-2)]">
                  <td className="py-1.5 pl-4 pr-3 text-[var(--color-ink)] max-w-[260px] truncate" title={r.name}>{r.name}</td>
                  <td className="pr-3"><StatusChip label={r.tier_name} tone={TIER_TONE[r.tier]} /></td>
                  {c.designs.map(dz => <td key={dz} className="px-2 text-center"><CellChip c={r.tests[dz]} /></td>)}
                </tr>
              ))}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function HazardDetail({ r, designs, onClose }: { r: Row; designs: Design[]; onClose: () => void }) {
  const tested = designs.filter(dz => r.tests[dz])
  const sections: DetailSection[] = [
    { heading: 'Standing', body: <div className="space-y-1.5"><StatusChip label={r.tier_name} tone={TIER_TONE[r.tier]} /><div>{messageDetails(r.tier_message).sections[0]?.body}</div></div> },
    { heading: 'Tests on record', body: tested.length === 0 ? 'No test of this hazard is on the validation record.' : (
      <ul className="m-0 pl-4 space-y-1.5">
        {tested.map(dz => {
          const t = r.tests[dz]!
          return <li key={dz}><b>{DESIGN[dz].label}</b>: {t.runs.toLocaleString()} {t.runs === 1 ? 'test' : 'tests'}, {t.passed.toLocaleString()} clear the bar, against {t.records.toLocaleString()} observed {t.records === 1 ? 'record' : 'records'}. Last run {day(t.last)}.</li>
        })}
      </ul>
    ) },
  ]
  return (
    <Dialog title={r.name} onClose={onClose} className="max-w-xl">
      <DetailsBody sections={sections} />
      <Link to="/coverage" className="mt-4 inline-flex items-center gap-1 text-[12.5px] text-[var(--color-sky)] hover:underline">Where this hazard is validated<ChevronRight size={13} /></Link>
    </Dialog>
  )
}

function MethodDrawer({ d, onClose }: { d: Resp; onClose: () => void }) {
  const s = d.coverage.summary
  const e = d.economic
  const h = (t: string) => <h4 className="text-[12px] font-semibold uppercase tracking-[0.08em] text-[var(--color-mute)] mt-6 mb-2">{t}</h4>
  const item = (t: string, b: string) => <div key={t}><div className="text-[13px] font-semibold text-[var(--color-ink)]">{t}</div><div className="text-[13px] text-[var(--color-mute)] leading-relaxed">{b}</div></div>
  const near = d.perils.filter((p): p is Checked => p.available).map(p => `${p.near_field_km} km for ${p.name}s`).join(' and ')
  return (
    <Drawer label="Method and record" onClose={onClose} className="w-full max-w-lg h-full overflow-y-auto bg-[var(--color-bg-2)] border-l border-[var(--color-line)] p-5">
      <div className="flex items-center justify-between"><div className="text-[16px] font-semibold text-[var(--color-ink)]">Method and record</div><CloseButton onClick={onClose} /></div>
      {h('Two live tests')}
      <div className="space-y-3">
        {item('Event record', `Every scored place is matched with the observed events within the hazard’s physical reach: ${near}. The scores are built from the same records, so this checks faithfulness, not prediction.`)}
        {e.available && item('Past harvests', `Each crop’s score is tested against ${span(e.years_min, e.years_max)} years of observed yield in each growing region, out of sample. Yield never feeds the score, so this tests prediction.`)}
      </div>
      {h('The statistics')}
      <div className="space-y-3">
        {item('Ranking agreement (ρ)', 'Spearman’s rank correlation between the score and the observed outcome, from −1 to 1. A ranking test needs 0.35 or more.')}
        {item('Share explained (r²)', `The share of year-to-year yield swings the score explains, measured out of sample (Nash–Sutcliffe). It can fall below zero. A crop euro is published only at ${fmt2(e.gate_r2_oos)} or more.`)}
        {item('Hit separation (AUC)', 'The chance that a place with an event scored higher than a place without one. 0.5 is chance, 1 is perfect.')}
        {item('Fidelity score', 'The platform also states share explained × 100 as Ground-Truth Fidelity (Φ), and ranking agreement × 100 as Ranking Fidelity. Below the bar a result is held; above it, it reads Directional, Reliable or Strong.')}
      </div>
      {h('The validation record')}
      <div className="space-y-3">
        {item(`${s.runs.toLocaleString()} tests since ${day(s.first)}`, `${s.passed.toLocaleString()} of them clear their bar. Each test is kept unchanged once written, with the observed record it was tested against. Crop tests are re-run in each calibration batch, so one crop record can hold many tests.`)}
        {s.all_hazards_runs > 0 && item('Outside the table', `${s.all_hazards_runs} ${s.all_hazards_runs === 1 ? 'test covers' : 'tests cover'} every crop hazard together, so it sits under no single hazard.`)}
        {item('Last test', day(s.last))}
      </div>
    </Drawer>
  )
}
